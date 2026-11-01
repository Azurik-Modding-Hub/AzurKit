"""web/tables.json: each release's folder-table pages, the 1 MiB pages of its image that hold the volume
descriptor and every folder's table (worker.mjs's ahead()), keyed by the partition's base and the root table's
sector and size, so the site's first walk of an image reads them in one round of awaited reads after the
descriptor's, not one round a depth. Offsets only, no bytes; a hint: the engine still reads and checks every byte.

    uv run --locked python scripts/web_tables.py [--check]      (from the player's images, the ones the gate finds)

``--check`` writes nothing and exits 1 on a difference (the release check's).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from azurkit.core import gate, iso  # noqa: E402

OUT = ROOT / "web" / "tables.json"
PAGE, SLACK, PAGES = 1 << 20, 128 << 10, 64   # worker.mjs's PAGE, SLACK and PAGES
VD = iso._VD_SECTOR * iso.SECTOR


def pages(path: Path) -> tuple[str, list[int]]:
    """``path``'s key in the file and the pages of its tables, as ahead()'s walk finds them."""
    size = path.stat().st_size
    with iso.Reader(path) as r:
        bases = [b for b in iso._PARTITIONS if b + VD + iso.SECTOR <= size]
        used = {(b + VD) // PAGE for b in bases[:bases.index(r.base) + 1]}
        for sector, n in [r._root, *((e.sector, e.size) for e in r.entries() if e.is_dir and e.size)]:
            at = r.base + sector * iso.SECTOR
            used.update(range(at // PAGE, (at + n - 1 + SLACK) // PAGE + 1))
        return f"{r.base}:{r._root[0]}:{r._root[1]}", sorted(i for i in used if i * PAGE < size)[:PAGES]


def main(argv: list[str]) -> int:
    images = {release.name: gate.find(release) for release in gate.RELEASES}
    if none := [name for name, path in images.items() if path is None]:
        raise SystemExit(f"web_tables: no image of {', '.join(none)}")
    made = dict(pages(path) for path in images.values())
    text = json.dumps(made, sort_keys=True) + "\n"
    if "--check" in argv:
        return 0 if OUT.is_file() and OUT.read_text(encoding="utf-8") == text else 1
    OUT.write_text(text, encoding="utf-8")
    print(f"{OUT.name}: {', '.join(f'{key} {len(listed)} pages' for key, listed in made.items())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
