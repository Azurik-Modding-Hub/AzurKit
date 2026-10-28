"""Reading an XISO (XDVDFS) image's directory tree.

The volume descriptor sits at sector 32 with ``MICROSOFT*XBOX*MEDIA`` at
both ends; each directory is a table of records forming a binary tree
(left and right offsets in dwords, then the start sector, size,
attributes, name length and name).
"""

from __future__ import annotations

import struct
from collections.abc import Iterator
from dataclasses import dataclass
from typing import BinaryIO

SECTOR = 2048
MAGIC = b"MICROSOFT*XBOX*MEDIA"
_VD_SECTOR = 32
_RECORD = struct.Struct("<HHIIBB")
_DIRECTORY = 0x10


@dataclass(frozen=True)
class Entry:
    path: str    # posix, from the image's root
    sector: int
    size: int
    is_dir: bool


def entries(f: BinaryIO) -> Iterator[Entry]:
    """Every file and directory of the image open in ``f``, parents first;
    ``ValueError`` when it has no volume descriptor, a table runs past its
    end or a directory repeats."""
    f.seek(_VD_SECTOR * SECTOR)
    vd = f.read(SECTOR)
    if vd[:20] != MAGIC or vd[0x7EC:0x800] != MAGIC:
        raise ValueError("no XDVDFS volume descriptor at sector 32")
    root = struct.unpack_from("<II", vd, 20)
    stack, seen = [("", *root)], {root[0]}
    while stack:
        prefix, sector, size = stack.pop()
        if not size:
            continue
        f.seek(sector * SECTOR)
        table = f.read(size)
        if len(table) < size:
            raise ValueError(f"the directory table at sector {sector} runs past the image's end")
        todo, done = [0], set()
        while todo:
            at = todo.pop()
            if at in done or at + _RECORD.size > size or table[at:at + 2] == b"\xff\xff":
                continue
            done.add(at)
            left, right, start, length, attributes, name_length = _RECORD.unpack_from(table, at)
            name = table[at + _RECORD.size:at + _RECORD.size + name_length].decode("cp1252")
            entry = Entry(prefix + name, start, length, bool(attributes & _DIRECTORY))
            yield entry
            if entry.is_dir:
                if start in seen:
                    raise ValueError(f"directory cycle at {entry.path}")
                seen.add(start)
                stack.append((entry.path + "/", start, length))
            todo += [offset * 4 for offset in (right, left) if offset]
