"""The releases as Live reads a running game (Modkit's ``assets.vanilla``
regions, on AzurKit's facts): each one's label, the kernel thunk table's
address its booted XBE's header holds (how Live tells which release xemu
runs) and its address of each USA address Live reads (Europe's from its
address map)."""

from __future__ import annotations

from dataclasses import dataclass

from azurkit.core import facts, gate


class UnmappedAddressError(ValueError):
    """A USA address the release has no address for; its text says why."""


@dataclass(frozen=True)
class Region:
    release: gate.Release

    @property
    def name(self) -> str:
        return self.release.name

    @property
    def label(self) -> str:
        return self.release.label

    @property
    def thunk_va(self) -> int:
        return facts.of(self.release).thunks

    def va(self, usa_va: int) -> int:
        """``usa_va``'s address in this release; :class:`UnmappedAddressError` naming why there is none."""
        try:
            return facts.of(self.release).va(usa_va)
        except LookupError as exc:
            raise UnmappedAddressError(str(exc)) from None


REGIONS = tuple(Region(release) for release in gate.RELEASES)
