"""fps_unlock: the game at any whole number of frames per second, F
(``target_fps``, 60 by default; 30 is vanilla and writes nothing).

Three caps hold the game at 30. The present wrapper (0x8FBE0) waits two
VBlanks a frame; D3D's flip waits for VSync too, and in xemu that is a second
wait. The main loop (0x58E40) runs ROUND(elapsed x 30.0) steps of 1/30 s a
frame, at most 2. At F the pack makes it wait ceil(60/F) VBlanks, skips the
flip's VSync and fence waits, and runs steps of 1/F, truncated, at most
ceil(F/15) (so a frame as slow as vanilla's 15 FPS floor still keeps time).
Each subsystem's private timestep 1/30 becomes 1/F, each 30.0 rate F, a
length or cap applied once a tick x 30/F, and a decay factor d applied once
a tick d^(30/F), read from vanilla where it stays and written to a private
slot (literal-pool padding nothing reads). The readers of the shared 30.0
that need degrees or seconds are pointed at a 30.0 nothing writes.

Europe has every USA site at its own address, but the two D3D ones: its
XDK 4039 D3D has stand-ins at its own addresses. The pack's sites are a
function of F (:func:`sites`), its slider :data:`TARGET_FPS`; it is a
``custom_apply`` whose footprint is every place :func:`sites` can name
(AZ-097). Ported from Modkit's
``azurik_mod/patches/fps_unlock`` at the packs oracle's tag; its comments
there hold the evidence for each site.
"""

from __future__ import annotations

import struct
from collections.abc import Callable

from azurkit.tools.mods.engine import Pack, ParametricPatch, PatchSpec, Place, Xbe

MAX_FPS = 15 * 127   # the step cap and the bounce limit are signed imm8 operands: ceil(F/15) <= 127
RATE = 0x1A28C8      # the main loop's rate, a double

# Each subsystem's private float 1/30, a per-call timestep or a scheduler interval.
SUBSYSTEM_DT = (0x1981C8, 0x198628, 0x198688, 0x1980A0, 0x198410, 0x198560, 0x1981E0, 0x19873C, 0x198120,
                0x1981F0, 0x198228, 0x1985D0, 0x198700, 0x198758, 0x198788, 0x198AB0, 0x1A2740, 0x1981B8,
                0x198968, 0x1989A8, 0x198C98, 0x198660, 0x198580, 0x198138, 0x1985B8, 0x1986E8, 0x1989C8,
                0x198A38)
SHARED_30 = 0x1A2650   # the float 30.0 most rate readers share: it becomes F
KEEP_30 = 0x1A2524     # the high half of a double 2^32 nobody writes: 30.0 as a float
# The readers of SHARED_30 that turn seconds or degrees, not ticks: their operand points at KEEP_30.
KEEP_30_READERS = (0x4E9D9, 0x89AAC, 0xFB518, 0xFB608, 0x3EBD5)
# (the reader's operand, the vanilla factor it reads, the private slot it reads instead)
DECAYS = ((0x2A0BC, 0x1A2774, 0x1A2704), (0x2A0CD, 0x1A2774, 0x1A2704), (0x2BB55, 0x1A2768, 0x1A2724))
PROBE, PROBE_SLOT, PROBE_READER = 0x1A2674, 0x1A268C, 0x86162   # the ground probe's 0.1, its slot and reader
SOLVER_CAP = 0x1AA230                                            # the collision solver's correction cap


# F, a whole number of frames per second from 1 to MAX_FPS (an encoding limit, D45); 30 is vanilla.
TARGET_FPS = ParametricPatch(name="target_fps", label="Frame rate", default=60, slider_min=30, slider_max=120,
                             slider_step=1, unit="fps", description="Frames per second; 30 is vanilla.", vanilla=30,
                             whole=(1, MAX_FPS), why="the step cap ceil(F/15) is a signed byte")


def _f32(value: float) -> bytes:
    return struct.pack("<f", value)


def _addr(va: int) -> bytes:
    return struct.pack("<I", va)


def sites(F: int, read: Callable[[int, int], bytes]) -> list[PatchSpec]:
    """Every site at the rate ``F`` (not 30, which writes nothing), in
    order; ``read(usa_va, size)`` gives vanilla bytes the values scale."""
    present = -(-60 // F)   # VBlanks a present waits: renders no faster than F
    cap = -(-F // 15)       # steps a frame may run: down to 15 FPS rendered
    vanilla = lambda va: struct.unpack("<f", read(va, 4))[0]   # noqa: E731

    # The step count: the x87 control word saved and truncation (RC=11) set around the FISTP, then the
    # steps clamped to [1, cap] and stored, and the branch past the catch-up taken from cap down. 58 bytes.
    # The clamp's floor and the store (9 bytes) are vanilla's own, 91 bytes into the site: read from there.
    steps = (bytes.fromhex("d97c2460 668b442460 660d000c 6689442462 d96c2462 db5c2430 d96c2460"
                           "8b742430 83fe01 7d05") + read(0x059AFD, 100)[91:]
             + bytes([0x83, 0xFE, cap]) + bytes.fromhex("7e3b 9090909090"))
    # The catch-up after a hitch: dt (the timestep's float, abs32 at 2) times cap steps, the count kept in
    # ESI by a push and pop of cap; at cap 4 two doublings make 4 dt, otherwise an integer multiply by the
    # count it stored. Then the clock becomes the elapsed time less that: the site's last 13 bytes, kept
    # (read from vanilla). 30 bytes.
    times = "dcc0dcc0 89742414" if cap == 4 else "89742414 da4c2414"
    catchup = (bytes.fromhex("d905") + _addr(0x1983E8) + bytes([0x6A, cap, 0x5E]) + bytes.fromhex(times)
               + read(0x059B37, 30)[17:])

    out = [
        PatchSpec(label=f"VBlank wait 2->{present}", va=0x08FD19, patch=bytes([0x83, 0xC1, present])),
        PatchSpec(label="no D3D Present VSync", va=0x12635D, patch=b"\x90\x90", releases=("usa",)),
        PatchSpec(label="no D3D flip VSync", va=0x122BA9, patch=b"\x90\x90", releases=("europe",)),
        PatchSpec(label=f"rate 30->{F}", va=RATE, patch=struct.pack("<d", F)),
        PatchSpec(label=f"timestep 1/30->1/{F}", va=0x1983E8, patch=_f32(1 / F)),
        PatchSpec(label=f"steps truncated, at most {cap}", va=0x059AFD, patch=steps),
        PatchSpec(label=f"catch-up of {cap} steps", va=0x059B37, patch=catchup, abs32=(2,)),
        *(PatchSpec(label=f"subsystem timestep 1/{F}", va=va, patch=_f32(1 / F)) for va in SUBSYSTEM_DT),
        PatchSpec(label=f"animation clock 1/{F}", va=0x1A2750, patch=struct.pack("<d", 1 / F)),
        PatchSpec(label=f"shared rate 30->{F}", va=SHARED_30, patch=_f32(F)),
        *(PatchSpec(label="keeps reading 30.0", va=va, patch=_addr(KEEP_30), abs32=(0,)) for va in KEEP_30_READERS),
        *(PatchSpec(label=f"decay ^(30/{F})", va=slot, patch=_f32(vanilla(factor) ** (30 / F)))
          for factor, slot in dict.fromkeys((factor, slot) for _, factor, slot in DECAYS)),
        *(PatchSpec(label="reads its decay's slot", va=va, patch=_addr(slot), abs32=(0,)) for va, _, slot in DECAYS),
        PatchSpec(label="no Present spin-wait", va=0x1263E2, patch=b"\xEB", releases=("usa",)),
        PatchSpec(label="no Swap fence wait (copy)", va=0x122CB2, patch=b"\xEB", releases=("europe",)),
        PatchSpec(label="no Swap fence wait (flip)", va=0x122D02, patch=b"\xEB", releases=("europe",)),
        PatchSpec(label=f"bounce limit 2->{cap}", va=0x47EEF, patch=bytes([cap])),
        PatchSpec(label="ground probe x 30/F", va=PROBE_SLOT, patch=_f32(vanilla(PROBE) * 30 / F)),
        PatchSpec(label="reads the probe's slot", va=PROBE_READER, patch=_addr(PROBE_SLOT), abs32=(0,)),
    ]
    if F * F > 1800:   # the solver's doubling, x2 or x1, whichever is nearer 60/F
        out += [PatchSpec(label="solver doubling off", va=va, patch=b"\x90\x90") for va in (0x47BC6, 0x47CF3)]
    out.append(PatchSpec(label="solver cap x 30/F", va=SOLVER_CAP, patch=_f32(vanilla(SOLVER_CAP) * 30 / F)))
    return out


def apply(xbe: Xbe, target_fps: int) -> None:
    if target_fps != 30:
        for spec in sites(target_fps, xbe.read):
            xbe.patch(spec)


PACK = Pack(
    name="fps_unlock",
    description="Runs the game at a chosen frame rate (60 FPS by default) instead of 30.",
    sites=(TARGET_FPS,),
    custom_apply=apply,
    footprint=tuple(Place(va=s.va, releases=s.releases) for s in sites(60, lambda va, size: bytes(size))),
)
