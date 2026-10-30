"""What the randomizer modules the oracle sync installs from Modkit
(``scripts/oracle_sync.py``'s ``SOURCES``) import from Modkit's shared
engine, on AzurKit's: the sync's ``REWRITES`` point those imports here.
The node and TOC readers are :mod:`azurkit.core.xbr.nodes`; the maps'
other XBR readers (Step 4.2c3) are Modkit's own, in
:mod:`azurkit.tools.randomizer.art`, which read an XBE's release and
addresses through here."""

from __future__ import annotations

import struct
from typing import NamedTuple

from azurkit.core import facts, filelist, gate, iso
from azurkit.core import xbe as xbe_file

RETAIL_THUNK_XOR = 0x5B6D40B6   # a retail XBE's header +0x158 holds its kernel thunk table's address XOR this


class Listed(NamedTuple):
    path: str     # under gamedata/, as filelist.txt names it
    md5: str
    size: int


def listed(text: bytes) -> list[Listed]:
    """Every file line of ``filelist.txt`` (its bytes ``text``), each by
    its path under ``gamedata/`` (Modkit's ``assets.filelist.listed``)."""
    return [Listed(row.path.removeprefix("gamedata/"), row.md5, row.size) for row in filelist.rows(text)]


class XisoReader:
    """An image (a path or an :class:`iso.Image`) read file by file, as
    Modkit's ``iso.xiso.XisoReader``: :meth:`read_file` by its path."""

    def __init__(self, source) -> None:
        self._reader = iso.Reader(source)

    def __enter__(self) -> XisoReader:
        self._reader.__enter__()
        return self

    def __exit__(self, *exc) -> None:
        self._reader.__exit__(*exc)

    def read_file(self, path: str) -> bytes:
        return self._reader.read(path)


def xbe_layout(xbe: bytes) -> facts.Facts:
    """The release whose addresses ``xbe`` has, by its kernel thunk table's
    address (every build keeps it), as Modkit's ``assets.vanilla.xbe_layout``:
    its facts, whose :meth:`~facts.Facts.va` maps a USA address to its own;
    USA's for anything else."""
    try:
        thunks = struct.unpack_from("<I", xbe, 0x158)[0] ^ RETAIL_THUNK_XOR
    except struct.error:
        thunks = None
    return next((facts.of(r) for r in gate.RELEASES if bytes(xbe[:4]) == b"XBEH" and facts.of(r).thunks == thunks),
                facts.of(gate.USA))


def resolve_va_to_file(xbe: bytes, va: int) -> int | None:
    """The file offset of ``va`` in ``xbe``, by its own section table (Modkit's
    ``patching.xbe.resolve_va_to_file``); None where it has no file bytes."""
    try:
        return xbe_file.offset(xbe_file.sections(xbe), va)
    except ValueError:
        return None

