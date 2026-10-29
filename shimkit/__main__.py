import argparse
import sys
from pathlib import Path

import shimkit

ap = argparse.ArgumentParser(prog="shimkit", description=shimkit.__doc__.split("\n\n")[0])
ap.add_argument("--check", action="store_true", help="write nothing; exit 1 when an object isn't its source's build")
ap.add_argument("--headers", type=Path, metavar="DIR", help="write the headers a shim includes into DIR")
args = ap.parse_args()
if args.headers:
    args.headers.mkdir(parents=True, exist_ok=True)
    for name, write in shimkit.HEADERS.items():
        (args.headers / name).write_text(write(), encoding="utf-8")
    sys.exit(0)
stale = shimkit.build(check=args.check)
for obj in stale:
    print(f"{'stale' if args.check else 'built'}: {obj.relative_to(shimkit.ROOT)}")
sys.exit(1 if args.check and stale else 0)
