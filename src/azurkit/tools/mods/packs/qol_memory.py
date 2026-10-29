"""The memory packs: the load budget and the RAM past 64 MiB.

**qol_memory_budget** (D515, on by default since D528): boot sets the one
limit every archive's load runs are read under once, to 40 MiB, with an
imm32 at 0x596CC; ``budget_mib`` rewrites it (42 by default: the most that
held in xemu, where the game's own memory check cuts a larger one back).
Its shim (``shims/qol_memory_budget.c``) also retries the stream pump's
CreateThread (0xB5CED) every 20 ms for up to about 5 s when free memory runs
out at a level change, where vanilla marks the pump running without a thread
and "Loading..." holds for good (AZ-687).

**qol_memory_upper64** (D520, on by default since D571): on a 128 MiB
machine (xemu at 128, or an upgraded console, untested) its shim maps the
upper 64 MiB at 0x84000000 through the page directory and places the
virtual (mode-0) load runs there, outside the budget's counter: the run
allocator's call of its page allocator (0xA490C) and the run free's call of
VirtualFree (0xBAD55). Inert on 64 MiB.

**qol_memory_upper64_gpu** (D576, on by default since D588), with
upper64: the contiguous (mode-1) runs, the GPU's, in write-combined blocks
of the same heap (the allocator's XPhysicalAlloc at 0xA48FA, the free's
XPhysicalFree at 0xBAD46, which falls through to the kernel's
MmFreeContiguousMemory), past the budget's compare (0xA48DD) when the heap
holds the run; D3D's address masks widen from 0x3FFFFFF to 0x0FFFFFFF and
its DMA objects' limit (0x12D552) rises on a 128 MiB machine.

**qol_memory_upper256** (D600, off by default), with both: xemu at 256 MiB
(D601: xemu only); a probe on the mode-1 path (0xA48D7) maps the RAM from
128 to 256 MiB as the heap's third tier where it answers.

The heap the three upper shims share is ``shims/qol_memory_heap.h``. None
names an address of the image, so both releases take them. Ported from
Modkit's ``azurik_mod/patches/qol_memory_*`` at the packs oracle's tag,
whose READMEs and docstrings hold the evidence.
"""

from __future__ import annotations

import struct

from azurkit.tools.mods.engine import Pack, ParametricPatch, PatchSpec, TrampolinePatch

MiB = 1 << 20


def _budget(mib: float) -> bytes:
    """``mib`` MiB as the limit's u32 of bytes; ``ValueError`` past what it holds (D45)."""
    n = round(mib * MiB)
    if not 0 <= n <= 0xFFFFFFFF:
        raise ValueError(f"{mib:g} MiB is outside the limit's u32 of bytes (0 to under 4096 MiB)")
    return struct.pack("<I", n)


BUDGET = ParametricPatch(name="budget_mib", label="Load budget", va=0x000596CC, default=42.0, slider_min=40.0,
                         slider_max=44.0, slider_step=1.0, unit="MiB", encode=_budget,
                         decode=lambda b: struct.unpack("<I", b)[0] / MiB,
                         description="Room for loaded levels, models and menus (vanilla 40 MiB); cut back past 42.")

BUDGET_PACK = Pack(
    name="qol_memory_budget",
    description="Raises the game's 40 MiB load budget, so a larger player model fits.",
    sites=(BUDGET, TrampolinePatch(label="Stream pump: CreateThread retried for up to 5 s (AZ-687)", va=0x000B5CED,
                                   shim="qol_memory_budget", symbol="_c_pump_create@24")),
    default_on=True,
)

UPPER64_PACK = Pack(
    name="qol_memory_upper64",
    description="Levels load past 64 MiB in 128 MiB xemu or consoles (untested); inert on 64 MiB.",
    sites=(TrampolinePatch(label="Upper 64 MiB: the run allocator's mode-0 placement", va=0x000A490C,
                           shim="qol_memory_upper64", symbol="_c_upper64_alloc@4"),
           TrampolinePatch(label="Upper 64 MiB: the run free's VirtualFree", va=0x000BAD55, shim="qol_memory_upper64",
                           symbol="_c_upper64_free")),
    default_on=True,
)

_AND = {"eax": b"\x25", "ecx": b"\x81\xE1", "edx": b"\x81\xE2"}   # and reg, imm32


def _mask(va: int, reg: str, releases: tuple[str, ...] = ()) -> PatchSpec:
    """D3D's ``and reg, 0x3FFFFFF`` at ``va`` widened to 0x0FFFFFFF: the same
    output below 64 MiB, the right page above it, to 256 MiB."""
    return PatchSpec(label=f"Upper 64 MiB GPU: D3D address mask at 0x{va:X}", va=va,
                     patch=_AND[reg] + struct.pack("<I", 0x0FFFFFFF), releases=releases)


# The 22 masks (D576: every live or dead one), then D3DDevice_SetTile's, ECX in USA and EDX in Europe (XDK 4039),
# each at its release's own address, and Europe's second KickOff PUT path, which USA's D3D doesn't have.
MASKS = (*(_mask(va, reg) for va, reg in (
    (0x0011DF40, "eax"), (0x0011E074, "eax"), (0x001212D0, "eax"), (0x00121390, "eax"),
    (0x00123E90, "eax"), (0x00123EE5, "eax"), (0x00123F2C, "ecx"), (0x00123FBD, "eax"),
    (0x00124047, "edx"), (0x001240D3, "eax"), (0x001242C0, "eax"), (0x00124360, "eax"),
    (0x00124441, "eax"), (0x00124640, "eax"), (0x001249BD, "eax"), (0x00125160, "eax"),
    (0x0012A060, "eax"), (0x0012A15A, "eax"), (0x0012A3B8, "edx"), (0x0012D120, "eax"),
    (0x0012D497, "eax"))),
    _mask(0x0011F8F8, "ecx", ("usa",)), _mask(0x001203D8, "edx", ("europe",)), _mask(0x00129111, "eax", ("europe",)))


def _gpu(label: str, va: int, what: str) -> TrampolinePatch:
    return TrampolinePatch(label=f"Upper 64 MiB GPU: {label}", va=va, shim="qol_memory_upper64_gpu",
                           symbol=f"_c_upper64_gpu_{what}")


UPPER64_GPU_PACK = Pack(
    name="qol_memory_upper64_gpu",
    description="With qol_memory_upper64: textures and meshes past 64 MiB too; inert on 64 MiB.",
    sites=(_gpu("the run allocator's mode-1 placement", 0x000A48FA, "alloc"),
           _gpu("the run free's XPhysicalFree", 0x000BAD46, "free"),
           _gpu("D3D's DMA object limits", 0x0012D552, "limit"),
           _gpu("the run allocator's mode-1 budget compare", 0x000A48DD, "budget"),
           *MASKS),
    default_on=True,
    requires=("qol_memory_upper64",),   # its runs are placed in upper64's heap
)

UPPER256_PACK = Pack(
    name="qol_memory_upper256",
    description="With both upper packs: RAM to 256 MiB (xemu v0.16.2+ at 256 MiB); inert below.",
    sites=(TrampolinePatch(label="Upper 256 MiB: T3's probe on the run allocator's mode-1 path", va=0x000A48D7,
                           shim="qol_memory_upper256", symbol="_c_upper256_probe"),),
    requires=("qol_memory_upper64", "qol_memory_upper64_gpu"),
)
