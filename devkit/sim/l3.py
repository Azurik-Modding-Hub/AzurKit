"""Simulator Level 3: the game's own simulation step from a guest RAM snapshot (Steps X.5-X.6, D168, D170).

A snapshot is every present user page (VA below 0x80000000) of a running game, read through the page tables'
self-map (PDEs at 0xC0300000, PTEs at 0xC0000000), the halted CPU's registers and metadata (the level, the
player's entity and position, the xemu build, the ISO).  ``xemu_oracle.py snapshot`` takes one at the
player's update entry 0x8C230 (or the scene tick's entry 0x55AB0) into the private :func:`store`.  :class:`L3`
maps it under Unicorn and runs the game's code, unchanged, one step at a time:

- the player's per-frame update 0x8C230 (input build, armor, animation, the state machine, the move code 0x47380
  and its collision), with the scheduler's clock set the way scheduler_run 0xAB980 sets it before each event (its
  now, f64 +0x10, = the event's time entity+0x18);
- with ``scene=True``, on a snapshot taken at the scene tick, the whole step scene_state_tick 0x55AB0 (the
  scheduler, so every critter, rig and trigger, and the node graphs), the per-frame audio update stubbed
  (:data:`STUBS`), then the frame's render (:data:`RENDER`, Step X.20: it moves the cameras and draws from the
  game's random numbers) with the GPU a stub.

The step's inputs from outside it are the pad and the camera, and L3 writes both where the game gets them.  Each
tick's :class:`Pad` (left stick, held buttons, camera yaw) goes into the active ControllerState at the player
update's entry, after the main loop's poll 0xA2880 has cleared the latch of each button that read 0 on the frame
before (the latches are otherwise the game's).  The camera, which the game moves outside the step, is the ground
direction the input builder reads at 0x85276 ([esp+0x14], [esp+0x18]; its yaw is atan2(-x, y)).  Each step
returns a :class:`Row`: the body centre, state, HP and zone after the update, and the writes and camera
direction it used, which ``xemu_oracle.py``'s replayer writes into xemu at the same instructions, so an input
string found here replays exactly there.

Kernel imports return 0 and pop their declared arguments, as in L2 (the two critical-section calls in guest code,
:data:`NATIVE`), except NtAllocateVirtualMemory, which maps a zeroed region (the asset page manager allocates as it
streams), RtlInitAnsiString, which fills its ANSI_STRING as the kernel does, and the stream module's file reads,
which L3 serves from the disc's files (``disc``) and hands back through the main loop's poll before the next step;
any other NtReadFile reads zeros.  An access at or above 0x80000000 (contiguous memory) maps a zero page; RDTSC
reads a virtual clock.  What a run reads that L3 doesn't model taints it (:attr:`L3.taint`, on each row and saved
state; a kernel call's game caller and file, :attr:`L3.taint_at`), so a search that found nothing counts as a
refutation only untainted; L3 refuses a snapshot whose code isn't the XBE's (:func:`check_code`).  A step that leaves
the snapshot's world raises :class:`L3Error`, its ``site`` naming it.  A level exit (Step X.52b): a levelSwitch's
fire is on its step's row (``Row.exit``, :attr:`L3.fires`), and a step that reaches the level's unload stops at its
entry (:class:`LevelExit`), before the level's state is written or the next level loads.  docs/SIMULATOR.md has the
API and the xemu validation.

Guest RAM holds console key material: snapshots live only in the private store (mode 700, files 0600), are
never committed (``.gitignore``; ``tests/_leak_guard.py`` refuses :data:`MAGIC`) and never printed: lengths and
sha256[:12] only.
"""

from __future__ import annotations

import functools
import hashlib
import json
import math
import mmap
import os
import re
import struct
import sys
import threading
import time
import tomllib
import weakref
from pathlib import Path
from typing import Callable, Iterable, NamedTuple

import numpy as np
from unicorn import (UC_ARCH_X86, UC_HOOK_CODE, UC_HOOK_MEM_UNMAPPED, UC_MODE_32, UC_PROT_ALL, Uc,
                     UcError)
from unicorn import x86_const as X

from azurkit.tools.randomizer.live import recipes
from azurkit.tools.randomizer.live.pages import (PAGE, PDE_BASE, PTE_BASE,  # noqa: F401 (scripts read them here)
                                                 ram_reader)
from devkit.sim import obs as _obs
from devkit.sim import overlay as _ov
from devkit.sim import require_usa
from devkit.sim.l2 import _KERNEL_H, ASSERT_HANDLER, FPU_CW, kernel_arg_bytes
from devkit.sim.ports import parse_kernel_thunks, parse_xbe_sections
# The snapshot's file, its store and the pad (Step 4.14a1 split them off this module for the xemu harness), and
# the addresses the harness halts at: L3 re-exports them, so its importers read them here as in Modkit.
from devkit.sim.snapshot import (ACTIVE_PAD, BUTTONS, CAMERA_DIR, CONTROLLER_STATE, FORMAT, HIGH,  # noqa: F401
                                 MAGIC, MAIN_DT, MAIN_RATE, PAD_SIZE, PLAYER_UPDATE, SCENE_RETS, SCENE_TICK,
                                 SLOW_MOTION, SUFFIX, UPDATE_RETS, Pad, Row, Snapshot, _header, _private,
                                 camera_dir, pad_floats, pads, present_pages, private_out, read_meta,
                                 read_snapshot, snapshot_path, store, write_snapshot)

# The frame outside the step (Step X.20).  After a frame's scene ticks the main loop 0x58E40 renders the scene
# (0x5F930 calls RENDER with the scene and the frame's dt; RET 8), and the render moves the game too: it updates the
# active cameras (slot +0xCC: the level camera 0x81240 follows the player) and draws from the game's R250 generator
# 0xB61B0 (its 250 words and index at 0x37B4B8), which critters' AI draws from too: three numbers for each item it sorts into its draw lists
# (0xC14D0's randomized tree 0xB7E30, about 440 numbers a frame by town's rope bridge), the cameras' and, while a
# hit shakes the camera, two more.  So whole steps run the render after each frame's scene ticks, to RENDER_END,
# before its last flush 0x90C80 and the present 0x8FBE0: after the snapshot's frame (its ticks and those done, the
# main loop's MAIN_FRAME on the snapshot's stack), then after every tick, as the replayer pins xemu's frames
# (SLOW_MOTION; else the main loop catches up with the clock, two ticks a frame while xemu runs slow, varying run to
# run).  The GPU is a stub that has done all it was given: the NV2A's registers (NV2A) read 0 but the push buffer's
# GET (NV_GETS), which reads the last PUT the CPU wrote (NV_PUT), and at each such kickoff D3D's GPU time (the dword
# at [D3D_DEVICE]+0x3F0's address) becomes its CPU time ([D3D_DEVICE]+0x1C), so D3D's waits for the GPU end at once.
RENDER, RENDER_END = 0x54800, 0x55820
MAIN_FRAME = 0x59BAA      # the main loop's return from a frame's boot_state_tick (the CALL at 0x59BA5): 8 bytes
                          # above it the loop's frame, +0x14 the frame's ticks, +0x18 their dt so far (f32)
NV2A, NV2A_SIZE = 0xFD000000, 0x1000000
NV_PUT, NV_GETS = 0x800040, (0x800044, 0x324C)
D3D_DEVICE = 0x135420     # D3D's device pointer: +0x1C the CPU's push time, +0x3F0 the address of the GPU's time
DT_30 = 0x3D088889        # f32 1/30, the dt the main loop passes it
SCENE_PTR, PLACE_BUF = recipes.SCENE_PTR, recipes.PLACE_BUF   # the scene; R6's place buffer (live.recipes)
STUBS = {0xADCA0: (0, "the per-frame audio update (scene_state_tick's CALL at 0x562D6; plain RET): its DSOUND "
                     "callee writes through a null object without the audio hardware")}   # VA: (RET N, why)
# L3's own pages, in user VA no snapshot of the game has used (checked at load); _DATA: a page per kernel data
# export, unmapped until the game reads one (its thunk slot is pointed there, so the read is seen for free)
_POOL, _STACK, _GDT, _STOP, _DATA = 0x70000000, 0x7E000000, 0x7E200000, 0x7E300000, 0x7E400000
_CONTIG = 0x8C000000   # contiguous memory L3 allocates: above the 64 or 128 MiB of RAM mapped at 0x80000000
_STACK_SIZE = 0x100000
TSC_PER_TICK = 733_333_333 // 30   # a virtual RDTSC: the Xbox's 733 MHz clock, a frame per step,
TSC_PER_READ = 1000                # and this much more at each read in a step (the scene step spins on it)
# Taint: what a run read that L3 doesn't model, so that a search that found nothing can't count as a refutation
# (the xemu replay checks every positive).  Each kernel call returns 0 (NtAllocateVirtualMemory maps a zeroed
# region); the names here are faithful for the game's own single-threaded step: the rest taint "kernel:<name>".
READS = frozenset({"NtReadFile", "NtReadFileScatter"})   # "read": a read L3 can't serve (zeros)
# File reads (Step X.15).  In a step the game reads files only through its stream module (every read in runs
# from all 46 store snapshots, both modes: characters.xbr and fx.xbr pages): 0xA51C0 queues a request on the pending
# list STREAM_PENDING and calls ReadFile (overlapped), which returns into it at STREAM_READ_RET; the main loop's
# poll STREAM_POLL (CALL at 0x59C8B, once a frame) hands each request whose OVERLAPPED is no longer pending to its
# owner.  A request: +8 the OVERLAPPED (+8 status, +0xC bytes, +0x10 the offset), +0x20 the file object (+0 its name,
# +4 its handle), +0x28 the buffer, +0x2C the length; the files are STREAM_DIR\<name>, the HDD cache of the disc's
# gamedata folder (docs/RE_DATA.md).  L3 serves such a read from the disc at once (in xemu it completes between
# the frame's halts long before the next poll) and runs the poll at each frame's start after the snapshot's.
STREAM_READ_RET, STREAM_DIR = 0xA527B, 0x1BE328
STREAM_POLL, STREAM_PENDING = 0xA58A0, 0x1AA7F8
STATUS_PENDING, STATUS_END_OF_FILE = 0x103, 0xC0000011
TIME = frozenset({"KeQueryPerformanceCounter", "KeQueryPerformanceFrequency", "KeQuerySystemTime",
                  "KeQueryInterruptTime", "NtQuerySystemTime", "KeTickCount", "KeTimeIncrement"})   # "time"
MODELLED = {"NtAllocateVirtualMemory": "maps a zeroed region from L3's pool (or commits inside one)",
            "NtFreeVirtualMemory": "frees nothing: the region stays mapped, and the pool never hands its VAs out again",
            "RtlEnterCriticalSection": "a step is single-threaded: no other thread holds the lock (NATIVE)",
            "RtlLeaveCriticalSection": "the same",
            "MmAllocateContiguousMemory": "maps a zeroed region from L3's contiguous pool (_CONTIG, above any RAM)",
            "MmAllocateContiguousMemoryEx": "the same (a stream page handed to its owner allocates one)",
            "MmFreeContiguousMemory": "frees nothing, as NtFreeVirtualMemory",
            "RtlInitAnsiString": "fills the ANSI_STRING as the kernel does: Length the source's strlen, "
                                 "MaximumLength one more, Buffer the source (a NULL source: all zeros)"}
# Kernel calls that run as guest code at their kernel address, not through a hook (Step X.42): ``mov eax, 0; ret N``
# (N their argument bytes) returns as the hook did (EAX 0, the arguments popped, the flags kept), with no Python
# call (a whole step's kernel calls fell from 458 to 0.8 on f6, 910 to 2.8 in town; docs/SIMULATOR.md).  It keeps
# the game's semantics because a step runs the game's one thread: no other thread holds or waits on a section, so
# Enter never blocks and Leave wakes no one, and neither returns a value; the section's counts and owner stay as the
# snapshot holds them, as under the hook every conformance record ran with.  They count in no ``L3.kernel_calls``;
# a kernel whose exports leave no room for the stub keeps the hook.
NATIVE = frozenset({"RtlEnterCriticalSection", "RtlLeaveCriticalSection"})
# Code whose kernel calls taint nothing: its entry: (its RET's VA, why).
QUIET = {0xB1620: (0xB165B, "the stream module's idle handshake with the HDD-cache prefetch thread (0xB05xx-0xB16xx): "
                            "once no read is pending it takes their lock (a mutant), pulses the event the prefetcher "
                            "sleeps on and releases the lock; the prefetcher copies files to the HDD cache, which "
                            "no step reads")}
# The kernel calls 70 runs from 38 private snapshots made (Step X.10's survey): these four and NtReadFile.  Whole
# steps also read high pages at 0xDA0DD-0xDA0E4, 0xDD4A0, 0xDD5B3, 0xEC953, 0xD4896, 0xDBAC1 and 0xDBC40: arrays
# in contiguous memory (0xDD4A0 searches 0x24-byte records by a float at +0x18), which a snapshot doesn't hold.
# RDTSC reads that taint nothing: (the RDTSC's VA, the return address into its caller at [esp+4]): why.  Whole
# steps read the clock 21 times a step, all here; rows were identical with the virtual clock advancing 1, 1,000
# or 1,000,000 a read (8 private snapshots x 40 whole steps, Step X.10).
TSC_UNTAINTED = {(0xAF525, 0x21E51): "0x21E30 times a scheduler event: the cycles since its last run, divided by "
                                     "the frequency, into a 5-sample ring at +0x60",
                 (0xAF525, 0x21EC1): "0x21E30 keeps the event's start time at +0x48 for that ring"}
# A kernel taint's site (Step X.52): the first return address in the game's own code, GAME, on an EBP walk from the
# kernel call, and for NtCreateFile its object name; at most TAINT_SITES sites a taint.  The game's code is .text
# below the libraries: XAPI starts at 0xDF660 (the find-file helper FindFirstFile calls, after the game's last
# nop-padded function; CreateFile, WriteFile and their kind call the kernel from 0xDF6DE on), the C library follows
# it in .text (fopen, fwrite and fclose reach those wrappers: sitting X.52's e5.sav write showed 0xF3FDB, 0xF0D1C and
# 0xEB4BA as callers when only XAPI was skipped), and D3D, DSOUND and the rest are sections of their own; a word
# that isn't code (a frame that keeps no EBP) is skipped too.
GAME = (0x11000, 0xDF660)
TAINT_SITES = 8
RENDER_US, COLD_RENDER_US = 5_000_000, 60_000_000   # a render's cap; an L3's first render (its code untranslated:
                                                    # 0.4-1.5 s alone, past 5 s under load, Step X.42) gets 60 s
SCENE_US, UPDATE_US, POLL_US = 10_000_000, 2_000_000, 2_000_000   # a scene tick's, a player update's, a stream poll's
# The engine (Step X.52b): what an L3 result depends on beyond its problem id (which hashes the start, the goal's spec
# and the search's shape, never code): L3, the search, the explorer and their helpers, the guides and the reach model's
# code and its data (these paths under the checkout, a folder's ENGINE_SUFFIXES files at any depth; Modkit's were
# under azurik_mod/, so every engine moved with the port, Step 4.13a; the reach model's own folders join with their
# lanes) and Unicorn.  A
# goal names its reach model only by the pickle's path, which follows the level's zoning, and the router reads the
# level's file and its authoring as it loads, so a model fix that keeps the zoning keeps the problem id; proofs.jsonl,
# which no run reads, isn't hashed.  Step X.52 found 12 commits that moved TD.2's runs under the same problem ids; the
# wall-time caps (engine()'s ``caps``) cut a run by the host's load.
ENGINE_FILES = ("devkit/sim", "devkit/reach/l3_fast.py", "devkit/reach/l3_pool.py", "devkit/rando/draft",
                "devkit/rando/physics.py", "src/azurkit/tools/randomizer/draft",
                "src/azurkit/tools/randomizer/data", "src/azurkit/tools/randomizer/physics.py",
                "src/azurkit/tools/randomizer/art/collision.py",
                "src/azurkit/tools/randomizer/live/pages.py", "src/azurkit/tools/randomizer/live/recipes.py")
ENGINE_SUFFIXES = (".py", ".toml", ".json", ".gz")
# A level exit (Step X.52b).  The node graph's gate calls FIRE with the levelSwitch in EDI, which copies its movie
# (+0x18), level (+0x1C) and spot (+0x20) into the request 0x38D320 and posts it; a tick or two later the scene tick
# takes it and unloads the level, UNLOAD(scene, 0) (from 0x55F46, before load_level_from_path 0x55F80, or 0x55EF3,
# 'last-save-spot''s; a death is UNLOAD(scene, 1)): that writes the level's state to z:\scratch (0x52A10, from
# 0x54322), and the next level's load waits on threads L3 doesn't run.  So L3 records each fire (L3.fires; the step's
# row carries it, Row.exit) and lets its tick finish, and a step that reaches UNLOAD with flag 0, from either caller,
# stops at its entry (LevelExit): no save, wait or taint.  No exit is a hop's arrival (every hop's goal is in its
# snapshot's own level).
FIRE, UNLOAD = 0x6F050, 0x542E0


class L3Error(AssertionError):
    """The step left the snapshot's world: a game assert, an access to an unmapped user page, or a runaway.
    ``site`` names it by kind and place (Step X.52): ``assert <file>:<line>``, ``unmapped@<EIP>`` (another CPU
    error: its Unicorn name, ``insn_invalid@<EIP>``), ``runaway@<EIP>``, ``render timeout@<EIP>``, ``no player
    update``, ``no scene return``, ``place not consumed``; ``other`` when the raiser gave none."""

    def __init__(self, msg: str = "", site: str | None = None):
        super().__init__(msg)
        self.site = site or "other"

    def __reduce__(self):                  # a worker's error crosses the pool with its site
        return type(self), (str(self), self.site)


class LevelExit(L3Error):
    """A step that reached a level exit's unload, UNLOAD(scene, 0), stopped at its entry (Step X.52b): a request
    no levelSwitch fire posted (the debug warp's kind; a fire's own branch ends on its row, ``Row.exit``).  A search
    or the explorer ends that branch as a level exit, not a fault; ``site`` ``level exit``."""

    def __init__(self, msg: str = "", site: str | None = "level exit"):
        super().__init__(msg, site)


def fault_site(exc: BaseException) -> str:
    """The site an ``L3Error`` names (:class:`L3Error`), ``other`` for an error that names none."""
    return getattr(exc, "site", None) or "other"


                                     # every process that reads the snapshot shares one copy in the page cache)


class State(NamedTuple):
    """:meth:`L3.save`'s copy of the memory and the step counters, for :meth:`L3.reset`: the pages (by index)
    that differ from the snapshot (a few dozen after a hundred steps) and their bytes, each region mapped
    since, whole, and the run's taint so far."""
    pages: np.ndarray
    data: np.ndarray
    extra: dict[int, bytes]
    k: int
    polled: bool
    cam: bytes | None
    pool: int
    taint: frozenset = frozenset()
    contig: int = _CONTIG
    nv: tuple = ()                    # the GPU stub's registers (offset, value)
    taint_at: tuple = ()              # (taint, its sites) for L3.taint_at


# -- the code and the disc ----------------------------------------------------------------------------------


def kernel_names(xbe: bytes, snap: Snapshot) -> dict[int, str]:
    """{kernel address: export name}: each thunk slot of ``xbe`` as the snapshot holds it (the kernel resolved it).
    L3's VAs are the USA release's, so a Europe XBE is refused by name (D146)."""
    require_usa(xbe)
    mem = dict(snap.runs)
    starts = sorted(mem)

    def u32(va):
        for s in reversed(starts):
            if s <= va:
                return struct.unpack_from("<I", mem[s], va - s)[0]
        raise KeyError(hex(va))
    return {u32(t.thunk_va): t.name for t in parse_kernel_thunks(xbe)}


def kernel_data_exports() -> frozenset[str]:
    """The kernel's data exports (``KeTickCount``, ``XboxHardwareInfo``, ...): :data:`_KERNEL_H`'s ``data``, the
    variables the game reads through their thunk slots."""
    return frozenset(tomllib.loads(_KERNEL_H.read_text(encoding="utf-8"))["data"])


def _code_sections(xbe: bytes) -> list[dict]:
    return [s for s in parse_xbe_sections(xbe)[1] if s["flags"] & 4]   # executable


def check_code(snap: Snapshot, xbe: bytes) -> None:
    """Refuse a snapshot whose code isn't ``xbe``'s: every executable, read-only section's present pages must
    hold the XBE's bytes (the kernel thunk slots aside, which the loader fills), else the snapshot runs another
    build (a modded or a stale one) and L3 would run code it doesn't have.  Raises ``ValueError`` naming the
    section and the count of bytes that differ; prints no bytes."""
    thunks = [t.thunk_va for t in parse_kernel_thunks(xbe)]
    lo, hi = (min(thunks), max(thunks) + 4) if thunks else (0, 0)
    for sec in _code_sections(xbe):
        if sec["flags"] & 1:              # writable: library code with its data
            continue
        va0, n = sec["vaddr"], min(sec["raw_size"], sec["vsize"])
        want = np.frombuffer(xbe, np.uint8, n, sec["raw_addr"])
        bad = 0
        for va, data in snap.runs:
            a, b = max(va, va0), min(va + len(data), va0 + n)
            if a >= b:
                continue
            diff = np.frombuffer(data, np.uint8)[a - va:b - va] != want[a - va0:b - va0]
            diff[max(lo, a) - a:max(min(hi, b) - a, 0)] = False
            bad += int(diff.sum())
        if bad:
            raise ValueError(f"the snapshot's {sec['name']} differs from the XBE's in {bad} bytes: it runs another "
                             "build (a modded or stale one) than the XBE L3 was given")


def rdtsc_sites(xbe: bytes) -> list[int]:
    """Every VA in ``xbe``'s code where the bytes 0F 31 (RDTSC) lie: an instruction that starts at one is an
    RDTSC (a code hook fires only at an instruction's start, so the others cost nothing)."""
    out = []
    for sec in _code_sections(xbe):
        raw = xbe[sec["raw_addr"]:sec["raw_addr"] + min(sec["raw_size"], sec["vsize"])]
        out += [sec["vaddr"] + m.start() for m in re.finditer(b"\x0f\x31", raw)]
    return out


def disc_files(image: str | Path) -> Callable[[str, int, int], bytes | None]:
    """``read(path, off, n)``: up to ``n`` bytes of the file ``path`` (``gamedata/fx.xbr``) inside the Xbox image
    ``image`` from ``off``, or None when the image has no such file; the image stays open."""
    from devkit.sim.ports import XisoReader
    r, ents = XisoReader(image), {}

    def read(path: str, off: int, n: int) -> bytes | None:
        if path not in ents:
            try:
                ents[path] = r.find(path)
            except FileNotFoundError:
                ents[path] = None
        return None if ents[path] is None else r.read_at(ents[path], off, n)
    return read


def guest_path(path: str) -> str | None:
    """The disc path of a game file path: ``D:\\x\\y`` is ``x/y``; ``Z:\\gamedata\\y`` (the HDD cache, which keeps the
    disc's gamedata files under their own names) is ``gamedata/y``; anything else None."""
    if len(path) > 3 and path[1:3] == ":\\" and path[0].upper() in "DZ":
        return path[3:].replace("\\", "/")
    return None


def engine_sha12(root: str | Path | None = None, files=ENGINE_FILES) -> str:
    """sha256[:12] of the engine's code and data (:data:`ENGINE_FILES` under ``root``, by default the checkout's
    root: each file's path and bytes, in path order, a folder's every :data:`ENGINE_SUFFIXES` file at any depth) and
    Unicorn's version."""
    import unicorn
    root = Path(root) if root is not None else Path(__file__).resolve().parents[2]
    h = hashlib.sha256(f"unicorn {unicorn.__version__}\n".encode())
    for rel in files:
        p = root / rel
        for f in sorted(q for q in p.rglob("*") if q.suffix in ENGINE_SUFFIXES and q.is_file()) if p.is_dir() else [p]:
            h.update(f"{f.relative_to(root).as_posix()}\n".encode() + f.read_bytes())
    return h.hexdigest()[:12]


@functools.cache
def engine() -> dict:
    """The engine version every L3 result carries (Step X.52b): ``sha12`` (:func:`engine_sha12`), Unicorn's version
    and ``caps``, the wall-time caps a step runs under (the scene tick's, the player update's, a render's, the first
    render's, the stream poll's, in microseconds, and the watchdog's period in seconds).  Two results compare only
    on one engine and with no fault on either side (:func:`comparable`)."""
    import unicorn
    return {"sha12": engine_sha12(), "unicorn": unicorn.__version__,
            "caps": {"scene_us": SCENE_US, "update_us": UPDATE_US, "render_us": RENDER_US,
                     "cold_render_us": COLD_RENDER_US, "poll_us": POLL_US, "watchdog_s": _Watchdog.PERIOD}}


def comparable(a: dict, b: dict) -> bool:
    """Whether two L3 results compare (Step X.52b): both carry the same engine (``engine``'s ``sha12``) and neither
    had a fault (a result's ``faults``, or its ``runs``' summed): a fault is a wall-time cap or a step L3 can't run,
    so a run with faults isn't reproducible even on one engine, under another load."""
    def faults(r: dict) -> int:
        return r["faults"] if "faults" in r else sum(x.get("faults", 0) for x in r.get("runs", ()))
    ea, eb = (a.get("engine") or {}).get("sha12"), (b.get("engine") or {}).get("sha12")
    return ea is not None and ea == eb and not faults(a) and not faults(b)


def meta_sha12(meta: dict) -> str:
    """sha256[:12] of a snapshot's metadata without its label and time: the state's identity (the entity, the
    level, the body, the clock, the start hash, the tag, the build and the disc), as proof records name it."""
    return hashlib.sha256(json.dumps({k: v for k, v in meta.items() if k not in ("label", "taken")},
                                     sort_keys=True).encode()).hexdigest()[:12]


# -- the simulator ------------------------------------------------------------------------------------------

class _Watchdog:
    """A step's timeout: :meth:`arm` stores the step's deadline (``armed``), and a thread looks at it every
    :data:`PERIOD` s and stops (``emu_stop``) a step whose deadline has passed, so a runaway is stopped at most a
    period late.  Unicorn's own ``emu_start(timeout=)`` starts a timer thread on every call (92-205 us a call
    against 4-12 us without; the engine review's bench1), and the notify per step this replaced woke the thread
    every step (Step X.42; docs/SIMULATOR.md has its bench).  The thread checks the deadline again and stops under
    the lock :meth:`arm` and :meth:`disarm` take (uncontended: it takes it only for a step past its deadline), so a
    stop never lands in a later step, which could not resume: a stop from another thread is inexact (EIP can rest
    on a read-modify-write whose write landed).  The thread holds only a weak reference, so it ends with its L3."""

    PERIOD = 0.025

    def __init__(self, uc) -> None:
        self.uc, self.armed, self.lock = uc, None, threading.Lock()
        threading.Thread(target=_watch, args=(weakref.ref(self),), daemon=True, name="l3-watchdog").start()

    def arm(self, seconds: float) -> None:
        with self.lock:
            self.armed = time.monotonic() + seconds

    def disarm(self) -> None:
        with self.lock:
            self.armed = None


def _watch(ref: Callable[[], _Watchdog | None]) -> None:
    while True:
        time.sleep(_Watchdog.PERIOD)
        if (wd := ref()) is None:
            return
        if (d := wd.armed) is not None and time.monotonic() >= d:
            with wd.lock:              # the step can't disarm, nor the next arm, until this stop is in
                if (d := wd.armed) is not None and time.monotonic() >= d:
                    wd.uc.emu_stop()   # again each period until disarmed: a stop before emu_start begins is lost
        del wd


def _descriptor(base: int, limit: int, access: int, flags: int) -> bytes:
    return struct.pack("<Q", (limit & 0xFFFF) | (base & 0xFFFFFF) << 16 | access << 40
                       | ((limit >> 16) & 0xF) << 48 | flags << 52 | ((base >> 24) & 0xFF) << 56)


class L3:
    """``snap`` mapped under Unicorn; ``kernel`` is the game's XBE (its thunk table names the kernel addresses the
    snapshot holds, :func:`kernel_names`) or that mapping itself.  ``scene``: whole steps (a snapshot taken at
    the scene tick's entry); else player updates.  ``zone_at(feet) -> str`` names each row's zone (e.g. the
    route planner's ``Router.zone_at``).  Steps run on one memory, like consecutive frames; :meth:`save` and
    :meth:`reset` go back to a start in milliseconds (by default the snapshot's).  ``deep``: each row's
    observation reads the kit, inventory and flag hashes too (about 40 more reads a tick; a search goes
    without).  ``overlay``: a modded build laid over the vanilla snapshot (:mod:`devkit.sim.overlay`, Step
    X.11; ``kernel`` is then the vanilla XBE): its code, constants and appended sections, and its config cells.
    ``disc``: the Xbox image in the tray when the snapshot was taken (a path, or ``read(path, off, n)``,
    :func:`disc_files`), which serves the game's file reads; by default the vanilla ISO when the snapshot's disc
    is vanilla's (its ``iso_sha12``), else none: a read stays zeros and taints the run."""

    def __init__(self, snap: Snapshot, kernel: bytes | dict[int, str], *, scene: bool = False,
                 zone_at: Callable[[tuple], str | None] | None = None, stubs=STUBS, deep: bool = True,
                 overlay: _ov.Overlay | None = None,
                 disc: str | Path | Callable[[str, int, int], bytes | None] | None = None):
        xbe = None
        if isinstance(kernel, bytes):
            xbe, kernel = kernel, kernel_names(kernel, snap)
            check_code(snap, xbe)
        if scene and snap.meta.get("at") != "scene" and not any(
                va <= snap.regs.get("esp", 0) < va + len(d) for va, d in snap.runs):
            raise ValueError("whole steps need a snapshot taken at the scene tick's entry (snapshot --scene) or one "
                             "at the player's update entry that holds its stack (snapshot with high pages)")
        self.uc = uc = Uc(UC_ARCH_X86, UC_MODE_32)
        self.snap, self.kernel, self.scene, self.zone_at, self.deep = snap, kernel, scene, zone_at, deep
        self.entity: int | None = snap.meta.get("entity")
        for va, data in snap.runs:
            if va < 0x7F000000 and va + len(data) > _POOL or va < HIGH <= va + len(data) - 1:
                raise ValueError(f"the snapshot maps {va:#x}, where L3 keeps its own pages")
        fs = snap.regs["fs_base"]
        kpcr = {fs & ~0xFFF, (fs + 0x400) & ~0xFFF}       # a zeroed fake KPCR, unless a high run holds the real one
        kpcr -= {p for p in kpcr for va, d in snap.runs if va >= HIGH and va <= p < va + len(d)}
        own = sorted({a & ~0xFFF for a in kernel} | kpcr)
        # Guest memory is one buffer L3 owns, mapped page for page (mem_map_ptr): the snapshot's user runs, then
        # L3's own (the stack, the zeroed kernel stubs and fake KPCR), then the snapshot's high runs (format 3:
        # its thread's stack, the RAM window), each page mapped and copied in on first touch (_unmapped).  The
        # snapshot's pages as taken stay read-only in ``snap.image`` (a format 2 or 3 file's mapping, shared by
        # every process that loads it); a save or a reset compares and copies whole pages with numpy, in place.
        image = snap.image if snap.image is not None else np.frombuffer(b"".join(d for _, d in snap.runs), np.uint8)
        low = [(va, len(d)) for va, d in snap.runs if va < HIGH]
        high = [(va, len(d)) for va, d in snap.runs if va >= HIGH]
        nlow = sum(n for _, n in low)
        mine = [(_STACK, _STACK_SIZE), *((p, PAGE) for p in own)]
        regions = low + mine + high
        size = sum(n for _, n in regions)
        self._buf = mmap.mmap(-1, size)                    # page-aligned and zero-filled
        self._mem = np.frombuffer(self._buf, np.uint8)
        self._mem[:nlow] = image[:nlow]
        o = 0
        for va, n in low + mine:
            uc.mem_map_ptr(va, n, UC_PROT_ALL, self._mem.ctypes.data + o)
            o += n
        self._ns = nlow // PAGE                            # the snapshot's pages come first; L3's own are zero
        self._hb = o // PAGE                               # then the high pages, mapped as touched (self._hi)
        self._m64 = self._mem.view(np.uint64).reshape(-1, PAGE // 8)
        self._p64 = image[:nlow].view(np.uint64).reshape(-1, PAGE // 8)
        self._h64 = image[nlow:].view(np.uint64).reshape(-1, PAGE // 8)
        self._hruns = [(va, n, self._hb + (sum(m for _, m in high[:i]) // PAGE)) for i, (va, n) in enumerate(high)]
        self._hi = np.zeros(0, np.int64)
        self._page_va = np.concatenate([np.arange(va, va + n, PAGE, dtype=np.int64) for va, n in regions])
        uc.mem_map(_STOP, PAGE)
        gdt = (b"\0" * 8 + _descriptor(0, 0xFFFFF, 0x9B, 0xC) + _descriptor(0, 0xFFFFF, 0x93, 0xC)
               + _descriptor(fs, 0xFFF, 0x93, 0x4))
        uc.mem_map(_GDT, PAGE)
        uc.mem_write(_GDT, gdt)
        uc.reg_write(X.UC_X86_REG_GDTR, (0, _GDT, len(gdt) - 1, 0))
        for seg in (X.UC_X86_REG_SS, X.UC_X86_REG_DS, X.UC_X86_REG_ES):
            uc.reg_write(seg, 2 << 3)
        uc.reg_write(X.UC_X86_REG_FS, 3 << 3)
        self.kernel_calls: dict[str, int] = {}
        self.taint: set[str] = set()       # since the last reset (with the state's): the rows carry it
        self.taint_at: dict[str, set[str]] = {}   # a kernel taint's sites since the last reset (_kernel_site)
        self._warm = False                 # whether this L3 has rendered (its first render's cap is the cold one)
        self.fires: list[tuple] = []       # each levelSwitch fire since the last reset: (step, level, movie)
        self._exit, self._leaving = None, False
        self.k, self._polled, self._cam, self._pool, self._contig, self._quiet = 0, True, None, _POOL, _CONTIG, 0
        self._rendering, self._nv = False, {}
        self._first, self._first_dt = 0, None   # the step that ends the snapshot's frame, and that frame's dt
        if any(va >= HIGH for va, _ in snap.runs):   # format 3: the render's memory as taken; the GPU a stub
            uc.mmio_map(NV2A, NV2A_SIZE, self._nv_read, None, self._nv_write, None)
        r = snap.regs                      # each step starts from the snapshot's registers and FPU and SSE state
        self._fixed = [(X.UC_X86_REG_EAX, r.get("eax", 0)), (X.UC_X86_REG_EBX, r.get("ebx", 0)),
                       (X.UC_X86_REG_EDX, r.get("edx", 0)), (X.UC_X86_REG_ESI, r.get("esi", 0)),
                       (X.UC_X86_REG_EDI, r.get("edi", 0)), (X.UC_X86_REG_EFLAGS, r.get("eflags", 0x202) & ~0x100),
                       (X.UC_X86_REG_FPCW, r.get("fctrl", FPU_CW)), (X.UC_X86_REG_FPSW, r.get("fstat", 0)),
                       (X.UC_X86_REG_FPTAG, 0xFFFF), (X.UC_X86_REG_MXCSR, r.get("mxcsr", 0x1F80))]
        self._extra: dict[int, int] = {}   # regions mapped since (allocations, high pages): va -> size
        self._assert = self._row = self._cam_used = None
        self._entry: tuple = ()
        self._in = False
        for addr, name in kernel.items():   # NATIVE: mov eax, 0; ret N, where it fits before the next export
            stub = b"\xb8\0\0\0\0\xc2" + struct.pack("<H", kernel_arg_bytes()[name]) if name in NATIVE else b""
            if stub and (addr & 0xFFF) + len(stub) <= PAGE and not any(addr < a < addr + len(stub) for a in kernel):
                self.write(addr, stub)       # before the base state: every reset keeps it
            else:
                uc.hook_add(UC_HOOK_CODE, self._kernel_call, begin=addr, end=addr)
        for va, (pop, _why) in stubs.items():
            uc.hook_add(UC_HOOK_CODE, lambda u, a, s, d, pop=pop: self._return(0, pop), begin=va, end=va)
        for va, (ret, _why) in QUIET.items():
            uc.hook_add(UC_HOOK_CODE, self._quiet_in, begin=va, end=va)
            uc.hook_add(UC_HOOK_CODE, self._quiet_out, begin=ret, end=ret)
        uc.hook_add(UC_HOOK_CODE, self._game_assert, begin=ASSERT_HANDLER, end=ASSERT_HANDLER)
        uc.hook_add(UC_HOOK_CODE, self._update_entry, begin=PLAYER_UPDATE, end=PLAYER_UPDATE)
        uc.hook_add(UC_HOOK_CODE, self._camera, begin=CAMERA_DIR, end=CAMERA_DIR)
        for va in UPDATE_RETS:
            uc.hook_add(UC_HOOK_CODE, self._update_exit, begin=va, end=va)
        uc.hook_add(UC_HOOK_CODE, self._render_end, begin=RENDER_END, end=RENDER_END)
        uc.hook_add(UC_HOOK_CODE, self._fire, begin=FIRE, end=FIRE)
        uc.hook_add(UC_HOOK_CODE, self._unload, begin=UNLOAD, end=UNLOAD)
        uc.hook_add(UC_HOOK_MEM_UNMAPPED, self._unmapped)
        self._data: dict[int, str] = {}
        if overlay is not None and xbe is None:
            raise ValueError("an overlay needs the vanilla XBE: its sections are what the build changes")
        self.overlay = overlay
        if xbe is not None:
            for va in rdtsc_sites(overlay.xbe if overlay is not None else xbe):
                uc.hook_add(UC_HOOK_CODE, self._rdtsc, begin=va, end=va)
            data = kernel_data_exports()
            for t in parse_kernel_thunks(xbe):
                if t.name in data:
                    va = _DATA + PAGE * len(self._data)
                    self._data[va] = t.name
                    self.write(t.thunk_va, struct.pack("<I", va))
        if overlay is not None:
            self._lay(xbe, overlay, stubs)
        self._disc, self._disc_spec = None, disc
        self._wd = _Watchdog(uc)
        self._complete_pending()           # reads in flight when the snapshot was taken: done before the next poll
        self._frame()
        self._base = self.save()           # the snapshot, with those thunks pointed at _DATA

    def _lay(self, xbe: bytes, ov: _ov.Overlay, stubs) -> None:
        """Lay ``ov`` (:mod:`devkit.sim.overlay`) over the snapshot: the build's changed bytes where the
        snapshot holds vanilla's (else refused, naming the section), its appended sections on pages no one maps,
        the constants the game copied at load, then its config cells."""
        hooked = [(PLAYER_UPDATE, 8), (CAMERA_DIR, 4), (SCENE_TICK, 8), (ASSERT_HANDLER, 8), (RENDER, 8),
                  (RENDER_END, 1), (FIRE, 1), (UNLOAD, 1), *((va, 1) for va in UPDATE_RETS), *((va, 8) for va in stubs),
                  *((va, 1) for va in QUIET), *((ret, 1) for ret, _ in QUIET.values())]
        writes, new = _ov.code_writes(xbe, ov.xbe, hooked)
        live: dict[str, int] = {}
        for w in writes:
            try:
                have = self.read(w.va, len(w.new))
            except UcError:
                have = bytes(len(w.new))
            if have != w.old:
                live[w.section] = live.get(w.section, 0) + sum(a != b for a, b in zip(have, w.old))
        if live:
            raise ValueError("the overlay changes bytes the snapshot holds otherwise than vanilla's loader put them "
                             f"({', '.join(f'{k}: {n}' for k, n in sorted(live.items()))}): live data, or another "
                             "build's snapshot")
        for va, size, data, name in new:
            lo, hi = va & ~0xFFF, (va + size + 0xFFF) & ~0xFFF
            for page in range(lo, hi, PAGE):
                try:
                    self.uc.mem_read(page, 1)
                except UcError:
                    continue
                raise ValueError(f"the build's {name} section lands on {page:#x}, a page the snapshot or L3 maps")
            self._map_extra(lo, hi - lo)
            self.write(va, data)
        for w in writes:
            self.write(w.va, w.new)
        for va, data in _ov.copies(self.u32, self.read, self.entity, xbe, ov.xbe) if self.entity else ():
            self.write(va, data)
        for va, data in _ov.pokes(self.u32, self.read, self.entity, ov.cells):
            self.write(va, data)

    # -- memory --
    def _touch(self, va: int, n: int) -> None:
        """Map the snapshot's high pages in [va, va + n) not mapped yet (a host access doesn't fault them in)."""
        for page in range(max(va, HIGH) & ~0xFFF, va + n, PAGE):
            try:
                self.uc.mem_read(page, 1)
            except UcError:
                self._map_high(page)

    def read(self, va: int, n: int) -> bytes:
        try:
            return bytes(self.uc.mem_read(va, n))
        except UcError:
            if va + n <= HIGH:
                raise
            self._touch(va, n)
            return bytes(self.uc.mem_read(va, n))

    def write(self, va: int, data: bytes) -> None:
        """Write ``data`` at ``va`` and drop any translation of it: Unicorn 2.1.4 keeps running code it translated
        before a host write (the engine review's smc bench), so a code poke, an overlay or a reset over code would
        otherwise silently run the old bytes.  About 1.7 us a page."""
        if va + len(data) > HIGH:
            self._touch(va, len(data))
        self.uc.mem_write(va, data)
        if data:
            self.uc.ctl_remove_cache(va, va + len(data))

    def u32(self, va: int) -> int:
        return struct.unpack("<I", self.read(va, 4))[0]

    def pad_va(self) -> int:
        idx = self.u32(ACTIVE_PAD)
        return CONTROLLER_STATE + PAD_SIZE * (idx if idx < 4 else 0)

    def _map_extra(self, va: int, size: int) -> None:
        self.uc.mem_map(va, size)
        self._extra[va] = size

    def _dirty(self) -> np.ndarray:
        """The indices of the pages that differ from the snapshot (L3's own: from zero; the high pages mapped so
        far: from the snapshot's)."""
        m, ns, hb = self._m64, self._ns, self._hb
        d = np.flatnonzero((m[:ns] != self._p64).any(axis=1))
        o = np.flatnonzero(m[ns:hb].any(axis=1)) + ns
        h = self._hi[(m[self._hi] != self._h64[self._hi - hb]).any(axis=1)] if self._hi.size else self._hi
        return np.concatenate((d, o, h))

    def _map_high(self, page: int) -> bool:
        """Map the snapshot's high page ``page`` (VA) from its run, as taken; False when no high run holds it."""
        for va, n, i0 in self._hruns:
            if va <= page < va + n:
                i = i0 + (page - va) // PAGE
                self._m64[i] = self._h64[i - self._hb]
                self.uc.mem_map_ptr(page, PAGE, UC_PROT_ALL, self._mem.ctypes.data + i * PAGE)
                self._hi = np.append(self._hi, i)
                return True
        return False

    def save(self) -> State:
        """The memory and step counters now (a teleported start, say), for :meth:`reset`: the pages that
        differ from the snapshot and the regions mapped since."""
        d = self._dirty()
        return State(d, self._m64[d], {va: self.read(va, n) for va, n in self._extra.items()}, self.k,
                     self._polled, self._cam, self._pool, frozenset(self.taint), self._contig, tuple(self._nv.items()),
                     tuple((k, tuple(sorted(v))) for k, v in sorted(self.taint_at.items())))

    def reset(self, state: State | None = None) -> None:
        """Back to ``state`` (default: the snapshot): regions mapped since are unmapped, and only the pages that
        differ are rewritten, their translations dropped (unchanged code keeps its translations)."""
        state = state or self._base
        for va, size in list(self._extra.items()):
            if len(state.extra.get(va, b"")) != size:
                self.uc.mem_unmap(va, size)
                del self._extra[va]
        for va, data in state.extra.items():
            if va not in self._extra:
                self._map_extra(va, len(data))
            if self.read(va, len(data)) != data:
                self.write(va, data)
        m, hb = self._m64, self._hb
        back = np.setdiff1d(self._dirty(), state.pages, assume_unique=True)
        snap = back[back < self._ns]
        m[snap] = self._p64[snap]
        m[back[(back >= self._ns) & (back < hb)]] = 0
        hi = back[back >= hb]
        m[hi] = self._h64[hi - hb]
        same = (m[state.pages] == state.data).all(axis=1)
        fix = state.pages[~same]
        m[fix] = state.data[~same]
        for va in self._page_va[np.concatenate((back, fix))].tolist():
            self.uc.ctl_remove_cache(va, va + PAGE)
        self.k, self._polled, self._cam, self._pool, self._contig = state.k, state.polled, state.cam, state.pool, \
            state.contig
        self.taint = set(state.taint)
        self.taint_at = {k: set(v) for k, v in state.taint_at}
        self._nv = dict(state.nv)
        self.fires.clear()                 # a search saves no state past a fire: its branch ends on the fire's row

    # -- hooks --
    def _return(self, eax: int, pop: int) -> None:
        esp = self.uc.reg_read(X.UC_X86_REG_ESP)
        self.uc.reg_write(X.UC_X86_REG_EAX, eax & 0xFFFFFFFF)
        self.uc.reg_write(X.UC_X86_REG_EIP, self.u32(esp))
        self.uc.reg_write(X.UC_X86_REG_ESP, esp + 4 + pop)

    def _quiet_in(self, uc, addr, size, _):
        self._quiet += 1

    def _quiet_out(self, uc, addr, size, _):
        self._quiet = max(0, self._quiet - 1)

    def _tainted(self, name: str, site: Callable[[], str] | None = None) -> None:
        if self._quiet:
            return
        if name in READS:
            self.taint.add("read")
        elif name in TIME:
            self.taint.add("time")
        elif name not in MODELLED:
            self.taint.add(key := f"kernel:{name}")
            if site is not None and len(at := self.taint_at.setdefault(key, set())) < TAINT_SITES:
                at.add(site())

    def _kernel_site(self, name: str, esp: int, ebp: int) -> str:
        """A kernel call's site (Step X.52): the first return address in the game's own code (:data:`GAME`) on an
        EBP walk (the call's own, then each frame's ``[ebp + 4]``), and NtCreateFile's object name (its
        OBJECT_ATTRIBUTES' ANSI string); ``?`` for a walk that finds none."""
        rets: list[int] = []
        try:
            rets.append(self.u32(esp))
            for _ in range(16):
                if not ebp or ebp & 3:
                    break
                rets.append(self.u32(ebp + 4))
                nxt = self.u32(ebp)
                if nxt <= ebp:
                    break
                ebp = nxt
        except UcError:
            pass
        caller = next((r for r in rets if GAME[0] <= r < GAME[1]), None)
        out = "?" if caller is None else f"{caller:#x}"
        if name == "NtCreateFile":          # (PHANDLE, ACCESS_MASK, POBJECT_ATTRIBUTES {root, PANSI_STRING, ...}, ...)
            try:
                s = self.u32(self.u32(esp + 12) + 4)
                n, buf = struct.unpack("<HxxI", self.read(s, 8))
                out += " " + self.read(buf, min(n, 260)).decode("latin-1")
            except UcError:
                pass
        return out

    def disc(self) -> Callable[[str, int, int], bytes | None] | None:
        """The reader of the disc's files (``disc=``, or the vanilla ISO for a vanilla disc's snapshot), opened on
        first use; None when there is none."""
        if self._disc is None and self._disc_spec is not False:
            spec = self._disc_spec
            if spec is None:
                from devkit.sim.ports import VANILLA_ISO_SHA256, vanilla_iso
                if self.snap.meta.get("iso_sha12") == VANILLA_ISO_SHA256[:12]:
                    try:
                        spec = vanilla_iso()
                    except (FileNotFoundError, ValueError):
                        spec = None
            self._disc = spec if callable(spec) or spec is None else disc_files(spec)
            self._disc_spec = False if self._disc is None else self._disc_spec
        return self._disc

    def _cstr(self, va: int, n: int = 0x104) -> str:
        return self.read(va, n).split(b"\0")[0].decode("latin-1")

    def _strlen(self, va: int) -> int:
        n = 0
        while (i := (chunk := self.read(va + n, PAGE - ((va + n) & 0xFFF))).find(b"\0")) < 0:
            n += len(chunk)
        return n + i

    def _serve(self, fo: int, buf: int, n: int, off: int, iosb: int) -> int | None:
        """A read of ``n`` bytes at ``off`` of the stream module's file object ``fo`` (+0 its name in STREAM_DIR)
        into ``buf``, served from the disc: the bytes written, the IoStatusBlock ``iosb`` (status, count) set.
        Returns the status (0, or STATUS_END_OF_FILE past the file's end), or None when it can't be served (a
        file the disc doesn't have, no disc)."""
        path = guest_path(f"{self._cstr(STREAM_DIR)}\\{self._cstr(self.u32(fo))}")
        if path is None or (read := self.disc()) is None or (data := read(path, off, n)) is None:
            return None
        status = 0 if data else STATUS_END_OF_FILE
        self.write(buf, data)
        self.write(iosb, struct.pack("<II", status, len(data)))
        return status

    def _stream_pending(self) -> bool:
        try:
            return self.u32(STREAM_PENDING) != STREAM_PENDING
        except UcError:                    # a snapshot without the stream module's globals (a synthetic one)
            return False

    def _complete_pending(self) -> None:
        """Serve the stream requests still pending in the snapshot (in xemu they complete before the next poll);
        one that can't be served taints the run "read"."""
        if not self._stream_pending():
            return
        node, seen = self.u32(STREAM_PENDING), 0
        while node != STREAM_PENDING and seen < 4096:
            if self.read(node + 0x30, 1) == b"\0" and self.u32(node + 8) == STATUS_PENDING and self._serve(
                    self.u32(node + 0x20), self.u32(node + 0x28), self.u32(node + 0x2C),
                    struct.unpack("<Q", self.read(node + 0x10, 8))[0], node + 8) is None:
                self.taint.add("read")
            node, seen = self.u32(node), seen + 1

    def _caller(self, ebp: int) -> int | None:
        try:
            return self.u32(ebp + 4)
        except UcError:
            return None

    def _kernel_call(self, uc, addr, size, _):
        name = self.kernel[addr]
        self.kernel_calls[name] = self.kernel_calls.get(name, 0) + 1
        esp = uc.reg_read(X.UC_X86_REG_ESP)
        if name == "NtReadFile" and self._caller(uc.reg_read(X.UC_X86_REG_EBP)) == STREAM_READ_RET:
            # ReadFile's frame: its caller is the stream module's read, whose request holds the OVERLAPPED (the
            # IoStatusBlock) at +8 and the file object at +0x20; the handle must be that object's
            h, _ev, _apc, _ctx, iosb, buf, n, poff = struct.unpack("<8I", self.read(esp + 4, 32))
            fo = self.u32(iosb - 8 + 0x20)
            status = None if self.u32(fo + 4) != h or not poff else \
                self._serve(fo, buf, n, struct.unpack("<Q", self.read(poff, 8))[0], iosb)
            if status is not None:
                self._return(status, kernel_arg_bytes().get(name, 0))
                return
        self._tainted(name, lambda: self._kernel_site(name, esp, uc.reg_read(X.UC_X86_REG_EBP)))
        if name == "NtAllocateVirtualMemory":   # (PVOID *base, zero bits, PSIZE_T size, type, protect)
            pbase, _bits, psize = struct.unpack("<3I", self.read(esp + 4, 12))
            base, size = self.u32(pbase), (self.u32(psize) + 0xFFF) & ~0xFFF
            if base == 0:
                base, self._pool = self._pool, self._pool + ((size + 0xFFFF) & ~0xFFFF)
                self._map_extra(base, (size + 0xFFFF) & ~0xFFFF)
            else:   # a commit inside a region a reserve mapped (or the snapshot holds)
                base &= ~0xFFF
                for p in range(base, base + size, PAGE):
                    try:
                        uc.mem_read(p, 1)
                    except UcError:
                        self._map_extra(p, PAGE)
            self.write(pbase, struct.pack("<I", base))
            self.write(psize, struct.pack("<I", size))
        elif name in ("MmAllocateContiguousMemory", "MmAllocateContiguousMemoryEx"):   # (size, ...): the base
            size = (self.u32(esp + 4) + 0xFFFF) & ~0xFFFF
            base, self._contig = self._contig, self._contig + size
            self._map_extra(base, size)
            self._return(base, kernel_arg_bytes().get(name, 0))
            return
        elif name == "RtlInitAnsiString":   # (PANSI_STRING dest, PCSZ src); USHORT Length, MaximumLength; Buffer
            dest, src = struct.unpack("<2I", self.read(esp + 4, 8))
            n = self._strlen(src) if src else 0
            self.write(dest, struct.pack("<2HI", n & 0xFFFF, (n + 1) & 0xFFFF, src) if src else bytes(8))
        self._return(0, kernel_arg_bytes().get(name, 0))

    def _game_assert(self, uc, addr, size, _):
        esp = uc.reg_read(X.UC_X86_REG_ESP)
        f, line = struct.unpack("<II", self.read(esp + 4, 8))
        try:
            where = self.read(f, 64).split(b"\0")[0].decode("latin-1")
        except UcError:
            where = hex(f)
        self._assert = f"game assert at {where}:{line} (returns to {self.u32(esp):#x})", f"assert {where}:{line}"
        uc.emu_stop()

    def _update_entry(self, uc, addr, size, _):
        if uc.reg_read(X.UC_X86_REG_ECX) == self.entity and not self._in and self._row is None:
            for va, data in self._entry:
                self.write(va, data)
            self._in = True

    def _camera(self, uc, addr, size, _):
        if self._in:
            esp = uc.reg_read(X.UC_X86_REG_ESP)
            if self._cam is not None:
                self.write(esp + 0x14, self._cam)
            self._cam_used = self.read(esp + 0x14, 8)

    def _update_exit(self, uc, addr, size, _):
        if self._in:
            self._in = False
            o = _obs.read(self.read, self.entity, self._cam_used, deep=self.deep)
            zone = self.zone_at(o.feet) if self.zone_at else None
            self._row = Row(self.k, o.pos, o.state, o.hp, zone, self._entry, self._cam_used, frozenset(self.taint), o)

    def _render_end(self, uc, addr, size, _):
        if self._rendering:
            uc.reg_write(X.UC_X86_REG_EIP, _STOP)

    def _fire(self, uc, addr, size, _):
        """A levelSwitch fires (FIRE, EDI the switch): its level (+0x1C) and movie (+0x18) paths, for the row."""
        edi = uc.reg_read(X.UC_X86_REG_EDI)

        def path(off: int) -> str | None:
            try:
                return self._cstr(p, 0x50) if (p := self.u32(edi + off)) else None
            except UcError:
                return None
        self._exit = (path(0x1C), path(0x18))
        self.fires.append((self.k, *self._exit))

    def _unload(self, uc, addr, size, _):
        if self.u32(uc.reg_read(X.UC_X86_REG_ESP) + 8) == 0:   # UNLOAD(scene, 0): a level exit, not a death
            self._leaving = True
            uc.emu_stop()

    def _nv_read(self, uc, offset, size, _):
        return self._nv.get(NV_PUT, 0) if offset in NV_GETS else 0

    def _nv_write(self, uc, offset, size, value, _):
        self._nv[offset] = value
        if offset == NV_PUT:   # a kickoff: the GPU has run it, so its time is the CPU's (D3D's fences pass)
            dev = self.u32(D3D_DEVICE)
            self.write(self.u32(dev + 0x3F0), self.read(dev + 0x1C, 4))

    def _rdtsc(self, uc, addr, size, _):
        if size == 2:   # an RDTSC reads host time: a virtual clock instead, a frame a step, and the run is tainted
            if (addr, self.u32(uc.reg_read(X.UC_X86_REG_ESP) + 4)) not in TSC_UNTAINTED:
                self.taint.add("rdtsc")
            self._tsc += TSC_PER_READ
            t = self.k * TSC_PER_TICK + self._tsc
            uc.reg_write_batch([(X.UC_X86_REG_EAX, t & 0xFFFFFFFF), (X.UC_X86_REG_EDX, t >> 32)])
            uc.reg_write(X.UC_X86_REG_EIP, addr + 2)   # alone: a batch's EIP write doesn't leave the block

    def _unmapped(self, uc, access, addr, size, value, _):
        if (name := self._data.get(addr & ~0xFFF)) is not None:   # a kernel variable, read through its thunk: 0
            self._tainted(name, lambda: f"{uc.reg_read(X.UC_X86_REG_EIP):#x}")
            self._map_extra(addr & ~0xFFF, PAGE)
            return True
        if addr < HIGH:
            return False
        for page in sorted({addr & ~0xFFF, (addr + size - 1) & ~0xFFF}):
            try:
                uc.mem_read(page, 1)
            except UcError:   # an access across a page boundary may find one of its pages mapped
                if not self._map_high(page):   # the snapshot's, as taken; else contiguous memory, MMIO: a zero page
                    self.taint.add(f"high:{uc.reg_read(X.UC_X86_REG_EIP):#x}")
                    self._map_extra(page, PAGE)
        return True

    # -- steps --
    def _run(self, start: int, stack: tuple[int, ...] | None, regs: dict[int, int], timeout_us: int) -> None:
        """Run ``start`` to the _STOP page: on L3's own stack with ``stack`` (the arguments) under _STOP, or with
        ``stack`` None on the stack ``regs`` names (its return slot pointed at _STOP already)."""
        uc, esp = self.uc, _STACK + _STACK_SIZE - 0x400
        if stack is not None:
            self.write(esp, struct.pack(f"<{1 + len(stack)}I", _STOP, *stack))
        uc.reg_write_batch(self._fixed + [(X.UC_X86_REG_ESP, esp), (X.UC_X86_REG_EBP, esp + 0x100), *regs.items()])
        self._assert, self._tsc, self._quiet, self._leaving = None, 0, 0, False
        self._wd.arm(timeout_us / 1e6)        # one reusable watchdog, not emu_start's thread per call
        try:
            uc.emu_start(start, _STOP)
        except UcError as e:
            eip = uc.reg_read(X.UC_X86_REG_EIP)
            kind = m[1].lower() if (m := re.search(r"UC_ERR_(\w+)", str(e))) else "cpu error"
            raise L3Error(f"{e} at {eip:#x}", f"{'unmapped' if 'unmapped' in kind else kind}@{eip:#x}") from None
        finally:
            self._wd.disarm()
        if self._assert:
            raise L3Error(*self._assert)
        if self._leaving:
            raise LevelExit(f"{start:#x} reached a level exit's unload {UNLOAD:#x}(scene, 0): stopped at its entry")
        if (eip := uc.reg_read(X.UC_X86_REG_EIP)) != _STOP:
            raise L3Error(f"{start:#x} did not return within {timeout_us} us (at {eip:#x})",
                          f"{'render timeout' if start == RENDER else 'runaway'}@{eip:#x}")

    def step(self, pad: Pad = Pad(), *, writes: Iterable[tuple[int, bytes]] = (),
             timeout_us: int | None = None) -> Row:
        """One tick: at a frame's start (from the second step on, once the snapshot's own frame is done) the
        main loop's polls, the latches and the stream; then a player update or a whole step with ``pad`` (and
        ``writes``, (VA, bytes)) written at the player update's entry; a whole step ending a frame renders it."""
        if self.entity is None:
            raise ValueError("the snapshot names no player entity (its meta 'entity')")
        pv = self.pad_va()
        entry = ((pv, pad_floats(pad)), *((va, bytes(d)) for va, d in writes))
        if not self._polled and self.k > self._first:   # between frames (the snapshot's holds _first more ticks):
            # the main loop's poll 0xA2880: a button that read 0 frees its latch; then neutral
            floats = struct.unpack("<12f", self.read(pv + 0x18, 0x30))
            latch = self.read(pv + 0x48, 12)
            self.write(pv + 0x48, bytes(0 if f == 0.0 else b for f, b in zip(floats, latch)))
            self.write(pv, bytes(0x48))
            if self._stream_pending():   # the main loop's stream poll: the reads done since go to their owners
                self._run(STREAM_POLL, (), {}, POLL_US)
        self._polled = False
        if pad.cam is not None:
            self._cam = struct.pack("<2f", *pad.cam)
        elif pad.yaw is not None:
            self._cam = camera_dir(pad.yaw)
        self._entry = entry
        self._row = self._cam_used = self._exit = None
        self._in = False
        if self.scene:
            scene = self.snap.meta.get("scene") or self.u32(SCENE_PTR)
            dt = self.u32(MAIN_DT) if self.overlay is not None else self.snap.meta.get("dt", DT_30)
            if self.k == 0 and self.snap.meta.get("at") != "scene":
                self._finish_frame(timeout_us or SCENE_US)
            else:
                self._run(SCENE_TICK, (scene, dt), {}, timeout_us or SCENE_US)
            if self.k >= self._first:
                try:
                    self._render(scene, self._first_dt if self.k == self._first and self._first_dt else dt,
                                 timeout_us or (RENDER_US if self._warm else COLD_RENDER_US))
                finally:
                    self._warm = True
        else:
            self.write(self.u32(self.entity + 0xC) + 0x10, self.read(self.entity + 0x18, 8))
            self._run(PLAYER_UPDATE, (), {X.UC_X86_REG_ECX: self.entity}, timeout_us or UPDATE_US)
        if self._row is None:
            raise L3Error(f"step {self.k}: the player's update didn't run", "no player update")
        self.k += 1
        return self._row if self._exit is None else self._row._replace(exit=self._exit)

    def _frame(self) -> None:
        """The snapshot's frame, from the main loop's on its stack (MAIN_FRAME, a format 3 snapshot): the steps
        before its render (its ticks less those done, the current one among them) and the dt it renders with
        (the f32 sum the loop keeps).  Without one (no stack held), every step ends a frame."""
        esp, stack = self.snap.regs.get("esp", 0), b""
        for page in range(esp & ~0xFFF, (esp & ~0xFFF) + 0x10000, PAGE):
            try:
                stack += self.read(page, PAGE)
            except UcError:
                break
        want, o = struct.pack("<I", MAIN_FRAME), (esp & 0xFFF) + (-esp % 4)   # from ESP, 4-aligned
        while (o := stack.find(want, o)) >= 0 and o % 4:
            o += 1
        if o < 0 or o + 8 + 0x1C > len(stack):
            return
        ticks, done = struct.unpack_from("<If", stack, o + 8 + 0x14)
        dt, acc = struct.unpack("<f", self.read(MAIN_DT, 4))[0], 0.0
        for _ in range(ticks if 1 <= ticks <= 4 else 0):
            acc = struct.unpack("<f", struct.pack("<f", acc + dt))[0]
        if acc and 0 < done <= acc:
            self._first = ticks - round(done / dt)
            self._first_dt = struct.unpack("<I", struct.pack("<f", acc))[0]

    def _render(self, scene: int, dt: int, timeout_us: int) -> None:
        """The frame's render (RENDER): only on a format 3 snapshot (it draws through contiguous memory), else the
        run taints "render"."""
        if not any(va >= HIGH for va, _ in self.snap.runs):
            self.taint.add("render")
            return
        self._rendering = True
        try:
            self._run(RENDER, (scene, dt), {}, timeout_us)
        finally:
            self._rendering = False

    def _finish_frame(self, timeout_us: int) -> None:
        """Whole steps from an update-entry snapshot: the first one finishes the frame the snapshot stopped in,
        from its own registers on its own stack (a high run): the player's update, the rest of the scheduler's
        events and scene_state_tick's return, at whichever of its two call sites (SCENE_RETS) the stack holds,
        pointed at _STOP; later steps are whole scene ticks."""
        r = self.snap.regs
        for slot in range(r["esp"], r["esp"] + 0x4000, 4):
            if self.u32(slot) in SCENE_RETS:
                break
        else:
            raise L3Error("no scene_state_tick return on the snapshot's stack: not a player update in a scene tick",
                          "no scene return")
        self.write(slot, struct.pack("<I", _STOP))
        regs = {X.UC_X86_REG_ECX: r["ecx"], X.UC_X86_REG_ESP: r["esp"], X.UC_X86_REG_EBP: r.get("ebp", 0)}
        self._run(PLAYER_UPDATE, None, regs, timeout_us)

    def run(self, inputs: Iterable[Pad], *, until: Callable[[Row], bool] | None = None) -> list[Row]:
        """A row per input, stopping after the first row ``until`` accepts (a goal reached, a death)."""
        rows = []
        for pad in inputs:
            rows.append(self.step(pad))
            if until is not None and until(rows[-1]):
                break
        return rows

    def kit_writes(self, kit: dict) -> tuple[tuple[int, bytes], ...]:
        """R2 (``recipes.element_levels``): the writes that set every element level, ``kit``'s ({"earth" | "air" |
        "fire" | "water": 0..3}) and 0 for the ones it doesn't name, for a step's ``writes`` (the xemu replayer
        writes them too).  A level is what a pickup gives; the armor is cast by input (LT+Y)."""
        return tuple(recipes.element_levels(self.u32, {e: int(kit.get(e, 0)) for e in recipes.ELEMENTS} | kit))

    def teleport(self, feet: tuple[float, float, float], yaw: float, *, cell: int | None = None) -> Row:
        """Place the player the game's own way (R6, RAM_RECIPES §5.2): a place request at :data:`PLACE_BUF`,
        consumed by 0x855D0 in this step's player tick, puts the body centre 1 m over ``feet``, airborne (state
        2), facing ``yaw``, in ``cell`` (default: the player's cell now; the room the engine tracks it in).
        Returns that step's row (a neutral pad); the player lands over the next steps."""
        writes = recipes.place(self.u32, feet, yaw, cell=cell, critter=self.u32(self.entity + 0x20))
        row = self.step(writes=writes)
        if self.u32(writes[-1][0]):
            raise L3Error("the place request wasn't consumed: the player tick didn't reach 0x855D0",
                          "place not consumed")
        return row
