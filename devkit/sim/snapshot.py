"""A guest RAM snapshot's file, its private store and the pad, without a CPU (Steps X.5-X.6, D168, D170; split off
Modkit's ``sim/l3.py``, Step 4.14a1).

A snapshot is every present user page (VA below 0x80000000) of a running game, read through the page tables'
self-map (PDEs at 0xC0300000, PTEs at 0xC0000000), the halted CPU's registers and metadata (the level, the
player's entity and position, the xemu build, the ISO), and in format 3 runs at or above :data:`HIGH` too (the
thread's stack, the RAM window).  The xemu harness takes one at the player's update entry :data:`PLAYER_UPDATE`
(or the scene tick's entry :data:`SCENE_TICK`) into the private :func:`store`; simulator Level 3 (Step 4.13a)
maps it under Unicorn and runs the game's code on it.  This module is what both need without Unicorn: the file
(:func:`write_snapshot`, :func:`read_snapshot`, :func:`read_meta`), the store and the results writer
(:func:`private_out`), the addresses the harness halts at, and a tick's :class:`Pad` (:func:`pad_floats`,
:func:`camera_dir`, :func:`pads`) and :class:`Row`, which the harness's replayer writes into xemu at the same
instructions L3 does, so an input string found in L3 replays exactly there.

Guest RAM holds console key material: snapshots live only in the private store (mode 700, files 0600), are
never committed (``tests/_leak_guard.py`` refuses :data:`MAGIC`) and never printed: lengths and sha256[:12]
only.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import struct
import sys
from pathlib import Path
from typing import Callable, Iterable, NamedTuple

import numpy as np

from azurkit.tools.randomizer.live import recipes
from azurkit.tools.randomizer.live.pages import PAGE, PDE_BASE, PTE_BASE, ram_reader  # noqa: F401 (the harness's)
from devkit.sim import obs as _obs

PLAYER_UPDATE = 0x8C230   # ECX = entity; plain RET (vtable slot .rdata 0x19BC6C, called by scheduler_run)
UPDATE_RETS = (0x8C3F1, 0x8C401)   # its two RETs
SCENE_TICK = 0x55AB0      # scene_state_tick(scene, f32 dt); RET 8
SCENE_RETS = (0x566E1, 0x5F887)   # its returns into its two callers (the CALLs at 0x566DC and 0x5F882)
SLOW_MOTION = 0x38C058    # the "slow motion" cvar (-clock1/-clock2): +4 at 1, the main loop runs one scene tick a
                          # frame instead of catching up with the clock (0x59A77)
MAIN_DT = 0x1983E8        # f32: the main loop's timestep (0x59B94 passes it on; fps_unlock's Patch 3 sets 1/F)
MAIN_RATE = 0x1A28C8      # f64: the main loop's ticks a second, 30.0 (fps_unlock's Patch 2 sets F)
CAMERA_DIR = 0x85276      # fld dword [esp+0x14]: the input builder reads the camera's ground direction (x, y) at
                          # [esp+0x14], [esp+0x18] and stores its yaw atan2(-x, y) at input+0x10 (0x85282)
CONTROLLER_STATE, ACTIVE_PAD, PAD_SIZE = 0x37BE98, 0x1A7AE4, 0x54   # ControllerState[idx]; idx 4 reads [0]
BUTTONS = ("a", "b", "x", "y", "black", "white", "lt", "rt", "lstick", "rstick", "start", "back")
#           ControllerState floats +0x18 + 4i, their latches (u8) +0x48 + i (the game reference skill)
SCENE_PTR = recipes.SCENE_PTR   # the scene (azurkit.tools.randomizer.live.recipes)
MAGIC = b"AZL3SNAP"
SUFFIX = ".l3snap"
FORMAT = 3                # 1: the pages right after the header; 2: from the next 4 KiB boundary (a shared mapping);
                          # 3: 2 with runs at or above HIGH too (the thread's stack, the RAM window)
HIGH = 0x80000000         # a snapshot's runs from here on (format 3) are mapped page by page as a step touches them


class Snapshot(NamedTuple):
    regs: dict                       # the halted CPU: the integer registers, fs_base, fctrl, ...
    runs: list[tuple[int, bytes]]    # (va, bytes) of each run of present pages, ascending (bytes-like)
    meta: dict = {}                  # level, entity, at ("update" | "scene"), xemu, iso_sha12, ... (private)
    image: np.ndarray | None = None  # the runs' pages end to end, read-only (format 2: mapped from the file, so
                                     # every process that reads the snapshot shares one copy in the page cache)


class Pad(NamedTuple):
    """One tick's input: the left stick (x right, y forward: the pad's own floats, -1..1 inside its round
    gate), the buttons held (:data:`BUTTONS`) and the camera yaw in radians (the game's: yaw a looks along
    (-sin a, cos a)); ``None`` keeps the step before's camera (at the start, the snapshot's own).  ``cam``, when
    given, is the camera as the exact f32 pair the input builder reads (a recorded string's), and wins over
    ``yaw``."""
    stick: tuple[float, float] = (0.0, 0.0)
    buttons: frozenset = frozenset()
    yaw: float | None = None
    cam: tuple[float, float] | None = None


class Row(NamedTuple):
    """The player after step ``k`` (0 = the snapshot's own tick), read at the update's RET: ``pos`` the body
    centre critter+0x15C (the feet + 1 m), ``state`` entity+0x94, ``hp`` critter+0x210, ``zone`` the
    ``zone_at(feet)`` L3 was given.  ``writes`` are the (VA, bytes) written at the update's entry (the pad's
    floats, a teleport's request) and ``cam`` the camera direction the input builder read: what the xemu
    replayer writes.  ``obs`` is the whole observation (:mod:`devkit.sim.obs`, the reader the replayer uses at
    the same RET: velocity, flaps, the kit, inventory and flag hashes).  ``exit``: the levelSwitch the step fired
    (its level and movie paths; Step X.52b), else None.  Positions are private."""
    k: int
    pos: tuple[float, float, float]
    state: int
    hp: int
    zone: str | None
    writes: tuple[tuple[int, bytes], ...]
    cam: bytes | None
    taint: frozenset = frozenset()   # what the run so far read that L3 doesn't model
    obs: _obs.Obs | None = None
    exit: tuple | None = None        # a levelSwitch this step fired: (level, movie) (Step X.52b)


# -- the store and the file ---------------------------------------------------------------------------------

def store(folder: str | Path | None = None) -> Path:
    """The private snapshot store: ``folder``, or ``l3-snapshots`` in the user data folder (macOS:
    ``~/Library/Application Support/AzurKit/l3-snapshots``, Modkit's store too), made mode 700.  A folder
    anyone else may enter is refused: guest RAM holds console key material."""
    from platformdirs import user_data_path
    p = Path(folder or user_data_path("AzurKit", appauthor=False) / "l3-snapshots").expanduser()
    p.mkdir(mode=0o700, parents=True, exist_ok=True)
    _private(p)
    return p


def _private(folder: Path) -> None:
    if (mode := folder.stat().st_mode & 0o777) & 0o077:
        raise ValueError(f"{folder} is mode {mode:o}: an L3 snapshot store must be private (mode 700)")


def private_out(path: str | Path, data, indent: int | None = None) -> Path:
    """``data`` as JSON in a new file, mode 0600 (a run's results: tied to its strings and positions), and the path
    written: ``path``, or when a file of that name is there, the first free ``<stem>.<n><suffix>`` (n = 2, 3, ...;
    said on stderr).  No write replaces a file, one whose name differs only by case included: on a case-insensitive
    disk (APFS's default) it is that file (sitting TD.0's ``B-replay.json`` replaced its ``b-replay.json``).  The
    dev tools' one results writer (Step X.51), so a second run never overwrites the first's results."""
    path, n = Path(path), 1
    while True:
        p = path if n == 1 else path.with_name(f"{path.stem}.{n}{path.suffix}")
        try:
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            n += 1
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent)
            f.write("\n" if indent is not None else "")
        if p != path:
            print(f"{path} is there already: wrote {p}", file=sys.stderr)
        return p


def snapshot_path(label: str, folder: str | Path | None = None) -> Path:
    """``<store>/<label>.l3snap``; a label is a plain name (letters, digits, ``._-``)."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", label):
        raise ValueError(f"bad snapshot label {label!r}: letters, digits, '.', '_' and '-' only")
    return store(folder) / f"{label}{SUFFIX}"


def present_pages(read: Callable[[int, int], bytes], lo: int = 0, hi: int = 0x80000000) -> list[int]:
    """The VAs of the present 4 KiB pages in [lo, hi), from the page tables' self-map."""
    pdes = struct.unpack("<1024I", read(PDE_BASE, PAGE))
    out = []
    for i in range(lo >> 22, ((hi - 1) >> 22) + 1):
        if not pdes[i] & 1:
            continue
        ptes = [1] * 1024 if pdes[i] & 0x80 else struct.unpack("<1024I", read(PTE_BASE + i * PAGE, PAGE))
        out += [va for k, pte in enumerate(ptes) if pte & 1 and lo <= (va := (i << 22) | (k << 12)) < hi]
    return out


def write_snapshot(read: Callable[[int, int], bytes], path: Path, regs: dict, meta: dict | None = None,
                   high: Iterable[tuple[int, int, Callable[[int, int], bytes]]] = ()) -> dict:
    """Write the present user pages, ``regs`` and ``meta`` to ``path`` (mode 0600, in a private folder):
    ``MAGIC``, a u32 header length, the JSON header (format, regs, runs as [va, size], meta), zeros to the next
    4 KiB boundary and the pages; then ``high``, (va, size, read) runs at or above HIGH, ascending (format 3; L3
    maps their pages as a step touches them).  Returns counts and a sha256 prefix of the user pages, never
    bytes."""
    path = Path(path)
    _private(path.parent)
    runs: list[list[int]] = []
    for va in present_pages(read):
        if runs and runs[-1][0] + runs[-1][1] == va:
            runs[-1][1] += PAGE
        else:
            runs.append([va, PAGE])
    high = [(va, size, rd) for va, size, rd in high]
    if any(va < HIGH or va % PAGE or size % PAGE for va, size, _ in high) or high != sorted(high, key=lambda h: h[0]):
        raise ValueError("high runs are whole pages at or above 0x80000000, ascending")
    header = json.dumps({"format": FORMAT if high else 2, "regs": regs, "meta": meta or {},
                         "runs": runs + [[va, size] for va, size, _ in high]}).encode()
    digest = hashlib.sha256()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        head = MAGIC + struct.pack("<I", len(header)) + header
        f.write(head + bytes(-len(head) % PAGE))
        for va, size in runs:
            data = read(va, size)
            digest.update(data)
            f.write(data)
        for va, size, rd in high:
            for o in range(0, size, 1 << 22):
                f.write(rd(va + o, min(1 << 22, size - o)))
    return {"pages": sum(s for _, s in runs) // PAGE, "runs": len(runs), "high_pages": sum(s for _, s, _ in high) // PAGE,
            "bytes": sum(s for _, s in runs), "sha12": digest.hexdigest()[:12]}


def _header(f, path) -> tuple[dict, int]:
    """The header and the pages' offset in the file; a format this module doesn't know is refused by name."""
    if f.read(8) != MAGIC:
        raise ValueError(f"{path} is not an L3 snapshot")
    n = struct.unpack("<I", f.read(4))[0]
    hdr = json.loads(f.read(n))
    if (fmt := hdr.get("format", 1)) not in range(1, FORMAT + 1):
        raise ValueError(f"{path} is an L3 snapshot of format {fmt}; this reader reads formats 1 to {FORMAT}")
    return hdr, 12 + n + (-(12 + n) % PAGE if fmt >= 2 else 0)


def read_meta(path: Path) -> dict:
    """A snapshot's metadata, from its header alone."""
    with open(path, "rb") as f:
        return _header(f, path)[0].get("meta", {})


def read_snapshot(path: Path) -> Snapshot:
    """The snapshot at ``path``.  A format 2 file's pages are mapped read-only, not read: workers that load one
    snapshot share its pages."""
    with open(path, "rb") as f:
        hdr, off = _header(f, path)
        total = sum(size for _, size in hdr["runs"])
        if hdr.get("format", 1) >= 2:
            image = np.memmap(f, np.uint8, "r", offset=off, shape=(total,)) if total else np.zeros(0, np.uint8)
        else:
            f.seek(off)
            image = np.frombuffer(f.read(total), np.uint8)
    runs, o = [], 0
    for va, size in hdr["runs"]:
        runs.append((va, memoryview(image[o:o + size])))
        o += size
    return Snapshot(hdr["regs"], runs, hdr.get("meta", {}), image)


# -- inputs -------------------------------------------------------------------------------------------------

def pad_floats(pad: Pad) -> bytes:
    """ControllerState's 0x48 bytes of floats for ``pad``: the sticks, the D-pad (0) and the 12 buttons (1.0
    held).  The 12 latch bytes after them are the game's.  Unknown buttons and non-finite sticks are refused."""
    if bad := set(pad.buttons) - set(BUTTONS):
        raise ValueError(f"unknown buttons {sorted(bad)}; known: {', '.join(BUTTONS)}")
    if not all(math.isfinite(v) for v in pad.stick):
        raise ValueError(f"a stick of {pad.stick} isn't finite")
    return struct.pack("<18f", *pad.stick, 0.0, 0.0, 0.0, 0.0, *(float(b in pad.buttons) for b in BUTTONS))


def camera_dir(yaw: float) -> bytes:
    """The ground direction (-sin yaw, cos yaw), two f32, that the input builder turns into ``yaw``."""
    return struct.pack("<2f", -math.sin(yaw), math.cos(yaw))


def pads(segments: Iterable[dict]) -> list[Pad]:
    """An input string from run-length segments ``{"n": ticks, "stick": [x, y], "buttons": ["y"], "yaw": a}`` or
    with ``"cam": [x, y]`` (the camera's exact f32 pair) in place of ``yaw`` (all keys but ``n`` optional): the
    JSON form the harness's ``replay`` and the proof records hold."""
    out: list[Pad] = []
    for s in segments:
        out += [Pad(tuple(map(float, s.get("stick", (0.0, 0.0)))), frozenset(s.get("buttons", ())),
                    s.get("yaw"), tuple(map(float, s["cam"])) if "cam" in s else None)] * int(s["n"])
    return out
