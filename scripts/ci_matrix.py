"""CI's jobs (``.github/workflows/tests.yml``'s first job, Step 4.4dx5): the rows of the pure and the vanilla tier's
matrices a push or a pull request runs, each a JSON list on a line of ``$GITHUB_OUTPUT`` (``pure=``, ``vanilla=``).

    uv run --locked python -I scripts/ci_matrix.py     (it reads GITHUB_EVENT_NAME, GITHUB_REPOSITORY and GITHUB_REF)

The pure tier (``-m "not vanilla"``) runs once on each runner, every push and pull request. The vanilla tier
(``-m vanilla``) runs only on a push to main or to a lane branch (``p2/*``) of this repository, the vanilla job's own
``if:`` (D1123), each runner's in parts at once, a job each (``--shard``, ``scripts/ci_shards.py``). GitHub runs 5
macOS jobs at once here, and the pure job's two macOS rows made a push's 7: two of them waited 20-33 min for a free
one, on the run's critical path (runs 42198913490, 42222637371 and 42313664434). So on a push that runs the vanilla
tier each macOS runner's part 1 runs its pure tier first (its row's ``pure``: the pure tier's workers), before the
key or an image is on the runner, and scripts/ci_shards.py gives that part less of the vanilla tier by the pure
tier's seconds (``tests/ci_durations.json``'s ``head``): the pure job runs only Windows' and Linux's.

A lane branch whose name ends in a runner's word (:data:`NAMED`: ``p2/4.4ci47-webkit-arm64``) runs only that runner's
rows and Linux's pure tier (Step 4.4dx9, D1123's scope): two lanes' 7 macOS jobs each sat on main's 5 slots, and one
waited 44-121 min. Any other lane branch and main run every row, so main still runs everything before a release. It
prints the rows it picked, labels and numbers only."""

from __future__ import annotations

import json
import os
import sys

REPOSITORY = "Azurik-Modding-Hub/AzurKit"
RUNNERS = {
    # label: (its image, the pure tier's workers, the vanilla tier's workers, the vanilla tier's parts)
    # The pure tier holds no image: a Mac on Apple Silicon has 3 cores and about 4.4 GiB to spare, the others 4 and
    # 11-14. The serial vanilla tier's lowest free memory, of what was free at its most (GiB, scripts/ci_resources.py's
    # lines): Apple Silicon 1.1 of 4.4 and Linux 2.0-2.6 of 13.9, near that often, so one worker each; Intel 5.6 of
    # 11.0 and Windows 5.2-5.3 of 13.2, seldom near it, so two. Whole, the vanilla tier took Intel 2:28-2:56 of tests,
    # Apple Silicon 1:52-2:08, Windows 1:02-1:26 and Linux 1:26-1:28 (runs on 899cf05, bde5dae, b33204e and da30856),
    # each job's setup and images 6-14 min more: so 3, 2, 2 and 2 parts (Step 4.4ci35), about an hour each, no part
    # ending before its longest test (Intel's variant case, 44 min). The macOS ones make GitHub's 5 at once.
    "macos-x86_64": ("macos-15-intel", 3, 2, 3),
    "macos-arm64": ("macos-15", 2, 1, 2),
    "windows-x86_64": ("windows-latest", 3, 2, 2),
    "linux-x86_64": ("ubuntu-latest", 3, 1, 2),
}
NAMED = {"arm64": "macos-arm64", "intel": "macos-x86_64", "windows": "windows-x86_64", "linux": "linux-x86_64"}
"""The last word of a lane branch's name that picks its runner."""
LINUX = "linux-x86_64"   # whose pure tier, the quickest, a lane named for another runner runs too
FOLDED = frozenset(label for label, (image, *_) in RUNNERS.items() if image.startswith("macos-"))
"""The runners whose part 1 runs their pure tier on a push that runs the vanilla tier."""


def vanilla(event: str, repository: str, ref: str) -> bool:
    """Whether the vanilla tier runs: tests.yml's vanilla job's ``if:``, which alone guards the game data's key."""
    return (event == "push" and repository == REPOSITORY
            and (ref == "refs/heads/main" or ref.startswith("refs/heads/p2/")))


def rows(event: str, repository: str, ref: str) -> dict[str, list[dict]]:
    """``{"pure": rows, "vanilla": rows}``, each row a matrix entry: ``os``, ``label`` and ``workers``, and a vanilla
    row's ``shard`` and ``shards`` (part 1 of a :data:`FOLDED` runner's also ``pure``, its pure tier's workers); a lane
    branch named for a runner (:data:`NAMED`) gets that runner's rows and :data:`LINUX`'s pure tier."""
    runs = vanilla(event, repository, ref)
    named = NAMED.get(ref.rpartition("-")[2]) if runs and ref.startswith("refs/heads/p2/") else None
    pure_on, vanilla_on = ({named, LINUX}, {named}) if named else (RUNNERS.keys(), RUNNERS.keys())
    return {"pure": [{"os": image, "label": label, "workers": pure} for label, (image, pure, *_) in RUNNERS.items()
                     if label in pure_on and not (runs and label in FOLDED)],
            "vanilla": [{"os": image, "label": label, "workers": workers, "shard": k, "shards": parts}
                        | ({"pure": pure} if k == 1 and label in FOLDED else {})
                        for label, (image, pure, workers, parts) in RUNNERS.items() if runs and label in vanilla_on
                        for k in range(1, parts + 1)]}


def _named(row: dict) -> str:
    return (row["label"] + (f" {row['shard']} of {row['shards']}" if "shard" in row else "")
            + (" after its pure tier" if "pure" in row else ""))


def main() -> int:
    picked = rows(os.environ.get("GITHUB_EVENT_NAME", ""), os.environ.get("GITHUB_REPOSITORY", ""),
                  os.environ.get("GITHUB_REF", ""))
    if out := os.environ.get("GITHUB_OUTPUT"):
        with open(out, "a", encoding="utf-8") as f:
            f.writelines(f"{kind}={json.dumps(entries, separators=(',', ':'))}\n" for kind, entries in picked.items())
    for kind, entries in picked.items():
        print(f"{kind}: {', '.join(map(_named, entries)) or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
