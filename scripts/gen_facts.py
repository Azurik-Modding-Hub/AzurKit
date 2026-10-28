"""Write AzurKit's facts, ``src/azurkit/core/facts.<release>.json``, from the
oracle (``tests/oracle/``): each release's ``default.xbe`` sha256, size and
base, its section table, every patch site (its address, size and the sha256
of its vanilla bytes) and, for Europe, the address map's USA -> Europe
addresses and its named absences. Hashes, sizes and addresses only (D3).

    uv run --locked python scripts/gen_facts.py [--check]

``--check`` writes nothing and exits 1 when a file isn't what this derives;
``tests/test_packs.py`` checks the same. Run it after an oracle sync of the
packs or core family.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORACLE = ROOT / "tests" / "oracle"
SOURCES = {"usa": ORACLE / "packs/tests/facts/xbe.json", "europe": ORACLE / "packs/tests/facts/xbe.europe.json"}
ADDRESS_MAP = ORACLE / "core/azurik_mod/assets/region_europe.json"
OUT = ROOT / "src" / "azurkit" / "core"
ABOUT = ("Written by scripts/gen_facts.py from tests/oracle/ (Modkit's facts and Europe's address map), never by "
         "hand. Hashes, sizes and addresses only: a site's vanilla bytes are their sha256 and size.")


def derive(release: str) -> dict:
    """The facts file of ``release`` (``usa`` or ``europe``)."""
    facts = json.loads(SOURCES[release].read_text(encoding="utf-8"))
    out = {
        "_about": ABOUT,
        "release": release,
        "xbe": {"base": facts["xbe"]["base"], "sha256": facts["xbe"]["sha256"], "size": facts["xbe"]["size"]},
        "sections": [{k: s[k] for k in ("name", "va", "vsize", "raw", "raw_size", "flags", "sha256")}
                     for s in facts["sections"]],
        "sites": {va: {"size": s["size"], "sha256": s["original_sha256"]} for va, s in facts["patch_sites"].items()},
    }
    if release == "europe":
        amap = json.loads(ADDRESS_MAP.read_text(encoding="utf-8"))
        out["addresses"] = {va: entry["europe"] for va, entry in amap["map"].items()}
        out["absent"] = {va: amap["why"][key] for va, key in amap["absent"].items()}
    return out


def text(release: str) -> str:
    return json.dumps(derive(release), indent=1, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="write nothing; exit 1 when a file differs")
    args = ap.parse_args(argv)
    stale = []
    for release in SOURCES:
        path = OUT / f"facts.{release}.json"
        if path.exists() and path.read_text(encoding="utf-8") == text(release):
            continue
        stale.append(path)
        if not args.check:
            path.write_text(text(release), encoding="utf-8")
    for path in stale:
        print(f"{'stale' if args.check else 'wrote'}: {path.relative_to(ROOT)}")
    return 1 if args.check and stale else 0


if __name__ == "__main__":
    sys.exit(main())
