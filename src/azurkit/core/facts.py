"""The facts about each release's vanilla ``default.xbe``: its sha256 and
size, its section table (:mod:`azurkit.core.xbe`), every patch site a pack
writes as the sha256 and size of its vanilla bytes (never the bytes, D3),
and Europe's address map: each USA address the packs name, at its Europe
address, or why it has none. USA's addresses are the canonical ones, by
which every pack names its sites.

``facts.<release>.json`` beside this module holds them, written by
``scripts/gen_facts.py`` from the oracle (Modkit's facts and address map in
``tests/oracle/``), never by hand.
"""

from __future__ import annotations

import functools
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from azurkit.core import xbe
from azurkit.core.gate import Release


@dataclass(frozen=True)
class Site:
    va: int        # the release's own address
    size: int
    sha256: str    # of its vanilla bytes


@dataclass(frozen=True)
class Facts:
    release: Release
    sha256: str                        # the vanilla default.xbe's
    size: int
    sections: tuple[xbe.Section, ...]
    sites: Mapping[int, Site]          # by the release's own address
    addresses: Mapping[int, int] | None   # USA address -> this release's; None: USA's own
    absent: Mapping[int, str]          # USA address -> why this release has none

    def va(self, usa_va: int) -> int:
        """``usa_va``'s address in this release; ``LookupError`` says why
        there is none."""
        if self.addresses is None:
            return usa_va
        if (va := self.addresses.get(usa_va)) is None:
            why = self.absent.get(usa_va, "it is not in the address map")
            raise LookupError(f"0x{usa_va:08X} has no {self.release.label} address: {why}")
        return va

    def site(self, va: int) -> Site:
        """The patch site at this release's ``va``; ``LookupError`` when the
        facts have none there."""
        try:
            return self.sites[va]
        except KeyError:
            raise LookupError(f"the {self.release.label} facts have no patch site at 0x{va:08X}") from None

    def offset(self, va: int, size: int = 1) -> int:
        """The file offset of ``size`` bytes at this release's ``va``."""
        return xbe.offset(self.sections, va, size)


def path(release: Release) -> Path:
    return Path(__file__).with_name(f"facts.{release.name}.json")


@functools.cache
def of(release: Release) -> Facts:
    """The release's facts."""
    raw = json.loads(path(release).read_text(encoding="utf-8"))
    hexed = lambda table: {int(k, 16): v for k, v in table.items()}   # noqa: E731
    return Facts(
        release, raw["xbe"]["sha256"], raw["xbe"]["size"],
        tuple(xbe.Section(s["name"], *(int(s[k], 16) for k in ("va", "vsize", "raw", "raw_size", "flags")))
              for s in raw["sections"]),
        {va: Site(va, s["size"], s["sha256"]) for va, s in hexed(raw["sites"]).items()},
        {va: int(to, 16) for va, to in hexed(raw["addresses"]).items()} if "addresses" in raw else None,
        hexed(raw.get("absent", {})))
