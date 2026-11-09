"""``python -m devkit xbr edit IN OUT ...``: an XBR file's strings, bytes and
keyed cells written into a new file (Modkit's ``xbr edit``, ported in Step
4.6l). Nothing grows or moves:

- ``--set-string OLD=NEW`` rewrites the first NUL-terminated ASCII ``OLD``
  in the payloads (of ``--tag``'s entries only, when given) in place: NEW
  and its NUL must fit OLD's slot, NUL-padded;
- ``--replace-bytes OFFSET:HEX`` overwrites the bytes at a file offset;
- ``--set-value TABLE/ENTITY/PROP=NUMBER`` writes a keyed table's number
  cell (config.xbr's 18 tables, by the file's own names), any finite value
  (D23), as ``core.xbr.edits.set_number`` plans it;
- ``--set-keyed-string TABLE/ENTITY/PROP=TEXT`` gives a string cell a text,
  as ``core.xbr.edits.set_text`` does: it points at a string of its table
  that holds TEXT, else rewrites its own unshared string where TEXT fits.

They run in that order, each on what the ones before wrote. The output
appears only whole, once every edit took (D35); it is never the input or a
vanilla image (D36), which is refused before anything is read. A refusal is
one ``xbr edit:`` line and exit 1; the log of what was written goes to
stdout, by offsets and lengths, never bytes.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from azurkit.core import gate
from azurkit.core.xbr import Document, edits
from azurkit.core.xbr.nodes import TocEntry, parse_toc


class XbrEditError(ValueError):
    """An edit that would break the file (a size or range, a non-ASCII text)."""


@dataclass
class XbrEditLog:
    actions: list[str] = field(default_factory=list)

    def record(self, description: str) -> None:
        self.actions.append(description)

    def format(self) -> str:
        return "\n".join(f"  OK  {a}" for a in self.actions) if self.actions else "  (no edits applied)"


class XbrEditor:
    """An XBR file's bytes, edited in memory; ``ValueError`` when they aren't an XBR."""

    def __init__(self, data: bytes) -> None:
        self._data = bytearray(data)
        self.log = XbrEditLog()
        self._toc = parse_toc(self._data)

    @property
    def data(self) -> bytes:
        return bytes(self._data)

    def replace_bytes(self, offset: int, new: bytes) -> None:
        """``new`` over the bytes at ``offset``, which the file must hold."""
        end = offset + len(new)
        if offset < 0 or end > len(self._data):
            raise XbrEditError(f"replace_bytes out of range: offset=0x{offset:x} end=0x{end:x} "
                               f"file_size=0x{len(self._data):x}")
        self._data[offset:end] = new
        self.log.record(f"replace_bytes: @0x{offset:08x} len={len(new)}")

    def replace_string_at(self, offset: int, new: str) -> None:
        """``new`` over the NUL-terminated string at ``offset``: it and its
        NUL must fit the old one's bytes and NUL, the rest NULs."""
        if not new.isascii():
            raise XbrEditError(f"new string {new!r} contains non-ASCII characters; an XBR's strings are ASCII")
        if not 0 <= offset < len(self._data):    # a negative one would index from the end and grow the file (L34)
            raise XbrEditError(f"replace_string_at out of range: offset={offset:#x} file_size={len(self._data):#x}")
        end = self._data.find(0, offset)
        if end < 0:
            raise XbrEditError(f"no NUL terminator after offset 0x{offset:x}")
        slot = end - offset + 1
        raw = new.encode("ascii") + b"\0"
        if len(raw) > slot:
            raise XbrEditError(f"new string {new!r} ({len(raw)} B including NUL) is longer than the existing slot "
                               f"({slot} B) at offset 0x{offset:x}; the in-place editor refuses oversized writes")
        self._data[offset:offset + slot] = raw.ljust(slot, b"\0")
        self.log.record(f"replace_string_at: @0x{offset:08x} old_len={slot - 1} new_len={len(new)}")

    def replace_string_in_tag(self, *, old: str, new: str, tag: str | None = None, occurrence: int = 0) -> int:
        """Rewrite the ``occurrence``-th NUL-terminated ``old`` in the payloads
        of ``tag``'s entries (every entry's with none), in TOC order; its offset."""
        if not old.isascii():
            raise XbrEditError(f"search string {old!r} contains non-ASCII characters")
        needle, matches = old.encode("ascii") + b"\0", []
        for start, end in self._regions(tag):
            at = self._data.find(needle, start, end)
            while at >= 0:
                matches.append(at)
                at = self._data.find(needle, at + 1, end)
        if occurrence >= len(matches):
            raise XbrEditError(f"no match #{occurrence} for {old!r} in tag {tag or '*'} (found {len(matches)})")
        self.replace_string_at(matches[occurrence], new)
        return matches[occurrence]

    def apply(self, writes: Iterable[tuple[int, bytes]], what: str) -> None:
        """A cell edit's writes (``core.xbr.edits``), logged as ``what``."""
        for at, data in writes:
            self._data[at:at + len(data)] = data
        self.log.record(what)

    def _regions(self, tag: str | None) -> Iterable[tuple[int, int]]:
        entries: list[TocEntry] = [e for e in self._toc if tag is None or e.tag == tag]
        for e in entries:
            if e.file_offset < (end := min(e.file_offset + e.size, len(self._data))):
                yield e.file_offset, end


def _cell(spec: str, flag: str, kind: str) -> tuple[str, str, str, str]:
    path, eq, value = spec.partition("=")
    parts = path.split("/", 2)
    if not eq or len(parts) != 3:
        raise XbrEditError(f"bad {flag} spec {spec!r}: expected 'table/entity/prop={kind}'")
    return *parts, value


def _new_output(out: Path, source: Path) -> None:
    """D36: never over the input or a vanilla image."""
    if out.exists() and source.exists() and out.samefile(source):
        raise ValueError(f"{out}: it is the input, which xbr edit never writes over")
    for release in gate.RELEASES:
        if (vanilla := gate.find(release)) and out.exists() and out.samefile(vanilla):
            raise ValueError(f"{out}: it is the vanilla {release.label} image, which xbr edit never writes over")


def edit(args: argparse.Namespace) -> XbrEditor:
    """Every edit ``args`` asks, in order, on the input's bytes; nothing written."""
    editor = XbrEditor(Path(args.input).read_bytes())
    for spec in args.set_string or ():
        old, eq, new = spec.partition("=")
        if not eq:
            raise XbrEditError(f"bad --set-string spec {spec!r}: expected 'old=new'")
        editor.replace_string_in_tag(old=old, new=new, tag=args.tag)
    for spec in args.replace_bytes or ():
        offset, colon, hexed = spec.partition(":")
        if not colon:
            raise XbrEditError(f"bad --replace-bytes spec {spec!r}: expected 'OFFSET:HEX'")
        editor.replace_bytes(int(offset, 0), bytes.fromhex(hexed))
    for spec in args.set_value or ():
        table, entity, prop, value = _cell(spec, "--set-value", "number")
        try:
            number = float(value)
        except ValueError:
            raise XbrEditError(f"bad --set-value spec {spec!r}: {value!r} is not a number") from None
        editor.apply(edits.set_number(_table(editor, table), entity, prop, number),
                     f"set_value: {table}/{entity}/{prop} = {value}")
    for spec in args.set_keyed_string or ():
        table, entity, prop, text = _cell(spec, "--set-keyed-string", "string")
        editor.apply(edits.set_text(_table(editor, table), editor.data, entity, prop, text),
                     f"set_keyed_string: {table}/{entity}/{prop} = {text!r}")
    return editor


def _table(editor: XbrEditor, name: str):
    """The keyed table ``name`` of the bytes as edited so far."""
    tables = Document(editor.data).tables
    if name not in tables:
        raise XbrEditError(f"no keyed table {name!r} (the file's: {', '.join(tables) or 'none'})")
    return tables[name]


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m devkit xbr edit",
                                description="Write an XBR file's strings, bytes and keyed cells into a new file.")
    p.add_argument("input", help="the .xbr file to read")
    p.add_argument("output", help="the file to write: never the input or a vanilla image")
    p.add_argument("--set-string", action="append", metavar="OLD=NEW", help="an ASCII string in place; repeatable")
    p.add_argument("--tag", help="--set-string looks only in this TOC tag's payloads")
    p.add_argument("--replace-bytes", action="append", metavar="OFFSET:HEX", help="bytes at a file offset; repeatable")
    p.add_argument("--set-value", action="append", metavar="TABLE/ENTITY/PROP=NUMBER",
                   help="a keyed table's number cell; repeatable")
    p.add_argument("--set-keyed-string", action="append", metavar="TABLE/ENTITY/PROP=TEXT",
                   help="a keyed table's string cell; repeatable")
    return p


def main(argv: list[str]) -> int:
    args = parser().parse_args(argv)
    out = Path(args.output)
    try:
        _new_output(out, Path(args.input))
        editor = edit(args)
        out.parent.mkdir(parents=True, exist_ok=True)
        part = out.with_name(f"{out.name}.part")
        part.write_bytes(editor.data)
        os.replace(part, out)
    except (OSError, ValueError, LookupError) as exc:   # XbrEditError and the cell edits' refusals are ValueErrors
        print(f"xbr edit: {exc}", file=sys.stderr)
        return 1
    editor.log.record(f"wrote: {out}")
    print(editor.log.format())
    return 0
