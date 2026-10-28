"""qol_alloc_race: the sound thread's map nodes come from the heap, so it
never races the load thread on STLport's 32-byte free list (AZ-695), and the
disc-copy thread takes its refused stream buffer past the budget instead of
evicting the run lists (AZ-814). On by default.

STLport's node allocator keeps one global free list per block size and takes
no lock. The sound thread (0xAE450) keeps a map (0x37BC24) of 32-byte nodes,
while the load thread takes and frees blocks of the same list thousands of
times as a level loads. A thread switch inside the load thread's pop, with
the sound thread taking a node meanwhile, puts that node back on the list
while the map owns it, and the map's lookup 0xAF160 later follows a pointer
the load thread wrote: bugcheck 0x1E (about 1 schedule in 320 on the retail
disc, found by the xemu fork). The map's thread runs only three of the
list's sites: the pops in ``_M_insert`` (0xAF322) and ``create_node``
(0xAF3B0), each with its refill call, and the push in ``erase`` (0xAE76C).
The pack rewrites them in place to call the game's own ``malloc`` (0xAB5B0)
and ``free`` (0xAB580, the block in EAX), which use the process heap,
serialized.

The disc-copy thread (0xB0C70) opens a stream whose 1 MiB buffer 0xB5490's
loop (0xB54D0) takes through ``run_pages_alloc`` (0xBAB60) under the page
spinlock (0x1BF538). When the 40 MiB budget refuses it, vanilla releases the
lock and evicts runs from the expired list and the expiry wheel's 30 slots,
lists no lock guards and main walks every frame. The rewritten loop gives a
refused buffer of a stream with read-ahead 0 (the copy thread's; the movie's
asks for 0x200000) its pages past the budget, inside the same lock, by
entering ``run_pages_alloc`` past its budget test (0xBAB94): counted as
vanilla's pages are, and returned by the stream's close. Only when that
commit is refused too does vanilla's eviction run, unchanged. The loop keeps
vanilla's own code where the new one keeps it, read from the player's image
at the site (its lock, its sleep, the lock's release, the eviction's walk),
so this file holds only the code it adds.

71 + 133 bytes a release, no shim. Ported from Modkit's
``azurik_mod/patches/qol_alloc_race`` at the packs oracle's tag
(oracle-packs-2, Step 2.172d's fix).
"""

from __future__ import annotations

import struct
from collections.abc import Callable

from azurkit.tools.mods.engine import Pack, PatchSpec, Place, Xbe

MALLOC = 0x000AB5B0   # cdecl malloc(size)
FREE = 0x000AB580     # free(EAX)

COPY_LOOP = 0x000B54D0         # 0xB5490's buffer loop, to its give-up 0xB5555
COPY_SIZE = 0x85               # the loop's bytes, the site's size
GOT_BUFFER = 0x000B555D        # the loop's way out with a buffer
RUN_PAGES_ALLOC = 0x000BAB60   # run_pages_alloc(size): 0 past the budget
RUN_PAGES_COMMIT = 0x000BAB94  # run_pages_alloc past its budget test (ECX: the size to 64 KiB)
RUN_EVICT = 0x000A6450         # evict(list, size): the bytes it freed


def _call(at: int, target: int) -> bytes:
    """A CALL rel32 at ``at`` to ``target``."""
    return b"\xE8" + struct.pack("<i", target - (at + 5))


def _short(opcode: int, at: int, target: int) -> bytes:
    """A short jump (``opcode``, rel8) at ``at`` to ``target``."""
    return bytes([opcode]) + struct.pack("<b", target - (at + 2))


def _pop(va: int) -> PatchSpec:
    """The pop at ``va`` and its refill (29 bytes) become a call of
    malloc(0x20) (push the size, call, pop it), then a jump to where both
    paths join with the node in EAX, the rest filled with no-ops."""
    return PatchSpec(label=f"the map's node from the heap at 0x{va:X}", va=va,
                     patch=b"\x6A\x20" + _call(va + 2, MALLOC) + b"\x83\xC4\x04\xEB\x11" + b"\x90" * 17, rel32=(3,))


def _copy_buffer(read: Callable[[int, int], bytes]) -> PatchSpec:
    """0xB54D0's loop with a refused buffer of a read-ahead-0 stream
    committed past the budget before the lock's release; ``read(usa_va,
    size)`` gives the release's vanilla bytes, whose code the loop keeps.

    Kept from vanilla: the size's load and the lock's first try (17 bytes),
    the spin's sleep (7, in place), the release, the buffer's store and its
    test (14, from 0x30), and the eviction, moved 10 bytes on: its expired
    list's call (10, from 0x40), the result's test (5, from 0x4E), the
    wheel's first slot (5, from 0x54), the slot walk's test and pushes (7,
    from 0x60) and its step to the next slot (13, from 0x6B). They carry the
    release's own addresses; the calls placed here are relocated by the
    engine (``rel32``)."""
    at, old = COPY_LOOP, read(COPY_LOOP, COPY_SIZE)
    patch = (old[0x00:0x11] + _short(0x74, at + 0x11, at + 0x1C)   # took the lock: on to the alloc
             + old[0x13:0x1A] + _short(0xEB, at + 0x1A, at + 0x03)   # slept: try the lock again
             # Push the size and call run_pages_alloc. A buffer, or a stream with read-ahead (not the copy
             # thread's), goes on to the release; else the size rounded up to 64 KiB in ECX, the size pushed,
             # and the call past the budget test.
             + b"\x56" + _call(at + 0x1D, RUN_PAGES_ALLOC)
             + b"\x85\xC0" + _short(0x75, at + 0x24, at + 0x3A)
             + b"\x39\x43\x20" + _short(0x75, at + 0x29, at + 0x3A)
             + b"\x8D\x8E" + struct.pack("<I", 0xFFFF) + b"\x66\x33\xC9"
             + b"\x56" + _call(at + 0x35, RUN_PAGES_COMMIT)
             + old[0x30:0x3E] + _short(0x75, at + 0x48, GOT_BUFFER)
             # The eviction, moved: its two calls, the retry of the loop after the expired list freed
             # anything, then its slot walk as vanilla's.
             + old[0x40:0x4A] + struct.pack("<i", RUN_EVICT - (at + 0x58))
             + old[0x4E:0x53] + struct.pack("<b", at - (at + 0x5E))
             + old[0x54:0x59]
             + old[0x60:0x67] + struct.pack("<i", RUN_EVICT - (at + 0x6E))
             + old[0x6B:0x78]
             # Freed anything: retry the loop; else on to vanilla's give-up past four no-ops.
             + b"\x85\xFF" + _short(0x75, at + 0x7D, at) + b"\xEB\x04" + b"\x90" * 4)
    return PatchSpec(label="the copy thread's stream buffer past the budget at 0xB54D0", va=COPY_LOOP, patch=patch,
                     rel32=(0x1E, 0x36, 0x54, 0x6A))


def sites(read: Callable[[int, int], bytes]) -> tuple[PatchSpec, ...]:
    """Every site, in order; ``read(usa_va, size)`` gives the release's vanilla bytes."""
    return (_pop(0x000AF322), _pop(0x000AF3B0),
            PatchSpec(label="the map's node to the heap at 0xAE76C", va=0x000AE76C,
                      patch=_call(0x000AE76C, FREE) + b"\x90" * 8, rel32=(1,)),
            _copy_buffer(read))


def apply(xbe: Xbe) -> None:
    for spec in sites(xbe.read):
        xbe.patch(spec)


PACK = Pack(
    name="qol_alloc_race",
    description="Fixes a rare crash (0x1E) loading a level, and keeps the disc-copy thread off the run lists.",
    custom_apply=apply,
    footprint=tuple(Place(va=s.va) for s in sites(lambda va, size: bytes(size))),
    default_on=True,
)
