"""The pack engine: a pack's sites, as data, planned into a layer of changes.

A site (:class:`PatchSpec`) is the bytes a pack writes at an address. It is
a USA address (the canonical ones), which another release's address map
moves (``core.facts``), with the absolute addresses at the patch's ``abs32``
offsets and the targets of its rel32 branches at its ``rel32`` offsets moved
along; a site that names releases without USA is that release's own, at its
own address. The facts give each site's size and the sha256 of its vanilla
bytes, which the input must hold there (D27). A pack holds only what it
writes, never vanilla bytes (D3).

A pack writes its sites in order, or its ``custom_apply(xbe, **params)``
writes through the :class:`Xbe` it is given, only inside the ``footprint``
it declares (AZ-097). :func:`plan` makes a pack's layer (one group per
site), planned against the release's vanilla XBE, or raises
:class:`PackError` naming every site that failed and why: by its label and
address, never its bytes (D35).
"""

from __future__ import annotations

import hashlib
import inspect
import struct
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from azurkit.core import facts as facts_
from azurkit.core.gate import Release
from azurkit.edits.layer import Change, Layer

XBE = "default.xbe"


class PackError(ValueError):
    """A pack that can't be planned, with every reason by name (D35)."""


@dataclass(frozen=True, kw_only=True)
class Place:
    """An address a pack may write: a USA one, or (``releases`` without USA)
    those releases' own. ``releases`` empty: every release the pack lists."""
    va: int
    releases: tuple[str, ...] = ()

    def on(self, release: str) -> bool:
        return not self.releases or release in self.releases

    def own(self, facts: facts_.Facts) -> int:
        """Its address in the release of ``facts``; ``LookupError`` says why there is none."""
        return self.va if self.releases and "usa" not in self.releases else facts.va(self.va)


@dataclass(frozen=True, kw_only=True)
class PatchSpec(Place):
    """``patch`` written at the site :attr:`va`."""
    label: str
    patch: bytes
    abs32: tuple[int, ...] = ()   # offsets in patch of each absolute address it holds
    rel32: tuple[int, ...] = ()   # offsets in patch of each rel32 branch displacement

    def placed(self, facts: facts_.Facts, va: int) -> bytes:
        """The patch at ``va``, its address in the release of ``facts``."""
        if facts.addresses is None or (self.releases and "usa" not in self.releases):
            return self.patch
        out = bytearray(self.patch)
        for k in self.abs32:
            struct.pack_into("<I", out, k, facts.va(struct.unpack_from("<I", out, k)[0]))
        for k in self.rel32:
            target = (self.va + k + 4 + struct.unpack_from("<i", out, k)[0]) & 0xFFFFFFFF
            struct.pack_into("<i", out, k, facts.va(target) - (va + k + 4))
        return bytes(out)


@dataclass(frozen=True)
class Pack:
    name: str
    description: str
    sites: tuple[PatchSpec, ...] = ()
    custom_apply: Callable[..., None] | None = None   # (xbe: Xbe, **params); it writes only by Xbe.patch
    footprint: tuple[Place, ...] = ()                   # every place custom_apply may write
    default_on: bool = False                            # every build applies it unless told not to (D528)
    category: str = "qol"
    releases: tuple[str, ...] = ("usa", "europe")

    def parameters(self) -> dict[str, object]:
        """Each parameter it takes, with its default."""
        if self.custom_apply is None:
            return {}
        return {p.name: p.default for p in list(inspect.signature(self.custom_apply).parameters.values())[1:]}


def digest(data: bytes) -> str:
    """``data`` as messages name it: its size and sha256, never its bytes."""
    return f"<{len(data)} B, sha256 {hashlib.sha256(data).hexdigest()[:12]}>"


class Xbe:
    """A release's vanilla ``default.xbe`` as a pack plans against it: what
    it reads there, and the sites it writes."""

    def __init__(self, facts: facts_.Facts, vanilla: bytes, pack: Pack):
        self.release = facts.release.name
        self._facts, self._vanilla, self._pack = facts, vanilla, pack
        self.changes: list[Change] = []
        self.failures: list[str] = []
        self._written: set[int] = set()
        self._allowed: set[int] | None = None
        if pack.custom_apply is not None:
            self._allowed = set()
            for place in pack.footprint:
                if place.on(self.release):
                    try:
                        self._allowed.add(place.own(facts))
                    except LookupError as exc:
                        self.failures.append(f"its footprint at 0x{place.va:08X}: {exc}")

    def read(self, usa_va: int, size: int) -> bytes:
        """The vanilla bytes at ``usa_va`` in this release."""
        offset = self._facts.offset(self._facts.va(usa_va), size)
        return self._vanilla[offset:offset + size]

    def patch(self, spec: PatchSpec) -> None:
        """Write ``spec`` (nothing when it isn't one of this release's), or
        record why it can't be written."""
        if not spec.on(self.release):
            return
        where = f"{spec.label} at 0x{spec.va:08X}"
        try:
            va = spec.own(self._facts)
            where += f" ({self._facts.release.label} 0x{va:08X})" if va != spec.va else ""
            site = self._facts.site(va)
            data = spec.placed(self._facts, va)
            offset = self._facts.offset(va, site.size)
        except (LookupError, ValueError, struct.error) as exc:
            self.failures.append(f"{where}: {exc}")
            return
        held = self._vanilla[offset:offset + site.size]
        if self._allowed is not None and va not in self._allowed:
            why = "it is outside the pack's declared footprint"
        elif va in self._written:
            why = "the pack writes it twice"
        elif len(data) != site.size:
            why = f"the patch is {len(data)} B, the facts' site {site.size} B"
        elif hashlib.sha256(held).hexdigest() != site.sha256:
            why = f"default.xbe holds {digest(held)} there, not the facts' <{site.size} B, sha256 {site.sha256[:12]}>"
        else:
            self._written.add(va)
            self.changes.append(Change(XBE, offset, site.sha256, data, f"{self._pack.name} 0x{va:08X} ({spec.label})"))
            return
        self.failures.append(f"{where}: {why}")


def plan(pack: Pack, release: Release, vanilla: bytes, params: Mapping[str, object] | None = None) -> Layer:
    """``pack``'s layer on ``release``, planned against its vanilla
    ``default.xbe`` (``vanilla``) with ``params``; :class:`PackError` names
    each reason it can't be (D35)."""
    params = dict(params or {})
    if release.name not in pack.releases:
        raise PackError(f"pack {pack.name!r} is not available on the {release.label} release "
                        f"(it supports {', '.join(pack.releases)})")
    facts = facts_.of(release)
    if len(vanilla) != facts.size or hashlib.sha256(vanilla).hexdigest() != facts.sha256:
        raise PackError(f"pack {pack.name!r}: default.xbe {digest(vanilla)} is not the vanilla {release.label} one")
    xbe = Xbe(facts, vanilla, pack)
    if pack.custom_apply is None:
        if params:
            raise PackError(f"pack {pack.name!r} takes no parameters (given: {', '.join(map(str, params))})")
        for spec in pack.sites:
            xbe.patch(spec)
    else:
        try:
            inspect.signature(pack.custom_apply).bind(xbe, **params)
        except TypeError as exc:
            raise PackError(f"pack {pack.name!r}: {exc} (its parameters: "
                            f"{', '.join(pack.parameters()) or 'none'})") from None
        try:
            pack.custom_apply(xbe, **params)
        except (LookupError, ValueError) as exc:
            raise PackError(f"pack {pack.name!r}: {exc}") from None
    if xbe.failures:
        raise PackError(f"pack {pack.name!r}: {len(xbe.failures)} site(s) failed: " + "; ".join(xbe.failures))
    return Layer(f"pack {pack.name}", "mods", "packs", {"pack": pack.name, "params": params}, tuple(xbe.changes))
