"""Write ``tests/provenance/jtcpp_lines.txt``: a fingerprint of every line of
the Modkit files whose ``NOTICE.md`` credits lines to JTCPP, including the
files since removed.

    uv run --locked python scripts/provenance_fingerprints.py --modkit PATH [--ref REF]

Each file is read as it was added (closest to his code) and as it last stood
at REF, from Modkit's git objects; Modkit's checkout is never read or
changed. A line counts once it is stripped, if it has 25 or more characters
and isn't a comment: the count Modkit's ``NOTICE.md`` uses. A fingerprint is
the line's ``sha256[:16]``, so his code is never copied here.
``tests/test_provenance.py`` fails on a tracked file that shares 5 or more
of these lines (NOTICE's threshold).
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "tests" / "provenance" / "jtcpp_lines.txt"
CREDITED = (   # Modkit's NOTICE.md: the files with his lines, then those that held them and are gone
    "azurik_mod/config/keyed_tables.py", "azurik_mod/config/schema.json", "azurik_mod/cli.py", "gui/widgets.py",
    "azurik_mod/patching/mod_values.py", "azurik_mod/randomizer/commands.py", "gui/backend.py", "gui/models.py",
    "azurik_mod/xbr/sections.py",
    "azurik_mod/randomizer/parse_level_toc.py", "azurik_mod/config/registry.json",
    "azurik_mod/randomizer/level_editor.py", "gui/pages/entity_editor.py", "tests/test_entity_editor_keyed_flaps.py",
    "tests/test_entity_editor.py", "azurik_mod/randomizer/solver.py", "azurik_mod/randomizer/logic_db.json",
    "azurik_mod/randomizer/shufflers.py",
)
MIN_CHARS = 25


def lines(text: str) -> set[str]:
    """The lines that count: stripped, 25 characters or more, not a comment."""
    return {s for s in (line.strip() for line in text.splitlines())
            if len(s) >= MIN_CHARS and not s.startswith(("#", "//"))}


def fingerprint(line: str) -> str:
    return hashlib.sha256(line.encode("utf-8")).hexdigest()[:16]


def read(path: Path = OUT) -> set[str]:
    return {s for s in path.read_text(encoding="utf-8").splitlines() if s and not s.startswith("#")}


def _git(modkit: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(modkit), *args], capture_output=True, text=True, check=True).stdout


def versions(modkit: Path, ref: str, rel: str) -> list[str]:
    """``<commit>:<rel>`` for the version that added ``rel`` and the last one at ``ref``."""
    added = _git(modkit, "log", "--diff-filter=A", "--format=%H", ref, "--", rel).split()[-1]
    gone = _git(modkit, "log", "-1", "--diff-filter=D", "--format=%H", ref, "--", rel).strip()
    return list(dict.fromkeys([f"{added}:{rel}", f"{gone}^:{rel}" if gone else f"{ref}:{rel}"]))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--modkit", type=Path, default=os.environ.get("AZURKIT_MODKIT"),
                    help="Modkit's checkout (default $AZURKIT_MODKIT)")
    ap.add_argument("--ref", default="origin/main")
    args = ap.parse_args(argv)
    if args.modkit is None:
        ap.error("--modkit or $AZURKIT_MODKIT names Modkit's checkout")
    commit = _git(args.modkit, "rev-parse", "--verify", f"{args.ref}^{{commit}}").strip()
    prints, read_from = set(), []
    for rel in CREDITED:
        for spec in versions(args.modkit, commit, rel):
            prints |= {fingerprint(s) for s in lines(_git(args.modkit, "show", spec))}
            read_from.append(spec.replace(commit, "REF"))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join([
        "# Written by scripts/provenance_fingerprints.py, never by hand: sha256[:16] of each line (stripped,",
        "# 25+ characters, not a comment) of the Modkit files NOTICE.md credits to JTCPP (D95).",
        f"# Modkit REF = {commit}; read from:", *(f"#   {spec}" for spec in read_from),
        *sorted(prints)]) + "\n", encoding="utf-8")
    print(f"{len(prints)} fingerprints from {len(read_from)} file versions at {commit[:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
