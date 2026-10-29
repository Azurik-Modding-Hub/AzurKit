"""What the randomizer modules the oracle sync installs from Modkit
(``scripts/oracle_sync.py``'s ``SOURCES``) import from Modkit's shared
engine, on AzurKit's: the sync's ``REWRITES`` point those imports here.
The node and TOC readers are :mod:`azurkit.core.xbr.nodes`."""

from __future__ import annotations

from typing import NamedTuple

from azurkit.core import filelist, iso


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
