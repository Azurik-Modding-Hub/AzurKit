"""What the build checks read: a build's ``default.xbe`` (and, from an
image, its ``gamedata/config.xbr``), the release whose addresses it has, and
that release's vanilla ``default.xbe``, from ``--original`` or the player's
image (``core.gate.find``: ``AZURKIT_ISO`` or ``AZURKIT_ISO_EUROPE``, else
the user data folder). A refusal is a ``ValueError`` (an ``OSError`` for a
file that can't be read) naming why."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from azurkit.core import facts, gate, iso, xbe
from azurkit.core.gate import Release
from azurkit.core.xbr import Document
from azurkit.tools import data

CONFIG = "gamedata/config.xbr"


@dataclass(frozen=True)
class Build:
    path: Path
    xbe: bytes
    config: bytes | None       # None: a raw XBE was given
    release: Release
    facts: facts.Facts
    vanilla: bytes             # the release's vanilla default.xbe
    vanilla_from: str

    @property
    def tables(self):
        """config.xbr's keyed tables as the build holds them; ``None`` with no config.xbr."""
        return None if self.config is None else Document(self.config).tables


def read(path: str | Path) -> tuple[bytes, bytes | None]:
    """The XBE at ``path`` (a raw XBE), or an image's ``default.xbe`` and ``gamedata/config.xbr``."""
    path = Path(path)
    with path.open("rb") as f:
        if f.read(4) == xbe.MAGIC:
            return path.read_bytes(), None
    with iso.Reader(path) as r:
        try:
            return r.read("default.xbe"), r.read(CONFIG) if r.lookup(CONFIG) else None
        except FileNotFoundError:
            raise ValueError(f"{path} holds no default.xbe") from None


def release_of(data: bytes) -> Release | None:
    """The release whose kernel thunk table's address the XBE's header holds (a build keeps it)."""
    if bytes(data[:4]) != xbe.MAGIC or len(data) < 0x15C:
        return None
    thunks = int.from_bytes(bytes(data[0x158:0x15C]), "little") ^ facts.THUNK_KEY
    return next((r for r in gate.RELEASES if facts.of(r).thunks == thunks), None)


def load(path: str | Path, original: str | Path | None = None) -> Build:
    """The build at ``path`` (an image or a raw XBE) and its release's
    vanilla XBE (``original``, an image or a raw XBE, else the player's image)."""
    data, config = read(path)
    # refuses what isn't an XBE, a table that runs off it, or a section past its end (a cut copy)
    if cut := next((s.name for s in xbe.sections(data) if s.raw + s.raw_size > len(data)), None):
        raise ValueError(f"{path}: its default.xbe is cut short ({len(data)} B): section {cut} runs past its end")
    if (release := release_of(data)) is None:
        raise ValueError(f"{path}: its default.xbe is of neither release (its kernel thunk table's address is "
                         "neither's)")
    known = facts.of(release)
    where = original or gate.find(release)
    if where is None:
        raise ValueError(f"no vanilla {release.label} image to compare with: {gate.missing(release)}, or pass "
                         "--original PATH")
    vanilla = read(where)[0]
    if hashlib.sha256(vanilla).hexdigest() != known.sha256:
        raise ValueError(f"{where} holds no vanilla {release.label} default.xbe")
    return Build(Path(path), data, config, release, known, vanilla, str(where))


def vanilla_tables():
    """The vanilla config.xbr's keyed tables (the file AzurKit ships: both releases hold it byte for byte)."""
    return Document(Path(data.__file__).with_name("config.xbr").read_bytes()).tables
