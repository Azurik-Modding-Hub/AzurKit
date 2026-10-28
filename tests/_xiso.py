"""A synthetic XISO for the pure tier: the caller's names and contents, no
game bytes."""

from __future__ import annotations

import struct

from azurkit.core import iso

S = iso.SECTOR


def image(files: dict[str, bytes]) -> bytes:
    """An image holding ``files`` (``{posix path: bytes}``): the volume
    descriptor at sector 32, each folder's table in one sector from 33 (the
    root's first), then each file from a fresh sector, in path order. A
    table chains its records to the right in the kernel's name order."""
    folders = sorted({"/".join(p.split("/")[:depth]) for p in files for depth in range(p.count("/") + 1)})
    start, at = {}, 33
    for path in folders:
        start[path], at = at, at + 1
    for path in sorted(files):
        start[path], at = at, at + max(1, -(-len(files[path]) // S))
    out = bytearray(at * S)
    out[32 * S:32 * S + 28] = iso.MAGIC + struct.pack("<II", start[""], S)
    out[33 * S - 20:33 * S] = iso.MAGIC
    for folder in folders:
        kids = sorted((p for p in [*folders[1:], *files] if p.rpartition("/")[0] == folder),
                      key=lambda p: iso.key(p.rpartition("/")[2]))
        table = bytearray()
        for i, path in enumerate(kids):
            name = path.rpartition("/")[2].encode("latin-1")
            length = (14 + len(name) + 3) // 4 * 4
            right = (len(table) + length) // 4 if i + 1 < len(kids) else 0
            size, attributes = (S, 0x10) if path in folders else (len(files[path]), 0x20)
            table += struct.pack("<HHIIBB", 0, right, start[path], size, attributes, len(name)) + name
            table += b"\xff" * (length - 14 - len(name))
        assert len(table) <= S, f"{folder!r}: its table outgrows its one sector"
        out[start[folder] * S:(start[folder] + 1) * S] = table.ljust(S, b"\xff")
    for path, data in files.items():
        out[start[path] * S:start[path] * S + len(data)] = data
    return bytes(out)


def fill(tag: str, size: int) -> bytes:
    """``size`` bytes of ``tag`` repeated."""
    return (tag.encode() * (size // len(tag) + 1))[:size]
