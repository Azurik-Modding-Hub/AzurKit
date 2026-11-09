"""What reaching each spot needs, ``src/azurkit/tools/randomizer/spot_needs.json`` (Step 4.30, Modkit's map tips'
``item_needs``): :func:`azurkit.tools.randomizer.needs.spot_needs` on the randomizer's database under the default
options, which the tracker's maps name on each spot's tip. A reach of every spot takes seconds, so the maps read it
from this file.

    uv run --locked python scripts/spot_needs.py [--check]

``--check`` writes nothing and exits 1 naming each spot that differs. Run it after a change to the randomizer's
database or to what ``needs.py`` says (``tests/test_randomizer.py`` holds the file to it).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from azurkit.tools.randomizer import needs  # noqa: E402

FORMAT = "azurkit-spot-needs/1"
OUT = needs.SPOT_NEEDS


def text(made: dict[str, str]) -> str:
    """The file: one line a spot, by id."""
    keys = sorted(made)
    return (f'{{\n "format": {json.dumps(FORMAT)},\n "needs": {{\n'
            + "\n".join(f"  {json.dumps(k)}: {json.dumps(made[k])}" + ("," if k != keys[-1] else "") for k in keys)
            + "\n }\n}\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="write nothing; exit 1 naming each spot that differs")
    args = ap.parse_args(argv)
    made = needs.spot_needs()
    old = json.loads(OUT.read_text(encoding="utf-8"))["needs"] if OUT.is_file() else {}
    differs = [k for k in sorted(made.keys() | old.keys()) if made.get(k) != old.get(k)]
    for k in differs:
        print(f"{'differs' if args.check else 'changed'}: {k}")
    if args.check:
        return 1 if differs or not OUT.is_file() or text(made) != OUT.read_text(encoding="utf-8") else 0
    OUT.write_text(text(made), encoding="utf-8")
    print(f"wrote: {OUT.relative_to(ROOT)} ({len(made)} spots)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
