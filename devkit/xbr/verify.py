"""``python -m devkit xbr verify FILE [--cross-check-schema]``: that an XBR
parses whole (Modkit's ``xbr verify``, ported in Step 4.6l), a check after a
hand edit.

The parse is ``core.xbr.Document``'s: the header, the TOC (each payload
inside the file), the trailer's tables in their chain and the names in
their pool, and every keyed table (each row name and string cell's pointer
inside its table's payload, NUL-terminated). So a pointer the parse models
can't point past the file and parse: Modkit's past-EOF check is the parse's
here. It prints the counts and exits 0, or one ``xbr verify:`` line naming
what doesn't parse and exits 1, as for a file it can't read.

``--cross-check-schema`` also lists each pack's config.xbr slider whose cell
(its table and row, settings_foo's column) ``tools/data/schema.json``
doesn't document, the Data tab's notes; a multiplier's cells
(``XbrParametricEdit.cells``) are its pack's pick and aren't checked. A miss is a warning: the exit code stays
the parse's.
"""

from __future__ import annotations

import argparse
import sys

from azurkit.edits.xbr import BY_COLUMN
from azurkit.tools import data
from azurkit.tools.mods import PACKS, XbrParametricEdit
from devkit.xbr import xref


def undocumented() -> list[tuple[str, str, str]]:
    """Each ``(pack, table, name)`` of a config.xbr slider the schema doesn't
    document: its cell by its row's name (settings_foo's by its column's,
    the setting, as the Data tab reads it)."""
    tables = data.schema()["tables"]
    return [(pack.name, s.table, name) for pack in PACKS.values() for s in pack.sites
            if isinstance(s, XbrParametricEdit) and s.cells is None
            and (name := s.entity if s.table == BY_COLUMN else s.prop)
            not in tables.get(s.table, {}).get("cells", {})]


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m devkit xbr verify",
                                description="Check that an XBR file parses whole.")
    p.add_argument("path", help="an .xbr file")
    p.add_argument("--cross-check-schema", action="store_true",
                   help="also list the packs' config.xbr cells schema.json doesn't document")
    return p


def main(argv: list[str]) -> int:
    args = parser().parse_args(argv)
    try:
        graph = xref.load(args.path)
    except (OSError, ValueError) as exc:
        print(f"xbr verify: {exc}", file=sys.stderr)
        return 1
    if args.cross_check_schema:
        if misses := undocumented():
            print(f"xbr verify: cross-check: {len(misses)} undocumented pack target(s):")
            for pack, table, prop in misses:
                print(f"  - {pack}: {table}.{prop}")
        else:
            print("xbr verify: cross-check: OK")
    print(f"xbr verify: OK  ({len(graph.document.entries)} TOC entries, {len(graph.refs)} refs, "
          f"{len(graph.unmodeled())} unmodeled sections)")
    return 0
