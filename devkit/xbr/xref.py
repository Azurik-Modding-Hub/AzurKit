"""``python -m devkit xbr xref FILE``: the pointer fields AzurKit's parse of
an XBR models, source offset to target offset (Modkit's ``xbr xref``,
ported in Step 4.6l), to check a structural edit left no pointer dangling
and to show which sections no parse models yet.

The modelled fields are the keyed tables' (``core.xbr.keyed``: every
``tabl`` entry, config.xbr's 18): each row name's pointer, then each string
cell's, column by column, each relative to its own field
(``SelfRelativeRef``). Every other section is unmodeled but ``indx``
(index.xbr's records, ``core.xbr.nodes.IndexRecordsSection``), whose
strings no ref models yet either. Unlike Modkit's model, which read
config.xbr's damage and magic tables as fixed-stride records with no refs
(its Q160), AzurKit parses all 18 as keyed tables, so their refs count too.
A file that doesn't parse whole (``core.xbr.Document``) is one ``xbr xref:``
line and exit 1.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from azurkit.core.xbr import Document

KIND = "SelfRelativeRef"
WIDTH = 4
MODELLED = ("tabl", "indx")   # the tags a parse models: the keyed tables' refs, index.xbr's records


@dataclass(frozen=True)
class Ref:
    owner_tag: str
    src_offset: int      # the field's file offset
    target_offset: int   # the file offset it points at


@dataclass(frozen=True)
class Graph:
    document: Document
    refs: tuple[Ref, ...]

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self.refs:
            out[r.owner_tag] = out.get(r.owner_tag, 0) + 1
        return out

    def unmodeled(self) -> list[int]:
        """The TOC indexes of the entries no parse models."""
        return [e.index for e in self.document.entries if e.tag not in MODELLED]


def load(path: str | Path) -> Graph:
    """The file's pointer graph; ``OSError`` when it can't be read,
    ``ValueError`` naming what of it doesn't parse."""
    doc = Document(Path(path).read_bytes())
    owner = {e.start: e.tag for e in doc.entries}
    return Graph(doc, tuple(Ref(owner[t.start], field, target) for t in doc.tables.values()
                            for field, target in t.refs()))


def _hex(value: int) -> str:
    return f"0x{value:08X}"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m devkit xbr xref",
                                description="List the pointer fields AzurKit's parse of an XBR models.")
    p.add_argument("path", help="an .xbr file")
    p.add_argument("--tag", help="list only this TOC tag's refs")
    p.add_argument("--section-index", type=int, help="list only the refs in the entry at this TOC index")
    p.add_argument("--format", choices=("text", "json"), default="text", help="text (the default) or json")
    p.add_argument("--list-all", action="store_true", help="every ref's row (default: the summary)")
    return p


def main(argv: list[str]) -> int:
    args = parser().parse_args(argv)
    path = Path(args.path)
    try:
        graph = load(path)
    except (OSError, ValueError) as exc:
        print(f"xbr xref: {exc}", file=sys.stderr)
        return 1
    doc, refs = graph.document, list(graph.refs)
    if args.section_index is not None:
        if not 0 <= args.section_index < len(doc.entries):
            print(f"xbr xref: --section-index {args.section_index} is outside 0..{len(doc.entries) - 1}",
                  file=sys.stderr)
            return 2
        entry = doc.entries[args.section_index]
        refs = [r for r in refs if entry.start <= r.src_offset < entry.start + entry.size]
    if args.tag is not None:
        refs = [r for r in refs if r.owner_tag == args.tag]
    unmodeled = graph.unmodeled()
    if args.format == "json":
        print(json.dumps({
            "file": str(path), "toc_entries": len(doc.entries), "ref_counts_by_tag": graph.counts(),
            "refs": [{"kind": KIND, "owner_tag": r.owner_tag, "src_offset": _hex(r.src_offset), "width": WIDTH,
                      "target_offset": _hex(r.target_offset)} for r in refs],
            "unmodeled_sections": [{"toc_index": i, "tag": doc.entries[i].tag, "size": doc.entries[i].size,
                                    "file_offset": _hex(doc.entries[i].start)} for i in unmodeled]}, indent=2))
        return 0
    print(f"{path.name}: {len(doc.data):,} B, {len(doc.entries)} TOC entries")
    print(f"Total refs: {len(graph.refs)}")
    if counts := graph.counts():
        print("Refs by owner tag:")
        for tag in sorted(counts):
            print(f"  {tag}: {counts[tag]}")
    if unmodeled:
        print("\nUnmodeled sections (no parse models their pointers):")
        by_tag: dict[str, int] = {}
        for i in unmodeled:
            by_tag[doc.entries[i].tag] = by_tag.get(doc.entries[i].tag, 0) + 1
        for tag in sorted(by_tag):
            print(f"  {tag!r}: {by_tag[tag]} entr{'y' if by_tag[tag] == 1 else 'ies'}")
    if args.tag is not None or args.section_index is not None:
        print(f"\nRefs ({len(refs)} after filter):")
    elif args.list_all:
        print("\nRefs (--list-all):")
    else:
        print("\n(pass --list-all or --tag / --section-index to see individual ref rows)")
        return 0
    for r in refs:
        print(f"  [{r.owner_tag:>4s}] {KIND:<18s} @{_hex(r.src_offset)} -> {_hex(r.target_offset)}")
    return 0
