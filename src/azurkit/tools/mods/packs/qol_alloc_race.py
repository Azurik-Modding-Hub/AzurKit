"""qol_alloc_race: the sound thread's map nodes come from the heap, so it
never races the load thread on STLport's 32-byte free list (AZ-695); the
disc-copy thread takes its refused stream buffer past the budget instead of
evicting the run lists (AZ-814), and its out-of-memory evictions run on main
while main runs (AZ-817). On by default.

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
vanilla's pages are, and returned by the stream's close. The loop keeps
vanilla's own code where the new one keeps it, read from the player's image
at the site (its lock, its sleep, the lock's release), so this file holds
only the code it adds.

Only when that commit is refused too does the loop evict, and the copy
thread's other eviction, its stream object's heap failure (0xB5D35), with
it: both call a door, vanilla's dead evict-all 0xA66C0 (no code calls it),
which jumps to the copy gate (``shims/qol_alloc_race.c``, the size in ECX,
AL the answer). While main sleeps in its wait on the copy (0xB14E1) the
copy thread evicts at once and main's wake waits until it is done; else
main's next frame (its wheel tick, 0x59C90) evicts for it while the copy
thread sleeps, and after about half a second with neither it evicts itself,
vanilla's way. Each hook lands its own copy of the shim, so the gate's state
lives in the door's landing, which main's two hooks reach through the door
with an op in ECX. Other threads' out-of-memory evictions stay vanilla.

211 bytes in place and three hooks into the shim, on both releases. Ported
from Modkit's ``azurik_mod/patches/qol_alloc_race`` at the packs oracle's
tag (oracle-packs-4, Step 2.172g's copy gate).
"""

from __future__ import annotations

import struct
from collections.abc import Callable

from azurkit.tools.mods.engine import Pack, PatchSpec, Place, TrampolinePatch, Xbe

MALLOC = 0x000AB5B0   # cdecl malloc(size)
FREE = 0x000AB580     # free(EAX)

COPY_LOOP = 0x000B54D0         # 0xB5490's buffer loop, to its give-up 0xB5555
COPY_SIZE = 0x85               # the loop's bytes, the site's size
GIVE_UP = 0x000B5555           # the loop's way out with no buffer
GOT_BUFFER = 0x000B555D        # the loop's way out with a buffer
RUN_PAGES_ALLOC = 0x000BAB60   # run_pages_alloc(size): 0 past the budget
RUN_PAGES_COMMIT = 0x000BAB94  # run_pages_alloc past its budget test (ECX: the size to 64 KiB)
DOOR = 0x000A66C0              # vanilla's dead evict-all, jumped to the copy gate
SHIM = "qol_alloc_race"        # the copy gate's object: shims/qol_alloc_race.o


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
    committed past the budget before the lock's release, and a commit
    refused too sent to the copy gate; ``read(usa_va, size)`` gives the
    release's vanilla bytes, whose code the loop keeps.

    Kept from vanilla: the size's load and the lock's first try (17 bytes),
    the spin's sleep (7, in place), and the release, the buffer's store and
    its test (14, from 0x30). They carry the release's own addresses; the
    calls placed here are relocated by the engine (``rel32``)."""
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
             # Refused: the stream's size (its +0x1C) in ECX to the copy gate, which evicts; anything freed
             # retries the loop, else on to vanilla's give-up past the no-ops.
             + b"\x8B\x4B\x1C" + _call(at + 0x4D, DOOR) + b"\x84\xC0" + _short(0x75, at + 0x54, at)
             + _short(0xEB, at + 0x56, GIVE_UP) + b"\x90" * (GIVE_UP - (at + 0x58)))
    return PatchSpec(label="the copy thread's stream buffer past the budget, a refused commit through the copy "
                           "gate, at 0xB54D0", va=COPY_LOOP, patch=patch, rel32=(0x1E, 0x36, 0x4E))


def _hook(label: str, va: int, symbol: str, mode: str = "call") -> TrampolinePatch:
    return TrampolinePatch(label=f"the copy thread's evictions: {label}", va=va, shim=SHIM, symbol=symbol, mode=mode)


def sites(read: Callable[[int, int], bytes]) -> tuple[PatchSpec | TrampolinePatch, ...]:
    """Every site, in order; ``read(usa_va, size)`` gives the release's vanilla bytes."""
    return (_pop(0x000AF322), _pop(0x000AF3B0),
            PatchSpec(label="the map's node to the heap at 0xAE76C", va=0x000AE76C,
                      patch=_call(0x000AE76C, FREE) + b"\x90" * 8, rel32=(1,)),
            _copy_buffer(read),
            # 0xB5D00's out-of-memory loop (ECX = 0x34): the copy gate in place of the handler table's call
            PatchSpec(label="the copy thread's stream object: its out-of-memory eviction through the copy gate at "
                            "0xB5D35", va=0x000B5D35, patch=_call(0x000B5D35, DOOR) + b"\x90\x90", rel32=(1,)),
            _hook("the gate, behind vanilla's dead evict-all at 0xA66C0", DOOR, "@c_copy_gate@4", "jmp"),
            _hook("main's frame serves them, at 0x59C90", 0x00059C90, "_c_main_tick"),   # the wheel advance's call
            _hook("main asleep on the copy, at 0xB14E1", 0x000B14E1, "_c_main_park_wait@16"))   # its wait's call


def apply(xbe: Xbe) -> None:
    for spec in sites(xbe.read):
        xbe.patch(spec)


PACK = Pack(
    name="qol_alloc_race",
    description="Fixes rare crashes loading levels: the sound thread's (0x1E) and disc copy's.",
    custom_apply=apply,
    footprint=tuple(Place(va=s.va) for s in sites(lambda va, size: bytes(size))),
    default_on=True,
)
