"""``filelist.txt``: the game's list of its ``gamedata/`` files, each with its
md5 and size.

The game keeps the copy of a listed file it cached on the hard disk until that
file's line here changes, so a build rewrites the line of every file it
changes (:func:`rewrite`). A line ``\\`` or ``\\<folder>\\`` opens a folder of
``gamedata/``; ``f <md5> <size> <name>`` lists a file in it, the size
right-aligned in its column; ``d <name>`` names a subfolder that a later line
opens. Every other line is kept as it is.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator, Mapping
from typing import NamedTuple

_FIELDS = re.compile(r"(\s*f\s+)\S+(\s+\S+)")   # the lead up to the md5, then the size with its padding


class Row(NamedTuple):
    line: int    # the index of its line
    path: str    # from the image's root: gamedata/<folder>/<name>
    md5: str
    size: int


def rows(text: bytes) -> list[Row]:
    """Every file line of ``text`` (the bytes of ``filelist.txt``)."""
    return list(_rows(text.decode("latin-1").splitlines()))


def _rows(lines: list[str]) -> Iterator[Row]:
    folder = "gamedata"
    for number, line in enumerate(lines):
        line = line.rstrip()
        if line.startswith("\\"):
            folder = "/".join(["gamedata", *filter(None, line.strip("\\").split("\\"))])
            continue
        kind, *rest = line.split(None, 3) or [""]
        if kind == "f" and len(rest) == 3 and rest[1].isdecimal():
            yield Row(number, f"{folder}/{rest[2].strip()}", rest[0].lower(), int(rest[1]))


def rewrite(text: bytes, changed: Mapping[str, bytes]) -> bytes:
    """``text`` with the md5 and size of each file of ``changed`` (``{path
    from the image's root: its new bytes}``, matched case-blind) that it
    lists put in that file's line; every other byte stays, and a size stays
    right-aligned in its column (at least one space before it)."""
    new = {path.strip("/").lower(): data for path, data in changed.items()}
    lines = text.decode("latin-1").splitlines(keepends=True)
    for row in _rows(lines):
        if (data := new.get(row.path.lower())) is None:
            continue
        old = lines[row.line]
        fields = _FIELDS.match(old)
        size = f" {len(data)}".rjust(len(fields[2]))
        lines[row.line] = fields[1] + hashlib.md5(data, usedforsecurity=False).hexdigest() + size + old[fields.end():]
    return "".join(lines).encode("latin-1")
