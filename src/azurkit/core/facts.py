"""The facts about each release's vanilla ``default.xbe``: its sha256 and
size, its section table (:mod:`azurkit.core.xbe`), every patch site a pack
writes as the sha256 and size of its vanilla bytes (never the bytes, D3),
the kernel thunk table's address, the game's functions a shim may call (:class:`Function`: the one source of
their names, addresses and ABIs, from which ``shimkit`` writes the header a
shim includes, AZ-099), the kernel exports a shim may use (:class:`Kernel`:
their ordinals and slots in the release's thunk table, from which ``shimkit``
writes ``azurik_kernel.h``, Q85), and Europe's address map: each USA address the packs name, at its Europe
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
from dataclasses import dataclass, field
from pathlib import Path

from azurkit.core import xbe
from azurkit.core.gate import Release


@dataclass(frozen=True)
class Site:
    va: int        # the release's own address
    size: int
    sha256: str    # of its vanilla bytes


@dataclass(frozen=True)
class Function:
    """A game function a shim may call, at the release's own address."""
    name: str
    va: int
    convention: str     # cdecl, stdcall, fastcall or thiscall
    arg_bytes: int      # what it pops (thiscall: past ECX's this); fastcall: its @N, ECX's and EDX's 8 too
    undecorated: bool = False   # stdcall named without its @N (MSVC's 64-bit helpers, _allmul ...)

    @property
    def mangled(self) -> str:
        """Its name in an object's symbol table, as clang mangles C for i386 Windows."""
        if self.convention == "stdcall" and not self.undecorated:
            return f"_{self.name}@{self.arg_bytes}"
        return f"@{self.name}@{self.arg_bytes}" if self.convention == "fastcall" else f"_{self.name}"


@dataclass(frozen=True)
class Kernel:
    """A kernel export a shim may use: a function, called through a stub
    that jumps through its slot, or a variable (``data``), read through its
    slot (``__declspec(dllimport)``)."""
    name: str
    ordinal: int
    convention: str     # stdcall or fastcall; "data" for a variable
    arg_bytes: int
    slot: int | None    # its slot's address in the release's kernel thunk table; None: the game doesn't import it

    @property
    def mangled(self) -> str:
        """The symbol a shim's reference to it is, as clang mangles C for i386 Windows."""
        if self.convention == "data":
            return f"__imp__{self.name}"
        return f"@{self.name}@{self.arg_bytes}" if self.convention == "fastcall" else f"_{self.name}@{self.arg_bytes}"


@dataclass(frozen=True)
class Facts:
    release: Release
    sha256: str                        # the vanilla default.xbe's
    size: int
    sections: tuple[xbe.Section, ...]
    sites: Mapping[int, Site]          # by the release's own address
    addresses: Mapping[int, int] | None   # USA address -> this release's; None: USA's own
    absent: Mapping[int, str]          # USA address -> why this release has none
    functions: Mapping[str, Function] = field(default_factory=dict)   # by name
    kernel: Mapping[str, Kernel] = field(default_factory=dict)        # by name
    thunks: int = 0                    # the kernel thunk table's address (a booted XBE's header holds it)

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

    def mangled(self) -> dict[str, int]:
        """Each function's address by its mangled name (``coff.layout``'s ``vanilla``)."""
        return {f.mangled: f.va for f in self.functions.values()}


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
        hexed(raw.get("absent", {})),
        {name: Function(name, int(f["va"], 16), f["convention"], f["arg_bytes"], f.get("undecorated", False))
         for name, f in raw["functions"].items()},
        {name: Kernel(name, k["ordinal"], k["convention"], k["arg_bytes"], int(k["slot"], 16) if "slot" in k else None)
         for name, k in raw["kernel"].items()},
        int(raw["xbe"]["thunks"], 16))
