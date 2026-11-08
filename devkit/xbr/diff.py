"""``python -m devkit xbr diff A.xbr B.xbr``: what differs between two XBR
files (Modkit's ``xbr diff``, ported in Step 4.6l), so a modded level read
against vanilla shows:

- each tag whose total size changed (added, removed or resized: which kinds
  of asset moved);
- the NUL-terminated ASCII strings (with a letter, ``--min-len`` or longer)
  each tag's payloads gained or lost (a new texture, portal or event);
- each TOC entry with the same index, tag and size in both whose bytes
  differ (a value edit, such as a config.xbr cell's), as its first
  differing offset and how many bytes differ;
- and, when none of that differs, that the files differ only in bytes this
  doesn't compare (the header, the TOC, padding, entries that moved).

It doesn't read the records (``xbr inspect`` does). It exits 0 when the two
files hold the same bytes and 1 when they don't, or on an input it can't
read or that isn't an XBR (one ``xbr diff:`` line).
"""

from __future__ import annotations

import argparse
import functools
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from azurkit.core.xbr.nodes import TocEntry, parse_toc

_LETTER = re.compile(rb"[A-Za-z]")


@functools.cache
def _string_pattern(min_len: int) -> re.Pattern[bytes]:
    return re.compile(rb"([\x20-\x7E]{%d,})\x00" % min_len)


def find_strings_in_region(data: bytes, start: int, length: int, min_len: int = 6,
                           require_alpha: bool = True) -> list[tuple[int, str]]:
    """``(file offset, text)`` of each NUL-terminated ASCII string of
    ``min_len`` or more in ``data[start:start + length]``; ``require_alpha``
    drops those without a letter (the chaff of mesh and surface data)."""
    end = min(start + length, len(data))
    if end <= start:
        return []
    return [(m.start(1), m.group(1).decode("ascii")) for m in _string_pattern(min_len).finditer(data, start, end)
            if not require_alpha or _LETTER.search(m.group(1))]


@dataclass(frozen=True)
class TOCChange:
    kind: str                  # "added" | "removed" | "size_changed"
    tag: str
    size_before: int | None = None
    size_after: int | None = None


@dataclass(frozen=True)
class StringChange:
    kind: str                  # "added" | "removed"
    tag: str
    text: str


@dataclass(frozen=True)
class ByteChange:
    tag: str
    entry_index: int
    first_offset: int          # the file offset of the first differing byte
    changed_bytes: int


@dataclass
class XbrDiff:
    path_a: str
    path_b: str
    size_a: int = 0
    size_b: int = 0
    toc_changes: list[TOCChange] = field(default_factory=list)
    string_changes: list[StringChange] = field(default_factory=list)
    size_deltas: dict[str, int] = field(default_factory=dict)
    byte_changes: list[ByteChange] = field(default_factory=list)
    identical: bool = True

    @property
    def total_size_delta(self) -> int:
        return self.size_b - self.size_a

    @property
    def has_changes(self) -> bool:
        return not self.identical

    def to_json_dict(self) -> dict:
        return {"path_a": self.path_a, "path_b": self.path_b, "size_a": self.size_a, "size_b": self.size_b,
                "total_size_delta": self.total_size_delta, "identical": self.identical,
                "toc_changes": [{"kind": c.kind, "tag": c.tag, "size_before": c.size_before,
                                 "size_after": c.size_after} for c in self.toc_changes],
                "string_changes": [{"kind": c.kind, "tag": c.tag, "text": c.text} for c in self.string_changes],
                "size_deltas": dict(self.size_deltas),
                "byte_changes": [{"tag": c.tag, "entry_index": c.entry_index, "first_offset": c.first_offset,
                                  "changed_bytes": c.changed_bytes} for c in self.byte_changes]}


def _sizes(toc: list[TocEntry]) -> dict[str, int]:
    out: dict[str, int] = {}
    for e in toc:
        out[e.tag] = out.get(e.tag, 0) + e.size
    return out


def _strings(data: bytes, toc: list[TocEntry], min_len: int) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for e in toc:
        if hits := find_strings_in_region(data, e.file_offset, e.size, min_len=min_len):
            out.setdefault(e.tag, set()).update(text for _, text in hits)
    return out


def diff_xbr(path_a: str | Path, path_b: str | Path, *, min_len: int = 6) -> XbrDiff:
    """The two files' differences; ``OSError`` when either can't be read (a
    folder, a missing file), ``ValueError`` when either isn't an XBR."""
    pa, pb = Path(path_a).expanduser().resolve(), Path(path_b).expanduser().resolve()
    data_a, data_b = pa.read_bytes(), pb.read_bytes()
    toc_a, toc_b = parse_toc(data_a), parse_toc(data_b)
    diff = XbrDiff(str(pa), str(pb), len(data_a), len(data_b), identical=data_a == data_b)
    tags_a, tags_b = _sizes(toc_a), _sizes(toc_b)
    for tag in sorted(set(tags_a) | set(tags_b)):
        before, after = tags_a.get(tag, 0), tags_b.get(tag, 0)
        if before == after:
            continue
        diff.size_deltas[tag] = after - before
        kind = "added" if before == 0 else "removed" if after == 0 else "size_changed"
        diff.toc_changes.append(TOCChange(kind, tag, None if kind == "added" else before,
                                          None if kind == "removed" else after))
    strings_a, strings_b = _strings(data_a, toc_a, min_len), _strings(data_b, toc_b, min_len)
    for tag in sorted(set(strings_a) | set(strings_b)):
        a, b = strings_a.get(tag, set()), strings_b.get(tag, set())
        diff.string_changes += [StringChange("added", tag, s) for s in sorted(b - a)]
        diff.string_changes += [StringChange("removed", tag, s) for s in sorted(a - b)]
    for ea, eb in zip(toc_a, toc_b):
        if (ea.tag, ea.size) != (eb.tag, eb.size):
            continue
        a = data_a[ea.file_offset:ea.file_offset + ea.size]
        b = data_b[eb.file_offset:eb.file_offset + eb.size]
        if a == b:
            continue
        xor = (int.from_bytes(a, "little") ^ int.from_bytes(b, "little")).to_bytes(eb.size, "little")
        diff.byte_changes.append(ByteChange(eb.tag, eb.index, eb.file_offset + len(xor) - len(xor.lstrip(b"\0")),
                                            len(xor) - xor.count(0)))
    return diff


def format_diff(diff: XbrDiff, *, max_strings: int = 40) -> str:
    lines = ["XBR diff:", f"  A: {diff.path_a}  ({diff.size_a:,} B)", f"  B: {diff.path_b}  ({diff.size_b:,} B)",
             f"  Size delta: {diff.total_size_delta:+,} B"]
    if not diff.has_changes:
        return "\n".join(lines + ["", "(no changes detected)"])
    if not (diff.toc_changes or diff.byte_changes or diff.string_changes):
        return "\n".join(lines + ["", "(the files differ only in bytes this diff doesn't compare: the header, the "
                                      "TOC, padding or entries that moved)"])
    if diff.toc_changes:
        lines += ["", "TOC changes:"]
        for c in diff.toc_changes:
            if c.kind == "added":
                lines.append(f"  + tag {c.tag!r}  new ({c.size_after:,} B)")
            elif c.kind == "removed":
                lines.append(f"  - tag {c.tag!r}  was {c.size_before:,} B")
            else:
                lines.append(f"  ~ tag {c.tag!r}  {c.size_before:,} → {c.size_after:,} B  "
                             f"({c.size_after - c.size_before:+,})")
    if diff.byte_changes:
        lines += ["", "In-place byte changes:"]
        lines += [f"  ~ entry {c.entry_index} {c.tag!r}: {c.changed_bytes:,} B differ, the first at "
                  f"0x{c.first_offset:X}" for c in diff.byte_changes]
    if diff.string_changes:
        lines += ["", f"String changes ({len(diff.string_changes)} total):"]
        grouped: dict[str, list[StringChange]] = {}
        for sc in diff.string_changes:
            grouped.setdefault(sc.tag, []).append(sc)
        for tag, rows in grouped.items():
            lines.append(f"  [{tag}]")
            lines += [f"    {'+' if sc.kind == 'added' else '-'} {sc.text!r}" for sc in rows[:max_strings]]
            if len(rows) > max_strings:
                lines.append(f"    ... and {len(rows) - max_strings} more")
    return "\n".join(lines)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m devkit xbr diff",
                                description="What differs between two XBR files; exit 1 when they differ.")
    p.add_argument("path_a", help="the first .xbr file")
    p.add_argument("path_b", help="the second")
    p.add_argument("--min-len", type=int, default=6, help="the shortest string compared (default 6)")
    p.add_argument("--max-strings", type=int, default=40, help="the string changes shown a tag (default 40)")
    p.add_argument("--json", action="store_true", help="one JSON object")
    return p


def main(argv: list[str]) -> int:
    args = parser().parse_args(argv)
    try:
        diff = diff_xbr(args.path_a, args.path_b, min_len=args.min_len)
    except (OSError, ValueError) as exc:
        print(f"xbr diff: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(diff.to_json_dict(), indent=2) if args.json else format_diff(diff, max_strings=args.max_strings))
    return 1 if diff.has_changes else 0
