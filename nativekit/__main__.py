import argparse
import sys

import nativekit

ap = argparse.ArgumentParser(prog="nativekit", description=nativekit.__doc__.split("\n\n")[0])
ap.add_argument("--check", action="store_true", help="write nothing; exit 1 when a library isn't its sources' build")
args = ap.parse_args()
stale = nativekit.build(check=args.check)
for lib in stale:
    print(f"{'stale' if args.check else 'built'}: {lib.relative_to(nativekit.ROOT)}")
sys.exit(1 if args.check and stale else 0)
