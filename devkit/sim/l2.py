"""Simulator Level 2: run the game's own code under Unicorn.

Modkit's Steps 2.8-2.10 and 2.12 (behavior tests 5-6 and 8-14, and the
roll; ported in Step 4.13a).  :class:`Sim` loads a built XBE the way the Xbox loader
does (header and every section at its VA, appended sections such as
SHIMS included, BSS zero-filled) and calls game functions, *probes*, on
a named fake state:

- every kernel import is a stub that returns 0 (or what a probe's
  :attr:`Sim.kernel` callback computes) and pops the argument bytes
  :data:`_KERNEL_H` gives it (``data/kernel.toml``);
- the x87 control word is the game's 0x023F (53-bit precision: the game
  calls ``_controlfp(_PC_53)``, and the vanilla xemu dump holds it);
- the assert handler 0xA9000 never returns, so a call to it fails the
  probe with the game's file, line and expression;
- a probe's stub table names the callees that return at once with a
  fixed EAX (or one a Python callback computes); each pops the ``ret N``
  of its first ``ret`` before the next known function
  (:data:`RET_N_OVERRIDES` covers what that scan can't).  A stub whose
  caller cleans the stack itself, and a probe that returns with ESP off,
  fail;
- :class:`Player` names every value the probes read from the fake
  structs, ControllerState 0x37BE98 and the controller index 0x1A7AE4;
  reading any other byte there that a probe didn't write first fails;
- the code L2 can't judge is a committed fact, :data:`BLIND_SPOTS`: a
  probe may stub only a function listed there, and a build that changes
  a listed range loads only for a test signed off by an xemu session
  that lists the range (:attr:`Sim.signoff`).

:class:`PlayerSim` runs the movement probes in order on one memory, the
way consecutive ticks would: ``jump`` (player_jump_init 0x89060),
``flap`` (wing_flap 0x89300 with the real consume_fuel 0x842D0),
``fall`` (the next tick's player_airborne_tick 0x89480 up to the move
call in gravity_integrate_raw), ``walk`` (player_walk_state 0x85F50
up to its move call at 0x860C8) and ``roll`` (the attack-move entry
0x88990, then its tick 0x8C7D0 until the clip ends).  :func:`armor_slots`
runs the game's armor loader 0x3C700 on a ``config.xbr``,
:func:`boot_tick` one tick of the boot state machine 0x5F620,
:func:`transform_world` a transform chain's world matrix (0x68BE0 and
0x681E0, the check of ``nodes.Graph.world``), :class:`Runs` the load runs'
allocator 0xA4890 and free 0xBAD10, :func:`pump_start` the stream pump's
start 0xB5CC0, :func:`node_race` the sound thread's map node sites against
the load thread's free on STLport's 32-byte list, and :func:`build_physics` builds the XBE the tests probe with the real
``player_physics`` pack.

A pass means "the patched code computes this value from this state", not
"the game behaves this way" (§5.4 "Not proven"): the state is one xemu
dump plus the press each probe models, and the fields the dump doesn't
reach and everything behind a stub are assumptions.
"""

from __future__ import annotations

import ctypes
import hashlib
import math
import struct
import tomllib
from bisect import bisect_right
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

from capstone import CS_ARCH_X86, CS_MODE_32, Cs
from unicorn import (UC_ARCH_X86, UC_HOOK_CODE, UC_HOOK_MEM_READ,
                     UC_HOOK_MEM_WRITE, UC_MODE_32, UC_PROT_ALL, Uc, UcError)
from unicorn import x86_const as X

from devkit.sim.ports import apply_pack
from devkit.sim.ports import parse_kernel_thunks
from devkit.sim.ports import get_pack
from devkit.sim.ports import all_entries
from devkit.sim.ports import parse_xbe_sections
from devkit.sim import require_usa

FPU_CW = 0x023F
ASSERT_HANDLER = 0xA9000    # EDI = expression, [esp+4] = file, [esp+8] = line
CONTROLLERS = 0x37BE98      # ControllerState[4], stride 0x54
CONTROLLER_INDEX = 0x1A7AE4  # 0-3, or 4 = none (reads ControllerState[0])
GRAVITY_VA = 0x1980A8       # f32 9.8: the g jump_init (0x89160) and the airborne tick load
F32_EPS = 2.0 ** -23        # float32 relative precision, the unit of a probe's tolerance

RET_N_OVERRIDES: dict[int, int | None] = {
    ASSERT_HANDLER: None,   # noreturn: the scan would take a neighbour's ret
}

_PAGE = 0x1000
_STACK_TOP = 0x01000000     # stack: the 1 MiB below this
_FAKE = 0x02000000          # the fake structs, _REGION apart
_REGION = 2 * _PAGE         # one mapped page each, then an unmapped guard page
_XBR = 0x04000000           # where armor_slots maps config.xbr
_HEAP = 0x05000000          # and the armor slot vector
_HEAP_SIZE = 0x4000
_KERNEL = 0x80000000        # one stub byte per kernel thunk slot
_RETURN = 0x0FFFF000        # the probe's return address
_REPO = Path(__file__).resolve().parents[2]
_KERNEL_H = _REPO / "devkit/sim/data/kernel.toml"             # the kernel's exports: names, data, pops
BLIND_SPOTS = _REPO / "devkit/sim/data/sim_blind_spots.toml"
_MD = Cs(CS_ARCH_X86, CS_MODE_32)
_REGS = {r: getattr(X, f"UC_X86_REG_{r.upper()}") for r in
         ("eax", "ebx", "ecx", "edx", "esi", "edi", "ebp", "esp", "eip")}

Stub = int | Callable[[], int]   # the EAX a stubbed callee returns


@dataclass(frozen=True)
class Player:
    """The fake state the probes run on: every value they read, by name.

    :data:`LAYOUT` says where each field lives and :data:`POINTERS` how
    the fake structs link up.  :data:`STANDING` is the named state, and
    :data:`SHIELD_2` the same player with an air shield; tests vary them
    with :func:`dataclasses.replace`.
    """
    velocity: tuple[float, float, float]
    object_ptr: int             # 0x150 into an object; 0 or 0x150 (none) skip the slope projection
    flags: int
    charged_jump_height: float  # 0 = an ordinary jump
    state: int                  # 0 ground, 2 air, 5 the zipline ride, ...
    ground_normal: tuple[float, float, float]
    jump_hold: tuple[float, float]  # hold-jump timer and its vz
    move_flags: int             # bit 2 rides along to the move code
    dt: float                   # frame time; the input builder copies 0x1980A0
    buttons: int                # 0x04 = jump edge, 0x02 = jump held, 0x40 = cheat turbo
    position: tuple[float, float, float]
    support_vz: float           # vz of the surface underfoot
    stick: float                # stick magnitude, 0-1
    direction: tuple[float, float, float]  # stick direction
    air_flags: int              # & 8 = the slow air-steering rate
    run_jump_speed: float       # CritterData+0x38 (walkSpeed): picks the jump animation
    walk_speed: float           # CritterData+0x40 (runSpeed)
    # The equipped armor slot (no_armor_1: Level 1, Flaps 0).  Air power
    # needs Level 1-3 and Flaps != 0 (0x83F90).
    armor_level: int            # level+0x08
    flaps: int                  # level+0x38; also the fuel divisor
    fuel: float                 # the armor's gauge: 1.0 full, a flap costs 1/Flaps
    controller_index: int
    y_button: float             # ControllerState analog Y
    y_latch: int                # ControllerState per-press latch
    # The attack-move record 0x7F1F0 copies to entity+0xDC when a button
    # picks a move (BLACK picks 'roll forward'), and its animation.
    attack: int                 # its config.xbr attacks entry; the roll shim scales only 20
    attack_anim: int            # its animation id, 0x52 + entry
    move_window: tuple[float, float, float]  # Move start/end1/end2, fractions of the clip
    attack_rate: float          # Rate: the clip's playback speed
    attack_yaw: float           # the entry tick's heading (0x4FF10 makes it a quaternion)
    facing: tuple[float, float, float, float]  # later ticks' heading quaternion
    walk_facing: tuple[float, float, float, float]  # the walk's rate-limited heading (0x84710 writes it)
    anim_slot: int              # the anim slot anim_change took (critter+0x200): 0x52 + an attack column
    anim_layer: int             # the active animation layer n; its block is anim+0x40+0x40·n
    layer_flags: int            # the active layer's flags
    clip_length: float          # the active clip's length in seconds
    # The attack presses (Step 2.140): the clock [entity+0xC]+0x10 (s,
    # f64), the times of A's, B's and BLACK's last fresh press (entity
    # +0xA0/+0xA8/+0xB0, f64; -1.0: consumed), the pad's analog A and B
    # with their latches, BLACK's, input+0x30 (set: the attack state's
    # stamps wait) and the two words 0x88E70 hands the transition search
    # (input+0x14, +0x38; probes stop at its call).  None pressed.
    clock: float = 10.0
    stamps: tuple[float, float, float] = (-1.0, -1.0, -1.0)
    attack_buttons: tuple[float, float] = (0.0, 0.0)
    attack_latches: tuple[int, int] = (0, 0)
    black_button: float = 0.0
    black_latch: int = 0
    input_locked: int = 0
    search_args: int = 0


# Player field -> (struct, offset or offsets, format); "globals" offsets
# are absolute VAs, and "layer" is the active animation layer's block,
# anim+0x40+0x40·anim_layer (the game reads its flags and clip there).
LAYOUT = {
    "velocity": ("entity", 0x24, "3f"),
    "object_ptr": ("entity", 0x30, "I"),
    "flags": ("entity", 0x60, "B"),
    "charged_jump_height": ("entity", 0x68, "f"),
    "state": ("entity", 0x94, "I"),
    "ground_normal": ("entity", 0xB8, "3f"),
    "jump_hold": ("entity", 0x148, "2f"),
    "move_flags": ("entity", 0x16C, "B"),
    "dt": ("input", 0x04, "f"),
    "buttons": ("input", 0x20, "B"),
    "position": ("input", (0x3C, 0x54), "3f"),  # the builder copies it to both
    "support_vz": ("input", 0x74, "f"),
    "stick": ("input", 0x124, "f"),
    "direction": ("input", 0x128, "3f"),
    "air_flags": ("input", 0x134, "B"),
    "run_jump_speed": ("critter", 0x38, "f"),
    "walk_speed": ("critter", 0x40, "f"),
    "armor_level": ("level", 0x08, "I"),
    "flaps": ("level", 0x38, "I"),
    "fuel": ("armor", 0x24, "f"),
    "controller_index": ("globals", CONTROLLER_INDEX, "I"),
    "y_button": ("controller", 0x24, "f"),
    "y_latch": ("controller", 0x4B, "B"),
    "attack": ("entity", 0x134, "I"),
    "attack_anim": ("entity", 0xE0, "I"),
    "move_window": ("entity", 0xF8, "3f"),
    "attack_rate": ("entity", 0x104, "f"),
    "attack_yaw": ("entity", 0x138, "f"),
    "facing": ("input", 0xD0, "4f"),
    "walk_facing": ("input", 0x7C, "4f"),
    "anim_slot": ("body", 0x200, "I"),
    "anim_layer": ("anim", 0x10, "I"),
    "layer_flags": ("layer", 0x08, "I"),
    "clip_length": ("clip", 0x10, "f"),
    "clock": ("clock", 0x10, "d"),
    "stamps": ("entity", 0xA0, "3d"),
    "attack_buttons": ("controller", 0x18, "2f"),
    "attack_latches": ("controller", 0x48, "2B"),
    "black_button": ("controller", 0x28, "f"),
    "black_latch": ("controller", 0x4C, "B"),
    "input_locked": ("input", 0x30, "B"),
    "search_args": ("input", (0x14, 0x38), "I"),
}
# (struct, offset) -> the fake struct it points to
POINTERS = {
    ("entity", 0x20): "body",       # armor chain: body -> gameplay -> armor -> level
    ("body", 0x154): "gameplay",
    ("gameplay", 0xCC): "armor",
    ("armor", 0x20): "level",
    ("input", 0x00): "body",        # the input builder's copy of entity+0x20
    ("input", 0x34): "critter",
    ("body", 0x17C): "anim",        # the animation controller
    ("body", 0x204): "clip",        # the active clip, as anim_change 0x42910 stores it
    ("layer", 0x04): "clip",        # the active layer's clip
    ("entity", 0x0C): "clock",      # the game clock (+0x10: now) the press stamps read
}
_STRUCTS = ("entity", "input", "body", "gameplay", "armor", "level", "critter",
            "anim", "clip", "clock")
_GUARDED = ((_FAKE, _FAKE + len(_STRUCTS) * _REGION),
            (CONTROLLERS, CONTROLLERS + 4 * 0x54),
            (CONTROLLER_INDEX, CONTROLLER_INDEX + 4))

# The player standing still at the start of level 1 in a new game, as the
# Step 2.11 xemu session (xemu-oracle-2026-10-09) dumped it at
# player_jump_init 0x89060: flat ground, facing yaw 130°, controller port 2,
# no attack picked, and no air armor (the equipped slot is no_armor_1,
# Level 1 and Flaps 0, as its second sitting read; an empty gauge).  object_ptr is that run's
# heap pointer, which no probe dereferences.  Not dumped: the press each
# probe models (the jump edge and Y, which the input builder 0x84F90
# would set, and the stick pushed fully toward the facing).
# CritterData and the animation fields are xemu session s6's settled
# new-game player in w1 (its settle capture): CritterData+0x38 5.0 and
# +0x40 7.0 (on all 940 rows of its captures); idle on layer 1, flags 0xB, an 8.0 s clip.  The
# active layer is history (0, 1 or 2): a probe that models an animation
# sets the one anim_change would have left.
STANDING = Player(
    velocity=(0.0, 0.0, 0.0), object_ptr=0x17E08B0, flags=0x50, charged_jump_height=0.0,
    state=0, ground_normal=(-0.0, -0.0, 1.0), jump_hold=(0.0, 0.0), move_flags=0,
    dt=1 / 30, buttons=0x04, position=(76.53239, 18.17524, 0.2734375), support_vz=0.0,
    stick=1.0, direction=(-0.76604444, -0.64278764, 0.0), air_flags=0,
    run_jump_speed=5.0, walk_speed=7.0, armor_level=1, flaps=0, fuel=0.0,
    controller_index=1, y_button=1.0, y_latch=0, attack=0xFFFFFFFF, attack_anim=0,
    move_window=(0.0, 0.0, 0.0), attack_rate=0.0, attack_yaw=0.0,
    facing=(0.0, 0.0, 0.9063078, 0.42261824), walk_facing=(0.0, 0.0, 0.9063078, 0.42261824), anim_slot=1,
    anim_layer=1, layer_flags=0xB, clip_length=8.0)
# Air shield 2 equipped (config.xbr: Level 2, Flaps 2) with a full gauge;
# the xemu fuel run poked the same Flaps and gauge into this player.
SHIELD_2 = replace(STANDING, armor_level=2, flaps=2, fuel=1.0)


class ProbeError(AssertionError):
    """The probe left the modelled path: a game assert, an unexpected
    read, a bad stub, an unbalanced stack, a fault or a runaway; or the
    build changes code L2 can't judge."""


@lru_cache(maxsize=None)
def kernel_arg_bytes() -> dict[str, int]:
    """Stack bytes each kernel import pops, from :data:`_KERNEL_H`'s
    ``pops`` (the XBE's ordinal table has no argument sizes)."""
    return dict(tomllib.loads(_KERNEL_H.read_text(encoding="utf-8"))["pops"])


class BlindSpot(NamedTuple):
    """Code L2 can't judge, whose vanilla bytes in [va, va + size) hash
    to ``sha256``."""
    va: int
    size: int
    sha256: str
    what: str
    why: str


@lru_cache(maxsize=None)
def blind_spots() -> tuple[dict[int, BlindSpot], dict[str, frozenset[int]]]:
    """:data:`BLIND_SPOTS`: the spots by VA, and for each xemu session a
    test may be signed off by, the VAs of the spots it saw changed."""
    facts = tomllib.loads(BLIND_SPOTS.read_text(encoding="utf-8"))
    return ({s["va"]: BlindSpot(**s) for s in facts["spot"]},
            {name: frozenset(s["spots"]) for name, s in facts["signoffs"].items()})


@lru_cache(maxsize=None)
def _known_functions() -> list[int]:
    return sorted({s.va for s in all_entries()} | set(RET_N_OVERRIDES))


@lru_cache(maxsize=None)
def _first_ret(code: bytes, va: int) -> int | None:
    """Bytes the first ``ret`` of ``code`` (loaded at ``va``) pops, or
    ``None`` without one. Cached: probes stub the same callees every call."""
    for _addr, _size, mnemonic, op_str in _MD.disasm_lite(code, va):
        if mnemonic == "ret":
            return int(op_str, 16) if op_str else 0
    return None


class Sim:
    """One loaded XBE; :meth:`call` runs a probe on it.

    A build that changes a blind spot doesn't load unless :attr:`signoff`
    names a session :data:`BLIND_SPOTS` lists with that spot; the test
    session sets it from the running test's ``xemu_signoff`` sign-off
    (``tests/test_simulator.py``'s fixture).
    """

    signoff: str | None = None

    def __init__(self, xbe: bytes):
        require_usa(xbe)   # ValueError naming a Europe XBE (D146)
        self.uc = uc = Uc(UC_ARCH_X86, UC_MODE_32)
        base, sections = parse_xbe_sections(xbe)
        header_size, image_size = struct.unpack_from("<II", xbe, 0x108)
        end = max([base + image_size] + [s["vaddr"] + s["vsize"] for s in sections])
        uc.mem_map(base, -(-(end - base) // _PAGE) * _PAGE)
        uc.mem_write(base, xbe[:header_size])
        for s in sections:                # the rest of vsize stays zero (BSS)
            raw = s["raw_addr"]
            uc.mem_write(s["vaddr"], xbe[raw:raw + min(s["raw_size"], s["vsize"])])
        self._refuse_blind_spots()
        uc.mem_map(_STACK_TOP - 0x100000, 0x100000)
        for i in range(len(_STRUCTS)):    # a read past a struct's page faults
            uc.mem_map(_FAKE + i * _REGION, _PAGE)
        uc.mem_map(_RETURN, _PAGE)
        uc.mem_map(_KERNEL, _PAGE)
        self.thunks = parse_kernel_thunks(xbe)
        for i, t in enumerate(self.thunks):
            uc.mem_write(t.thunk_va, struct.pack("<I", _KERNEL + i))
        uc.hook_add(UC_HOOK_CODE, self._kernel_call, begin=_KERNEL, end=_KERNEL + _PAGE - 1)
        uc.hook_add(UC_HOOK_CODE, self._game_assert, begin=ASSERT_HANDLER, end=ASSERT_HANDLER)
        for lo, hi in _GUARDED:
            uc.hook_add(UC_HOOK_MEM_READ, self._guard_read, begin=lo, end=hi - 1)
            uc.hook_add(UC_HOOK_MEM_WRITE, self._guard_write, begin=lo, end=hi - 1)
        self.at: dict[str, int] = {}      # struct name -> address
        self._named: set[int] = set()     # bytes the fake state names
        self._written: set[int] = set()   # guarded bytes the probe wrote
        self.kernel: dict[str, Callable[[], int]] = {}   # import -> its EAX (reads :meth:`arg`)

    def _refuse_blind_spots(self) -> None:
        spots, signoffs = blind_spots()
        seen = signoffs.get(self.signoff, frozenset())
        unseen = [s for s in spots.values() if s.va not in seen and hashlib.sha256(
            self.uc.mem_read(s.va, s.size)).hexdigest() != s.sha256]
        if unseen:
            raise ProbeError(
                "the build changes code L2 can't judge ("
                + "; ".join(f"{s.va:#x} {s.what}" for s in unseen)
                + "): sign the test off with xemu_signoff(<session>) naming the "
                f"Step 2.11 xemu session that saw it changed in game and lists these "
                f"spots in {BLIND_SPOTS.name}"
                + (f" ({self.signoff!r} doesn't list them)" if self.signoff else ""))

    # -- memory -------------------------------------------------------
    def reg(self, name: str) -> int:
        return self.uc.reg_read(_REGS[name])

    def u32(self, va: int) -> int:
        return struct.unpack("<I", self.uc.mem_read(va, 4))[0]

    def arg(self, i: int) -> int:
        """Stack argument ``i`` (from 0) of the call just entered."""
        return self.u32(self.reg("esp") + 4 + 4 * i)

    def f32(self, va: int) -> float:
        return struct.unpack("<f", self.uc.mem_read(va, 4))[0]

    def cstr(self, va: int) -> str:
        """The C string at ``va``, or ``va`` in hex if it isn't readable
        (NULL or not a pointer)."""
        out = bytearray()
        try:
            while len(out) < 256 and (c := self.uc.mem_read(va + len(out), 1)[0]):
                out.append(c)
        except UcError:
            return f"{va:#x}"
        return out.decode("latin-1")

    def install(self, player: Player) -> None:
        """Write ``player`` into the fake structs and the controller
        globals; :attr:`at` holds each struct's address."""
        idx = player.controller_index
        self.at = {name: _FAKE + i * _REGION for i, name in enumerate(_STRUCTS)}
        self.at["controller"] = CONTROLLERS + 0x54 * (idx if idx < 4 else 0)
        self.at["layer"] = self.at["anim"] + 0x40 + 0x40 * player.anim_layer
        for (where, off), target in POINTERS.items():
            self._name(self.at[where] + off, "I", self.at[target])
        self.set(**asdict(player))

    def set(self, **fields) -> None:
        """Overwrite named :class:`Player` fields, e.g. between probes."""
        for name, value in fields.items():
            where, offs, fmt = LAYOUT[name]
            for off in offs if isinstance(offs, tuple) else (offs,):
                self._name((0 if where == "globals" else self.at[where]) + off, fmt, value)

    def _name(self, va: int, fmt: str, value) -> None:
        data = struct.pack("<" + fmt, *(value if isinstance(value, tuple) else (value,)))
        self.uc.mem_write(va, data)
        self._named.update(range(va, va + len(data)))

    # -- hooks --------------------------------------------------------
    def _return(self, eax: int, pop: int) -> None:
        esp = self.reg("esp")
        self.uc.reg_write(X.UC_X86_REG_EAX, eax & 0xFFFFFFFF)
        self.uc.reg_write(X.UC_X86_REG_EIP, self.u32(esp))
        self.uc.reg_write(X.UC_X86_REG_ESP, esp + 4 + pop)

    def _kernel_call(self, uc, addr, size, _):
        name = self.thunks[addr - _KERNEL].name
        if name not in kernel_arg_bytes():
            raise ProbeError(f"kernel import {name} has no pops in kernel.toml")
        self._return(self.kernel[name]() if name in self.kernel else 0, kernel_arg_bytes()[name])

    def _game_assert(self, uc, addr, size, _):
        esp, msg = self.reg("esp"), self.reg("eax")
        raise ProbeError(
            f"game assert at {self.cstr(self.u32(esp + 4))}:{self.u32(esp + 8)}: "
            f"{self.cstr(self.reg('edi'))}{' ' + self.cstr(msg) if msg else ''} "
            f"(returns to {self.u32(esp):#x})")

    def _guard_read(self, uc, access, addr, size, value, _):
        if not set(range(addr, addr + size)) <= self._named | self._written:
            where = next((f"{n}+{addr - a:#x}" for n, a in self.at.items()
                          if a <= addr < a + _REGION), f"{addr:#x}")
            raise ProbeError(f"unexpected read of {where} ({size} B) at "
                             f"{self.reg('eip'):#x}: the fake state doesn't name it")

    def _guard_write(self, uc, access, addr, size, value, _):
        self._written.update(range(addr, addr + size))

    # -- probes -------------------------------------------------------
    def ret_n(self, va: int) -> int:
        """Bytes the function at ``va`` pops: its override, else the
        ``ret N`` of its first ``ret`` before the next known function."""
        if va in RET_N_OVERRIDES:
            if RET_N_OVERRIDES[va] is None:
                raise ProbeError(f"{va:#x} never returns, so it can't be stubbed")
            return RET_N_OVERRIDES[va]
        starts = _known_functions()
        i = bisect_right(starts, va)
        end = min(starts[i] if i < len(starts) else va + 0x4000, va + 0x4000)
        pop = _first_ret(bytes(self.uc.mem_read(va, end - va)), va)
        if pop is not None:
            return pop
        raise ProbeError(f"no ret between {va:#x} and the next known function "
                         f"{end:#x}: add {va:#x} to RET_N_OVERRIDES")

    def _stub(self, va: int, eax: Stub) -> int:
        if va not in blind_spots()[0]:
            raise ProbeError(f"stub {va:#x} isn't listed in {BLIND_SPOTS.name}: L2 "
                             f"can't judge a patch inside a stub, so list it there")
        pop = self.ret_n(va)

        def hook(uc, addr, size, _):
            ret = self.u32(self.reg("esp"))
            if pop and bytes(uc.mem_read(ret, 2)) in (b"\x83\xC4", b"\x81\xC4"):  # add esp
                raise ProbeError(f"stub {va:#x} pops {pop} bytes but its caller at "
                                 f"{ret:#x} cleans the stack itself")
            self._return(eax() if callable(eax) else eax, pop)
        return self.uc.hook_add(UC_HOOK_CODE, hook, begin=va, end=va)

    def call(self, va: int, *, regs: dict[str, int] | None = None,
             args: tuple[int, ...] = (), stubs: dict[int, Stub] | None = None,
             until: int | tuple[int, ...] | None = None, budget: int = 200_000,
             stack: int = _STACK_TOP) -> int:
        """Call the game function at ``va`` and return EAX, or stop when
        it reaches ``until``, or the first it reaches of several (then the
        stack isn't checked; EIP says which).  ``stubs`` maps a callee VA
        to the EAX it returns at once; ``stack`` is the top of the stack it
        runs on (another, below the default, leaves a stopped call's frames
        alone)."""
        esp = stack - 0x100
        for arg in reversed(args):
            esp -= 4
            self.uc.mem_write(esp, struct.pack("<I", arg))
        self.uc.mem_write(esp - 4, struct.pack("<I", _RETURN))
        self.uc.reg_write(X.UC_X86_REG_ESP, esp - 4)
        self.uc.reg_write(X.UC_X86_REG_EBP, 0)
        self.uc.reg_write(X.UC_X86_REG_FPCW, FPU_CW)
        for name, value in (regs or {}).items():
            self.uc.reg_write(_REGS[name], value)
        hooks = [self._stub(callee, eax) for callee, eax in (stubs or {}).items()]
        stops = (_RETURN,) if until is None else (until,) if isinstance(until, int) else until
        hooks += [self.uc.hook_add(UC_HOOK_CODE, lambda uc, *_: uc.emu_stop(), begin=s, end=s)
                  for s in stops[1:]]   # stops before the instruction, as emu_start's until does
        try:
            self.uc.emu_start(va, stops[0], count=budget)
        except UcError as e:
            raise ProbeError(f"{e} at {self.reg('eip'):#x}") from None
        finally:
            for h in hooks:
                self.uc.hook_del(h)
        if self.reg("eip") not in stops:
            raise ProbeError(f"{va:#x} did not reach {' or '.join(f'{s:#x}' for s in stops)} within "
                             f"{budget} instructions (stopped at {self.reg('eip'):#x})")
        if until is None and self.reg("esp") != (balanced := esp + self.ret_n(va)):
            raise ProbeError(f"stack unbalanced after {va:#x}: ESP "
                             f"{self.reg('esp'):#x}, expected {balanced:#x}")
        return self.reg("eax")


# -- player movement ------------------------------------------------------
JUMP_INIT = 0x89060         # ESI = entity, EAX = input; AL = started; plain ret
WING_FLAP = 0x89300         # ESI = entity, [esp+4] = input; AL = flapped; ret 4
AIRBORNE_TICK = 0x89480     # EDI = entity, [esp+4] = input; ret 4
WALK_STATE = 0x85F50        # EAX = entity, [esp+4] = input; ret 4
FALL_MOVE = 0x857FE         # gravity_integrate_raw's call of the move code 0x47380
WALK_MOVE = 0x860C8         # player_walk_state's call of gravity_integrate_raw
ARMOR_RESET = 0x837A0       # armor_reset_out_of_fuel(armor_mgr); flap() stubs and reports it
ATTACK_ENTRY = 0x88990      # EDI = entity, [esp+4] = input, [esp+8] = new state; ret 8
ATTACK_TICK = 0x8C7D0       # EDI = input, [esp+4] = entity; ret 4 (runs 0x8C630)
ATTACK_STATE = 0x100        # entity+0x94 while a ground attack move plays
ROOT_SAMPLER = 0xCACD0      # ESI = out, [esp+0xC]/[esp+0x10] = clip times; returns out
MOVE = 0x47380              # collide/move; [esp+4] = the request (desired velocity at +0x28)
DT_VA = 0x1980A0            # f32 frame time, 1/30 (fps_unlock: 1/60)
_ANIM_STUBS = {
    0x42910: 0,             # anim_change
    0x42E40: 0,             # anim_apply_translation (needs animation data)
    0x8BE00: 0,             # fall_death_dispatch
}
JUMP_STUBS = _ANIM_STUBS | {
    0xA5CA0: 0xFFFFFFFF,    # sound lookup: "none", so no sound plays
}
FLAP_STUBS = _ANIM_STUBS | {
    0x8D4E0: 0,             # play the flap sound
}


class Jump(NamedTuple):
    started: bool       # AL
    vz: float           # entity+0x2C: the launch speed the next tick integrates
    state: int          # entity+0x94: 2 = airborne
    air_control: float  # entity+0x140, as airborne_reinit 0x83F90 left it


class Flap(NamedTuple):
    flapped: bool       # AL
    vz: float           # entity+0x2C after the flap
    fuel: float         # the gauge after the flap
    armor_reset: bool   # the flap called armor_reset_out_of_fuel 0x837A0


class Roll(NamedTuple):
    state: int                          # entity+0x94 after the entry: 0x100
    ticks: int                          # ticks the move code got a request
    displacement: tuple[float, float]   # Σ desired v_xy·dt over those ticks
    vz: tuple[float, ...]               # each tick's desired vz
    desired: tuple[tuple[float, float, float], ...]  # each tick's desired velocity


def root_track(t: float, length: float) -> tuple[float, float, float]:
    """The fake root track the sampler stub reads: where the feet bone
    is ``t`` seconds into a ``length``-second clip (forward along +y
    with a hop).  The real roll_forward curve needs the animation
    assets; any track the game turns into velocity linearly will do."""
    t = min(max(t, 0.0), length)
    return 0.0, 3.0 * t - 0.75 * t * t, 0.5 * t * (length - t)


class PlayerSim(Sim):
    """A build with ``player`` installed.  The probes run in order on
    the same memory, like consecutive ticks; :meth:`set` changes the
    state between them (landing, moving)."""

    def __init__(self, xbe: bytes, player: Player = STANDING):
        super().__init__(xbe)
        self.install(player)

    def jump(self) -> Jump:
        """player_jump_init 0x89060 (it runs airborne_reinit 0x83F90)."""
        e = self.at["entity"]
        al = self.call(JUMP_INIT, regs={"esi": e, "eax": self.at["input"]},
                       stubs=JUMP_STUBS) & 0xFF
        return Jump(al == 1, self.f32(e + 0x2C), self.u32(e + 0x94), self.f32(e + 0x140))

    def flap(self) -> Flap:
        """wing_flap 0x89300; consume_fuel 0x842D0, airborne_reinit and
        mark_armor_feature_used 0x846D0 run for real.  The out-of-fuel
        reset 0x837A0 is a stub: in game it swaps in the level-1 Armor
        slot and empties the gauge."""
        e, reset = self.at["entity"], []
        al = self.call(WING_FLAP, regs={"esi": e}, args=(self.at["input"],),
                       stubs=FLAP_STUBS | {ARMOR_RESET: lambda: reset.append(1) or 0}) & 0xFF
        return Flap(al == 1, self.f32(e + 0x2C), self.f32(self.at["armor"] + 0x24), bool(reset))

    def fall(self) -> float:
        """The next tick: player_airborne_tick 0x89480 up to the point
        where gravity_integrate_raw hands the move code its request;
        return the request's vz (this tick's vz minus g·dt)."""
        self.call(AIRBORNE_TICK, regs={"edi": self.at["entity"]},
                  args=(self.at["input"],), until=FALL_MOVE)
        return self.f32(self.reg("eax") + 0x24)

    def walk(self) -> tuple[float, float, float]:
        """player_walk_state 0x85F50 up to its gravity_integrate_raw call;
        return the velocity it hands over (EDX)."""
        self.call(WALK_STATE, regs={"eax": self.at["entity"]},
                  args=(self.at["input"],), until=WALK_MOVE)
        return struct.unpack("<3f", self.uc.mem_read(self.reg("edx"), 12))

    def _attack_stubs(self, desired: list) -> dict[int, Stub]:
        """The attack probes' stubs: the root sampler (:func:`root_track`
        over the active clip), the move code (it appends the request's
        desired velocity to ``desired``), anim_change,
        anim_apply_translation and 0x8BF90."""
        length = self.f32(self.at["clip"] + 0x10)

        def sample() -> int:
            esp, out = self.reg("esp"), self.reg("esi")
            t0, t1 = (root_track(self.f32(esp + o), length) for o in (0xC, 0x10))
            self.uc.mem_write(out, struct.pack("<3f", *(b - a for a, b in zip(t0, t1))))
            return out

        def move() -> int:
            request = self.u32(self.reg("esp") + 4)
            desired.append(struct.unpack("<3f", self.uc.mem_read(request + 0x28, 12)))
            return 0
        return _ANIM_STUBS | {ROOT_SAMPLER: sample, MOVE: move, 0x8BF90: 0}

    def enter(self, state: int = ATTACK_STATE) -> tuple[float, float, float]:
        """The attack entry 0x88990 alone, into ``state`` (0x102: an air
        attack's, as player_air_attack_start 0x88E70 enters it): the
        desired velocity its one 0x8C630 tick hands the move code."""
        desired: list = []
        self.call(ATTACK_ENTRY, regs={"edi": self.at["entity"]}, args=(self.at["input"], state),
                  stubs=self._attack_stubs(desired))
        return desired[0]

    def roll(self) -> Roll:
        """Start the attack move the record names, as a button press
        does (the entry 0x88990, state 0x100, first tick included), then
        run its tick 0x8C7D0 until the clip reaches Move end2.  Each tick
        0x8C630 turns the root track's motion into a desired velocity,
        rotates it by the heading (0xA1420) and hands it to
        gravity_integrate_raw 0x85700, which hands it to the move code.
        Modelled: the animation system's clock (layer time += Rate·dt
        between ticks; the game ends the move when that flag fires);
        stubbed: the root sampler (:func:`root_track`), the move code
        (it records the request's desired velocity), anim_change,
        anim_apply_translation and 0x8BF90."""
        e, i, layer = self.at["entity"], self.at["input"], self.at["layer"]
        desired: list = []
        stubs = self._attack_stubs(desired)
        self.call(ATTACK_ENTRY, regs={"edi": e}, args=(i, ATTACK_STATE), stubs=stubs)
        state, dt = self.u32(e + 0x94), self.f32(DT_VA)
        while (t := self.f32(layer + 0x18) + self.f32(layer + 0x20) * dt) < self.f32(layer + 0x24):
            self.uc.mem_write(layer + 0x18, struct.pack("<f", t))
            self.call(ATTACK_TICK, regs={"edi": i}, args=(e,), stubs=stubs)
        return Roll(state, len(desired),
                    (dt * math.fsum(v[0] for v in desired), dt * math.fsum(v[1] for v in desired)),
                    tuple(v[2] for v in desired), tuple(desired))


def build_physics(vanilla: bytes, **params) -> bytes:
    """``vanilla`` built with the real ``player_physics`` pack at ``params``.
    No XBR files, so ``walk_speed_scale`` (a config.xbr cell, D53) must
    stay 1.0: any other value raises ``ValueError``."""
    xbe = bytearray(vanilla)
    apply_pack(get_pack("player_physics"), xbe, params)
    return bytes(xbe)


# -- load_armor_properties_config 0x3C700 ---------------------------------
ARMOR_LOADER = 0x3C700
ARMOR_LOADER_SLOTS_DONE = 0x3CC92   # the end of its slot loop
ARMOR_SLOTS = 0x38C4D4              # std::vector<slot> begin, end; 0x40 B a slot
# The config.xbr offset of the table the asset stub 0xA67A0 hands over:
# armor_properties' keyed table (sections.py: TOC entry 0x2000, grid
# +0x1000), the one in-game edits act on (Modkit's finding "XBR armor
# table aliasing").  Pinned here rather than looked up, so a pack that
# writes the 0x5000 grid (attacks_anims, labelled armor_properties_unused
# until AZ-113; historical case 10) can't pass; that it is the table the
# game loads is still taken on trust.
ARMOR_TABLE = 0x3000


class ArmorSlot(NamedTuple):
    level: int      # slot+0x08: Level, which wing_flap's reinit reads (Player.armor_level)
    flaps: int      # slot+0x38: Flaps, truncated toward zero by 0xF5A40 (u32 here)


def armor_slots(xbe: bytes, config_xbr: bytes) -> dict[str, ArmorSlot]:
    """Run the build's armor loader 0x3C700 on ``config_xbr`` to the end
    of its slot loop; return each armor row's slot by row name.  The
    game's keyed-table readers (0xD1420/0xD1520/0xD1630) and float-to-int
    0xF5A40 run for real."""
    sim = Sim(xbe)
    sim.uc.mem_map(_XBR, -(-len(config_xbr) // _PAGE) * _PAGE)
    sim.uc.mem_write(_XBR, config_xbr)
    sim.uc.mem_map(_HEAP, _HEAP_SIZE)

    def grow() -> int:      # vector::insert(end, EDX slots) on the empty vector
        n = sim.reg("edx")
        if n * 0x40 > _HEAP_SIZE:
            raise ProbeError(f"the armor table has {n} rows; raise _HEAP_SIZE")
        sim.uc.mem_write(ARMOR_SLOTS, struct.pack("<II", _HEAP, _HEAP + n * 0x40))
        return 0

    sim.call(ARMOR_LOADER, until=ARMOR_LOADER_SLOTS_DONE, budget=5_000_000, stubs={
        0xA5CA0: 0,                 # asset index lookup: found
        0xA6110: 0,                 # asset prefetch
        0xA67A0: _XBR + ARMOR_TABLE,  # load the 'tabl' asset
        0x3D3C0: grow,
        0x50D80: 0,                 # name lookup for slot+0x3C
    })
    begin, end = sim.u32(ARMOR_SLOTS), sim.u32(ARMOR_SLOTS + 4)
    return {sim.cstr(sim.u32(a)): ArmorSlot(sim.u32(a + 0x08), sim.u32(a + 0x38))
            for a in range(begin, end, 0x40)}


# -- the boot state machine 0x5F620 ----------------------------------------
BOOT_TICK = 0x5F620     # [esp+4] = dt, which only poll_movie reads; ret 4
BOOT_STATE = 0x1BF61C   # its state (BSS): 1 starts the logo, 2 polls it, 3 starts prophecy, 4 polls it
PLAY_MOVIE = 0x18980    # play_movie_fn(name, flag), stdcall: AL = started
POLL_MOVIE = 0x18D30    # poll_movie(dt), stdcall: 0 = still playing


class Boot(NamedTuple):
    movies: tuple[str, ...]     # the movies play_movie_fn was asked to start
    state: int                  # BOOT_STATE after the tick


def boot_tick(xbe: bytes, state: int) -> Boot:
    """One tick of the boot state machine 0x5F620 from ``state``: each
    movie it asks play_movie_fn 0x18980 for starts, and poll_movie
    0x18D30 says it's still playing, so the tick ends polling the first
    movie it starts."""
    sim, movies = Sim(xbe), []
    sim.uc.mem_write(BOOT_STATE, struct.pack("<I", state))

    def play() -> int:
        movies.append(sim.cstr(sim.u32(sim.reg("esp") + 4)))
        return 1

    sim.call(BOOT_TICK, args=(0,), stubs={PLAY_MOVIE: play, POLL_MOVIE: 0})
    return Boot(tuple(movies), sim.u32(BOOT_STATE))


# -- a transform's world matrix: the local builder 0x68BE0 and 0x681E0 -----
XFORM_LOCAL = 0x68BE0   # ECX = transform, [esp+4] = its local matrix (+0x70); ret 4
XFORM_WORLD = 0x681E0   # EAX = transform: +0x30 = local x the parent's +0x30 by the inherit mode +0xF0
_XFORMS = 0x06000000    # where transform_world lays its transforms out, 0x400 B each


def transform_world(xbe: bytes, chain) -> tuple:
    """The world matrix the game's own code gives the last of ``chain``
    (root first; each a :meth:`azurkit.core.xbr.graph.Graph.xform_fields`
    dict), as a column-vector 4x4: each transform laid out as the loader
    0x67F80 fills it (attributes at +0x08, parent +0x18, -sp +0xB0,
    spt + sp - rp +0xBC, rp +0xC8, rpt + rp +0xD4, the inherit mode +0xF0
    and rotation order +0xF4), then its local builder and 0x681E0 run."""
    sim = Sim(xbe)
    sim.uc.mem_map(_XFORMS, -(-len(chain) * 0x400 // _PAGE) * _PAGE)
    parent = 0
    for k, x in enumerate(chain):
        o = _XFORMS + 0x400 * k
        sp, spt, rp, rpt = x["sp"], x["spt"], x["rp"], x["rpt"]
        sim.uc.mem_write(o + 0x200, struct.pack("<10f", 0.0, *x["t"], *x["r"], *x["s"]))
        sim.uc.mem_write(o + 0x08, struct.pack("<I", o + 0x200))
        sim.uc.mem_write(o + 0x18, struct.pack("<I", parent))
        sim.uc.mem_write(o + 0xB0, struct.pack("<12f", *(-v for v in sp), *(spt[i] + sp[i] - rp[i] for i in range(3)),
                                               *rp, *(rpt[i] + rp[i] for i in range(3))))
        sim.uc.mem_write(o + 0xF0, struct.pack("<II", x["mode"], x["order"]))
        sim.call(XFORM_LOCAL, regs={"ecx": o}, args=(o + 0x70,))
        sim.call(XFORM_WORLD, regs={"eax": o})
        parent = o
    m = struct.unpack("<16f", sim.uc.mem_read(parent + 0x30, 64))   # D3D rows: the transpose
    return tuple(tuple(m[4 * c + r] for c in range(4)) for r in range(4))


# -- the load runs' allocator 0xA4890 and free 0xBAD10 (Steps 2.162e, 2.162h, 2.162l)
RUN_ALLOC = 0xA4890     # EDI = size, [esp+4] = mode (0 virtual, 1 contiguous), [esp+8] = level; ret 8
RUN_FREE = 0xBAD10      # ESI = the run, EAX = its size, [esp+4] = mode; ret 4
RUNS_USED = 0x1BF400    # the resident runs' bytes
RUNS_LIMIT = 0x1BF404   # the budget, 40 MiB from boot (0x596C6)
CSTATUS = 0xFD10020C    # NV_PFB_CSTATUS: the machine's RAM in bytes
PDE_UPPER = 0xC0300840  # PDE[0x210..0x21F] (VA 0x84000000-0x87FFFFFF) through the self-map
PDE_T3 = 0xC0300880     # PDE[0x220..0x23F] (VA 0x88000000-0x8FFFFFFF), qol_memory_upper256's T3
UPPER_STATE = 0x87FFF000   # qol_memory_upper64's state page (heap.h, layout 3)
UPPER_W2 = 0x87FFF7FC   # the probe's word in it (phys 0x07FFF7FC)
T3_VERDICT = 0x87FFF05C   # the probe's verdict: 0 not probed, 1 RAM, 2 fold, 3 hole, 4 the kernel's
T3_BITMAP = 0x8FFFF000  # T3's last page: its bitmap, and W2's alias 128 MiB up (phys 0x0FFFF7FC)
TOPS = ("ram", "fold", "hole")   # what answers at phys 0x0FFFF7FC
LOW_RUNS = 0x00400000   # where NtAllocateVirtualMemory's stand-in reserves the first run
LOW_CONTIG = 0x00800000  # where MmAllocateContiguousMemoryEx's stand-in places the first contiguous run
REGISTER = 0x1249A0     # D3DResource_Register(resource, base): Data := (Data + base) & 0x3FFFFFF; ret 8
DMA_LIMIT = 0x12D552    # CMiniport_CreateCtxDmaObject's store of its limit [ebp+0x14] at [ecx+0x700004]
DMA_LIMIT_END = 0x12D55B
_SCRATCH = _STACK_TOP - 0x80000   # Register's resource, the limit's frame and RAMIN word
RUN_BUDGET = 4_000_000   # instructions: a fit scans T2's 0x3FFF pages and T3's 0x7FFF, twice with the budget hook


class Runs(Sim):
    """The run allocator and the run free on a machine with ``ram_mib``
    MiB whose kernel left ``pde`` in PDE[0x210] (0 on ours) and the rest
    of the 48 at 0, the budget at boot's 40 MiB. NV_PFB_CSTATUS reads the
    RAM up to 128 MiB (256 MiB reads 128, as in xemu). ``top`` is what
    answers at physical 0x0FFFF7FC, the word qol_memory_upper256's probe
    stores to through VA 0x8FFFF7FC: ``"ram"`` (a page of its own: the
    default at 256 MiB), ``"fold"`` (W2's page, a machine that drops
    address bit 27) or ``"hole"`` (writes dropped, reads 0: xemu below
    256 MiB, the default there). NtAllocateVirtualMemory's stand-in
    reserves each virtual run 64 KiB-aligned from :data:`LOW_RUNS`,
    MmAllocateContiguousMemoryEx's places each contiguous one page-aligned
    from ``contig`` (a kernel that maps the upper 64 MiB itself may place
    them there); no run's memory is mapped (the allocator and the free
    never touch it)."""

    def __init__(self, xbe: bytes, ram_mib: int, pde: int = 0, contig: int = LOW_CONTIG,
                 top: str | None = None):
        super().__init__(xbe)
        top = top or ("ram" if ram_mib >= 256 else "hole")
        if top not in TOPS:
            raise ValueError(f"top {top!r}: one of {', '.join(TOPS)}")
        for va in (CSTATUS, PDE_UPPER):
            self.uc.mem_map(va & ~(_PAGE - 1), _PAGE)
        self._pages = ctypes.create_string_buffer(_PAGE)   # the state page, which "fold" maps twice
        self.uc.mem_map_ptr(UPPER_STATE, _PAGE, UC_PROT_ALL, ctypes.addressof(self._pages))
        if top == "fold":
            self.uc.mem_map_ptr(T3_BITMAP, _PAGE, UC_PROT_ALL, ctypes.addressof(self._pages))
        else:
            self.uc.mem_map(T3_BITMAP, _PAGE)
        if top == "hole":
            self.uc.hook_add(UC_HOOK_MEM_READ, lambda uc, *_: uc.mem_write(T3_BITMAP, bytes(_PAGE)),
                             begin=T3_BITMAP, end=T3_BITMAP + _PAGE - 1)
        self.uc.mem_write(CSTATUS, struct.pack("<I", min(ram_mib, 128) << 20))
        self.uc.mem_write(PDE_UPPER, struct.pack("<I", pde))
        self.uc.mem_write(RUNS_LIMIT, struct.pack("<I", 40 << 20))
        self._next, self._contig = LOW_RUNS, contig
        self.kernel["NtAllocateVirtualMemory"] = self._reserve
        self.kernel["MmAllocateContiguousMemoryEx"] = self._contiguous

    def _reserve(self) -> int:
        base, size = self.arg(0), self.u32(self.arg(2))
        if not self.u32(base):      # the reserve; the commit names its base
            self.uc.mem_write(base, struct.pack("<I", self._next))
            self._next += -(-size // 0x10000) * 0x10000
        return 0

    def _contiguous(self) -> int:
        run, self._contig = self._contig, self._contig + -(-self.arg(0) // _PAGE) * _PAGE
        return run

    def alloc(self, size: int, mode: int = 0) -> int:
        """A run of ``size`` bytes, mode 0 (virtual) or 1 (contiguous, the
        GPU's): its address, or 0."""
        return self.call(RUN_ALLOC, regs={"edi": size}, args=(mode, 0), budget=RUN_BUDGET)

    def free(self, run: int, size: int, mode: int = 0) -> None:
        self.call(RUN_FREE, regs={"esi": run, "eax": size}, args=(mode,), budget=RUN_BUDGET)

    def register(self, data: int, base: int) -> int:
        """A texture's Data after D3DResource_Register with ``base``."""
        self.uc.mem_write(_SCRATCH, struct.pack("<II", 0x00040001, data))   # a texture, one reference
        self.call(REGISTER, args=(_SCRATCH, base))
        return self.u32(_SCRATCH + 4)

    def dma_limit(self, limit: int) -> int:
        """The limit a DMA object created with ``limit`` gets in RAMIN."""
        self.uc.mem_write(_SCRATCH + 0x14, struct.pack("<I", limit))
        self.call(DMA_LIMIT, regs={"ebp": _SCRATCH, "ecx": _SCRATCH + 0x100 - 0x700004}, until=DMA_LIMIT_END)
        return self.u32(_SCRATCH + 0x100)

    @property
    def used(self) -> int:
        """[0x1BF400], the bytes the budget counts."""
        return self.u32(RUNS_USED)

    def pdes(self, tier: int = 2) -> list[int]:
        """T2's 16 PDEs (PDE[0x210..0x21F]), or T3's 32 (``tier`` 3)."""
        n = 16 if tier == 2 else 32
        return list(struct.unpack(f"<{n}I", self.uc.mem_read(PDE_UPPER if tier == 2 else PDE_T3, 4 * n)))


# -- the stream pump's start 0xB5CC0 (AZ-687, Step 2.162e) -----------------
PUMP_START = 0xB5CC0    # starts the stream pump thread (0xB5940); plain ret
PUMP_EVENT = 0x1BF548   # its wake event, made by the first start
PUMP_HANDLE = 0x1BEFEC  # the thread's handle
PUMP_RUNNING = 0x1BF544  # u8: the pump runs (1 after a start)
PUMP_THREAD = 0x0000ABCD   # the handle the kernel's stand-in gives
NO_MEMORY = 0xC0000017  # STATUS_NO_MEMORY


class Pump(NamedTuple):
    tries: int          # PsCreateSystemThreadEx calls
    sleeps: int         # KeDelayExecutionThread calls
    handle: int         # [0x1BEFEC]
    running: int        # [0x1BF544]


def _thread_block(sim: Sim) -> None:
    """A thread block at FS's base (0) for XAPI's SetLastError: Irql 0
    (+0x24) and a TLS array (+0x04) whose slot [0x1ADDC8] (0) points at
    +0x200."""
    sim.uc.mem_map(0, _PAGE)
    sim.uc.mem_write(0x04, struct.pack("<I", 0x100))
    sim.uc.mem_write(0x100, struct.pack("<I", 0x200))


def pump_start(xbe: bytes, refusals: int) -> Pump:
    """0xB5CC0 once, its event already made, with the kernel refusing the
    thread (STATUS_NO_MEMORY) ``refusals`` times and then making it."""
    sim, n = Sim(xbe), {"tries": 0, "sleeps": 0}
    _thread_block(sim)
    sim.uc.mem_write(PUMP_EVENT, struct.pack("<I", 1))

    def create() -> int:
        n["tries"] += 1
        if n["tries"] <= refusals:
            return NO_MEMORY
        sim.uc.mem_write(sim.arg(0), struct.pack("<I", PUMP_THREAD))
        return 0

    def sleep() -> int:
        n["sleeps"] += 1
        return 0

    sim.kernel |= {"PsCreateSystemThreadEx": create, "KeDelayExecutionThread": sleep}
    sim.call(PUMP_START)
    return Pump(n["tries"], n["sleeps"], sim.u32(PUMP_HANDLE), sim.uc.mem_read(PUMP_RUNNING, 1)[0])



# -- a stream's buffer 0xB5490 and the run lists (AZ-814, Step 2.172d) -------
STREAM_BUFFER = 0xB54B2   # 0xB5490 past its CreateFile: EBX = the stream, [esp+4] = size, [esp+8] = read-ahead
STREAM_GOT = 0xB555D      # the buffer taken ([stream+0x18]); CreateEventA next
STREAM_GAVE_UP = 0xB5555  # no buffer: 0xB5490 returns 0 (the copy thread's 0xB06B0 then dies, 0xA9100)
RUN_EVICT = 0xA6450       # evict(list, size): unlinks and frees runs, returns the bytes freed; ret 8
RUN_LISTS = (0x1AA7F0,) + tuple(0x37BD00 + 8 * k for k in range(30))   # the expired list, the wheel's 30 slots
PAGE_LOCK = 0x1BF538      # run_pages_alloc's spinlock
COPY_BUFFER = 0x100000    # the copy thread's buffer (0xB06C5: read-ahead 0)
MOVIE_READ_AHEAD = 0x200000   # the movie opener's (0xD0074), on main


class StreamBuffer(NamedTuple):
    buffer: int                 # [stream+0x18]: its pages, or 0
    used: int                   # [0x1BF400] after
    evicts: tuple[int, ...]     # the lists evict ran on, in order
    lock: int                   # [0x1BF538] after (0: released)


def stream_buffer(xbe: bytes, read_ahead: int, used: int, commit: bool = True) -> StreamBuffer:
    """0xB5490's 1 MiB buffer for a stream with ``read_ahead`` (0: the copy
    thread's), ``used`` of the 40 MiB budget taken and every run list
    empty (each head links to itself, so an evict frees nothing), on a
    64 MiB machine; ``commit`` False: the kernel refuses every commit
    (STATUS_NO_MEMORY). Runs to the buffer or the give-up; evict runs
    as the game's own code, watched, not stubbed."""
    runs, evicts = Runs(xbe, 64), []
    _thread_block(runs)
    runs.uc.mem_write(RUNS_USED, struct.pack("<I", used))
    for head in RUN_LISTS:
        runs.uc.mem_write(head, struct.pack("<II", head, head))
    if not commit:
        reserve = runs.kernel["NtAllocateVirtualMemory"]
        runs.kernel["NtAllocateVirtualMemory"] = lambda: NO_MEMORY if runs.u32(runs.arg(0)) else reserve()
    runs.uc.hook_add(UC_HOOK_CODE, lambda *_: evicts.append(runs.arg(0)), begin=RUN_EVICT, end=RUN_EVICT)
    stream = _SCRATCH + 0x200
    runs.call(STREAM_BUFFER, regs={"ebx": stream}, args=(COPY_BUFFER, read_ahead),
              until=(STREAM_GOT, STREAM_GAVE_UP))
    return StreamBuffer(runs.u32(stream + 0x18), runs.used, tuple(evicts), runs.u32(PAGE_LOCK))



# -- the copy thread's out-of-memory eviction and main (AZ-817, Step 2.172g) --
STREAM_OOM = 0xB5D23      # 0xB5D00 after the heap refused the stream object (EBX = EDI = 0): its handler loop
STREAM_OOM_FREED = 0xB5E71   # a handler freed something: the alloc is tried again
STREAM_OOM_NONE = 0xB5D4E    # none did: the open logs and is fatal
OOM_TABLE = 0x1BEF80      # the out-of-memory handlers; [0x1BEFA8] their count
OOM_HANDLER = 0xA66A0     # the one registered (0xA6B9A): 0xA64D0(size, 3)
MAIN_TICK = 0x59C90       # the main loop's CALL of the wheel advance 0xA62B0
MAIN_WAIT = 0xB14D0       # 0xB13B0's wait on the copy: its pushes, then the CALL at 0xB14E1
SIGNAL_AND_WAIT = 0xE0FB3  # XAPI SignalObjectAndWait (main asleep in it; stdcall, 4 arguments)
MAIN_WOKEN = 0xB14E6      # 0xB13B0 past that wait: main goes on (the copy mutex next)
SLEEP = 0xE1218           # XAPI Sleep (stdcall, 1 argument)
EVICTING = 0xA64D7        # run_evict_until (0xA64D0) begun, before its first list
COPY_THREAD, MAIN_THREAD = 0x8004C8B8, 0x8002F018   # their KTHREADs, at fs:[0x28]
_MAIN_STACK = _STACK_TOP - 0x40000   # main's frames, apart from the copy thread's
COPY_MAINS = ("none", "ticks", "parked", "woken", "silent")
HOLD = 3                  # main's turns while the copy thread evicts ("woken")


class CopyOom(NamedTuple):
    walks: tuple[tuple[str, int], ...]   # (thread, lists 0xA6450 walked on it), by thread
    sleeps: int                          # KeDelayExecutionThread calls on the copy thread
    main_held: int = 0                   # "woken": main's turns (of HOLD) spent asleep while the copy evicted


def copy_oom(xbe: bytes, main: str) -> CopyOom:
    """The copy thread's stream object refused by the heap (0xB5D00, after
    0xB5D19) with every run list empty, so an eviction walks all 31 and
    frees nothing. ``main``: ``"none"`` (main hasn't run a frame yet),
    ``"ticks"`` (main ran one, and runs its next while the copy thread
    first sleeps), ``"parked"`` (main ran one and sleeps in its wait on the
    copy, 0xB13B0's SignalObjectAndWait), ``"woken"`` (asleep so, and woken
    by the copy thread's pulse just before this open: main gets HOLD turns
    while the copy thread is inside its eviction, each ending at main's
    next sleep or at 0xB14E6, past its wait, and runs on to 0xB14E6 once
    the copy is done) or ``"silent"`` (main ran one and neither runs
    another nor sleeps on the copy). Main's frame is the main loop's tick
    at 0x59C90 (the wheel advance, the lists empty); the two threads are
    fs:[0x28]'s KTHREAD, switched by hand, and a sleep or wait main stops
    in returns at once when it runs on."""
    if main not in COPY_MAINS:
        raise ValueError(f"main {main!r}: one of {', '.join(COPY_MAINS)}")
    sim, walks, n = Sim(xbe), [], {"sleeps": 0}
    _thread_block(sim)
    for head in RUN_LISTS:
        sim.uc.mem_write(head, struct.pack("<II", head, head))
    sim.uc.mem_write(OOM_TABLE, struct.pack("<I", OOM_HANDLER))
    sim.uc.mem_write(OOM_TABLE + 0x28, struct.pack("<I", 1))
    thread = {COPY_THREAD: "copy", MAIN_THREAD: "main"}

    def on(kthread: int) -> None:
        sim.uc.mem_write(0x28, struct.pack("<I", kthread))

    def sleep() -> int:
        n["sleeps"] += sim.u32(0x28) == COPY_THREAD
        return 0

    sim.kernel["KeDelayExecutionThread"] = sleep
    sim.uc.hook_add(UC_HOOK_CODE, lambda *_: walks.append(thread[sim.u32(0x28)]), begin=RUN_EVICT, end=RUN_EVICT)

    def main_frame() -> None:
        on(MAIN_THREAD)
        sim.call(MAIN_TICK, until=MAIN_TICK + 5, stack=_MAIN_STACK)

    def run(stops: tuple[int, ...]) -> int:
        """The current thread on from EIP to the first of ``stops``."""
        hooks = [sim.uc.hook_add(UC_HOOK_CODE, lambda uc, *_: uc.emu_stop(), begin=s, end=s) for s in stops]
        try:
            sim.uc.emu_start(sim.reg("eip"), 0, count=2_000_000)
        except UcError as e:
            raise ProbeError(f"{e} at {sim.reg('eip'):#x}") from None
        finally:
            for h in hooks:
                sim.uc.hook_del(h)
        if sim.reg("eip") not in stops:
            raise ProbeError(f"stopped at {sim.reg('eip'):#x}, not {' or '.join(f'{s:#x}' for s in stops)}")
        return sim.reg("eip")

    if main != "none":
        main_frame()
    if main in ("parked", "woken"):
        sim.call(MAIN_WAIT, until=SIGNAL_AND_WAIT, stack=_MAIN_STACK)
        asleep = sim.uc.context_save()
    on(COPY_THREAD)
    ends = (STREAM_OOM_FREED, STREAM_OOM_NONE)
    first = {"ticks": (SLEEP,), "woken": (EVICTING,)}.get(main, ())
    sim.call(STREAM_OOM, regs={"ebx": 0, "edi": 0}, until=ends + first, budget=2_000_000)
    held, at = 0, MAIN_WOKEN
    if sim.reg("eip") in first:
        copy = sim.uc.context_save()
        if main == "ticks":
            main_frame()
        else:
            sim.uc.context_restore(asleep)
            on(MAIN_THREAD)
            sim._return(0, 16)                 # SignalObjectAndWait returns: the copy pulsed
            for _ in range(HOLD):
                if (at := run((MAIN_WOKEN, SLEEP))) == MAIN_WOKEN:
                    break
                held += 1
                sim._return(0, 4)              # Sleep returns
            woken = sim.uc.context_save()
        sim.uc.context_restore(copy)
        on(COPY_THREAD)
        run(ends)
        if at != MAIN_WOKEN:
            sim.uc.context_restore(woken)
            on(MAIN_THREAD)
            run((MAIN_WOKEN,))
    counts: dict[str, int] = {}
    for t in walks:
        counts[t] = counts.get(t, 0) + 1
    return CopyOom(tuple(sorted(counts.items())), n["sleeps"], held)

# -- STLport's 32-byte free list and the sound thread's map (AZ-695, Step 2.172)
NODE_STATE = 0x1AAC14   # _S_chunk_alloc's heap size, pool end and start, then the 16 lists' heads (8-128 B)
NODE_STATE_END = 0x1AAC60
LIST_32 = 0x1AAC2C      # the 32-byte list's head
LOAD_FREE = 0xC49ED     # the load thread's deallocate (EAX = block, ECX = (size - 1) >> 3): its load of the head
LOAD_FREE_STORE = 0xC49FD   # ... and its store of the new head
LOAD_FREE_END = 0xC49FF
MALLOC = 0xAB5B0        # cdecl malloc(size): the process heap
FREE = 0xAB580          # free(EAX)
MAP_CREATE_POP = 0xAF3B0    # the sound thread's map: create_node's node pop
MAP_INSERT_POP = 0xAF322    # _M_insert's
MAP_ERASE_PUSH = 0xAE76C    # erase's push of the node in EAX
MAP_JOINS = {MAP_CREATE_POP: 0xAF3CD, MAP_INSERT_POP: 0xAF33F, MAP_ERASE_PUSH: 0xAE779}   # where vanilla's spans end
_BLOCKS = 0x07000000
NODE_BLOCKS = tuple(_BLOCKS + 0x20 * k for k in range(4))   # H, H2 (on the list), X (the load thread's), N (a map node)


class NodeRace(NamedTuple):
    node: int | None            # the block create_node took off the list; None: it called the heap
    free: tuple[int, ...]       # the 32-byte list after the load thread's store
    heap: tuple[tuple[str, int], ...]   # the sound thread's heap calls: ("malloc", size), ("free", block)
    touched: tuple[int, ...]    # the sound thread's PCs that read or wrote NODE_STATE


def node_race(xbe: bytes) -> NodeRace:
    """The fork's interleaving (AZ-628's reply, 2026-10-23): with the 32-byte
    list H -> H2, the load thread frees X and is cut between its load of the
    head (0xC49ED) and its store (0xC49FD); the sound thread's create_node
    pop (0xAF3B0) runs; then the load thread's store. After it, _M_insert's
    pop (0xAF322) and erase's push of N (0xAE76C) run once each. Each of the
    sound thread's spans stops at its vanilla join or at the entry of malloc
    or free, so nothing is stubbed."""
    sim = Sim(xbe)
    h, h2, x, n = NODE_BLOCKS
    sim.uc.mem_map(_BLOCKS, _PAGE)
    sim.uc.mem_write(LIST_32, struct.pack("<I", h))
    sim.uc.mem_write(h, struct.pack("<I", h2))
    touched: list[int] = []
    sim.uc.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, lambda uc, *_: touched.append(sim.reg("eip")),
                    begin=NODE_STATE, end=NODE_STATE_END - 1)
    heap: list[tuple[str, int]] = []

    def sound_thread(va: int, **regs: int) -> int | None:
        """The span at ``va``: EAX at its join, or None at a heap call."""
        eax = sim.call(va, regs=regs, until=(MAP_JOINS[va], MALLOC, FREE))
        if sim.reg("eip") == MAP_JOINS[va]:
            return eax
        heap.append(("malloc", sim.arg(0)) if sim.reg("eip") == MALLOC else ("free", eax))
        return None

    sim.call(LOAD_FREE, regs={"eax": x, "ecx": 3}, until=LOAD_FREE_STORE)
    cut = {r: sim.reg(r) for r in ("eax", "ecx", "edx")}
    mark = len(touched)
    node = sound_thread(MAP_CREATE_POP)
    sound = touched[mark:]
    sim.call(LOAD_FREE_STORE, regs=cut, until=LOAD_FREE_END)
    free, link = [], sim.u32(LIST_32)
    while link and len(free) < len(NODE_BLOCKS):
        free.append(link)
        link = sim.u32(link)
    mark = len(touched)
    sound_thread(MAP_INSERT_POP)
    sound_thread(MAP_ERASE_PUSH, eax=n)
    return NodeRace(node, tuple(free), tuple(heap), tuple(sound + touched[mark:]))
