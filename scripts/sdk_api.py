"""Write the sdk's API snapshot, ``tests/sdk_api.txt``: each name in
``azurkit.sdk.__all__``, its signature and its docstring, after the module's
own docstring. The sdk is the one surface every UI calls (the page, the app,
the CLI, and later tools), so a change to it shows in the snapshot's diff;
``tests/test_contracts.py`` holds the snapshot to the sdk.

    uv run --locked python scripts/sdk_api.py [--check]

``--check`` writes nothing and exits 1 when the snapshot isn't the sdk's.
Run it after changing the sdk's surface, and read its diff.
"""

from __future__ import annotations

import argparse
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))   # this checkout's engine, whichever venv runs it
SNAPSHOT = ROOT / "tests" / "sdk_api.txt"


def text() -> str:
    """The snapshot as this checkout's sdk has it."""
    from azurkit import sdk
    parts = ["# azurkit.sdk, written by scripts/sdk_api.py, never by hand", "", inspect.cleandoc(sdk.__doc__)]
    for name in sdk.__all__:
        function = getattr(sdk, name)
        parts += ["", "", f"def {name}{inspect.signature(function)}:", "",
                  inspect.cleandoc(function.__doc__ or "(no docstring)")]
    return "\n".join(parts) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="write nothing; exit 1 if the snapshot is stale")
    args = parser.parse_args(argv)
    new = text()
    if SNAPSHOT.is_file() and SNAPSHOT.read_text(encoding="utf-8") == new:
        return 0
    if args.check:
        print(f"{SNAPSHOT.relative_to(ROOT)} isn't the sdk's: run scripts/sdk_api.py", file=sys.stderr)
        return 1
    SNAPSHOT.write_text(new, encoding="utf-8")
    print(f"wrote {SNAPSHOT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
