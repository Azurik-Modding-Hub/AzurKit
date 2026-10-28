"""qol_alloc_race: the sound thread's map nodes come from the heap, so it
never races the load thread on STLport's 32-byte free list (AZ-695; on by
default).

STLport's node allocator keeps one global free list per block size and takes
no lock. The sound thread (0xAE450) keeps a map (0x37BC24) of 32-byte nodes,
while the load thread takes and frees blocks of the same list thousands of
times as a level loads. A thread switch inside the load thread's pop, with
the sound thread taking a node meanwhile, puts that node back on the list
while the map owns it, and the map's lookup 0xAF160 later follows a pointer
the load thread wrote: bugcheck 0x1E (about 1 schedule in 320 on the retail
disc, found by the xemu fork).

The map's thread runs only three of the list's sites: the pops in
``_M_insert`` (0xAF322) and ``create_node`` (0xAF3B0), each with its refill
call, and the push in ``erase`` (0xAE76C). The pack rewrites them in place to
call the game's own ``malloc`` (0xAB5B0) and ``free`` (0xAB580, the block in
EAX), which use the process heap, serialized. 71 bytes a release, no shim.
Ported from Modkit's ``azurik_mod/patches/qol_alloc_race`` at the packs
oracle's tag (oracle-packs-1), before Step 2.172d's fix (AZ-814).
"""

from __future__ import annotations

import struct

from azurkit.tools.mods.engine import Pack, PatchSpec

MALLOC = 0x000AB5B0   # cdecl malloc(size)
FREE = 0x000AB580     # free(EAX)


def _call(at: int, target: int) -> bytes:
    """A CALL rel32 at ``at`` to ``target``."""
    return b"\xE8" + struct.pack("<i", target - (at + 5))


def _pop(va: int) -> PatchSpec:
    """The pop at ``va`` and its refill (29 bytes) become a call of
    malloc(0x20) (push the size, call, pop it), then a jump to where both
    paths join with the node in EAX, the rest filled with no-ops."""
    return PatchSpec(label=f"the map's node from the heap at 0x{va:X}", va=va,
                     patch=b"\x6A\x20" + _call(va + 2, MALLOC) + b"\x83\xC4\x04\xEB\x11" + b"\x90" * 17, rel32=(3,))


PACK = Pack(
    name="qol_alloc_race",
    description="Fixes a rare crash (0x1E) loading a level: the sound thread's race.",
    sites=(_pop(0x000AF322), _pop(0x000AF3B0),
           PatchSpec(label="the map's node to the heap at 0xAE76C", va=0x000AE76C,
                     patch=_call(0x000AE76C, FREE) + b"\x90" * 8, rel32=(1,))),
    default_on=True,
)
