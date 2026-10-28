"""First setup: ``uv sync --locked``, the leak guard's ``pre-push`` hook,
and Pyodide for the ``web`` tests.

    uv run bootstrap.py [--no-hooks] [--no-web]

The hook (in the repository's common git dir, so every worktree shares it)
runs ``tests/_leak_guard.py --pre-push`` over every file the pushed commits
add or change, and refuses the push on a hit (Q273). Pyodide's core goes in
the main checkout's ``.tools/`` (``scripts/web_tools.py``: pinned by sha256),
which every lane uses. Run this in the main checkout, not in a lane. Stdlib
only.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOOK = """#!/bin/sh
# leak-guard pre-push hook, written by `uv run bootstrap.py` (AzurKit, Q273)
# It runs only tests/_leak_guard.py (stdlib) over every file the pushed
# commits add or change, those no remote-tracking ref of the remote reaches
# (a new remote: the whole history): a push fails while one of them holds
# anything taken from the game, even one a later commit deleted, naming each
# file and the commit that added it. Delete this file to remove it.
cd "$(git rev-parse --show-toplevel)" || exit 1
for py in .venv/bin/python .venv/Scripts/python.exe; do
  if [ -x "$py" ]; then exec "$py" -I tests/_leak_guard.py --pre-push "$1"; fi
done
exec uv run --no-sync python -I tests/_leak_guard.py --pre-push "$1"
"""


def install_hook(root: Path = ROOT) -> Path:
    common = subprocess.run(["git", "-C", str(root), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                            capture_output=True, text=True, check=True).stdout.strip()
    hook = Path(common) / "hooks" / "pre-push"
    if hook.exists() and "leak-guard pre-push hook" not in hook.read_text(encoding="utf-8", errors="replace"):
        raise SystemExit(f"{hook} exists and isn't the leak guard's: merge it by hand")
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(HOOK, encoding="utf-8")
    os.chmod(hook, 0o755)
    return hook


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--no-hooks", action="store_true", help="leave the pre-push hook out")
    ap.add_argument("--no-web", action="store_true", help="leave Pyodide out (then run pytest -m \"not web\")")
    args = ap.parse_args(argv)
    subprocess.run(["uv", "sync", "--locked"], cwd=ROOT, check=True)
    if not args.no_hooks:
        print(f"pre-push hook: {install_hook()}")
    if not args.no_web:
        from scripts import web_tools
        print(f"Pyodide {web_tools.VERSION}: {web_tools.fetch(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
