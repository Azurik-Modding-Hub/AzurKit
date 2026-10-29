"""The guest's page tables: virtual reads over physical RAM (Steps X.22, R1.26).

The Xbox kernel runs one page directory with no PAE: 4 KiB and 4 MiB pages, the directory mapping itself at
``PDE_BASE`` (its page tables at ``PTE_BASE``).  :func:`ram_reader` reads a VA out of a copy or a mapping of guest
RAM through them; :func:`find_page_directory` finds the directory in one.  Pure (no numpy, no Unicorn): simulator
Level 3 (:mod:`azurik_mod.sim.l3`) and the live tracker's shared-RAM link
(:mod:`azurkit.tools.randomizer.live_link`) both read through it.
"""

from __future__ import annotations

from typing import Callable

PDE_BASE, PTE_BASE = 0xC0300000, 0xC0000000
PAGE = 0x1000
CR3 = 0xF000          # the retail kernel's page directory (the vanilla registers' cr3)


def ram_reader(ram, pd: int, other: Callable[[int, int], bytes] | None = None) -> Callable[[int, int], bytes]:
    """``read(va, n)`` over a dump of guest RAM (``ram``, bytes-like, physical address 0 on): each page through
    the page tables the dump holds (the page directory at physical ``pd``: its own frame, the self-map's entry for
    ``PDE_BASE``; 4 MiB pages too).  A page that isn't present raises ``OSError``, as the gdbstub's E14; a page
    no RAM backs is read by ``other`` (the gdbstub), else raises.  Step X.22: an L3 snapshot reads its pages from
    one dump instead of the gdbstub."""
    size = len(ram)

    def u32(pa: int) -> int:
        return int.from_bytes(ram[pa:pa + 4], "little")

    def frame(va: int) -> int | None:
        pde = u32(pd + 4 * (va >> 22))
        if not pde & 1:
            return None
        if pde & 0x80:
            return (pde & 0xFFC00000) | (va & 0x3FF000)
        if (pde & 0xFFFFF000) + PAGE > size:
            return None
        pte = u32((pde & 0xFFFFF000) + 4 * ((va >> 12) & 0x3FF))
        return pte & 0xFFFFF000 if pte & 1 else None

    def read(va: int, n: int) -> bytes:
        out = bytearray()
        while n:
            k = min(n, PAGE - (va & 0xFFF))
            pa = frame(va)
            if pa is None:
                raise OSError(f"read {va:#x}: not present in the dump's page tables")
            if pa + PAGE <= size:
                out += ram[pa + (va & 0xFFF):pa + (va & 0xFFF) + k]
            elif other is not None:
                out += other(va, k)
            else:
                raise OSError(f"read {va:#x}: physical {pa:#x} is past the dump's {size:#x} bytes")
            va += k
            n -= k
        return bytes(out)
    return read


def maps_itself(ram, pd: int) -> bool:
    """Whether the page at physical ``pd`` of ``ram`` is a page directory: its entry for ``PDE_BASE`` is
    present, not a 4 MiB page, and its own frame."""
    at = pd + 4 * (PDE_BASE >> 22)
    if pd % PAGE or at + 4 > len(ram):
        return False
    pde = int.from_bytes(ram[at:at + 4], "little")
    return pde & 0x81 == 1 and pde & 0xFFFFF000 == pd


def find_page_directory(ram) -> int | None:
    """The physical address of the guest's page directory in ``ram``: ``CR3`` when it maps itself
    (:func:`maps_itself`), else the first page-aligned frame that does; None when none does (the kernel
    hasn't set paging up yet)."""
    if maps_itself(ram, CR3):
        return CR3
    return next((pa for pa in range(0, len(ram) - PAGE + 1, PAGE) if maps_itself(ram, pa)), None)
