"""Dev-only xemu oracle: what the game really does with an ISO or a save state.

REORG_PLAN Step 2.11 (D11); agent session s6's harness since Step 2.20l.
Runs sandboxed copies of the owner's macOS xemu fork, each on APFS clones
of the oracle's own fixtures (D98: the folder ``AZURIK_XEMU_FIXTURES`` names,
else the user data folder's ``xemu-fixtures``; never the owner's own xemu), and drives
them over the QEMU gdbstub (GDB RSP), QMP and the fork's input FIFO
(``XEMU_INPUT_PIPE``, MichaelJSr/xemu-macos 38e5e42bbd). Each sandbox
takes a slot (D108 as D174 and D263 amend it): two may always run, whatever the
load, and each one after them starts only while no full test suite runs
(``SUITE_LOCKS``), at least ``MIN_FREE_CORES`` CPU cores are free (idle over
a second, not the load average) and 8 GiB of RAM is free; while an owner demo runs (the fork's ``OWNER_DEMO`` file,
which a demo writes, Step X.37) a window waits, and a headless sandbox starts beside it at macOS background priority
while fewer than ``xemu_queue.demo_budget()`` of ours run there (D526), every other sandbox of ours moved there too
until the demo ends. Waiting sandboxes start first come, first served
(``devkit.xemu.queue``'s tickets, Step X.8). Each runs under ``nice -n 10`` with its own gdb
port and QMP socket, and no running one is ever stopped for load.

    uv run --locked python -m devkit xemu oracle jump --ticks 30    # cold-boot the vanilla ISO, jump once, print v0
    uv run --locked python -m devkit xemu oracle up <group>         # a deterministic sandbox; prints its W
    uv run --locked python -m devkit xemu oracle loadvm <W> <tag>   # a D98 README tag; halts at the first player tick
    uv run --locked python -m devkit xemu oracle snapshot <W> <label> --hold   # an L3 snapshot into the private store
    uv run --locked python -m devkit xemu oracle replay <W> <label> <inputs.json>  # L3, then xemu, compared
    uv run --locked python -m devkit xemu oracle down <W>           # quit, baseline diff, delete W
    uv run --locked python -m devkit xemu oracle selftest           # offline checks (no xemu)

Dev only (devkit, Step 4.14a2), never a player's verb; pytest runs only its offline ``selftest``
(``tests/test_xemu_harness.py``, marked ``xemu``), which launches no xemu. ``devkit/xemu/README.md`` lists every
command; the sandbox recipe, the RAM map and the hazards are in the
``azurik-xemu-oracle`` skill. Scripts use the classes directly
(``from devkit.xemu import oracle as xo``). Nothing here
prints game bytes: decoded values, VAs, hashes and lengths only.
"""

from __future__ import annotations

import argparse
import collections
import contextlib
import ctypes
import datetime
import errno
import functools
import hashlib
import json
import math
import mmap
import os
import re
import shutil
import signal
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
from multiprocessing import shared_memory
from pathlib import Path

from platformdirs import user_cache_dir, user_data_path

from azurkit.core import facts, gate
from azurkit.core import iso as xiso
from azurkit.core.facts import Facts as Region
from azurkit.core.facts import xbe_layout
from azurkit.core.xbe import sections as xbe_sections
from azurkit.tools.randomizer.live import recipes
from devkit.sim import inputs, obs
from devkit.sim import snapshot as l3   # Modkit's sim.l3 without its CPU (Step 4.14a1); L3 itself: l3_replay
from devkit.xemu import queue as xemu_queue
from devkit.xemu import warm as xemu_warm
from devkit.xemu.shim_ranges import copy_gate as copy_gate_data
from devkit.xemu.shim_ranges import player_model as shim_data

ROOT = Path(__file__).resolve().parents[2]   # the checkout (the reaper runs ``-m devkit.xemu.oracle`` there)
USA, EUROPE = facts.of(gate.USA), facts.of(gate.EUROPE)   # each release's facts: its addresses (D146)


def region_named(name: str) -> Region:
    """The facts of the release ``name`` names (``usa``, ``europe``); ``ValueError`` for any other name."""
    for release in gate.RELEASES:
        if release.name == name:
            return facts.of(release)
    raise ValueError(f"no release {name!r}: {', '.join(r.name for r in gate.RELEASES)}")


def vanilla_iso(region: Region = USA) -> Path:
    """``region``'s image the resolver finds (USA's: ``AZURKIT_ISO``, else the user data folder's), through the
    identity gate: ``FileNotFoundError`` says where it looked, ``gate.NotVanillaError`` the first file that differs
    (or another release)."""
    release = region.release
    if (path := gate.find(release)) is None:
        raise FileNotFoundError(f"no {release.label} image: {gate.missing(release)}")
    gate.verify(path, releases=(release,))
    return path


def verify_vanilla_iso(iso: Path) -> None:
    """``gate.NotVanillaError`` (a ``ValueError``) naming the first differing file unless ``iso`` is a vanilla
    release's image."""
    gate.verify(iso)


def read_file(image: Path, name: str) -> bytes:
    """The file ``name`` of the XISO ``image``."""
    with xiso.Reader(image) as r:
        return r.read(name)


def _git_common_dir() -> Path:
    """The checkout's common git folder (a worktree's main checkout's ``.git``), or ``ROOT/.git`` where git can't
    say."""
    try:
        return Path(subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--path-format=absolute",
                                    "--git-common-dir"], capture_output=True, text=True, check=True).stdout.strip())
    except (OSError, subprocess.CalledProcessError):
        return ROOT / ".git"


_COMMON_GIT = _git_common_dir()

# The oracle's fixtures (D98, D67's oracle HDD; their README.md): the
# folder AZURIK_XEMU_FIXTURES names, else the user data folder's
# xemu-fixtures (a link to them): an xemu.toml whose [sys.files] point
# inside the folder, its disc the vanilla ISO. A sandbox clones the files
# it names and never opens them in place. The owner's own xemu
# (OWNER_XEMU, PREF_DIR) is never a source: PREF_DIR, where caches
# would go if portable mode failed, is only listed before and after.
FIXTURES = Path(os.environ.get("AZURIK_XEMU_FIXTURES")
                or user_data_path("AzurKit", appauthor=False) / "xemu-fixtures").expanduser()
# The fork build every sandbox runs by default (D184; Steps X.14, X.22, X.26, X.30, X.32, X.40, X.43, X.61, X.66,
# X.71, X.72, X.94): the owner's local build three commits past the fork's v0.16.4 (0.16.4-3-g95e7ffc7ec, a PGO arm64
# build; D894), with headless and deterministic (-icount) modes, QMP status, display, checkpoint, advance and dump
# commands, input recording, PC hooks, since v0.16.1 the QMP watch monitor and the guest bugcheck report, since
# v0.16.2 28-bit NV2A addresses at 256 MiB or more (nv2a_bits), since v0.16.3 the display query's frame-ends
# (flip_count) and prewarm lists (cache_reads), and since it AZ-822's fix (a park's savevm re-arms the dirty log, so a
# verified restore finds no page missed), the bugcheck event's registers and stack (BUGCHECK_REGS_MARK) and timeout-ms
# on the advances and runs (TIMEOUT_MARK); the code reads each feature's mark from the binary, and the
# azurik-xemu-oracle skill and the developer log hold its history build by build. Cloned into the fixtures (never run in
# place) as xemu-v<the version it logs>.app; the D98 states load in it (a state it saves loads in v0.16.1 to v0.16.4
# and back, not in v0.16 or the kept build: STATE_STREAMS). app=<a path> runs another build: the fixtures keep this
# one, v0.16.4's release (FIXTURES / "xemu-v0.16.4.app", while the lanes that run it end) and KEPT_APP (D683).
FORK_APP = FIXTURES / "xemu-v0.16.4-3-g95e7ffc7ec.app"
# The build that made the D98 states: the fallback (app="kept"), should a state refuse the fork build.
KEPT_APP = FIXTURES / "xemu-v0.13.3-37-gd5ad94f4bf.app"
PREF_DIR = Path.home() / "Library/Application Support/xemu/xemu"
OWNER_XEMU = Path.home() / "Documents/Xemu"
SANDBOX_FILES = {"hdd_path": "xbox_hdd.qcow2", "eeprom_path": "eeprom.bin",
                 "bootrom_path": "bootrom.bin", "flashrom_path": "flashrom.bin",
                 "dvd_path": "dvd.iso"}   # [sys.files] key -> its file in the sandbox
# How long xemu may take to log its paths, then to open its gdbstub: under
# load ~40 on 24 cores (session s5) they took up to 90.1 s and 110.5 s from
# the launch. 180 s each is twice the slowest log line; it costs time only
# when xemu hangs (an exit ends either wait at once).
LAUNCH_S = 180.0
LOADVM_AFTER_S = 25.0   # an older build's first loadvm waits at most this long after its gdbstub answers (await_ready)
# A build with the readiness lines (Step X.14) prints READY once its machine and pads exist (x14: 0.6 s after the
# launch; a loadvm works from then on) and LOADED after each loadvm; a headless one prints DEVICE_LOST and exits
# when macOS stops taking its GPU work (a crash; exit_cause names it). Its known cause, the compositor sampling
# freed surfaces, is fixed since v0.14-12, and the null renderer has no GPU device.
READY, LOADED, DEVICE_LOST = "xemu: ready", "xemu: state loaded", "xemu: Vulkan device lost; exiting"
# Since the fork's 3147640b9b (after v0.14-36; PROMPT-7 P, AZ-293) a failed Vulkan call ends xemu instead of trapping
# forever (the flip-stall hang: QMP dead, SIGTERM ignored): it names the call ("vk_result = N in <function>
# (<file>:<line>)"), then a headless xemu prints DEVICE_LOST for a lost device, else VULKAN_FAILED (a fence wait's
# timeout among them, after its own line), and exits 1; a windowed one aborts. exit_cause names either line and the call.
VULKAN_FAILED = "xemu: Vulkan call failed; exiting"
_VK_CALL = re.compile(r"(?m)^vk_result = -?\d+ in .+$")   # v0.14-36's line is "vk_result = N" alone
_VK_WAIT = re.compile(r"(?m)^xemu: (vkWaitForFences (?:timeout|failed) in .+?)(?: \(>5s\)\.|: VkResult=)")
_OPTION_ERROR = re.compile(r"(?m)^(?:xemu|qemu-system-\w+): (-\w.*)$")   # QEMU's error on an option (AZ-480)
# An assertion that aborted xemu: libc's line (nv2a's vsh-prog.c "Unknown vs param", after its own fprintf line, Step
# 2.105) or glib's (g_assert, g_assert_not_reached, "Bail out!"); exit_cause names it with the line before it (Step X.45)
_ABORT = re.compile(r"(?m)^(?:Assertion failed: .+|(?:\*\* ?)?ERROR:\S+:\d+:.+|Bail out! .+)$")
# A build whose QMP offers query-xemu-status (the fork after v0.14-36, 65421d2d3f; PROMPT-7 N, Step X.33; its
# query-commands lists it, st["xemu_status"]) says the same over QMP: query-xemu-status {ready, loads}, and the events
# XEMU_READY and XEMU_STATE_LOADED (sent before the reply of the load that caused it), with the lines kept. The
# harness then waits on QMP (await_ready, _await_loaded), not on the run log; v0.14-36 has neither.
XEMU_STATUS = "query-xemu-status"
# v0.15 (9ecfc05d3b, 9b5ac9c00f; PROMPT-8 C, AZ-452) waits for the compositor before a screendump and dates the frame it
# writes: query-xemu-display {frame, loads, flips, flip-frame, flip-loads, scanout}. While flip-loads is below loads
# (or absent: no flip yet) the guest hasn't flipped since the last load and the picture is the loaded state's own
# saved frame; v0.14-36's screendump could return the previous screendump's picture (AZ-452) and has no such query.
DISPLAY_QUERY = "query-xemu-display"
# v0.16.1 (the fork's 5e310738d4; PART-11 2.7) adds picture-stale (with picture-loads and picture-frame): true until a GPU
# write into the buffer on screen counts since the last load or checkpoint restore. Azurik writes the same scanout every
# vblank, so after a restore flip-loads said fresh for 1-6 vblanks while the picture was the loaded RAM's frame; the fork
# checked picture-stale over 102 pictures (every old frame flagged, no fresh one). screenshot dates a picture by it where
# present and, on a paused deterministic sandbox, advances one vblank at a time until it is fresh (at most
# PICTURE_STALE_ADVANCE: about 10 covered every case the fork tried).
PICTURE_STALE_ADVANCE = 12
# v0.16.1's XEMU_RENDER_NULL_RAM=request (8ff764493c, 7d518f253a): offscreen Vulkan writes guest RAM as the null renderer
# does and skips draws until xemu-render-next {"flips": N}, which runs the VM until N frames are drawn and on screen
# (at most "frames" vblanks, 120 by default), then pauses: pictures from a run that stays on null's RAM at about null's
# cost (the fork: +4.5 % a frame, against +61-66 % drawing every frame; {"flips": 2} matches an every-frame picture in
# all 1,228,800 pixels, 1 is a few pixels off on a process's first request). Sandbox(null_ram=True), st["null_ram"].
RENDER_NULL_RAM_MARK, RENDER_FLIPS = b"XEMU_RENDER_NULL_RAM", 2
# v0.16.1's xemu-input-queue (6b5ae446f4): XEMU_INPUT_PIPE's lines over QMP (the same grammar and frame tags, the
# keyboard pad's port, a bad line refusing the whole call by its number), up to INPUT_QUEUE_MAX a call and no pipe
# window: play_recording sends a section in one call where query-commands lists it (st["input_queue"]).
INPUT_QUEUE, INPUT_QUEUE_MAX = "xemu-input-queue", 262_144
# v0.16.1's NV2A workload counters (5913de45ef): xemu-frame-advance {"gpu-counters": true} returns the advance's {flips,
# total, max, tail[, per-flip]}, 44 counts each, counted in PGRAPH's method path (the same under null and Vulkan; off,
# nothing changes). GPU_CEILING is vanilla's heaviest flip per counter (sitting x61, results/gpu-ceiling-v0.16.1.json,
# and x66's results/gpu-ceiling-v0.16.2.json, equal: the fork's pack-03 heavy scenes, 2 x 300 vblanks null each, every
# RAM hash the fork's; e7's fight the most begin/end pairs, rz-new the most triangles and pushbuffer): gpu_budget sets a
# build's counters against it. It is no upper bound (sitting x61's s03: vanilla booted at a1, 600 vblanks, went over it
# in 7 of its 10 counts, up to 2.03x), so a build is set against its own vanilla control in the same scene
# (gpu_budget(build, ceiling=control's max)). Sitting 2.173-fc's three cold vanilla boots raised 4 of its counts in
# model_kit's e2/idle (begin-end 521, pushbuffer-bytes 1,110,996, reports 466, texture-binds 1,503; its
# results/summary-b45): frame_ceiling takes those from each sitting's own control, so the values here stay pack-03's.
GPU_CEILING = {"begin-end": 347, "vertices": 218_183, "triangles": 213_262, "pushbuffer-bytes": 1_024_084,
               "vertex-bytes": 13_522_118, "texture-binds": 1_028, "texture-bytes": 10_125_884,
               "surface-bytes": 8_945_664, "clears": 4, "reports": 294}
VBLANK_NS = 16_666_666   # a 60 Hz vblank; v0.16.1's replies carry vblank-ns (20,000,000 under its opt-in PAL 50 Hz)
# v0.15's PC hooks (PROMPT-7 B, PROMPT-8 G): collect and write guest memory at guest PCs with no stop, drained over QMP
# or carried by the next advance's reply, and run a stopped VM to a PC; st["hooks"] where query-commands lists them.
# Sandbox.replay runs through them where it can (Step X.32b; sitting x32: 8.6 ms a tick against 23.4 by gdbstub).
HOOK_COMMANDS = ("xemu-hooks-set", "xemu-hooks-clear", "xemu-run-until")
# v0.16.1's xemu-run (the fork's qapi/xemu.json): input queued and the VM run to a PC, a value in guest memory or a
# budget of vblanks in one call, nothing run between the queueing and the start: deterministic boots run on it
# (st["xemu_run"]; Step X.64, Sandbox.boot_frames).
XEMU_RUN = "xemu-run"
# v0.16's access log (the fork's 47c3dc2b53; README "Memory access log"): xemu-watch-start logs every CPU load or store
# that overlaps up to 64 ranges (1 B to 16 MiB, below 4 GiB; physical by default, matching every mapping of that RAM, or
# virtual) with its frame, pc, address, physical address, size, access and value, the VM never stopped, the same in
# every run under icount and the guest's RAM as without it; -drain returns the hits so far, -stop the rest. Device DMA
# and page-table walks aren't seen. Sandbox.watch (Step X.58), st["watch"] where query-commands lists it.
WATCH_START = "xemu-watch-start"
# v0.16's host-time counters, cumulative since the launch (README "Host-time profile"): translate-ns and translations
# (host time translating guest code), apu-ns and apu-ticks (the APU's ticks under icount; 0 on its own thread in real
# time), idle-ns and idle-warps (guest time a halted vCPU skipped under sleep=off, at no host cost). boot_build keeps
# each boot's difference (host_delta, Step X.58): where a cold boot's host time goes (the fork read's P2).
HOST_PROFILE = "query-xemu-host-profile"
WATCH_RANGES, WATCH_SIZE, WATCH_HITS, WATCH_ACCESS = 64, 16 << 20, 1_000_000, ("r", "w", "rw")
# v0.16.1's QMP watch monitor (the fork's 51cbd74b46; its PART-11 answer 2.2): XEMU_QMP_WATCH=<a -qmp spec> opens one more
# QMP monitor whose requests run on the main loop outside the dispatcher, so it answers while another monitor's advance
# holds QMP: nine read-only queries (query-status, query-xemu-frame, query-xemu-status, ...), CommandNotFound for the
# rest. Every sandbox on a build with it opens W/WATCH_SOCK (st["qmp_watch"]), which a long command's wait asks whether
# the guest's frame still moves (Sandbox._long_qmp, AZ-685). XEMU_SOCKET_BACKLOG=<n> (fc43e0a8bb) sets every listening
# socket chardev's backlog (else 1): with it a second client queues for its greeting, and a refused connect means the
# listener is gone (st["backlog"]).
QMP_WATCH_MARK, WATCH_SOCK = b"XEMU_QMP_WATCH", "qmp-watch.sock"
BACKLOG_MARK, BACKLOG = b"XEMU_SOCKET_BACKLOG", 64
READY_S, LOADED_S = 120.0, 30.0   # how long a launch may take to print READY, and a loadvm's reply LOADED
# A sandbox of ours runs at macOS background priority beside an owner demo (D526): the fork measured, under taskpolicy
# -b, up to 111 s from launch to ready and 24.5 s a loadvm, so READY_S and LOADED_S are this many times longer there.
BACKGROUND_SCALE = 4
UNPARK_LINE_S = 3.0   # unpark's wait for LOADED with the guest held halted (Step X.12)
QMP_S = 10.0   # a QMP connection's socket timeout (an xemu-frame-advance's: ADVANCE_S)
QUIT_S, TERM_S = 20.0, 5.0   # how long down waits for xemu to end after QMP quit, then after SIGTERM and SIGKILL each
WAIT_S = 240.0   # how long a new launch waits for a slot by default (--wait; D108)
POLL_S = 5.0     # a waiting launch checks this often
LEASE_S = 600.0  # a slot whose xemu isn't running is kept this long after its last renewal (Step X.8)
SLOTS = xemu_queue.ROOT   # /tmp/azx-xemu-slots: <W name>.json per sandbox, launch.lock, queue/ (Step X.8)
HELD_DIR = "held"   # SLOTS/HELD_DIR: a sandbox held for its sitting's next run, <W name>.json (Step X.81d; held_dir())
HOLD_S = 300.0   # how long a held sandbox waits for that run (under LEASE_S, so it keeps its slot): 90 % of a
#                  sitting's next sandboxes since 10-22 queued within 289 s of its last teardown (Step X.81d's evidence)
MIN_FREE_RAM = 8 * 2**30
MIN_FREE_DISK = 30 * 2**30   # a sitting's sandbox, its disk image and pictures take 10-27 GiB (Step X.65b)
# D263 (amending D108/D174's load test, on the fork's RESPONSE-8): a third or later sandbox starts while this many
# cores are idle: one for its xemu (each adds about one busy core; the fork measured 196 f/s with 1 instance, 1358
# with 8 and 2100 with 16, which a load-average gate of 16 left mostly unused) and three for the owner's work and
# the agents' tests. Measured as the CPU count times the idle fraction over CPU_WINDOW_S (idle_fraction).
MIN_FREE_CORES = 4
CPU_WINDOW_S = 1.0
ALWAYS = 2   # sandboxes that may always run, whatever the load (D174, amending D108's one)
# The suites' locks: Modkit's agents run its full suite under `lockf -k` on the first (while Modkit lives);
# AzurKit's scripts/fullsuite.py holds its receipts folder's (AZURKIT_RECEIPTS, else in the common git folder) for
# each run, an flock.
SUITE_LOCKS = (Path("/tmp/az-fullsuite.lock"),
               Path(os.environ.get("AZURKIT_RECEIPTS") or _COMMON_GIT / "azurkit-receipts") / "lock")
PRIVATE_TAG = "vanilla-rzp-"   # agent-made states on a private drive (Q250, D102)
CD = "ide0-cd1"   # the DVD drive's QMP device

# Guest VAs below are the USA release's; use_release() points them at the
# booted disc's release through its address map (D146, Step RG.5).
PLAYER_TICK = 0x8CCC0   # player state machine, once per tick; [esp+4] = entity; returns to TICK_RETURN
TICK_RETURN = 0x8C382
JUMP_INIT = 0x89060     # player_jump_init, every ground tick (ESI = entity)
INPUT_BUILD = 0x84F90   # player_input_build, called just before PLAYER_TICK by the same update (0x8C2A0); it reads
                        # ControllerState's sticks after its entry: an analog stick written there acts this tick
CONTROLLER_STATE, ACTIVE_PAD = 0x37BE98, 0x1A7AE4   # ControllerState[idx] (stride 0x54), the active index
# Player entity fields (skill section 4.2): name -> (offset, struct code).
ENT = {"vx": (0x24, "f"), "vy": (0x28, "f"), "vz": (0x2C, "f"),
       "x": (0x38, "f"), "y": (0x3C, "f"), "z": (0x40, "f"),
       "state": (0x94, "I"), "t": (0x9C, "f"), "flaps_used": (0xD8, "i"), "attack": (0x134, "i"),
       "air_ctl": (0x140, "f"), "h": (0x144, "f"), "hold_t": (0x148, "f"), "hold_vz": (0x14C, "f"),
       "peak_z": (0x164, "f"), "prev_z": (0x168, "f"),
       "bx": (0x19C, "f"), "by": (0x1A0, "f"), "bz": (0x1A4, "f")}
ENT_SPAN = max(o + struct.calcsize(c) for o, c in ENT.values())   # 0x1A8: no read past the last field
SAME = ("t", "x", "y", "z", "vz", "state")   # a hit equal on all of these is the same tick again
PAD_FIELDS = {"lx": 0x00, "ly": 0x04, "rx": 0x08, "ry": 0x0C, "dpad_x": 0x10, "dpad_y": 0x14,
              "a": 0x18, "b": 0x1C, "x": 0x20, "y": 0x24, "black": 0x28, "white": 0x2C,
              "lt": 0x30, "rt": 0x34, "start": 0x40, "back": 0x44}   # ControllerState, f32

# Menu checkpoints, confirmed by breakpoints: fixed timings went
# off-script on 3 of 5 edited-config boots (session 4). The boot state
# machine 0x5F620 starts prophecy.bik in state 3 (play_movie_fn returns
# to 0x5F748 at once) and leaves the polling state 4 at 0x5F774 when the
# movie ends. A new game is the level it loads: load_level_from_path
# 0x53750 (stdcall; [esp+8] = path) gets levels/training_room. The
# inventory reset 0x57B70 can't tell: the save list's preview of a save
# runs it too (session s5, AZ-254).
PROPHECY_STARTED, PROPHECY_ENDED = 0x5F748, 0x5F774
LOAD_LEVEL, NEW_GAME_LEVEL = 0x53750, "levels/training_room"
PROPHECY_S = 90.0   # prophecy.bik's length: 2699 frames at 30 fps (its Bink header)
# START presses that don't skip prophecy.bik: the guest ignores the pad
# (AZ-296). In the 86 boot captures in the evidence archive where it
# skipped, the first press did; in the 3 where it didn't (sittings rz-c
# and modelswap2, all after a DVD swap and reset) the movie played out
# through 60-74 presses and nothing after it loaded a level.
DEAD_PAD = 10
LEVEL_S = 45.0      # a route's last press to the level load (p9's value under load)
# A on a save makes boot state 8 call 0x56620: it builds the scene
# (0x563D0: its constructor 0x51650 runs the inventory reset 0x57B70 from
# the CALL at 0x52133, and SCENE_PTR is set once it returns), then
# continues (game_start_setup 0x52F50, from 0x56672), which loads the
# save's level. In 102 of the 104 boot captures in the evidence archive
# with that reset, Continue followed within 0.09 s and the level within
# 0.05 s more; in 2 (sitting modelswap3, AZ-302, the pad live) Continue
# never ran, no level loaded, and in the next 28 s the DVD and HDD read
# no more than a good boot has read when its level load starts.
SCENE_RESET, START_SETUP, SCENE_PTR = 0x52133, 0x52F50, 0x1BF63C
CONTINUE_S = 10.0   # the scene's reset to Continue, and Continue to the level
# The boot state machine's state (docs/RE_XBE.md, enum BootState): the menu
# walk waits on it, not on wall-clock seconds (Step X.9).
BOOT_STATE, MENU, LIST = 0x1BF61C, 6, 8   # 6: the title (sitting x9: 0.26 s after the movie's end); 8: START
                                          # opened the save list
MENU_S = 20.0       # the movie's end to the title, at most
TITLE_AGAIN_S = 2.0   # a press at the title that leaves the state there this long was ignored: press it again
# The save list is ready for A once it has previewed the save under its
# cursor: the preview runs the inventory reset 0x57B70 (s5, AZ-254), within
# 0.5 s of START, so it is armed before the press. Sitting x9 pressed A as
# the list opened: one boot's three As hit no checkpoint and the save loaded
# unseen, another's built the scene with no Continue (AZ-302).
INV_RESET = 0x57B70
# After its preview the list reads the HDD (about 8.5 MB/s, 15 s and more,
# sitting x9: it never stands still) and takes A only when done, 5-25 s
# after it opened: an A pressed sooner waits (taken at once from about 16 s),
# and a second A while it waits delayed or lost the load. So A goes once,
# and again only after A_AGAIN_S with no checkpoint.
A_AGAIN_S = 25.0
A_PRESSES = 3       # each press of the route, at most
# A cursor move onto the next save (dpad_right in the list; on the D98 drive SaveGame #2, the new-game character, is
# one right of #1) is dropped while the list reads the HDD (AZ-354: a press 2 s after the list opened was dropped, one
# at 17 s taken, sitting x15-az354), so it is pressed again every CURSOR_S until the list previews the save it moved
# to (the inventory reset 0x57B70 from 0x1C6A9 again), CURSOR_PRESSES at most (past the read's 25 s). A preview's
# calls come in a burst within 10 ms, and a bare continue from its stop stops there again: those stops are let pass
# until QUIET_S goes by with none before each press (they were taken for the move's preview: 3 boots of 3 loaded #1).
CURSOR_S = 3.0
CURSOR_PRESSES = 12
QUIET_S = 0.5
STEADY_S = 8.0      # guest seconds the player tick must run at every poll (a dialog can open late)
STEADY_WAIT_S = 240.0   # how long `to_player_tick` polls for steady play before NoSteadyTick (wall clock)
NO_TICK_EIPS = 8    # the no-tick polls whose EIPs a NoSteadyTick keeps (AZ-628)
ARENA_STEADY_S = 20.0   # `jump`'s: a new game's Training Arena runs the player tick through its intro with Y
                        # ignored, then opens the welcome dialog about 12 s in (Step X.24, v0.14-12)
BOOT_TRIES = 3      # a boot's tries; each failure relaunches xemu before the next (Step X.9)
# Step X.64 (AZ-675; AZ-628's flake): a deterministic sandbox boots on guest frames (``Sandbox.boot_frames``). Each
# press is queued with its frame counted from the reset in the ``xemu-run`` call that runs to it (nothing runs between
# the queueing and the start), and each wait is a budget in vblanks (the seconds above at 60 Hz) that ends at a PC or a
# boot state, so a build boots the same way in every process. The wall-clock walk let a process's second boot, its
# translations cached, press later in guest time, and one A frame on the save list bugchecks a build (AZ-695, the
# game's own allocator race: the fork's AZ-628 answer, 2026-10-23: one schedule in about 210 for balthazar at f6,
# A = 1459 of 1428-1477 with its START at A - 2, and one in 320 for the vanilla disc). A_FRAME is the frame A goes
# down on the save list: under this schedule (START held PRESS_HOLD a frame after the title, A held A_HOLD) every A
# in 1420-1469 booted both at f6, 100 of 100 (sitting x64's sweep). A retry presses A_RETRY frames later per try (a
# schedule that bugchecks does so in every process).
A_FRAME, A_HOLD, A_RETRY = 1440, 13, 4
SKIP_HOLD = 2       # frames the movie's START is held (prophecy.bik reads the pad every frame: taken at once)
PRESS_HOLD = 8      # frames a menu press is held: the title reads the pad only every few frames (sitting x64: a 2-frame
                    # START was taken at 66 of 108 frames after the title came up, 4 frames 99, 8 frames all 108)
SKIP_F = 90         # frames a START waits for the movie's end before the next (the walk's 1.5 s)
POLL_F, POLL_GAP_F = 90, 30   # frames a steady-tick poll waits for the player tick; frames between polls


def vblanks(seconds: float) -> int:
    """``seconds`` of guest time in 60 Hz vblanks (``VBLANK_NS``): a frame route's budget from the walk's bound."""
    return round(seconds * 1e9 / VBLANK_NS)


_USA_VAS = {name: globals()[name] for name in (
    "PLAYER_TICK", "TICK_RETURN", "JUMP_INIT", "INPUT_BUILD", "CONTROLLER_STATE", "ACTIVE_PAD", "PROPHECY_STARTED",
    "PROPHECY_ENDED", "LOAD_LEVEL", "SCENE_RESET", "START_SETUP", "SCENE_PTR", "BOOT_STATE", "INV_RESET")}


def use_release(region: Region) -> Region:
    """Point the guest VAs above at ``region``'s, each through its address
    map, which names any it lacks (D146). Returns ``region``."""
    globals().update({name: region.va(va) for name, va in _USA_VAS.items()})
    return region
# Title to the save list (in s5 it opened on a save, Start New Game to its
# left), dpad-left, A. (button, wait s)
TITLE = (("start", 3.0), ("dpad_left", 2.0), ("a", 0.0))
SAVE_ROUTE = (("start", 5.0), ("a", 0.0))   # title, A on SaveGame #1 (s6's modded-build path); the waits are bounds


def save_route(save: int = 1) -> tuple:
    """The title to SaveGame #``save``: START, ``save`` - 1 cursor moves right (each confirmed by the list's
    preview of the save it moved to, ``walk_to_level``), A."""
    if save < 1:
        raise ValueError(f"save {save}: the saves count from 1")
    return SAVE_ROUTE[:1] + (("dpad_right", CURSOR_S),) * (save - 1) + SAVE_ROUTE[1:]


JUMP_AT, JUMP_HOLD = 4, 6   # press jump on the first ground tick >= 4, hold 6
# xemu's 25 keyboard-pad inputs (config_spec.yml). The scratch map binds
# them to SDL scancodes 232-256, where SDL3 defines no key, so a real
# keystroke can't reach the pad: only the FIFO can.
PAD = ("a b x y back guide start lstick_btn rstick_btn white black dpad_up "
       "dpad_down dpad_left dpad_right lstick_up lstick_left lstick_right "
       "lstick_down ltrigger rstick_up rstick_left rstick_right rstick_down "
       "rtrigger").split()
_REGS = "eax ecx edx ebx esp ebp esi edi eip eflags cs ss ds es fs gs".split()
_PREF_MARK = "# pref dir (listing only)\n"


def log(*a) -> None:
    print(*a, flush=True)


def now() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def fnum(v):
    """JSON-safe number: a non-finite float becomes its repr."""
    return v if not isinstance(v, float) or math.isfinite(v) else repr(v)


# The NV2A's register window (NV_USER at 0xFD800000): a gdbstub read that strayed there aborted xemu on the fork's
# "Failed to enter DMA mode" assertion (AZ-308, sitting sight223); the fork reads it as 0 since a6d0fdcb79, but its
# write path still asserts. RSP reads and writes refuse it.
NV2A_WINDOW = range(0xFD000000, 0xFE000000)


def nv2a_refused(what: str, va: int, n: int) -> None:
    """Raise ``OSError`` if ``[va, va + n)`` touches ``NV2A_WINDOW`` (AZ-308)."""
    if va < NV2A_WINDOW.stop and va + n > NV2A_WINDOW.start:
        raise OSError(f"{what} {va:#x}: refused, the GPU's register window 0xFD000000-0xFDFFFFFF (a gdbstub "
                      "access there can abort xemu, AZ-308)")


def _pieces(va: int, n: int) -> list[tuple[int, int]]:
    """``[va, va + n)`` cut into gdbstub reads that cross no 4 KiB page, 0x800 bytes at most (AZ-346)."""
    out = []
    while n:
        k = min(n, 0x800, 0x1000 - (va & 0xFFF))
        out.append((va, k))
        va, n = va + k, n - k
    return out


class RSP:
    """GDB remote serial protocol client for QEMU's i386 gdbstub.

    Attaching halts the guest and closing the socket doesn't resume it;
    any byte sent while it runs stops it. ``?`` deletes every
    breakpoint. Watchpoints work on v0.16 (sitting X.58 checked Z2; Z3 and Z4 rest on the fork's 32b1ddf856);
    the kept build wedges on one.
    Reads and writes refuse the GPU's register window (``NV2A_WINDOW``).

    Two of v0.15's features are taken where the stub offers them in its ``qSupported`` reply (Step X.32b; the
    fork's PROMPT-8 advice): ``stepover`` (``Qxemu.stepover+``, turned on for this connection: a resume from a halt
    on an armed ``Z0`` runs the instruction under the PC first, so ``resume`` is a plain ``c``; 1.8 ms a stop
    against z0/s/Z0/c's 4.2) and ``xread`` (``qxemu.read+``: several reads in one round trip, ``read_many``).
    """

    stepover = xread = False   # until the stub offers them (an RSP made without __init__, the selftest's, too)
    writes = 0   # memory writes sent (``M`` packets): a fork request's call sequence counts them (Step X.96)

    def __init__(self, port: int, host: str = "127.0.0.1"):
        self.addr = (port, host)
        self.s = socket.create_connection((host, port), timeout=10.0)
        self.buf = b""
        self._send(b"qSupported:swbreak+;hwbreak+;xemu.stepover+")
        while not (r := self._recv()).startswith(b"PacketSize"):
            pass   # stop replies left over from an earlier client
        offered = set(r.decode(errors="replace").split(";"))
        self.xread = "qxemu.read+" in offered
        self.stepover = "Qxemu.stepover+" in offered and self.cmd("Qxemu.stepover:1") == b"OK"

    def reconnect(self) -> None:
        """This client attached again after its connection was closed (``Sandbox._let_go`` before a run xemu makes,
        Step X.96): the same object, so a caller's ``g`` goes on working; attaching halts the guest."""
        with contextlib.suppress(OSError):
            self.s.close()
        self.__init__(*self.addr)

    def _send(self, payload: bytes) -> None:
        self.s.sendall(b"$%s#%02x" % (payload, sum(payload) & 0xFF))

    def _recv(self) -> bytes:
        while True:
            i = self.buf.find(b"$")
            j = self.buf.find(b"#", i)
            if i >= 0 and j >= 0 and len(self.buf) >= j + 3:
                payload, self.buf = self.buf[i + 1:j], self.buf[j + 3:]
                self.s.sendall(b"+")
                return payload
            chunk = self.s.recv(65536)
            if not chunk:
                raise EOFError("the gdbstub closed the connection")
            self.buf += chunk

    def cmd(self, payload: bytes | str) -> bytes:
        payload = payload.encode() if isinstance(payload, str) else payload
        self._send(payload)
        while True:
            r = self._recv()
            # A stop notification that raced this command isn't its reply.
            if (payload[:1] not in (b"?", b"s", b"g")
                    and r[:1] in (b"T", b"S") and len(r) < 40):
                continue
            return r

    def read(self, va: int, n: int) -> bytes:
        """``n`` bytes at ``va``, in pieces that don't cross a 4 KiB page:
        a read across one fails with E14 now and then (AZ-346: e7's
        townsmen's entity at 0x1653E60, sitting p8). A short reply (the
        fork build answers a partly readable ``m`` with its readable
        prefix) fails like an E14: no read comes back short. The pieces go
        in one ``qxemu.read`` where the stub offers it (``read_many``)."""
        return self.read_many([(va, n)])[0]

    def read_many(self, regions: list[tuple[int, int]]) -> list[bytes]:
        """Each ``(va, n)`` region's bytes, as ``read`` reads them (page-sized pieces, none short), with every piece
        of every region in one ``qxemu.read`` packet where the stub offers it (``xread``, v0.15: 16 x 64 B in
        0.12 ms against 1.6 for 16 ``m`` packets), else an ``m`` each."""
        for va, n in regions:
            nv2a_refused("read", va, n)
        cut = [_pieces(va, n) for va, n in regions]
        flat = [p for c in cut for p in c]
        if self.xread and len(flat) > 1:
            replies = []
            for i in range(0, len(flat), 128):   # a request packet of at most about 2.3 KiB
                part = flat[i:i + 128]
                r = self.cmd(b"qxemu.read:" + b";".join(b"%x,%x" % p for p in part)).split(b";")
                if len(r) != len(part):
                    raise OSError(f"qxemu.read of {len(part)} regions: {len(r)} fields ({r[0][:8]!r})")
                replies += r
        else:
            replies = [self.cmd(b"m%x,%x" % p) for p in flat]
        got = []
        for (va, k), r in zip(flat, replies):
            if r.startswith(b"E"):
                raise OSError(f"read {va:#x}: {r!r}")
            if len(r) != 2 * k:
                raise OSError(f"read {va:#x}: {len(r) // 2} of {k} bytes readable")
            got.append(bytes.fromhex(r.decode()))
        out, i = [], 0
        for c in cut:
            out.append(b"".join(got[i:i + len(c)]))
            i += len(c)
        return out

    def write(self, va: int, data: bytes) -> None:
        nv2a_refused("write", va, len(data))
        self.writes += 1
        r = self.cmd(b"M%x,%x:" % (va, len(data)) + data.hex().encode())
        if r != b"OK":
            raise OSError(f"write {va:#x}: {r!r}")

    def u32(self, va: int) -> int:
        return struct.unpack("<I", self.read(va, 4))[0]

    def regs(self) -> dict[str, int]:
        """The 16 integer registers, ``fs_base`` and ``gs_base`` (bytes
        64 and 68 of this fork's 344-byte 'g' packet), the x87 ``fctrl``,
        ``fstat`` and ``ftag`` (bytes 180, 184, 188, after st0-st7) and
        ``mxcsr`` (byte 340, after xmm0-xmm7): an L3 snapshot's CPU state."""
        raw = bytes.fromhex(self.cmd("g").decode())
        r = dict(zip(_REGS, struct.unpack_from("<16I", raw)))
        r["fs_base"], r["gs_base"] = struct.unpack_from("<II", raw, 64)
        r["fctrl"], r["fstat"], r["ftag"] = (v & 0xFFFF for v in struct.unpack_from("<3I", raw, 180))
        if len(raw) >= 344:
            r["mxcsr"] = struct.unpack_from("<I", raw, 340)[0]
        return r

    def cr3(self) -> int:
        """CR3, the page directory's physical address (byte 84 of the 'g' packet, after the 16 integer registers,
        fs_base, gs_base, k_gs_base, cr0 and cr2): where ``Sandbox``'s shared-memory reads start their page walk."""
        return struct.unpack_from("<I", bytes.fromhex(self.cmd("g").decode()), 84)[0]

    def interrupt(self) -> bytes:
        self.s.sendall(b"\x03")
        return self._recv()

    def cont(self) -> None:
        self._send(b"c")

    def wait_stop(self, timeout: float) -> bytes:
        """The next stop reply; ``TimeoutError`` if the guest runs on."""
        self.s.settimeout(timeout)
        try:
            return self._recv()
        finally:
            self.s.settimeout(10.0)

    def set_bp(self, va: int) -> None:
        self.cmd(b"Z0,%x,1" % va)

    def clear_bp(self, va: int) -> None:
        self.cmd(b"z0,%x,1" % va)


def arm(g: RSP, vas: list[int]) -> None:
    """Make ``vas`` the only breakpoints. On a build before v0.15 each
    identical byte is rewritten to force re-translation: that fork didn't
    invalidate code translated before a ``Z0``, so a bare one might never
    fire. v0.15 (the stub that offers ``Qxemu.stepover``, ``g.stepover``)
    compiles a ``Z0`` into the translated code and retranslates the page at
    the first one (the fork's 21f9186fa7), where the rewrite only
    invalidated the page's 230-odd blocks again (Step X.32b)."""
    g.cmd("?")
    for va in vas:
        g.set_bp(va)
        if not getattr(g, "stepover", False):
            g.write(va, g.read(va, 1))


def resume(g: RSP, vas: list[int], pc: int | None = None) -> None:
    """Continue from a stop with ``vas`` armed. A stub with step-over
    (``g.stepover``, v0.15, Step X.32b) runs the instruction under the PC
    itself: a plain ``c``. An older stub doesn't step over the breakpoint
    under the PC (a bare ``c`` reports that hit again), so only that one is
    lifted: ``z0 pc``, ``s``, ``Z0 pc``, ``c``, 4 packets where lifting
    every armed one took 2N + 2 (Step X.31a). A breakpoint the step lands on
    still stops the continue; from a PC with none under it, a plain ``c``.
    ``pc``: the EIP the caller already read (else one 'g' packet reads it)."""
    if getattr(g, "stepover", False):
        g.cont()
        return
    pc = g.regs()["eip"] if pc is None else pc
    n = vas.count(pc)   # Z0 stacks duplicates: lift each
    for _ in range(n):
        g.clear_bp(pc)
    if n:
        g.cmd("s")
    for _ in range(n):
        g.set_bp(pc)
    g.cont()


QMP_EVENTS_KEPT = 256   # the asynchronous events one QMP connection keeps unread; past it the oldest go (Step X.33)


QMP_REFUSED_S = 3.0   # a per-command QMP connect refused (ECONNREFUSED: nothing sent) is tried again this long


def qmp_dial(path: Path, timeout: float, alive=None, backlog: bool = False) -> tuple["QMP", int]:
    """A per-command QMP connection (a real-time sandbox's, ``Sandbox._qmp_conn``) and how many connects were refused
    first: an ECONNREFUSED connect sent nothing, so it is tried again every 50 ms for ``QMP_REFUSED_S`` while
    ``alive()`` (Step X.56's sitting: a boot's warm savevm, its reload's next connect refused with the demo's
    watchers standing aside, the same boot's retry clean), then raised as before. ``backlog`` (the run set
    ``XEMU_SOCKET_BACKLOG``): a refused connect means the listener is gone, so it is raised at once."""
    end, n = time.monotonic() + QMP_REFUSED_S, 0
    while True:
        try:
            return QMP(path, timeout=timeout, backlog=backlog), n
        except ConnectionRefusedError:
            n += 1
            if backlog or time.monotonic() >= end or (alive is not None and not alive()):
                raise
            time.sleep(0.05)


def qmp_connect_error(path: Path, e: OSError, backlog: bool = False) -> OSError:
    """A failed connect to a QMP socket, saying which case it is (PROMPT-8 E, Step X.37; AZ-464): the file gone
    (ENOENT, by ``lstat``: removed), or there but refusing (ECONNREFUSED: the chardev serves one client with a listen
    backlog of 1, so it is held by another client or by an advance that holds QMP, or another listener took the path
    over, or its xemu died and left the file; with ``backlog``, a run that set ``XEMU_SOCKET_BACKLOG``, a held client
    queues instead, so only the last two). The same OSError subclass, so callers catch it as before. (The first
    client past a held one connects into the backlog and is never greeted: ``QMP`` says so at its timeout.)"""
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        mode = None
    if mode is None:
        why = "removed (ENOENT): its xemu exited, or something deleted the file"
    elif not stat.S_ISSOCK(mode):
        why = "present, not a socket"
    elif e.errno == errno.ECONNREFUSED and backlog:
        why = (f"present, connection refused (ECONNREFUSED) with a listen backlog of {BACKLOG}: no listener, so left "
               "by an xemu that died or taken over (a held client would queue, not refuse)")
    elif e.errno == errno.ECONNREFUSED:
        why = ("present, connection refused (ECONNREFUSED): held by another client or taken over (the chardev serves "
               "one client, listen backlog 1; a held xemu-frame-advance holds it too), or left by an xemu that died")
    else:
        why = f"present, {errno.errorcode.get(e.errno, e.errno) if e.errno else type(e).__name__}: {e.strerror or e}"
    return type(e)(e.errno, f"QMP socket {path}: {why}") if e.errno else type(e)(f"QMP socket {path}: {why}")


class QMP:
    """One QMP connection, negotiated (xemu sends events only to a client that has sent ``qmp_capabilities``).
    ``execute`` returns a command's reply. The asynchronous events that arrive on the connection, before a reply
    or while ``wait_event`` reads, are kept in ``events`` as QMP sends them (``{"event", "data", "timestamp"}``),
    the last ``QMP_EVENTS_KEPT`` (PROMPT-7 N, Step X.33: they were dropped). Each command carries an ``id`` and
    a reply with another one (a late reply to a command whose wait timed out) is skipped (Step X.61). The watch
    monitor's socket (``WATCH_SOCK``) is a monitor of its own, so the held connection doesn't refuse it.
    ``backlog``: the run set ``XEMU_SOCKET_BACKLOG`` (``qmp_connect_error``)."""

    def __init__(self, path: Path, timeout: float = 10.0, backlog: bool = False):
        path = Path(path)
        if path.name != WATCH_SOCK and (_QMP_HELD.get(str(path.parent)) or [None, None])[1] is not None:   # Step X.45
            raise ConnectionRefusedError(errno.ECONNREFUSED, f"QMP socket {path}: held by another client: this "
                                         "process's own (a deterministic sandbox keeps one; send on it with "
                                         "Sandbox.qmp(cmd): a second connection would wait ungreeted to its timeout)")
        self.s = socket.socket(socket.AF_UNIX)
        self.s.settimeout(timeout)
        try:
            self.s.connect(str(path))
        except OSError as e:
            self.s.close()
            raise qmp_connect_error(path, e, backlog) from e
        self._buf, self._seen, self._id = bytearray(), 0, 0
        self.events: collections.deque[dict] = collections.deque(maxlen=QMP_EVENTS_KEPT)
        try:
            self._read()   # greeting
        except TimeoutError as e:   # PROMPT-8 E: the first client past a held one waits in the backlog, ungreeted
            self.s.close()
            raise TimeoutError(f"QMP socket {path}: connected, no greeting in {timeout:g} s: " + (
                f"queued behind a held client (listen backlog {BACKLOG}; an xemu-frame-advance holds QMP too)"
                if backlog else "held by another client or by an xemu-frame-advance that holds QMP (AZ-451; the "
                "chardev serves one client, listen backlog 1)") + ", or xemu's main loop is stuck") from e
        self.execute("qmp_capabilities")

    def _message(self) -> dict:
        """The next whole message (the greeting, a reply or an event); a timeout keeps a partial one buffered."""
        while (i := self._buf.find(b"\n", self._seen)) < 0:
            self._seen = len(self._buf)
            chunk = self.s.recv(1 << 16)
            if not chunk:
                raise EOFError("QMP closed")
            self._buf += chunk
        line = bytes(self._buf[:i])
        del self._buf[:i + 1]
        self._seen = 0
        return scrub_event(json.loads(line))

    def _read(self) -> dict:
        """The next reply (or the greeting); the events before it are kept."""
        while "event" in (msg := self._message()):
            self.events.append(msg)
        return msg

    def send(self, cmd: str, **args) -> int:
        """Send one command; returns its ``id`` (``reply`` waits for it)."""
        self._id += 1
        req = {"execute": cmd, **({"arguments": args} if args else {}), "id": self._id}
        self.s.sendall(json.dumps(req).encode() + b"\n")
        return self._id

    def reply(self, rid: int) -> dict:
        """The reply to command ``rid``: a reply that carries another id (a late one, to a command whose wait timed
        out) is skipped, the events kept. A socket timeout leaves what arrived buffered, so it may be called again."""
        while (msg := self._read()).get("id", rid) != rid:
            pass
        return msg

    def execute(self, cmd: str, **args) -> dict:
        return self.reply(self.send(cmd, **args))

    def wait_event(self, name: str, timeout: float, match=None) -> dict | None:
        """The first kept event ``name`` (with ``match(event)`` true, if given), taken out of ``events``; else the
        next one to arrive within ``timeout`` s, any other event before it kept; None if none came (the connection
        stays usable)."""
        for e in self.events:
            if e.get("event") == name and (match is None or match(e)):
                self.events.remove(e)
                return e
        end, was = time.monotonic() + timeout, self.s.gettimeout()
        try:
            while (left := end - time.monotonic()) > 0:
                self.s.settimeout(left)
                try:
                    msg = self._message()
                except TimeoutError:
                    break
                if "event" not in msg:
                    continue   # a reply no command here waits for
                if msg["event"] == name and (match is None or match(msg)):
                    return msg
                self.events.append(msg)
        finally:
            self.s.settimeout(was)
        return None

    def hmp(self, line: str):
        """A monitor command, e.g. ``info snapshots``."""
        r = self.execute("human-monitor-command", **{"command-line": line})
        return r.get("return", r)

    def open(self) -> bool:
        """Whether xemu still holds this connection, asked without waiting: what waits on it is read into the
        buffer (events, kept for the next read), then end-of-file means xemu closed it (a quit or SIGTERM sends a
        ``SHUTDOWN`` event before it, so a peek alone would say open), nothing more to read means open."""
        was = self.s.gettimeout()
        self.s.setblocking(False)
        try:
            while chunk := self.s.recv(1 << 16):
                self._buf += chunk
            return False
        except BlockingIOError:
            return True
        except OSError:
            return False
        finally:
            self.s.settimeout(was)


def xemu_status_offered(reply: dict, name: str = XEMU_STATUS) -> bool:
    """Whether a ``query-commands`` reply lists ``query-xemu-status`` (or ``name``) by its exact name
    (``st["xemu_status"]``, Step X.33; ``st["display_query"]``, Step X.32): v0.14-36's (``query-xemu-frame``,
    ``query-xemu-checkpoints``) lists neither, nor does an error."""
    return any(c.get("name") == name for c in reply.get("return", []))


def send_keys(fifo: Path, line: str) -> None:
    """One FIFO line: ``down <sc>``, ``up <sc>`` or ``clear``, where
    ``<sc>`` is the SDL scancode bound to a port-2 pad button."""
    fd = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)   # ENXIO: xemu isn't reading
    try:
        os.write(fd, line.encode() + b"\n")
    finally:
        os.close(fd)


def press(fifo: Path, sc: int, wait: float) -> None:
    """Hold a menu button 0.5 s (session 4's working walk), then wait."""
    send_keys(fifo, f"down {sc}")
    time.sleep(0.5)
    send_keys(fifo, f"up {sc}")
    time.sleep(wait)


# --- slots: who may start, on which port (D108, Q258) ------------------

def vm_stat_free(text: str) -> int:
    """Bytes of free RAM in ``vm_stat`` output: its free and speculative pages."""
    page = int(re.search(r"page size of (\d+) bytes", text)[1])
    pages = {m[1]: int(m[2]) for m in re.finditer(r"(?m)^Pages (\w+):\s+(\d+)\.", text)}
    return page * (pages["free"] + pages.get("speculative", 0))


HOST_CPU_LOAD_INFO, CPU_STATE_IDLE = 3, 2   # mach/host_info.h; cpu_ticks[4]: user, system, idle, nice


@functools.cache
def _mach_host() -> tuple[ctypes.CDLL, int]:
    """libSystem and this process's host port (one send right, not one per sample)."""
    lib = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
    lib.mach_host_self.restype = ctypes.c_uint32
    return lib, lib.mach_host_self()


def cpu_ticks() -> list[int] | None:
    """All CPUs' ticks since boot, by state (user, system, idle, nice): mach ``host_statistics``
    (``HOST_CPU_LOAD_INFO``) through ctypes; None when the call fails (not macOS)."""
    try:
        lib, host = _mach_host()
        ticks, count = (ctypes.c_uint32 * 4)(), ctypes.c_uint32(4)   # HOST_CPU_LOAD_INFO_COUNT
        kr = lib.host_statistics(host, HOST_CPU_LOAD_INFO, ticks, ctypes.byref(count))
    except (OSError, AttributeError):
        return None
    return list(ticks) if kr == 0 else None


def idle_fraction(window: float = CPU_WINDOW_S, sample=None) -> float | None:
    """The share of all CPUs' time spent idle over ``window`` seconds: two ``sample()`` calls (``cpu_ticks``)
    that far apart, each state's ticks differenced modulo 2**32 (they are 32-bit and wrap). A niced thread's
    ticks (``CPU_STATE_NICE``: the sandboxes', the fork's automation's) count as busy. None when a sample fails."""
    sample = sample or cpu_ticks
    if (a := sample()) is None:
        return None
    time.sleep(window)
    if (b := sample()) is None:
        return None
    d = [(y - x) % 2**32 for x, y in zip(a, b)]
    return d[CPU_STATE_IDLE] / sum(d) if sum(d) else None


def free_ram() -> int:
    """Bytes of free RAM now (``vm_stat_free``)."""
    return vm_stat_free(subprocess.run(["vm_stat"], capture_output=True, text=True, check=True).stdout)


def suite_running() -> Path | None:
    """The one of ``SUITE_LOCKS`` a test suite holds (Modkit's runs take
    theirs with ``lockf -k``, AzurKit's fullsuite.py its own: both flocks),
    or None: a shared non-blocking flock on each, dropped at once. No lock
    file, no suite."""
    import fcntl   # POSIX's (the module loads on Windows)

    for lock in SUITE_LOCKS:
        try:
            fd = os.open(lock, os.O_RDONLY)
        except OSError:
            continue
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return lock
        finally:
            os.close(fd)
    return None


class CoreWait(str):
    """A refusal that freed cores would end (``admission``'s free-core test, or D174's load test where that can't be
    measured): its ticket says so (``cores``), and only such a wait makes the batch jobs give way (AZ-620)."""


def admission(running: int, idle: float | None = None, cpus: int | None = None,
              free: int | None = None, load: tuple[float, ...] | None = None) -> str | None:
    """Why a new sandbox may not start now, or None (D108, Q258, as D174
    and D263 amend it). While fewer than ``ALWAYS`` (two) are ``running``
    or held, one may always start, whatever the load; each one after them
    only while no full test suite runs (``suite_running``; EFFICIENCY M1
    schedules sittings around it), at least ``MIN_FREE_CORES`` cores are
    free (the CPU count times ``idle``, the idle fraction ``idle_fraction``
    measures) and ``MIN_FREE_RAM`` is free. When the measure fails (not
    macOS) D174's load test decides instead, and its verdict says so: the
    1- and 5-minute ``load`` averages both below two-thirds of the CPUs.
    The first two aren't held back by a suite either: the agents' suites
    queue on the lock, so it can stay held for longer than a sitting
    waits. A core or load refusal is a ``CoreWait``."""
    if running < ALWAYS:
        return None
    if held := suite_running():
        return f"{running} sandbox(es) run and a full suite is running ({held} is held)"
    n = cpus or os.cpu_count() or 1
    if idle is None:
        idle = idle_fraction()
    if idle is not None:
        if (cores := n * idle) < MIN_FREE_CORES:
            return CoreWait(f"{running} sandbox(es) run and {cores:.1f} of {n} CPU cores are free (idle over "
                            f"{CPU_WINDOW_S:g} s), under {MIN_FREE_CORES}")
    else:
        l1, l5 = (load or os.getloadavg())[:2]
        if not (l1 < 2 * n / 3 and l5 < 2 * n / 3):
            return CoreWait(f"{running} sandbox(es) run and the load {l1:.1f} / {l5:.1f} (1 / 5 min) is not below "
                            f"{2 * n / 3:g}, two-thirds of {n} CPUs (host_statistics failed: D174's load test, not "
                            "free cores)")
    if free is None:
        free = free_ram()
    if free < MIN_FREE_RAM:
        return f"{running} sandbox(es) run and {free / 2**30:.1f} GiB of RAM is free, under {MIN_FREE_RAM // 2**30}"
    return None


def disk_wait(w: Path, free: int | None = None) -> str | None:
    """Why a sandbox in ``w`` may not start yet for room, or None: under ``MIN_FREE_DISK`` free (``free``, else
    measured) on ``w``'s volume, its disk image could fill the disk mid-sitting (Step X.65b)."""
    free = shutil.disk_usage(w).free if free is None else free
    if free < MIN_FREE_DISK:
        return f"{free / 2**30:.1f} GiB of disk is free on {w}'s volume, under {MIN_FREE_DISK // 2**30}"
    return None


def slots() -> list[dict]:
    """The held slots, each with its ``state`` (Step X.8's leases):
    ``running`` (its xemu runs, which renews the lease), ``launching`` (no
    xemu yet, and the process taking the slot is alive) or ``kept`` (no
    xemu runs, less than ``LEASE_S`` after the last renewal: kept for its
    own relaunch, ``lease_s`` left). A slot's lease is its file's mtime:
    a launch, ``attach`` and every check that sees its xemu run renew it.
    Every other entry is reclaimed (its file removed; W is left alone): a
    deleted W, a launcher that died before its xemu started, a lease run
    out. No running sandbox is ever stopped (D108)."""
    out = []
    for p in sorted(SLOTS.glob("azx-*.json")):
        try:
            s = json.loads(p.read_text(encoding="utf-8"))
            age = time.time() - p.stat().st_mtime
        except (OSError, ValueError):
            continue
        pid, state = s.get("pid"), None
        if not Path(s["W"]).exists():
            pass
        elif pid and f"{s['W']}/xemu.app/" in pid_command(pid):
            state = "running"
            _renew_slot(Path(s["W"]))
        elif not pid and xemu_queue.alive(s.get("holder")):
            state = "launching"
        elif age < LEASE_S and pid:
            state = "kept"
        if state is None:
            p.unlink(missing_ok=True)
        else:
            out.append({**s, "state": state, **({"lease_s": round(LEASE_S - age)} if state == "kept" else {})})
    return out


def _write_slot(w: Path, info: dict) -> None:
    SLOTS.mkdir(exist_ok=True)
    (SLOTS / f"{w.name}.json").write_text(json.dumps({"W": str(w), **info}), encoding="utf-8")


def _drop_slot(w: Path) -> None:
    (SLOTS / f"{w.name}.json").unlink(missing_ok=True)


def _renew_slot(w: Path) -> bool:
    """Renew ``w``'s slot's lease (its file's mtime); False when it has none."""
    try:
        os.utime(SLOTS / f"{w.name}.json")
        return True
    except FileNotFoundError:
        return False


def xemu_pids() -> list[int]:
    r = subprocess.run(["pgrep", "-x", "xemu"], capture_output=True, text=True)
    return [int(p) for p in r.stdout.split()]


pid_command = xemu_queue.pid_command


def held_dir() -> Path:
    """The folder of held sandboxes' records (``Sandbox.hold_for_sitting``): a subfolder of ``SLOTS``, which
    ``slots`` never reads."""
    return SLOTS / HELD_DIR


def _take_held(p: Path) -> bool:
    """Take the hold record ``p`` (renamed away, then deleted: of two takers one wins); False when another took it."""
    mine = p.with_name(f"{p.name}.taken-{os.getpid()}-{threading.get_ident()}")
    try:
        os.rename(p, mine)
    except FileNotFoundError:
        return False
    mine.unlink(missing_ok=True)
    return True


def finish_held(p: Path) -> bool:
    """Down a held sandbox no run claimed (Step X.81d; its xemu quit and its sources checked at the hold): take its
    record, free its slot and delete W (D147). False when another took it first."""
    try:
        w = Path(json.loads(p.read_text(encoding="utf-8"))["W"])
    except (OSError, ValueError, KeyError):
        return False
    if not _take_held(p):
        return False
    _drop_slot(w)
    if w.is_dir():
        delete_sandbox(w)
    log(f"held sandbox {w.name} downed: no run claimed it")
    return True


def release_held(expired_only: bool = False) -> int:
    """Down the oldest held sandbox (``expired_only``: every one past its time): a launch the admission rule refuses
    frees a hold's slot first, so a hold never keeps a waiting sitting out. Returns how many it downed."""
    recs = []
    for p in held_dir().glob("azx-*.json"):
        with contextlib.suppress(OSError, ValueError):
            recs.append((json.loads(p.read_text(encoding="utf-8"))["until"], p))
    n = 0
    for until, p in sorted(recs):
        if expired_only and until > time.time():
            break
        n += finish_held(p)
        if n and not expired_only:
            break
    return n


def unhold(w: Path, after: float) -> int:
    """The reaper ``hold_for_sitting`` starts: after ``after`` seconds, down the held sandbox ``w`` unless a run
    claimed it (a record that holds it longer is a later hold's, which has its own reaper)."""
    time.sleep(max(0.0, after))
    p = held_dir() / f"{Path(w).name}.json"
    try:
        if json.loads(p.read_text(encoding="utf-8"))["until"] > time.time() + 1:
            return 0
    except (OSError, ValueError, KeyError):
        return 0
    return 0 if finish_held(p) or not p.exists() else 1


def delete_sandbox(w: Path) -> None:
    """Delete a sandbox folder W directly (D147: delete, don't trash). Only a
    harness folder qualifies: a ``azx-*`` directory under /tmp that is not the
    slots folder; anything else is refused by name."""
    p = Path(w).resolve()
    tmp = Path("/tmp").resolve()
    if not (p.name.startswith("azx-") and tmp in p.parents and p != SLOTS.resolve() and p.is_dir()):
        raise RuntimeError(f"refusing to delete {w}: not a harness sandbox folder under /tmp")
    shutil.rmtree(p)


_SANDBOX_APP = re.compile(r"(?:/private)?/tmp/azx-[^/\s]+/xemu\.app/Contents/MacOS/xemu(?:\s|$)")


_FORK_AUTO = re.compile(r"\s-name\s+xemu-fork-auto(?:\s|$)")


def fork_auto_xemus(procs: dict[int, str] | None = None) -> list[int]:
    """The fork's automated xemus (D248, PROMPT-7 A): ``-name xemu-fork-auto``
    in the command (right after the binary in every fork launcher; matched
    anywhere, as the fork's own lease check, ``xemu_lease._is_ours``, does;
    an interactive xemu never has it). They are load, counted through the
    cores they use (``admission``'s free-core measure), not the owner's."""
    if procs is None:
        procs = {p: pid_command(p) for p in xemu_pids()}
    return sorted(p for p, c in procs.items() if not _SANDBOX_APP.match(c) and _FORK_AUTO.search(c))


def foreign_xemus(procs: dict[int, str] | None = None) -> list[int]:
    """The running xemu processes (``{pid: command}``) that aren't an
    oracle sandbox (an app in a ``/tmp/azx-*`` folder) or the fork's automation (``fork_auto_xemus``): the
    owner's own, or someone's ad-hoc copy."""
    if procs is None:
        procs = {p: pid_command(p) for p in xemu_pids()}
    auto = set(fork_auto_xemus(procs))
    return sorted(p for p, c in procs.items() if not _SANDBOX_APP.match(c) and p not in auto)


def sandbox_pids(procs: dict[int, str] | None = None, held: list[dict] | None = None) -> set[int]:
    """The running sandboxes: every xemu whose app is in a ``/tmp/azx-*``
    folder, and every registered slot's process that still runs its W's app."""
    if procs is None:
        procs = {p: pid_command(p) for p in xemu_pids()}
    pids = {p for p, c in procs.items() if _SANDBOX_APP.match(c)}
    return pids | {s["pid"] for s in (slots() if held is None else held) if s["state"] == "running"}


def sandboxes(procs: dict[int, str]) -> int:
    """The sandboxes D108 counts: the running ones (``sandbox_pids``) and
    every slot held with no xemu running (launching, or kept for its own
    relaunch: ``slots``)."""
    held = slots()
    return len(sandbox_pids(procs, held)) + sum(s["state"] != "running" for s in held)


# The fork's owner-demo file (PROMPT-8 F(2): its 81b2192b2e, after v0.14-36; Step X.37). While it names a live pid,
# every fork launcher starts no xemu (it waits, saying so once a minute), and so does every launch of ours but an owner
# demo's (take_slot). An owner demo (D205, ``owner_pad``) writes it atomically right after its xemu starts:
# {"pid": that xemu, "who", "purpose"} (only pid is required; a dead pid or a file that doesn't parse is no demo), and
# removes it once that xemu is gone, only while it still names that pid: a thread of the launching process waits for
# the xemu (reaping it: an exited child left unreaped is a zombie, which ``kill(pid, 0)`` and ``ps -p``, the fork's
# tests, count as running), and ``Sandbox.alive`` (down, a failed launch, a death the harness sees); and any reader of
# ours (``owner_demo``) removes a record of ours whose pid is no xemu (a zombie, or a pid reused after a CLI ``up``'s
# xemu ended with no ``down``). A demo's relaunch keeps it (AZ-601: three sittings launched in that gap beside 2.76's
# window): before its quit the record names the relaunching process, ``relaunch_of`` the old xemu (``_quit(relaunch=
# True)``), so the old xemu's end leaves it, the new xemu's launch replaces it, and a relaunch that never launches
# ends it (``relaunch``, ``down``, ``_abort``); such a record counts while that process runs (its ``relaunch_cmd``).
OWNER_DEMO = xemu_queue.OWNER_DEMO   # the batch tokens read theirs: a driver simulating a demo points both elsewhere
OWNER_DEMO_WHO = xemu_queue.OWNER_DEMO_WHO
# A ticket's wait that only the owner demo's end ends: a window of ours (``owner_demo_says``) or any launch of an older
# harness (Step X.37's hold, in the fork's words); while a demo plays no other launch waits behind one (D526)
DEMO_HELD = re.compile(r": no new (?:window|xemu) until it ends")


def owner_demo() -> dict | None:
    """The record ``OWNER_DEMO`` holds while its pid runs, read as the fork's launchers read it; else None. A record
    of ours (``who`` ``OWNER_DEMO_WHO``) counts only while its pid is an xemu (``ps`` shows an ``xemu.app``; a zombie
    shows ``<defunct>``) or, a relaunch's (``relaunch_of``, AZ-601), while its pid runs the command it recorded
    (``relaunch_cmd``: a reused pid is no relaunch), and one that doesn't is removed (``owner_demo_end``)."""
    try:
        rec = json.loads(OWNER_DEMO.read_text(encoding="utf-8"))
        if isinstance(rec["pid"], bool):
            return None
        pid = int(rec["pid"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if xemu_queue.stale_ours(rec, pid):
        owner_demo_end(rec["pid"])
        return None
    return rec if pid > 0 and xemu_queue.alive(pid) else None


def _demo_named(rec: dict) -> str:
    what = ", ".join([f"pid {rec['pid']}",
                      *(f"{k} {rec[k]}" for k in ("who", "purpose", "expected_end") if rec.get(k))])
    return f"an owner demo runs ({what}; {OWNER_DEMO})"


def owner_demo_says(rec: dict) -> str:
    """Why a window of ours waits for the owner demo ``rec`` (``owner_demo``; ``demo_admission``)."""
    return (f"{_demo_named(rec)}: no new window until it ends (D526: a headless sandbox starts beside it, in the "
            "background)")


def demo_admission(rec: dict, procs: dict[int, str], window: bool = False, keep: bool = False) -> str | None:
    """Why a launch of ours waits while the owner demo ``rec`` plays, or None: then it starts beside the demo at
    background priority (``_launch``) once the usual rule (``admission``) admits it, a relaunch keeping its slot
    (``keep``) at once (D526, amending Step X.37's hold: AZ-620's two hours of idle workers a long demo). A visible
    window waits: the screen is the owner's while they play. A headless sandbox waits while ``demo_budget`` of ours
    already run beside the demo (each uses about one core; the demo's own xemu isn't one of them): the core budget
    background work keeps to, so the demo keeps its cores."""
    if window:
        return owner_demo_says(rec)
    if keep:
        return None
    beside = sandboxes(procs) - bool(_SANDBOX_APP.match(procs.get(int(rec["pid"]), "")))
    if beside >= (budget := xemu_queue.demo_budget()):
        return f"{_demo_named(rec)} and {beside} sandbox(es) run beside it in the background, its budget of {budget}"
    return None


def demo_background(rec: dict | None = None, read: bool = True) -> list[int]:
    """D526: while an owner demo plays (``owner_demo``) every running sandbox of ours but the demo's own runs at macOS
    background priority (``xemu_queue.set_background``); while none plays, each is taken back out. The pids set. A
    sandbox launched beside a demo starts there (``_launch``); this moves those that ran before it, at our demo's start
    (``owner_demo_begin``, its record ``rec``), and puts them back at its end (``owner_demo_end``, ``read`` False: no
    demo), and every admitted launch (``take_slot``) and ``slots`` run it too, for a demo of the fork's or the owner's
    or one whose launcher died. The demo's own xemu (the record's pid, or a sandbox whose ``sandbox.json`` names an
    ``owner_pad``) is never touched, nor a sandbox whose ``sandbox.json`` can't be read."""
    rec, done = rec or (owner_demo() if read else None), []
    for s in slots():
        pid = s.get("pid")
        if s["state"] != "running" or not pid or (rec and pid == int(rec["pid"])):
            continue
        try:
            if json.loads((Path(s["W"]) / "sandbox.json").read_text(encoding="utf-8")).get("owner_pad") is not None:
                continue
        except (OSError, ValueError, AttributeError):
            continue
        if xemu_queue.set_background(pid, rec is not None):
            done.append(pid)
    return done


def owner_demo_begin(pid: int, purpose: str, **extra) -> None:
    """``OWNER_DEMO`` for our demo's xemu ``pid`` (or, ``relaunch_of`` the old xemu in ``extra``, the process that
    relaunches it: AZ-601): a temp file in its folder (made 0o755 if missing), then ``os.replace``, so a launcher
    never reads half of one."""
    d = OWNER_DEMO.parent
    try:
        d.mkdir(mode=0o755, parents=True)
        d.chmod(0o755)   # whatever the umask
    except FileExistsError:
        pass
    fd, tmp = tempfile.mkstemp(prefix=".owner-demo.", suffix=".tmp", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"pid": pid, "who": OWNER_DEMO_WHO, "purpose": purpose, **extra}, f)
        os.chmod(tmp, 0o644)
        os.replace(tmp, OWNER_DEMO)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    demo_background({"pid": pid})   # the sandboxes already running go to the background (D526)


def owner_demo_end(pid: int | None) -> bool:
    """Remove ``OWNER_DEMO`` while it names ``pid`` (our demo's xemu); another's is never touched. True if removed:
    then every sandbox of ours leaves the background (``demo_background``, D526)."""
    try:
        if not pid or json.loads(OWNER_DEMO.read_text(encoding="utf-8")).get("pid") != pid:
            return False
        OWNER_DEMO.unlink()
    except (OSError, ValueError, AttributeError):
        return False
    demo_background(read=False)
    return True


def _owner_demo_reaper(proc: subprocess.Popen) -> threading.Thread:
    """A daemon thread that waits for our demo's xemu ``proc`` (reaping it) and then ends its ``OWNER_DEMO``."""
    def run() -> None:
        proc.wait()
        owner_demo_end(proc.pid)
    t = threading.Thread(target=run, daemon=True, name=f"owner-demo-{proc.pid}")
    t.start()
    return t


def _try_lock() -> int | None:
    import fcntl

    SLOTS.mkdir(exist_ok=True)
    fd = os.open(SLOTS / "launch.lock", os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except BlockingIOError:
        os.close(fd)
        return None


def _unlock(fd: int | None) -> None:
    if fd is not None:
        os.close(fd)   # closing the descriptor drops its flock


LAUNCHING = "another sandbox is launching"   # the launch lock's refusal: no word on cores (``renew_ticket``)


def take_slot(w: Path, wait_s: float, keep: bool = False, demo: bool = False, window: bool = False) -> int:
    """Register ``w``'s slot in first-come order (Step X.8): a ticket
    (``xemu_queue``) waits until no earlier live ticket does, then until
    the launch lock is free, no xemu but the sandboxes and the fork's
    automation runs (``foreign_xemus``), an owner demo that runs
    (``owner_demo``) lets it start beside it (``demo_admission``, D526: a
    ``window`` waits, a headless sandbox within the demo's core budget
    starts in the background; ``demo``, an owner demo's own launch,
    doesn't wait for one, nor, while one runs, for the earlier tickets:
    Step X.37; while one runs no other launch waits behind a ticket that
    waits only for its end, ``DEMO_HELD``), its volume has room (``disk_wait``) and ``admission()`` passes for the sandboxes
    running or held (``sandboxes``), polling every ``POLL_S`` for up to
    ``wait_s`` and saying why at most once a minute while it stays the same;
    the ticket goes once it starts or stops. Admitted, it moves our
    sandboxes into or out of the background (``demo_background``). Returns the held
    launch lock: release it once the gdbstub answers. Launches are
    serialized, so a port ``free_port`` picks can't go to two of them,
    and a running sandbox's port stays bound.
    ``keep``: ``w`` already holds its slot (a relaunch replacing its own
    xemu), so it takes no ticket and no admission test, and waits only
    for the launch lock, a foreign xemu and, a window, an owner demo, renewing its lease."""
    deadline = time.monotonic() + wait_s
    ticket = None if keep else xemu_queue.take_ticket({"W": str(w)}, SLOTS)
    said, said_at = None, 0.0
    try:
        while True:
            fd = None
            ahead = [t for t in xemu_queue.tickets(SLOTS) if t["n"] < int(ticket.stem)] if ticket else []
            if ahead and owner_demo():   # they're first again once it ends
                ahead = [] if demo else [t for t in ahead if not DEMO_HELD.search(t.get("why") or "")]
            if ahead:
                why = f"{len(ahead)} sitting(s) asked first and wait (first come, first served)"
            else:
                fd = _try_lock()
                why = LAUNCHING if fd is None else None
            if why is None:
                procs = {p: pid_command(p) for p in xemu_pids()}
                if others := foreign_xemus(procs):
                    why = f"an xemu runs that isn't a sandbox (pids {others}; maybe the owner's)"
                elif not demo and (rec := owner_demo()) and (why := demo_admission(rec, procs, window, keep)):
                    pass
                elif not keep:
                    release_held(expired_only=True)
                    while (why := disk_wait(w) or admission(sandboxes(procs))) and release_held():
                        pass   # a held sandbox (Step X.81d) gives its slot to a launch the rule refuses
            if why is None:
                if not keep:
                    _write_slot(w, {"holder": os.getpid()})
                demo_background()
                return fd
            _unlock(fd)
            if time.monotonic() > deadline:
                raise SystemExit(f"STOP: {why}; waited {wait_s:.0f} s and started nothing")
            if ticket:   # batch jobs give way only to a wait for cores (AZ-620); another launch's lock says nothing
                xemu_queue.renew_ticket(ticket, why, cores=None if why == LAUNCHING else isinstance(why, CoreWait))
            else:
                _renew_slot(w)
            if (kind := re.sub(r"[\d.]+", "#", why)) != said or time.monotonic() - said_at > 60:   # not every load
                log(f"waiting ({f'ticket {int(ticket.stem)}' if ticket else 'keeping its slot'}): {why}")
                said, said_at = kind, time.monotonic()
            time.sleep(POLL_S)
    finally:
        if ticket:
            xemu_queue.drop_ticket(ticket)


def xemu_argv(w: Path, port: int, deterministic: bool = False, nice: bool = True, live_pads: bool = False) -> list[str]:
    """W's xemu under ``nice -n 10`` (EFFICIENCY M1: test suites and the
    owner's work keep the CPU first), its gdbstub on ``port``, its QMP
    socket and an HMP monitor (``HMP_SOCK``: its ``info status`` answers
    while an advance holds QMP, hazard 15; Step X.32) in W;
    ``deterministic``: ``ICOUNT_ARGS``; ``live_pads``: ``ICOUNT_LIVE_ARGS``
    (a demo as played, Step X.32b). ``nice=False``: an
    owner demo's (Step X.34), at normal priority, as the owner plays it in
    real time (sitting x32: at load 65 under nice 10 the play lagged). nice
    and nohup exec, so ``ps`` shows the app's own command line, which
    ``_SANDBOX_APP`` and ``alive()`` match."""
    return [*(("nice", "-n", "10") if nice else ()), "nohup", str(w / "xemu.app/Contents/MacOS/xemu"),
            "-config_path", str(w / "xemu.toml"), "-gdb", f"tcp:127.0.0.1:{port}",
            "-qmp", f"unix:{w}/qmp.sock,server,nowait", "-monitor", f"unix:{w}/{HMP_SOCK},server,nowait",
            *(ICOUNT_ARGS if deterministic else ICOUNT_LIVE_ARGS if live_pads else ())]


# Guest RAM sizes (Step X.60; the fork read at v0.16-40, 3decd4eef2). xemu sizes guest RAM by -m, which wins, else
# by the config's [sys] mem_limit, an enum: '64' and '128' (v0.16 and older), '256' and '512' too (experimental) from
# 5f105ce472 on, in v0.16.1 (system/vl.c, config_spec.yml); any other value is an error line and the default '64'.
# NV2A BAR1 aliases guest RAM, up to 128 MiB (hw/xbox/nv2a/nv2a.c nv2a_init_memory), and pci_register_bar asserts a
# power-of-two BAR (hw/pci/pci.c:1494): at or below 128 MiB a size that isn't one aborts xemu at start (SIGABRT from
# nv2a_init, as the xemu fork's own -m 192 probe on v0.16 did; no sandbox of ours has). Below 64 MiB the flash's
# kernel (built for 64 MiB) can't run. Above
# 128 MiB a build with BIG_RAM_MARK takes a multiple of 16 MiB up to BIG_RAM_MAX_MIB (hw/xbox/xbox.c; else it
# exits 1); an older one (v0.16, the kept build) aborts at 192 and leaves BAR1 unmapped at 256 and 512.
RAM_MIB = (64, 128)
BIG_RAM_MARK = b"guest RAM above 128 MiB must be a multiple of 16 MiB"
BIG_RAM_MAX_MIB = 3840   # XBOX_RAM_SIZE_MAX, 0xF0000000: RAM ends below BAR1
# v0.16.2 (the fork's 74a27096ed; its PART-12 answer and addendum, D599): the NV2A's DMA address mask (every DMA
# object's base, the PCRTC start, NV062's offsets, the surface base checks) is 28 bits whenever guest RAM is 256 MiB or
# more and 27 below, latched at init, and its init line says so (1eecc99e56's opt-in XEMU_NV2A_WIDE was never released
# and is gone). Earlier builds are 27 bits at every size: there a DMA base above 128 MiB wraps (textures, vertices,
# the push buffer) or aborts xemu as a render target (vk/surface.c). On every build an offset keeps the hardware's
# field width (a report's is 24 bits: a base-0 report object reaches only the first 16 MiB) and an offset past its DMA
# object's limit aborts xemu, release builds too (texture.c, vk/vertex.c, vk/surface.c). No savestate change: a
# state's RAM size fixes the mask. pfb_init prints _BIG_RAM_LINE above 128 MiB (v0.16.1 on).
NV2A_WIDE_MARK = b"NV2A wide addressing: 28 bits"
_BIG_RAM_LINE = re.compile(r"(?m)^xemu: guest RAM (\d+) MiB \(experimental above 128 MiB\)")


def nv2a_bits(log_text: str) -> tuple[int | None, int]:
    """A launch's guest RAM above 128 MiB from its run log (None at or below 128) and the NV2A's DMA address bits it
    runs with: 28 where the log has v0.16.2's wide line (``NV2A_WIDE_MARK``), else 27 (Step X.66)."""
    m = _BIG_RAM_LINE.search(log_text)
    return (int(m[1]) if m else None), (28 if NV2A_WIDE_MARK.decode() in log_text else 27)


def _ram_mib_refusal(mib: int, big: bool) -> str | None:
    """Why xemu can't run a guest of ``mib`` MiB (``ram_refusal``); None: it can."""
    if mib in RAM_MIB or (big and 128 < mib <= BIG_RAM_MAX_MIB and mib % 16 == 0):
        return None
    if mib < 64:
        return "below 64 MiB: the flash's kernel is built for 64 MiB"
    if mib < 128:
        return ("not a power of two: NV2A BAR1 aliases all guest RAM and pci_register_bar asserts a power-of-two "
                "BAR, so xemu aborts at start (SIGABRT from nv2a_init)")
    if big:
        return f"above 128 MiB this build takes a multiple of 16 MiB, {BIG_RAM_MAX_MIB} MiB at most"
    return ("above 128 MiB: this build has no RAM past 128 MiB (the fork's 5f105ce472, in v0.16.1): a size that "
            "isn't a power of two aborts it on pci_register_bar's assert, and 256 or 512 leaves BAR1 unmapped")


def ram_refusal(argv: list[str], tomls: list[str], big: bool) -> str | None:
    """Why a launch's guest RAM size is one xemu aborts on or doesn't run, by name and with its reason: each ``-m``
    in ``argv`` and each config's ``[sys] mem_limit`` (``tomls``, the sandbox's xemu.toml texts) checked against
    what the build takes (``big``: it has ``BIG_RAM_MARK``); None: 64 or 128 MiB, or a size above 128 the build
    takes (Step X.60)."""
    whys = []
    for i, a in enumerate(argv):
        if a == "-m":
            v = argv[i + 1] if i + 1 < len(argv) else ""
            m = re.fullmatch(r"(?:size=)?(\d+)([MG]?)(?:,.*)?", v, re.I)
            why = (_ram_mib_refusal(int(m[1]) << (10 if m[2].upper() == "G" else 0), big) if m
                   else "not a size in MiB the harness reads")
            if why:
                whys.append(f"-m {v}: {why}")
    names = ("64", "128", *(("256", "512") if big else ()))
    for t in tomls:
        v = (tomllib.loads(t).get("sys") or {}).get("mem_limit")
        if v is not None and v not in names:
            whys.append(f"[sys] mem_limit {v!r}: not one of this build's values ({', '.join(map(repr, names))}), "
                        "so xemu ignores it and runs its default 64 MiB")
    return "; ".join(dict.fromkeys(whys)) or None


# XEMU_HEADLESS's values in the fork build: offscreen (a hidden window, no Dock icon, no focus, no audio; the
# guest still renders), the null renderer (no window, no GPU work: logic, RAM and the gdbstub only), or "0":
# a visible window. Agent sandboxes run null and deterministic by default (Step X.22); a sitting that needs
# pictures asks for offscreen ("1", D184's old default; deterministic=True for reproducible ones, Step X.26),
# visual work that needs eyes for "0" (never deterministic).
HEADLESS = ("1", "null", "0")
DEFAULT_HEADLESS = "null"
# Deterministic mode (Step X.22): the fork build's -icount fast-forward (ed21e852cf). Guest time follows executed
# instructions, not the host clock, and runs as fast as the host allows (sleep=off; shift=2, about 60 fps on a
# heavy scene; v0.14-27 about 89); with the null renderer the same state, the same input and the same QMP and
# gdbstub calls give bit-identical guest RAM, in any process. -S: nothing runs before the first loadvm (each load
# starts the host's device state afresh). Since v0.14-27 (fa860ee510) offscreen Vulkan under icount is
# deterministic too, screendumps taken paused included, at about a third of the null renderer's speed: a sitting
# asks for it (headless "1", deterministic=True). A window never is.
ICOUNT_ARGS = ("-S", "-icount", "shift=2,align=off,sleep=off")
# Demos as played (v0.15; AZ-475, Step X.32b): with XEMU_ICOUNT_LIVE_PADS=1 and -icount align=on,sleep=on host gamepads
# (and the host keyboard on the keyboard pad) drive their ports as in real time, read once a vblank where pipe lines
# apply, so the run stays deterministic and XEMU_INPUT_RECORD holds exactly the input the guest got: the recording's
# section, replayed after a load of the same state in a deterministic sandbox, ends on the session's RAM, tick for
# tick. A scene the host can't run at full speed plays slower (stderr says by how much). Nothing is plugged or
# unplugged meanwhile: the owner's gamepad takes a port that has a pad by QMP xemu-input-bind (applied at a vblank;
# a gamepad not open yet is waited for), and the pad stays across loads with no replug.
ICOUNT_LIVE_ARGS = ("-S", "-icount", "shift=2,align=on,sleep=on")
LIVE_PADS_MARK = b"XEMU_ICOUNT_LIVE_PADS"
# XEMU_LOADVM_ADD_PADS=1 (v0.15): a load that stops at a pad hub or pad the machine lacks plugs it (no host source)
# and loads again, the result a load with the pad already there; set in every sandbox whose build has it, so a demo's
# state loads in a replay sandbox whatever pads it holds (the harness's own plugging, _pads, stays before it).
ADD_PADS_MARK = b"XEMU_LOADVM_ADD_PADS"
DETERMINISTIC_MARK = b"applied at the next vblank"   # in a build with the mode: its warning for a late @N pipe line
OFFSCREEN_DETERMINISTIC_MARK = b"only the null and Vulkan renderers are deterministic"   # v0.14-27's renderer note
# Since v0.14-36 (daf8bd8017) a state saved under icount carries the host-side state a later run depends on (the
# resampler, filter and HRTF history, the APU schedule, AC'97, the RTC's sub-second phase, the field pin, the pad
# reports and the keys and axes the pipe holds), so a run continued past a savevm is the run every load of it gives:
# the checkpoint needs no reload (Step X.30). A state saved without icount starts that state fresh, as before.
CONTINUITY_MARK = b"mcpx-apu/history"   # the APU's new vmstate subsection
# Since v0.14-36 (b382fd3cef) QMP xemu-checkpoint-save / -restore / -delete keep whole-machine states in host memory:
# a restore is a loadvm (the disk sectors the guest wrote since put back) that never touches the qcow2.
CHECKPOINT_MARK = b"xemu-checkpoint-save"
CHECKPOINTS_KEPT = 8   # in-memory checkpoints a sandbox keeps (each about 70 MiB of host memory): the oldest goes first
# Step X.96's standing rule (the xemu fork session's, D894): a finding that points at xemu goes to the fork session at
# once with the state, the call sequence and the counts. A verified restore that missed pages on a build with AZ-822's
# fix drafts its request into FORK_REQUESTS (a date's folder in the evidence archive, for the orchestrator to relay)
# from the last CALLS_KEPT guest-touching harness calls (_note_call: QMP and HMP commands by name, their frame counts
# and checkpoint names, the gdbstub's memory writes counted; never an argument's data).
FORK_REQUESTS = Path(os.environ.get("EV") or _COMMON_GIT.parent.parent / "evidence")   # $EV, beside the main
#                  checkout; + xemu-fork-requests-<date>/ (fork_requests_dir)
CALLS_KEPT = 256
_CALL_ARGS = ("frames", "name", "timeout-ms", "incremental", "verify", "device", "flips", "every", "count")
# Since v0.15 (PROMPT-8 round 4) xemu-checkpoint-restore {"incremental": true} writes back only the pages written since
# the last checkpoint save or restore (QEMU's migration dirty log), in 4.5-5.8 ms against loadvm's 25.5 (Step X.32b:
# loadvm keeps each tag's load as a checkpoint, LOAD_CHECKPOINT). Nothing here writes through XEMU_RAM_SHM
# (Sandbox._ram and ram_sha256, the demo recorder and its replug watcher only read that memory, Live a read-only view),
# yet the log misses writes: sitting 2.172f's restore after a pilot's retreat left 132 pages of the run after the
# start, the start check passing, and the guest bugchecked (AZ-821), so every restore asks "verify" too (every other
# page compared, those that differed written back and counted in "pages-missed"). Its replies carry "pages-copied".
INCREMENTAL_MARK = b"pages-copied"
# AZ-822 (the fork's 39d8f4e002, in 0.16.4-3-g95e7ffc7ec, Step X.94): the log missed those writes because HMP savevm's
# migration dirty sync (every park's) took the log's bits without re-arming the store traps, so a verified restore on
# a build with the fix finds none: checkpoint_restore counts each restore's "pages-missed" (st["restores"], down's and
# the kit report's) and names a nonzero there a fork bug to report. The fix has no mark of its own; the fork's
# timeout-ms (95e7ffc7ec, TIMEOUT_MARK), which came after it, stands for it.
DIRTY_LOG_FIX_MARK = b"timeout-ms"
LOAD_CHECKPOINT = "load-{}"   # the checkpoint a loadvm of a tag keeps of its load (the VM stopped, nothing run yet)
# D200's guard, its rule since Step X.32b: v0.14-36's repeated loadvm in one deterministic offscreen Vulkan process
# diverged about 1 time in 7 (the fork, 2026-10-15); v0.15 fixed icount loads (PROMPT-7 E(1), 0372addc87: the virtual
# clock after a stop), and XEMU_LOAD_VERIFY came with that fix. Seven loads in one such process ended on one RAM in
# sittings x32 (v0.15) and x40 (v0.15.1), so the guard warns only on a build without the mark.
LOAD_FIX_MARK = b"XEMU_LOAD_VERIFY"
# QMP xemu-ram-digest (v0.15, PROMPT-7 E(3), round 4): guest RAM's sha256 (xemu-dump-ram's file's) with no file, or with
# {"algorithm": "xxh3-128"} its XXH3-128 (32 hex digits, about 4 ms for 128 MiB against sha256's 55): ram_digest.
DIGEST_MARK = b"xxh3-128"
# Since v0.14-36 xemu-frame-advance starts a VM the gdbstub stopped from that very instruction (a breakpoint under the
# PC lifted first) and reports a breakpoint that ends it early as "debug-stop": frame counts from a parked start.
DEBUG_ADVANCE_MARK = b"debug-stop"
# Since the fork's 29a024b18e (after v0.14-36, in v0.15; PROMPT-8 D, Step X.37) xemu-frame-advance (and xemu-run-until
# and xemu-run, which run on it) also ends early on any other VM stop it didn't make, the VM left as that stop left
# it, and its reply's "stopped" names the run state (its "frame" is then where it stopped). v0.14-36 waits through
# any such stop forever, holding QMP: a new client gets no greeting, then ECONNREFUSED, and SIGTERM never ends xemu
# (AZ-451's wedge). frame_advance names the stop; any but a breakpoint's raises AdvanceStopped.
ADVANCE_STOPS = {"paused": "a gdbstub client attached, sent ^C or a stray byte", "debug": "a gdbstub breakpoint",
                 "shutdown": "SIGTERM: xemu exits", "restore-vm": "a failed loadvm", "io-error": "a disk I/O error"}
ADVANCE_S = 600.0   # how long an xemu-frame-advance's reply may take (a build without the watch monitor)
# With the watch monitor (QMP_WATCH_MARK, AZ-685) a long command's reply is waited for in LIVE_SLICE_S slices, the watch
# asked for the frame between them: it is hung only once no frame moved for STALL_S (sitting X.59: a background
# sandbox at load 104-119 ran 600 frames in 203 s, so a long advance outran ADVANCE_S with its guest alive), and never
# waited for past LONG_CAP_S.
LIVE_SLICE_S, STALL_S, LONG_CAP_S = 5.0, 120.0, 4 * 3600.0
PIPE_WINDOW = 8192  # bytes play_recording writes into the input pipe between advances (a macOS pipe holds 16 KiB
                    # until its reader takes it, and a paused xemu reads nothing: AZ-539)
LONG_QMP = ("xemu-frame-advance", "xemu-run-until", XEMU_RUN, "xemu-render-next")   # they run the VM before they reply
# 0.16.4-3-g95e7ffc7ec (the fork's 95e7ffc7ec, Step X.94): xemu-frame-advance, xemu-run-until and xemu-run take
# "timeout-ms": one still short of its frame after that many host milliseconds pauses the VM wherever it is and replies
# "timed-out": true (the runs: reason "timeout"), so a stalled advance comes back and QMP is free again. That pause is
# at a host-time point, not a deterministic one, so a deterministic sandbox runs no further advance or run from it
# until a checkpoint restore or a load (_refuse_after_timeout). Each advance and run asks advance_bound_s(its frames):
# STALL_S plus FRAME_BOUND_S a vblank, at most LONG_CAP_S (sitting X.59's background sandbox at load 104-119 took
# 0.34 s a vblank). While the watch answers, _long_qmp waits for that reply even when no frame moves (a guest
# looping inside a frame: sitting s94's t03b); a deadlock that holds the BQL, which timeout-ms can't end, leaves the
# watch mute, and the watch's stall still raises for it.
TIMEOUT_MARK = b"timeout-ms"
FRAME_BOUND_S = 1.0


def advance_bound_s(frames: int) -> float:
    """The host seconds an advance or run of ``frames`` vblanks may take before xemu pauses it (``TIMEOUT_MARK``)."""
    return min(LONG_CAP_S, STALL_S + max(1, int(frames)) * FRAME_BOUND_S)


_QMP_HELD: dict[str, list] = {}   # W -> [its lock, the QMP connection a deterministic sandbox keeps] (Step X.32b)


HMP_SOCK = "hmp.sock"   # W's HMP monitor (xemu_argv), apart from QMP: it answers while an advance holds QMP
QMP_TURN = "qmp.turn"   # W's QMP turn (AZ-644): a flock the serve holds per request and a demo's watchers per pass
_TURNS_HELD: dict[str, int] = {}   # W -> how deep this process holds its turn through qmp_turn (it nests)


class QmpTurn:
    """W's QMP turn (AZ-644): an exclusive ``flock`` on ``W/qmp.turn`` (W outlives a relaunch). QMP serves one client
    (listen backlog 1: a second waits ungreeted, a third is refused), and a real-time sandbox connects per command, so
    the kit's serve takes the turn for each request (``qmp_turn``) and a demo's watchers (the recorder, replug) try it
    once a pass with no wait (``take``) and drop it before their sleep: a boot's, tag's or load's QMP never meets
    theirs (2.147's AE load met "refused" on its first try), and their stop and cont never fall between the harness's
    own stop and its load. ``mine``: whether it is held. One descriptor, kept open."""

    def __init__(self, w: Path | str):
        self.path, self.fd, self.mine = Path(w) / QMP_TURN, None, False

    def take(self, block: bool = False, wait_s: float = 0.0) -> bool:
        """The turn: at once (``block`` False: polled every 50 ms for ``wait_s``) or waiting; whether it is held."""
        if self.mine:
            return True
        import fcntl

        if self.fd is None:
            self.fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        end = time.monotonic() + wait_s
        while True:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_EX if block else fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.mine = True
                return True
            except BlockingIOError:
                if time.monotonic() >= end:
                    return False
                time.sleep(0.05)

    def drop(self) -> None:
        import fcntl

        if self.mine:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            self.mine = False

    def close(self) -> None:
        self.drop()
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


@contextlib.contextmanager
def qmp_turn(w: Path | str, block: bool = True):
    """W's QMP turn for one stretch of this process's QMP (``QmpTurn``; the kit's serve, per request), yielding
    whether it is held: ``block`` waits for a watcher's current exchange (about 0.25 s at most), else it is tried
    once. Nested in this process it is the outer one's."""
    key = str(Path(w).resolve())
    if _TURNS_HELD.get(key):
        _TURNS_HELD[key] += 1
        try:
            yield True
        finally:
            _TURNS_HELD[key] -= 1
        return
    t = QmpTurn(w)
    try:
        got = t.take(block)
        if got:
            _TURNS_HELD[key] = 1
        yield got
    finally:
        if t.mine:
            _TURNS_HELD.pop(key, None)
        t.close()


def hmp_command(sock: Path, line: str, timeout: float = 5.0) -> str:
    """One HMP command on a ``-monitor unix:`` socket (W's ``HMP_SOCK``): its reply text, the banner and prompts
    dropped. An HMP command doesn't stop the VM."""
    def prompt(s: socket.socket) -> bytes:   # what comes up to the next "(qemu) " prompt
        buf = b""
        while not buf.endswith(b"(qemu) ") and (chunk := s.recv(4096)):
            buf += chunk
        return buf
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(str(sock))
        prompt(s)   # the banner
        s.sendall(line.encode() + b"\n")
        buf = prompt(s)
    text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", buf.decode(errors="replace")).replace("\r", "").splitlines()
    echo = next((i for i, ln in enumerate(text) if ln.rstrip().endswith(line)), -1)   # readline redraws as it echoes
    return "\n".join(ln for ln in text[echo + 1:] if ln.strip() and ln.strip() != "(qemu)").strip()


def hang_probe(pid: int, dest: Path, run=subprocess.run) -> Path:
    """A held xemu's evidence (AZ-451; PROMPT-8 D's recipe), to take before anything touches it (a gdbstub attach,
    a QMP call, a signal): ``sample <pid> 5`` first, into ``dest``'s ``hang-<pid>-<time>.sample.txt``, then ``ps``
    (state, %CPU), ``lsof -p`` and, when ``dest`` holds W's ``HMP_SOCK`` (Step X.32), HMP ``info status`` into
    ``hang-<pid>-<time>.txt`` beside it. Returns the sample's path."""
    stem = dest / f"hang-{pid}-{time.strftime('%H%M%S')}"
    sample = Path(f"{stem}.sample.txt")
    with open(f"{stem}.txt", "w", encoding="utf-8") as f:
        for argv in (["sample", str(pid), "5", "-file", str(sample)],
                     ["ps", "-o", "pid=,stat=,%cpu=,etime=,command=", "-p", str(pid)], ["lsof", "-p", str(pid)]):
            try:
                r = run(argv, capture_output=True, text=True, timeout=60, check=False)
                f.write(f"$ {' '.join(argv)}\n{r.stdout}{r.stderr}\n")
            except (OSError, subprocess.SubprocessError) as e:
                f.write(f"$ {' '.join(argv)}\nfailed: {e}\n")
        if (dest / HMP_SOCK).exists():
            try:
                f.write(f"$ hmp info status\n{hmp_command(dest / HMP_SOCK, 'info status')}\n")
            except OSError as e:
                f.write(f"$ hmp info status\nfailed: {e!r}\n")
    return sample


def deterministic_mode(binary: bytes, headless: str, asked: bool | None, name: str = "this build") -> bool:
    """Whether a launch runs deterministic (``ICOUNT_ARGS``): with the null renderer unless ``asked`` is False, on a
    build that has the mode; offscreen only when ``asked`` (Step X.26), on a build whose Vulkan path has it
    (v0.14-27); a window never. Asked of a build without it: refused."""
    can = DETERMINISTIC_MARK in binary and (headless != "1" or OFFSCREEN_DETERMINISTIC_MARK in binary)
    if asked and (headless == "0" or not can):
        raise SystemExit(f"{name} has no deterministic {'window' if headless == '0' else 'mode'} (-icount"
                         f"{', offscreen Vulkan' if headless == '1' else ''}): use the fork build, the null renderer "
                         "or offscreen, or deterministic=False")
    return can and (asked is not False if headless == "null" else bool(asked) and headless == "1")


def app_path(app: Path | str | None) -> Path:
    """The ``xemu.app`` a sandbox clones: ``FORK_APP`` by default (or "fork"), ``KEPT_APP`` for "kept" (the
    build that made the D98 states, the fallback), else the bundle named."""
    return {None: FORK_APP, "fork": FORK_APP, "kept": KEPT_APP}.get(app, None) or Path(app).expanduser()


# What a sandbox's xemu never inherits from the shell that launched it: the variables xemu_env sets for W, and the
# others v0.15's launchers drop too (PROMPT-8 A, Step X.32): traces, block, voice and audio logs that write files
# outside W, and live pads under icount, which would change a deterministic run; and v0.16.1's (Step X.61): its
# monitors and backlog, the bugcheck report, the renderer's RAM mode, the language, a smaller RAM's loads, the
# old reset, OHCI and render-pass orders, the AGP decode, CSTATUS and the present bound; and v0.16.3's (Step X.71):
# the PFIFO thread's per-command locking and the vblank thread's old wait, which change a real-time run's frame rate;
# and v0.16.4's (Step X.72): the PFIFO thread's unfused commands (XEMU_PFIFO_FUSE=0), which does too.
NOT_INHERITED = ("XEMU_INPUT_RECORD", "XEMU_INPUT_RECORD_PORT", "XEMU_RAM_SHM", "XEMU_BASE_PATH", "XEMU_TRACE_RECORD",
                 "XEMU_TRACE_REGIONS", "XEMU_BLOCK_LOG", "XEMU_VOICE_LOG", "XEMU_AUDIO_WAV", "XEMU_ICOUNT_LIVE_PADS",
                 "XEMU_LOADVM_ADD_PADS", "XEMU_STRICT_CPUID", "XEMU_QMP_WATCH", "XEMU_SOCKET_BACKLOG",
                 "XEMU_GUEST_BUGCHECK", "XEMU_RENDER_NULL_RAM", "XEMU_LANGUAGE", "XEMU_LOADVM_SHRINK_RAM",
                 "XEMU_NV2A_RESET_IRQ", "XEMU_OHCI_HCCA_FIRST", "XEMU_AGP_FULL_DECODE", "XEMU_CSTATUS_FULL_RAM",
                 "XEMU_PRESENT_STALL_MS", "XEMU_VK_CLEAR_IN_PASS", "XEMU_PFIFO_LOCK_BATCH", "XEMU_VBLANK_KQUEUE",
                 "XEMU_PFIFO_FUSE")


def xemu_env(w: Path, headless: str | None = None, record: int | None = None,
             ram_shm: str | None = None, base: str | None = None, live_pads: bool = False,
             add_pads: bool = False, strict_cpuid: bool = False, watch: bool = False, backlog: bool = False,
             bugcheck: bool = False, null_ram: bool = False, legacy_reset: bool = False) -> dict[str, str]:
    """xemu's environment: the input FIFO (``XEMU_INPUT_PIPE``) and ``XEMU_HEADLESS`` (default
    ``DEFAULT_HEADLESS``; "0" a window; a build without the mode ignores it and opens its window); with ``record``
    (a port, 1-4) the fork's input recorder (v0.14-36, Step X.30) writes that pad's input into ``W/INPUT_RECORD``;
    with ``ram_shm`` guest RAM is that named shared memory (``XEMU_RAM_SHM``, ``ram_shm_name``); with ``base``
    xemu's data folder (``XEMU_BASE_PATH``: its shader and pipeline caches) is that folder in W; ``live_pads``:
    ``XEMU_ICOUNT_LIVE_PADS=1`` (Step X.32b); ``add_pads``: ``XEMU_LOADVM_ADD_PADS=1``; ``strict_cpuid``:
    ``XEMU_STRICT_CPUID=1`` (Step X.58); ``watch``: the QMP watch monitor on ``W/WATCH_SOCK``; ``backlog``:
    ``XEMU_SOCKET_BACKLOG=BACKLOG``; ``bugcheck``: ``XEMU_GUEST_BUGCHECK=1`` (Step X.61); ``null_ram``:
    ``XEMU_RENDER_NULL_RAM=request``; ``legacy_reset``: ``XEMU_NV2A_RESET_IRQ=0`` (v0.16's reset, for an older
    recording that crosses one). Those variables are never inherited, nor are the fork's other run-changing ones
    (``NOT_INHERITED``)."""
    headless = headless or DEFAULT_HEADLESS
    if headless not in HEADLESS:
        raise SystemExit(f"headless {headless!r}: one of {', '.join(HEADLESS)} (1 offscreen, null no rendering, "
                         "0 a window)")
    env = {**os.environ, "XEMU_INPUT_PIPE": str(w / "input.fifo"), "XEMU_HEADLESS": headless}
    for k in NOT_INHERITED:
        env.pop(k, None)
    if record:
        env.update(XEMU_INPUT_RECORD=str(w / INPUT_RECORD), XEMU_INPUT_RECORD_PORT=str(int(record)))
    if ram_shm:
        env["XEMU_RAM_SHM"] = ram_shm
    if base:
        env["XEMU_BASE_PATH"] = base
    if live_pads:
        env["XEMU_ICOUNT_LIVE_PADS"] = "1"
    if add_pads:
        env["XEMU_LOADVM_ADD_PADS"] = "1"
    if strict_cpuid:
        env["XEMU_STRICT_CPUID"] = "1"
    if watch:
        env["XEMU_QMP_WATCH"] = f"unix:{w / WATCH_SOCK},server=on,wait=off"
    if backlog:
        env["XEMU_SOCKET_BACKLOG"] = str(BACKLOG)
    if bugcheck:
        env["XEMU_GUEST_BUGCHECK"] = "1"
    if null_ram:
        env["XEMU_RENDER_NULL_RAM"] = "request"
    if legacy_reset:
        env["XEMU_NV2A_RESET_IRQ"] = "0"
    return env


# XEMU_BASE_PATH=<dir> (the fork's 0babe23fbc, after v0.14-36; PROMPT-7 A(4), Step X.33) moves xemu's data folder
# (spirv_cache_v*/ and pipeline_cache.bin; xemu.toml and eeprom.bin too, but the sandbox names both) to <dir>, ahead
# of portable mode, and logs "base path: <dir>/". A sandbox on a build that has it (the fork's own check: the name in
# the binary) points it at W/DATA_DIR, so the caches stay in W however portable mode fares; on one without it
# portable mode keeps them in the cloned app's Contents/Resources, as before.
BASE_PATH_MARK = b"XEMU_BASE_PATH"
DATA_DIR = "xemu-data"


def base_path_for(w: Path, binary: bytes) -> str | None:
    """A sandbox's ``XEMU_BASE_PATH`` (``st["base_path"]``): W/DATA_DIR on a build whose binary holds the name,
    else None (portable mode: v0.14-36)."""
    return str(w / DATA_DIR) if BASE_PATH_MARK in binary else None


# A warm shader cache for windowed sandboxes (Step X.69; the fork's answer on FRAME-8bffffeb0243, the fire-armor cast
# hitch): W's data folder starts empty, so an owner demo compiled every shader and pipeline it met (x67demo: 679
# variants; the first armor casts 1.9-2.3 s of compiling a cast cold, 45-190 ms warm). A windowed sandbox (an owner
# demo, or a window an agent watches: real time only) starts instead from a folder kept per build, SHADER_CACHE/<the
# binary's sha256[:12]>, seeded once from the fork's bench cache (FORK_BENCH, read only) with only the files that build
# reads (cache_reads), cloned (cp -c) into W's data folder before its launch, its new and changed files cloned back
# at its down. The cache is W's own copy, so the sources and their baselines don't change. Null and offscreen
# sandboxes, deterministic or real time (the rate pairs too), keep an empty data folder.
SHADER_CACHE = Path(user_cache_dir("AzurKit")) / "xemu-shader-cache"
FORK_BENCH = Path.home() / "Library/Caches/xemu-fork-bench"
_PREWARM_FILE = re.compile(r"vk_prewarm-[A-Za-z0-9_]+-[0-9a-f]{16}\.bin")
# A prewarm list the fork set aside (v0.16.3's check_dead_workers, prewarm.c): a launch that died rebuilding its
# pipelines leaves <name>.<pid>.running, and the next launch renames <name> to <name>.bad
_PREWARM_ASIDE = re.compile(rf"({_PREWARM_FILE.pattern})\.(?:bad|\d+\.running)")


def warms_shader_cache(headless: str, base_path: str | None) -> bool:
    """Whether a sandbox starts from its build's kept shader cache: only a window (headless "0") on a build with
    ``XEMU_BASE_PATH``; null and offscreen sandboxes (the rate pairs too) keep an empty base."""
    return headless == "0" and bool(base_path)


def cache_reads(binary: bytes, version: str | None) -> dict:
    """The cache files a build reads in its data folder, by the names in its binary: the pipeline caches (MoltenVK's
    ``pipeline_cache.bin``, KosmicKrisp's ``pipeline_cache-kosmickrisp.bin``), v0.16.3's prewarm lists
    (``vk_prewarm-<driver>-<schema>.bin``) and its own version's SPIR-V folders (``spirv_cache_v<M.m.p>-*``, the
    version the app is named for; none where it isn't known)."""
    key = xemu_version_key(version)
    return {"files": [n for n in ("pipeline_cache.bin", "pipeline_cache-kosmickrisp.bin")
                      if b"%s" + n.encode() in binary],
            "prewarm": b"vk_prewarm-%s-" in binary,
            "spirv": "spirv_cache_v%d.%d.%d-" % key if key and b"spirv_cache_v%d.%d.%d-" in binary else None}


def cache_files(root: Path, reads: dict) -> dict[str, tuple[int, int]]:
    """The files ``reads`` names under ``root``: {relative path: (size, mtime_ns)}; never a temp file, a prewarm
    marker or anything else xemu keeps there."""
    out: dict[str, tuple[int, int]] = {}
    for p in sorted(root.iterdir()) if root.is_dir() else ():
        n = p.name
        if p.is_file() and (n in reads["files"] or (reads["prewarm"] and _PREWARM_FILE.fullmatch(n))):
            st = p.stat()
            out[n] = (st.st_size, st.st_mtime_ns)
        elif p.is_dir() and reads["spirv"] and n.startswith(reads["spirv"]):
            for f in sorted(p.iterdir()):
                if f.is_file() and not f.name.endswith(".tmp"):
                    st = f.stat()
                    out[f"{n}/{f.name}"] = (st.st_size, st.st_mtime_ns)
    return out


def _clone_files(src: Path, dst: Path, rels: list[str]) -> int:
    """Clone ``rels`` from ``src`` into ``dst`` (``cp -c``: APFS clones, times kept), each folder's files in one call
    into a staging folder beside them and renamed into place, so no reader sees half a file. Returns their bytes."""
    by_dir: dict[str, list[str]] = collections.defaultdict(list)
    for rel in rels:
        by_dir[str(Path(rel).parent)].append(rel)
    total = 0
    for parent, group in by_dir.items():
        (dst / parent).mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".azx-stage.", dir=dst / parent))
        try:
            subprocess.run(["cp", "-c", *[str(src / r) for r in group], str(stage)], check=True, capture_output=True)
            for rel in group:
                total += (stage / Path(rel).name).stat().st_size
                os.replace(stage / Path(rel).name, dst / rel)
        finally:
            shutil.rmtree(stage, ignore_errors=True)
    return total


@contextlib.contextmanager
def _cache_lock(sha12: str):
    import fcntl

    SHADER_CACHE.mkdir(parents=True, exist_ok=True)
    with (SHADER_CACHE / f"{sha12}.lock").open("a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


def warm_shader_cache(base: Path, binary: bytes, version: str | None) -> dict:
    """Clone the build's kept shader cache into ``base`` (a sandbox's data folder) before its launch, seeding the
    kept folder from ``FORK_BENCH`` first if this build's never was (``seeded.json``). Returns ``st["shader_cache"]``:
    the kept folder, what the build reads, and the files and bytes cloned in (``seeded``: this call's seed)."""
    sha12 = hashlib.sha256(binary).hexdigest()[:12]
    keep, reads = SHADER_CACHE / sha12, cache_reads(binary, version)
    res: dict = {"dir": str(keep), "sha12": sha12, "reads": reads}
    with _cache_lock(sha12):
        if not (keep / "seeded.json").exists():
            have = cache_files(FORK_BENCH, reads)
            keep.mkdir(parents=True, exist_ok=True)
            res["seeded"] = {"from": str(FORK_BENCH), "files": len(have),
                             "bytes": _clone_files(FORK_BENCH, keep, list(have))}
            (keep / "seeded.json").write_text(json.dumps({**res["seeded"], "at": now()}), encoding="utf-8")
        have = cache_files(keep, reads)
        res.update(files=len(have), bytes=_clone_files(keep, base, list(have)))
    return res


def keep_shader_cache(base: Path, cache: dict) -> dict:
    """At a sandbox's down: clone the cache files its xemu wrote or changed in ``base`` back into the build's kept
    folder (``cache``: ``warm_shader_cache``'s), and drop from it a prewarm list the fork set aside in ``base``
    (``_PREWARM_ASIDE``), so no later window gets it again. Returns the files and bytes kept (``set_aside``: those
    dropped)."""
    keep = Path(cache["dir"])
    aside = sorted({m[1] for p in base.iterdir() if (m := _PREWARM_ASIDE.fullmatch(p.name))}) if base.is_dir() else []
    with _cache_lock(cache["sha12"]):
        old = cache_files(keep, cache["reads"])
        new = [rel for rel, v in cache_files(base, cache["reads"]).items() if old.get(rel) != v and rel not in aside]
        for name in aside:
            (keep / name).unlink(missing_ok=True)
        return {"files": len(new), "bytes": _clone_files(base, keep, new), **({"set_aside": aside} if aside else {})}


# XEMU_STRICT_CPUID=1 (v0.16, the fork's 2b17215fb7): an instruction the Xbox's Pentium III lacks (SSE2, SSE3's FISTTP
# and LFENCE, by prefix) raises #UD as on the console, logged "xemu: strict CPUID: #UD at <pc>: <opcode> needs <feature>"
# and sent as QMP XEMU_CPUID_FAULT (the first 32 per launch; the kernel's handler then usually bugchecks); without it
# TCG runs them (the skill's hazard 3, AZ-021). Retail Azurik and its cold boot never trip it, and the fork's
# deterministic goldens match with it on (its README). Every sandbox on a build that has it sets it (Step X.58), so a
# build whose shim needs SSE2 faults in xemu as on the console, and boot_build refuses it by name (CpuidFault).
STRICT_CPUID_MARK = b"XEMU_STRICT_CPUID"
_CPUID_FAULT = re.compile(r"(?m)^xemu: strict CPUID: #UD at ([0-9a-fA-F]+): [0-9A-F ]+ needs (MMX|SSE2|SSE3|SSE)\b")


def cpuid_faults(log_text: str) -> list[dict]:
    """The strict-CPUID faults a run log names (``STRICT_CPUID_MARK``): ``[{pc, feature}]``, in order, the opcode
    bytes left out (they are the guest's code)."""
    return [{"pc": f"{int(pc, 16):#x}", "feature": feat} for pc, feat in _CPUID_FAULT.findall(log_text)]


# XEMU_GUEST_BUGCHECK=1 (v0.16.1, the fork's 68b474a36f): xemu hooks the 4627 kernel's KeBugCheckEx (export 96) and logs
# "xemu: guest bugcheck 0x<code> (<p1>, <p2>, <p3>, <p4>) from <ret>" per call, and "xemu: guest halted with interrupts
# disabled at <eip> (esp <esp>)" per HLT with IF clear (QMP XEMU_GUEST_BUGCHECK / XEMU_GUEST_HALTED; the first 16 of
# each per launch); RAM and goldens are unchanged with it on. Both end in the kernel's halt loop HALT_LOOP (cli; hlt;
# jmp 0x800151ED), KeBugCheckEx having stored its code and p1-p4 at BUGCHECK_DATA first (the double fault halts there
# with zeros), so a boot idle there names its cause by the line (AZ-628). V22, the fork's 858e2af19f (fixed in v0.16.1,
# real-time boots only): IRQL_NOT_LESS_OR_EQUAL 0xA at the XDK OHCI driver's done queue, p4 V22_P4.
BUGCHECK_MARK = b"XEMU_GUEST_BUGCHECK"
_BUGCHECK = re.compile(r"(?m)^xemu: guest (?:bugcheck 0x([0-9a-f]{8}) \(0x([0-9a-f]{8}), 0x([0-9a-f]{8}), "
                       r"0x([0-9a-f]{8}), 0x([0-9a-f]{8})\) from 0x([0-9a-f]{8})|halted with interrupts disabled at "
                       r"0x([0-9a-f]{8}) \(esp 0x([0-9a-f]{8})\))")
HALT_LOOP, BUGCHECK_DATA = 0x800151EF, 0x8003AB20
V22_P4 = (0x18D0FC, 0x18D0C0)
# 0.16.4-3-g95e7ffc7ec (the fork's ef33705322, Step X.94): each bugcheck line is followed by "xemu: guest bugcheck
# registers: eax=... eflags=... (stack: N bytes in the event)" (the registers at KeBugCheckEx's first instruction), and
# QMP XEMU_GUEST_BUGCHECK carries them with "regs" (EIP too: KeBugCheckEx) and "stack": up to 4 KiB of guest memory from
# that ESP, in hex, which holds a 0x1E's trap frame and context record (each where the faulting EIP, p2, is followed by
# CS 0x0008). The stack is guest data: scrub_event takes it out of every QMP message as it arrives, keeping only its
# length, its sha256[:12] and the trap frame's EIP decoded from it in memory (trap_frame), so no log, report, sandbox.json
# or commit ever holds it.
BUGCHECK_REGS_MARK = b"guest bugcheck registers"
_BUGCHECK_REGS = re.compile(r"(?m)^xemu: guest bugcheck registers: ((?:[a-z]+=[0-9a-f]{8} )+)\(stack: (\d+) bytes")
TRAP_CS = 0x0008   # the kernel's code segment, after the trap frame's (and the context record's) EIP


def trap_frame(stack: bytes, code: int, p2: int) -> dict:
    """The trap frame a bugcheck's stack holds (``scrub_event``; Step X.94), decoded in memory: ``trap_eip`` and
    ``trap_at``, the offsets from ESP of each EIP, CS 0x0008, EFLAGS triple (a trap frame's and a context record's:
    EFLAGS with its always-one bit 1 set and its reserved bits 3, 5, 15 and 22-31 clear), {} when none is. A 0x1E
    (KMODE_EXCEPTION_NOT_HANDLED) names its faulting EIP as p2, so only triples whose EIP is p2 count there."""
    n = len(stack) // 4
    words = struct.unpack(f"<{n}I", stack[:4 * n])
    at = [4 * i for i in range(n - 2) if words[i + 1] == TRAP_CS and words[i + 2] & 0x2
          and not words[i + 2] & 0xFFC08028 and words[i] and (code != 0x1E or words[i] == p2)]
    return {"trap_eip": hex(words[at[0] // 4]), "trap_at": [hex(a) for a in at]} if at else {}


def scrub_event(msg: dict) -> dict:
    """A QMP message as the harness keeps it (``QMP._message``; Step X.94): an ``XEMU_GUEST_BUGCHECK`` event's
    ``stack`` (guest memory) replaced by ``stack_bytes``, ``stack_sha12`` and ``trap_frame``'s fields; anything else
    as it came."""
    data = msg.get("data") if msg.get("event") == "XEMU_GUEST_BUGCHECK" else None
    if isinstance(data, dict) and isinstance(data.get("stack"), str):
        raw = bytes.fromhex(data.pop("stack"))
        params = data.get("params") or [0, 0]
        data.update(stack_bytes=len(raw), stack_sha12=hashlib.sha256(raw).hexdigest()[:12],
                    **trap_frame(raw, int(data.get("code", 0)), int(params[1]) if len(params) > 1 else 0))
    return msg


def bugchecks(log_text: str) -> list[dict]:
    """The guest bugchecks and dead halts a run log names (``BUGCHECK_MARK``), in order: ``{"kind": "bugcheck",
    "code", "params": [p1..p4], "ret", "v22"}`` (``v22``: code 0xA with p4 at the OHCI driver's done queue; on a
    build with ``BUGCHECK_REGS_MARK`` also ``regs``, the registers at KeBugCheckEx's entry by name, and
    ``stack_bytes``, what its QMP event carried) or ``{"kind": "halt", "eip", "esp"}``, as hex strings."""
    out: list[dict] = []
    for m in re.finditer(r"(?m)^xemu: guest .*$", log_text):
        if r := _BUGCHECK_REGS.match(m[0]):
            if out and out[-1]["kind"] == "bugcheck" and "regs" not in out[-1]:
                out[-1].update(regs={k: hex(int(v, 16)) for k, v in (kv.split("=") for kv in r[1].split())},
                               stack_bytes=int(r[2]))
        elif not (b := _BUGCHECK.match(m[0])):
            continue
        elif b[1]:
            code, params = int(b[1], 16), [int(p, 16) for p in b.groups()[1:5]]
            out.append({"kind": "bugcheck", "code": hex(code), "params": [hex(p) for p in params],
                        "ret": hex(int(b[6], 16)), "v22": code == 0xA and params[3] in V22_P4})
        else:
            out.append({"kind": "halt", "eip": hex(int(b[7], 16)), "esp": hex(int(b[8], 16))})
    return out


# v0.16.1 (188ff96260; PART-11 2.3, on by default): a windowed present waits at most XEMU_PRESENT_STALL_MS (100 ms) for a
# CAMetalLayer drawable, then drops frames and keeps polling input and serving screendumps, logging "xemu: present stall
# N: no drawable for M ms; ..." (QMP XEMU_PRESENT_STALL): the fixtures' frame interpolation '2x' no longer starves the
# UI thread (AZ-601's hang), so a window keeps it on such a build (scratch_toml's present_stall) and down keeps the
# stalls (st["present_stalls"]).
PRESENT_STALL_MARK = b"XEMU_PRESENT_STALL"
_PRESENT_STALL = re.compile(r"(?m)^xemu: present stall (\d+): no drawable for (\d+) ms")
_PRESENT_STALL_OVER = re.compile(r"(?m)^xemu: present stall (\d+) over after (\d+) ms")
# v0.16.1 (056c25b49f): a system_reset clears the NV2A's interrupt state as power-on does, so an icount run that crosses
# a reset (boot_build's reset_into) parts from v0.16's in its first frames after it; XEMU_NV2A_RESET_IRQ=0 restores
# v0.16's reset, for replaying a recording of a build before it whose section crosses one (Sandbox(legacy_reset=True);
# needs_legacy_reset). A load restores all of it, so sections that start from a load and cross no reset need nothing.
RESET_IRQ_MARK, RESET_IRQ_FROM = b"XEMU_NV2A_RESET_IRQ", (0, 16, 1)


def present_stalls(log_text: str) -> list[dict]:
    """The windowed present's stalls one run log names (``PRESENT_STALL_MARK``): ``[{"n", "ms"}]``, in order, ``ms``
    the stall's length from its "over after" line (its start line's is only the first wait, about the bound), or
    that first wait for a stall still open."""
    over = {int(n): int(ms) for n, ms in _PRESENT_STALL_OVER.findall(log_text)}
    return [{"n": int(n), "ms": over.get(int(n), int(ms))} for n, ms in _PRESENT_STALL.findall(log_text)]


def xemu_version_key(v: str | None) -> tuple[int, int, int] | None:
    """A logged ``xemu_version`` (``0.16.1``, ``0.16``, ``v0.13.3-37-gd5ad94f4bf``, ``0.16-48-gb44bb02f9b``) as
    (major, minor, patch), the commits past a tag left out; None for anything else."""
    m = re.match(r"v?(\d+)\.(\d+)(?:\.(\d+))?(?:-|$)", v or "")
    return (int(m[1]), int(m[2]), int(m[3] or 0)) if m else None


def needs_legacy_reset(recorded_on: str | None) -> bool:
    """Whether a recording made on the build that logged ``recorded_on`` (its sandbox's ``xemu_version``) replays
    across a ``system_reset`` only with v0.16's reset (``legacy_reset``): a build before v0.16.1."""
    k = xemu_version_key(recorded_on)
    return k is not None and k < RESET_IRQ_FROM


# Savestate streams (Steps X.61, X.66): a state loads in a build of its own stream or a later one. v0.16.1 made the
# NV2A's device section version 5, so its states don't load in v0.16 or the kept build; v0.16.2 changed nothing in
# the stream (its states and v0.16.1's load both ways at every RAM size: the fork's PART-12 addendum), nor did v0.16.3
# (no device section changed from v0.16.2's tag to its 7b9f1d6029; the fork's release notes: the 32 D98 states replay
# to v0.16.2's RAM) or v0.16.4 (no vmstate line changed from v0.16.3's tag to its 237d34f193; its notes: pack 03
# replays to the same RAM), nor its three commits to 0.16.4-3-g95e7ffc7ec (the fork session: goldens and RAM equal).
STATE_STREAMS = ((0, 16, 1),)   # each newer stream's first build


def state_stream(v: str | None) -> int | None:
    """The savestate stream of the build that logged ``v`` (an ``xemu_version``): how many of ``STATE_STREAMS`` it
    has reached; None for a version ``xemu_version_key`` can't read."""
    k = xemu_version_key(v)
    return None if k is None else sum(k >= s for s in STATE_STREAMS)


def bugcheck_list(items: list[dict]) -> str:
    """Guest bugchecks and halts (``bugchecks``) in a line, the first 4; a bugcheck's trap frame EIP and its
    KeBugCheckEx registers where they were read (Step X.94)."""
    def regs(b: dict) -> str:
        r = b.get("regs") or {}
        return f"; regs {' '.join(f'{k}={v}' for k, v in r.items())}" if r else ""
    return ", ".join((f"bugcheck {b['code']} ({', '.join(b['params'])}) from {b['ret']}{' (V22)' if b['v22'] else ''}"
                      + (f", trap eip {b['trap_eip']}" if b.get("trap_eip") else "") + regs(b)
                      if b["kind"] == "bugcheck" else f"halt at {b['eip']} with interrupts off")
                     for b in items[:4]) + (f" and {len(items) - 4} more" if len(items) > 4 else "")


# XEMU_RAM_SHM=<name> (the fork, hw/xbox/xbox.c): guest RAM is named POSIX shared memory (mode 0600, replaced at
# launch, unlinked at exit), so a halted guest's RAM is read with no gdbstub packet and hashed with no file (the fork
# survey's "Our side first", Step X.31a; X.27's recorder reads it the same way). A name is global to the machine:
# each sandbox takes its own from W.
RAM_SHM_MARK = b"XEMU_RAM_SHM"


def ram_shm_name(w: Path) -> str:
    """W's ``XEMU_RAM_SHM`` name: one per sandbox, short enough for macOS (31 characters)."""
    return "azx." + hashlib.sha256(str(w).encode()).hexdigest()[:16]


def unlink_ram_shm(name: str | None) -> None:
    """Remove a sandbox's shared memory that its xemu left (killed before its exit handler ran); none: nothing."""
    if not name:
        return
    try:
        shm = shared_memory.SharedMemory(name, track=False)
    except OSError:
        return
    shm.close()
    shm.unlink()


# The fork's input recorder (v0.14-36, 187adba114; Step X.30): XEMU_INPUT_RECORD=<file> writes, every vblank, what
# one pad (XEMU_INPUT_RECORD_PORT) gave the guest, as XEMU_INPUT_PIPE lines tagged +N from the last load, a "# load"
# line opening each load's section; buttons as the keyboard map's scancodes. Replayed on the keyboard pad bound to
# that port with the same map, after a paused load of the same state (play_recording): bit-identical when recorded
# under icount; recorded in real time (an owner demo: icount ignores physical pads) the same on every replay and
# within about 0.001 units of the session (the guest's time followed the host clock).
INPUT_RECORD = "input-record.txt"
RECORD_MARK = b"XEMU_INPUT_RECORD"


def recording_sections(path: Path | str) -> list[list[str]]:
    """An input recording's sections: [0] the lines before any load (from the launch), then one per ``# load``,
    in order; comment lines dropped. Each is replayed after a paused load of the state it was recorded from."""
    secs: list[list[str]] = [[]]
    for ln in Path(path).read_text(encoding="utf-8").splitlines():
        if ln.strip() == "# load":
            secs.append([])
        elif ln.strip() and not ln.startswith("#"):
            secs[-1].append(ln.strip())
    return secs


def headless_mode(log_text: str) -> str | None:
    """The mode a build that supports ``XEMU_HEADLESS`` says it runs in (its startup line ``xemu: headless mode:
    <mode>``, offscreen or null), or None: windowed, as every build before the fork's headless mode."""
    m = re.search(r"(?m)^xemu: headless mode: (\S+)", log_text)
    return m[1] if m else None


def log_count(w: Path, line: str) -> int:
    """How many times W's run log has ``line`` (a whole line: the readiness lines, ``DEVICE_LOST``)."""
    try:
        text = (w / "run.log").read_text(errors="replace", encoding="utf-8")
    except FileNotFoundError:
        return 0
    return len(re.findall(rf"(?m)^{re.escape(line)}$", text))


def exit_cause(w: Path) -> str:
    """Why W's xemu stopped, from its run log's tail: the first known marker (the Vulkan exits ``DEVICE_LOST`` and
    ``VULKAN_FAILED``, the fork's OHCI and nv2a crashes, MoltenVK's lost device); a Vulkan exit with the call or fence
    wait a later build names before it (Step X.33), and that call alone when a windowed later build aborted with no
    exit line; else an assertion's abort (``_ABORT``: "abort: " and the line before it, then the assertion, Step X.45);
    else QEMU's last error on a launch option (a ``-qmp`` port already taken, AZ-480); else "no cause in the run log"."""
    try:
        tail = (w / "run.log").read_text(errors="replace", encoding="utf-8")[-4000:]
    except FileNotFoundError:
        tail = ""
    cause = next((m for m in (DEVICE_LOST, VULKAN_FAILED, "SIGSEGV", "ohci_", "Failed to enter DMA mode",
                              "VK_ERROR_DEVICE_LOST") if m in tail), None)
    named = [*_VK_CALL.finditer(tail), *(_VK_WAIT.finditer(tail) if cause == VULKAN_FAILED else ())]
    last = max(named, key=lambda m: m.start(), default=None)
    why = last and (last[1] if last.re is _VK_WAIT else last[0])
    if cause in (DEVICE_LOST, VULKAN_FAILED):
        return f"{cause} ({why})" if why else cause
    if not cause and not why and (aborts := list(_ABORT.finditer(tail))):
        before = tail[:aborts[0].start()].rstrip("\n").rpartition("\n")[2].strip()
        return "abort: " + (f"{before}; " if before and before != "**" else "") + aborts[0][0].strip()[:200]
    option = _OPTION_ERROR.findall(tail)
    return cause or why or (option[-1] if option else "no cause in the run log")


def pipe_axis(f: float) -> float:
    """The input pipe's ``axis`` value (raw / 32767) that gives the left or right stick float ``f`` in the
    game's ControllerState: the game maps a raw axis past its dead zone linearly (``devkit.sim.inputs``)."""
    if not math.isfinite(f):
        raise ValueError(f"stick value {f!r}")
    if f == 0.0:
        return 0.0
    raw = min(inputs.DEAD_RAW + abs(f) / inputs.RAW_SCALE, inputs.GATE_RAW)
    return math.copysign(raw / inputs.GATE_RAW, f)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# --- fixtures and the scratch config ------------------------------------

SHA_CACHE = Path(user_cache_dir("AzurKit")) / "xemu-sha256.json"   # file_sha256's content keys (Step X.95)
SHA_CACHE_MAX = 256    # entries it keeps (the newest)


def _identity(p: Path) -> list[int]:
    """What a file's content key is: its device, inode, size, mtime_ns and ctime_ns (a write changes the mtime and
    the ctime, which no tool sets back; a copy or an APFS clone is another inode)."""
    st = p.stat()
    return [st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns]


def _sha_cache() -> dict:
    try:
        doc = json.loads(SHA_CACHE.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (OSError, ValueError):
        return {}


def file_sha256(p: Path, *, fresh: bool = False) -> str:
    """``p``'s sha256 (hex), kept in :data:`SHA_CACHE` by its path and :func:`_identity` (Step X.95, X.93's fixed
    costs: the sources' baselines took 6-19 s a sandbox, the build disc's hash 1-2 s): a file hashed before and
    standing as it was then is not read again.  ``fresh``: hashed whatever the cache holds (the teardown's
    baseline, D98's proof that the sandbox changed no source), and kept.  A file that changed while it was read
    is not kept."""
    key, ident = str(Path(p).absolute()), _identity(Path(p))
    got = _sha_cache().get(key)
    if not fresh and isinstance(got, list) and got[:1] == [ident]:
        return got[1]
    with Path(p).open("rb") as f:
        digest = hashlib.file_digest(f, "sha256").hexdigest()
    if _identity(Path(p)) == ident:
        doc = _sha_cache()
        doc.pop(key, None)
        doc[key] = [ident, digest]
        doc = dict(list(doc.items())[-SHA_CACHE_MAX:])
        SHA_CACHE.parent.mkdir(parents=True, exist_ok=True)
        tmp = SHA_CACHE.with_name(f"{SHA_CACHE.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(doc), encoding="utf-8")
        os.replace(tmp, SHA_CACHE)
    return digest


def baseline(originals: list[Path], *, fresh: bool = False, known: dict | None = None) -> str:
    """sha256, mtime_ns, size and path of each source, then the mtime_ns,
    size and path of every entry of xemu's pref dir (listed only: it shows
    portable mode kept the caches in W).  Each source's sha256 is
    :func:`file_sha256`'s: by its content key, read again only with
    ``fresh``; ``known`` (``baseline_keys``: the sandbox's ``up``) gives the
    digest of each source still at the content key it had then, unread (the
    teardown's, Step X.96: a write or a metadata change moves the ctime, which
    no tool sets back, and a replaced file is another inode)."""
    lines = []
    for p in originals:
        got = (known or {}).get(str(p))
        digest = got[1] if got and got[0] == _identity(p) else file_sha256(p, fresh=fresh)
        st = p.stat()
        lines.append(f"{digest} {st.st_mtime_ns} {st.st_size} {p}\n")
    lines.append(_PREF_MARK)
    for p in sorted(PREF_DIR.rglob("*")):
        st = p.lstat()
        lines.append(f"- {st.st_mtime_ns} {st.st_size} {p}\n")
    return "".join(lines)


def baseline_keys(originals: list[Path], before: str, ids: dict[str, list[int]]) -> dict[str, list]:
    """Each source's content key (``_identity``) and the digest ``before`` holds for it (a baseline taken after
    ``ids`` were read): what the teardown's baseline takes unread while the key stands (Step X.96, the xemu fork's
    advice: the teardown read about 6.5 GB a sandbox, the drive and the discs).  A source whose key moved while
    ``before`` was taken is left out, so the teardown reads it whole."""
    digests = {ln.split(" ", 3)[3]: ln.split(" ", 1)[0]
               for ln in before.partition(_PREF_MARK)[0].splitlines() if ln}
    return {k: [ident, digests[k]] for p in originals
            if (k := str(p)) in digests and (ident := _identity(p)) == ids.get(k)}


def sums_check(before: str, fixtures: Path) -> list[str]:
    """The fixtures' SHA256SUMS.txt lines a baseline's hashes don't match
    (reported in the sandbox's state; the owner adds states to the HDD)."""
    here, have = {fixtures, fixtures.resolve()}, {}
    for ln in before.splitlines():
        if ln and not ln.startswith(("-", "#")):
            digest, _, _, p = ln.split(" ", 3)
            if Path(p).parent in here:
                have[Path(p).name] = digest
    try:
        sums = (fixtures / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return ["no SHA256SUMS.txt"]
    bad = []
    for ln in filter(str.strip, sums):
        want, name = ln.split()[0], ln.split()[-1]
        if name in have and have[name] != want:
            bad.append(f"{name}: SHA256SUMS {want[:12]}, now {have[name][:12]}")
    return bad


def fixture_files(fixtures: Path = FIXTURES, hdd: Path | None = None) -> dict[str, Path]:
    """``{sandbox file: source}`` for the HDD, EEPROM, boot ROM and BIOS
    that ``fixtures/xemu.toml`` names; refuses one outside ``fixtures``.
    ``hdd`` replaces the HDD (an agent's private drive, Q250), never one of
    the owner's own xemu files."""
    toml = fixtures / "xemu.toml"
    try:
        files = tomllib.loads(toml.read_text(encoding="utf-8"))["sys"]["files"]
    except FileNotFoundError:
        raise SystemExit(f"{toml} not found: set AZURIK_XEMU_FIXTURES to the "
                         "oracle fixtures folder (D98)") from None
    out = {}
    for key, name in SANDBOX_FILES.items():
        if key != "dvd_path":   # the disc is the sandbox's own (boot_disc)
            out[name] = src = Path(files[key]).resolve(strict=True)
            if not src.is_relative_to(fixtures.resolve()):
                raise SystemExit(f"{toml} names {key} {src}, outside {fixtures}")
    if hdd is not None:
        out["xbox_hdd.qcow2"] = hdd = hdd.resolve(strict=True)
        if hdd.is_relative_to(OWNER_XEMU.resolve()):
            raise SystemExit(f"{hdd} is one of the owner's own xemu files: never a source")
    return out


def boot_disc(iso: Path, fixtures: Path = FIXTURES) -> Path:
    """``iso`` resolved; a disc inside ``fixtures`` must pass the vanilla
    identity gate (D98's ``vanilla.iso`` does), whatever its name."""
    iso = iso.resolve(strict=True)
    if iso.is_relative_to(fixtures.resolve()):
        try:
            verify_vanilla_iso(iso)
        except (OSError, ValueError) as e:   # not vanilla, or not an XISO
            raise SystemExit(f"{iso} is a fixtures disc but not the vanilla ISO "
                             f"({e}): boot the vanilla ISO or a build in out/") from None
    return iso


def oracle_tags(fixtures: Path = FIXTURES) -> list[str]:
    """The tags of the fixtures README's Savestates table: the oracle states."""
    try:
        txt = (fixtures / "README.md").read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    return re.findall(r"(?m)^\| `([^`]+)` \|", txt.partition("## Savestates")[2])


def snapshot_tags(info: str) -> set[str]:
    """Tags in an HMP ``info snapshots`` listing (rows 'ID|-- TAG SIZE DATE ...')."""
    return {p[1] for p in (ln.split() for ln in info.splitlines())
            if len(p) >= 2 and (p[0] == "--" or p[0].isdigit())}


def _put(s: str, table: str, key: str, val: str) -> str:
    """Set ``key = val`` in ``[table]``, adding the line or table."""
    m = re.search(rf"(?m)^\[{re.escape(table)}\]\n", s)
    if not m:
        return f"{s}\n[{table}]\n{key} = {val}\n"
    nxt = re.search(r"(?m)^\[", s[m.end():])
    end = m.end() + nxt.start() if nxt else len(s)
    body, n = re.subn(rf"(?m)^{key} = .*$", lambda _: f"{key} = {val}",
                      s[m.end():end])
    return s[:m.end()] + (body if n else f"{key} = {val}\n{body}") + s[end:]


def tray_disc(blocks: list[dict], w: Path | str) -> str | None:
    """The file in the DVD tray from QMP ``query-block``'s ``blocks``: its name when it is in ``w``, else its path
    (``Sandbox.dvd``; the demo recorder names a load's disc by it, AZ-612)."""
    for d in blocks:
        if d.get("device") == CD:
            f = (d.get("inserted") or {}).get("file")
            return f[len(f"{w}/"):] if f and f.startswith(f"{w}/") else f
    return None


def owner_pads(src: str, port: int) -> dict[str, str]:
    """An owner demo's pad bindings (D205, Step X.31a): the owner's pad, as the fixtures' config names it (its
    port-1 GUID, then its other ``gamepad_mappings``), on ``port``, each other GUID of it on the next free port of
    3, 4, 1 (X.28 bound both, on ports 1 and 3); port 2 keeps the harness's keyboard pad unless ``port`` is 2."""
    c = tomllib.loads(src)["input"]
    guids = list(dict.fromkeys([g for g in [c.get("bindings", {}).get("port1"),
                                             *(m.get("gamepad_id") for m in c.get("gamepad_mappings", []))] if g]))
    if not guids:
        raise SystemExit("--owner-pad: the fixtures' xemu.toml names no pad of the owner's (port1, gamepad_mappings)")
    free = [p for p in (3, 4, 1) if p != port][:len(guids) - 1]
    return {f"port{p}": g for p, g in zip([port, *free], guids)}


def scratch_toml(src: str, w: str, owner_pad: int | None = None, pad_port: int = 2, window: bool = False,
                 present_stall: bool = False) -> str:
    """The fixtures' config with no pad on port 1 (the game's pad is the
    port-2 keyboard), the pad on keys no keyboard has (``PAD``), no F5-F8
    snapshot shortcuts (they ``loadvm``), no background input capture,
    no fullscreen, the volume at 0.0 (the owner's preference, a float),
    and every file it reads or writes in ``w``. ``owner_pad`` (an owner
    demo, D205; ``Sandbox`` allows it only windowed and in real time): the
    owner's pad bound on that port (``owner_pads``), auto-bind on, the
    volume still 0.0. ``pad_port`` (AZ-439): the keyboard pad, which the
    pipe drives, on that port instead of port 2 (port 2 then has no pad):
    a demo recorded on the owner's port 1 replays there as the owner's
    pad (``play_recording``). ``window`` (headless "0"): frame interpolation off (the fixtures' '2x' starved v0.16's
    windowed present path, CAMetalLayer's nextDrawable, and hung 2.76's boots; every demo relaunched to turn it off,
    AZ-601's gap), unless ``present_stall`` (a build with v0.16.1's bounded present, ``PRESENT_STALL_MARK``: an owner
    demo keeps the owner's '2x')."""
    if not 1 <= int(pad_port) <= 4:
        raise SystemExit(f"pad_port {pad_port!r}: a port, 1-4")
    s = re.sub(r"(?m)^(port1|fullscreen_exclusive) = .*\n", "", src)
    if pad_port != 2:   # the keyboard pad moves: its port 2 binding goes, a binding on its new port goes
        s = re.sub(rf"(?m)^(port2|port{pad_port}|port{pad_port}_driver) = .*\n", "", s)
    s = re.sub(r"(?ms)^\[(general\.snapshots\.shortcuts|input\.keyboard_"
               r"controller_scancode_map)\]\n.*?(?=^\[|\Z)", "", s)
    s += "\n[input.keyboard_controller_scancode_map]\n" + "".join(
        f"{key} = {sc}\n" for sc, key in enumerate(PAD, 232))
    for table, key, val in (
            ("general", "screenshot_dir", f"'{w}'"),
            ("general", "games_dir", f"'{w}'"),
            ("input", "background_input_capture", "false"),
            ("input", "auto_bind", "true" if owner_pad else "false"),
            ("display.window", "fullscreen_on_startup", "false"),
            ("display.window", "startup_size", "'640x480'"),
            ("audio", "volume_limit", "0.0"),
            *((("display", "frame_interpolation", "'off'"),) if window and not present_stall else ()),
            *(("sys.files", key, f"'{w}/{name}'") for key, name in SANDBOX_FILES.items())):
        s = _put(s, table, key, val)
    owner = owner_pads(src, owner_pad) if owner_pad else {}
    if pad_port != 2 and f"port{pad_port}" in owner:   # (the owner's pad on port 2 replaces the keyboard pad)
        raise SystemExit(f"pad_port {pad_port}: the owner's pad is bound there (--owner-pad): one pad a port")
    if pad_port != 2:
        s = _put(_put(s, "input.bindings", f"port{pad_port}", "'keyboard'"), "input.bindings",
                 f"port{pad_port}_driver", "'usb-xbox-gamepad'")
    for key, guid in owner.items():
        s = _put(_put(s, "input.bindings", f"{key}_driver", "'usb-xbox-gamepad'"), "input.bindings", key, f"'{guid}'")
    c = tomllib.loads(s)
    files, bindings, vol = c["sys"]["files"], c["input"].get("bindings", {}), c["audio"]["volume_limit"]
    pads = {k: v for k, v in bindings.items() if re.fullmatch(r"port\d", k)}
    kb = f"port{pad_port}"
    bad = [name for name, failed in (
        ("background input capture", c["input"]["background_input_capture"]),
        ("a pad on port 1", "port1" in bindings and "port1" not in owner and kb != "port1"),
        (f"port {pad_port} isn't the keyboard pad", bindings.get(kb) != "keyboard" and kb not in owner),
        ("a pad bound that isn't the keyboard pad or the owner's demo pad",
         pads != {**({kb: "keyboard"} if kb not in owner else {}), **owner}),
        ("snapshot shortcuts", "shortcuts" in c["general"].get("snapshots", {})),
        ("pad scancodes", sorted(c["input"]["keyboard_controller_scancode_map"].values())
         != list(range(232, 257))),
        ("volume_limit isn't 0.0", not isinstance(vol, float) or vol != 0.0),
        ("a [sys.files] path outside W", not all(files[k].startswith(w + "/") for k in SANDBOX_FILES)))
        if failed]
    if bad:
        raise SystemExit(f"the scratch xemu.toml isn't sandboxed: {', '.join(bad)}")
    return s


def scancodes(toml_text: str) -> dict[str, int]:
    return dict(tomllib.loads(toml_text)["input"]["keyboard_controller_scancode_map"])


def sandbox_problems(log_text: str, w: str, base_path: str | None = None) -> list[str]:
    """What the run log shows outside ``w`` (empty = sandboxed). The base path (the caches in W:
    ``base_path``, the ``XEMU_BASE_PATH`` the sandbox set, Step X.33, else portable mode's) prints when the
    renderer first uses it; the null renderer never does (sitting x14), so a null-mode log needs none, but any
    base path it shows must be that one."""
    launch = next((ln for ln in log_text.splitlines()
                   if "Created QEMU launch" in ln), "")
    base = f"base path: {base_path or f'{w}/xemu.app/Contents/Resources'}/"
    problems = [want for want in (f"config path: {w}/xemu.toml", base)
                if want not in log_text and (want != base or headless_mode(log_text) != "null"
                                             or "base path:" in log_text)]
    problems += [want for want in (f"bootrom={w}/bootrom.bin",
                                   f"smbus-storage,file={w}/eeprom.bin",
                                   f"-bios {w}/flashrom.bin",
                                   f"media=disk,file={w}/xbox_hdd.qcow2",
                                   f"media=cdrom,file={w}/dvd.iso")
                 if want not in launch]
    if base_path and not base_path.startswith(w + "/"):
        problems.append(f"XEMU_BASE_PATH outside W: {base_path}")
    launch = launch.replace(w + "/", "")
    return problems + re.findall(r"(?:^|[\s=,:])(/[^\s,]+)", launch)


def host_delta(a: dict | None, b: dict | None) -> dict | None:
    """One boot's host-time counters (``Sandbox.host_profile``'s, Step X.58): ``b`` less ``a`` (``since`` "boot"),
    or ``b`` alone when a relaunch came between them (``since`` "launch": the new xemu's counters start at 0); times
    in seconds (``translate_s``, ``apu_s``, ``idle_s``), counts as they are. None when ``b`` is."""
    if b is None:
        return None
    same = a is not None and a.get("launch") == b.get("launch")
    out: dict = {"since": "boot" if same else "launch"}
    for k, v in b.items():
        if k != "launch" and isinstance(v, int):
            d = v - (a.get(k, 0) if same else 0)
            out[k[:-3] + "_s" if k.endswith("-ns") else k.replace("-", "_")] = round(d / 1e9, 3) if k.endswith("-ns") \
                else d
    return out


def gpu_budget(counters: dict, ceiling: dict | None = None) -> dict:
    """A build's NV2A work against vanilla's (Step X.61): per counter of ``ceiling`` (default ``GPU_CEILING``, vanilla's
    heaviest flip in the pack-03 scenes) that ``counters`` holds, ``{"max": the build's heaviest flip, "vanilla",
    "ratio", "over": ratio > 1}``. ``counters``: an advance's ``gpu-counters`` (its ``max`` is read) or a ``max`` set
    itself. Counts only: a sitting runs its row on its build and on the vanilla control, and ``ceiling`` the control's
    own ``max`` sets the build against vanilla in the same scene (``GPU_CEILING`` is no upper bound: vanilla at a1 goes
    over it, sitting x61)."""
    mx = counters.get("max", counters)
    out = {}
    for k, v in (GPU_CEILING if ceiling is None else ceiling).items():
        if k in mx:
            r = mx[k] / v if v else (math.inf if mx[k] else 0.0)
            out[k] = {"max": mx[k], "vanilla": v, "ratio": round(r, 3), "over": r > 1}
    return out


# Step 2.173 (the owner's D603 "measure and warn, never refuse" and D604 "if framerate decreases due to models, we can
# create a prompt for the xemu fork"): a build's frame cost against vanilla's. frame_cost reads an advance's per-flip
# counters (the first flip, partial, dropped: a scene's whole-advance max can be a flip with none of the body in it, as
# vanilla's and booblord's heaviest a1 flips in sitting x61 had the same vertex and surface bytes) as each counter's
# steady max, p95 and median by kind. frame_warning's L1 warns where a steady flip passes vanilla's heaviest
# (GPU_CEILING raised by the vanilla control's own steady maxima: vanilla at a1 passes GPU_CEILING), L2 notes each scene
# against its control (past BOOT_NOISE with fewer than 3 control boots: 2.162h's row b, two cold boots of one disc up
# to 1.316x apart), and L3 warns where the real-time rate fell below vanilla's in every alternated fresh-process pair by
# more than max(FPS_DROP, the vanilla-vs-vanilla spread): icount's counts are exact but hide the host's cost, so only a
# real-time pair says the owner's frame rate fell. Where L3 fires, fork_request drafts the fork's prompt (FORK_REQUEST:
# counts, times and sha12s, never game bytes). Nothing here refuses a build.
FRAME_KINDS = (("draws", ("begin-end",)), ("geometry", ("vertices", "prim-", "triangles", "vertex-bytes")),
               ("pushbuffer", ("pushbuffer-",)), ("textures", ("texture-",)), ("surfaces", ("surface-", "clear")),
               ("reports", ("report",)), ("memory", ("read-bytes", "write-bytes")))
FRAME_PARTIAL = 1    # an advance's first flip holds only the work since counting began (the fork's README)
BOOT_NOISE = 1.316   # heaviest-flip counts of two cold boots of one disc, up to this far apart (2.162h's row b; sitting
#                      2.173-fc: two cold vanilla boots up to 1.13x apart in e2/idle, and FC-ctl judged by three other
#                      cold boots passed their max 4 times, up to 1.08x, so L1 takes this band at any number of
#                      controls). Since Step X.64 two cold boots in fresh processes repeat exactly (FC-ctl4, FC-ctl5),
#                      so the band now covers a build's boot against vanilla's (booblord 1.03-1.07x) [inferred]
FPS_DROP = 0.03      # L3: a real-time drop past max(3 %, the vanilla-vs-vanilla spread) in every pair
RT_PAIRS = 3         # L3's alternated fresh-process pairs, control then build
RT_FLOOR = 0.49      # flips a vblank: a vanilla control under it (under ~29.4 fps) is a loaded host, L3 inconclusive
#                      (sitting 2.173-fc: vanilla gave 0.4933-0.5 in 12 real-time offscreen rows at load 39-103, and
#                      the lowest less a1/turn's vanilla-vs-vanilla spread, 0.69 %, is 0.490; those arms counted, but
#                      vanilla's few index words cost little and it sits at its 30 fps cap, so the floor stands)
# Step X.68 (the fork's reply on FRAME-8bffffeb0243, item 1): a rate arm counted every NV2A method (gpu-counters on: on
# l256_120 about 6.5M counter calls a flip on the PFIFO thread, the fork's estimate 18-26 ms of its 51 ms frame), so
# its rate held the counters' host cost. A rate arm now runs them off and counts flips without them (flip_count):
# query-xemu-display's FRAME_ENDS where the binary's reply has the key (Step X.69, the fork's answer: cb971fc49b,
# v0.16.3; the guest's frame ends, NV097 FLIP_STALL, what gpu-counters' flips counts, with the counters on or off; a
# running total since the process's launch that no loadvm, checkpoint restore or reset clears, so only a difference
# within one process is a rate), else the game's own present counter, PRESENT_COUNT (0x1A9C0C, Europe 0x1ABB8C: ++
# after D3DDevice_Present at 0x8FD44, the pacer's frame end 0x8FBE0; it counts a frame whose present the device skips
# too, none in play [inferred]; the fork: the two agree). L3 takes counter-free arms only: older (counted) pairs are
# inconclusive. The det cost rows keep the counters (row_cost: exact counts).
FRAME_ENDS = "frame-ends"
PRESENT_COUNT = 0x1A9C0C
NOT_RECORDED = "not recorded"   # an older row's binary, load or reach: fork_request refuses it as missing
FLIPS_BY = {"gpu-counters": "the NV2A counters (their host cost in the rate)",
            "display": f"query-xemu-display's {FRAME_ENDS}, the NV2A counters off",
            "guest": "the game's present counter, the NV2A counters off"}
ASK_FOR = (("vertex-bytes", "the vertex upload (vk/vertex.c)"), ("vertices", "the vertex upload (vk/vertex.c)"),
           ("texture-bytes-new", "texture conversion and caching"),
           ("texture-bytes-uploaded", "texture conversion and caching"), ("texture-", "texture binding and caching"),
           ("begin-end", "per-draw overhead"), ("triangles", "per-draw overhead and rasterisation"),
           ("prim-", "per-draw overhead and rasterisation"), ("pushbuffer-", "the pusher and method path"),
           ("surface-", "surface management (vk/surface.c)"), ("clear", "surface clears"),
           ("report", "reports and queries"))
FORK_REQUEST = """\
DRAFT for the owner to relay (D604): a frame-rate request to the xemu fork, from AzurKit Step {step}, {date}.
WHAT DROPS: {scene}. In real time (offscreen Vulkan, headless, xemu {xemu}, on {host}, host load {load}),
  vanilla flips {a} a vblank ({a_fps} fps) and this build {b} ({b_fps} fps), over {n} alternated fresh-process
  pairs (drops {drops}); flips counted by {flips_by}.
HOW EACH ARM RAN (the build's; the xemu binary's sha256[:12], the load, the scene by warp or by state):
  rates (real time): binary {run_binary}; loaded from {run_load}; {scene} reached by {run_reached}.
  counts (det null): binary {counts_binary}; loaded from {counts_load}; {scene} reached by {counts_reached}.
THE BUILD: disc {disc}, default.xbe {xbe}, recipe `{recipe}`, its ISO on this machine: {iso} (read-only for
  you). In the scene: settle {settle}, then the phase's frame-tagged pipe lines (below), from vblank {start}
  for {frames}.
  lines: {lines}
WHERE THE FRAME GOES (build / vanilla, steady p95 a flip; det null):
{where}
  host, det null: {null_ms} ms a vblank; translate/apu/idle s {host_s}.
  host, det offscreen: {off_ms} ms a vblank; render share = offscreen - null.
  guest: busy ns a flip (icount) {busy}; flips a vblank (det) {det_rate}.
WHAT WE ASK: the host path behind the largest ratio: {ask}. Say if it is ours (the game doing more work) and where.
ACCEPT: real-time flips a vblank within 3% of vanilla's on this Mac in the scene; det RAM digests and pictures
  unchanged; the 32 D98 replays and your goldens unchanged.
OUR FILES (read-only for you): {files}
"""


def frame_kind(counter: str) -> str:
    """A counter's kind in ``FRAME_KINDS`` (draws, geometry, pushbuffer, textures, surfaces, reports, memory), else
    "other" (blits, occlusion samples)."""
    return next((kind for kind, heads in FRAME_KINDS if counter.startswith(heads)), "other")


def _rank(xs: list, q: float):
    """The nearest-rank ``q`` quantile of the sorted, non-empty ``xs``."""
    return xs[max(0, math.ceil(q * len(xs)) - 1)]


def frame_cost(counters: dict, frames: int | None = None, *, partial: int = FRAME_PARTIAL) -> dict:
    """One advance's frame cost (Step 2.173): its ``gpu-counters`` with ``per-flip`` (``frame_advance(n,
    gpu="per-flip")``), the first ``partial`` flips dropped, as ``{flips, steady, [per_vblank], [dropped], kinds:
    {kind: {counter: {max, p95, median}}}}`` over the steady flips (``frame_kind``; no kinds when none is left).
    ``frames``: the advance's vblanks, for flips a vblank (``per_vblank``). Counts only."""
    steady = (counters.get("per-flip") or [])[partial:]
    out: dict = {"flips": counters.get("flips"), "steady": len(steady)}
    if frames:
        out["per_vblank"] = round((counters.get("flips") or 0) / frames, 4)
    if counters.get("per-flip-dropped"):
        out["dropped"] = counters["per-flip-dropped"]
    kinds: dict = {}
    for c in sorted({c for f in steady for c in f}):
        xs = sorted(f.get(c, 0) for f in steady)
        kinds.setdefault(frame_kind(c), {})[c] = {"max": xs[-1], "p95": _rank(xs, 0.95), "median": _rank(xs, 0.5)}
    out["kinds"] = kinds
    return out


def _flat(cost: dict, stat: str = "max") -> dict:
    return {c: v[stat] for kind in cost.get("kinds", {}).values() for c, v in kind.items()}


def frame_ceiling(*scenes: dict, base: dict | None = None) -> dict:
    """Vanilla's heaviest steady flip per counter of ``base`` (default ``GPU_CEILING``, the pack-03 scenes) over
    ``scenes`` (each a vanilla row's ``{label: frame_cost}``), as ``{counter: (value, where)}``, ``where`` "pack-03" or
    the label of the scene that set it."""
    out = {c: (v, "pack-03") for c, v in (GPU_CEILING if base is None else base).items()}
    for sc in scenes:
        for label, cost in sc.items():
            for c, v in _flat(cost).items():
                if c in out and v > out[c][0]:
                    out[c] = (v, label)
    return out


def rate_spread(pairs: list[dict]) -> float:
    """The largest relative difference of a pair's two rates (``{control, build}`` flips a vblank): two vanilla runs'
    gives L3's noise floor (Step 2.173's FC0)."""
    return max((abs(1 - p["build"] / p["control"]) for p in pairs if p.get("control")), default=0.0)


def frame_warning(build: dict, control=None, *, ceiling: dict | None = None, rt: dict | None = None,
                  noise: float | None = None) -> dict:
    """D603's warning and D604's frame-rate line (Step 2.173), never a refusal. ``build``: its scenes, ``{label:
    frame_cost}`` (``model_kit``'s ``row_cost``: "a1/idle" ...); ``control``: the vanilla disc's, one boot's or a list
    of boots'. ``ceiling``: vanilla's heaviest per counter (default ``GPU_CEILING``), raised by every control scene's
    steady max (``frame_ceiling``). ``rt``: ``{scene, pairs: [{control, build}] (flips a vblank, real time, each a
    fresh process), mode, flips_by, vblank_ns}``; ``noise``: the vanilla-vs-vanilla spread (``rate_spread``).
    L1, a warning per counter where a scene's steady max passes the ceiling times ``BOOT_NOISE``, however many
    controls (sitting 2.173-fc: one cold vanilla boot judged by another warned 4 lines at 1.08-1.13x, as did booblord
    at 1.03-1.07x, and the max of 3 cold boots doesn't bound a 4th: its skeptic's D1). L2, a note per scene
    with a control: its
    largest p95 ratio, "above vanilla here" past the controls' band (their largest p95, times ``BOOT_NOISE`` with
    fewer than 3 boots). L3, with ``rt``: a warning where every pair's build is below its control by more than
    max(``FPS_DROP``, ``noise``); inconclusive with fewer than ``RT_PAIRS`` pairs, a control under ``RT_FLOOR`` flips
    a vblank (a loaded host), deterministic pairs (``mode``) or counted ones (``flips_by`` "gpu-counters" or absent:
    Step X.68). Returns ``{warn, notes, fps (L3's verdict or None), request (L3 fired: draft fork_request),
    heaviest (the scene and counter with the largest steady max over the ceiling: the one to time in real time),
    ceiling}``."""
    controls = [] if control is None else control if isinstance(control, list) else [control]
    ceil = frame_ceiling(*controls, base=ceiling)
    warn: list[str] = []
    notes: list[str] = []
    heaviest: dict | None = None
    for label, cost in build.items():
        mx = _flat(cost)
        for c, (v, _) in ceil.items():
            if c in mx and v and (heaviest is None or mx[c] / v > heaviest["ratio"]):
                heaviest = {"scene": label, "counter": c, "ratio": round(mx[c] / v, 3)}
        over = sorted(((mx[c] / v if v else math.inf), c, v, where) for c, (v, where) in ceil.items()
                      if mx.get(c, 0) > v * BOOT_NOISE)
        warn += [f"frame cost: {label} {c} {mx[c]:,} a flip, {r:.2f}x vanilla's heaviest ({v:,}, {where})"
                 for r, c, v, where in reversed(over)]
        ctl = [sc[label] for sc in controls if label in sc]
        p95, base = _flat(cost, "p95"), {c: max(_flat(x, "p95").get(c, 0) for x in ctl) for c in ceil} if ctl else {}
        ratios = [(p95[c] / base[c], c) for c in ceil if c in p95 and base.get(c)]
        if ratios:
            r, c = max(ratios)
            band = 1.0 if len(ctl) >= 3 else BOOT_NOISE
            notes.append(f"{label}: p95 {c} {p95[c]:,} against vanilla's {base[c]:,} ({r:.2f}x"
                         f"{', above vanilla here' if r > band else ''}; {len(ctl)} control boot(s))")
    fps = None
    if rt is not None:
        pairs, thr = rt.get("pairs") or [], max(FPS_DROP, noise or 0.0)
        hz, scene = 1e9 / rt.get("vblank_ns", VBLANK_NS), rt.get("scene", "?")
        if rt.get("mode") == "deterministic":
            fps = {"verdict": "inconclusive", "why": "deterministic pairs: icount hides the host's cost"}
        elif pairs and "gpu-counters" in rt.get("flips_by", "gpu-counters"):   # absent: pairs from before X.68
            fps = {"verdict": "inconclusive", "why": "counted arms: the NV2A counters' host cost is in their rates "
                                                     "(Step X.68); take the pairs again counter-free"}
        elif len(pairs) < RT_PAIRS:
            fps = {"verdict": "inconclusive", "why": f"{len(pairs)} pair(s), {RT_PAIRS} needed"}
        elif (low := min(p["control"] for p in pairs)) < RT_FLOOR:
            fps = {"verdict": "inconclusive",
                   "why": f"vanilla held {low:.3f} flips a vblank, under {RT_FLOOR}: the host is too loaded"}
        else:
            drops = [1 - p["build"] / p["control"] for p in pairs]
            fps = {"verdict": "fell" if all(d > thr for d in drops) else "held",
                   "drops": [round(d, 4) for d in drops], "threshold": round(thr, 4)}
            if fps["verdict"] == "fell":
                b, a = (sum(p[k] for p in pairs) / len(pairs) for k in ("build", "control"))
                warn.append(f"frame rate: {scene} {b:.3f} flips a vblank ({b * hz:.1f} fps) against vanilla's "
                            f"{a:.3f} ({a * hz:.1f} fps), down {min(drops):.1%}-{max(drops):.1%} in all "
                            f"{len(pairs)} pairs (past {thr:.1%})")
        notes.append(f"frame rate: {scene} {fps['verdict']}"
                     + (f" ({fps['why']})" if "why" in fps else f", drops {fps['drops']} against {thr:.1%}"))
    if any(w.startswith("frame cost:") for w in warn):
        if fps is None:
            notes.append("past vanilla's heaviest NV2A work: real-time pairs (model_kit's rate_pairs, in a real-time "
                         "sitting) say whether the frame rate falls")
        elif fps["verdict"] == "held":
            notes.append("past vanilla's heaviest NV2A work; xemu held vanilla's rate here: no request")
    return {"warn": warn, "notes": notes, "fps": fps, "request": bool(fps and fps["verdict"] == "fell"),
            "heaviest": heaviest, "ceiling": {c: v for c, (v, _) in ceil.items()}}


def fork_requests_dir() -> Path:
    """Today's folder of drafted xemu fork requests (``FORK_REQUESTS``/xemu-fork-requests-<date>), which the
    orchestrator relays to the fork session (D894)."""
    return FORK_REQUESTS / f"xemu-fork-requests-{time.strftime('%Y-%m-%d')}"


def fork_request(r: dict) -> str:
    """D604's draft (Step 2.173): ``FORK_REQUEST`` filled from ``r``, for the owner to relay to the fork. Keys (a
    missing one prints "?"): step, date, scene, xemu, host, load (the host's), rt (``frame_warning``'s ``rt``), disc,
    xbe, recipe, iso, settle, start, frames, lines, build and control (the scene's ``frame_cost``, det null),
    host_build and host_control (``timed_advance``'s times, det null), off_ms ("build / vanilla"), files. Required
    (the fork's item 7, Step X.68; else ``ValueError`` naming them): ``run`` and ``counts``, how the build's rate arms
    and its count row ran, each ``{binary (the xemu binary's sha256[:12]), load (the state tag and drive, or the cold
    boot's recipe), reached ("warp levels/..." or "state (...)")}``. The ask is the counter with the largest p95 ratio
    of those the build raised past vanilla's (``ASK_FOR``; none raised: the host's time), or the guest's busy time or
    the null host's time when one rose more. Counts, times and sha12s only: never game bytes. A field that is
    ``NOT_RECORDED`` (an older row's, ``model_kit.run_how``) is missing too."""
    need = [f"{arm}.{k}" for arm in ("run", "counts") for k in ("binary", "load", "reached")
            if (r.get(arm) or {}).get(k) in (None, "", NOT_RECORDED)]
    if need:
        raise ValueError(f"fork_request: every draft states each arm's binary, load and warp-or-state (the fork's "
                         f"item 7): missing {', '.join(need)}")
    rt = r.get("rt") or {}
    pairs, hz = rt.get("pairs") or [], 1e9 / rt.get("vblank_ns", VBLANK_NS)
    a, b = ((sum(p[k] for p in pairs) / len(pairs)) if pairs else None for k in ("control", "build"))
    bp, cp = _flat(r.get("build") or {}, "p95"), _flat(r.get("control") or {}, "p95")
    where = []
    for kind, _ in (*FRAME_KINDS, ("other", ())):
        cs = [c for c in sorted(set(bp) | set(cp)) if frame_kind(c) == kind and (bp.get(c) or cp.get(c))]
        if cs:
            where.append(f"  {kind}: " + "; ".join(f"{c} {bp.get(c, 0):,} / {cp.get(c, 0):,}" for c in cs))
    hb, hc = r.get("host_build") or {}, r.get("host_control") or {}

    def pair(key: str) -> str:
        return f"{hb.get(key, '?')} / {hc.get(key, '?')}"

    def up(key: str) -> float:
        return hb[key] / hc[key] if isinstance(hb.get(key), (int, float)) and hc.get(key) else 0.0
    ratios = sorted(((bp[c] / cp[c], c) for c in bp if cp.get(c) and bp[c] > cp[c]), reverse=True)   # rises only
    ask = next((f"{c} {rr:.2f}x -> {path}" for rr, c in ratios for head, path in ASK_FOR if c.startswith(head)),
               "none of the counts rose: the host's time is the lead")
    if up("busy_ns_flip") > max(1 + FPS_DROP, ratios[0][0] if ratios else 0):
        ask = f"guest busy {up('busy_ns_flip'):.2f}x -> TCG speed on the hot guest PCs"
    elif up("wall_ms_vblank") > max(1 + FPS_DROP, ratios[0][0] if ratios else 0):
        ask = f"null host time {up('wall_ms_vblank'):.2f}x with the guest's busy time {up('busy_ns_flip'):.2f}x -> " \
              "the pusher and method path"
    host_s = " against vanilla's ".join("/".join(str((h.get("host") or {}).get(k, "?"))
                                                 for k in ("translate_s", "apu_s", "idle_s")) for h in (hb, hc))
    fill = {"step": "?", "date": datetime.date.today(), "scene": rt.get("scene", "?"), "xemu": "?",
            "load": "?", "disc": "?", "xbe": "?", "recipe": "?", "iso": "?",
            "settle": "?", "start": "?", "frames": "?", "files": "?",
            **{k: v for k, v in r.items() if v is not None},
            **{f"{arm}_{k}": r[arm][k] for arm in ("run", "counts") for k in ("binary", "load", "reached")},
            "flips_by": FLIPS_BY.get(rt.get("flips_by", "gpu-counters"), rt.get("flips_by")),
            "a": f"{a:.3f}" if a is not None else "?", "b": f"{b:.3f}" if b is not None else "?",
            "a_fps": f"{a * hz:.1f}" if a is not None else "?", "b_fps": f"{b * hz:.1f}" if b is not None else "?",
            "n": len(pairs), "drops": ", ".join(f"{1 - p['build'] / p['control']:.1%}" for p in pairs) or "?",
            "lines": "; ".join(r.get("lines") or []) or "none (idle)", "where": "\n".join(where) or "  ?",
            "null_ms": pair("wall_ms_vblank"), "off_ms": r.get("off_ms", "? / ?"), "host_s": host_s,
            "busy": pair("busy_ns_flip"), "det_rate": f"{(r.get('build') or {}).get('per_vblank', '?')} / "
                                                     f"{(r.get('control') or {}).get('per_vblank', '?')}",
            "ask": ask, "host": r.get("host") or host_line()}
    return FORK_REQUEST.format(**fill)


def host_line() -> str:
    """This Mac in a few words: its model, macOS and cores (a fork request's "on <host>")."""
    def sysctl(k: str) -> str:
        try:
            return subprocess.run(["sysctl", "-n", k], capture_output=True, text=True, timeout=5).stdout.strip() or "?"
        except (OSError, subprocess.SubprocessError):
            return "?"
    import platform
    return f"{sysctl('hw.model')} / macOS {platform.mac_ver()[0] or '?'} / {os.cpu_count()} cores"


def ps_cpu_s(pid: int | None, run=subprocess.run) -> float | None:
    """A process's CPU seconds so far (``ps -o time=``: [[dd-]hh:]mm:ss.cc), None where it can't be read."""
    if not pid:
        return None
    try:
        t = run(["ps", "-o", "time=", "-p", str(int(pid))], capture_output=True, text=True, timeout=5).stdout.strip()
        days, _, hms = t.rpartition("-")
        s = 0.0
        for part in hms.split(":"):
            s = s * 60 + float(part)
        return round(s + 86400 * int(days or 0), 2)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def flip_count(sb) -> tuple[str, int] | None:
    """The guest's flips so far with the NV2A counters off (Step X.68): ("display", query-xemu-display's
    ``FRAME_ENDS``, the process's total since its launch) where the binary's reply has the key, else ("guest", the
    game's ``PRESENT_COUNT``, this release's address); None where neither reads."""
    try:
        if sb.st.get("display_query"):
            d = sb.qmp(DISPLAY_QUERY).get("return") or {}
            if isinstance(d.get(FRAME_ENDS), int):
                return "display", d[FRAME_ENDS]
        return "guest", sb.read_u32(region_named(sb.st.get("release", "usa")).va(PRESENT_COUNT))
    except (OSError, EOFError, ValueError, LookupError):
        return None


def timed_advance(sb, frames: int, *, gpu: bool | str = "per-flip", play: list[str] | None = None) -> tuple[dict, dict]:
    """``frames`` vblanks, timed (Step 2.173): ``sb.frame_advance``, or with ``play`` (a phase's ``+k`` pipe lines)
    ``sb.play_recording``, with the NV2A counters (``gpu``) or, ``gpu=False``, none, its flips by ``flip_count``
    before and after in one xemu process (Step X.68: a rate arm's; none across a relaunch). Returns (the advance's
    reply, its times: ``wall_ms_vblank``, the xemu process's ``cpu_s`` (``ps_cpu_s``), ``host`` (the host profile's
    difference, ``host_delta``), ``flips``, ``per_vblank`` and ``flips_by`` (``FLIPS_BY``'s key), ``start_frame``,
    ``windows`` (a pipe's: only the last window's counters are in the reply) and, under icount, ``busy_ns_flip``: the
    vblanks' guest time less the halted vCPU's skipped ``idle-ns``, a flip)."""
    pid = sb.st.get("pid")
    f0 = None if gpu else flip_count(sb)
    h0, c0, t0 = sb.host_profile(), ps_cpu_s(pid), time.monotonic()
    r = sb.play_recording(play, frames, gpu=gpu) if play else sb.frame_advance(frames, gpu=gpu)
    wall, c1, h1 = time.monotonic() - t0, ps_cpu_s(pid), sb.host_profile()
    flips, by = (r.get("gpu-counters") or {}).get("flips"), "gpu-counters"
    if not gpu and f0 is not None and (f1 := flip_count(sb)) is not None and f1[0] == f0[0] \
            and sb.st.get("pid") == pid:   # a total of one process (frame-ends) or of its guest RAM (the counter)
        flips, by = f1[1] - f0[1] if f1[0] == "display" else (f1[1] - f0[1]) & 0xFFFFFFFF, f1[0]
    t: dict = {"wall_ms_vblank": round(wall * 1e3 / frames, 3),
               "cpu_s": round(c1 - c0, 2) if None not in (c0, c1) else None, "host": host_delta(h0, h1),
               "start_frame": r.get("frame", frames) - frames, "windows": r.get("windows", 1)}
    if flips is not None:
        t.update(flips=flips, per_vblank=round(flips / frames, 4), flips_by=by)
    if flips and t["host"] and sb.st.get("deterministic") and "idle_s" in t["host"]:
        t["busy_ns_flip"] = round((frames * sb.st.get("vblank_ns", VBLANK_NS) - t["host"]["idle_s"] * 1e9) / flips)
    return r, t


def watch_ranges(ranges) -> list[dict]:
    """``xemu-watch-start``'s ranges (``Sandbox.watch``) from ``(address, size[, access[, virtual]])`` tuples or
    dicts of those keys: virtual addresses by default (the game's own VAs; ``virtual=False`` a physical range, which
    matches every mapping of that RAM) and writes (``access`` ``r``, ``w`` or ``rw``); 1 to 64 ranges of 1 B to
    16 MiB below 4 GiB (the fork's limits), else ``ValueError``."""
    keys = ("address", "size", "access", "virtual")
    out = []
    for r in ranges:
        d = dict(r) if isinstance(r, dict) else dict(zip(keys, r))
        d.setdefault("access", "w")
        d.setdefault("virtual", True)
        if set(d) - set(keys) or d["access"] not in WATCH_ACCESS or not (
                1 <= int(d["size"]) <= WATCH_SIZE and 0 <= int(d["address"]) <= (1 << 32) - int(d["size"])):
            raise ValueError(f"watch range {r!r}: an address and 1 B to {WATCH_SIZE >> 20} MiB below 4 GiB, "
                             f"access one of {', '.join(WATCH_ACCESS)}")
        out.append({"address": int(d["address"]), "size": int(d["size"]), "access": d["access"],
                    "virtual": bool(d["virtual"])})
    if not 1 <= len(out) <= WATCH_RANGES:
        raise ValueError(f"watch: 1 to {WATCH_RANGES} ranges, not {len(out)}")
    return out


class Watch:
    """A running xemu access log (``Sandbox.watch``): ``drain()`` returns the hits since the start or the last
    drain and keeps logging, ``stop()`` (the ``with`` block's end too) returns the rest and stops it; ``hits`` holds
    every hit returned, ``dropped`` those xemu counted past its ``max`` and didn't keep."""

    def __init__(self, sb: "Sandbox", ranges: list[dict]):
        self.sb, self.ranges, self.hits, self.dropped, self.running = sb, ranges, [], 0, True

    def _take(self, cmd: str) -> list[dict]:
        r = self.sb.qmp(cmd)
        if "error" in r:
            raise SystemExit(f"{cmd}: {r['error'].get('desc', r['error'])}")
        got = r["return"]
        self.hits += got["hits"]
        self.dropped += got.get("dropped", 0)
        return got["hits"]

    def drain(self) -> list[dict]:
        return self._take("xemu-watch-drain")

    def stop(self) -> list[dict]:
        if not self.running:
            return []
        hits = self._take("xemu-watch-stop")   # a stop that fails can be retried
        self.running = False
        self.sb.event(f"watch stopped: {len(self.hits)} hit(s), {self.dropped} dropped")
        return hits

    def __enter__(self) -> "Watch":
        return self

    def __exit__(self, exc_type, *_) -> None:
        if exc_type is None:
            self.stop()
        else:   # the block's own error comes first: a dead or relaunched xemu can't stop its log (SystemExit)
            with contextlib.suppress(Exception, SystemExit):
                self.stop()


# --- the sandbox ---------------------------------------------------------

class Sandbox:
    """One sandboxed xemu in its own slot. ``with Sandbox(group) as sb:``
    starts one (``up``) and, on exit, quits it (``down``; W is deleted
    unless ``keep``). ``Sandbox.attach(W)`` drives one that ``up`` left
    running; its exit only releases the gdbstub.

    app: the ``xemu.app`` to clone (default ``FORK_APP``, the fork build;
    "kept": ``KEPT_APP``, the build that made the D98 states; an app named
    ``xemu-v<version>.app`` must log that version). disc: the ISO in the
    tray (default the fixtures' ``vanilla.iso``; a fixtures disc must be
    vanilla). hdd: an HDD to clone instead of the fixtures' (default
    ``AZURIK_XEMU_HDD``: an agent's private drive, Q250, whose
    ``vanilla-rzp-*`` tags then load). out: where labelled captures and
    the baselines go (default W). headless: ``XEMU_HEADLESS``, ``"null"``
    (no rendering: the default, Step X.22), ``"1"`` (offscreen: a sitting
    that needs pictures, D184) or ``"0"`` (a visible window); the build
    says which it runs in its run log (``headless_mode``), and one without
    the mode opens its window. deterministic: ``ICOUNT_ARGS`` (default: with
    the null renderer, on a build that has the mode, ``st["deterministic"]``;
    False runs null in real time; True with offscreen, on a build whose
    Vulkan path has the mode (v0.14-27), gives reproducible screendumps
    taken paused, about 3x slower; a window never is). record: a port
    (1-4) whose pad the fork's recorder writes into ``W/INPUT_RECORD``
    (v0.14-36; an owner demo, ``play_recording``). live_pads: a demo as
    played (v0.15, Step X.32b): ``ICOUNT_LIVE_ARGS`` with
    ``XEMU_ICOUNT_LIVE_PADS``, windowed or offscreen, its recording replayed
    tick for tick; an ``owner_pad`` (the keyboard pad's port) takes that
    port's pad by ``xemu-input-bind`` (``_bind_owner_pad``). A
    deterministic launch's guest waits for its first ``loadvm`` (``-S``;
    ``run()`` starts a cold boot). A build with the readiness lines
    (``st["ready_line"]``) is waited on by them, not by the clock
    (``await_ready``, ``loadvm``); one whose QMP offers ``query-xemu-status``
    (``st["xemu_status"]``, Step X.33) by QMP instead of its run log.
    null_ram (v0.16.1, Step X.61): offscreen deterministic with ``XEMU_RENDER_NULL_RAM=request``, guest RAM null's
    and each ``screenshot`` drawn by ``xemu-render-next`` (``RENDER_NULL_RAM_MARK``); legacy_reset: v0.16's reset
    (``XEMU_NV2A_RESET_IRQ=0``) to replay an older build's recording across one (``needs_legacy_reset``).
    warm_sitting (Step X.81d): the sitting (its evidence folder) whose warm build states this sandbox shares through
    its ``xemu_warm.WarmStore`` (``_open_warm``): it starts on the drive holding the most of them, and each build it
    boots cold is published there for the sitting's later sandboxes; never a window or an owner demo.
    """

    def __init__(self, group: str = "x", *, app: Path | str | None = None,
                 disc: Path | str | None = None, hdd: Path | str | None = None,
                 out: Path | str | None = None, wait_s: float = WAIT_S, keep: bool = False,
                 headless: str | None = None, deterministic: bool | None = None, record: int | None = None,
                 owner_pad: int | None = None, pad_port: int = 2, live_pads: bool = False,
                 logs: Path | str | None = None, null_ram: bool = False, legacy_reset: bool = False,
                 warm_sitting: str | None = None):
        self.group = re.sub(r"[^A-Za-z0-9_-]", "-", group)[:32]
        if not 1 <= int(pad_port) <= 4 or (owner_pad is not None and int(owner_pad) == int(pad_port) != 2):
            raise SystemExit(f"pad_port {pad_port!r}: a port, 1-4, not the owner's pad's")
        self.pad_port = int(pad_port)
        if record is not None and not 1 <= int(record) <= 4:
            raise SystemExit(f"record {record!r}: a port, 1-4")
        self.record = record
        if owner_pad is not None and not (1 <= int(owner_pad) <= 4 and headless == "0" and not deterministic):
            raise SystemExit(f"owner_pad {owner_pad!r}: a port, 1-4, in a windowed real-time sandbox only "
                             "(headless '0', not deterministic): an owner demo (D205)")
        self.owner_pad = owner_pad
        if live_pads and (deterministic or headless not in ("0", "1")
                          or (owner_pad is not None and int(owner_pad) != self.pad_port)):
            raise SystemExit("live_pads: a demo as played (icount paced in real time, XEMU_ICOUNT_LIVE_PADS): windowed "
                             "or offscreen, not deterministic, and the owner's pad on the keyboard pad's port, which it "
                             "takes by xemu-input-bind (a port with a pad: the D98 states' port 2)")
        self.live_pads = bool(live_pads)
        if null_ram and not (headless == "1" and deterministic):
            raise SystemExit("null_ram: offscreen and deterministic (headless '1', deterministic=True): the Vulkan "
                             "renderer drawing only the frames a screenshot asks for, guest RAM the null renderer's")
        self.null_ram, self.legacy_reset = bool(null_ram), bool(legacy_reset)
        self.app = app_path(app)
        self.disc = Path(disc) if disc else FIXTURES / "vanilla.iso"
        hdd = hdd or os.environ.get("AZURIK_XEMU_HDD")
        self.hdd = Path(hdd).expanduser() if hdd else None
        self.out = Path(out).resolve() if out else None   # attach may run from another cwd
        self.logs = Path(logs).resolve() if logs else None   # a dead xemu's run log tail goes here (else out)
        self.fixtures = FIXTURES
        self.wait_s, self.keep = wait_s, keep
        self.headless = headless or DEFAULT_HEADLESS
        xemu_env(Path("/"), self.headless)   # refuse an unknown mode before taking a slot
        if deterministic and self.headless == "0":
            raise SystemExit("deterministic needs the null renderer or offscreen (headless 'null' or '1'): "
                             "a window follows host and GPU time")
        self.deterministic = deterministic
        self.warm_sitting = warm_sitting if owner_pad is None and self.headless != "0" else None
        self.w: Path | None = None
        self.st: dict = {}
        self.sc: dict[str, int] = {}
        self._g: RSP | None = None
        self._halted = False
        self._calls: collections.deque = collections.deque(maxlen=CALLS_KEPT)   # _note_call's (Step X.96)
        self._writes_seen: tuple[RSP | None, int] = (None, 0)   # (the RSP itself, its writes) at the last note
        self._owner = True   # up() here: the context exit runs down()
        self._proc: subprocess.Popen | None = None
        self._demo_reaper: threading.Thread | None = None   # an owner demo's (``_owner_demo_reaper``)
        self._xbes: dict[str, bytes] = {}
        self._ramr: tuple | None = None   # (the RSP it was built on, its reader or None; Step X.31a)
        self._shm: shared_memory.SharedMemory | None = None
        self._due = 0   # (continuity) the frame by which every pipe line written has reached the pad (send)
        self.last_picture: dict | None = None   # the last screenshot's age (DISPLAY_QUERY, v0.15)
        self._stop = None   # a boot try's early end on a guest bugcheck (``_bugcheck_stop``, Step X.61)

    @classmethod
    def attach(cls, w: Path | str, wait_s: float = WAIT_S) -> "Sandbox":
        """Drive the sandbox ``up`` left running in ``w``; a launch it
        makes (``relaunch``, and ``boot_build``'s before a retry) waits
        up to ``wait_s`` for a slot (AZ-301)."""
        w = Path(w)
        try:
            st = json.loads((w / "sandbox.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise SystemExit(f"{w} is not a sandbox (no sandbox.json)") from None
        if not (Path(st["W"]).exists() and Path(st["W"]).samefile(w)):
            raise SystemExit(f"{w}'s sandbox.json names another W, {st['W']}")
        sb = cls(st["group"], app=st["app"], disc=st["disc"], out=st["out"], wait_s=wait_s,
                 headless=st.get("headless_requested"), deterministic=st.get("deterministic", False),
                 record=st.get("record_port"), owner_pad=st.get("owner_pad"), pad_port=st.get("pad_port", 2),
                 live_pads=st.get("live_pads", False), null_ram=st.get("null_ram", False),
                 legacy_reset=st.get("legacy_reset", False))
        sb.hdd = Path(st["hdd"]) if st["hdd"] else None
        sb.fixtures = Path(st["fixtures"])
        # up's W, the path xemu was launched by (``ps`` shows it, and alive()
        # looks for it), whatever form the caller typed (/private/tmp, relative)
        sb.w, sb.st, sb._owner = Path(st["W"]), st, False
        sb.sc = scancodes((sb.w / "xemu.toml").read_text(encoding="utf-8"))
        use_release(region_named(st.get("release", "usa")))   # the disc's release's VAs (D146)
        _renew_slot(sb.w)   # its owner is here: renew the lease (Step X.8)
        return sb

    def __enter__(self) -> "Sandbox":
        if self.w is None:
            self.up()
        return self

    def __exit__(self, exc_type, *_) -> None:
        self.release()
        if self._owner and self.st.get("pid") and not self.st.get("down"):
            if not self.down()["sources_equal"] and exc_type is None:
                raise SystemExit("INCIDENT: a source file changed (see the baselines)")

    def _save(self) -> None:
        (self.w / "sandbox.json").write_text(json.dumps(self.st, indent=1), encoding="utf-8")

    def event(self, what: str) -> None:
        self.st.setdefault("events", []).append(f"{now()} {what}")
        self._save()

    # -- up / launch / down --
    def up(self, hold: bool = False) -> dict:
        """Take a slot (waiting up to ``wait_s``), baseline the sources,
        clone them, write the scratch config, launch, prove the sandbox
        from the run log and wait for the gdbstub. Returns the state
        (``W/sandbox.json``). ``hold`` keeps the guest halted where the
        gdbstub's first attach stopped it, early in the boot, and stays
        attached (``jump`` arms its boot checkpoints there)."""
        if sys.platform != "darwin":
            raise SystemExit("macOS only (the fork's app bundle, APFS clones)")
        self._refuse_niced()
        disc = boot_disc(self.disc, self.fixtures)
        sources = fixture_files(self.fixtures, self.hdd)
        self.w = w = Path(tempfile.mkdtemp(prefix=f"azx-{self.group}.", dir="/tmp"))
        lock, asked, t_ask = None, now(), time.monotonic()
        try:
            lock = take_slot(w, self.wait_s, demo=self.owner_pad is not None, window=self.headless == "0")
            t0 = time.monotonic()
            app_files = [self.app / "Contents/MacOS/xemu",
                         *[p for p in [self.app / "Contents/Resources/xemu.toml"] if p.exists()]]
            originals = [*sources.values(), self.fixtures / "xemu.toml", *app_files, disc]
            ids = {str(p): _identity(p) for p in originals}
            before = baseline(originals)
            keys = baseline_keys(originals, before, ids)   # the teardown's: unread while they stand (Step X.96)
            (w / "baseline_before.txt").write_text(before, encoding="utf-8")
            for name, src in {"xemu.app": self.app, **sources, "dvd.iso": disc}.items():
                subprocess.run(["cp", "-Rc", str(src), str(w / name)], check=True)   # APFS clones
            binary = (w / "xemu.app/Contents/MacOS/xemu").read_bytes()
            ready_line = READY.encode() + b"\n" in binary
            can = DETERMINISTIC_MARK in binary
            det = deterministic_mode(binary, self.headless, self.deterministic, self.app.name)
            src = (self.fixtures / "xemu.toml").read_text(encoding="utf-8")
            toml = scratch_toml(src, str(w), None if self.live_pads else self.owner_pad, self.pad_port,
                                window=self.headless == "0", present_stall=PRESENT_STALL_MARK in binary)
            for p in (w / "xemu.toml", w / "xemu.app/Contents/Resources/xemu.toml"):
                p.write_text(toml, encoding="utf-8")
            self.sc = scancodes(toml)
            self.st = {"W": str(w), "group": self.group, "created": now(), "app": str(self.app),
                       "disc": str(disc), "release": use_release(xbe_layout(self._xbe("dvd.iso"))).release.name,
                       "hdd": str(self.hdd) if self.hdd else None, "headless_requested": self.headless,
                       "ready_line": ready_line, "deterministic": det,
                       "continuity": det and CONTINUITY_MARK in binary, "checkpoints": CHECKPOINT_MARK in binary,
                       "incremental": INCREMENTAL_MARK in binary, "load_fix": LOAD_FIX_MARK in binary,
                       "ram_digest": DIGEST_MARK in binary, "strict_cpuid": STRICT_CPUID_MARK in binary,
                       "big_ram": BIG_RAM_MARK in binary, "qmp_watch": QMP_WATCH_MARK in binary,
                       "backlog": BACKLOG_MARK in binary, "bugcheck": BUGCHECK_MARK in binary,
                       "timeout_ms": TIMEOUT_MARK in binary, "dirty_log_fix": DIRTY_LOG_FIX_MARK in binary,
                       "null_ram": self.null_ram,
                       "legacy_reset": self.legacy_reset and RESET_IRQ_MARK in binary,   # older builds reset so anyway
                       "record_port": self.record, "owner_pad": self.owner_pad, "pad_port": self.pad_port,
                       "live_pads": self.live_pads, "add_pads": ADD_PADS_MARK in binary,
                       **({"owner_guid": owner_pads(src, self.owner_pad)[f"port{self.owner_pad}"]}
                          if self.live_pads and self.owner_pad else {}),
                       "debug_advance": DEBUG_ADVANCE_MARK in binary,
                       "ram_shm": ram_shm_name(w) if RAM_SHM_MARK in binary else None,
                       "base_path": base_path_for(w, binary),
                       "out": str(self.out) if self.out else None, "fixtures": str(self.fixtures),
                       "originals": [str(p) for p in originals], "source_keys": keys,
                       "sha256sums_mismatch": sums_check(before, self.fixtures),
                       "asked": asked, "slot_wait_s": round(t0 - t_ask, 1),
                       "setup_s": round(time.monotonic() - t0, 1), "launches": 0,
                       "saved_tags": [], "events": []}
            self._save()
            if self.record and RECORD_MARK not in binary:
                raise SystemExit(f"{self.app.name} has no input recorder (XEMU_INPUT_RECORD, v0.14-36 on)")
            if self.live_pads and LIVE_PADS_MARK not in binary:
                raise SystemExit(f"{self.app.name} has no live pads under icount (XEMU_ICOUNT_LIVE_PADS, v0.15 on)")
            if self.null_ram and RENDER_NULL_RAM_MARK not in binary:
                raise SystemExit(f"{self.app.name} has no XEMU_RENDER_NULL_RAM (v0.16.1 on): null_ram needs it")
            if self.headless == "null" and self.deterministic is None and not can:
                self.event(f"{self.app.name} has no deterministic mode: the null renderer in real time")
            if warms_shader_cache(self.headless, self.st["base_path"]):   # a window starts warm (X.69): never a must
                try:
                    want = re.fullmatch(r"xemu-v(.+)\.app", self.app.name)
                    self.st["shader_cache"] = c = warm_shader_cache(Path(self.st["base_path"]), binary,
                                                                    want and want[1])
                    self.event(f"shader cache: {c['files']} file(s), {c['bytes']} B from {c['dir']}"
                               + (f" (seeded with {c['seeded']['files']} from {FORK_BENCH})" if "seeded" in c else ""))
                except (OSError, subprocess.CalledProcessError) as e:
                    self.event(f"shader cache not warmed ({e}): the window compiles from cold")
            if self.warm_sitting:
                self._open_warm(binary, det)
            self._launch(hold)
            return self.st
        except BaseException:
            self._abort()
            raise
        finally:
            _unlock(lock)

    def _refuse_niced(self) -> None:
        """An owner demo's launch (``up``, ``relaunch``) refuses a niced launcher (``demo_priority``, AZ-466)."""
        if (self.owner_pad or self.st.get("owner_pad")) and (why := demo_priority(os.getpriority(os.PRIO_PROCESS, 0))):
            raise SystemExit(why)

    def argv(self, port: int) -> list[str]:
        """This sandbox's launch line (``xemu_argv``): an owner demo's at normal priority (Step X.34)."""
        return xemu_argv(self.w, port, self.st.get("deterministic", False), nice=self.st.get("owner_pad") is None,
                         live_pads=bool(self.st.get("live_pads")))

    def _launch(self, hold: bool = False) -> None:
        w = self.w
        port = free_port()
        argv = self.argv(port)
        tomls = [p.read_text(encoding="utf-8") for p in (w / "xemu.toml", w / "xemu.app/Contents/Resources/xemu.toml")
                 if p.exists()]
        if why := ram_refusal(argv, tomls, bool(self.st.get("big_ram"))):   # Step X.60: before xemu starts
            raise SystemExit(f"not launched: a guest RAM size {self.app.name} can't run: {why}")
        for name in ("input.fifo", "qmp.sock", HMP_SOCK, WATCH_SOCK):
            (w / name).unlink(missing_ok=True)
        if (w / "run.log").exists():
            (w / "run.log").rename(w / f"run.{self.st['launches']}.log")
        if (w / INPUT_RECORD).exists():   # the recorder rewrites its file at each launch: keep the last one's
            (w / INPUT_RECORD).rename(w / f"input-record.{self.st['launches']}.txt")
        os.mkfifo(w / "input.fifo", 0o600)   # before launch: xemu opens it once
        self._close_ram()   # a new process makes a new shared memory object under the name
        self._close_qmp()   # and a new QMP socket
        self._due = 0   # a new process: its frames count from 0 and no pipe line waits
        t0 = time.time()
        with (w / "run.log").open("wb") as logf:
            self._proc = proc = subprocess.Popen(
                argv,
                env=xemu_env(w, self.headless, self.st.get("record_port"), self.st.get("ram_shm"),
                             self.st.get("base_path"), bool(self.st.get("live_pads")), bool(self.st.get("add_pads")),
                             bool(self.st.get("strict_cpuid")), bool(self.st.get("qmp_watch")),
                             bool(self.st.get("backlog")), bool(self.st.get("bugcheck")), bool(self.st.get("null_ram")),
                             bool(self.st.get("legacy_reset"))),
                cwd=str(w),
                stdin=subprocess.DEVNULL, stdout=logf, stderr=subprocess.STDOUT, start_new_session=True)
        (w / "xemu.pid").write_text(f"{proc.pid}\n", encoding="utf-8")
        self.st.update(pid=proc.pid, gdb_port=port, qmp=str(w / "qmp.sock"), launched_at=t0,
                       launches=self.st["launches"] + 1)
        if self.st.get("owner_pad") is None and (rec := owner_demo()):   # D526: beside an owner demo, in the background
            bg = xemu_queue.set_background(proc.pid, True)
            self.event(f"{'launched at' if bg else 'not set to'} background priority beside an owner demo "
                       f"(pid {rec['pid']}; D526)")
        if self.st.get("owner_pad"):   # what the owner plays at (AZ-466: its launch refuses a niced launcher)
            try:   # the fork's launchers start no xemu while it runs (PROMPT-8 F(2)); its end ends it
                owner_demo_begin(proc.pid, self.group)
                self._demo_reaper = _owner_demo_reaper(proc)
            except OSError as e:
                self.event(f"{OWNER_DEMO} not written ({e}): the fork's launchers won't wait for this demo")
            with contextlib.suppress(OSError):
                self.st["xemu_nice"] = os.getpriority(os.PRIO_PROCESS, proc.pid)
        self.st.pop("down", None)
        _write_slot(w, {"pid": proc.pid, "gdb_port": port, "qmp": str(w / "qmp.sock"), "holder": os.getpid()})
        self._save()
        text = ""
        while time.time() - t0 < LAUNCH_S:
            text = (w / "run.log").read_text(errors="replace", encoding="utf-8")
            if ("Created QEMU launch" in text and ("base path:" in text or headless_mode(text) == "null")) \
                    or proc.poll() is not None:   # the null renderer never prints its base path (sandbox_problems)
                break
            time.sleep(0.2)
        if proc.poll() is not None:   # it quit before its proof: its own cause, not the short log's (AZ-480)
            raise SystemExit(f"xemu exited ({proc.returncode}, {exit_cause(w)}) at launch; see {w}/run.log")
        if problems := sandbox_problems(text, str(w), self.st.get("base_path")):
            self._kill_own()
            raise SystemExit(f"sandbox check failed, our xemu stopped: {problems}")
        version = next((ln.split(": ", 1)[1].strip() for ln in text.splitlines()
                        if ln.startswith("xemu_version:")), None)
        self.st.update(xemu_version=version, proof_s=round(time.time() - t0, 1), headless=headless_mode(text))
        if (want := re.fullmatch(r"xemu-v(.+)\.app", self.app.name)) and version != want[1]:
            self._kill_own()
            raise SystemExit(f"xemu_version {version} isn't {self.app.name}'s")
        if self.headless != "0" and self.st["headless"] is None:   # its startup line comes before the paths
            self.event(f"XEMU_HEADLESS={self.headless} asked; this build doesn't support it: windowed")
        self._save()
        g = None
        while g is None and time.time() - t0 < 2 * LAUNCH_S:
            try:
                g = RSP(port)
            except OSError:
                if proc.poll() is not None:
                    raise SystemExit(f"xemu exited ({proc.returncode}, {exit_cause(w)}) before its gdbstub "
                                     f"answered; see {w}/run.log") from None
                time.sleep(0.2)
        if g is None:
            self._kill_own()
            raise SystemExit(f"no gdbstub on port {port}")
        g.cmd("?")   # attaching halted the guest
        if hold:
            self._g, self._halted = g, True
        else:
            if not self.st.get("deterministic"):   # -S: a deterministic guest waits for its first loadvm
                g.cont()
            g.s.close()
        cmds = self.qmp("query-commands")
        self.st.update(gdb_ready_at=time.time(), gdb_s=round(time.time() - t0, 1), xemu_status=xemu_status_offered(cmds),
                       display_query=xemu_status_offered(cmds, DISPLAY_QUERY),
                       hooks=all(xemu_status_offered(cmds, c) for c in HOOK_COMMANDS),
                       watch=xemu_status_offered(cmds, WATCH_START),
                       host_profile=xemu_status_offered(cmds, HOST_PROFILE),
                       input_queue=xemu_status_offered(cmds, INPUT_QUEUE),
                       xemu_run=xemu_status_offered(cmds, XEMU_RUN))
        big, bits = nv2a_bits((w / "run.log").read_text(errors="replace", encoding="utf-8"))   # Step X.66
        self.st["nv2a_bits"] = bits
        if big:
            self.event(f"guest RAM {big} MiB: NV2A DMA addresses {bits} bits" + (
                "" if bits == 28 else ": a DMA base above 128 MiB wraps, or aborts xemu as a render target "
                "(v0.16.2 reaches 28 bits at 256 MiB or more)"))
        have = snapshot_tags(self._hmp("info snapshots"))
        self.st.update(snapshots=len(have),
                       readme_tags_missing=[t for t in oracle_tags(self.fixtures) if t not in have])
        self._save()
        if self.st.get("live_pads") and self.st.get("owner_pad"):
            self._bind_owner_pad()
        log(json.dumps({k: self.st.get(k) for k in (
            "W", "pid", "gdb_port", "xemu_version", "headless", "deterministic", "proof_s", "gdb_s", "snapshots",
            "readme_tags_missing", "sha256sums_mismatch")}))

    def _bind_owner_pad(self) -> None:
        """(A demo as played, Step X.32b) The owner's gamepad onto the keyboard pad's port by QMP ``xemu-input-bind``
        once xemu is ready: that port keeps its pad (the D98 states hold it), so nothing is plugged, and a load needs
        no replug (the pad follows its port across loads); the port is pinned (the gamepad drives it again when it
        reconnects), and under icount the change lands at the next vblank. Refused by xemu, the launch fails."""
        self.await_ready()
        port, guid = int(self.st["owner_pad"]), self.st["owner_guid"]
        r = self.qmp("xemu-input-bind", port=port, source="gamepad", guid=guid)
        if "error" in r:
            self._kill_own()
            raise SystemExit(f"xemu-input-bind port {port}: {r['error'].get('desc', r['error'])}")
        self.event(f"the owner's pad bound on port {port} by xemu-input-bind"
                   f"{' (pending: at the next vblank)' if r.get('return', {}).get('pending') else ''}")

    def relaunch(self) -> None:
        """After our xemu died (the fork's OHCI crash, hazard 10) or
        ``_relaunch_after`` quit it: launch again on the same W and clones;
        then ``loadvm`` again. While W still holds its slot (a stopped
        xemu's is kept ``LEASE_S``, ``slots``) the relaunch keeps it: it
        replaces this sandbox rather than adding one, so it skips the queue
        and the admission test and waits only for another launch or a foreign
        xemu (Step X.8). A slot already reclaimed is taken like a new one.
        Either way it waits up to ``wait_s`` (AZ-301). It keeps W's drive: a sitting's warm store is adopted only
        at ``up``, ``claim`` and ``boot_build`` (Step X.81d)."""
        if self.alive():
            raise SystemExit(f"xemu pid {self.st['pid']} still runs: down it or use it")
        try:
            self._refuse_niced()
            pid, how = self.st.get("pid"), self._ended()
            keep = any(s["W"] == str(self.w) for s in slots()) and _renew_slot(self.w)
            self.event(f"relaunch after pid {pid} {how} "
                       f"({'keeping its slot' if keep else 'its slot was reclaimed: queued like a new one'})")
            lock = take_slot(self.w, self.wait_s, keep=keep, demo=bool(self.st.get("owner_pad")),
                             window=self.st.get("headless_requested") == "0")
            try:
                self._launch()
            finally:
                _unlock(lock)
        except BaseException:
            owner_demo_end(os.getpid())   # a demo's relaunch marker (``_quit(relaunch=True)``) whose xemu never came
            raise

    def _ended(self) -> str:
        """How our stopped xemu's launch ended: ``quit`` (``_quit``'s: a fresh process per row, a retry's) or ``died
        (rc, exit_cause)``, a death's run log tail then kept in the logs folder before W goes (``relaunch``, ``down``;
        Step X.45)."""
        pid = self.st.get("pid")
        if self.st.get("quit_by_us") == pid:
            return "quit"
        rc = self._proc.poll() if self._proc is not None and self._proc.pid == pid else None
        if (logs := self.logs or self.out) and (self.w / "run.log").exists():
            logs.mkdir(parents=True, exist_ok=True)
            tail = (self.w / "run.log").read_text(errors="replace", encoding="utf-8")[-8000:]
            (logs / f"{self.w.name}-run.{self.st.get('launches')}.log.tail").write_text(tail, encoding="utf-8")
        return f"died ({rc}, {exit_cause(self.w)})"

    def alive(self) -> bool:
        """Whether our xemu runs (``ps`` shows W's app under its pid). An owner demo's found gone (down, a failed
        launch, a death) removes ``OWNER_DEMO`` while it names that pid (PROMPT-8 F(2))."""
        pid = self.st.get("pid")
        up = bool(pid) and f"{self.w}/xemu.app/" in pid_command(pid)
        if not up and pid and self.st.get("owner_pad"):
            owner_demo_end(pid)
        return up

    def _reap(self) -> None:
        if self._proc is not None:
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass

    def _kill_own(self) -> str:
        """SIGTERM, then SIGKILL, our own xemu only (``ps`` must show W's app), ``TERM_S`` each: an xemu that ignores
        SIGTERM (the flip-stall hang, AZ-293) ends by SIGKILL."""
        pid = self.st.get("pid")
        for sig in (signal.SIGTERM, signal.SIGKILL):
            if not self.alive():
                break
            os.kill(pid, sig)
            end = time.monotonic() + TERM_S
            while time.monotonic() < end and self.alive():
                time.sleep(0.1)
        self._reap()
        self._close_qmp()
        return "killed" if not self.alive() else "STILL RUNNING"

    def _abort(self) -> None:
        """A failed up: stop our xemu if it started, free the slot, compare the sources and xemu's pref dir with
        their baseline as ``down`` does (``st["abort"]``, logged; AZ-480), and delete W (kept with ``keep`` once
        xemu has written a run log, or when a source changed, and then its ``kept`` says so; D147)."""
        res: dict = {}
        try:
            if self.st.get("pid"):
                self._kill_own()
                unlink_ram_shm(self.st.get("ram_shm"))
        finally:
            owner_demo_end(os.getpid())   # a relaunch marker (AZ-601)
            _drop_slot(self.w)
            keep = self.keep and (self.w / "run.log").exists()
            if self.st.get("originals"):
                try:
                    res = {"W": str(self.w), **self._baselines()}
                except OSError as e:
                    res = {"W": str(self.w), "error": f"no baseline check: {e}"}
                res["kept"] = keep or res.get("kept", False)   # W stays: as down's ``kept``
                self.st["abort"] = res
                log(json.dumps(res))
            if keep or res.get("kept"):
                self._save()
                log(f"kept {self.w} (delete it by this path when done)")
            else:
                try:
                    delete_sandbox(self.w)
                except (OSError, RuntimeError) as e:
                    log(f"could not delete {self.w}: {e}")

    def _quit(self, relaunch: bool = False) -> dict:
        """Quit our xemu over QMP (SIGTERM, then SIGKILL, to our own
        process only if it lingers ``QUIT_S``: a QMP that never answers
        fails the quit at its ``QMP_S`` timeout); W and its clones stay. A quit of a running xemu is ours
        (``st["quit_by_us"]``: ``relaunch`` logs it as a quit, not a death, Step X.45). ``relaunch`` (a ``relaunch``
        follows): an owner demo's lease names this process until the new xemu's launch (AZ-601)."""
        if self.alive():
            self.st["quit_by_us"] = self.st.get("pid")
        if relaunch and self.st.get("owner_pad"):
            try:
                owner_demo_begin(os.getpid(), self.group, relaunch_of=self.st.get("pid"),
                                 relaunch_cmd=pid_command(os.getpid()))
            except OSError as e:
                self.event(f"{OWNER_DEMO} not kept for the relaunch ({e}): launches may start in its gap")
        self.release()
        res: dict = {}
        try:
            self.qmp("quit")
            res["quit"] = "qmp"
        except (OSError, EOFError, ValueError) as e:
            res["quit"] = f"qmp failed: {e!r}"
        end = time.monotonic() + QUIT_S
        while time.monotonic() < end and self.alive():
            time.sleep(0.2)
        res["process"] = "exited" if not self.alive() else self._kill_own()
        self._reap()
        self._close_ram()
        self._close_qmp()
        unlink_ram_shm(self.st.get("ram_shm"))   # a killed xemu leaves its guest RAM (console keys) behind
        return res

    def down(self, keep: bool | None = None) -> dict:
        """Quit xemu over QMP (SIGTERM, then SIGKILL, to our own process
        only if it lingers), write ``baseline_after.txt`` and compare it
        with ``baseline_before.txt``, free the slot, and delete W unless
        ``keep``, a source changed (an incident: ``sources_equal`` is
        False, and the CLI exits 1) or W holds a hung advance's sample
        (``st["hang_probes"]``, AZ-451). An xemu that died before it keeps
        its run log's tail (``_ended``)."""
        keep = (self.keep if keep is None else keep) or bool(self.st.get("hang_probes"))
        w = self.w
        if self.st.get("pid") and not self.alive():   # it stopped before the down: a death keeps its run log's tail
            self.event(f"down after pid {self.st['pid']} {self._ended()}")
        res: dict = {"W": str(w), **self._quit()}
        self._log_findings(res)
        owner_demo_end(os.getpid())   # a relaunch marker whose relaunch never came (AZ-601)
        if (cache := self.st.get("shader_cache")) and w.is_dir():   # what this window compiled, for the next (X.69)
            try:
                res["shader_cache"] = kept = keep_shader_cache(Path(self.st["base_path"]), cache)
                self.event(f"shader cache: {kept['files']} file(s), {kept['bytes']} B kept in {cache['dir']}"
                           + (f"; set aside by the fork, dropped: {', '.join(kept['set_aside'])}"
                              if "set_aside" in kept else ""))
            except (OSError, subprocess.CalledProcessError) as e:
                self.event(f"shader cache not kept ({e})")
        res.update(self._baselines(), events=self.st.get("events", []))
        res.pop("kept")
        _drop_slot(w)
        self.st["down"] = now()
        if self.st.get("parked") and not keep:   # the parked starts' copies outside W (persist_parked)
            shutil.rmtree(l3.store() / "parked" / w.name, ignore_errors=True)
        if keep or not res["sources_equal"]:
            self._save()
            res["kept"] = True
        else:
            delete_sandbox(w)
        log(json.dumps(res))
        if res.get("kept"):
            log(f"kept {w} (delete it when done)")
        return res

    def _log_findings(self, res: dict) -> None:
        """The run logs' strict-CPUID faults, guest bugchecks and present stalls into ``st`` and ``res`` (``down``,
        ``hold_for_sitting``), and the advances xemu paused at their timeout and the verified restores' missed pages
        (Step X.94) into ``res``: kept past W, the kit's report lists them."""
        if faults := self.cpuid_faults(every_launch=True):
            self.st["cpuid_faults"] = res["cpuid_faults"] = faults
            self.event(f"strict CPUID faults (AZ-021): {fault_list(faults)}")
        if items := self.bugchecks(every_launch=True):   # the same for the guest's bugchecks (Step X.61)
            self.st["bugchecks"] = res["bugchecks"] = items
            self.event(f"guest bugchecks: {bugcheck_list(items)}")
        if timeouts := self.st.get("timeouts"):   # advances and runs xemu paused at their timeout-ms (Step X.94)
            res["timeouts"] = timeouts
        if restores := self.st.get("restores"):   # verified checkpoint restores and the pages they missed (AZ-822)
            res["restores"] = restores
        if stalls := self._log_items(present_stalls, every_launch=True):   # a window's present stalls (v0.16.1)
            self.st["present_stalls"] = res["present_stalls"] = {"n": len(stalls), "max_ms": max(x["ms"] for x in stalls)}
            self.event(f"present stalls: {len(stalls)}, the longest {res['present_stalls']['max_ms']} ms")

    def hold_for_sitting(self, sitting: str, box: dict, hold_s: float = HOLD_S) -> dict:
        """Keep this sandbox for its sitting's next run (Step X.81d) in place of ``down``: its xemu quit, the run
        logs' findings and the sources' baseline checked as ``down`` does them, W (its drive with the warm states,
        its staged discs) and its slot kept (a stopped xemu's slot is kept ``LEASE_S``, longer than ``hold_s``)
        under a record in ``held_dir()`` for ``claim``, and a reaper (``unhold``) that downs it unless a run claims it
        within ``hold_s``; a launch the admission rule refuses takes it first (``release_held``). A source that
        changed (an incident) or a parked start (its copy outside W goes with ``down``) downs it at once."""
        if self.st.get("parked") or self.st.get("owner_pad") or self.st.get("hang_probes"):
            return self.down()
        res: dict = {"W": str(self.w), **self._quit()}
        self._log_findings(res)
        res.update(self._baselines(), events=self.st.get("events", []))
        if not res.pop("kept") and _renew_slot(self.w):   # its lease from now: LEASE_S, past the hold
            held_dir().mkdir(exist_ok=True)
            until = time.time() + hold_s
            rec = held_dir() / f"{self.w.name}.json"
            rec.write_text(json.dumps({"W": str(self.w), "sitting": sitting, "box": box, "until": until}),
                           encoding="utf-8")
            reaper = subprocess.Popen([sys.executable, "-m", "devkit.xemu.oracle", "unhold", str(self.w),
                                       "--after", str(hold_s), "--slots", str(SLOTS)],
                                      cwd=ROOT,
                                      stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                      start_new_session=True)
            self.event(f"held {hold_s:.0f} s for the sitting's next run (reaper pid {reaper.pid})")
            self._save()
            res.update(held=True, hold_s=hold_s)
            log(json.dumps(res))
            return res
        return self.down()

    @classmethod
    def claim(cls, sitting: str, box: dict, *, out: Path | str | None = None, logs: Path | str | None = None,
              wait_s: float = WAIT_S) -> "Sandbox | None":
        """The sandbox a run of this ``sitting`` with this ``box`` (its ``Sandbox`` arguments) held
        (``hold_for_sitting``), relaunched on its W: a fresh xemu process on its own drive (or the sitting's store
        drive holding more of its warm states, ``_adopt_warm``), keeping its slot (no queue, no admission test; one
        already reclaimed is queued like a new one), its earlier run logs, events and slot wait set aside so this
        run reports only its own; None when none waits. A hold past its time, or one whose W can't be driven, is
        downed here."""
        for p in sorted(held_dir().glob("azx-*.json")):
            try:
                rec = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if time.time() > rec["until"] + 60:   # its reaper didn't run (the Mac slept through it, a kill)
                finish_held(p)
                continue
            if rec["sitting"] != sitting or rec["box"] != box or not _take_held(p):
                continue
            w = Path(rec["W"])
            try:
                sb = cls.attach(w, wait_s)
            except (SystemExit, OSError, ValueError, KeyError):
                _drop_slot(w)
                if w.is_dir():
                    delete_sandbox(w)
                continue
            sb._owner, sb.out = True, Path(out).resolve() if out else sb.out
            sb.logs = Path(logs).resolve() if logs else None
            sb.st["out"] = str(sb.out) if sb.out else None
            for k in ("cpuid_faults", "bugchecks", "present_stalls"):   # the last run's, in its report
                sb.st.pop(k, None)
            sb.st.update(events=[], asked=now(), slot_wait_s=0.0)   # this run's report: its own events and wait
            prev = w / "run-logs-before"
            prev.mkdir(exist_ok=True)
            for q in w.glob("run*.log"):
                q.rename(prev / f"{q.stem}.{sb.st.get('launches')}{q.suffix}")
            sb.event("claimed by the sitting's next run")
            try:
                sb._adopt_warm()   # the store's drive, when it holds more of the sitting's warm states than W's
                sb.relaunch()
            except BaseException:
                sb.down()
                raise
            return sb
        return None

    def _baselines(self) -> dict:
        """``baseline_after.txt`` beside ``baseline_before.txt`` (both copied to the out folder): whether the sources
        and xemu's pref dir listing are as they were (``kept``: a source changed, an incident, so W stays)."""
        w = self.w
        before = (w / "baseline_before.txt").read_text(encoding="utf-8")
        after = baseline([Path(p) for p in self.st["originals"]], fresh=True,   # D98's proof: a source whose
                         known=self.st.get("source_keys"))   # content key moved since up is read whole (Step X.96)
        (w / "baseline_after.txt").write_text(after, encoding="utf-8")
        b_src, _, b_pref = before.partition(_PREF_MARK)
        a_src, _, a_pref = after.partition(_PREF_MARK)
        if self.out:
            dst = self.out / "baselines"
            dst.mkdir(parents=True, exist_ok=True)
            for k, text in (("before", before), ("after", after)):
                (dst / f"{w.name}-{k}.txt").write_text(text, encoding="utf-8")
        res = {"sources_equal": b_src == a_src, "pref_dir_equal": b_pref == a_pref,
               "baseline_lines": len(before.splitlines()), "kept": b_src != a_src}
        if not res["sources_equal"]:
            print(f"INCIDENT: a source file changed: diff {w}/baseline_before.txt "
                  f"{w}/baseline_after.txt", file=sys.stderr, flush=True)
        if not res["pref_dir_equal"]:
            log("WARNING: xemu's pref dir listing changed (did the owner run xemu?)")
        return res

    # -- QMP --
    def _holds_qmp(self) -> bool:
        """Whether this sandbox keeps one QMP connection (Step X.32b; the fork measured 0.13 ms a command on one
        against 0.34 connecting each time): a deterministic one, one per W in a process (``_held_qmp``). W's QMP
        serves one client at a time, so a real-time sandbox, an owner demo and a recorded one connect per command:
        the demo recorder, its replug watcher and the owner's tools share that socket; and the kit's exec server lets
        it go after each request (``_close_qmp``), so a command from another process can drive the sandbox between
        requests. Any other driver holds it for its life: another process's command fails at ``QMP_S`` ("held by
        another client"), as it did during an advance before, and ``down`` ends that xemu by SIGTERM."""
        return bool(self.st.get("deterministic")) and not self.st.get("owner_pad") and not self.st.get("record_port")

    def _held_qmp(self) -> list:
        """W's held QMP connection in this process, ``[lock, QMP or None]``: one per sandbox, whichever ``Sandbox``
        object (``attach`` in a driver too) drives it."""
        return _QMP_HELD.setdefault(str(self.w), [threading.RLock(), None])

    def _close_qmp(self) -> None:
        """Let W's held QMP connection go (a relaunch, a quit; the kit's exec server after each request, so another
        process may drive the sandbox meanwhile)."""
        held = self._held_qmp()
        with held[0]:
            q, held[1] = held[1], None
        if q is not None:
            with contextlib.suppress(OSError):
                q.s.close()

    @contextlib.contextmanager
    def _qmp_conn(self, timeout: float = QMP_S):
        """A QMP connection for one exchange, ``timeout`` its socket's: the one a deterministic sandbox keeps
        (``_holds_qmp``; one xemu closed, after a quit or a relaunch, is found before it is used and opened again;
        one an exchange leaves by any exception, a signal's too, is dropped and the exception raised, so a command
        that may have run is never sent twice and no late reply answers the next one), else a new one closed after
        it."""
        if not self._holds_qmp():
            q, refused = qmp_dial(self.w / "qmp.sock", timeout, self.alive, bool(self.st.get("backlog")))
            if refused:
                self.event(f"QMP: {refused} connect(s) refused before this one went through (nothing sent; "
                           f"ECONNREFUSED: the listen backlog of 1 was full)")
            try:
                yield q
            finally:
                q.s.close()
            return
        held = self._held_qmp()
        with held[0]:
            if held[1] is not None and not held[1].open():
                self._close_qmp()
            if held[1] is None:
                held[1] = QMP(self.w / "qmp.sock", timeout=QMP_S, backlog=bool(self.st.get("backlog")))
            q = held[1]
            q.s.settimeout(timeout)
            try:
                yield q
            except BaseException:   # a signal's exit or ^C mid-reply too: its reply would answer the next command
                self._close_qmp()
                raise
            finally:
                if held[1] is q:
                    q.s.settimeout(QMP_S)

    def qmp(self, cmd: str, **args) -> dict:
        """One QMP command's reply (``_qmp_conn``): an advance or a run to a PC (``LONG_QMP``) may take ``ADVANCE_S``,
        or on a build with the watch monitor as long as the guest's frame moves (``_long_qmp``, AZ-685); any other
        command ``QMP_S``."""
        self._note_call(cmd, args)
        if cmd in LONG_QMP and self.st.get("qmp_watch"):
            return self._long_qmp(cmd, args)
        with self._qmp_conn(ADVANCE_S if cmd in LONG_QMP else QMP_S) as q:
            r = q.execute(cmd, **args)
            self._hear_bugchecks(q)
            return r

    def _long_qmp(self, cmd: str, args: dict, slice_s: float | None = None) -> dict:
        """(AZ-685, Step X.61) A long command's reply, waited for in ``LIVE_SLICE_S`` slices (a timeout keeps a
        partial reply buffered, and the held connection stays; a new connection's greeting gets ``QMP_S``, as any
        command's, so one queued in the backlog behind another client isn't taken for a hang): between them the watch monitor (``W/WATCH_SOCK``,
        which answers while the command holds QMP) is asked ``query-xemu-frame``. While the frame moves the guest is
        alive however slowly it runs (a background sandbox beside an owner demo, D526); ``TimeoutError`` (the hang's
        evidence is the caller's: ``frame_advance``) once no frame moved for ``STALL_S`` (a watch that doesn't
        answer counts as no move: xemu's main loop is stuck) or after ``LONG_CAP_S``. (Step X.94) A command carrying
        ``timeout-ms`` whose frame stopped under a watch that answers is waited for until one slice past that bound:
        xemu's main loop runs, so xemu pauses it there itself and replies (``timed-out``)."""
        slice_s = slice_s or LIVE_SLICE_S
        grace = None if args.get("timeout-ms") is None else args["timeout-ms"] / 1000 + slice_s
        t0 = time.monotonic()
        seen, moved, wq, said = None, t0, None, "no answer"
        try:
            with self._qmp_conn(QMP_S) as q:
                q.s.settimeout(slice_s)
                rid = q.send(cmd, **args)
                while True:
                    try:
                        r = q.reply(rid)
                        self._hear_bugchecks(q)
                        return r
                    except TimeoutError:
                        pass
                    answered = False
                    try:
                        wq = wq or QMP(self.w / WATCH_SOCK, timeout=slice_s, backlog=bool(self.st.get("backlog")))
                        f = wq.execute("query-xemu-frame").get("return") or {}
                        said = f"frame {f.get('frame')}, {'running' if f.get('running') else 'not running'}"
                        answered = True
                        if f.get("frame") != seen:
                            seen, moved = f.get("frame"), time.monotonic()
                    except (OSError, EOFError, ValueError):
                        if wq is not None:
                            wq.s.close()
                        wq, said = None, "no answer"
                    el, cap = time.monotonic() - t0, max(LONG_CAP_S, grace or 0)
                    bounded = answered and grace is not None and el < grace   # xemu's timeout-ms ends it (Step X.94)
                    if (stalled := not bounded and time.monotonic() - moved >= STALL_S) or el >= cap:
                        why = (f"no frame moved in {STALL_S:.0f} s" if stalled else f"still running after {cap:.0f} s")
                        if stalled and grace is not None and el >= grace:
                            why += f" nor a reply {slice_s:g} s past its timeout-ms"
                        raise TimeoutError(f"{cmd}: no reply, {why} (the watch monitor: {said}; "
                                           f"{time.monotonic() - t0:.0f} s in)")
        finally:
            if wq is not None:
                wq.s.close()

    def _hmp(self, line: str):
        r = self.qmp("human-monitor-command", **{"command-line": line})
        return r.get("return", r)

    def _note_call(self, cmd: str, args: dict) -> None:
        """(Step X.96) One guest-touching call into ``_calls``, the sequence a fork request names: a QMP command (no
        ``query-*``) with its scalar counts and names (``_CALL_ARGS``), an HMP line's command and tag (no ``info``),
        and before it the gdbstub's memory writes since the last call (``_note_writes``). Memory only."""
        self._note_writes()
        if cmd.startswith("query-") or cmd in ("qmp_capabilities", "xemu-hooks-drain", "xemu-watch-drain"):
            return
        if cmd == "human-monitor-command":
            words = str(args.get("command-line", "")).split()
            if words and words[0] != "info":
                self._calls.append({"call": f"hmp {' '.join(words[:2])}"})
            return
        self._calls.append({"call": cmd, **{k: args[k] for k in _CALL_ARGS
                                            if isinstance(args.get(k), (int, float, str, bool))}})

    def _note_writes(self) -> None:
        """(Step X.96) The gdbstub's memory writes since the last note into ``_calls``, one entry between two calls
        (added to the one already last there): at every QMP call and before a client is dropped (``_drop_g``), so a
        client no call saw (made after a release, dropped by the next advance's ``_let_go``) is counted too. The
        client last counted is kept (the object, not its id), so ``RSP.reconnect`` (the same object, its count kept)
        isn't counted twice; a new client's whole count is added (none for a selftest's fake, which keeps none)."""
        last, seen = self._writes_seen
        n = getattr(last, "writes", 0) - seen
        if self._g is not None and self._g is not last:
            n, last = n + getattr(self._g, "writes", 0), self._g
        self._writes_seen = (last, getattr(last, "writes", 0))
        if n > 0:
            if self._calls and self._calls[-1]["call"] == "gdbstub memory writes":
                self._calls[-1]["n"] += n
            else:
                self._calls.append({"call": "gdbstub memory writes", "n": n})

    def _drop_g(self) -> None:
        """Forget the gdbstub client (its connection closed or lost), its writes noted first (``_note_writes``)."""
        self._note_writes()
        self._g, self._halted = None, False

    def hmp(self, line: str):
        """A monitor command; ``loadvm`` and ``savevm`` go through their
        methods (the tag rules), and ``delvm`` is refused."""
        if re.match(r"\s*(loadvm|savevm|delvm)\b", line):
            raise SystemExit("use Sandbox.loadvm / savevm (the tag rules); delvm is refused")
        return self._hmp(line)

    def status(self) -> str:
        return self.qmp("query-status")["return"]["status"]

    def blockstats(self) -> dict:
        return {(d.get("device") or d.get("qdev")): {"rd": d["stats"]["rd_bytes"], "wr": d["stats"]["wr_bytes"]}
                for d in self.qmp("query-blockstats")["return"]}

    def dvd(self) -> str | None:
        """The file in the DVD tray: its name when it is in W, else its path (``tray_disc``)."""
        return tray_disc(self.qmp("query-block")["return"], self.w)

    def insert(self, name: str) -> None:
        """Put ``W/name`` in the DVD tray (the tray isn't locked: no ``force``)."""
        r = self.qmp("blockdev-change-medium", device=CD, filename=str(self.w / name), format="raw")
        if "error" in r:
            raise SystemExit(f"blockdev-change-medium {name}: {r['error']}")

    def usb(self) -> dict[str, str]:
        """The machine's USB devices now (``usb_devices`` of ``info usb``)."""
        return usb_devices(self._hmp("info usb"))

    def plug_pad(self, root: str, index: int, ids: tuple[str, str] | None = None) -> list[dict]:
        """A pad hub on root port ``root`` (``1.1``-``1.4``, 3 ports) and an Xbox pad on its port 1 that reads player
        ``index + 1``'s host source (none bound: neutral), over QMP, as xemu plugs a bound pad and the replug watcher
        its demo hub: before a load of a state saved with a pad this machine lacks. ``ids``: the two device ids
        (default ``plughub<root>``, ``plugpad<root>``). Refused by xemu on a port that holds a device already."""
        hub, pad = ids or (f"plughub{root.replace('.', '')}", f"plugpad{root.replace('.', '')}")
        out = [self.qmp("device_add", driver="usb-hub", port=root, ports=3, id=hub),
               self.qmp("device_add", driver="usb-xbox-gamepad", index=int(index), port=f"{root}.1", id=pad)]
        if err := next((r["error"] for r in out if "error" in r), None):
            raise SystemExit(f"plugging a pad hub on USB {root}: {err.get('desc', err)}")
        self.event(f"plugged a pad hub on USB {root} (its pad reads player {int(index) + 1})")
        return out

    def _pads(self, tag: str, held: dict[str, str] | None) -> float | None:
        """Before a load: the pads the state holds, in place (a load into a machine without one fails, "Unknown
        section ... usb-hub"). An owner demo's (AZ-466): the owner's pad is waited for until ``info usb`` lists its
        hub (``Port 1.3,`` for port 1), ``OWNER_PAD_S`` at most, the wait said in an event and the log. Then each pad
        hub ``held`` lists (``usb_devices`` at its ``savevm``: ``tag_usb``, or a demo's meta in a replay, AZ-439) that
        the machine lacks is plugged (``plug_pad``): the replug watcher's demo hub (its pad ``demopad``) reading
        player 1, as ``xemu_demo.replug_once`` plugs it, any other reading its own player (none bound: neutral).
        Returns the seconds the owner's pad was waited for; None outside a demo. No demo and nothing held: no
        query at all."""
        port = self.st.get("owner_pad")
        if not port and not held:
            return None
        waited, now_usb = self._await_owner_pad(tag, port) if port else (None, self.usb())
        for root in sorted(r for r in (held or {}) if r.count(".") == 1 and r not in now_usb):
            demo = held.get(f"{root}.1") == "demopad"
            self.plug_pad(root, 0 if demo else HUB_PORTS.index(int(root.split(".")[1])),
                          ("demohub", "demopad") if demo else None)
        return waited

    def _await_owner_pad(self, tag: str, port: int) -> tuple[float, dict[str, str]]:
        """(An owner demo) Until ``info usb`` lists the owner's pad's hub: the seconds waited and the USB devices."""
        want, t0, said = hub_port(port), time.monotonic(), False
        while want not in (now_usb := self.usb()):
            if not said:
                msg = (f"loadvm {tag}: waiting for the owner's pad on port {port} (USB {want}, 'Port {want},' in info "
                       f"usb) before the load, {OWNER_PAD_S:.0f} s at most: connect it")
                self.event(msg)
                log(msg)
                said = True
            if time.monotonic() - t0 > OWNER_PAD_S or not self.alive():
                raise SystemExit(f"loadvm {tag}: the owner's pad never came on port {port} (USB {want}) in "
                                 f"{OWNER_PAD_S:.0f} s ({'alive' if self.alive() else exit_cause(self.w)}) (AZ-466)")
            time.sleep(1.0)
        return round(time.monotonic() - t0, 1), now_usb

    def reset_into(self, name: str, *, cont: bool = True) -> None:
        """Order A of s6's modded-build path (5 of 5 boots): QMP ``stop``,
        ``W/name`` into the tray, ``system_reset``, ``cont``: the disc
        cold-boots, keeping the HDD the loaded state left. ``cont=False``
        (``boot_frames``): the VM stays stopped at the reset, for the run
        that queues the boot's presses."""
        self.release()
        self.qmp("stop")
        self.insert(name)
        self.qmp("system_reset")
        if cont:
            self.qmp("cont")
        if (now_in := self.dvd()) != name:
            raise SystemExit(f"the tray holds {now_in}, not {name}")
        self.event(f"reset into {name}")

    # -- gdbstub --
    @property
    def g(self) -> RSP:
        """The RSP connection; attaching halts the guest and clears stale breakpoints."""
        if self._g is None:
            end = time.monotonic() + 10.0
            while True:
                try:
                    self._g = RSP(self.st["gdb_port"])
                    break
                except OSError:
                    if time.monotonic() > end or not self.alive():
                        raise
                    time.sleep(0.3)
            self._g.cmd("?")
            self._halted = True
        return self._g

    def halt(self) -> RSP:
        g = self.g
        if not self._halted:
            self._halt_guest(g)
        return g

    def _halt_guest(self, g: RSP) -> None:
        """Halt a guest we let run (``_halted`` False): ^C, unless the VM already stands (``query-status`` not
        ``running``: a breakpoint whose stop reply something read, a QMP ``stop``), which is taken as halted, a
        stop reply already sent read off first. The stub answers ^C only while the VM runs (``gdb_read_byte``
        drops it otherwise), so such a guest left ^C waiting for a reply that never came (AZ-781: s204l's row, 13
        min in recv; a timed-out ^C in ``release`` also skipped its ``c``, leaving the guest held)."""
        if self.status() == "running":
            g.interrupt()
        else:
            with contextlib.suppress(TimeoutError):
                g.wait_stop(0.2)
        self._halted = True

    def run(self) -> None:
        """Clear the breakpoints and let the guest run (stay attached)."""
        g = self.halt()
        g.cmd("?")
        g.cont()
        self._halted = False

    def release(self) -> None:
        """Clear the breakpoints, let the guest run, close the gdbstub connection."""
        if self._g is None:
            return
        try:
            if not self._halted:
                self._halt_guest(self._g)
            self._g.cmd("?")
            self._g.cont()
            self._g.s.close()
        except (OSError, EOFError):
            pass
        self._drop_g()

    def _wait(self, timeout: float) -> bool:
        """Wait for a stop; on a timeout interrupt. Halted either way."""
        try:
            self.g.wait_stop(timeout)
            ok = True
        except TimeoutError:
            self.g.interrupt()
            ok = False
        self._halted = True
        return ok

    def wait_bp(self, vas: list[int], timeout: float) -> int | None:
        """Arm ``vas`` and run to the next hit: the EIP it stopped at
        (halted), or None after ``timeout``. Halted on one of them, it
        steps off first: the stub would report that hit again (rz-a).
        Where waits run on guest frames (``_frame_waits``, Step X.96: the
        xemu fork session's advice) ``timeout`` is guest seconds: one
        ``xemu-run`` to the PCs within ``vblanks(timeout)`` frames, its host
        time bounded by xemu (``timeout-ms``), not a breakpoint, the host's
        clock and a ^C. A hit is the same (the run stops before the
        instruction, as ``Z0`` does); a miss ends on the same frame in every
        run and process, whatever the host's load. The gdbstub client (a
        caller's ``g`` too) is attached again after the run, halted."""
        if self._frame_waits():
            g = self.halt()
            if g.regs()["eip"] in vas:   # halted on one: step off it (the run would stop there again)
                g.cmd("s")
            try:
                r = self._run(vblanks(timeout), [{"pc": va} for va in vas])
            finally:
                try:
                    g.reconnect()
                    self._g, self._halted = g, True
                except OSError:   # xemu gone: the next use says so
                    self._drop_g()
            return (r.get("pc") or r["regs"]["eip"]) if r.get("reason") == "hit" else None
        g = self.halt()
        arm(g, list(vas))
        resume(g, list(vas))
        self._halted = False
        return g.regs()["eip"] if self._wait(timeout) else None

    # -- memory --
    def read(self, va: int, n: int) -> bytes:
        """``n`` bytes at ``va``, the guest halted: from its RAM in shared memory where the build exposes it
        (``_ram``, Step X.31a), else through the gdbstub; the same bytes either way."""
        g = self.halt()
        ram = self._ram()
        return ram(va, n) if ram is not None else g.read(va, n)

    def _ram(self):
        """``read(va, n)`` over guest RAM in shared memory (``XEMU_RAM_SHM``, ``st["ram_shm"]``), the guest
        halted: each page through the guest's page tables from CR3, as the owner-demo recorder walks them
        (``l3.ram_reader``: 4 MiB pages too; a page that isn't present raises ``OSError`` as an E14 does), a page
        no RAM backs through the gdbstub. Built once per gdbstub connection (a load keeps the RAM block, a
        relaunch makes a new one) and checked against the gdbstub's view of the page directory; None when the
        build has none or the check fails (reads then go through the gdbstub)."""
        g = self.halt()
        if self._ramr is not None and self._ramr[0] is g:
            return self._ramr[1]
        self._close_ram()
        read = None
        if self.st.get("ram_shm"):
            try:
                shm = shared_memory.SharedMemory(self.st["ram_shm"], track=False)
            except OSError:
                shm = None
            if shm is not None:   # read only: an incremental restore can't see writes from here (Step X.32b)
                read = l3.ram_reader(shm.buf, g.cr3() & ~0xFFF, g.read)
                try:
                    same = read(l3.PDE_BASE, l3.PAGE) == g.read(l3.PDE_BASE, l3.PAGE)
                except OSError:
                    same = False
                if same:
                    self._shm = shm
                else:
                    read = None
                    shm.close()
                    self.event(f"XEMU_RAM_SHM {self.st['ram_shm']} isn't the guest's RAM: reads go through the "
                               "gdbstub")
        self._ramr = (g, read)
        return read

    def _close_ram(self) -> None:
        self._ramr = None
        if self._shm is not None:
            try:
                self._shm.close()
            except BufferError:   # a view still held: the mapping goes with it
                pass
            self._shm = None

    def ram_sha256(self) -> str:
        """The sha256 of all guest RAM, the VM stopped (halted at the gdbstub, or paused: ``frame_advance``;
        a running one is halted first): straight from ``XEMU_RAM_SHM`` where the build exposes it (no file, no
        copy; Step X.31a), else from a dump (``ram_dump``, into W, deleted at once). RAM holds console keys: only
        the hash leaves."""
        if not self._halted and self.status() == "running":
            self.halt()
        if self.st.get("ram_shm"):
            try:
                shm = shared_memory.SharedMemory(self.st["ram_shm"], track=False)
            except OSError:
                shm = None
            if shm is not None:
                try:
                    return hashlib.sha256(shm.buf).hexdigest()
                finally:
                    shm.close()
        p = self.w / f"pmem-sha.{os.getpid()}.bin"
        try:
            self.ram_dump(p)
            with p.open("rb") as f:
                return hashlib.file_digest(f, "sha256").hexdigest()
        finally:
            p.unlink(missing_ok=True)

    def ram_digest(self) -> str:
        """Guest RAM's XXH3-128 from xemu itself (QMP ``xemu-ram-digest``, v0.15, ``st["ram_digest"]``; Step
        X.32b), the VM stopped as for ``ram_sha256``: 32 hex digits in about 4 ms for 128 MiB, for telling runs of
        one sitting apart (equal across identical runs, not cryptographic; the sittings' baselines hold
        ``ram_sha256``'s). A build without it refuses."""
        if not self.st.get("ram_digest"):
            raise SystemExit(f"{self.app.name} has no xemu-ram-digest xxh3-128 (v0.15 on): use ram_sha256")
        if not self._halted and self.status() == "running":
            self.halt()
        r = self.qmp("xemu-ram-digest", algorithm="xxh3-128")
        if "error" in r:
            raise SystemExit(f"xemu-ram-digest: {r['error'].get('desc', r['error'])}")
        return r["return"]["xxh3-128"]

    def host_profile(self) -> dict | None:
        """xemu's host-time counters since this launch (QMP ``query-xemu-host-profile``, v0.16,
        ``st["host_profile"]``; Step X.58) with the launch they count from (``launch``); None on a build without
        them or from an xemu that doesn't answer (a boot's diagnostic never fails it)."""
        if not self.st.get("host_profile"):
            return None
        try:
            r = self.qmp(HOST_PROFILE)
        except (OSError, EOFError, SystemExit):
            return None
        return {"launch": self.st.get("launches"), **r["return"]} if "return" in r else None

    def watch(self, ranges, *, max_hits: int | None = None) -> "Watch":
        """xemu's access log (QMP ``xemu-watch-start``, v0.16, ``st["watch"]``; Step X.58): who reads or writes a
        field, with no stop (on v0.16.1 a hit on a physical range reached through another bus address, such as the
        NV2A's RAM window, also carries ``ram-address``, the RAM offset). Every CPU load or store that overlaps
        ``ranges`` (``watch_ranges``: the game's VAs and writes by default) is kept with its ``frame``, ``pc`` (the accessing instruction), ``address``,
        ``physical``, ``size``, ``access`` and ``value`` (the bytes, hex: what a read read, what a write left); the
        same in every run under icount, the guest's RAM as without it. Start it paused or halted for an exact first
        instruction, then run (``frame_advance``, a capture, ``run``); device DMA and page-table walks aren't seen.
        ``max_hits``: what xemu keeps between drains (its default 100000; past it only counted, ``dropped``).
        Returns the ``Watch`` (``drain``, ``stop``); ``with sb.watch(...) as w:`` stops it at the block's end. A
        hit's ``value`` is guest memory: decode it to numbers, never print it raw. A build without it refuses."""
        if not self.st.get("watch"):
            raise SystemExit(f"{self.app.name} has no {WATCH_START} (v0.16 on)")
        args: dict = {"ranges": watch_ranges(ranges)}
        if max_hits is not None:
            if not 1 <= int(max_hits) <= WATCH_HITS:
                raise ValueError(f"max_hits {max_hits!r}: 1 to {WATCH_HITS}")
            args["max"] = int(max_hits)
        r = self.qmp(WATCH_START, **args)
        if "error" in r:
            raise SystemExit(f"{WATCH_START}: {r['error'].get('desc', r['error'])}")
        self.event(f"watch started on {len(args['ranges'])} range(s)")
        return Watch(self, args["ranges"])

    def read_u32(self, va: int) -> int:
        return struct.unpack("<I", self.read(va, 4))[0]

    def read_i32(self, va: int) -> int:
        return struct.unpack("<i", self.read(va, 4))[0]

    def read_f32(self, va: int) -> float:
        return struct.unpack("<f", self.read(va, 4))[0]

    def write(self, va: int, data: bytes) -> bytes:
        """Write guest memory and read it back (raises if it differs)."""
        g = self.halt()
        g.write(va, data)
        back = g.read(va, len(data))
        if back != data:
            raise OSError(f"write {va:#x}: the read-back differs")
        return back

    def write_f32(self, va: int, v: float) -> float:
        return struct.unpack("<f", self.write(va, struct.pack("<f", v)))[0]

    def write_i32(self, va: int, v: int) -> int:
        return struct.unpack("<i", self.write(va, struct.pack("<i", v)))[0]

    def write_u32(self, va: int, v: int) -> int:
        return struct.unpack("<I", self.write(va, struct.pack("<I", v)))[0]

    # -- game structures --
    def entity_row(self, ent: int) -> dict:
        b = self.read(ent, ENT_SPAN)
        return {k: struct.unpack_from("<" + c, b, o)[0] for k, (o, c) in ENT.items()}

    def chain(self, ent: int) -> dict:
        """The critter and armor chain (pointers as ints): critter =
        [ent+0x20]; HP (i32) critter+0x210/+0x214; armor_mgr =
        [[critter+0x154]+0xCC]; fuel f32 armor_mgr+0x24; the armor level
        slot [armor_mgr+0x20]: Level i32 +0x08, drain f32 +0x34, Flaps i32 +0x38."""
        c = self.read_u32(ent + 0x20)
        hp, hp_max = struct.unpack("<ii", self.read(c + 0x210, 8))
        gp = self.read_u32(c + 0x154)
        am = self.read_u32(gp + 0xCC)
        lv = self.read_u32(am + 0x20)
        fuel = struct.unpack("<f", self.read(am + 0x24, 4))[0]
        lb = self.read(lv + 0x08, 0x34)
        return {"critter": c, "gameplay": gp, "armor_mgr": am, "level_ptr": lv, "hp": hp,
                "hp_max": hp_max, "fuel": fuel, "armor_level": struct.unpack_from("<i", lb, 0)[0],
                "fuel_drain": struct.unpack_from("<f", lb, 0x2C)[0],
                "flaps": struct.unpack_from("<i", lb, 0x30)[0]}

    def pad(self) -> dict:
        """The active ControllerState ([0x1A7AE4]; port 2 = 1) as floats, and its index."""
        idx = self.read_u32(ACTIVE_PAD)
        b = self.read(CONTROLLER_STATE + 0x54 * (idx if idx < 4 else 0), 0x54)
        return {"idx": idx, **{k: struct.unpack_from("<f", b, o)[0] for k, o in PAD_FIELDS.items()}}

    def player(self) -> dict | None:
        """Run to the next player tick (5 s): its entity row and chain, halted there."""
        if self.wait_bp([PLAYER_TICK], 5.0) != PLAYER_TICK:
            return None
        r = self.g.regs()
        ent = self.g.u32(r["esp"] + 4)
        return {"ent": ent, "ret": self.g.u32(r["esp"]), "fctrl": r["fctrl"],
                **self.entity_row(ent), **self.chain(ent)}

    def _xbe(self, name: str) -> bytes:
        if name not in self._xbes:
            self._xbes[name] = read_file(self.w / name, "default.xbe")
        return self._xbes[name]

    def shim_data(self, name: str = "dvd.iso") -> list[tuple[int, int]]:
        """The ``(start, end)`` VAs ``W/name``'s shims write while the game
        runs, read from the build: the player-model shims' (X3's damage
        marker, every tick; AZ-300; ``_player_character.shim_data``) and
        qol_alloc_race's copy gate's, on in every build (g_main from main's
        first frame; AZ-817; ``qol_alloc_race.shim_data``)."""
        try:
            xbe = self._xbe(name)
            return sorted({*shim_data(xbe), *copy_gate_data(xbe)})
        except (ValueError, LookupError) as e:   # it doesn't build, or isn't the build's
            raise SystemExit(f"{name}: can't place its shims' data: {e}") from None

    def code_identity(self, name: str = "dvd.iso") -> dict[str, list[int]]:
        """``{section: [bytes compared, bytes that differ]}`` of the guest's
        ``.text`` and ``SHIMS`` against ``W/name``'s ``default.xbe``,
        leaving out what its shims write (:meth:`shim_data`)."""
        return {k: list(v) for k, v in code_identity(
            self.halt(), self._xbe(name), self.shim_data(name)).items()}

    # -- L3 snapshots and the exact replayer (Step X.6, D170) --
    def disc_sha12(self) -> str:
        """sha256[:12] of the disc in the tray: ``dvd.iso``'s from its
        source's baseline line, a staged or adopted one's from its source's
        hash as it was cloned (``stage``, ``adopt_parked``), another's hashed
        once (kept in sandbox.json)."""
        name = self.dvd() or "dvd.iso"
        known = self.st.setdefault("disc_sha12", {})
        if name not in known:
            if name == "dvd.iso":
                lines = (self.w / "baseline_before.txt").read_text(encoding="utf-8").splitlines()
                known[name] = next(ln for ln in lines if ln.endswith(f" {self.st['disc']}"))[:12]
            else:
                with (self.w / name).open("rb") as f:
                    known[name] = hashlib.file_digest(f, "sha256").hexdigest()[:12]
            self._save()
        return known[name]

    def disc_source(self, name: str | None = None) -> str:
        """The image ``W/name`` (by default the disc in the tray) was cloned
        from: ``dvd.iso``'s source or the build ``stage`` took in, which the
        conformance corpus keeps beside the disc's sha12 (AZ-380)."""
        name = name or self.dvd() or "dvd.iso"
        if name == "dvd.iso":
            return self.st["disc"]
        return next((k.rsplit("|", 2)[0] for k, v in self.st.get("staged", {}).items() if name == f"b-{v}.iso"),
                    str(self.w / name))

    def snapshot(self, label: str, *, store: Path | str | None = None, scene: bool = False, here: bool = False,
                 parent: dict | None = None, high: bool = True) -> dict:
        """An L3 snapshot (``devkit.sim.snapshot``): run to the player's next
        update entry 0x8C230 (``scene``: the next scene tick entry 0x55AB0)
        and write every present user page, the registers and the metadata
        (the level, entity, body centre, state and HP, the event clock and
        ``start_hash`` for the replayer's start check, the last loadvm tag,
        the xemu build, the disc's sha256[:12]) to ``<store>/<label>.l3snap``
        (``l3.store``: private, mode 700; never overwritten). Stays halted
        there, the start ``replay`` replays from. The game's frame pacing is
        pinned first (``pin_pace``), so the snapshot's tick ends its frame, as
        L3, which renders after each whole step, assumes. Returns counts and
        hashes: no positions, no bytes.

        ``here``: the guest is halted exactly where ``replay`` left it, the
        player's update entry of the tick after the string, and the snapshot
        is taken there without running a tick (D172's chain: no tick goes
        unrecorded between a segment and the next); ``parent`` (the string's
        sha12 and the start's metadata hash, say) is kept in the metadata.

        ``high`` (the default; Step X.15): the snapshot also holds the
        thread's stack (ESP's page to the TIB's StackBase) and the RAM window
        at 0x80000000, so L3 can run whole steps from an update entry (it
        finishes the frame on that stack) and reads contiguous memory as
        taken: kernel memory, which stays in the private store like the rest.

        Every page comes from one dump of guest RAM (``ram_dump``, into W,
        deleted at once; Step X.22, sitting x22: 152 MB in 0.16 s where the
        gdbstub's page reads took 1.9 s), each user page through the page
        tables the dump holds (``l3.ram_reader``), checked against the
        gdbstub's view of the page directory and the entity's page; the
        gdbstub reads the registers and the metadata."""
        if self.st.get("release", "usa") != "usa":
            raise SystemExit("L3 runs the USA release only (D146)")
        path = l3.snapshot_path(label, store)
        if path.exists():
            raise SystemExit(f"{path} exists: a snapshot is never overwritten; pick another label")
        g = self.halt()   # a guest left running (run(), until_movable's wait) must stop before the first read
        pin_pace(g)   # the next update entry ends its frame (a frame planned before this holds the tick after it)
        if here:
            if scene:
                raise SystemExit("here=True takes an update-entry snapshot (a replay halts there), not a scene one")
            r = g.regs()
            if r["eip"] != l3.PLAYER_UPDATE:
                raise SystemExit(f"here=True needs the guest halted at the player's update entry {l3.PLAYER_UPDATE:#x}"
                                 f" (a replay leaves it there); it is at {r['eip']:#x}")
            ent = r["ecx"]
        else:
            if self.wait_bp([PLAYER_TICK], 10.0) != PLAYER_TICK:
                raise SystemExit("no player tick within 10 s (a menu, dialog or cutscene?)")
            ent = g.u32(g.regs()["esp"] + 4)
            at = l3.SCENE_TICK if scene else l3.PLAYER_UPDATE
            for _ in range(64):
                if self.wait_bp([at], 5.0) != at:
                    raise SystemExit(f"no stop at {at:#x} within 5 s")
                r = g.regs()
                if scene or r["ecx"] == ent:
                    break
            else:
                raise SystemExit(f"64 player updates, none of entity {ent:#x}")
        t0 = time.monotonic()
        crit = g.u32(ent + 0x20)
        pd = g.u32(g.u32(l3.SCENE_PTR) + 0x2C)
        meta = {"label": label, "at": "scene" if scene else "update", "entity": ent,
                "level": g.read(pd, 0x50).split(b"\0")[0].decode("latin-1"),
                "pos": list(struct.unpack("<3f", g.read(crit + 0x15C, 12))),   # in the private file only
                "state": g.u32(ent + 0x94), "hp": struct.unpack("<i", g.read(crit + 0x210, 4))[0],
                "clock": struct.unpack("<d", g.read(ent + 0x18, 8))[0], "start_sha12": start_hash(g.read, ent),
                "tag": self.st.get("last_tag"), "xemu": self.st.get("xemu_version"),
                "iso_sha12": self.disc_sha12(), "taken": now()}
        if parent is not None:
            meta["parent"] = parent
        if scene:
            meta["scene"], meta["dt"] = struct.unpack("<II", g.read(r["esp"] + 4, 8))
        pmem = self.w / f"pmem-{label}.bin"
        try:
            dump = self.ram_dump(pmem)
            with pmem.open("rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as ram:
                pdes = g.read(l3.PDE_BASE, l3.PAGE)   # the page directory, by its self-map: its own frame
                read = l3.ram_reader(ram, struct.unpack_from("<I", pdes, 4 * (l3.PDE_BASE >> 22))[0] & ~0xFFF,
                                     g.read)
                for va in (l3.PDE_BASE, ent & ~0xFFF):
                    if read(va, l3.PAGE) != g.read(va, l3.PAGE):
                        raise SystemExit(f"the RAM dump isn't the guest's memory at {va:#x}")
                info = l3.write_snapshot(read, path, r, meta, self._high_runs(g, r, read, ram) if high else ())
        finally:
            pmem.unlink(missing_ok=True)
        g.cmd("?")   # no breakpoint left; halted at the start
        self.event(f"L3 snapshot {label}: {info['pages']} pages, sha12 {info['sha12']}")
        return {"path": str(path), **info, "seconds": round(time.monotonic() - t0, 2), "ram": dump["how"],
                "dump_s": dump["s"], "entity": hex(ent),
                **{k: meta[k] for k in ("label", "at", "level", "state", "hp", "tag", "xemu", "iso_sha12")}}

    def ram_dump(self, path: Path) -> dict:
        """All of guest RAM into ``path`` (in W, mode 0600: RAM holds console keys; the caller deletes it):
        QMP ``xemu-dump-ram`` (the fork build, Step X.22: one write, tens of milliseconds; ``gpu-sync`` off, so a
        dump never writes guest RAM), else ``pmemsave`` (an older build). Returns how, the size and the seconds."""
        os.close(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600))   # xemu would create it 0644
        t0 = time.monotonic()
        how, r = "xemu-dump-ram", self.qmp("xemu-dump-ram", filename=str(path), **{"gpu-sync": False})
        if r.get("error", {}).get("class") == "CommandNotFound":
            size = self.qmp("query-memory-size-summary")["return"]["base-memory"]
            how, r = "pmemsave", self.qmp("pmemsave", val=0, size=size, filename=str(path))
        size = path.stat().st_size
        if "error" in r or not size or (how == "xemu-dump-ram" and size != r["return"]["ram-size"]):
            raise SystemExit(f"{how} failed: {r.get('error')}")
        return {"how": how, "size": size, "s": round(time.monotonic() - t0, 3)}

    def _high_runs(self, g: RSP, r: dict, read, ram) -> list[tuple[int, int, object]]:
        """A format 3 snapshot's high runs: the halted thread's stack (its
        present pages from the TIB's StackLimit, fs:[8], to StackBase, fs:[4],
        and on to the next page that isn't present: the thread's TLS data
        sits at StackBase, and a step's frames go below ESP), its KTHREAD's
        page (fs:[0x28], under the stack: the CRT's per-thread data starts
        there), read by ``read`` (the dump's pages), and guest RAM (``ram``,
        the dump) as the kernel's window at 0x80000000 maps it (checked
        against the gdbstub's view of two of its pages)."""
        base, limit = struct.unpack("<II", read(r["fs_base"] + 4, 8))
        lo = limit & ~0xFFF
        if not lo <= r["esp"] < base <= lo + 0x100000:
            raise SystemExit(f"ESP {r['esp']:#x} isn't inside the TIB's stack ({limit:#x}, {base:#x})")
        runs: list[list[int]] = []
        for va in l3.present_pages(read, lo, (base & ~0xFFF) + 0x10000):
            if va >= base and not (runs and runs[-1][0] + runs[-1][1] == va):
                break                                       # past the stack and its TLS
            if runs and runs[-1][0] + runs[-1][1] == va:
                runs[-1][1] += 0x1000
            else:
                runs.append([va, 0x1000])
        size = len(ram)
        thread = struct.unpack("<I", read(r["fs_base"] + 0x28, 4))[0] & ~0xFFF
        if not (l3.HIGH <= thread < l3.HIGH + size or any(va <= thread < va + n for va, n in runs)) \
                and l3.present_pages(read, thread, thread + 0x1000):
            runs = sorted([*runs, [thread, 0x1000]])

        def window(va: int, n: int) -> bytes:
            return ram[va - l3.HIGH:va - l3.HIGH + n]
        for va in (l3.HIGH + 0x10000, r["fs_base"] & ~0xFFF):
            if l3.HIGH <= va < l3.HIGH + size and g.read(va, 0x1000) != window(va, 0x1000):
                raise SystemExit(f"guest RAM at {va - l3.HIGH:#x} isn't the kernel's page at {va:#x}")
        out = [(l3.HIGH, size, window), *((va, n, read) for va, n in runs)]
        return sorted(out, key=lambda h: h[0])

    def write_pad(self, pad: l3.Pad, *, stick_only: bool = False) -> None:
        """``pad`` into the active ControllerState in guest RAM, encoded as
        L3 writes it (``l3.pad_floats``): every float, or with
        ``stick_only`` the left stick alone (+0x00, +0x04), the buttons
        left to the FIFO pad. The one RAM pad writer (the replayer; a
        pilot's analog stick); the latches stay the game's."""
        g = self.halt()
        idx = g.u32(ACTIVE_PAD)
        data = l3.pad_floats(pad)
        g.write(CONTROLLER_STATE + 0x54 * (idx if idx < 4 else 0), data[:8] if stick_only else data)

    def _hooks_refused(self, rows: list, meta: dict, deep: bool) -> str | None:
        """Why ``replay`` can't run these rows through PC hooks (None: it can): a sandbox without v0.15's hooks and
        checkpoints or not deterministic (the run must repeat from its checkpoint), ``deep`` (the latches' map is a
        tree, which no fixed region holds), a scene start, or a row with writes past its pad after tick 0 (a
        teleport's request: a hook writes one region queue)."""
        if not (self.st.get("hooks") and self.st.get("checkpoints") and self.st.get("deterministic")):
            return "no PC hooks and checkpoints in a deterministic sandbox"
        if not rows:
            return "no tick to replay"
        if deep:
            return "a deep observation (the latches' tree has no fixed region)"
        if meta["at"] != "update":
            return "a scene-tick start"
        if any(rw.writes[1:] for rw in rows[1:]):
            return "a row writes more than its pad after tick 0"
        return None

    def _replay_by_hooks(self, pads: list, rows: list, meta: dict, timeout: float, stops: dict | None,
                         clock0: float, rate: float) -> list[dict] | None:
        """``replay`` through the fork's PC hooks (v0.15, Step X.32b; the recipe sitting x32 checked, equal to the
        gdbstub replay on every tick and in its end RAM, 8.6 ms a tick against 23.4): the start kept as a
        checkpoint, ``_hooks_pass`` runs the string with no stop; a diverge stop past which it ran goes back to the
        start and runs again to the entry after the first tick off (the same run, deterministic). Returns the rows,
        halted where the gdbstub replay halts, or None (an event says why), back at the start, for the gdbstub."""
        ent, m = meta["entity"], (stops or {}).get("diverge")
        self.checkpoint_save(REPLAY_START)
        try:
            t0 = time.monotonic()
            got, end = self._hooks_pass(pads, rows, ent, clock0, rate, len(rows), timeout, stops is not None)
            off = next((k for k, x in enumerate(got or ()) if (x["state"], x["hp"]) != (rows[k].state, rows[k].hp)
                        or math.dist(x["pos"], rows[k].pos) > m), None) if m is not None else None
            if got is not None and off is not None:
                if off + 1 < len(got):   # it ran past the entry after that tick: again from the start, to there
                    self._back_to_start(meta)
                    again, end = self._hooks_pass(pads, rows, ent, clock0, rate, off + 1, timeout, False)
                    if again is None or end["at"] != "entry" or \
                            [x["obs"] for x in again] != [x["obs"] for x in got[:off + 1]]:
                        self.event("replay by hooks: the run to the first tick off didn't repeat the first")
                        got = None
                    else:
                        got, end = again, {"at": "diverged"}
                elif end["at"] == "entry":   # (a load or a stall right after it ends it, as a gdbstub stop does)
                    end = {"at": "diverged"}
            if got is None:
                self._back_to_start(meta)
                return None
            g = self.halt()
            if end["at"] in ("entry", "diverged") and (g.regs()["eip"], g.regs()["ecx"]) != (l3.PLAYER_UPDATE, ent):
                raise SystemExit(f"the hooks replay ended at {g.regs()['eip']:#x}, not the player's update entry")
            if end["at"] == "load":
                end["level"] = level_path(g)
            if stops is not None:
                stops.update(**end, k=len(got))
            elif end["at"] != "entry":
                raise SystemExit(f"no stop within {timeout} s after {len(got)} ticks (a dialog or cutscene?)")
            s = time.monotonic() - t0
            self.event(f"replay by PC hooks: {len(got)} ticks, {1000 * s / max(1, len(got)):.1f} ms a tick, "
                       f"ended {end['at']}")
            return got
        finally:
            self.checkpoint_delete(REPLAY_START)

    def _back_to_start(self, meta: dict) -> None:
        """Restore the replay's start checkpoint (every RAM page compared, ``checkpoint_restore``) and check the
        start as ``replay`` did (halted there); the last tag loaded stays the start's (a snapshot names it). One that
        misses its start stops the sitting (AZ-703's misses were the incremental restore's, AZ-821)."""
        tag, ent = self.st.get("last_tag"), meta["entity"]
        self.checkpoint_restore(REPLAY_START)
        self.st["last_tag"] = tag
        g = self.halt()
        r = g.regs()
        if (r["eip"], r["ecx"], struct.unpack("<d", g.read(ent + 0x18, 8))[0], start_hash(g.read, ent)) \
                != (l3.PLAYER_UPDATE, ent, meta["clock"], meta["start_sha12"]):
            raise SystemExit(f"the replay's start checkpoint didn't bring back {meta['label']}'s start (halted at "
                             f"{r['eip']:#x})")

    def _hooks_pass(self, pads: list, rows: list, ent: int, clock0: float, rate: float, n: int, timeout: float,
                    load_stop: bool) -> tuple[list[dict] | None, dict]:
        """``n`` ticks of the string from the halted start, by three hooks (the fork's recipe, PROMPT-7 B): the
        pad's floats written at the player's update entry once its clock passed the start's (tick 0's, at the
        halted entry itself, written here as the gdbstub replay writes it), keyed on the event clock so a repeated
        call in one tick takes no entry, ``stop-empty`` ending the run at the entry after the last tick; the camera
        written over [esp+0x14] at 0x85276 (EBP the entity) where a row has one; the light observation's regions
        collected at the update's RETs. It runs ``max(60, timeout x 60)`` vblanks a call (``xemu-run-until`` to
        ``LOAD_LEVEL`` with ``load_stop``), so a chunk with no tick is a stall. Returns the rows and how it ended
        (``{"at": entry | load | stall}``), or None where the records can't be trusted (dropped, a tick whose
        camera hit missed while the camera queue runs, a region unread, the active pad moved)."""
        g = self.halt()
        idx = g.u32(ACTIVE_PAD)   # the pad goes where write_pad puts it: ControllerState[idx] (4 reads [0])
        pad_va = CONTROLLER_STATE + 0x54 * (idx if idx < 4 else 0)
        g.write(pad_va, l3.pad_floats(pads[0]))
        for va, data in rows[0].writes[1:]:
            g.write(va, data)
        clock, crit = hex(ent + 0x18), hex(ent + obs.ENT_CRITTER)
        key = {"addr": clock, "size": 8}
        cams = any(rw.cam is not None for rw in rows[:n])
        hooks = [{"pcs": [l3.PLAYER_UPDATE], "key": key,
                  "cond": [{"reg": "ecx", "op": "eq", "value": ent},
                           {"addr": clock, "size": 8, "type": "f", "op": "gt", "value": clock0}],
                  "write": [{"addr": hex(pad_va), "size": 0x48}], "set": [l3.pad_floats(p).hex() for p in pads[1:n]],
                  "stop-empty": True},
                 {"pcs": [l3.CAMERA_DIR], "key": key, "cond": [{"reg": "ebp", "op": "eq", "value": ent}],
                  "collect": [{"addr": "esp+0x14", "size": 8}],
                  **({"write": [{"addr": "esp+0x14", "size": 8}], "set": [(rw.cam or b"").hex() for rw in rows[:n]]}
                     if cams else {})},
                 {"pcs": list(l3.UPDATE_RETS), "key": key, "collect": [
                     {"addr": hex(ent), "size": obs.ENT_FALL_REF + 4},
                     {"addr": f"[{crit}]+{obs.CR_PD:#x}", "size": recipes.CR_HP + 8 - obs.CR_PD},
                     {"addr": f"[[{crit}]+{obs.CR_PD:#x}]+{recipes.PD_ARMOR:#x}",
                      "size": obs.PD_SHARED + 4 - recipes.PD_ARMOR},
                     {"addr": f"[[[{crit}]+{obs.CR_PD:#x}]+{recipes.PD_ARMOR:#x}]+{obs.ARMOR_SLOT:#x}",
                      "size": obs.ARMOR_GAUGE + 4 - obs.ARMOR_SLOT},
                     {"addr": f"[[[[{crit}]+{obs.CR_PD:#x}]+{recipes.PD_ARMOR:#x}]+{obs.ARMOR_SLOT:#x}]"
                              f"+{obs.SLOT_LEVEL:#x}", "size": obs.SLOT_FLAPS + 4 - obs.SLOT_LEVEL},
                     {"addr": hex(ACTIVE_PAD), "size": 4}]}]
        r = self.qmp("xemu-hooks-set", hooks=hooks)
        if "error" in r:
            self.event(f"replay by gdbstub stops: xemu-hooks-set: {r['error'].get('desc', r['error'])}")
            return None, {}
        ids = [h["id"] for h in r["return"]]
        recs, end, chunk = [], None, max(60, round(timeout * 60))
        try:   # from here every way out clears the hooks: the pad queue's stop-empty would end a later advance
            g.cmd("?")   # no breakpoint; let go of the gdbstub without a continue: the run starts at the halt
            g.s.close()
            self._drop_g()
            while end is None:
                self._refuse_after_timeout("the hooks replay")
                bound, f0 = self._bound(chunk), self.frame()["frame"] if self.st.get("timeout_ms") else None
                r = (self.qmp("xemu-run-until", until=[{"pc": LOAD_LEVEL}], frames=chunk, **bound) if load_stop
                     else self.qmp("xemu-frame-advance", frames=chunk, **bound))
                if "error" in r:
                    raise SystemExit(f"the hooks replay: {r['error'].get('desc', r['error'])}")
                res, h = r["return"], r["return"].get("hooks") or {}
                if res.get("timed-out") or res.get("reason") == "timeout":
                    raise self._timed_out("xemu-run-until" if load_stop else "xemu-frame-advance", chunk, res, f0,
                                          bound["timeout-ms"])
                if h.get("dropped"):
                    self.event(f"replay by hooks: {h['dropped']} records dropped")
                    return None, {}
                new = h.get("records") or []
                recs += new
                stop = h.get("stop") or {}
                if res.get("reason") == "empty" or (stop.get("hook") == ids[0] and stop.get("empty")):
                    end = {"at": "entry"}
                elif res.get("reason") == "hit":
                    end = {"at": "load"}
                elif res.get("stopped") or res.get("reason") in ("debug", "stopped", "mismatch"):
                    raise SystemExit(f"the hooks replay was stopped: {res.get('stopped') or res.get('reason')}")
                elif not any(x.get("hook") == ids[2] for x in new):
                    end = {"at": "stall"}
        finally:
            self.qmp("xemu-hooks-clear", ids=ids)
        out, seen = [], []
        for x in recs:
            if x.get("hook") == ids[1]:
                seen.append(x)
            elif x.get("hook") == ids[2]:
                k = len(out)
                if cams and len(seen) != 1:
                    self.event(f"replay by hooks: tick {k} took {len(seen)} camera entries")
                    return None, {}
                if cams and rows[k].cam is not None:
                    cam = rows[k].cam
                else:
                    cam = bytes.fromhex(seen[-1]["data"][0]) if seen and seen[-1]["data"][0] else None
                seen = []
                o = hooked_obs(x["data"], ent, cam)
                if o is None or x["data"][5] != struct.pack("<I", idx).hex():
                    self.event(f"replay by hooks: tick {k}'s observation wasn't all collected, or the pad moved")
                    return None, {}
                clk = struct.unpack_from("<d", bytes.fromhex(x["data"][0]), 0x18)[0]
                if round((clk - clock0) * rate) != k + 1:
                    raise SystemExit(f"the RET of tick {k} at clock key {round((clk - clock0) * rate)}: the replay "
                                     "lost a tick")
                out.append({"k": k, "pos": o.pos, "state": o.state, "hp": o.hp, "obs": o})
        return out, end

    def replay(self, pads: list, rows: list, meta: dict, *, timeout: float = 5.0, deep: bool = True,
               stops: dict | None = None) -> list[dict]:
        """Replay an L3 run (``rows``, from ``pads``) exactly: from the
        snapshot's start, where ``snapshot`` left the guest halted
        (checked: the stop, the entity, its event clock and start hash),
        at each of the player's update entries write the tick's pad
        (``write_pad``) and the row's other writes (a teleport's request),
        at 0x85276 the row's camera direction ([esp+0x14]), and at the
        update's RET read the observation L3's rows hold, with the same
        reader (``devkit.sim.obs``; ``deep``: the kit, inventory and
        flag hashes too). The main loop's poll and the latches are the
        game's own, its frames one scene tick each (``pin_pace``); ticks are
        counted by the event clock (a repeated report of one entry is
        folded). Returns a dict per tick (``k``, ``pos``,
        ``state``, ``hp``, ``obs``: positions, keep them private) and halts
        at the entry after the last tick, with no breakpoints.

        ``stops`` (D172's chain, Step X.12): a dict the replay fills with how
        it ended instead of raising when the game leaves the player's
        updates before the string's end: ``{"at": "entry"}`` (every tick
        replayed, halted at the next entry), ``{"at": "load", "k", "level"}``
        (a level load, ``load_level_from_path``: an exit fired; halted
        there) or ``{"at": "stall", "k"}`` (no player update within
        ``timeout``: a popup, a dialog or a cutscene; halted where it was).
        Given ``{"diverge": m}`` it also ends at the entry after the first
        tick whose state or HP isn't L3's or whose body centre is more than
        ``m`` metres off (``{"at": "diverged", "k"}``: a chain re-anchors
        there).

        On a deterministic v0.15 sandbox (``st["hooks"]``) a light replay
        (not ``deep``) from an update-entry start runs through the fork's PC
        hooks with no gdbstub stop (Step X.32b; ``_replay_by_hooks``): the
        same writes at the same instructions, the same observation, the same
        stops; anything it can't vouch for goes back to the start and replays
        by gdbstub stops."""
        g = self.halt()
        ent, start = meta["entity"], l3.SCENE_TICK if meta["at"] == "scene" else l3.PLAYER_UPDATE
        pin_pace(g)
        r = g.regs()
        clock0 = struct.unpack("<d", g.read(ent + 0x18, 8))[0]
        rate = struct.unpack("<d", g.read(l3.MAIN_RATE, 8))[0]   # ticks a second: 30, or fps_unlock's F (X.11)
        if (r["eip"], ent if meta["at"] == "scene" else r["ecx"], clock0, start_hash(g.read, ent)) \
                != (start, ent, meta["clock"], meta["start_sha12"]):
            raise SystemExit(f"the guest isn't at {meta['label']}'s start (halted at {r['eip']:#x}): take the "
                             "snapshot again and replay before anything resumes the guest")
        if (why := self._hooks_refused(rows, meta, deep)) is None:
            if (got := self._replay_by_hooks(pads, rows, meta, timeout, stops, clock0, rate)) is not None:
                return got
            g = self.halt()   # back at the start (its checkpoint): the gdbstub replays it
            r = g.regs()
        elif self.st.get("hooks"):
            self.event(f"replay by gdbstub stops: {why}")
        vas = [l3.PLAYER_UPDATE, l3.CAMERA_DIR, *l3.UPDATE_RETS, *((LOAD_LEVEL,) if stops is not None else ())]
        out: list[dict] = []
        cur = last = cam = None
        diverged = False
        arm(g, vas)
        try:
            while True:
                if r["eip"] == LOAD_LEVEL and stops is not None:
                    stops.update(at="load", k=len(out), level=level_path(g))
                    break
                if r["eip"] == l3.PLAYER_UPDATE and r["ecx"] == ent:
                    clock = struct.unpack("<d", self.read(ent + 0x18, 8))[0]
                    if clock != last:
                        last, k = clock, round((clock - clock0) * rate)
                        if k != len(out):
                            raise SystemExit(f"entry of tick {k} after {len(out)} rows: the replay lost a tick")
                        if diverged:
                            stops.update(at="diverged", k=len(out))
                            break
                        if k >= len(rows):
                            if stops is not None:
                                stops["at"] = "entry"
                            break
                        self.write_pad(pads[k])
                        for va, data in rows[k].writes[1:]:
                            g.write(va, data)
                        cur = k
                elif r["eip"] == l3.CAMERA_DIR and cur is not None:
                    if rows[cur].cam is not None:
                        g.write(r["esp"] + 0x14, rows[cur].cam)
                    cam = self.read(r["esp"] + 0x14, 8)
                elif r["eip"] in l3.UPDATE_RETS and cur is not None:
                    o = obs.read(self.read, ent, cam, deep=deep)   # the reader L3's rows use, at the same RET
                    out.append({"k": cur, "pos": o.pos, "state": o.state, "hp": o.hp, "obs": o})
                    diverged = stops is not None and stops.get("diverge") is not None and (
                        (o.state, o.hp) != (rows[cur].state, rows[cur].hp)
                        or math.dist(o.pos, rows[cur].pos) > stops["diverge"])
                    cur = cam = None
                resume(g, vas, r["eip"])
                self._halted = False
                if not self._wait(timeout):
                    if stops is not None:
                        stops.update(at="stall", k=len(out))
                        break
                    raise SystemExit(f"no stop within {timeout} s after {len(out)} ticks (a dialog or cutscene?)")
                r = g.regs()
        finally:
            g.cmd("?")
        return out

    def detach(self) -> None:
        """Close the gdbstub connection leaving the guest halted where it is
        (no breakpoints): ``snapshot --hold``, for a ``replay`` to follow."""
        if self._g is not None:
            self.halt().cmd("?")
            self._g.s.close()
            self._drop_g()

    # -- save states --
    def loadable(self, tag: str) -> bool:
        """The fixtures README's tags, the tags ``savevm`` saved in this
        sandbox (they live and die with its HDD clone, D110) and, on a
        private HDD, ``vanilla-rzp-*`` tags (Q250); never a July ``vm-*``
        state (hazard 1)."""
        return not tag.startswith("vm-") and (
            tag in oracle_tags(self.fixtures) or tag in self.st.get("saved_tags", [])
            or (self.st.get("hdd") is not None and tag.startswith(PRIVATE_TAG)))

    def _await_line(self, line: str, seen: int, timeout: float) -> bool:
        """Whether W's run log gets more than ``seen`` ``line`` lines within ``timeout`` (False at once if
        our xemu stopped)."""
        end, n = time.monotonic() + timeout, 0
        while log_count(self.w, line) <= seen:
            n += 1
            if time.monotonic() > end or (n % 20 == 0 and not self.alive()):   # ps once a second
                return False
            time.sleep(0.05)
        return True

    def _await_status_ready(self, timeout: float) -> bool:
        """(A build with ``query-xemu-status``) Whether xemu is ready within ``timeout``: ``ready`` from
        ``query-xemu-status`` on a negotiated connection, else ``XEMU_READY`` arriving on it (the fork's recipe:
        the event may go out before a client negotiates, the query then says so). False at once if our xemu
        stopped."""
        end = time.monotonic() + timeout
        try:
            with self._qmp_conn() as q:
                if q.execute(XEMU_STATUS)["return"]["ready"]:
                    return True
                while (left := end - time.monotonic()) > 0:
                    if q.wait_event("XEMU_READY", min(left, 1.0)) is not None:
                        return True
                    if not self.alive():
                        return False
                return False
        except (OSError, EOFError, ValueError, KeyError):
            return False

    def _loads(self) -> int:
        """The loads xemu has confirmed so far: ``query-xemu-status``'s count on a build that has it
        (``st["xemu_status"]``), else the run log's ``xemu: state loaded`` lines."""
        if self.st.get("xemu_status"):
            return self.qmp(XEMU_STATUS)["return"]["loads"]
        return log_count(self.w, LOADED)

    def _await_loaded(self, seen: int, timeout: float) -> bool:
        """Whether xemu confirms a load past ``seen`` (``_loads``) within ``timeout``: on a build with
        ``query-xemu-status`` its count (``XEMU_STATE_LOADED`` goes out before the load's reply, so the first
        query has it), else the run log's line; False at once if our xemu stopped."""
        if not self.st.get("xemu_status"):
            return self._await_line(LOADED, seen, timeout)
        end, n = time.monotonic() + timeout, 0
        while True:
            try:
                if self.qmp(XEMU_STATUS)["return"]["loads"] > seen:
                    return True
            except (OSError, EOFError, ValueError, KeyError):
                pass
            n += 1
            if time.monotonic() > end or (n % 20 == 0 and not self.alive()):
                return False
            time.sleep(0.05)

    def _loaded_what(self) -> str:
        """What confirms a load on this build, for an error."""
        return f"XEMU_STATE_LOADED ({XEMU_STATUS})" if self.st.get("xemu_status") else f"'{LOADED}'"

    def _slow(self) -> int:
        """``BACKGROUND_SCALE`` while an owner demo runs and this sandbox isn't it (D526: ours run at background
        priority beside one), else 1: the factor on ``READY_S`` and ``LOADED_S`` (Step X.61)."""
        return BACKGROUND_SCALE if self.st.get("owner_pad") is None and owner_demo() is not None else 1

    def await_ready(self) -> float:
        """Before a launch's first ``loadvm``. A build with ``query-xemu-status`` (Step X.33): until QMP says
        it is ready (``_await_status_ready``); one with the readiness lines: until it printed ``xemu: ready``
        (its machine and pads exist); either ``READY_S`` from the launch at most, then ``TimeoutError``. An
        older build: until QMP reports the guest running and ``info usb``
        lists the port-2 pad (the D98 states were saved with it attached;
        ``usb_ready``), no longer than ``LOADVM_AFTER_S`` after the gdbstub
        came up. That path stays though every fork sandbox runs v0.15 or later
        (Step X.32b): the kept build (``--app kept``, v0.13.3-37, which made
        the D98 states) and upstream xemu (R1.26's sitting B) print no ready
        line. Returns the seconds since the gdbstub came up."""
        if self.st.get("ready_at", -1) < self.st.get("launched_at", 0):
            ready = READY_S * self._slow()
            if self.st.get("xemu_status"):
                left = self.st["launched_at"] + ready - time.time()
                if not self._await_status_ready(left):
                    raise TimeoutError(f"not ready ({XEMU_STATUS}, XEMU_READY) within {ready:.0f} s of the "
                                       f"launch ({'alive' if self.alive() else exit_cause(self.w)})")
            elif self.st.get("ready_line"):
                left = self.st["launched_at"] + ready - time.time()
                if not self._await_line(READY, 0, left):
                    raise TimeoutError(f"no '{READY}' within {ready:.0f} s of the launch "
                                       f"({'alive' if self.alive() else exit_cause(self.w)})")
            else:
                while time.time() < self.st["gdb_ready_at"] + LOADVM_AFTER_S:
                    try:
                        if self.status() == "running" and usb_ready(self._hmp("info usb")):
                            break
                    except (OSError, EOFError, ValueError):
                        pass
                    time.sleep(0.5)
            t = time.time()
            self.st.update(ready_at=t, ready_s=round(t - self.st["gdb_ready_at"], 1),
                           ready_launch_s=round(t - self.st.get("launched_at", t), 2))
            self._save()
        return self.st["ready_s"]

    def tag_disc(self, tag: str) -> str:
        """The disc a ``loadvm`` of ``tag`` puts in the tray when the caller names none (AZ-465: X.34's hand-over load
        named none and put the vanilla disc back under a build's state): the disc the state was saved with, as this
        sandbox recorded it (a warm build state's build, a parked start's disc, the tray at a ``savevm``); else, for
        any other tag, ``dvd.iso`` (the oracle states and private-drive tags are saved on the vanilla disc). An owner
        demo never takes that default: a tag whose disc it didn't record needs ``disc=``."""
        for known in (self.st.get("warm", {}).get(tag), self.st.get("parked", {}).get(tag),
                      {"disc": self.st.get("tag_discs", {}).get(tag)}):
            if known and known.get("disc"):
                return known["disc"]
        if self.st.get("owner_pad"):
            raise SystemExit(f"refusing loadvm {tag!r} in an owner demo with no disc named: this sandbox didn't save "
                             f"it, so the disc it was saved with is unknown; name it (disc='dvd.iso', the CLI's --disc "
                             f"dvd.iso, for the vanilla disc, or the build's name in W) (AZ-465)")
        return "dvd.iso"

    def loadvm(self, tag: str, *, halt_at_tick: bool = True, tick_timeout: float = 10.0,
               disc: str | None = None, paused: bool = False, pads: dict[str, str] | None = None) -> dict:
        """``loadvm`` a loadable tag once the launch is ready
        (``await_ready``), with its disc in the tray first (a medium change
        outlives ``loadvm``, s6 §8): ``disc``, else the disc the state was
        saved with (``tag_disc``: a warm build state's build, a tag this
        sandbox saved with the build in the tray), else ``W/dvd.iso``; an
        owner demo refuses a load whose disc it can't name. The load's event
        and its result name the disc (AZ-465). The pads the state holds go in
        first (``_pads``: ``pads``, the ``info usb`` devices it was saved with,
        else those this sandbox recorded at its ``savevm``; an owner demo waits
        for the owner's pad). Then, by default, run to the
        first player tick and stay halted there: a running VM is stopped
        before the load, so the load keeps it stopped and the halt is the
        load's own first tick (a VM that ran ran on past a varying number of
        ticks before the gdbstub's attach halted it: sitting x32d, Step
        X.32). A build with the readiness
        lines must confirm it (``LOADED_S``; ``_await_loaded``); an
        older build's first ``loadvm`` that fails before ``LOADVM_AFTER_S``
        is tried once more at that mark. Without ``halt_at_tick`` the guest
        runs after it (a deterministic launch's first, ``-S``, too), and with
        ``paused`` it stays paused for input written after the load, then
        ``frame_advance`` (Step X.30: a load drops lines queued before it).
        A load that leaves the VM stopped (``paused`` or ``halt_at_tick``) on
        a build with incremental restores (v0.15, ``_keeps_loads``) keeps the
        load as an in-memory checkpoint (``LOAD_CHECKPOINT``) and loads the tag
        again in this xemu by restoring it incrementally (``how``: loadvm or
        checkpoint; 4.5-5.8 ms against 25.5, the same machine; Step X.32b); a
        ``savevm`` or ``park`` of the tag drops it, and a ``loadvm`` of another
        tag drops it and every other checkpoint (``_drop_checkpoints_for``).
        Returns the timings and that tick's row."""
        if not self.loadable(tag):
            raise SystemExit(f"refusing loadvm {tag!r}: not an oracle tag in "
                             f"{self.fixtures / 'README.md'} or one saved in this sandbox")
        disc = disc or self.tag_disc(tag)
        ready_s = self.await_ready()
        pad_wait_s = self._pads(tag, pads or self.st.get("tag_usb", {}).get(tag))
        self.release()
        if (held := self.dvd()) != disc:
            self.insert(disc)
            self.event(f"{disc} into the tray (it held {held})")
        stopped = paused or halt_at_tick
        if stopped and self.status() == "running":
            self.qmp("stop")
        ck, kept, loaded_s = LOAD_CHECKPOINT.format(tag), None, LOADED_S * self._slow()
        keep = stopped and self._keeps_loads()
        t0 = time.monotonic()
        if keep and self.checkpoints().get(ck, {}).get("disc") == disc:   # this xemu loaded it before (Step X.32b)
            c = self.checkpoint_restore(ck, line_s=loaded_s)
            how, out = "checkpoint", "ok" if c["state_loaded"] is not False else (
                f"no {self._loaded_what()} within {loaded_s:.0f} s ({'alive' if self.alive() else exit_cause(self.w)})")
        else:
            how = "loadvm"
            self._drop_checkpoints_for(tag)
            self._load_drops_input(f"loadvm {tag}")
            loaded = self._loads()
            out = (self._hmp(f"loadvm {tag}") or "").strip() or "ok"
            if out != "ok" and not self.st.get("ready_line") \
                    and (left := self.st["gdb_ready_at"] + LOADVM_AFTER_S - time.time()) > 0:
                self.event(f"loadvm {tag} {ready_s} s after the gdbstub: {out[:120]}; again in {left:.0f} s")
                time.sleep(left)
                out = (self._hmp(f"loadvm {tag}") or "").strip() or "ok"
            if out == "ok" and self.st.get("ready_line") and not self._await_loaded(loaded, loaded_s):
                out = (f"no {self._loaded_what()} within {loaded_s:.0f} s "
                       f"({'alive' if self.alive() else exit_cause(self.w)})")
            if out == "ok" and keep:   # the load as it is, the VM stopped and nothing run: the next load's start
                kept = self.checkpoint_save(ck, disc)["s"]
        res = {"tag": tag, "disc": disc, "loadvm": out, "how": how, "ready_s": ready_s,
               "loadvm_s": round(time.monotonic() - t0, 3) if kept is None else round(time.monotonic() - t0 - kept, 3),
               "status": self.status() if self.alive() else "exited",
               **({"pad_wait_s": pad_wait_s} if pad_wait_s is not None else {}),
               **({"checkpoint_s": kept} if kept is not None else {})}
        if res["loadvm"] != "ok":
            raise SystemExit(f"loadvm {tag} (disc {disc}): {res['loadvm']}")
        self.st["last_tag"] = tag
        self.st.pop("timed_out", None)   # a load's point again (Step X.94)
        self.event(f"{how} {tag} (disc {disc})" if how == "loadvm" else f"loadvm {tag} by its checkpoint (disc {disc})")
        if self.st.get("owner_pad") and tag not in self.st.get("tag_usb", {}):
            self.event(f"{tag} wasn't saved in this demo: xemu's Snapshots menu loads it without asking only when the "
                       f"tray holds its disc's image (by the fingerprint a v0.15+ save keeps, or its saved image file), "
                       f"else it asks (Load Anyway); savevm it in this sandbox for a silent menu load (AZ-466)")
        if not halt_at_tick and not paused and res["status"] == "prelaunch":   # a deterministic first load (-S): run
            self.qmp("cont")
        if halt_at_tick and not paused:
            t1 = time.monotonic()
            if self.wait_bp([PLAYER_TICK], tick_timeout) == PLAYER_TICK:
                res["first_tick_s"] = round(time.monotonic() - t1, 3)
                r = self.g.regs()
                ent = self.g.u32(r["esp"] + 4)
                res["entity"] = hex(ent)
                res["row"] = self._jsonrow({**self.entity_row(ent), **self.chain(ent)})
            else:
                res["first_tick"] = f"no player tick within {tick_timeout} s (a menu, dialog or cutscene)"
        return res

    def savevm(self, tag: str):
        """``savevm`` into this sandbox's HDD clone only; never a README tag or a ``vm-*`` name. A checkpoint: the
        run that goes on is the one every later load of the tag gives. Deterministic on a build with continuity
        (v0.14-36, Step X.30) the save itself does that; otherwise (a real-time sitting, an older build, or a pipe
        line still waiting for its vblank, which a load drops) the VM stopped, ``savevm``, then ``loadvm`` of it
        (``_reload``, Step X.26), then it runs on. A deterministic guest the gdbstub holds halted is saved where it
        is and stays held, as ``park`` saves (AZ-732): letting it go first ran it for as long as the stop took on
        the host, on a loaded host past a player tick, so ``boot_build``'s warm save halted its boot ticks late."""
        if tag.startswith("vm-") or tag in oracle_tags(self.fixtures):
            raise SystemExit(f"refusing savevm {tag!r}: an oracle tag or a vm-* name")
        if self._halted and self._g is not None and self.st.get("deterministic"):
            self._g.cmd("?")   # every breakpoint lifted; the VM stays stopped
        else:
            self.release()
        held = self.dvd()
        if self.st.get("owner_pad") and (not held or held.startswith("/")):   # before the stop: the owner plays on
            raise SystemExit(f"refusing savevm {tag!r} in an owner demo with {held or 'no disc'} in the tray: its "
                             "states are saved under a disc in this sandbox: its loads put that image back, and its "
                             "Snapshots menu then loads them without asking (AZ-466)")
        if running := self.status() == "running":
            self.qmp("stop")
        self.checkpoint_delete(LOAD_CHECKPOINT.format(tag))   # its load is the new state from now on
        out = self._hmp(f"savevm {tag}")
        self.st["saved_tags"] = sorted({*self.st.get("saved_tags", []), tag})
        self.st.setdefault("tag_discs", {})[tag] = held   # its loads put it back (tag_disc, AZ-465)
        if self.st.get("owner_pad"):   # the pads a load of it needs (_pads), and where the menu finds its disc
            self.st.setdefault("tag_usb", {})[tag] = self.usb()
            self.event(f"savevm {tag} (disc {held}; saved under the disc path {self.w}/{held}: xemu's Snapshots menu "
                       f"loads it without asking with that disc here, or, by the fingerprint a v0.15+ save keeps, "
                       f"wherever the tray holds that image)")
        else:
            self.event(f"savevm {tag} (disc {held})")
        if not (out or "").strip() and not self._keeps_run():
            self._reload(tag)
        if running:
            self.qmp("cont")
        return out

    def _keeps_loads(self) -> bool:
        """Whether ``loadvm`` keeps each tag's load as a checkpoint and loads it again by an incremental restore: a
        build with them (``st["incremental"]``, v0.15), except an owner demo, whose loads wait for the owner's
        pad and plug the pads a state holds (AZ-466)."""
        return bool(self.st.get("incremental")) and not self.st.get("owner_pad")

    def _drop_checkpoints_for(self, tag: str) -> None:
        """Before an HMP ``loadvm`` of ``tag`` (``loadvm``, ``unpark``): drop every in-memory checkpoint but the
        tag's own load (``LOAD_CHECKPOINT``). That load reverts the qcow2 to the tag's disk outside the fork's
        checkpoints, which keep only the sectors the guest writes through IDE (a checkpoint restore keeps the
        others in step; an HMP load tells none), so another state's checkpoint restored after it would put that
        state's RAM over this tag's disk (the save files a level exit writes, a build's cached game files).
        ``_reload`` drops none: it loads the tag just saved, whose disk is the one there."""
        keep = LOAD_CHECKPOINT.format(tag)
        for name in [n for n in self.checkpoints() if n != keep]:
            self.checkpoint_delete(name)

    def _keeps_run(self) -> bool:
        """Whether a save made now is the run that goes on past it (Step X.30): a deterministic sandbox on a build
        whose icount saves carry the host-side state (``CONTINUITY_MARK``), with no pipe line still waiting for its
        vblank (the continued run would apply it; a load drops it)."""
        return bool(self.st.get("continuity")) and not self._input_pending()

    def _input_pending(self) -> bool:
        """(Continuity) whether a pipe line written (``send``) hasn't reached the pad yet."""
        return self._due > 0 and self.frame()["frame"] < self._due

    def _load_drops_input(self, what: str) -> None:
        """Before a load (``loadvm``, its reload, ``unpark``, ``checkpoint_restore``): pipe lines queued before a
        load are dropped, so a run's input is written after its load (Step X.30); one written before is reported.
        D200's guard (Step X.31a): a second load in one deterministic offscreen Vulkan process is warned by name
        on a build before v0.15's load fix (``LOAD_FIX_MARK``: v0.14-36's repeated load diverged about 1 time in 7
        there; on v0.15 and v0.15.1 seven such loads ended on one RAM, sittings x32 and x40; Step X.32b)."""
        if self.st.get("continuity") and self._input_pending():
            self.event(f"{what} drops pipe input written before it (write a run's input after its load)")
            log(f"warning: {what} drops pipe input written before it: write a run's input after its load")
        self._due = 0
        same = self.st.get("loads_pid") == self.st.get("pid")
        n = self.st["loads_in_process"] = (self.st.get("loads_in_process", 0) if same else 0) + 1
        self.st["loads_pid"] = self.st.get("pid")
        if n > 1 and self.headless == "1" and self.st.get("deterministic") and not self.st.get("load_fix"):
            msg = (f"D200: {what} is load {n} in this offscreen Vulkan process, where a repeated load diverges about "
                   "1 time in 7 (the fork's known issue): relaunch before a load whose pictures or RAM must reproduce")
            self.event(msg)
            log(f"warning: {msg}")

    def _reload(self, tag: str) -> float:
        """The checkpoint recipe's second half (Step X.26; the fork's README): ``loadvm`` the tag just saved, the
        VM's run state kept (a stopped or halted guest stays so). Without continuity (``_keeps_run``) a run
        continued past its ``savevm`` and a run loaded from it differ from the next frame on (a load restarts host
        audio state, the resampler's and filters' history, which such a save doesn't hold); after this load both
        are one run. Returns its seconds."""
        self._load_drops_input(f"loadvm {tag} (the checkpoint's reload)")
        loaded = self._loads()
        t0 = time.monotonic()
        out = (self._hmp(f"loadvm {tag}") or "").strip() or "ok"
        if out != "ok":
            raise SystemExit(f"loadvm {tag} (the checkpoint's reload): {out}")
        self.st.pop("timed_out", None)
        if self.st.get("ready_line"):
            self._await_loaded(loaded, UNPARK_LINE_S)
        s = round(time.monotonic() - t0, 3)
        self.event(f"loadvm {tag} (the checkpoint's reload, {s} s)")
        return s

    def park(self, tag: str) -> dict:
        """D172's parked start (Step X.12): ``savevm`` into this sandbox's
        HDD clone (never D98's drive, D102) with the guest held halted where
        it is (an L3 snapshot's start: the player's update entry), so the
        sandbox may be released during a long search and the start brought
        back by ``unpark``. ``savevm`` doesn't resume a stopped guest; the
        stop is checked after it. A checkpoint: the run that goes on from
        here is the one every ``unpark`` gives: deterministic on a build with
        continuity the save itself is (Step X.30, ``reload_s`` None),
        otherwise ``loadvm`` of it follows, the guest still held
        (``_reload``, ``reload_s``; Step X.26). On a build with in-memory
        checkpoints it is kept in host memory too (``checkpoint_s``), so an
        ``unpark`` in this xemu restores it without the qcow2. Returns the
        seconds and the status."""
        if tag.startswith("vm-") or tag in oracle_tags(self.fixtures):
            raise SystemExit(f"refusing savevm {tag!r}: an oracle tag or a vm-* name")
        g = self.halt()
        g.cmd("?")
        before = g.regs()
        self.checkpoint_delete(LOAD_CHECKPOINT.format(tag))
        t0 = time.monotonic()
        out = (self._hmp(f"savevm {tag}") or "").strip() or "ok"
        res = {"tag": tag, "savevm": out, "savevm_s": round(time.monotonic() - t0, 3), "status": self.status()}
        if out != "ok":
            raise SystemExit(f"savevm {tag}: {out}")
        if g.regs() != before:
            raise SystemExit(f"savevm {tag} moved the halted guest (status {res['status']})")
        res["reload_s"] = None if self._keeps_run() else self._reload(tag)
        if g.regs() != before:
            raise SystemExit(f"loadvm {tag} after its savevm didn't bring back the halted guest")
        self.st["saved_tags"] = sorted({*self.st.get("saved_tags", []), tag})
        self.st.setdefault("parked", {})[tag] = {"disc": self.dvd(), "eip": before["eip"], "saved": now(),
                                                 "xemu": self.st.get("xemu_version")}
        if self.st.get("checkpoints"):
            res["checkpoint_s"] = self.checkpoint_save(tag, self.st["parked"][tag]["disc"])["s"]
        self.event(f"savevm {tag} (parked, halted at {before['eip']:#x})")
        t0 = time.monotonic()
        res["kept_as"] = self.persist_parked().name
        res["persist_s"] = round(time.monotonic() - t0, 2)
        return res

    def parked_dir(self, name: str | None = None) -> Path:
        """Where this sandbox's parked starts outlive W (Step X.15): the
        private L3 store's ``parked/<W name>`` (mode 700)."""
        d = l3.store() / "parked"
        d.mkdir(mode=0o700, exist_ok=True)
        d = d / (name or self.w.name)
        d.mkdir(mode=0o700, exist_ok=True)
        return d

    def persist_parked(self) -> Path:
        """Keep the parked starts past a reboot, which clears /tmp and W
        with it: W's HDD clone (its ``savevm`` tags inside) and each parked
        disc, APFS-cloned into ``parked_dir()``, and ``parked.json`` (the
        tags and their discs). The guest is halted (the VM stopped, its
        drive flushed). ``Sandbox(hdd=<dir>/xbox_hdd.qcow2)`` and
        ``adopt_parked(<dir>)`` bring them back after one; ``down``
        deletes the folder unless kept."""
        d = self.parked_dir()
        part = d / "xbox_hdd.qcow2.part"
        part.unlink(missing_ok=True)
        subprocess.run(["cp", "-c", str(self.w / "xbox_hdd.qcow2"), str(part)], check=True)
        part.rename(d / "xbox_hdd.qcow2")
        for info in self.st.get("parked", {}).values():
            if (disc := info.get("disc")) and "/" not in disc and not (d / disc).exists():
                subprocess.run(["cp", "-c", str(self.w / disc), str(d / disc)], check=True)
        (d / "parked.json").write_text(json.dumps({"W": str(self.w), "parked": self.st.get("parked", {}),
                                                   "saved_tags": self.st.get("saved_tags", [])}, indent=1),
                                       encoding="utf-8")
        return d

    def adopt_parked(self, folder: Path | str) -> list[str]:
        """After a reboot: in a sandbox started on ``folder``'s drive
        (``Sandbox(hdd=<folder>/xbox_hdd.qcow2)``), take over the starts
        ``persist_parked`` kept there (their discs cloned into W, each
        disc's ``disc_sha12`` its source's, :func:`file_sha256` by content
        key), so ``unpark`` brings them back. Returns the tags."""
        folder = Path(folder)
        doc = json.loads((folder / "parked.json").read_text(encoding="utf-8"))
        if self.hdd is None or self.hdd.resolve() != (folder / "xbox_hdd.qcow2").resolve():
            raise SystemExit(f"start the sandbox on {folder}/xbox_hdd.qcow2 (hdd=) to adopt its parked starts")
        for info in doc["parked"].values():
            if (disc := info.get("disc")) and not (self.w / disc).exists():
                subprocess.run(["cp", "-c", str(folder / disc), str(self.w / disc)], check=True)
                self.st.setdefault("disc_sha12", {})[disc] = file_sha256(folder / disc)[:12]
        self.st.setdefault("parked", {}).update(doc["parked"])
        self.st["saved_tags"] = sorted({*self.st.get("saved_tags", []), *doc["saved_tags"]})
        self._save()
        self.event(f"adopted {len(doc['parked'])} parked starts from {folder.name}")
        return sorted(doc["parked"])

    def adopt_tags(self, tags: dict[str, dict]) -> list[str]:
        """A demo's tags (``xemu_demo.note_tag``'s meta: ``{tag: {"disc", "usb", ...}}``) as this sandbox's own, to
        replay them (AZ-439): it runs on a clone of the demo's drive (``hdd=``), which holds them; their discs (W's
        names) and pads go where ``loadvm`` takes them (``tag_disc``, ``_pads``). Returns the tags."""
        if self.hdd is None:
            raise SystemExit("adopt_tags: start the sandbox on the demo's drive (hdd=), which holds its tags")
        for tag, t in tags.items():
            if t.get("disc"):
                self.st.setdefault("tag_discs", {})[tag] = t["disc"]
            if t.get("usb"):
                self.st.setdefault("tag_usb", {})[tag] = t["usb"]
        self.st["saved_tags"] = sorted({*self.st.get("saved_tags", []), *tags})
        self.event(f"adopted {len(tags)} demo tags from the drive {self.hdd.name}")
        return sorted(tags)

    def unpark(self, tag: str, meta: dict | None = None) -> dict:
        """Bring back a ``park``ed start, halted: after a relaunch the
        launch's readiness first (``await_ready``), then the gdbstub
        attached (the guest stopped), the parked disc in the tray and
        ``loadvm`` (a stopped guest stays stopped). With ``meta`` (the L3
        snapshot's) the replayer's start check: the stop, the entity, its
        event clock and start hash; a checkpoint restore that fails it is
        dropped and the tag loaded from the qcow2 instead (AZ-694: sitting
        r116f's restores missed their start after a placement or a pilot,
        where a load of the same tag held it), the result's ``missed``
        naming the checkpoint. Returns the timings and ``at_start``.
        A start parked by a build of a newer savestate stream than this
        sandbox's (``state_stream``) is refused by name: v0.16.1's and
        v0.16.2's, v0.16.3's and v0.16.4's states don't load in v0.16 or the
        kept build (the NV2A's device section is version 5; Step X.61); v0.16.2's
        to v0.16.4's load in v0.16.1 and each other (Steps X.66, X.71, X.72)."""
        if tag not in self.st.get("parked", {}):
            raise SystemExit(f"{tag} isn't a start parked in this sandbox")
        by, mine = self.st["parked"][tag].get("xemu"), self.st.get("xemu_version")
        if (kb := state_stream(by)) is not None and (km := state_stream(mine)) is not None and kb > km:
            raise SystemExit(f"{tag} was parked by xemu {by}, newer than this sandbox's {mine}: a state saved by a newer "
                             "build doesn't load in an older one (v0.16.1's NV2A section is version 5): unpark it on "
                             f"{by} or later (--app)")
        fresh = self.st.get("ready_at", -1) < self.st.get("launched_at", 0)
        ready_s = self.await_ready() if fresh else None
        self._pads(tag, self.st.get("tag_usb", {}).get(tag))
        g = self.halt()
        g.cmd("?")
        if (held := self.dvd()) != (disc := self.st["parked"][tag]["disc"]):
            self.insert(disc)
            self.event(f"{disc} into the tray (it held {held})")
        missed = None
        while True:
            if tag in self.checkpoints():   # kept in this xemu's memory (Step X.30): the same load, no qcow2
                c = self.checkpoint_restore(tag, line_s=UNPARK_LINE_S)
                res = {"tag": tag, "loadvm": "ok", "loadvm_s": c["s"], "how": "checkpoint", "ready_s": ready_s,
                       "status": self.status(), "state_loaded": c["state_loaded"]}
            else:
                self._drop_checkpoints_for(tag)
                self._load_drops_input(f"loadvm {tag}")
                loaded = self._loads()
                t0 = time.monotonic()
                out = (self._hmp(f"loadvm {tag}") or "").strip() or "ok"
                res = {"tag": tag, "loadvm": out, "loadvm_s": round(time.monotonic() - t0, 3), "how": "loadvm",
                       "ready_s": ready_s, "status": self.status()}
                if out != "ok":
                    raise SystemExit(f"loadvm {tag}: {out}")
                self.st.pop("timed_out", None)   # the parked start's point again (Step X.94)
                if self.st.get("ready_line"):   # the fork build's confirmation (the guest held halted: a short wait)
                    res["state_loaded"] = self._await_loaded(loaded, UNPARK_LINE_S)
            self.event(f"{res['how']} {tag} (unparked)")
            r = g.regs()
            res["eip"] = hex(r["eip"])
            if meta is not None:   # replay's start check: a scene start halts at the scene tick's entry, ECX any
                ent, scene = meta["entity"], meta.get("at") == "scene"
                clock = struct.unpack("<d", g.read(ent + 0x18, 8))[0]
                res["at_start"] = (r["eip"], ent if scene else r["ecx"], clock, start_hash(g.read, ent)) == (
                    l3.SCENE_TICK if scene else l3.PLAYER_UPDATE, ent, meta["clock"], meta["start_sha12"])
                if not res["at_start"] and res["how"] == "checkpoint":   # AZ-694: the qcow2's load instead
                    missed = {"loadvm_s": res["loadvm_s"], "eip": res["eip"]}
                    self.event(f"checkpoint {tag} missed its start: loading the tag instead (AZ-694)")
                    self.checkpoint_delete(tag)
                    continue
            return {**res, **({"missed": missed} if missed else {})}

    # -- in-memory checkpoints (v0.14-36, Step X.30) --
    def checkpoints(self) -> dict[str, dict]:
        """The in-memory checkpoints this xemu holds (a relaunch loses them), oldest first: name -> its disc."""
        held = self.st.get("checkpoints_held") or {}
        return held.get("names", {}) if held.get("pid") == self.st.get("pid") else {}

    def checkpoint_save(self, name: str, disc: str | None = None) -> dict:
        """QMP ``xemu-checkpoint-save``: the whole machine in this xemu's memory as ``name`` (what ``savevm``
        writes; the VM keeps its run state, a halted guest stays halted). ``CHECKPOINTS_KEPT`` at most: the oldest
        is freed first, a kept load (``loadvm``'s) before any other. Returns its size, frame and seconds."""
        if not self.st.get("checkpoints"):
            raise SystemExit(f"checkpoint {name}: {self.app.name} has no in-memory checkpoints (v0.14-36 on)")
        names = dict(self.checkpoints())
        disc = disc or self.dvd()
        t0 = time.monotonic()
        r = self.qmp("xemu-checkpoint-save", name=name)
        if "error" in r:
            raise SystemExit(f"xemu-checkpoint-save {name}: {r['error'].get('desc', r['error'])}")
        res = {**r["return"], "s": round(time.monotonic() - t0, 3)}
        names.pop(name, None)
        names[name] = {"disc": disc}
        while len(names) > CHECKPOINTS_KEPT:   # a kept load goes before a parked start (loadvm makes it again)
            old = next((n for n in names if n.startswith(LOAD_CHECKPOINT.format("")) and n != name), next(iter(names)))
            self.qmp("xemu-checkpoint-delete", name=old)
            del names[old]
        self.st["checkpoints_held"] = {"pid": self.st.get("pid"), "names": names}
        self._save()
        return res

    def checkpoint_restore(self, name: str, line_s: float = LOADED_S) -> dict:
        """QMP ``xemu-checkpoint-restore``: load ``name`` as ``loadvm`` loads a snapshot (the machine reset and
        loaded, the disk sectors the guest wrote since put back, run again only if it ran; a halted guest stays
        halted), its disc in the tray first. Pipe input goes in after it (``_load_drops_input``). On a build with
        incremental restores (``INCREMENTAL_MARK``, v0.15) the pages written since the last save or restore are
        compared and written back first, and ``verify`` compares every other page too (a few ms more): xemu's
        dirty log misses some writes (sitting 2.172f: 132 pages after a pilot's retreat, the start check passing,
        and the guest bugchecked 0x1E in D3D or the timer heap, AZ-821), so a restore without it isn't the
        checkpoint. Each verified restore's ``pages-missed`` is counted (``_count_restore``): a nonzero is named in an
        event, on a build with AZ-822's fix (Step X.94) as a fork bug to report.
        Returns its seconds, the pages it copied and whether xemu confirmed the load (``_await_loaded``)."""
        if name not in (names := self.checkpoints()):
            raise SystemExit(f"no checkpoint {name!r} in this xemu (a relaunch loses them)")
        if (disc := names[name]["disc"]) and self.dvd() != disc:
            self.insert(disc)
        self._load_drops_input(f"checkpoint {name}")
        loaded = self._loads()
        t0 = time.monotonic()
        inc = {"incremental": True, "verify": True} if self.st.get("incremental") else {}
        r = self.qmp("xemu-checkpoint-restore", name=name, **inc)
        if "error" in r:
            raise SystemExit(f"xemu-checkpoint-restore {name}: {r['error'].get('desc', r['error'])}")
        if "pages-missed" in r["return"]:
            self._count_restore(name, int(r["return"]["pages-missed"]), r["return"])
        res = {**r["return"], "s": round(time.monotonic() - t0, 3),
               "state_loaded": self._await_loaded(loaded, line_s) if self.st.get("ready_line") else None}
        self.st["last_tag"] = name
        self.st.pop("timed_out", None)   # the checkpoint's point again (Step X.94)
        return res

    def _count_restore(self, name: str, missed: int, reply: dict | None = None) -> None:
        """(Step X.94) One verified restore into ``st["restores"]``: ``verified`` restores, ``pages_missed`` in all
        and the first 32 that missed any (``missed``: name, pages, when, xemu's pid). A nonzero is an event; on a
        build with AZ-822's fix (``DIRTY_LOG_FIX_MARK``) also a warning: the fork's dirty log missed writes again,
        and (Step X.96's standing rule) the fork's request drafted at once (``_draft_pages_request``), its path in
        the event, the warning and ``st["restores"]["requests"]``."""
        rs = self.st.setdefault("restores", {"verified": 0, "pages_missed": 0, "missed": []})
        rs["verified"] += 1
        if not missed:
            return
        rs["pages_missed"] += missed
        if len(rs["missed"]) < 32:
            rs["missed"].append({"name": name, "pages": missed, "at": now(), "pid": self.st.get("pid")})
        msg = f"checkpoint {name}: {missed} page(s) xemu's dirty log missed, written back (AZ-821)"
        if self.st.get("dirty_log_fix"):
            try:
                req = self._draft_pages_request(name, missed, reply or {})
                rs.setdefault("requests", []).append(str(req))
                msg += f"; on a build with AZ-822's fix: a fork bug, its request drafted in {req}: relay it now"
            except OSError as e:
                msg += f"; on a build with AZ-822's fix: a fork bug to report (no draft written: {e})"
            log(f"warning: {msg}")
        self.event(msg)

    def _draft_pages_request(self, name: str, missed: int, reply: dict) -> Path:
        """(Step X.96's standing rule) The fork's request for a verified restore that missed pages on a build with
        AZ-822's fix, in ``fork_requests_dir()`` as ``PAGES-MISSED-<W name>-<n>.txt``: the build, the sandbox, the
        checkpoint and the restore's reply counts, this sandbox's restores so far, and the call sequence since the
        checkpoint's save (``_calls``). Names, counts and sha12s only: no guest bytes, no positions."""
        calls = list(self._calls) or [{"call": "xemu-checkpoint-restore", "name": name}]   # its own call last
        at = next((i for i in range(len(calls) - 1, -1, -1)
                   if calls[i]["call"] == "xemu-checkpoint-save" and calls[i].get("name") == name), None)
        seq = calls[at:] if at is not None else calls
        app = Path(self.st.get("app") or self.app)
        try:
            binary = file_sha256(app / "Contents/MacOS/xemu")[:12]
        except OSError:
            binary = "?"
        rs = self.st.get("restores", {})
        d = fork_requests_dir()
        d.mkdir(parents=True, exist_ok=True)
        n = len(list(d.glob(f"PAGES-MISSED-{self.w.name}-*.txt"))) + 1
        out = d / f"PAGES-MISSED-{self.w.name}-{n}.txt"
        lines = [
            "To the xemu fork session (D894; the azurik-xemu-oracle skill's standing rule, Step X.96): a verified",
            "checkpoint restore missed pages on a build with AZ-822's fix (39d8f4e002). Relay at once; no workaround.",
            f"drafted: {now()}",
            f"build: xemu {self.st.get('xemu_version')} ({app.name}), binary sha256[:12] {binary}",
            f"sandbox: {self.w.name}, xemu pid {self.st.get('pid')}, launch {self.st.get('launches')}, "
            f"headless {self.st.get('headless')}, deterministic {self.st.get('deterministic')}, "
            f"NV2A address bits {self.st.get('nv2a_bits')}",
            f"checkpoint: {name} (the tag last loaded: {self.st.get('last_tag')}; disc "
            f"{(self.checkpoints().get(name) or {}).get('disc')})",
            f"restore reply: pages-missed {missed}"
            + "".join(f", {k} {v}" for k, v in reply.items() if k != "pages-missed" and isinstance(v, (int, float))),
            f"this sandbox's verified restores: {rs.get('verified')}, pages missed in all {rs.get('pages_missed')}",
            f"call sequence since the checkpoint's save ({len(seq)} calls"
            + ("" if at is not None else f"; its save is older than the {CALLS_KEPT} calls kept, so the last ones")
            + "; QMP and HMP by name, gdbstub memory writes counted, no data):",
            *(f"  {i + 1:3d}. {c['call']}" + "".join(f" {k}={v}" for k, v in c.items() if k != "call")
              + (f" -> pages-missed {missed}" if i == len(seq) - 1 else "") for i, c in enumerate(seq))]
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return out

    def checkpoint_delete(self, name: str) -> None:
        """Free an in-memory checkpoint."""
        if name in (names := dict(self.checkpoints())):
            self.qmp("xemu-checkpoint-delete", name=name)
            del names[name]
            self.st["checkpoints_held"] = {"pid": self.st.get("pid"), "names": names}
            self._save()

    def _open_warm(self, binary: bytes, det: bool) -> None:
        """Join the sitting's warm store (Step X.81d, ``xemu_warm``): keyed by the sitting, this xemu binary, the
        release, determinism and the drive it started from; idle stores swept first; the drive holding the most of
        the sitting's warm states cloned over W's before the launch (``_adopt_warm``). Only a sandbox whose guest RAM
        is the null renderer's (null, or offscreen ``null_ram``) publishes (``publish``): plain offscreen RAM isn't
        null's (sitting x61c), so a null row never starts from an offscreen-born state, while an offscreen sandbox
        loads a null-born one (sitting X.81d)."""
        root = l3.store() / "warm"
        key = {"sitting": self.warm_sitting, "xemu": hashlib.sha256(binary).hexdigest()[:12],
               "release": self.st["release"], "deterministic": bool(det), "hdd": self.st.get("hdd")}
        if gone := xemu_warm.sweep(root):
            self.event(f"warm store: {len(gone)} idle store(s) deleted")
        self.st["warm_store"] = {"dir": str(xemu_warm.WarmStore(root, key).dir), "key": key,
                                 "publish": self.headless == "null" or self.null_ram}
        self._adopt_warm()

    def _warm_store(self) -> xemu_warm.WarmStore | None:
        """The sitting's warm store this sandbox joined (``_open_warm``), or None."""
        ws = self.st.get("warm_store")
        return xemu_warm.WarmStore(Path(ws["dir"]).parent, ws["key"]) if ws else None

    def _adopt_warm(self, need: str | None = None) -> dict:
        """With this xemu down: W's drive swapped for the sitting's store drive that holds ``need`` (else one with
        more warm states than W's), their discs cloned in (``WarmStore.adopt``); never while W holds a tag no store
        drive does (a parked start, a spot). Its states are then all W's warm states. Returns them ({}: no swap)."""
        if (store := self._warm_store()) is None:
            return {}
        got = store.adopt(self.w, set(self.st.get("warm", {})), set(self.st.get("saved_tags", [])), need)
        if got:   # every tag W saved is a state the store holds: the new drive's are W's now
            self.st["warm"], self.st["saved_tags"] = got, sorted(got)
            self.st["warm_drive"] = drive = next(iter(got.values()))["drive"]
            self.event(f"warm store: drive {drive}, {len(got)} warm state(s): {', '.join(sorted(got))}")
            self._save()
        return got

    def stage(self, build: Path) -> tuple[str, str]:
        """``build`` APFS-cloned into W as ``b-<sha256[:12]>.iso`` (once per
        build: its warm state names that disc); returns the name and the hash
        (:func:`file_sha256`'s, by the build's content key; the disc's
        ``disc_sha12`` too, the clone's content being the build's)."""
        st = Path(build).stat()
        key = f"{Path(build).resolve()}|{st.st_size}|{st.st_mtime_ns}"
        if (sha12 := self.st.setdefault("staged", {}).get(key)) is None:
            sha12 = self.st["staged"][key] = file_sha256(Path(build))[:12]
        name = f"b-{sha12}.iso"
        if not (self.w / name).exists():
            subprocess.run(["cp", "-c", str(build), str(self.w / name)], check=True)   # an APFS clone
        self.st.setdefault("disc_sha12", {})[name] = sha12
        return name, sha12

    def boot_build(self, build: Path, tag: str = "vanilla-ig-w1", *, save: int = 1, warm: bool = True,
                   tries: int = BOOT_TRIES, want: str | None = None, a_frame: int | None = None) -> dict:
        """The modded-build path (skill section 6; s6, 5 of 5 boots): clone
        ``build`` into W (``stage``), ``loadvm`` a ``vanilla-ig-*`` tag
        (the save menu), ``reset_into`` the build, skip the movie, take
        the title to SaveGame #``save`` (``save_route``, on the boot state;
        on the D98 drive #1 is the all-powers character, #2 the new-game
        one, AZ-354), wait
        for steady play (``to_player_tick``) and check ``.text`` and
        ``SHIMS`` against the build, all but the data its shims write while
        the game runs (``shim_data``, found before the boot; AZ-300); ``want``:
        the level path the save loads, a try that loads another is a menu miss
        (AZ-363: under load a late preview of #1 passed for the cursor's move
        to #2). Halts
        at a player tick; the next ``loadvm`` of another tag puts that tag's
        own disc back (``tag_disc``).

        Warm (Step X.9): a booted build's state is saved into this
        sandbox's HDD clone as ``b-<iso sha12>-<tag>`` (never D98's drive,
        D102), so the same build boots again in this sandbox by one
        ``loadvm`` with its disc in the tray (``warm=False``: a cold boot,
        whose state isn't saved; a save other than #1 adds ``-s<save>`` to the
        tag). Self-healing: each failure of a boot try
        (``failure_class``: a dead pad AZ-296, a Continue that never runs
        AZ-302, the boot hang V22, a menu route that loads no level, no
        steady tick, an xemu that died or stalled) is recorded in
        ``incidents`` and relaunches xemu on its W (keeping its slot)
        before the next try, ``tries`` in all; any other error stops it.

        On guest frames (Step X.64, AZ-675; ``frame_boot``: a deterministic
        sandbox on v0.16.1): the tag loads paused, the reset stops there and
        ``boot_frames`` boots from it, so a build's boot is the same in every
        process; its schedule (frames from the reset) is ``frames``. A goes
        down on the save list at frame ``a_frame`` (default ``A_FRAME``, in
        the middle of the frames sitting x64 booted balthazar and the
        vanilla disc at f6 from) or once the list is ready, and each retry
        ``A_RETRY`` frames later (a schedule that hits AZ-695's race
        bugchecks in every process): AZ-695's sitting presses a given
        frame with ``tries=1``.
        A real-time sandbox walks the menus on the wall clock as before."""
        t0 = time.monotonic()
        name, sha12 = self.stage(build)
        cpu0 = self._cpuid_mark()   # only this boot's strict-CPUID faults stop it
        host0 = self.host_profile()
        if (got := xbe_layout(self._xbe(name))) is not (disc := xbe_layout(self._xbe("dvd.iso"))):
            raise SystemExit(f"{Path(build).name} is the {got.release.label} release; this sandbox's disc "
                             f"and states are the {disc.release.label} one's")
        self.st["build"] = name
        save_route(save)   # a bad index fails before the boot
        res: dict = {"build": Path(build).name, "iso_sha12": sha12,
                     "xbe_sha256": hashlib.sha256(self._xbe(name)).hexdigest()[:12], "tag": tag, "save": save,
                     "shim_data": [[hex(lo), hi - lo] for lo, hi in self.shim_data(name)], "warm": False,
                     "incidents": []}
        launches, key = self.st["launches"], f"b-{sha12}-{tag}" + (f"-s{save}" if save != 1 else "")
        if warm and (store := self._warm_store()) is not None and store.plan(
                key, self.st.get("warm", {}), self.st.get("saved_tags", [])) == "adopt":
            self._quit(relaunch=True)   # another sandbox of the sitting booted it (Step X.81d): its drive, then
            self._adopt_warm(key)       # a fresh process (as a row's), costs a relaunch, not a cold boot
            self.relaunch()
        if want is not None and self.st.get("warm", {}).get(key, {}).get("level", want) != want:
            self.st["warm"].pop(key)          # a warm state of another save (AZ-363): boot cold
        if warm and key in self.st.get("warm", {}):
            shared = self.st["warm"][key].get("drive")   # a state another sandbox of the sitting saved (Step X.81d)
            try:
                lv = self.loadvm(key, disc=name)
                if "entity" not in lv:
                    raise NoSteadyTick(f"{key}: {lv.get('first_tick')}")
                res.update(warm=True, level=self.st["warm"][key]["level"], tries=0,
                           **({"warm_drive": shared} if shared else {}))
            except (SystemExit, OSError, EOFError) as e:
                self._refuse_cpuid_faults(res["build"], cpu0)
                if (cls := self.failure_class(e)) is None:
                    if not shared or str(e).startswith("STOP:"):
                        raise
                    cls = "warm_load"   # a shared state this xemu refused: boot it cold (and publish that)
                res["incidents"].append(self._incident(0, cls, e))
                self.st["warm"].pop(key)
                self._recover(cls, e)
        for n in range(1, tries + 1):
            if res["warm"]:
                break
            try:
                self._stop = self._bugcheck_stop()   # a guest bugcheck or dead halt ends the try at once (AZ-628)
                if self.frame_boot():
                    self.loadvm(tag, halt_at_tick=False, disc="dvd.iso", paused=True)
                    self.reset_into(name, cont=False)
                    res["frames"] = self.boot_frames(save_route(save), want, a_frame=(
                        A_FRAME if a_frame is None else a_frame) + (n - 1) * A_RETRY, dead_after=DEAD_PAD)
                    res["level"], res["polls"] = res["frames"]["level"], res["frames"]["polls"]
                else:
                    res["start_presses"], res["level"], res["route_try"] = self.reset_to_level(tag, save, want)
                    res["walk"] = last_walk.get("tries")
                    res["polls"] = to_player_tick(self.g, self.w / "input.fifo", self.sc, stop=self._stop)
                self._halted = True
                res["tries"] = n
                break
            except (SystemExit, OSError, EOFError) as e:
                self._refuse_cpuid_faults(res["build"], cpu0)
                if (cls := self.failure_class(e)) is None:
                    raise
                res["incidents"].append(self._incident(n, cls, e))
                if n == tries:
                    raise BootFailed(f"{res['build']} didn't boot in {tries} tries: "
                                     f"{[i['class'] for i in res['incidents']]}; last: {e}") from None
                self._recover(cls, e)
            finally:
                self._stop = None
        res["relaunches"] = self.st["launches"] - launches
        g = self.g
        self._refuse_cpuid_faults(res["build"], cpu0)
        res["code"] = {"build": self.code_identity(name), "dvd.iso": self.code_identity("dvd.iso")}
        r = g.regs()
        ent = g.u32(r["esp"] + 4)
        res["entity"] = hex(ent)
        res["row"] = self._jsonrow({**self.entity_row(ent), **self.chain(ent)})
        if any(d for _, d in res["code"]["build"].values()):
            raise SystemExit(f"the guest isn't running {res['build']}'s default.xbe: {res['code']}")
        if warm and not res["warm"]:
            if err := (self.savevm(key) or "").strip():   # HMP's error text: no state to load or share
                self.event(f"savevm {key} failed ({err[:120]}): not kept warm, not published")
            else:
                self.st.setdefault("warm", {})[key] = {"disc": name, "level": res["level"], "saved": now()}
                res["warm_saved"] = key
            if self.wait_bp([PLAYER_TICK], 10.0) != PLAYER_TICK:
                raise SystemExit(f"no player tick after savevm {key}")
            if not err and (store := self._warm_store()) is not None and self.st["warm_store"].get("publish"):
                res["warm_published"] = store.publish(self.w, self.st["warm"])   # halted: the drive flushed
                self.event(f"warm store: {key} published as {res['warm_published']}")
        res["s"] = round(time.monotonic() - t0, 1)
        if (host := host_delta(host0, self.host_profile())) is not None:
            res["host_profile"] = host
        self._save()
        how = "warm" if res["warm"] else f"try {res['tries']}"
        self.event(f"booted {res['build']} from {tag}'s save #{save} into {res['level']} ({how}, {res['s']} s)")
        return res

    def cpuid_faults(self, every_launch: bool = False) -> list[dict]:
        """The strict-CPUID faults (``cpuid_faults``) in this xemu's run log, or ``every_launch``'s (``run.<n>.log``
        too, in launch order)."""
        return self._log_items(cpuid_faults, every_launch)

    def bugchecks(self, every_launch: bool = False) -> list[dict]:
        """The guest bugchecks and dead halts (``bugchecks``, ``XEMU_GUEST_BUGCHECK``) in this xemu's run log, or
        ``every_launch``'s (Step X.61); each bugcheck whose QMP event this sandbox heard (``_hear_bugchecks``, Step
        X.94) with that event's ``eip`` (KeBugCheckEx), ``stack_sha12`` and trap frame (``trap_eip``, ``trap_at``)."""
        heard = {(e.get("launch"), e.get("count")): e for e in self.st.get("bugcheck_events", [])}
        olds = sorted(int(m[1]) for q in self.w.glob("run.*.log")
                      if (m := re.fullmatch(r"run\.(\d+)\.log", q.name))) if every_launch else []
        out: list[dict] = []
        for launch in [*olds, None]:
            q = self.w / ("run.log" if launch is None else f"run.{launch}.log")
            with contextlib.suppress(OSError):
                n, items = 0, bugchecks(q.read_text(errors="replace", encoding="utf-8"))
                for b in items:
                    if b["kind"] == "bugcheck":
                        n += 1
                        e = heard.get((self.st.get("launches", 0) if launch is None else launch, n), {})
                        b.update({k: e[k] for k in ("stack_sha12", "trap_eip", "trap_at") if k in e},
                                 **({"eip": hex(e["regs"]["eip"])} if isinstance(e.get("regs"), dict)
                                    and "eip" in e["regs"] else {}))
                out += items
        return out

    def _hear_bugchecks(self, q: "QMP") -> None:
        """(Step X.94) The ``XEMU_GUEST_BUGCHECK`` events a QMP connection kept, scrubbed as they arrived
        (``scrub_event``: no stack bytes), moved into ``st["bugcheck_events"]`` with this launch's number, where
        ``bugchecks`` finds them by launch and count."""
        if got := [e for e in q.events if e.get("event") == "XEMU_GUEST_BUGCHECK"]:
            for e in got:
                q.events.remove(e)
                self.st.setdefault("bugcheck_events", []).append({"launch": self.st.get("launches", 0),
                                                                  **(e.get("data") or {})})
            self._save()

    def _log_items(self, parse, every_launch: bool) -> list[dict]:
        olds = sorted((int(m[1]), q) for q in self.w.glob("run.*.log")
                      if (m := re.fullmatch(r"run\.(\d+)\.log", q.name))) if every_launch else []
        out: list[dict] = []
        for q in [*(q for _, q in olds), self.w / "run.log"]:
            with contextlib.suppress(OSError):
                out += parse(q.read_text(errors="replace", encoding="utf-8"))
        return out

    def _bugcheck_stop(self):
        """A boot try's early end (Step X.61; AZ-628): a function the boot's waits call between polls, which returns
        a ``GuestBugcheck`` once this xemu's run log names a guest bugcheck or dead halt it didn't hold when the try
        began (else None), so the try ends at once, not after ``STEADY_WAIT_S``. None on a build without the
        report."""
        if not self.st.get("bugcheck"):
            return None
        launch, seen = self.st.get("launches", 0), len(self.bugchecks())

        def stop() -> GuestBugcheck | None:
            new = self.bugchecks()[seen if self.st.get("launches", 0) == launch else 0:]
            return GuestBugcheck(f"the guest stopped: {bugcheck_list(new)} (XEMU_GUEST_BUGCHECK)", new) if new else None
        return stop

    def _cpuid_mark(self) -> tuple[int, int]:
        """Where this xemu's strict-CPUID faults stand: (its launch, the faults its run log holds)."""
        return self.st.get("launches", 0), len(self.cpuid_faults())

    def _refuse_cpuid_faults(self, build: str, since: tuple[int, int]) -> None:
        """A boot whose xemu logged a strict-CPUID fault since ``since`` (``_cpuid_mark``; a relaunch's are all
        new) stops by name (Step X.58): the build runs code the Pentium III lacks (AZ-021), which a relaunch can't
        cure."""
        faults = self.cpuid_faults()
        if faults := faults[since[1]:] if self.st.get("launches", 0) == since[0] else faults:
            raise CpuidFault(f"{build} ran code the Pentium III lacks (XEMU_STRICT_CPUID's #UD; AZ-021): "
                             f"{fault_list(faults)}", faults)

    def failure_class(self, e: BaseException) -> str | None:
        """A boot try's failure, classified once (Step X.9), or None for an
        error a relaunch doesn't cure (a wrong save, a bad build, no slot)."""
        named = {DeadPad: "dead_pad", NoContinue: "no_continue", BootHang: "boot_hang", MenuMiss: "menu_miss",
                 NoSteadyTick: "no_steady_tick", GuestBugcheck: "bugcheck", AdvanceTimedOut: "timed_out"}
        if cls := next((v for k, v in named.items() if isinstance(e, k)), None):
            return cls
        if str(e).startswith("STOP:"):
            return None
        if not self.alive():   # a crash; its run log's cause (a lost GPU device among them) goes in the incident
            return "xemu_died"
        if isinstance(e, (TimeoutError, EOFError, OSError)):
            return "stalled"
        return None

    def _incident(self, n: int, cls: str, e: BaseException) -> dict:
        inc = {"try": n, "class": cls, "detail": f"{type(e).__name__}: {e}"[:200]}
        if getattr(e, "diag", None):   # where a try that found no steady tick was (AZ-628)
            inc["diag"] = e.diag
        if getattr(e, "frames", None):   # a try on guest frames: its schedule so far (Step X.64)
            inc["frames"] = e.frames
        if items := e.items if isinstance(e, GuestBugcheck) else (self._stop and (b := self._stop()) and b.items):
            inc["bugchecks"] = items   # the guest's own word on why (XEMU_GUEST_BUGCHECK, Step X.61)
        if cls == "xemu_died":
            inc["log"] = exit_cause(self.w)
        self.event(f"incident: try {n} {cls}: {inc['detail']}")
        return inc

    def _recover(self, cls: str, e: BaseException) -> None:
        """Before a boot's next try: a stalled xemu's ``sample`` into W (AZ-293), then quit it and relaunch
        on the same W, keeping its slot."""
        if cls == "stalled" and self.alive():
            subprocess.run(["sample", str(self.st["pid"]), "2", "-file", str(self.w / f"sample-{now()[11:19]}.txt")],
                           capture_output=True, timeout=60, check=False)
        self._relaunch_after(e)

    def reset_past_movie(self, tag: str) -> int:
        """``loadvm`` ``tag``, ``reset_into`` the staged build and skip
        prophecy.bik; returns the START presses. ``DEAD_PAD`` presses that
        don't skip it raise ``DeadPad`` (AZ-296; ``boot_build`` relaunches
        before its next try: a ``loadvm`` in that same xemu hung once,
        AZ-293)."""
        self.loadvm(tag, halt_at_tick=False, disc="dvd.iso")   # a vanilla-ig-* state: the vanilla disc's save menu
        self.reset_into(self.st.get("build", "mod.iso"))
        return skip_prophecy(self.halt(), self.w / "input.fifo", self.sc, dead_after=DEAD_PAD, stop=self._stop)

    def reset_to_level(self, tag: str, save: int = 1, want: str | None = None) -> tuple[int, str, int]:
        """``reset_past_movie``, then the title to SaveGame #``save``'s level
        (``save_route``); returns the START presses, the level and the
        route's try. A on the save that builds the scene with no Continue
        after it raises ``NoContinue`` (AZ-302; the route's B, B retries
        didn't recover one in sitting sight222kl)."""
        presses = self.reset_past_movie(tag)
        return presses, *walk_to_level(self.g, self.w / "input.fifo", self.sc, save_route(save), want,
                                       continue_s=CONTINUE_S)

    # -- boots on guest frames (Step X.64) --
    def _frame_waits(self) -> bool:
        """(Step X.96) Whether ``wait_bp`` runs on guest frames: boots do here (``frame_boot``) and xemu bounds a
        run's host time (``timeout-ms``, 0.16.4-3-g95e7ffc7ec)."""
        return self.frame_boot() and bool(self.st.get("timeout_ms"))

    def frame_boot(self) -> bool:
        """Whether boots here run on guest frames (``boot_frames``): a deterministic sandbox on a build with
        ``xemu-run`` that starts a VM the gdbstub holds from that instruction (v0.16.1). A real-time one (a window,
        an owner demo, real-time offscreen) walks the menus on the wall clock: its guest time follows the host, so
        no schedule repeats there."""
        return all(self.st.get(k) for k in ("deterministic", "xemu_run", "debug_advance"))

    def _run(self, frames: int, stops: list[dict] | None = None, lines: list[str] | None = None) -> dict:
        """One ``xemu-run`` from a stopped VM (``boot_frames``): ``lines`` (``@N``-tagged pipe lines) queued, then
        ``frames`` vblanks (1 at least) or until a ``stops`` entry ends it (``{"pc": va}``: before that instruction;
        an ``addr`` with ``lo``/``hi``: on the vblank it leaves the range), paused there; the gdbstub lets go first,
        without a continue. Returns the reply (``reason`` hit, value or budget; ``frame``; a hit's ``pc`` and
        ``regs``, a value's ``data``). Another VM stop raises ``AdvanceStopped``; a boot try's ``_stop`` (a guest
        bugcheck, AZ-628) its ``GuestBugcheck``."""
        self._refuse_after_timeout(f"{XEMU_RUN} {frames}")
        self._let_go()
        args = {"frames": max(1, int(frames)), **({"input": list(lines)} if lines else {}),
                **({"stop-when": list(stops)} if stops else {}), **self._bound(max(1, int(frames)))}
        start = self.frame()["frame"] if args.get("timeout-ms") else None
        try:
            r = self.qmp(XEMU_RUN, **args)
        except TimeoutError as e:
            raise TimeoutError(f"{XEMU_RUN} {args['frames']}: {e}: {self._hang_evidence()}") from e
        if "error" in r:
            raise SystemExit(f"{XEMU_RUN}: {r['error'].get('desc', r['error'])}")
        res = r["return"]
        if res.get("reason") == "timeout":
            raise self._timed_out(XEMU_RUN, args["frames"], res, start, args["timeout-ms"])
        if res.get("reason") in ("debug", "stopped"):
            raise AdvanceStopped(f"{XEMU_RUN} {args['frames']}: the VM stopped ({res.get('stopped')}: "
                                 f"{ADVANCE_STOPS.get(res.get('stopped'), 'a stop it did not make')}) at frame "
                                 f"{res.get('frame')}", res)
        if self._stop is not None and (e := self._stop()) is not None:
            raise e
        return res

    def _keys(self, button: str, at: int, hold: int = PRESS_HOLD) -> list[str]:
        """``button`` down at frame ``at`` (the frame counter's) and up ``hold`` frames later, as ``_run``'s lines."""
        sc = self.code(button)
        return [f"@{at} down {sc}", f"@{at + hold} up {sc}"]

    def _quiet(self, r: dict) -> tuple[dict, int]:
        """(``boot_frames``) Let a save preview's burst of ``INV_RESET`` calls pass: runs until ``QUIET_S`` goes by
        with none (8 runs at most). Returns the last reply and the calls let pass."""
        for n in range(8):
            r = self._run(vblanks(QUIET_S), [{"pc": INV_RESET}])
            if r["reason"] != "hit":
                return r, n
        return r, 8

    def boot_frames(self, route, want: str | None = None, *, a_frame: int = A_FRAME, steady_s: float | None = None,
                    dead_after: int | None = None, continue_s: float | None = CONTINUE_S) -> dict:
        """The boot from a stopped reset (``reset_into(name, cont=False)``, or a ``-S`` power-on) to steady play on
        guest frames (Step X.64, AZ-675; ``frame_boot``): every wait a budget in vblanks (the walk's bounds at
        60 Hz) that a PC or the boot state ends (``_run``), every press queued at its frame from the reset, so the
        same build boots the same way in every process. The movie: START 1 frame after prophecy.bik starts
        (``SKIP_HOLD``), again every ``SKIP_F`` frames until it ends (``dead_after`` presses: ``DeadPad``,
        AZ-296). The title (boot state ``MENU``), then ``route`` (``save_route``'s, ``TITLE``), each press held
        ``PRESS_HOLD``: START a frame after the title is up, until the list previews a save (``INV_RESET``), again
        after ``TITLE_AGAIN_S``; a
        cursor move right until the list previews the save it moved to, again every ``CURSOR_S`` (AZ-354; the last
        preview's burst let pass first, and after a press with none a stop then is its late preview, AZ-363); any
        other press its bound or a preview; the last (A) at frame ``a_frame`` (or a frame after the list is
        ready), held ``A_HOLD``, again after ``A_AGAIN_S`` with no checkpoint, until ``LOAD_LEVEL`` loads a level
        that isn't a ``bink:`` movie (another than ``want``: ``MenuMiss``; with ``continue_s``, a scene with no
        Continue within it: ``NoContinue``, AZ-302). Then ``to_player_tick`` on frames: a poll every ``POLL_GAP_F``
        frames waits ``POLL_F`` for the player tick, holds the HP (``hold_hp``, AZ-305) and presses A where none
        ran (a dialog), until the tick ran at every poll over ``steady_s`` (``STEADY_S``) of the player's event
        clock: halted there, before ``PLAYER_TICK``; ``NoSteadyTick`` after ``STEADY_WAIT_S`` of guest time, its
        ``diag`` ``to_player_tick``'s. Returns the schedule, each frame counted from the reset: ``movie``,
        ``skips``, ``title``, ``presses`` ([button, frame]), ``a`` (A's first), ``level``, ``level_at``,
        ``polls``, ``steady_at``; ``reset`` is the frame counter there."""
        rec: dict = {"reset": self.frame()["frame"], "a_asked": a_frame, "presses": []}
        try:
            return self._walk_frames(rec, route, want, a_frame, steady_s, dead_after, continue_s)
        except (SystemExit, OSError, EOFError) as e:
            e.frames = rec   # where the try was: its incident keeps it
            raise

    def _walk_frames(self, rec: dict, route, want, a_frame, steady_s, dead_after, continue_s) -> dict:
        """(``boot_frames``) The boot itself, ``rec`` the schedule it fills."""
        f0 = rec["reset"]

        def keys(button: str, at: int, hold: int = PRESS_HOLD) -> list[str]:
            rec["presses"].append([button, at - f0])
            return self._keys(button, at, hold)
        r = self._run(vblanks(PROPHECY_S), [{"pc": PROPHECY_STARTED}])
        if r["reason"] != "hit":
            raise BootHang(f"the game never started prophecy.bik in {vblanks(PROPHECY_S)} frames of the reset")
        rec["movie"], end, n = r["frame"] - f0, r["frame"] + vblanks(PROPHECY_S + 30.0), 0
        while True:
            n += 1
            r = self._run(SKIP_F, [{"pc": PROPHECY_ENDED}], keys("start", r["frame"] + 1, SKIP_HOLD))
            if r["reason"] == "hit":
                break
            if n == dead_after:
                raise DeadPad(f"{n} START presses didn't skip prophecy.bik: the pad is dead (AZ-296)")
            if r["frame"] >= end:
                raise BootHang("prophecy.bik never ended")
        rec["skips"] = n
        r = self._run(vblanks(MENU_S), [{"addr": hex(BOOT_STATE), "size": 4, "lo": 0, "hi": MENU - 1}])
        if r["reason"] != "value" or int.from_bytes(bytes.fromhex(r.get("data") or ""), "little") < MENU:
            raise MenuMiss(f"no title (boot state {MENU}) within {vblanks(MENU_S)} frames of the movie's end")
        rec["title"] = r["frame"] - f0
        *steps, (last, _) = route
        for i, (button, wait) in enumerate(steps):
            if button == "dpad_right":   # onto the next save: confirmed by its preview (AZ-354)
                for k in range(CURSOR_PRESSES):
                    r, burst = self._quiet(r)
                    if burst and k:   # the move pressed last came late (AZ-363)
                        break
                    r = self._run(1 + vblanks(CURSOR_S), [{"pc": INV_RESET}], keys(button, r["frame"] + 1))
                    if r["reason"] == "hit":
                        break
                else:
                    raise MenuMiss(f"the save list never moved right in {CURSOR_PRESSES} presses (AZ-354)")
                continue
            if i:
                r, _ = self._quiet(r)
            for _ in range(A_PRESSES):
                r = self._run(1 + vblanks(TITLE_AGAIN_S if i == 0 else wait), [{"pc": INV_RESET}],
                              keys(button, r["frame"] + 1))
                if r["reason"] == "hit" or i or self.read_u32(BOOT_STATE) == LIST:
                    break   # previewed, a press at the list that had its wait, or the list opened unpreviewed
            else:
                raise MenuMiss(f"START at the title opened no save list in {A_PRESSES} presses")
        at = max(r["frame"] + 1, f0 + a_frame)
        rec["a"], lines = at - f0, keys(last, at, A_HOLD)
        stops = [{"pc": LOAD_LEVEL}, *([{"pc": SCENE_RESET}, {"pc": START_SETUP}] if continue_s else [])]
        end, again, presses, seen, scene, path = at + vblanks(LEVEL_S), at + vblanks(A_AGAIN_S), 1, False, False, None
        while path is None:
            r = self._run((end if seen else min(end, again)) - r["frame"], stops, lines)
            lines = []
            if r["reason"] != "hit":
                if scene:
                    raise NoContinue(f"A on the save built the scene, but Continue ({START_SETUP:#x}) didn't run "
                                     f"within {vblanks(continue_s)} frames (AZ-302); the scene pointer "
                                     f"{SCENE_PTR:#x} {'set' if self.read_u32(SCENE_PTR) else 'not set'}")
                if not seen and presses < A_PRESSES and r["frame"] < end:   # no checkpoint: the list didn't take it
                    lines, presses = keys(last, r["frame"] + 1, A_HOLD), presses + 1
                    again = r["frame"] + 1 + vblanks(A_AGAIN_S)
                    continue
                raise MenuMiss(f"A loaded no level within {vblanks(LEVEL_S)} frames ({presses} presses)")
            seen = True
            if r["pc"] == LOAD_LEVEL:
                p = self.read_u32(r["regs"]["esp"] + 8)
                got = self.read(p, 0x50).split(b"\0")[0].decode("latin-1") if p else "<NULL>"
                path = None if got.startswith("bink:") else got   # a movie passes
            else:   # the scene's reset: Continue within continue_s; Continue: the level within as long
                scene, end = r["pc"] == SCENE_RESET, r["frame"] + vblanks(continue_s)
        rec.update(level=path, level_at=r["frame"] - f0, a_presses=presses)
        if want is not None and path != want:   # another save (AZ-363): a menu miss, which a boot retries
            raise MenuMiss(f"the menu walk loaded {path!r}, not {want}")
        rec["polls"] = self._steady_frames(STEADY_S if steady_s is None else steady_s, keys)
        rec["steady_at"] = self.frame()["frame"] - f0
        return rec

    def _steady_frames(self, steady: float, keys) -> int:
        """(``boot_frames``) ``to_player_tick`` on guest frames: the polls taken until the player tick ran at every
        poll over ``steady`` s of its event clock, halted there; ``keys`` makes (and records) a press's lines."""
        start, hp, n, ticks, best, ents, halt, lines = None, None, 0, 0, 0.0, [], None, None
        eips: collections.deque = collections.deque(maxlen=NO_TICK_EIPS)
        end = self.frame()["frame"] + vblanks(STEADY_WAIT_S)
        while True:
            n += 1
            r = self._run(POLL_F, [{"pc": PLAYER_TICK}], lines)
            lines = None
            if r["reason"] == "hit":
                ticks += 1
                ent = self.read_u32(r["regs"]["esp"] + 4)
                clock = struct.unpack("<d", self.read(ent + 0x18, 8))[0]
                hp = hold_hp(self.halt(), hp)
                if start is None or start[0] != ent:
                    start = (ent, clock)
                if ent not in ents:
                    ents.append(ent)
                best = max(best, clock - start[1])
                if clock - start[1] >= steady:
                    return n
            else:
                eips.append(eip := self.halt().regs()["eip"])
                start = None
                if eip == HALT_LOOP and halt is None:
                    with contextlib.suppress(OSError):
                        halt = [hex(v) for v in struct.unpack("<5I", self.read(BUGCHECK_DATA, 20))]
                lines = keys("a", r["frame"] + 1, A_HOLD)   # a dialog or cutscene: A
            if r["frame"] >= end:
                break
            if r["reason"] == "hit":
                self._run(POLL_GAP_F)
        diag = {"polls": n, "ticked": ticks, "entities": len(ents), "best_s": round(best, 3),
                "no_tick_eips": [hex(e) for e in eips], **({"bugcheck_data": halt} if halt else {})}
        raise NoSteadyTick(f"no steady player tick in {STEADY_WAIT_S / 60:g} minutes of guest time: a dialog or "
                           f"cutscene is still up ({ticks} of {n} polls ticked; no-tick EIPs "
                           f"{sorted(set(diag['no_tick_eips']))})", diag)

    def _relaunch_after(self, e: BaseException) -> None:
        """Quit this xemu and relaunch it on the same W, keeping its slot, before a retry."""
        self.event(f"{e}; relaunching before the retry")
        _renew_slot(self.w)
        self._quit(relaunch=True)   # an owner demo keeps its lease (AZ-601)
        self.relaunch()

    # -- input --
    def code(self, btn: str | int) -> int:
        return int(btn) if str(btn).isdigit() else self.sc[btn]

    def send(self, line: str, *, at: int | None = None, after: int | None = None) -> None:
        """One input-pipe line, applied on arrival (deterministic: at the next vblank), or (a fork build) at
        frame ``at`` or ``after`` frames from now (vblanks: ``frame``). In real time a frame-tagged line lands
        within a frame or two; deterministic, written while the VM is paused and then ``frame_advance``d, at its
        frame exactly. ``write_pad``, at the input builder, is the replayer's exact path in either.
        A ``down``/``up`` line takes one scancode: a button's name is refused (the fork's pipe reads only
        ``down <sc>``, so Step 2.153's ``down start`` did nothing; Step 2.158b)."""
        if at is not None and after is not None:
            raise ValueError("send: at or after, not both")
        words = line.split()
        if words and words[0][:1] in "@+" and words[0][1:].isdigit():   # a line's own frame tag
            words = words[1:]
        if words[:1] in (["down"], ["up"]) and not (len(words) == 2 and words[1].lstrip("-").isdigit()):
            name = " ".join(words[1:])
            raise ValueError(f"send {line!r}: the pipe takes a scancode, not a button name: send "
                             f"f\"{words[0]} {{sb.code({name!r})}}\", or hold, release_btn or press, which take names")
        tag = f"@{int(at)} " if at is not None else f"+{int(after)} " if after is not None else ""
        send_keys(self.w / "input.fifo", tag + line)
        if self.st.get("continuity"):   # the frame it reaches the pad by (one late at most): a save or load drops it
            f = int(at) if at is not None else self.frame()["frame"] + int(after or 0)
            self._due = max(self._due, f + 1)

    def axis(self, name: str, v: float, *, at: int | None = None, after: int | None = None) -> None:
        """An analog value through the pad's own path (the fork build's pipe): ``lx``, ``ly``, ``rx``, ``ry``
        in -1..1 (positive right / up; the raw axis over 32767: ``pipe_axis`` gives the value for a
        ControllerState float) or ``lt``, ``rt`` in 0..1; 0 hands it back to the keys. No RAM write."""
        if name not in ("lx", "ly", "rx", "ry", "lt", "rt") or not math.isfinite(v):
            raise ValueError(f"axis {name} {v!r}: lx, ly, rx, ry (-1..1) or lt, rt (0..1)")
        self.send(f"{'trigger' if name in ('lt', 'rt') else 'axis'} {name} {v:.6f}", at=at, after=after)

    def frame(self) -> dict:
        """QMP ``query-xemu-frame`` (a fork build): ``{frame, running}``, vblanks while the VM ran (v0.16.1: and
        ``vblank-ns``, kept as ``st["vblank_ns"]``)."""
        r = self.qmp("query-xemu-frame")
        if "error" in r:
            raise SystemExit(f"query-xemu-frame: {r['error'].get('desc', r['error'])} (not a fork build?)")
        return self._vblank(r["return"])

    def _vblank(self, reply: dict) -> dict:
        if "vblank-ns" in reply:
            self.st["vblank_ns"] = reply["vblank-ns"]
        return reply

    def guest_s(self, frames: int) -> float:
        """``frames`` vblanks in guest seconds: by the build's ``vblank-ns`` (v0.16.1; 20 ms under its opt-in PAL
        50 Hz), else 60 Hz (``VBLANK_NS``)."""
        return frames * self.st.get("vblank_ns", VBLANK_NS) / 1e9

    def frame_advance(self, frames: int = 1, *, trace: list[dict] | None = None, every: int | None = None,
                      gpu: bool | str = False, timeout_s: float | bool | None = None) -> dict:
        """QMP ``xemu-frame-advance``: run the VM ``frames`` vblanks, then pause it (0: just pause); QMP
        ``cont`` resumes it. The gdbstub lets go of the guest first (``release``). Returns ``{frame, running}``.
        ``trace`` (v0.14-36, Step X.30): regions ``{"address", "size"[, "virtual"]}`` (at most 256 of 1-4096
        bytes) read at every ``every``-th vblank (default each; the last always) before the guest sees it,
        returned as ``trace``: ``[{frame, data: [hex per region]}]``, exact under icount. A guest the gdbstub
        holds halted (a parked start) starts from that instruction on a build that can (v0.14-36): its
        breakpoints lifted and the gdbstub let go without a continue, so no guest time passes on the host clock.
        A VM stop it didn't make that ended it early (a later build's ``stopped``, PROMPT-8 D, ``ADVANCE_STOPS``)
        is an event naming the run state and ``ran``, the frames that ran (``ran_at_most`` when the VM ran before
        the advance began, as ``release`` lets it): a breakpoint's (``debug``, the debugger's stop, as
        ``debug-stop`` says) returns with them, any other raises ``AdvanceStopped``. An advance with no reply in
        ``ADVANCE_S`` (v0.14-36 held by such a stop, AZ-451; on a build with the watch monitor, once no frame moved
        for ``STALL_S``, with ``timeout-ms`` and a watch that answers one slice past that bound: ``_long_qmp``,
        AZ-685) first takes the hang's evidence (``hang_probe`` into
        W, which ``down`` then keeps: ``st["hang_probes"]``), before any later QMP call, gdbstub attach or signal,
        then raises ``TimeoutError`` naming it. ``gpu`` (v0.16.1, Step X.61): the advance's NV2A work counted,
        returned as ``gpu-counters`` (``{flips, total, max, tail}``; ``"per-flip"`` adds each flip's): set its ``max``
        against vanilla's with ``gpu_budget``. ``timeout_s`` (Step X.94, a build with ``TIMEOUT_MARK``): xemu pauses
        an advance still short of its frame after that many host seconds (None: ``advance_bound_s``; False: no
        bound), which raises ``AdvanceTimedOut`` (``_timed_out``), and a deterministic sandbox then advances no
        further until a checkpoint restore or a load."""
        if frames:
            self._refuse_after_timeout(f"xemu-frame-advance {frames}")
        self._let_go()
        args = {"frames": int(frames), **({"trace": trace} if trace else {}),
                **({"trace-every": int(every)} if every else {}), **({"gpu-counters": True} if gpu else {}),
                **({"gpu-counters-per-flip": True} if gpu == "per-flip" else {}), **self._bound(frames, timeout_s)}
        at = self.frame()   # a running VM (release let it go) moves on before the advance begins
        start = at["frame"]
        try:
            r = self.qmp("xemu-frame-advance", **args)
        except TimeoutError as e:
            said = str(e) if self.st.get("qmp_watch") else f"no reply in {ADVANCE_S:.0f} s"
            raise TimeoutError(f"xemu-frame-advance {frames}: {said} from frame {start} (AZ-451's wedge?): "
                               f"{self._hang_evidence()}") from e
        if "error" in r:
            raise SystemExit(f"xemu-frame-advance: {r['error'].get('desc', r['error'])} (not a fork build?)")
        res = self._vblank(r["return"])
        if res.get("timed-out"):
            raise self._timed_out("xemu-frame-advance", frames, res, start, args["timeout-ms"])
        if (state := res.get("stopped")) is not None:
            n, key = res["frame"] - start, "ran_at_most" if at.get("running") else "ran"
            res = {**res, key: n}
            ran = f"{n} frame(s)" if key == "ran" else f"at most {n} frame(s) (the VM ran before the advance)"
            why = f"the VM stopped ({state}: {ADVANCE_STOPS.get(state, 'a stop it did not make')})"
            self.event(f"xemu-frame-advance {frames}: {why} after {ran}, at frame {res['frame']}")
            if state != "debug":
                raise AdvanceStopped(f"xemu-frame-advance {frames}: {why} after {ran} of the {frames} asked; the VM "
                                     "is left as that stop left it", res)
        return res

    def _let_go(self) -> None:
        """Before a command that runs the VM itself (``frame_advance``, ``xemu-render-next``): a guest the gdbstub
        holds halted is let go without a continue on a build that starts it from that instruction (v0.14-36,
        ``st["debug_advance"]``), else ``release``."""
        if self.st.get("debug_advance") and self._g is not None and self._halted:
            try:
                self._g.cmd("?")   # every breakpoint lifted, the one under the PC too; the VM stays stopped
                self._g.s.close()
            except (OSError, EOFError):
                pass
            self._drop_g()
        else:
            self.release()

    def _bound(self, frames: int, timeout_s: float | bool | None = None) -> dict:
        """(Step X.94) An advance's or run's ``timeout-ms`` on a build with it (``TIMEOUT_MARK``): ``timeout_s``
        seconds, None ``advance_bound_s(frames)``, False none."""
        if not self.st.get("timeout_ms") or timeout_s is False:
            return {}
        return {"timeout-ms": max(1, round(1000 * (advance_bound_s(frames) if timeout_s is None else timeout_s)))}

    def _timed_out(self, cmd: str, frames: int, res: dict, start: int | None, ms: int) -> AdvanceTimedOut:
        """(Step X.94) xemu paused ``cmd`` at its ``timeout-ms`` before its frame: an event with the frames that ran,
        kept in ``st["timeouts"]`` (``down`` reports them), and the run's point marked (``st["timed_out"]``, this
        xemu's) so a deterministic sandbox refuses to run on from it (``_refuse_after_timeout``). Returns the error to
        raise."""
        ran = None if start is None or res.get("frame") is None else res["frame"] - start
        rec = {"cmd": cmd, "frames": int(frames), "ran": ran, "frame": res.get("frame"), "bound_s": ms / 1000,
               "at": now()}
        self.st.setdefault("timeouts", []).append(rec)
        self.st["timed_out"] = {**rec, "pid": self.st.get("pid")}
        msg = (f"{cmd} {frames}: timed out after {ms / 1000:g} s (timeout-ms), "
               f"{'?' if ran is None else ran} frame(s) ran, the VM paused at frame {res.get('frame')}: a host-time "
               "point, not a deterministic one: restore a checkpoint or loadvm before running on")
        self.event(msg)
        return AdvanceTimedOut(msg, {**res, "ran": ran})

    def _refuse_after_timeout(self, what: str) -> None:
        """(Step X.94) A deterministic sandbox whose xemu paused an advance or run at its timeout
        (``st["timed_out"]``) runs no advance or run from that point: its result wouldn't be the run a load gives."""
        t = self.st.get("timed_out")
        if self.st.get("deterministic") and t and t.get("pid") == self.st.get("pid"):
            raise SystemExit(f"{what}: refused: {t['cmd']} timed out at frame {t['frame']} (a host-time point, not a "
                             "deterministic one): restore a checkpoint or loadvm first (Step X.94)")

    def _hang_evidence(self) -> str:
        """``hang_probe`` of our xemu into W, first, before anything else touches it (AZ-451; the sitting's error
        path attaches the gdbstub, ``down`` sends QMP quit and signals): recorded in ``st["hang_probes"]``, so
        ``down`` keeps W. Says where it went."""
        pid = self.st.get("pid")
        if not self.alive():
            return f"xemu pid {pid} is gone, so no sample"
        probe = hang_probe(pid, self.w)
        self.st.setdefault("hang_probes", []).append(str(probe))
        self.event(f"hung advance: sampled pid {pid} into {probe} (W is kept)")
        return (f"sampled pid {pid} into {probe} (ps and lsof beside it; W is kept): read it before a relaunch "
                "(the xemu skill's hazard 15)")

    def play_recording(self, lines: list[str], frames: int | None = None, port: int | None = None,
                       **advance) -> dict:
        """Replay one section of an input recording (``recording_sections``; Step X.30): with the state it was
        recorded from loaded paused (``loadvm(tag, paused=True)``, called right after it) and the keyboard pad on
        the recorded port, each ``+N body`` line written as ``@<base+N> body``, base the frame the paused load left
        (on the pipe ``+N`` counts from the frame xemu reads the line at, so a raw ``+N`` read late lands late:
        AZ-510, the fork's PROMPT-9 07), other lines as they are, then ``frame_advance`` past the last (or
        ``frames``; ``trace``/``every`` as there). ``port``: the port it was recorded on (the demo's
        ``record_port``), refused unless the keyboard pad is there (``Sandbox(pad_port=)``: a demo on the owner's
        port 1 replays as the owner's pad with ``pad_port=1``, AZ-439). A paused xemu reads nothing from the pipe,
        so a section of more than ``PIPE_WINDOW`` bytes goes a window at a time (AZ-539: X.36's 4,836-line section
        filled the pipe, EAGAIN): a window's lines, then an advance to the frame before the next window's first
        line, at a multiple of ``every`` from base (a single advance's samples), which drains the pipe. On a build
        with ``xemu-input-queue`` (v0.16.1, ``st["input_queue"]``; Step X.61) the section goes in one call instead
        (``INPUT_QUEUE_MAX`` lines a call, every line accepted and none skipped, else it raises), then one advance;
        lines past the replayed frames aren't sent. Returns the last advance's reply, its ``trace`` every window's,
        ``windows`` how many."""
        if port is not None and int(port) != self.st.get("pad_port", 2):
            raise SystemExit(f"play_recording: recorded on port {port}, but this sandbox's keyboard pad is on port "
                             f"{self.st.get('pad_port', 2)}: replay it in a Sandbox(pad_port={port}) (AZ-439)")
        base, last, timed = self.frame()["frame"], 0, []
        for ln in lines:
            n = None
            if ln.startswith("+"):
                k, body = ln[1:].split(" ", 1)
                n, last = int(k), max(last, int(k))
                ln = f"@{base + n} {body}"
            timed.append((n, ln))
        if self.st.get("continuity"):
            self._due = max(self._due, base + last + 1)
        total, step = frames if frames is not None else last + 1, int(advance.get("every") or 1)
        if self.st.get("input_queue"):
            body = [ln for n, ln in timed if n is None or n <= total]
            if len(body) < len(timed):
                self.event(f"play_recording: {len(timed) - len(body)} line(s) past the {total} frames replayed, not sent")
            for k in range(0, len(body), INPUT_QUEUE_MAX):
                chunk = body[k:k + INPUT_QUEUE_MAX]
                r = self.qmp(INPUT_QUEUE, lines=chunk)
                if "error" in r:
                    raise SystemExit(f"{INPUT_QUEUE}: {r['error'].get('desc', r['error'])}")
                if (got := r["return"])["accepted"] != len(chunk) or got["skipped"]:
                    raise SystemExit(f"{INPUT_QUEUE}: {got['accepted']} of {len(chunk)} line(s) accepted, "
                                     f"{got['skipped']} skipped")
            r = self.frame_advance(total, **advance)
            return {**r, "trace": r.get("trace", []), "windows": 1, "queued": len(body)}
        done, size, trace, windows = 0, 0, [], 1
        for i, (n, ln) in enumerate(timed):
            if size + len(ln) + 1 > PIPE_WINDOW and size and n is not None:
                upto = min((n - 1) // step * step, total)
                if upto <= done:
                    upto = min(n - 1, total)
                if upto >= total and n >= total:   # the rest lands past this replay's end
                    self.event(f"play_recording: {len(timed) - i} line(s) from frame +{n} on, past the {total} frames "
                               "replayed, not written")
                    break
                if upto > done:
                    r = self.frame_advance(upto - done, **advance)
                    trace += r.get("trace", [])
                    if r.get("stopped") is not None:
                        return {**r, "trace": trace, "windows": windows}
                    done, size, windows = upto, 0, windows + 1
            send_keys(self.w / "input.fifo", ln)
            size += len(ln) + 1
        r = self.frame_advance(total - done, **advance)
        return {**r, "trace": trace + r.get("trace", []), "windows": windows}

    def screenshot(self, name: str, dest: Path | str | None = None) -> Path:
        """The guest's frame as a PNG through QMP ``screendump`` (never HMP's, which holds the main lock),
        into ``dest`` (default ``<out or W>/<name>.png``); xemu writes it in W first. Windowed and offscreen
        give the frame; the null renderer (the deterministic default) draws none, so it is refused: a sitting
        that needs pictures runs offscreen (``headless="1"``; with ``deterministic=True`` a picture taken with
        the VM paused, e.g. after ``frame_advance``, is the same bytes in every run, Step X.26, so a running
        one is refused there). A build before the fork's screendump answers with an error. On a build that dates
        its pictures (``DISPLAY_QUERY``, v0.15; AZ-452) ``last_picture`` is the query's reply just before the
        screendump, with ``stale`` True (and an event) when the guest hadn't flipped since the last load: the
        picture is then the loaded state's own saved frame, so advance until it flips. Older builds' pictures
        can be stale with no sign (retake one whose bytes equal the last's, AZ-452). On v0.16.1 (Step X.61) the
        query's ``picture-stale`` dates it (a checkpoint restore too, which ``flip-loads`` missed): a deterministic
        sandbox, or any whose VM isn't running (paused, or halted after a load), advances one vblank at a time until
        it is fresh (``PICTURE_STALE_ADVANCE`` at most, ``last_picture["advanced"]``: a caller counting frames adds
        them), a running real-time one polls it for a second, and one still stale raises. A
        ``null_ram`` sandbox first draws ``RENDER_FLIPS`` frames by ``xemu-render-next`` (``last_picture``'s
        ``render_flips`` and the frames it ran), the RAM staying null's."""
        if self.st.get("headless") == "null":
            raise SystemExit(f"screenshot {name}: the null renderer draws nothing; a sitting that needs pictures "
                             "runs offscreen (headless '1', deterministic=True for reproducible ones)")
        if self.st.get("deterministic") and self.status() == "running":
            raise SystemExit(f"screenshot {name}: a deterministic picture is taken paused: frame_advance (or halt) "
                             "first")
        drawn = {}
        if self.st.get("null_ram"):   # draws are skipped until asked: draw the next frames, then the VM pauses
            self._refuse_after_timeout(f"screenshot {name}")
            self._let_go()
            f0 = self.frame()["frame"]
            r = self.qmp("xemu-render-next", flips=RENDER_FLIPS)
            if "error" in r:
                raise SystemExit(f"screenshot {name}: xemu-render-next: {r['error'].get('desc', r['error'])}")
            got = r["return"]
            drawn = {"render_flips": got.get("render-flips", 0), "render_frames": got["frame"] - f0}
            if drawn["render_flips"] < RENDER_FLIPS:
                raise SystemExit(f"screenshot {name}: xemu-render-next drew {drawn['render_flips']} of {RENDER_FLIPS} "
                                 f"frames in its {drawn['render_frames']} vblanks (its frames cap): the guest isn't "
                                 "flipping (a halt, a load screen?)")
        if self.st.get("display_query"):   # before the screendump: a flip after it can't make a stale one look fresh
            d, advanced = self.qmp(DISPLAY_QUERY).get("return", {}), 0
            dated = "picture-stale" in d
            stale = d["picture-stale"] if dated else d.get("flip-loads", -1) < d.get("loads", 0)
            end = time.monotonic() + 1.0
            # a stopped VM can't freshen by itself: advance it, deterministic or not; poll only a running one
            stepping = stale and dated and (bool(self.st.get("deterministic")) or self.status() != "running")
            while stale and dated:   # v0.16.1: wait for a frame drawn after the load (the fork: ~10 vblanks at most)
                if stepping:
                    if advanced >= PICTURE_STALE_ADVANCE:
                        break
                    self.frame_advance(1)
                    advanced += 1
                elif time.monotonic() >= end:
                    break
                else:
                    time.sleep(0.05)
                d = self.qmp(DISPLAY_QUERY).get("return", {})
                stale = d["picture-stale"]
            self.last_picture = {"name": name, **d, "stale": stale, "advanced": advanced, **drawn}
            if stale and dated:
                raise SystemExit(f"screenshot {name}: the picture on screen still predates the last load (picture-stale, "
                                 f"loads {d.get('loads')}, picture-loads {d.get('picture-loads')}) after "
                                 f"{f'{advanced} vblank(s)' if stepping else 'a second'}")
            if stale:
                self.event(f"screenshot {name}: no flip since the last load (flip-loads {d.get('flip-loads')}, loads "
                           f"{d.get('loads')}): the loaded state's own saved frame; advance until the guest flips")
            elif advanced:
                self.event(f"screenshot {name}: advanced {advanced} vblank(s) to a frame drawn after the last load")
        tmp = self.w / f"screendump.{os.getpid()}.png"
        r = self.qmp("screendump", filename=str(tmp), format="png")
        if "error" in r or not tmp.exists():
            raise SystemExit(f"screendump: {r.get('error', {}).get('desc', 'no file written')}")
        dest = Path(dest) if dest else (self.out or self.w) / f"{name}.png"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(tmp, dest)
        return dest

    def hold(self, btn: str) -> None:
        self.send(f"down {self.code(btn)}")

    def release_btn(self, btn: str) -> None:
        self.send(f"up {self.code(btn)}")

    def clear(self) -> None:
        """Every key up and every analog value handed back to the keys: the pipe's ``clear``. AZ-390 refuted:
        X.31a's row c (v0.14-36) saw it release ``trigger lt 1`` by the third frame, as a press shows (a pipe line
        lands 2-4 frames late), so the trigger and stick zeros it once sent too changed nothing."""
        self.send("clear")

    def press(self, btn: str, *, ticks: int | None = None, seconds: float | None = None,
              label: str | None = None) -> dict | None:
        """Press ``btn`` for ``seconds`` of wall time (the guest running),
        or for ``ticks`` player ticks (tick-locked: down on the next tick,
        up ``ticks`` ticks later; returns that capture)."""
        if ticks is not None:
            return self.capture(ticks + 1, {0: f"down {btn}", ticks: f"up {btn}"}, label=label,
                                chain=False)
        if self._g is not None and self._halted:
            self.run()
        self.hold(btn)
        time.sleep(0.5 if seconds is None else seconds)
        self.release_btn(btn)
        return None

    # -- tick-locked capture --
    def _act(self, a, held: dict, row: dict, rows: list) -> list[str]:
        if callable(a):
            return [s for x in (a(self, row, rows) or []) for s in self._act(x, held, row, rows)]
        if isinstance(a, list):   # a list of actions; a tuple ('down', 'y') is one action
            return [s for x in a for s in self._act(x, held, row, rows)]
        parts = a.split() if isinstance(a, str) else list(a)
        if parts[0] == "clear":
            self.clear()
            held.clear()
            return ["clear"]
        if parts[0] == "stop":
            return ["stop"]
        if parts[0] in ("axis", "trigger") and len(parts) == 3:   # the fork build's analog pipe input
            self.axis(parts[1], float(parts[2]))
            key = f"{'trigger' if parts[1] in ('lt', 'rt') else 'axis'} {parts[1]}"
            if float(parts[2]) == 0.0:
                held.pop(key, None)
            else:
                held[key] = key
            return [" ".join(parts)]
        if parts[0] not in ("down", "up") or len(parts) != 2:
            raise ValueError(f"bad action {a!r}: want 'down <btn>', 'up <btn>', 'axis <lx|ly|rx|ry> <v>', "
                             "'trigger <lt|rt> <v>', 'clear', 'stop' or a callable")
        sc = self.code(parts[1])
        self.send(f"{parts[0]} {sc}")
        if parts[0] == "down":
            held[sc] = parts[1]
        else:
            held.pop(sc, None)
        return [f"{parts[0]} {parts[1]}"]

    def capture(self, n_ticks: int, schedule: dict | None = None, *, on_tick=None, fields: dict | None = None,
                bps=(), bp_readers: dict | None = None, hooks: dict | None = None, label: str | None = None,
                chain: bool = True,
                pad: bool = False, timeout: float = 5.0, first_timeout: float = 10.0, leave: str = "halt",
                note: str | None = None, max_hits: int = 5000) -> dict:
        """``n_ticks`` distinct player ticks, tick-locked on 0x8CCC0 (entity =
        [esp+4]); a hit equal on ``SAME`` to the last row is folded into it
        (``dups``). Starts from the current halt if it is at 0x8CCC0 (that
        tick is row 0), else runs to the next one.

        schedule: {tick k: action | [actions]}; an action is 'down <btn>',
        'up <btn>', 'axis <lx|ly|rx|ry> <v>' or 'trigger <lt|rt> <v>' (the
        fork build's analog pipe input, ``axis``), 'clear', 'stop' (end the
        capture after this row), or a
        callable f(sb, row, rows) -> actions|None (e.g. a poke). on_tick: the
        same kind of callable, run on every new row after the schedule (a
        callable passed as the schedule is taken as on_tick: sitting r18's
        pilot was). fields: {name: f(sb, ent) -> value}. bps:
        extra breakpoints; each hit is logged with the registers, [esp ..
        esp+0xC] as u32 and f32, fctrl, the tick index k and the last
        entity's fuel and flaps_used; bp_readers: {va: f(sb, regs) -> dict}
        adds fields. hooks: {va: f(sb, regs)}, breakpoints whose callable
        runs on every hit with nothing logged (the route pilot's analog
        stick at INPUT_BUILD). Buttons still held and axes still off rest at
        the end are released. leave:
        'halt' (at the last tick, no breakpoints) or 'run'. With a label it
        writes ``<out or W>/<label>.json``."""
        if callable(schedule):
            if on_tick is not None:
                raise ValueError("capture: a callable schedule and an on_tick; pass one per-tick callable")
            schedule, on_tick = None, schedule
        schedule = dict(schedule or {})
        # beside an owner demo the guest runs at background priority (D526): its tick waits stretch as READY_S's do
        timeout, first_timeout = timeout * (slow := self._slow()), first_timeout * slow
        bps = [int(v) for v in bps]
        hooks = {int(v): f for v, f in (hooks or {}).items()}
        vas = [PLAYER_TICK, *bps, *hooks]
        quiet = 0   # hook hits since the last player tick
        g = self.halt()
        meta = {"label": label, "tag": self.st.get("last_tag"), "W": self.w.name, "xemu": self.st.get("xemu_version"),
                "started": now(), "n_ticks": n_ticks, "bps": [hex(v) for v in bps], "note": note,
                "schedule": {str(k): [x if isinstance(x, (str, tuple)) else repr(x) for x in v]
                             if isinstance(v, list) else v if isinstance(v, str) else repr(v)
                             for k, v in schedule.items()}}   # a callable shows as its repr
        rows: list[dict] = []
        hits: list[dict] = []
        held: dict[int | str, str] = {}   # scancode -> button; "axis lx" -> itself
        stop = None
        at_tick = g.regs()["eip"] == PLAYER_TICK
        arm(g, vas)
        t0 = time.monotonic()
        try:
            if not at_tick:
                g.cont()
                self._halted = False
                if not self._wait(first_timeout):
                    stop = f"no player tick within {first_timeout} s"
            while stop is None:
                r = g.regs()
                eip = r["eip"]
                if eip in hooks:
                    hooks[eip](self, r)
                    quiet += 1
                    if quiet > 300:
                        stop = "300 hook hits with no player tick (a dialog, cutscene or menu?)"
                        break
                elif eip == PLAYER_TICK:
                    quiet = 0
                    ent = self.read_u32(r["esp"] + 4)
                    row = self.entity_row(ent)
                    if rows and rows[-1]["ent"] == ent and all(rows[-1][k] == row[k] for k in SAME):
                        rows[-1]["dups"] += 1
                    else:
                        row = {"k": len(rows), "ent": ent, "ret": self.read_u32(r["esp"]), "fctrl": r["fctrl"], **row,
                               "dups": 0}
                        if chain:
                            try:
                                row.update(self.chain(ent))
                            except OSError as e:
                                row["chain_error"] = str(e)[:80]
                        for name, fn in (fields or {}).items():
                            row[name] = fn(self, ent)
                        if pad:
                            row["pad"] = self.pad()
                        sent = []
                        if (acts := schedule.get(row["k"])) is not None:
                            sent += self._act(acts, held, row, rows)
                        if on_tick is not None:
                            sent += self._act(on_tick, held, row, rows)
                        if sent:
                            row["sent"] = sent
                        rows.append(row)
                        if "stop" in sent:
                            stop = f"a stop action at tick {row['k']}"
                        if len(rows) >= n_ticks or stop:
                            break
                elif eip in bps:
                    if len(hits) >= max_hits:
                        stop = f"max_hits {max_hits} reached"
                        break
                    hits.append(self._hit(r, eip, rows, bp_readers))
                else:
                    hits.append({"k": rows[-1]["k"] if rows else None, "va": hex(eip), "unexpected_stop": True})
                resume(g, vas, eip)
                self._halted = False
                if not self._wait(timeout):
                    stop = f"no stop within {timeout} s after tick {len(rows) - 1} (a dialog, cutscene or menu?)"
        finally:
            for sc in list(held):
                try:
                    self.send(f"up {sc}" if isinstance(sc, int) else f"{sc} 0")   # a button, or an axis back to rest
                except OSError:
                    pass
            meta["released_at_end"] = sorted(held.values())
        meta.update(rows=len(rows), complete=len(rows) >= n_ticks, stop=stop, hits=len(hits),
                    wall_s=round(time.monotonic() - t0, 2), dups=sum(r["dups"] for r in rows),
                    returns=sorted({hex(r["ret"]) for r in rows}), entities=sorted({hex(r["ent"]) for r in rows}))
        if leave == "run":
            self.run()
        else:
            g.cmd("?")   # stay halted; no breakpoints left armed
        out = {"meta": meta, "rows": [self._jsonrow(r) for r in rows], "hits": hits}
        if label:
            p = (self.out or self.w) / f"{label}.json"
            if p.exists():
                p = p.with_name(f"{label}-{time.strftime('%H%M%S')}.json")
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(out, indent=0), encoding="utf-8")
            out["path"] = str(p)
            log(f"capture: {len(rows)} ticks, {len(hits)} hits, stop={stop!r} -> {p}")
        return out

    @staticmethod
    def _jsonrow(r: dict) -> dict:
        o = {}
        for k, v in r.items():
            if k in ("ent", "ret", "critter", "gameplay", "armor_mgr", "level_ptr", "fctrl") and isinstance(v, int):
                o[k] = hex(v)
            elif isinstance(v, dict):
                o[k] = {a: fnum(b) for a, b in v.items()}
            else:
                o[k] = fnum(v)
        return o

    def _hit(self, r: dict, eip: int, rows: list, readers: dict | None) -> dict:
        g = self.g
        st = g.read(r["esp"], 16)
        hit = {"k": rows[-1]["k"] if rows else None, "va": hex(eip), "fctrl": hex(r["fctrl"]),
               "regs": {k: hex(r[k]) for k in ("eax", "ecx", "edx", "ebx", "esp", "ebp", "esi", "edi")},
               "stack_u32": [hex(v) for v in struct.unpack("<4I", st)],
               "stack_f32": [fnum(v) for v in struct.unpack("<4f", st)]}
        if rows:
            try:
                c = self.chain(rows[-1]["ent"])
                hit.update(fuel=fnum(c["fuel"]), flaps_used=self.read_i32(rows[-1]["ent"] + 0xD8))
            except OSError:
                pass
        if readers and eip in readers:
            hit.update(readers[eip](self, r) or {})
        return hit


def pin_pace(g: "RSP") -> bool:
    """Hold the game to one scene tick a frame (Step X.20): its own "slow motion" cvar (``l3.SLOW_MOTION``, the
    command line's -clock1) at 1, as a console at full speed runs.  Else the main loop catches up with the clock,
    two ticks a frame while xemu runs slower than the game, so the frame's render, which draws from the game's
    random numbers, follows a different count of ticks from run to run (and from L3, which renders after each).
    Returns whether it had to set it (placed)."""
    cvar = g.u32(l3.SLOW_MOTION)
    if g.u32(cvar + 4) == 1:
        return False
    g.write(cvar + 4, struct.pack("<I", 1))
    return True


REPLAY_START = "replay-start"   # the checkpoint a replay through hooks keeps of its start (Sandbox._replay_by_hooks)


def hooked_obs(data: list[str], ent: int, cam: bytes | None) -> obs.Obs | None:
    """The light observation (``obs.read`` without ``deep``) from a RET hook's collected regions
    (``Sandbox._hooks_pass``: the entity, its critter's span from +0x154, the player data's span from its armor
    manager, the manager's slot and gauge, the slot's Level to Flaps; ``""`` an unreadable one), read through the
    pointers those regions hold, as ``obs.read`` reads them; None when a region a pointer names wasn't read."""
    b = [bytes.fromhex(d) if d else None for d in data[:5]]
    if b[0] is None or b[1] is None:
        return None
    mem = {ent: b[0], struct.unpack_from("<I", b[0], obs.ENT_CRITTER)[0] + obs.CR_PD: b[1]}
    ptr = struct.unpack_from("<I", b[1])[0]   # pd, then its armor manager, then the manager's slot
    for i, at in ((2, recipes.PD_ARMOR), (3, obs.ARMOR_SLOT), (4, obs.SLOT_LEVEL)):
        if not ptr:
            break
        if b[i] is None:
            return None
        mem[ptr + at] = b[i]
        ptr = struct.unpack_from("<I", b[i])[0] if i < 4 else 0

    def read(va: int, n: int) -> bytes:
        if va in mem and len(mem[va]) >= n:
            return mem[va][:n]
        raise OSError(f"{va:#x}: not collected")
    try:
        return obs.read(read, ent, cam, deep=False)
    except OSError:
        return None


def start_hash(read, ent: int) -> str:
    """sha256[:12] of the player's entity (0x1C0 B) and body (0x240 B): the
    replayer's check that the guest is at a snapshot's start."""
    return hashlib.sha256(read(ent, 0x1C0) + read(struct.unpack("<I", read(ent + 0x20, 4))[0], 0x240)).hexdigest()[:12]


def l3_compare(want: list, got: list[dict]) -> dict:
    """L3's rows against the replay's, tick by tick: the body centre's
    error in metres, the length of xemu's path, state and HP mismatches, xemu's
    state changes, and every observed field (``obs.compare``: per field the
    ticks it differs on, the first tick that differs). No positions."""
    errs = [math.dist(a.pos, b["pos"]) for a, b in zip(want, got)]
    states = [b["state"] for b in got]
    fields = obs.compare([a.obs for a in want], [b["obs"] for b in got]) \
        if all(a.obs is not None for a in want) and all("obs" in b for b in got) else {}
    return {**fields, "ticks": len(errs), "l3_ticks": len(want), "max_err_m": max(errs, default=None),
            "path_m": sum(math.dist(a["pos"], b["pos"]) for a, b in zip(got, got[1:])),
            "first_err_tick": next((k for k, e in enumerate(errs) if e), None),
            "err_at": {k: errs[k] for k in sorted({0, 10, 25, 50, 75, 100, len(errs) - 1}) if 0 <= k < len(errs)},
            "states_differ": sum(a.state != b["state"] for a, b in zip(want, got)),
            "hp_differ": sum(a.hp != b["hp"] for a, b in zip(want, got)),
            "states": [hex(s) for i, s in enumerate(states) if not i or states[i - 1] != s],
            "hp": sorted({b["hp"] for b in got})}


def l3_replay(sb: Sandbox, label: str, segments: list[dict], *, store: Path | str | None = None,
              scene: bool = False) -> dict:
    """``replay``: run the input string (``l3.pads`` segments) in L3 from
    snapshot ``label`` (``scene``: whole steps), then replay it in xemu
    from the same start (the guest halted there) and compare; the replay
    goes into the private conformance corpus (``devkit.sim.corpus``)."""
    from devkit.sim import corpus   # the simulator's (Step 4.13a), on Unicorn: only replay runs it
    from devkit.sim.l3 import L3

    snap = l3.read_snapshot(l3.snapshot_path(label, store))
    pads = l3.pads(segments)
    t0 = time.monotonic()
    rows = L3(snap, sb._xbe("dvd.iso"), scene=scene).run(pads)
    t1 = time.monotonic()
    got = sb.replay(pads, rows, snap.meta)
    corpus.record(snap.meta, scene, pads, rows, got, store=store, disc=sb.disc_source())
    return {"label": label, "mode": "scene" if scene else "tick", "l3_s": round(t1 - t0, 2),
            "xemu_s": round(time.monotonic() - t1, 1), **l3_compare(rows, got)}


def jump_summary(rows: list[dict]) -> dict:
    """v0 = vz on the first tick whose state turns 2 (air) from non-2; Δvz
    per airborne tick; the airborne ticks (consecutive state-2 rows); the
    apex = the highest bbox min z (+0x1A4) less its takeoff value, None when
    one of them isn't a finite number (a save-loaded entity's bbox can hold
    a non-finite float, which ``capture``'s rows carry as a string, AZ-337)."""
    i = next((j for j in range(1, len(rows)) if rows[j - 1]["state"] != 2 and rows[j]["state"] == 2), None)
    if i is None:
        return {"takeoff": None}
    j = i
    while j < len(rows) and rows[j]["state"] == 2:
        j += 1
    air = rows[i:j]
    dvz = [round(b["vz"] - a["vz"], 6) for a, b in zip(air, air[1:])]
    bz = [r["bz"] for r in rows[i - 1:j]]
    apex = (round(max(bz[1:]) - bz[0], 4)
            if all(isinstance(v, (int, float)) and math.isfinite(v) for v in bz) else None)
    return {"takeoff_k": rows[i]["k"], "pre_state": rows[i - 1]["state"], "v0": rows[i]["vz"],
            "h": rows[i]["h"], "air_ctl": rows[i]["air_ctl"], "airborne_ticks": len(air),
            "landed": j < len(rows), "land_state": rows[j]["state"] if j < len(rows) else None,
            "dvz": dvz, "dvz_set": sorted(set(dvz)),
            "apex_bz": apex,
            "peak_z": rows[i]["peak_z"], "hold_t": [round(r["hold_t"], 4) for r in air[:8]]}


# --- the boot walk ---------------------------------------------------------

def stopped_at(g: RSP, va: int, timeout: float, stop=None) -> bool:
    """Whether the running guest stops at ``va`` within ``timeout`` s;
    it's halted either way. ``stop`` (``Sandbox._bugcheck_stop``'s): asked
    every second meanwhile, the guest halted and its error raised once it
    names one."""
    end = time.monotonic() + timeout
    while True:
        try:
            g.wait_stop(max(0.05, min(end - time.monotonic(), 1.0)) if stop else timeout)
            return g.regs()["eip"] == va
        except TimeoutError:
            if stop is not None and (e := stop()) is not None:
                g.interrupt()
                raise e from None
            if stop is None or time.monotonic() >= end:
                g.interrupt()
                return False


class DeadPad(SystemExit):
    """START doesn't skip prophecy.bik: the guest ignores the pad (AZ-296)."""


class NoContinue(SystemExit):
    """A on the save built the scene, but Continue never ran (AZ-302)."""


class BootHang(SystemExit):
    """prophecy.bik never started or never ended: possibly the boot hang (V22)."""


class MenuMiss(SystemExit):
    """The menu route loaded no level in its tries."""


class NoSteadyTick(SystemExit):
    """The player tick never ran steadily: a dialog or cutscene is still up. ``diag`` (``to_player_tick``'s, AZ-628):
    the polls, how many saw the tick, the entities they saw, the most event-clock seconds a run of ticked polls
    reached, and the EIPs of the last ``NO_TICK_EIPS`` polls that saw none, so a failed try says where the guest was."""

    def __init__(self, msg: str, diag: dict | None = None):
        super().__init__(msg)
        self.diag = diag


class GuestBugcheck(SystemExit):
    """The guest bugchecked or halted with interrupts off (``XEMU_GUEST_BUGCHECK``, Step X.61; AZ-628): ``items``
    holds each one (``bugchecks``). A boot try ends on it at once and is retried (``failure_class`` "bugcheck")."""

    def __init__(self, msg: str, items: list[dict]):
        super().__init__(msg)
        self.items = items


class CpuidFault(SystemExit):
    """The guest ran an instruction the Pentium III lacks (``XEMU_STRICT_CPUID``, Step X.58; AZ-021): ``faults``
    holds each one's pc and feature."""

    def __init__(self, msg: str, faults: list[dict]):
        super().__init__(msg)
        self.faults = faults


def fault_list(faults: list[dict]) -> str:
    """Strict-CPUID faults (``cpuid_faults``) in a line: each feature at its pc, the first 4."""
    return ", ".join(f"{f['feature']} at {f['pc']}" for f in faults[:4]) + (
        f" and {len(faults) - 4} more" if len(faults) > 4 else "")


class BootFailed(SystemExit):
    """Every try of a boot failed (``Sandbox.boot_build``)."""


class AdvanceStopped(SystemExit):
    """A VM stop it didn't make, not a breakpoint's, ended ``frame_advance`` before its frame (PROMPT-8 D):
    ``reply`` is xemu's, with ``stopped`` the run state and ``ran`` (or ``ran_at_most``) the frames that ran."""

    def __init__(self, msg: str, reply: dict):
        super().__init__(msg)
        self.reply = reply


class AdvanceTimedOut(AdvanceStopped):
    """An advance or run that xemu paused at its ``timeout-ms`` (``TIMEOUT_MARK``, Step X.94) before its frame: at a
    host-time point, so a deterministic sandbox runs on only after a checkpoint restore or a load
    (``_refuse_after_timeout``); a boot try retries it from a relaunch (``failure_class`` "timed_out")."""


def usb_ready(info: str) -> bool:
    """Whether HMP ``info usb`` lists a device that isn't a hub: the port-2 pad is attached."""
    return any("Product" in ln and "hub" not in ln.lower() for ln in str(info).splitlines())


# xemu's player ports on the machine's root hub (ui/xemu-input.c, xemu_input_hub_ports): player 1's pad hub is on USB
# port 1.3, player 2's on 1.4, 3's on 1.1, 4's on 1.2, each pad on its hub's port 1 (1.3.1, ...). A state holds the hubs
# and pads it was saved with: a load into a machine without one of them fails ("Unknown section ... usb-hub").
HUB_PORTS = (3, 4, 1, 2)
OWNER_PAD_S = 900.0     # an owner demo's load waits this long for the owner's pad (AZ-466)


def hub_port(player: int) -> str:
    """Player ``player``'s (1-4) pad hub port: ``1.3`` for player 1."""
    return f"1.{HUB_PORTS[int(player) - 1]}"


def usb_devices(info: str) -> dict[str, str]:
    """HMP ``info usb`` as ``{port: its id, else its product}``: ``{"1.3": "USB Hub", "1.1.1": "demopad"}``."""
    return {m[1]: m[3] or m[2].strip() for m in re.finditer(
        r"Port ([\d.]+), Speed [^,]+, Product ([^,\n]+)(?:, ID: (\S+))?", str(info))}


def demo_priority(nice: int) -> str | None:
    """Why an owner demo can't launch from a process at ``nice`` (AZ-466), else None: xemu inherits its launcher's
    nice value, zsh's ``bg_nice`` runs a ``&`` job at nice 5 (X.34 and X.35's xemus ran there, the play lagging), and
    only root renices back to 0, so the launch refuses rather than lag."""
    if nice > 0:
        return (f"an owner demo's xemu runs at normal priority, but this process runs at nice {nice} and xemu would "
                "inherit it (zsh's bg_nice puts a '&' job at nice 5; renicing to 0 needs root): launch it from bash, "
                "after 'setopt no_bg_nice', or in the foreground (AZ-466)")
    return None


def skip_prophecy(g: RSP, fifo: Path, sc: dict[str, int], dead_after: int | None = None, stop=None) -> int:
    """Run until the game starts prophecy.bik, then press START every
    1.5 s until the game sees the movie end, for longer than the movie
    lasts (START can fail to skip it, and then it plays out); halt
    there. Returns the presses sent. The intermittent boot hang (V22)
    can freeze the guest before the movie or during it. With
    ``dead_after``, that many presses that don't end it halt the guest
    and raise ``DeadPad``. ``stop`` (a boot try's, Step X.61): asked each
    second, its ``GuestBugcheck`` raised at once."""
    v22 = "possibly the intermittent boot hang (V22); run it again"
    try:
        arm(g, [PROPHECY_STARTED])
    except OSError:
        pass   # the XBE isn't mapped yet: nothing is translated, a bare Z0 fires
    g.cont()
    if not stopped_at(g, PROPHECY_STARTED, 90.0, stop):
        raise BootHang(f"the game never started prophecy.bik: {v22}")
    arm(g, [PROPHECY_ENDED])
    g.cont()
    deadline, n = time.monotonic() + PROPHECY_S + 30.0, 0
    while time.monotonic() < deadline:
        n += 1
        press(fifo, sc["start"], 0.0)
        try:
            g.wait_stop(1.0)
            return n
        except TimeoutError:
            if stop is not None and (e := stop()) is not None:
                g.interrupt()
                raise e from None
        if n == dead_after:
            g.interrupt()
            raise DeadPad(f"{n} START presses didn't skip prophecy.bik: the pad is dead (AZ-296)")
    raise BootHang(f"prophecy.bik never ended: {v22}")


def level_path(g: RSP) -> str:
    """The path argument of the ``LOAD_LEVEL`` call the guest is halted at
    (``"<NULL>"`` for a NULL one, which no vanilla caller is known to
    pass: ``return-to-shell`` is a destination, docs/RE_DATA.md § 7)."""
    p = g.u32(g.regs()["esp"] + 8)
    return g.read(p, 0x50).split(b"\0")[0].decode("latin-1") if p else "<NULL>"


def boot_state(g: RSP) -> int | None:
    """The boot state machine's state (``BOOT_STATE``), the guest halted; None while the XBE isn't mapped."""
    try:
        return g.u32(BOOT_STATE)
    except OSError:
        return None


def await_state(g: RSP, ok, timeout: float, every: float = 0.25) -> int | None:
    """Poll the boot state, the guest running with no breakpoint armed,
    until ``ok(state)``: that state, or None after ``timeout``. Leaves the
    guest running."""
    end = time.monotonic() + timeout
    while True:
        g.interrupt()
        s = boot_state(g)
        g.cont()
        if s is not None and ok(s):
            return s
        if time.monotonic() >= end:
            return None
        time.sleep(every)


last_walk: dict = {}   # walk_to_level's last route: the boot states it saw and the presses of its last button


def walk_to_level(g: RSP, fifo: Path, sc: dict[str, int], route, want: str | None = None,
                  continue_s: float | None = None) -> tuple[str, int]:
    """From the end of the movie, ``route`` ((button, wait s) pairs) until
    the game loads a level within ``LEVEL_S`` (movies, ``bink:`` paths,
    pass); a level other than ``want`` (a save the walk opened) fails by
    name. It waits on the boot state, not on the clock (Step X.9): the
    first press once the title is up (``MENU``, within ``MENU_S``), each
    press but the last until the state moves on (its wait at most: a cursor
    move changes none; at the title, pressed again after
    ``TITLE_AGAIN_S``), and the last with the checkpoints armed, pressed
    again when ``A_AGAIN_S`` pass with no stop (the list didn't take it
    yet); ``A_PRESSES`` of each at most. A press that opens the save list
    ends at the list's preview of its save (``INV_RESET``, armed before it).
    A cursor move right in the save list (``dpad_right``) is pressed again
    every ``CURSOR_S`` until the list previews the save it moved to (it
    drops a move while it reads the HDD, AZ-354), ``CURSOR_PRESSES`` at most.
    On a miss, B twice back to the title and
    the route again, 3 tries, then ``MenuMiss``. With ``continue_s``, A
    on a save that builds the scene (``SCENE_RESET``) and doesn't reach
    Continue (``START_SETUP``) within that many seconds halts the guest
    and raises ``NoContinue`` (AZ-302) instead of retrying the route.
    Leaves the game running. Returns the level and the try that worked;
    ``last_walk`` keeps the states it saw."""
    vas = [LOAD_LEVEL, *((SCENE_RESET, START_SETUP) if continue_s else ())]
    *steps, (last, _) = route
    last_walk.clear()
    for n in range(1, 4):
        g.cmd("?")   # no breakpoint while the boot state is polled
        g.cont()
        t0 = time.monotonic()

        def at() -> float:
            return round(time.monotonic() - t0, 2)
        if n > 1:
            press(fifo, sc["b"], 1.5)
            press(fifo, sc["b"], 1.5)
        states = [s := await_state(g, lambda v: v >= MENU, MENU_S)]
        rec = {"states": states, "title_s": at()}
        missed = False
        for button, wait in steps:
            cursor = s == LIST and button == "dpad_right"   # onto the next save: confirmed by its preview
            for i in range(CURSOR_PRESSES if cursor else A_PRESSES):
                g.interrupt()
                arm(g, [INV_RESET])   # armed before the press: the list previews its save within 0.5 s
                resume(g, [INV_RESET])   # halted on it (the last preview's stop again): off it, or it reports it
                if cursor:            # the last preview's burst passes first: only a stop after the press is the move's
                    late = False      # ... but after a press of ours whose preview didn't come within its wait, a
                    for _ in range(8):   # stop now is that move's late preview (AZ-363: pressing again wrapped the
                        if not stopped_at(g, INV_RESET, QUIET_S):   # list back to #1 at load ~60)
                            break     # quiet; halted
                        resume(g, [INV_RESET])
                        rec["drained"] = rec.get("drained", 0) + 1
                        late = late or i > 0
                    if late:
                        g.cmd("?")
                        g.cont()
                        rec.setdefault("cursor", []).append([i, at(), "late"])
                        break
                    g.cont()
                press(fifo, sc[button], 0.0)
                seen_preview = stopped_at(g, INV_RESET, TITLE_AGAIN_S if s == MENU else wait)   # halted either way
                now_s = boot_state(g)
                g.cmd("?")
                if seen_preview:
                    g.cmd("s")   # off the preview's stop
                g.cont()
                if seen_preview:
                    rec["preview_s"] = at()
                moved = now_s if now_s != s else None
                if cursor:
                    if seen_preview:
                        rec.setdefault("cursor", []).append([i + 1, at()])   # presses, seconds
                        break
                    continue   # dropped while the list reads the HDD: press it again
                if seen_preview or moved is not None or s != MENU:
                    break   # the list previewed its save, the state moved on, or a cursor move had its wait
            else:
                missed = cursor   # the list never moved to the save: this try failed
            states.append(moved)
            s = s if moved is None else moved
            if missed:
                break
        if missed:
            rec["cursor_missed"] = at()
            last_walk.setdefault("tries", []).append({**rec, "presses": 0, "level": None})
            continue   # B, B and the route again
        g.interrupt()
        arm(g, vas)
        if g.regs()["eip"] == INV_RESET:
            g.cmd("s")
        g.cont()
        press(fifo, sc[last], 0.0)
        rec["a_s"] = [at()]
        end, a_end, presses, seen = time.monotonic() + LEVEL_S, time.monotonic() + A_AGAIN_S, 1, False
        scene, path = False, None
        while True:
            try:
                g.wait_stop(max(0.1, (end if seen else min(end, a_end)) - time.monotonic()))
            except TimeoutError:
                g.interrupt()
                if scene:
                    raise NoContinue(
                        f"A on the save built the scene, but Continue ({START_SETUP:#x}) didn't run within "
                        f"{continue_s:.0f} s (AZ-302); halted at EIP {g.regs()['eip']:#x}, the scene pointer "
                        f"{SCENE_PTR:#x} {'set' if g.u32(SCENE_PTR) else 'not set'}") from None
                if not seen and presses < A_PRESSES and time.monotonic() < end:
                    g.cont()
                    press(fifo, sc[last], 0.0)   # no checkpoint: the list didn't take it
                    rec["a_s"].append(at())
                    presses, a_end = presses + 1, time.monotonic() + A_AGAIN_S
                    continue
                break
            eip = g.regs()["eip"]
            if not seen:
                rec["first_stop"] = [at(), hex(eip)]
            seen = True
            if eip == LOAD_LEVEL and not (p := level_path(g)).startswith("bink:"):
                path = p
                break
            if eip in (SCENE_RESET, START_SETUP):
                scene, end = eip == SCENE_RESET, time.monotonic() + continue_s
            resume(g, vas, eip)
        last_walk.setdefault("tries", []).append({**rec, "presses": presses, "level": path})
        if path is None:
            continue   # no level loaded; halted
        if want is not None and path != want:   # another save (AZ-363): a menu miss, which a boot retries
            raise MenuMiss(f"the menu walk loaded {path!r}, not {want}")
        g.cmd("?")
        g.cont()
        return path, n
    raise MenuMiss(f"the menu route never loaded a level (3 tries; boot states {last_walk.get('tries')})")


def hold_hp(g: RSP, hp: int | None) -> int:
    """Halted at a player tick: put the player's HP (critter+0x210) back
    to ``hp`` if it fell below it (``None``: just read it); returns the
    HP held."""
    at = g.u32(g.u32(g.regs()["esp"] + 4) + 0x20) + 0x210   # [esp+4] = entity; [entity+0x20] = critter
    now = struct.unpack("<i", g.read(at, 4))[0]
    if hp is not None and now < hp:
        g.write(at, struct.pack("<i", hp))
    return now if hp is None else hp


def to_player_tick(g: RSP, fifo: Path, sc: dict[str, int], steady_s: float | None = None, stop=None) -> int:
    """Poll the player tick every 0.5 s (each poll waits up to 1.5 s for
    one), pressing A whenever it doesn't run (a cutscene or dialog is up),
    until it has run at every poll over ``STEADY_S`` seconds of the
    player's event clock (entity+0x18: guest time, so a slow guest takes
    longer in wall time, not less; Step X.9 replaced a fixed 6 s and 7
    polls 2 s apart); halt at it. Its first tick can come during the
    arena's intro cutscene, before the welcome dialog. Each tick it stops
    at puts the player's HP back to the first one's (``hold_hp``): e7's
    enemies attack during the polls, and once killed the player (AZ-305).
    Returns the polls taken; ``NoSteadyTick`` after ``STEADY_WAIT_S`` (4
    minutes), its ``diag`` the polls, the ticked ones, the entities seen,
    the longest steady run and the last no-tick polls' EIPs (AZ-628), and
    at a halt in the kernel's halt loop (``HALT_LOOP``) the five dwords
    KeBugCheckEx stores (``BUGCHECK_DATA``: code and p1-p4; zeros, the
    double fault's halt; Step X.61). ``stop`` (a boot try's): asked each
    poll, its ``GuestBugcheck`` raised at once."""
    steady = STEADY_S if steady_s is None else steady_s
    start, hp, n, end = None, None, 0, time.monotonic() + STEADY_WAIT_S
    ticks, best, ents, eips, halt = 0, 0.0, [], collections.deque(maxlen=NO_TICK_EIPS), None
    while time.monotonic() < end:
        if stop is not None and (e := stop()) is not None:
            raise e
        n += 1
        g.interrupt()
        arm(g, [PLAYER_TICK])
        resume(g, [PLAYER_TICK])   # halted on it: step off, or the stub reports that tick again
        ticked = stopped_at(g, PLAYER_TICK, 1.5)
        if ticked:
            ticks += 1
            ent = g.u32(g.regs()["esp"] + 4)
            clock = struct.unpack("<d", g.read(ent + 0x18, 8))[0]
            hp = hold_hp(g, hp)
            if start is None or start[0] != ent:
                start = (ent, clock)
            if ent not in ents:
                ents.append(ent)
            best = max(best, clock - start[1])
            if clock - start[1] >= steady:
                return n
        else:
            eips.append(eip := g.regs()["eip"])   # halted where the interrupt (or another stop) left it
            start = None
            if eip == HALT_LOOP and halt is None:
                with contextlib.suppress(OSError):
                    halt = [hex(v) for v in struct.unpack("<5I", g.read(BUGCHECK_DATA, 20))]
        g.cmd("?")
        g.cont()
        if not ticked:
            press(fifo, sc["a"], 0.0)
        time.sleep(0.5)
    diag = {"polls": n, "ticked": ticks, "entities": len(ents), "best_s": round(best, 3),
            "no_tick_eips": [hex(e) for e in eips], **({"bugcheck_data": halt} if halt else {})}
    raise NoSteadyTick(f"no steady player tick in {STEADY_WAIT_S / 60:g} minutes: a dialog or cutscene is still up "
                       f"({ticks} of {n} polls ticked; no-tick EIPs {sorted(set(diag['no_tick_eips']))})", diag)


def code_identity(g: RSP, xbe: bytes, skip=()) -> dict[str, tuple[int, int]]:
    """``{section: (bytes compared, bytes that differ)}`` for ``.text``
    and ``SHIMS``: the guest must run the build under test. The VAs in
    ``skip``'s ``(start, end)`` ranges (the data the build's shims write
    while the game runs, ``shim_data``; AZ-300) are left out of both."""
    out = {}
    for sec in xbe_sections(xbe):
        if sec.name in (".text", "SHIMS"):
            n = min(sec.raw_size, sec.vsize)
            want = xbe[sec.raw:sec.raw + n]
            got = g.read(sec.va, n)
            left = {va - sec.va for lo, hi in skip for va in range(lo, hi)
                    if 0 <= va - sec.va < n}
            out[sec.name] = (n - len(left), sum(a != b for i, (a, b) in enumerate(zip(want, got))
                                                 if i not in left))
    return out


def _press_jump():
    """``capture``'s on_tick for ``jump``: Y down on the first ground tick
    at or after ``JUMP_AT``, up ``JUMP_HOLD`` ticks later."""
    at = None

    def act(sb, row, rows):
        nonlocal at
        if at is None and row["k"] >= JUMP_AT and row["state"] == 0:
            at = row["k"]
            return ["down y"]
        return ["up y"] if at is not None and row["k"] == at + JUMP_HOLD else None
    return act


def jump(iso: Path, ticks: int, wait_s: float = WAIT_S, headless: str | None = None, app=None,
         deterministic: bool | None = None) -> int:
    """Cold-boot ``iso`` in a sandbox (the fork build, null and
    deterministic by default), walk to the Training Arena, check ``.text``, jump once and
    print v0. W is kept."""
    sb = Sandbox("jump", app=app, disc=iso, wait_s=wait_s, keep=True, headless=headless, deterministic=deterministic)
    ok = False
    try:
        sb.up(hold=True)
        log(f"sandbox: {sb.w}; pid {sb.st['pid']}, gdb port {sb.st['gdb_port']}; sandbox ok")
        if sb.frame_boot():   # the power-on on guest frames from its -S stop (Step X.64)
            rec = sb.boot_frames(TITLE, NEW_GAME_LEVEL, steady_s=ARENA_STEADY_S, continue_s=None)
            log(f"menu: prophecy.bik ended after {rec['skips']} START presses; A at frame {rec['a']}; Start New "
                f"Game loaded {rec['level']} at frame {rec['level_at']}; the player tick ran {ARENA_STEADY_S:g} s of "
                f"game time at every poll by poll {rec['polls']} (frame {rec['steady_at']})")
        else:
            g, fifo = sb.halt(), sb.w / "input.fifo"
            log(f"menu: prophecy.bik ended after {skip_prophecy(g, fifo, sb.sc)} START presses")
            level, n = walk_to_level(g, fifo, sb.sc, TITLE, NEW_GAME_LEVEL)
            log(f"menu: Start New Game loaded {level} on try {n}")
            log(f"menu: the player tick ran {ARENA_STEADY_S:g} s of game time at every poll by poll "
                f"{to_player_tick(g, fifo, sb.sc, ARENA_STEADY_S)}")
        sb._halted = True
        code = sb.code_identity()
        log("code: " + ", ".join(f"{s} {n} B, {d} differ" for s, (n, d) in code.items()))
        if any(d for _, d in code.values()):
            raise SystemExit("the guest isn't running the ISO's default.xbe")
        cap = sb.capture(ticks, on_tick=_press_jump(), chain=False, label="jump")
        if not cap["meta"]["complete"]:
            raise SystemExit(f"the player tick stopped: {cap['meta']['stop']} (see {cap['path']})")
        rows = cap["rows"]
        air = next((i for i in range(1, len(rows))
                    if rows[i - 1]["state"] == 0 and rows[i]["state"] == 2), None)
        if air is None:
            raise SystemExit(f"no 0 -> 2 state change in {ticks} ticks (see {cap['path']})")
        log(f"player: entity {rows[0]['ent']}, fctrl {rows[0]['fctrl']}, "
            f"returns {cap['meta']['returns']}, h {rows[air]['h']}")
        log(f"jump: pressed at tick {next((r['k'] for r in rows if 'down y' in r.get('sent', [])), None)}, "
            f"airborne at tick {air}")
        log(f"v0 = {rows[air]['vz']:.4f} m/s ({rows[air]['vz']!r})")
        ok = True
    finally:
        if sb.st.get("pid") and not sb.st.get("down"):
            ok = sb.down()["sources_equal"] and ok
    return 0 if ok else 1


# --- selftest (offline: no xemu, no fixtures) -------------------------------

def _hook_expr(e: str, regs: dict, u32) -> int:
    """(selftest) The fork's hook address expressions, evaluated as xemu does: hex or decimal constants, registers,
    ``+`` and ``[ ]`` pointer reads (``u32``)."""
    def term(i: int) -> tuple[int, int]:
        if e[i] == "[":
            v, i = summed(i + 1)
            return u32(v), i + 1
        tok = re.match(r"0x[0-9a-fA-F]+|\d+|[a-z]+", e[i:])[0]
        return (int(tok, 0) if tok[0].isdigit() else regs[tok]), i + len(tok)

    def summed(i: int) -> tuple[int, int]:
        v, i = term(i)
        while i < len(e) and e[i] == "+":
            d, i = term(i + 1)
            v += d
        return v, i
    return summed(0)[0]


class _FakeGuest:
    """``RSP``'s surface over fake memory: each tick clears port 2's stick
    (the poll) and stops at INPUT_BUILD, JUMP_INIT, then PLAYER_TICK (each
    when armed), the player tick twice on every 3rd
    tick (a duplicate hit); the boot movie stops at PROPHECY_STARTED and,
    unless ``dead_pad`` (AZ-296), at PROPHECY_ENDED (when armed). A on
    the save (``a_on_save``) stops at the scene's inventory reset, then,
    unless ``no_continue`` (AZ-302), at Continue and at the level load
    (the save under the list's cursor: ``saves[cursor]``), each when
    armed. As on the fork's stub, ``c`` with the PC on an armed
    breakpoint reports that hit again, ``s`` steps off it, and with none
    there the guest runs on. The entity's timer and vz advance per tick;
    its chain reads HP 318/400, armor Level 3, Flaps 5, fuel 1.0. With
    ``dialog`` the player tick stops after its second tick (AZ-628) and an
    interrupt halts it at 0xAF17A or 0xAF190, in turn by poll."""

    def __init__(self):
        self.tick, self.queue, self.bps, self.eip, self.again = 0, [], set(), 0x12345, False
        self.dead_pad = self.no_continue = self.hang = self.dialog = False
        self.held = 0   # (dialog) the polls the player tick didn't run at
        self.a_ignored = self.start_ignored = self.cursor_lost = self.cursor = 0
        self.saves = ["levels/water/w1", "levels/water/w2"]   # the save list: #1, #2
        self.menu: list[int] = []
        self.esp, self.ent = 0xD0000000, 0x481C60
        self.s = type("S", (), {"close": lambda *_: None})()
        self.mem = {self.esp: bytearray(struct.pack("<4I", TICK_RETURN, self.ent, 0x900000, 0)),
                    self.ent: bytearray(ENT_SPAN), 0x500000: bytearray(0x220), 0x600000: bytearray(0xD0),
                    0x700000: bytearray(0x30), 0x800000: bytearray(0x40),
                    0x900000: bytearray(b"levels/water/w1".ljust(0x50, b"\0")),
                    ACTIVE_PAD: bytearray(struct.pack("<I", 1)), CONTROLLER_STATE: bytearray(0x54 * 4),
                    BOOT_STATE: bytearray(struct.pack("<I", 4))}   # the movie plays
        for base, off, fmt, v in ((self.ent, 0x20, "<I", 0x500000), (0x500000, 0x210, "<ii", (318, 400)),
                                  (0x500000, 0x154, "<I", 0x600000), (0x600000, 0xCC, "<I", 0x700000),
                                  (0x700000, 0x20, "<I", 0x800000), (0x700000, 0x24, "<f", 1.0),
                                  (0x800000, 0x08, "<i", 3), (0x800000, 0x38, "<i", 5)):
            struct.pack_into(fmt, self.mem[base], off, *(v if isinstance(v, tuple) else (v,)))
        self._tick()

    def a_on_save(self):
        self.write(0x900000, self.saves[self.cursor].encode().ljust(0x50, b"\0"))
        self.menu = [SCENE_RESET, *(() if self.no_continue else (START_SETUP, LOAD_LEVEL))]

    def _tick(self):
        struct.pack_into("<d", self.mem[self.ent], 0x18, self.tick / 30)   # the event clock
        struct.pack_into("<f", self.mem[self.ent], 0x9C, self.tick / 30)
        struct.pack_into("<f", self.mem[self.ent], 0x2C, -0.326667 * self.tick)

    def _region(self, va, n):
        for base, b in self.mem.items():
            if base <= va and va + n <= base + len(b):
                return b, va - base
        return None, 0

    def read(self, va, n):
        b, o = self._region(va, n)
        return bytes(b[o:o + n]) if b is not None else b"\x90" * n

    def write(self, va, data):
        b, o = self._region(va, len(data))
        if b is not None:
            b[o:o + len(data)] = data

    def u32(self, va):
        return struct.unpack("<I", self.read(va, 4))[0]

    def cmd(self, p):
        p = p.decode() if isinstance(p, bytes) else p
        if p == "?":
            self.bps.clear()
        elif p[:3] in ("Z0,", "z0,"):
            (self.bps.add if p[0] == "Z" else self.bps.discard)(int(p[3:].split(",")[0], 16))
        elif p == "s":
            self.eip += 1   # off the breakpoint
            return b"T05"
        return b"OK"

    def set_bp(self, va):
        self.cmd(f"Z0,{va:x},1")

    def clear_bp(self, va):
        self.cmd(f"z0,{va:x},1")

    def regs(self):
        return {"eip": self.eip, "esp": self.esp, "fctrl": 0x23F,
                **{k: 0 for k in ("eax", "ecx", "edx", "ebx", "ebp", "esi", "edi")}}

    def cont(self):
        self.again = self.eip in self.bps
        if not self.again:
            self.eip = 0x12345   # it runs on: an interrupt halts it elsewhere

    def interrupt(self):
        if self.held:
            self.eip = (0xAF17A, 0xAF190)[self.held % 2]
        return b"T02"

    def wait_stop(self, timeout):
        if self.again:
            self.again = False
            return b"T05"
        if movie := self.bps & {PROPHECY_STARTED, PROPHECY_ENDED}:
            if self.hang or (PROPHECY_ENDED in movie and self.dead_pad):
                raise TimeoutError   # START never ends it
            self.eip = min(movie)
            if self.eip == PROPHECY_ENDED:
                self.write(BOOT_STATE, struct.pack("<I", MENU))   # the movie's end: the title comes up
            return b"T05"
        while self.menu and self.menu[0] not in self.bps:
            self.menu.pop(0)   # unarmed: the guest runs through it
        if self.menu:
            self.eip = self.menu.pop(0)
            return b"T05"
        if not self.queue:
            if not self.bps & {JUMP_INIT, PLAYER_TICK, INPUT_BUILD}:
                raise TimeoutError
            if self.dialog and self.tick >= 2:   # a dialog holds the player tick
                self.held += 1
                raise TimeoutError
            self.tick += 1
            self._tick()
            self.mem[CONTROLLER_STATE][0x54:0x5C] = bytes(8)   # the poll: the FIFO pad's stick, at rest
            self.queue = ([INPUT_BUILD] if INPUT_BUILD in self.bps else []) + (
                [JUMP_INIT] if JUMP_INIT in self.bps else []) + (
                [PLAYER_TICK] * (2 if self.tick % 3 == 0 else 1) if PLAYER_TICK in self.bps else [])
        self.eip = self.queue.pop(0)
        return b"T05"


class _FrameGuest(_FakeGuest):
    """(selftest) A deterministic boot on frames for ``boot_frames``: QMP ``xemu-run`` (its ``@N`` input lines
    applied at their vblank, its ``stop-when`` PCs and boot-state range) and ``query-xemu-frame``, from a reset at
    frame ``f0``: prophecy.bik starts at +1350 and a START ends it that frame (``dead_pad``: none does), the title
    80 frames on; START there opens the save list, which previews the save under its cursor (two ``INV_RESET``
    calls) the frame after; a move right previews the next save (``cursor_lost``: that many dropped); A on the list
    builds the scene the frame after (``SCENE_RESET``, then Continue and a ``bink:`` load), the save's level 25
    frames on and the player tick every 2nd frame from 125 on, held after its 2nd tick until an A (``dialog``). An A
    at ``race`` frames from the reset bugchecks the guest 200 frames on (``run_log`` gains the line; AZ-695). The
    gdbstub's surface is _FakeGuest's."""

    def __init__(self, f0: int = 5000, run_log: Path | None = None, **flags):
        super().__init__()
        self.f, self.f0, self.run_log, self.race, self.lines, self.sched = f0, f0, run_log, None, [], {}
        self.pending: list[int] = []
        self.got: list[str] = []   # every input line, as sent
        for k, v in flags.items():
            setattr(self, k, v)
        self.sched[f0 + 1350] = [PROPHECY_STARTED]

    def qmp(self, cmd, **a):
        if cmd == "query-xemu-frame":
            return {"return": {"frame": self.f, "running": False}}
        return {"return": self.run(a) if cmd == XEMU_RUN else {}}

    def _at(self, f: int, *pcs: int) -> None:
        self.sched.setdefault(f, []).extend(pcs)

    def _key(self, f: int, sc: int) -> None:
        state = self.u32(BOOT_STATE)
        if sc == 238 and state == 4 and not self.dead_pad and self.sched.get("title") is None:
            self._at(f, PROPHECY_ENDED)
            self.sched["title"] = f + 80
        elif sc == 238 and state == MENU:
            self.write(BOOT_STATE, struct.pack("<I", LIST))
            self._at(f + 1, INV_RESET, INV_RESET)
        elif sc == 247 and state == LIST:
            if self.cursor_lost:
                self.cursor_lost -= 1
            else:
                self.cursor = min(self.cursor + 1, len(self.saves) - 1)
                self._at(f + 1, INV_RESET, INV_RESET)
        elif sc == 232 and state == LIST:
            self.write(BOOT_STATE, struct.pack("<I", 9))
            self._at(f + 1, SCENE_RESET)
            self._at(f + 2, START_SETUP)
            self._at(f + 5, LOAD_LEVEL)
            self._at(f + 25, LOAD_LEVEL)
            self.sched.update(level=f + 25, ticks=f + 125, crash=f + 200 if f - self.f0 == self.race else None)
        elif sc == 232 and state == 9:
            self.dialog = False

    def _arrive(self, pc: int) -> None:
        if pc == LOAD_LEVEL:
            path = self.saves[self.cursor] if self.f >= self.sched["level"] else "bink:intro"
            self.mem[0x900000][:] = path.encode().ljust(0x50, b"\0")
        elif pc == PLAYER_TICK:
            self.tick += 1
            self._tick()

    def run(self, a: dict) -> dict:
        for ln in a.get("input", []):
            self.got.append(ln)
            tag, body = ln.split(" ", 1)
            self.lines.append((int(tag[1:]), body))
        pcs = {s["pc"] for s in a.get("stop-when", []) if "pc" in s}
        vals = [s for s in a.get("stop-when", []) if "addr" in s]
        end = self.f + a["frames"]
        while True:
            while self.pending:
                pc = self.pending.pop(0)
                self._arrive(pc)
                if pc in pcs:
                    self.eip = pc
                    return {"reason": "hit", "frame": self.f, "running": False, "hits": 1, "pc": pc,
                            "regs": self.regs()}
            if self.f >= end:
                self.eip = 0xAF17A if self.dialog else 0x12345
                return {"reason": "budget", "frame": self.f, "running": False, "hits": 0}
            self.f += 1
            if self.f == self.sched.get("title"):
                self.write(BOOT_STATE, struct.pack("<I", MENU))
            if self.f == self.sched.get("crash") and self.run_log is not None:
                with self.run_log.open("a", encoding="utf-8") as fh:
                    fh.write("xemu: guest bugcheck 0x0000001e (0xc0000005, 0x000af173, 0x00000000, 0x6fdb4011) "
                             "from 0x8001ca36\n")
                self.sched["ticks"] = None
            for at, body in [x for x in self.lines if x[0] == self.f]:
                self.lines.remove((at, body))
                if body.startswith("down "):
                    self._key(self.f, int(body.split()[1]))
            for v in vals:
                if not int(v["lo"]) <= self.u32(int(v["addr"], 16)) <= int(v["hi"]):
                    return {"reason": "value", "frame": self.f, "running": False, "hits": 0,
                            "data": self.read(int(v["addr"], 16), 4).hex()}
            self.pending = list(self.sched.pop(self.f, []))
            if (t := self.sched.get("ticks")) is not None and self.f >= t and (self.f - t) % 2 == 0 \
                    and not (self.dialog and self.tick >= 2):
                self.pending.append(PLAYER_TICK)


_SAMPLE_TOML = """[general]
screenshot_dir = '{fx}/screens'
games_dir = '{fx}'

[general.snapshots.shortcuts]

[input]
background_input_capture = true

[input.bindings]
port1_driver = 'usb-xbox-gamepad'
port1 = '03000000000000000000000000000001'
port2 = 'keyboard'

[input.keyboard_controller_scancode_map]
y = 44

[display.window]
fullscreen_on_startup = true
fullscreen_exclusive = true

[audio]
volume_limit = 0.71123

[sys.files]
bootrom_path = '{fx}/mcpx_1.0.bin'
flashrom_path = '{fx}/Complex_4627v1.03.bin'
eeprom_path = '{fx}/eeprom.bin'
hdd_path = '{fx}/xbox_hdd.qcow2'
dvd_path = '{fx}/vanilla.iso'
"""
_SAMPLE_VM_STAT = """Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                                    400000.
Pages active:                                 1393391.
Pages speculative:                             124288.
"""


def selftest() -> int:
    """Offline checks of the harness's own logic: no xemu, no fixtures."""
    import fcntl

    global SLOTS, SUITE_LOCKS, STEADY_S, STEADY_WAIT_S, READY_S, LOADED_S, QMP_S, QUIT_S, TERM_S, OWNER_DEMO, press, take_slot, \
        xemu_pids, admission, hang_probe, idle_fraction, QMP_REFUSED_S, STALL_S, disk_wait, SHA_CACHE, FORK_REQUESTS
    ok = True

    def check(name: str, cond, detail: str = "") -> None:
        nonlocal ok
        ok &= bool(cond)
        log(f"{'ok  ' if cond else 'FAIL'} {name}{f' ({detail})' if detail else ''}")

    def refused(fn, *a) -> bool:
        try:
            fn(*a)
        except SystemExit:
            return True
        return False

    def _err(fn, *a, **kw) -> BaseException | None:
        try:
            fn(*a, **kw)
        except BaseException as e:  # noqa: BLE001  (the error is the check's subject)
            return e
        return None

    tmp = Path(tempfile.mkdtemp(prefix="azx-selftest.", dir="/tmp"))
    real_slots, real_suite, real_press, real_take_slot = SLOTS, SUITE_LOCKS, press, take_slot
    real_xemu_pids, real_admission, real_waits, real_demo = xemu_pids, admission, (READY_S, LOADED_S), OWNER_DEMO
    real_idle, real_disk_wait, real_sha_cache, real_requests = idle_fraction, disk_wait, SHA_CACHE, FORK_REQUESTS
    try:
        SHA_CACHE = tmp / "xemu-sha256.json"   # never the user cache dir's
        FORK_REQUESTS = tmp / "evidence"   # never the evidence archive's
        SUITE_LOCKS = (tmp / "suite.lock", tmp / "azurkit-suite.lock")   # none yet: no suite runs
        OWNER_DEMO = xemu_queue.OWNER_DEMO = tmp / "leases" / "owner-demo.json"   # never the fork's real one
        fx, w = tmp / "fx", tmp / "azx-st.1"
        fx.mkdir()
        gone, other = tmp / "azx-st.del", tmp / "not-a-sandbox"
        gone.mkdir(); other.mkdir(); (gone / "f").write_text("x", encoding="utf-8")
        delete_sandbox(gone)
        was_refused = False
        try:
            delete_sandbox(other)
        except RuntimeError:
            was_refused = True
        check("down deletes an azx sandbox folder directly (D147) and refuses any other folder",
              not gone.exists() and other.exists() and was_refused)
        # Step X.95: a source's sha256 by its content key. Step X.96: the teardown's baseline reads a source only when
        # its content key moved since up (baseline_keys), whatever the cache holds
        src, reads, real_digest = tmp / "src.iso", [], hashlib.file_digest
        src.write_bytes(b"A" * 4096)
        hashlib.file_digest = lambda f, alg: reads.append(1) or real_digest(f, alg)
        try:
            one = (file_sha256(src), file_sha256(src), len(reads))
            ids = {str(src): _identity(src)}
            up = baseline([src])
            keys = baseline_keys([src], up, ids)
            down = (baseline([src], fresh=True, known=keys), len(reads))   # unread: the key stands
            src.write_bytes(b"B" * 4096)                                  # the same size, written again
            moved = baseline([src], fresh=True, known=keys)               # read whole: an incident's diff
            two = (file_sha256(src), len(reads))
            os.utime(src, ns=(ids[str(src)][3], ids[str(src)][3]))       # the old mtime put back: the ctime moves
            touched = (baseline([src], fresh=True, known=keys).split()[0] == moved.split()[0], len(reads))
            subprocess.run(["cp", "-c", str(src), str(tmp / "clone.iso")], check=True)
            three = (file_sha256(tmp / "clone.iso") == two[0], len(reads))
        finally:
            hashlib.file_digest = real_digest
        check("file_sha256: a source standing as it was hashed is not read again; a write or a clone is; the "
              "teardown's baseline reads a source only when its content key moved since up (a write, or the old "
              "mtime put back after one: the ctime moved), never on the cache's word (Step X.96)",
              one[0] == one[1] == hashlib.sha256(b"A" * 4096).hexdigest() and one[2] == 1
              and down == (up, 1) and moved != up and moved.split()[0] == hashlib.sha256(b"B" * 4096).hexdigest()
              and two == (hashlib.sha256(b"B" * 4096).hexdigest(), 2) and touched == (True, 3) and three == (True, 4),
              f"{one[2]} {down[1]} {two[1]} {touched} {three}")
        (w / "xemu.app/Contents/Resources").mkdir(parents=True)
        (fx / "README.md").write_text("# Fixtures\n\n## Savestates\n\n| Tag | Spot |\n|---|---|\n"
                                      "| `vanilla-flat` | S3 |\n| `vanilla-ig-w1` | menu |\n", encoding="utf-8")
        # the scratch config, in both tomls
        s = scratch_toml(_SAMPLE_TOML.format(fx=fx), str(w))
        for p in (w / "xemu.toml", w / "xemu.app/Contents/Resources/xemu.toml"):
            p.write_text(s, encoding="utf-8")
        cs = [tomllib.loads(p.read_text(encoding="utf-8"))
              for p in (w / "xemu.toml", w / "xemu.app/Contents/Resources/xemu.toml")]
        vols = [c["audio"]["volume_limit"] for c in cs]
        check("scratch toml: volume_limit 0.0, a float, in both tomls",
              all(isinstance(v, float) and v == 0.0 for v in vols), f"{vols}")
        check("scratch toml: port1 gone, port2 the keyboard pad",
              all("port1" not in c["input"]["bindings"] and c["input"]["bindings"]["port2"] == "keyboard"
                  for c in cs))
        check("scratch toml: scancodes 232-256, every [sys.files] path in W, no fixtures path left",
              sorted(scancodes(s).values()) == list(range(232, 257))
              and all(v.startswith(f"{w}/") for v in cs[0]["sys"]["files"].values()) and str(fx) not in s)
        interp = [tomllib.loads(scratch_toml(_SAMPLE_TOML.format(fx=fx).replace(
            "[display.window]", "[display]\nframe_interpolation = '2x'\n\n[display.window]"), str(w), window=win,
            present_stall=bounded))["display"].get("frame_interpolation")
            for win, bounded in ((True, False), (False, False), (True, True))]
        check("scratch toml (AZ-601): a window's frame interpolation off (the fixtures' '2x' hung v0.16's windowed "
              "boots; no demo relaunches to turn it off), a headless one's as the fixtures have it; on a build with "
              "v0.16.1's bounded present (Step X.61) a window keeps the owner's '2x'",
              interp == ["off", "2x", "2x"], f"{interp}")
        # AZ-397: an owner demo binds the owner's pad (the fixtures' GUIDs) in a window only, still at volume 0
        two = _SAMPLE_TOML.format(fx=fx).replace("[input]\n", "[input]\ngamepad_mappings = [{gamepad_id = 'b2'}]\n")
        demo = {port: tomllib.loads(scratch_toml(two, str(w), port)) for port in (1, 2)}
        binds = {port: {k: v for k, v in c["input"]["bindings"].items() if k[-1].isdigit()} for port, c in demo.items()}
        guid = "03000000000000000000000000000001"
        check("owner demo (AZ-397): --owner-pad binds the owner's pad on its port and its other GUID on a free one, "
              "auto-bind on, volume 0.0, port 2 the keyboard unless the owner's; only in a real-time window",
              binds == {1: {"port1": guid, "port2": "keyboard", "port3": "b2"}, 2: {"port2": guid, "port3": "b2"}}
              and all(c["input"]["auto_bind"] is True and c["audio"]["volume_limit"] == 0.0
                      and c["input"]["bindings"][f"port{p}_driver"] == "usb-xbox-gamepad" for p, c in demo.items())
              and tomllib.loads(s)["input"]["auto_bind"] is False
              and all(isinstance(_err(Sandbox, "h", **kw), SystemExit) for kw in (
                  {"owner_pad": 2}, {"owner_pad": 2, "headless": "1"}, {"owner_pad": 5, "headless": "0"}))
              and Sandbox("h", headless="0", owner_pad=2).owner_pad == 2, f"{binds}")
        # AZ-397: the demo recorder (devkit/xemu/demo.py) writes a row per player tick, and after a load (the
        # clock jumped back, the level's nodes re-allocated) reads its nodes where the load put them
        from devkit.xemu import demo as xd
        regions: dict[int, bytearray] = {}

        def put(va: int, fmt: str, *vals) -> None:
            base = next((b for b in regions if b <= va < b + 0x1000), va & ~0xFFF)
            struct.pack_into(fmt, regions.setdefault(base, bytearray(0x1000)), va - base, *vals)

        def ram(va: int, n: int) -> bytes:
            base = va & ~0xFFF
            return bytes(regions[base][va - base:va - base + n]) if base in regions else bytes(n)
        put(SCENE_PTR, "<I", 0x700000)
        put(0x700000 + xd.recipes.SCENE_PD, "<I", 0x710000)
        put(0x710000, "12s", b"levels/life")
        put(0x710000 + xd.recipes.PD_PLAYER, "<I", 0x720000)
        put(0x720000 + 0x180, "<I", 0x730000)
        put(0x730000 + 0x20, "<I", 0x720000)
        put(0x710000 + xd.GRAPH, "<I", 0x740000)
        put(l3.MAIN_RATE, "<d", 30.0)

        def nodes_at(vec: int, node: int, value: float) -> None:   # the graph's 3 records, record 2 a switch
            put(0x740000 + xd.VEC, "<II", vec, vec + 12)
            put(vec + 8, "<I", node)
            put(node + xd.ATTRS_AT, "<I", node + 0x100)
            put(node + 0x100 + 4, "<f", value)
        rec = xd.Recorder(ram, {"levels": {"levels/life": {"count": 3, "nodes": {"Switch#2": {"output": 1}}}},
                                "tags": {"t1": {"clk": 5.0, "lvl": "levels/life"}}})
        trace = []
        for clk, at, value, load in ((10.0, 0x750000, 0.0, None), (10.0, 0x750000, 0.0, None),
                                     (10.0 + 1 / 30, 0x750000, 1.0, None), (5.5, 0x780000, 0.25, 1),
                                     (5.5 + 3 / 30, 0x780000, 0.25, None)):
            put(0x730000 + 0x18, "<d", clk)
            nodes_at(at, at + 0x1000, value)
            row = rec.step(1.0, load)
            trace.append(row and {k: row[k] for k in ("n", "lvl", "load", "sw_all", "sw", "gap_ticks") if k in row})
        check("demo recorder (AZ-397): a row per player tick; after a load its nodes are read where the load put "
              "them, the load named by the tag's clock; missed ticks counted",
              trace == [{"n": 0, "lvl": "levels/life", "sw_all": {"Switch#2": {"output": 0.0}}}, None,
                        {"n": 1, "sw": {"Switch#2": {"output": 1.0}}},
                        {"n": 2, "load": {"clk_jump": True, "loads": 1, "tag": "t1", "since_save_s": 0.5},
                         "sw_all": {"Switch#2": {"output": 0.25}}},
                        {"n": 3, "gap_ticks": 2}], f"{trace}")
        # AZ-612: two builds' tags at one clock and level (2.142's C0 and BL w1 tags, 0.0000 s apart): a load names the
        # one saved with the tray's disc, also a disc read as a path (tray_disc with W spelled another way); with no
        # disc to tell them by, none, both listed
        twin_tags = {"tags": {"tA": {"clk": 7.0, "lvl": "levels/life", "disc": "b-aaaaaaaaaaaa.iso"},
                        "tB": {"clk": 7.0, "lvl": "levels/life", "disc": "b-bbbbbbbbbbbb.iso"}}}
        named, other_w = [], "/private/tmp/azx-st.w/b-bbbbbbbbbbbb.iso"
        for d in ("b-bbbbbbbbbbbb.iso", other_w, None):
            drec = xd.Recorder(ram, twin_tags, disc=lambda d=d: d)
            put(0x730000 + 0x18, "<d", 12.0)
            drec.step(1.0)
            put(0x730000 + 0x18, "<d", 7.0 + 1 / 30)
            named.append(drec.step(1.0)["load"])
        check("demo recorder (AZ-612): of two tags at one clock and level, a load names the one saved with the tray's "
              "disc, which its row says, by its name also when the tray's reads as a path in a W spelled another "
              "way; with no disc to tell them by, none, both listed",
              named == [{"clk_jump": True, "loads": None, "tag": "tB", "since_save_s": 0.033,
                         "disc": "b-bbbbbbbbbbbb.iso"},
                        {"clk_jump": True, "loads": None, "tag": "tB", "since_save_s": 0.033, "disc": other_w},
                        {"clk_jump": True, "loads": None, "tag": None, "since_save_s": None, "disc": None,
                         "tags": ["tA", "tB"]}], f"{named}")
        # AZ-644: W's QMP turn: while the serve holds it (another descriptor's flock), a watcher's pass takes none and
        # its QMP refuses without connecting; once let go, the pass takes it and connects; the serve's own turn nests
        import threading   # (the selftest imports it below too: a local name)
        tw = tmp / "azx-st.turn"
        tw.mkdir()
        conns, tstop = [], threading.Event()
        tsrv = socket.socket(socket.AF_UNIX)
        tsrv.bind(str(tw / "qmp.sock"))
        tsrv.listen(4)
        tsrv.settimeout(0.05)

        def tserve() -> None:   # a QMP that counts its clients and answers every command
            while not tstop.is_set():
                try:
                    c, _ = tsrv.accept()
                except TimeoutError:
                    continue
                except OSError:
                    return
                conns.append(1)
                with c:
                    c.settimeout(2.0)
                    with contextlib.suppress(OSError):
                        c.sendall(b'{"QMP": {"version": {}, "capabilities": []}}\n')
                        for _line in c.makefile("rb"):
                            c.sendall(b'{"return": {}}\n')
        threading.Thread(target=tserve, daemon=True).start()
        watcher = xd.TurnQmp(tw)
        serve_fd = os.open(tw / QMP_TURN, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(serve_fd, fcntl.LOCK_EX)   # the serve, mid-request
            held_pass = (watcher.turn.take(), type(_err(watcher, "query-status")).__name__, len(conns))
            with qmp_turn(tw, block=False) as other:
                pass
            os.close(serve_fd)
            serve_fd = None
            free_pass = (watcher.turn.take(), watcher("query-status"), len(conns))
            with qmp_turn(tw, block=False) as while_watched:
                pass
            watcher.turn.drop()
            with qmp_turn(tw) as outer:
                with qmp_turn(tw) as inner:
                    nested = (outer, inner, watcher.turn.take())
            after = watcher.turn.take()
        finally:
            tstop.set()
            tsrv.close()
            watcher.turn.close()
            if serve_fd is not None:
                os.close(serve_fd)
        check("QMP turn (AZ-644): while the serve holds W's turn a watcher's pass takes none and its QMP refuses "
              "without connecting; let go, the pass takes it and connects; a serve's turn isn't had during a watcher's "
              "pass and nests in its own process",
              held_pass == (False, "OSError", 0) and other is False and free_pass == (True, {"return": {}}, 1)
              and while_watched is False and nested == (True, True, False) and after is True,
              f"{held_pass} {other} {free_pass} {while_watched} {nested} {after}")
        # Step X.56 (AZ-645): add-body's request: a new body's quiet boot at its level's save, 60 ticks at rest, its
        # tag and its load; a tag saved in another level than the booted one is tried once more from the warm boot
        # state, then refused and dropped from the meta; a body already tagged with its disc is one load; a boot that
        # fails loads the tag loaded before it again and the failure stands, the guest let run even when that load is
        # refused (a SystemExit, as tag_disc's for an oracle tag in a demo)
        calls, lvls, fail_boot, refuse = [], [], [], []

        class BodyBox:
            w, st = tmp / "azx-st.body", {"saved_tags": []}

            def stage(self, iso):
                calls.append("stage")
                return "b-0123456789ab.iso", "0123456789ab"

            def loadable(self, tag):
                return tag in self.st["saved_tags"]

            def release(self):
                calls.append("release")

        class BodySit:
            name = "p999"

            def boot(self, iso, tag, quiet=None, want=None):
                calls.append(f"boot {tag} quiet {quiet} want {want}")
                if fail_boot:
                    raise SystemExit("boot failed")
                return {"iso_sha12": "0123456789ab", "s": 30.0, "tries": 1, "warm": False, "incidents": []}

            def level(self):
                return "levels/water/w1"

            def loadvm(self, tag, **_):
                calls.append(f"loadvm {tag}")
                if tag in refuse:
                    raise SystemExit(f"refusing loadvm {tag!r}")
                return {"loadvm": "ok"}

            def tick(self, timeout=10.0):
                calls.append("tick")
                return 1

            def result(self, row):
                calls.append("result")

        def fake_note_tag(sb_, tag, meta_p):   # the level the save happened in: the next of lvls
            m = xd._meta(meta_p)
            m["tags"][tag] = {"lvl": lvls.pop(0), "disc": "b-0123456789ab.iso"}
            xd._save_meta(meta_p, m)
            sb_.st["saved_tags"].append(tag)
        BodyBox.w.mkdir()
        bmeta = BodyBox.w / xd.DEMO_META
        xd._save_meta(bmeta, {"levels": {"levels/water/w1": {}}, "tags": {}})   # its nodes noted already
        real_body = xd.ground, xd.note_tag
        xd.ground, xd.note_tag = (lambda _s: {"try": 1, "ticks": 60}), fake_note_tag
        try:
            bsb, bs = BodyBox(), BodySit()
            lvls[:] = ["levels/earth/e6", "levels/water/w1"]
            first = xd.add_body(bs, bsb, tmp / "b.iso", "w1", want="0123456789ab")
            seq1, calls[:] = list(calls), []
            again = xd.add_body(bs, bsb, tmp / "b.iso", "w1")
            seq2, calls[:] = list(calls), []
            lvls[:] = ["levels/earth/e6", "levels/earth/e6"]
            bsb.st["saved_tags"].clear()
            xd._save_meta(bmeta, {"levels": {"levels/water/w1": {}}, "tags": {}})
            twice = _err(xd.add_body, bs, bsb, tmp / "b.iso", "w1", load=False)
            seq3, kept = list(calls), xd._meta(bmeta)["tags"]
            wrong = _err(xd.add_body, bs, bsb, tmp / "b.iso", "w1", want="ba9876543210")
            calls[:], fail_boot[:] = [], [1]
            bsb.st.update(last_tag="p999-fedcba987654-w1", saved_tags=["p999-fedcba987654-w1"])
            failed = _err(xd.add_body, bs, bsb, tmp / "b.iso", "w1")
            seq4, calls[:], refuse[:] = list(calls), [], ["vanilla-ig-w1"]
            bsb.st.update(last_tag="vanilla-ig-w1", saved_tags=["vanilla-ig-w1"])
            no_back = _err(xd.add_body, bs, bsb, tmp / "b.iso", "w1")
            seq5 = list(calls)
        finally:
            xd.ground, xd.note_tag = real_body
        boot_seq = ["stage", "boot vanilla-ig-w1 quiet True want levels/water/w1",
                    "loadvm b-0123456789ab-vanilla-ig-w1"]
        check("add-body (Step X.56, AZ-645): a body's quiet boot at its level's save, 60 ticks at rest, its tag "
              "<serve>-<sha12>-<level>, a few ticks on (its load a clock jump) and its load, the guest let run; a "
              "tag saved in another level than the booted "
              "one is retried once from the warm boot state, then refused and dropped from the meta (the guest let "
              "run, no tag before it); a tag held with "
              "its disc is one load (a switch back); an ISO that isn't the build is refused; a failed boot loads the "
              "body before it again, its failure standing, the guest let run when that load is refused too",
              first["tag"] == "p999-0123456789ab-w1" and first["level_misses"] == ["levels/earth/e6"]
              and seq1 == [*boot_seq, "result", *["tick"] * xd.LOAD_GAP_TICKS, "loadvm p999-0123456789ab-w1",
                           "release"]
              and again.get("reused") and seq2 == ["stage", "loadvm p999-0123456789ab-w1", "release"]
              and isinstance(twice, SystemExit) and "AZ-645" in str(twice) and seq3 == [*boot_seq, "release"]
              and kept == {}
              and isinstance(wrong, SystemExit) and "not the build's" in str(wrong)
              and isinstance(failed, SystemExit) and str(failed) == "boot failed"
              and seq4 == [*boot_seq[:2], "loadvm p999-fedcba987654-w1", "release"]
              and isinstance(no_back, SystemExit) and str(no_back) == "boot failed"
              and seq5 == [*boot_seq[:2], "loadvm vanilla-ig-w1", "release"],
              f"{seq1} {seq2} {seq3} {twice} {kept} {failed} {seq4} {no_back} {seq5}")
        # AZ-522: a load the recorder sees first by its clock jump takes the run log's count on that row, so the flush
        # (every FLUSH_S) marks no later row for it; an in-game reload (a jump, no new count) has no count; a load with
        # no clock jump keeps the flush's mark
        count = [0]
        lrec, marks, flushes = xd.Recorder(ram, rec.meta, loads=lambda: count[0]), [], []
        for clk, n_log, flush in ((20.0, 0, False), (5.5, 1, False), (5.5 + 1 / 30, 1, True), (30.0, 1, False),
                                  (30.0 + 1 / 30, 2, True)):
            put(0x730000 + 0x18, "<d", clk)
            count[0] = n_log
            pending = lrec.flushed(n_log) if flush else None
            flushes += [pending] if flush else []
            marks.append(lrec.step(1.0, pending).get("load"))
        check("demo recorder (AZ-522): a load seen first by its clock jump is marked once, on that row, with the run "
              "log's count read there, and the flush marks no later row for it; an in-game reload's jump has no "
              "count; a load with no clock jump is the flush's",
              marks == [None, {"clk_jump": True, "loads": 1, "tag": "t1", "since_save_s": 0.5}, None,
                        {"clk_jump": True, "loads": None, "tag": None, "since_save_s": None},
                        {"clk_jump": False, "loads": 2, "tag": None, "since_save_s": None}] and flushes == [None, 2],
              f"{marks} {flushes}")
        # AZ-479: the game's own respawn re-allocates the nodes with no load and no clock jump: the recorder sees a
        # watched node move and reads them where they are now; every critterGenerator's numDead is read (record 1
        # here: a boss's generator the meta doesn't name), all after a resolve, then on change
        def gen_at(vec: int, node: int, dead: float) -> None:
            put(vec + 4, "<I", node)
            put(node, "<I", xd.GENERATOR_VT)
            put(node + xd.ATTRS_AT, "<I", node + 0x100)
            put(node + 0x100 + xd.NUM_DEAD, "<f", dead)
        trace = []
        for clk, at, value, dead in ((5.5 + 4 / 30, 0x7A0000, 0.5, 0.0), (5.5 + 5 / 30, 0x7A0000, 0.5, 1.0),
                                     (5.5 + 6 / 30, 0x7A0000, 0.5, 1.0)):
            put(0x730000 + 0x18, "<d", clk)
            nodes_at(at, at + 0x1000, value)
            gen_at(at, at + 0x2000, dead)
            row = rec.step(1.0)
            trace.append(row and {k: row[k] for k in ("n", "moved", "sw_all", "sw", "dead_all", "dead") if k in row})
        check("demo recorder (AZ-479): after the game's own respawn (nodes moved, no load, no clock jump) it reads "
              "them where they are, saying so; every critterGenerator's numDead is recorded, a boss's the meta "
              "doesn't name too, all after a resolve, then on change",
              trace == [{"n": 4, "moved": True, "sw_all": {"Switch#2": {"output": 0.5}}, "dead_all": {"#1": 0.0}},
                        {"n": 5, "dead": {"#1": 1.0}}, {"n": 6}], f"{trace}")
        # AZ-475: the pad the input builder read, per tick: read first at every poll, exact; where the read before
        # the tick differs from the one after, both are kept (a poll fell between them), and tick_pads hands a
        # per-tick replay each tick's float block, with the other where the recorder couldn't tell
        rows = []
        for clk, lx, a in ((5.5 + 6 / 30, 0.3, 0.0), (5.5 + 7 / 30, 0.7, 1.0), (5.5 + 8 / 30, 0.7, 1.0)):
            put(0x730000 + 0x18, "<d", clk)
            put(CONTROLLER_STATE, "<f", lx)
            put(CONTROLLER_STATE + 0x18, "<f", a)
            rows.append(rec.step(1.0 + len(rows) / 100))
        tp = xd.tick_pads([r for r in rows if r])
        tp60 = xd.tick_pads([{"n": 0, "clk": 2.0, "pidx": 0, "pad": {"lx": 0.25}},   # a 60 fps build, 2 ticks missed
                             {"n": 1, "clk": 2.0 + 1 / 60, "pidx": 0, "pad": {"lx": 0.5}, "pad_ms": 30.0},
                             {"n": 2, "clk": 2.0 + 4 / 60, "pidx": 0, "pad": {"lx": 0.75}, "pad_ms": 10.0,
                              "gap_ticks": 2}])
        f32 = lambda v: struct.pack("<f", v)   # noqa: E731
        check("demo recorder (AZ-475): a tick's pad is read first and exact; when the read before the tick differs "
              "from the one after, the row keeps both; tick_pads gives each tick's float block, and the other one "
              "where the builder may have read it, unknown where the reads were 1.5 ticks apart at the build's "
              "rate; missed ticks keep their places, holding the last pad read",
              [t["n"] for t in tp60] == [0, 1, None, None, 2] and tp60[0].get("start") and "alt" not in tp60[0]
              and "alt" in tp60[1] and tp60[1]["alt"] is None and tp60[4]["alt"] is None
              and all(t["missed"] and t["block"] == tp60[1]["block"] and t["alt"] is None for t in tp60[2:4]) and
              rows[0] is None and f32(rows[1]["pad"]["lx"]) == f32(0.7) and rows[1]["pad"]["a"] == 1.0
              and f32(rows[1]["pad_alt"]["lx"]) == f32(0.3) and rows[1]["pad_ms"] == 10.0 and "pad_alt" not in rows[2]
              and len(tp) == 2 and tp[0]["block"][:4] == f32(0.7) and tp[0]["alt"][:4] == f32(0.3)
              and "alt" not in tp[1] and len(tp[1]["block"]) == 0x48
              and xd.pad_block(xd.pad_dict(tp[0]["block"] + bytes(12))) == tp[0]["block"],
              f"{[r and {k: r[k] for k in ('n', 'pad_ms') if k in r} for r in rows]} {[sorted(t) for t in tp]}")
        # AZ-508: the camera the input builder read, per tick, from the fork's PC hook at 0x85276 ([esp+0x14] and the
        # entity's clock through EBP), drained at each row: a row keeps the hit of the tick that moved the clock
        # there (not an older attempt's), with the contact normal, fall reference and animation; tick_pads carries it
        # and the per-tick replay writes it over [esp+0x14] at 0x85276 (a fitted one first), the pad block at the
        # update entry, and ends after 3 ticks off
        sent, hits, vm = [], [], {"status": "running", "hooks": {3: "another client's"}, "next": 7}

        def fake_hooks(cmd: str, **args) -> dict:   # the fork's rules: a hook goes in only while the VM is stopped
            sent.append((cmd, args))
            if cmd == "query-commands":
                return {"return": [{"name": "xemu-hooks-set"}, {"name": "xemu-hooks-drain"}]}
            if cmd == "query-status":
                return {"return": {"status": vm["status"]}}
            if cmd in ("stop", "cont"):
                vm["status"] = "paused" if cmd == "stop" else "running"
            if cmd == "xemu-hooks-set":
                if vm["status"] == "running":
                    return {"error": {"class": "GenericError", "desc": "pause the VM first"}}
                vm["hooks"][vm["next"]], vm["next"] = args["hooks"][0], vm["next"] + 1
                return {"return": [{"id": vm["next"] - 1, "pcs": args["hooks"][0]["pcs"], "hits": 0}]}
            if cmd == "xemu-hooks-clear":
                for i in args.get("ids", list(vm["hooks"])):
                    vm["hooks"].pop(i, None)
            if cmd == "xemu-hooks-drain":
                out, hits[:] = list(hits), []
                return {"return": {"records": out, "dropped": 0}}
            return {"return": {}}

        def hit(clk: float, x: float, y: float, frame: int) -> None:
            hits.append({"pc": l3.CAMERA_DIR, "frame": frame,
                         "data": [struct.pack("<2f", x, y).hex(), struct.pack("<d", clk).hex()]})
        ch = xd.CamHook(fake_hooks)
        armed, rec.cam = ch.arm(), ch.take
        rearmed = (ch.arm(), [c for c, _ in sent[5:]], sent[6][1], sorted(vm["hooks"]), vm["status"])
        put(0x730000 + 0xB8, "<3f", 0.0, 0.6, 0.8)
        put(0x730000 + 0x168, "<f", 2.5)
        put(0x720000 + xd.CR_ANIM, "<i", 9)
        c0, cam_rows = 5.5 + 8 / 30, []
        for clk, hs in ((c0 + 1 / 30, [(c0 - 4.0, 1.0, 0.0, 90), (c0, 0.0, 1.0, 100)]),
                        (c0 + 2 / 30, [(c0 + 1 / 30, -0.6, 0.8, 101)]), (c0 + 3 / 30, []),
                        (c0 + 5 / 30, [(c0 + 3 / 30, 0.6, 0.8, 102), (c0 + 4 / 30, 0.8, 0.6, 102)])):   # a 2-tick frame
            for h in hs:
                hit(*h)
            put(0x730000 + 0x18, "<d", clk)
            cam_rows.append(rec.step(2.0 + len(cam_rows) / 30))
        rec.cam = None
        ch.disarm()
        disarmed = (sorted(vm["hooks"]), sent[-2:])
        tpc = xd.tick_pads(cam_rows)
        tr_rows = [{"n": i, "clk": 10.0 + i / 30, "pidx": 0, "pad": {"lx": 0.25 * i}, "body": [float(i), 0.0, 0.0],
                    "st": 0, "hp": [200, 200], "cam": [0.0, 1.0],
                    **({"pad_ms": 33.0} if i else {"load": {"clk_jump": True}})} for i in range(6)]
        tr = xd.TickReplay(tr_rows, 30.0, cams={301: l3.camera_dir(0.5)})
        steps = []
        for key, pos, st in ((300, (1.0, 0.0, 0.0), 0), (301, (2.0, 0.6, 0.0), 0), (302, (3.0, 0.0, 0.0), 2),
                             (303, (4.0, 0.7, 0.0), 0)):
            steps.append((tr.entry(key, 0), tr.camera(0x2000), tr.ret(obs.Obs(pos, (0.0,) * 3, st, 200, 200, 0))))
        summ = tr.summary()
        check("demo recorder (AZ-508): the camera the builder read at 0x85276 comes from the fork's PC hook, armed "
              "with the running guest paused around the call (the fork refuses a running VM) and cleared by its own "
              "id (another client's hook stays), drained per row: a row keeps its own tick's hit (the clock it "
              "entered at), not an older attempt's, none when no hit came, and a missed tick's own hit; the rows "
              "hold the contact normal, fall reference and animation; tick_pads carries the camera (a missed "
              "tick's own); the per-tick replay writes the pad block at the update entry and the camera over "
              "[esp+0x14] (a fitted one first), compares the body, state and HP, ends after 3 ticks off and "
              "refuses rows that span a load",
              armed is None and [c for c, _ in sent[:5]] == ["query-commands", "query-status", "stop",
                                                             "xemu-hooks-set", "cont"]
              and sent[3][1]["hooks"] == [{"pcs": [l3.CAMERA_DIR], "collect": [{"addr": "esp+0x14", "size": 8},
                                                                               {"addr": "ebp+0x18", "size": 8}]}]
              and rearmed == (None, ["query-commands", "xemu-hooks-clear", "xemu-hooks-drain", "query-status",
                                     "stop", "xemu-hooks-set", "cont"], {"ids": [7]}, [3, 8], "running")
              and disarmed == ([3], [("xemu-hooks-clear", {"ids": [8]}), ("xemu-hooks-drain", {})])
              and [(r.get("cam"), r.get("cf")) for r in cam_rows] == [
                  ([0.0, 1.0], 100), (list(struct.unpack("<2f", struct.pack("<2f", -0.6, 0.8))), 101), (None, None),
                  (list(struct.unpack("<2f", struct.pack("<2f", 0.8, 0.6))), 102)]
              and cam_rows[3]["gap_ticks"] == 1 and cam_rows[3]["cam_gap"] == [
                  list(struct.unpack("<2f", struct.pack("<2f", 0.6, 0.8)))]
              and all(r["nrm"] == [0.0, 0.6, 0.8] and r["fref"] == 2.5 and r["anim"] == 9 for r in cam_rows)
              and [t["cam"] for t in tpc] == [struct.pack("<2f", 0.0, 1.0), struct.pack("<2f", -0.6, 0.8), None,
                                              struct.pack("<2f", 0.6, 0.8), struct.pack("<2f", 0.8, 0.6)]
              and steps[0][0] == [(CONTROLLER_STATE, xd.pad_block({"lx": 0.25}))]
              and steps[0][1] == [(0x2014, struct.pack("<2f", 0.0, 1.0))] and steps[1][1] == [(0x2014,
                                                                                               l3.camera_dir(0.5))]
              and [x[2] for x in steps] == [False, False, False, True] and tr.done
              and (summ["within_0.1m"], summ["state_differ"], summ["first_over_0.1m"], summ["cams_written"]) ==
              (2, 1, 301, 4) and tr.entry(305, 0) is None and isinstance(_err(xd.TickReplay, [
                  tr_rows[0], {**tr_rows[1], "load": {"clk_jump": True}}], 30.0), ValueError),
              f"{[(r.get('cam'), r.get('cf')) for r in cam_rows]} {summ}")
        # Step X.32b (AZ-518, AZ-479): on v0.15 the recorder's rows come from a PC hook at the player update's RET:
        # its regions (address expressions, evaluated there) read back by row_reader give the poller's row of the same
        # memory; the level's nodes and generators by expressions from their record indices follow a respawn that
        # moved them; HookRows sets its hooks with the guest paused around the call, drains the row, node and camera
        # records in one call and pairs each row with its tick's node values; tick_pads takes a RET row's pad as the
        # builder's (no alt, no new run); the per-tick replay marks a poller's row that holds the tick before's
        u32r = lambda va: struct.unpack("<I", ram(va, 4))[0]   # noqa: E731

        def collect(cs: list[dict]) -> list[str]:   # one hook hit's regions over the fake RAM
            return [ram(_hook_expr(c["addr"], {}, u32r), c["size"]).hex() for c in cs]
        put(0x730000 + 0x18, "<d", 9.0)
        polled = xd.Recorder(ram, rec.meta)
        prow = polled.step(3.0)
        hrec = xd.Recorder(xd.row_reader(collect(xd.ROW_HOOK["collect"])), rec.meta)
        hrow = hrec.step(3.0, hooked=({}, {}))
        nh, nregs = xd.node_hooks(rec.meta, "levels/life", 3, [1])
        before = xd.node_values([{"data": collect(h["collect"])} for h in nh], nregs)
        nodes_at(0x7E0000, 0x7E1000, 0.75)   # the game's own respawn: both re-allocated
        gen_at(0x7E0000, 0x7E2000, 2.0)
        after = xd.node_values([{"data": collect(h["collect"])} for h in nh], nregs)
        hq, hsent, ids, hfail = [], [], iter(range(20, 99)), {"set": None}

        def hook_qmp(cmd: str, **args) -> dict:
            hsent.append(cmd)
            if cmd == "query-commands":
                return {"return": [{"name": "xemu-hooks-set"}, {"name": "xemu-hooks-drain"}]}
            if cmd == "query-status":
                return {"return": {"status": "running"}}
            if cmd == "xemu-hooks-set" and hfail["set"] == "held":
                raise TimeoutError("QMP held by another client")
            if cmd == "xemu-hooks-set" and hfail["set"] == "refused":
                return {"error": {"class": "GenericError", "desc": "too many hooks"}}
            if cmd == "xemu-hooks-set":
                return {"return": [{"id": next(ids)} for _ in args["hooks"]]}
            if cmd == "xemu-hooks-drain":
                out, hq[:] = list(hq), []
                return {"return": {"records": out, "dropped": 0}}
            return {"return": {}}
        hcam = xd.CamHook(hook_qmp)
        hr = xd.HookRows(hook_qmp, hcam, ram, rec.meta)
        armed_rows, arm_seq, fed_armed = hr.arm(), list(hsent), hcam.fed
        hsent.clear()
        hr.nodes("levels/life", 0x710000)   # its generators found through the live reader
        node_seq, row_data = list(hsent), collect(xd.ROW_HOOK["collect"])
        hq += [{"hook": 21, "pc": l3.CAMERA_DIR, "data": [struct.pack("<2f", 0.0, 1.0).hex(),
                                                          struct.pack("<d", 9.0 - 1 / 30).hex()], "frame": 6},
               {"hook": hr.id, "pc": l3.UPDATE_RETS[0], "data": row_data, "frame": 7},
               {"hook": hr.node_ids[0], "pc": l3.UPDATE_RETS[0], "data": collect(nh[0]["collect"]), "frame": 7}]
        drained = hr.drain()
        # Step X.32b's review: a level's node hooks QMP didn't take (held) leave its rows without nodes, never the
        # last level's, and are tried again NODE_RETRY_S later; ones xemu refused aren't; a failed arm (a
        # relaunch's) leaves the camera hook draining its own records, as the poller's rows take them
        hfail["set"] = "held"
        hr.nodes("levels/air", 0x710000)
        held_try = (hr.level, hr.node_ids, hr.regions, hr.stale)
        hfail["set"] = None
        hr.nodes("levels/air", 0x710000)
        too_soon = hr.node_ids
        hr.retry_at = 0.0
        hr.nodes("levels/air", 0x710000)
        retried = (hr.level, len(hr.node_ids))
        hfail["set"] = "refused"
        hr.nodes("levels/fire", 0x710000)
        refused_try = (hr.level, hr.node_ids)
        hfail["set"] = "held"
        rearm = (hr.arm(), hcam.fed)
        hfail["set"] = None
        node_notes = [n.split(", ")[0] for n in hr.notes]
        ret_pads = xd.tick_pads([{"n": 0, "clk": 2.0, "pidx": 0, "pad": {"lx": 0.5}, "ret": 1},
                                 {"n": 1, "clk": 2.0 + 2 / 30, "pidx": 0, "pad": {"lx": 0.25}, "ret": 1,
                                  "gap_ticks": 1}])
        lag_rows = [{"n": i, "clk": 20.0 + i / 30, "pidx": 0, "pad": {}, "body": [0.0] * 3, "st": 0,
                     "stt": round((i if i != 3 else 2) / 30, 4), "hp": [200, 200],
                     **({"pad_ms": 33.0} if i else {"load": {"clk_jump": True}})} for i in range(5)]
        lag = xd.TickReplay(lag_rows, 30.0, patience=1)
        for c in range(600, 604):
            lag.entry(c, 0)
            lag.ret(obs.Obs((0.0,) * 3, (0.0,) * 3, 0, 200, 200, 0, state_t=(c - 599) / 30))
        check("demo recorder on v0.15 (Step X.32b, AZ-518, AZ-479): a row from the RET hook's regions is the poller's "
              "row of the same memory; the nodes and generators by record-index expressions follow a respawn; the "
              "hooks set with the guest paused around the call; one drain pairs a row with its tick's node values "
              "and feeds the camera; a level's node hooks a held QMP didn't take are tried again later, its rows "
              "reading no nodes meanwhile, and ones xemu refused aren't; a failed arm leaves the camera hook "
              "draining itself; a RET row's pad is the builder's; a poller's row holding the tick before's is "
              "marked torn and judges nothing",
              {k: v for k, v in prow.items() if k not in ("sw_all", "dead_all")} == hrow
              and before == polled._nodes() == ({"Switch#2": {"output": 0.5}}, {"#1": 1.0})
              and after == ({"Switch#2": {"output": 0.75}}, {"#1": 2.0})
              and armed_rows is None and arm_seq == ["query-commands", "query-status", "stop", "xemu-hooks-set", "cont"]
              and node_seq == ["query-status", "stop", "xemu-hooks-set", "cont"]
              and fed_armed and [(x["frame"], n) for x, n in drained] == [(7, after)] and len(hcam.recs) == 1
              and held_try == ("levels/life", [], [], []) and too_soon == [] and retried == ("levels/air", 1)
              and refused_try == ("levels/fire", []) and rearm[0].startswith("QMP: ") and rearm[1] is False
              and node_notes == ["levels/air: its node hooks not set", "levels/fire: its node hooks refused"]
              and [("start" in t, t.get("alt", "none"), t.get("missed", False)) for t in ret_pads] == [
                  (True, "none", False), (False, None, True), (False, "none", False)]
              and [x.get("torn", False) for x in lag.results] == [False, False, True, False] and not lag.done
              and lag.summary()["torn"] == 1,
              f"{[k for k in {**prow, **hrow} if prow.get(k) != hrow.get(k)]} {before} {after} {node_seq} {drained}")
        # TD.0's sitting: fit_cams keeps the last camera on a tick the stick steers nothing (a roll), where every yaw
        # gives the same tick; it drifted 11 degrees a tick there (M2's part B: 44 degrees off by the roll's end)
        class FitSim:   # a body moving 0.1 m a tick along the camera's heading, but along +x on roll ticks 1 and 2
            snap, entity = type("S", (), {"meta": {"clock": 10.0}})(), 0

            def __init__(self):
                self.p, self.i = (0.0, 0.0), 0

            def pad_va(self):
                return 0x1000

            def save(self):
                return self.p, self.i

            def reset(self, s=None):
                self.p, self.i = s or ((0.0, 0.0), 0)

            def step(self, pad, writes=()):
                d = (0.1, 0.0) if self.i in (1, 2) else (0.1 * pad.cam[0], 0.1 * pad.cam[1]) if pad.cam else (0.0, 0.0)
                self.p, self.i = (self.p[0] + d[0], self.p[1] + d[1]), self.i + 1
                return type("R", (), {"pos": (*self.p, 0.0), "obs": type("O", (), {"vel": (0.0,) * 3,
                                                                              "state_t": self.i / 30})(),
                                      "state": 0, "hp": 200})()

            def u32(self, va):
                return 0

            def read(self, va, n):
                return struct.pack("<4f", 0.0, 0.0, 0.0, 1.0)
        fit_rows, p = [], (0.0, 0.0)
        for i in range(5):
            p = (p[0] + 0.1, p[1]) if i in (1, 2) else (p[0] - 0.1 * math.sin(0.3), p[1] + 0.1 * math.cos(0.3))
            fit_rows.append({"n": i, "clk": (301 + i) / 30, "pidx": 0, "pad": {"ly": 1.0}, "body": [*p, 0.0],
                             "vel": [0.0] * 3, "quat": [0.0, 0.0, 0.0, 1.0], "st": 0, "hp": [200, 200],
                             **({"pad_ms": 33.0} if i else {})})
        fcams, _, finfo = xd.fit_cams(FitSim(), xd.TickReplay(fit_rows, 30.0))
        fyaw = {k: math.atan2(-c[0], c[1]) for k, c in ((k, struct.unpack("<2f", v)) for k, v in fcams.items())}
        tcams, _, tinfo = xd.fit_cams(FitSim(), xd.TickReplay(   # Step X.32b, AZ-518: row 3 holds row 2's tick
            [{**r, "stt": round((i + 1 if i != 3 else i) / 30, 4)} for i, r in enumerate(fit_rows)], 30.0))
        check("fit_cams keeps the last camera on a tick the stick steers nothing (a roll) and fits the next steered "
              "tick round it; a poller's row holding the tick before's isn't fitted (AZ-518)",
              fyaw[301] == fyaw[302] == fyaw[300] and abs(fyaw[303] - 0.3) < 1e-4 and finfo["fitted"] == 3
              and finfo["l3_max_err_m"] < 1e-4 and finfo["torn"] == 0
              and (tinfo["torn"], tinfo["fitted"], tcams[303] == tcams[302]) == (1, 2, True),
              f"{ {k: round(math.degrees(v), 3) for k, v in fyaw.items()} } {finfo} {tinfo}")
        # AZ-438: the recorder checks its page directory every flush (it maps itself), and finds the one that does
        # when it moved, instead of trusting the CR3 it started with
        pdr = bytearray(0x30000)
        struct.pack_into("<I", pdr, 0xF000 + 0xC00, 0xF003)
        kept_pd = xd.page_directory(pdr, 0xF000)
        struct.pack_into("<I", pdr, 0xF000 + 0xC00, 0)
        struct.pack_into("<I", pdr, 0x20000 + 0xC00, 0x20003)
        moved_pd = xd.page_directory(pdr, 0xF000)
        struct.pack_into("<I", pdr, 0x20000 + 0xC00, 0)
        check("demo recorder (AZ-438): its page directory is checked against the RAM (it maps itself), and one that "
              "moved is found again; none, None",
              (kept_pd, moved_pd, xd.page_directory(pdr, 0x20000)) == (0xF000, 0x20000, None),
              f"{kept_pd} {moved_pd}")
        qd = Path(tempfile.mkdtemp(prefix="azx-qw.", dir="/tmp"))
        try:   # Step X.34: the replug watcher logs each change of W's QMP socket, timestamped by its caller
            qw = xd.QmpWatch(qd, probe_s=0.0)
            qlines = [qw.poll(0.0)]
            srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            srv.bind(str(qd / "qmp.sock"))
            srv.listen(4)
            qlines += [qw.poll(1.0), qw.poll(2.0)]
            srv.close()   # the file stays, nothing listens
            qlines.append(qw.poll(3.0))
            (qd / "qmp.sock").unlink()
            qlines.append(qw.poll(4.0))
        finally:
            shutil.rmtree(qd, ignore_errors=True)   # its own mktemp folder (D147)
        check("demo replug watcher (Step X.34): a line when W's QMP socket appears, stops accepting a connection "
              "or disappears, none while it stays the same",
              qlines[0] == "qmp.sock: missing" and qlines[1].startswith("qmp.sock: socket inode")
              and qlines[1].endswith("accepts a connection (was: missing)") and qlines[2] is None
              and "refuses a connection (ECONNREFUSED)" in qlines[3]
              and qlines[4].startswith("qmp.sock: missing (was: socket inode"), f"{qlines}")
        good = (f"config path: {w}/xemu.toml\nbase path: {w}/xemu.app/Contents/Resources/\n"
                f"Created QEMU launch: -bios {w}/flashrom.bin bootrom={w}/bootrom.bin "
                f"smbus-storage,file={w}/eeprom.bin media=disk,file={w}/xbox_hdd.qcow2 "
                f"media=cdrom,file={w}/dvd.iso")
        null = "xemu: headless mode: null\n" + good.replace(f"base path: {w}/xemu.app/Contents/Resources/\n", "")
        check("sandbox proof: a log inside W passes, an outside path fails; the null renderer needs no base "
              "path line (it never prints one), but a base path it shows must be W's",
              sandbox_problems(good, str(w)) == []
              and sandbox_problems(good + " -drive file=/elsewhere/x.qcow2", str(w)) == ["/elsewhere/x.qcow2"]
              and sandbox_problems(null, str(w)) == [] and len(sandbox_problems(null.split("\n", 1)[1], str(w))) == 1
              and len(sandbox_problems(null + "\nbase path: /Users/x/Library/xemu/\n", str(w))) == 1)
        data, bench = f"{w}/{DATA_DIR}", "/Users/x/Library/Caches/xemu-fork-bench"
        based = good.replace(f"base path: {w}/xemu.app/Contents/Resources/", f"base path: {data}/")
        prior = os.environ.get("XEMU_BASE_PATH")
        os.environ["XEMU_BASE_PATH"] = bench   # a shell that ran the fork's benches
        try:
            envs_b = [xemu_env(w, base=b).get("XEMU_BASE_PATH") for b in (None, data)]
        finally:
            os.environ.pop("XEMU_BASE_PATH")
            if prior is not None:
                os.environ["XEMU_BASE_PATH"] = prior
        check("XEMU_BASE_PATH (Step X.33, PROMPT-7 A(4)): a build with it (the name in its binary) gets W's data "
              "folder, never an inherited one, and its proof wants that base path alone (a null log none); a build "
              "without it is proven as before; a data folder outside W fails",
              base_path_for(w, b"\0XEMU_RAM_SHM\0XEMU_BASE_PATH\0") == data
              and base_path_for(w, b"\0XEMU_RAM_SHM\0XEMU_INPUT_RECORD\0") is None
              and envs_b == [None, data] and sandbox_problems(based, str(w), data) == []
              and sandbox_problems(null, str(w), data) == [] and len(sandbox_problems(good, str(w), data)) == 1
              and len(sandbox_problems(based, str(w))) == 1
              and len(sandbox_problems(based.replace(data, bench), str(w), bench)) == 1, f"{envs_b}")
        # Step X.69: a windowed sandbox's data folder starts from its build's kept shader cache, seeded once from the
        # fork's bench cache with only the files that build reads, and its down keeps what its xemu wrote or changed
        real_cache = (SHADER_CACHE, FORK_BENCH)
        globals().update(SHADER_CACHE=tmp / "shader-cache", FORK_BENCH=tmp / "bench")
        v2, v2s = "spirv_cache_v0.16.2-glslang16.6.0", "spirv_cache_v0.16.2-glslang16.6.0-spv1.5"
        try:
            pa, pb = "vk_prewarm-moltenvk-00000000000000aa.bin", "vk_prewarm-kosmickrisp-00000000000000bb.bin"
            for rel in ("pipeline_cache.bin", "pipeline_cache-kosmickrisp.bin", pa, pb, "eeprom.bin", f"{v2}/a",
                        f"{v2}/c.tmp", f"{v2s}/s", "spirv_cache_v0.16.3-glslang16.6.0/b"):
                (tmp / "bench" / rel).parent.mkdir(parents=True, exist_ok=True)
                (tmp / "bench" / rel).write_text(rel, encoding="utf-8")
            bin_ = b"\0%spipeline_cache.bin\0%sspirv_cache_v%d.%d.%d-%s%s%s\0XEMU_BASE_PATH\0"   # v0.16.2's names
            reads = cache_reads(bin_, "0.16.2")
            first = tmp / "azx-st.cache1" / DATA_DIR
            got1 = warm_shader_cache(first, bin_, "0.16.2")
            in1 = sorted(cache_files(first, reads))
            (first / "pipeline_cache.bin").write_text("compiled", encoding="utf-8")   # what the window's xemu wrote
            for rel in (f"{v2}/d", f"{v2}/e.tmp", "pipeline_cache.bin.99.tmp", "vk_prewarm-moltenvk-00000000000000aa.bin"):
                (first / rel).write_text(rel, encoding="utf-8")
            (tmp / "bench" / "pipeline_cache.bin").write_text("newer bench", encoding="utf-8")   # seeded once only
            box = Sandbox("cache", headless="0")
            box.w, box._owner = first.parent, False
            box.st = {"W": str(box.w), "base_path": str(first), "shader_cache": got1, "events": []}
            box._quit, box._baselines = (lambda: {"quit": "qmp"}), (lambda: {"sources_equal": True, "kept": False})
            kept = box.down().get("shader_cache")
            second = tmp / "azx-st.cache2" / DATA_DIR
            got2 = warm_shader_cache(second, bin_, "0.16.2")
            in2 = {rel: (second / rel).read_text(encoding="utf-8") for rel in cache_files(second, reads)}
            again = keep_shader_cache(second, got2)
            bin3 = b"\0%spipeline_cache.bin\0%svk_prewarm-%s-%016llx.bin\0XEMU_BASE_PATH\0"   # v0.16.3's prewarm lists
            third = tmp / "azx-st.cache3" / DATA_DIR
            got3 = warm_shader_cache(third, bin3, "0.16.3")
            (third / f"{pa}.4321.running").write_text("", encoding="utf-8")   # a launch died rebuilding pa's pipelines
            (third / pb).rename(third / f"{pb}.bad")   # check_dead_workers' rename on a relaunch
            aside = keep_shader_cache(third, got3)
            fourth = tmp / "azx-st.cache4" / DATA_DIR
            in4 = sorted(cache_files(fourth, warm_shader_cache(fourth, bin3, "0.16.3")["reads"]))
        finally:
            globals().update(SHADER_CACHE=real_cache[0], FORK_BENCH=real_cache[1])
        v163 = cache_reads(b"%spipeline_cache.bin %spipeline_cache-kosmickrisp.bin %svk_prewarm-%s-%016llx.bin "
                           b"%sspirv_cache_v%d.%d.%d-", "0.16.3")
        check("warm shader cache (Step X.69, the fork's cast-hitch request): a window's data folder starts from its "
              "build's kept cache, seeded once from the fork's bench cache with only what the build reads (its "
              "pipeline caches, prewarm lists and its version's SPIR-V folders, never a temp file); its down clones "
              "back only what its xemu wrote or changed, which the next window starts from, and drops a prewarm list "
              "the fork set aside (.bad, a dead launch's .running); only a window on a build with XEMU_BASE_PATH warms",
              in1 == ["pipeline_cache.bin", f"{v2s}/s", f"{v2}/a"] and got1["seeded"]["files"] == got1["files"] == 3
              and kept == {"files": 2, "bytes": len("compiled") + len(f"{v2}/d")} and not first.parent.exists()
              and "seeded" not in got2 and again == {"files": 0, "bytes": 0}
              and in2 == {"pipeline_cache.bin": "compiled", f"{v2}/a": f"{v2}/a", f"{v2}/d": f"{v2}/d",
                          f"{v2s}/s": f"{v2s}/s"}
              and v163 == {"files": ["pipeline_cache.bin", "pipeline_cache-kosmickrisp.bin"], "prewarm": True,
                           "spirv": "spirv_cache_v0.16.3-"} and cache_reads(bin_, None)["spirv"] is None
              and got3["files"] == 3 and aside == {"files": 0, "bytes": 0, "set_aside": [pb, pa]}
              and in4 == ["pipeline_cache.bin"]
              and warms_shader_cache("0", data) and not any(warms_shader_cache(h, b) for h, b in
                                                             (("1", data), ("null", data), ("0", None))),
              f"{in1} {got1} {kept} {got2} {in2} {again} {v163} {got3} {aside} {in4}")
        # admission (D108, Q258, D174, D263): two may always run; with 24
        # CPUs a third needs 4 cores idle and 8 GiB free
        gib = 2**30
        check("admission: with none or one running, another starts with no core and no RAM free (D174)",
              admission(0, 0.0, 24, 0) is None and admission(1, 0.0, 24, 0) is None)
        check("admission (D263): a third starts with 4 of 24 cores free and 8 GiB free, and 3.9 free cores refuse "
              "it, whatever the load average",
              admission(2, 4 / 24, 24, 8 * gib, (40.0, 40.0, 40.0)) is None
              and "3.9 of 24 CPU cores are free" in (admission(2, 3.9 / 24, 24, 64 * gib, (1.0, 1.0, 1.0)) or ""))
        ram = admission(2, 1.0, 24, 8 * gib - 1)
        check("admission: less than 8 GiB free refuses a third; only a refusal for cores is a CoreWait, the one "
              "batch jobs give way to (AZ-620)",
              ram and not isinstance(ram, CoreWait) and isinstance(admission(2, 3.9 / 24, 24, 64 * gib), CoreWait))
        ticks = iter([[2**32 - 100, 10, 2**32 - 50, 0], [100, 60, 150, 50]])   # user and idle wrapped
        check("idle_fraction: two samples' ticks differenced modulo 2**32, nice counted busy",
              idle_fraction(0, lambda: next(ticks)) == 200 / 500 and idle_fraction(0, lambda: None) is None)
        live = idle_fraction(0.05)
        check("idle_fraction: host_statistics answers on macOS", sys.platform != "darwin" or 0 <= live <= 1, f"{live}")
        idle_fraction = lambda *a: None   # noqa: E731  host_statistics failed
        try:
            check("admission: when the free-core measure fails, D174's load test decides, and says so",
                  admission(2, None, 24, 64 * gib, (15.9, 15.9, 40.0)) is None
                  and "load test" in (admission(2, None, 24, 64 * gib, (1.0, 16.0, 0.0)) or ""))
        finally:
            idle_fraction = real_idle
        check("vm_stat: free + speculative pages", vm_stat_free(_SAMPLE_VM_STAT) == 524288 * 16384)
        check("disk_wait: a launch waits while its volume has under 30 GiB free, and says so",
              "29.0 GiB of disk is free" in (disk_wait(w, 29 * gib) or "") and disk_wait(w, 30 * gib) is None)
        disk_wait = lambda w, free=None: None   # noqa: E731  the queue checks below never wait on this host's disk
        # slots: registration, pruning, foreign xemus, the launch lock
        SLOTS = tmp / "slots"
        w2 = tmp / "azx-st.2"
        w2.mkdir()
        _write_slot(w, {"pid": 101, "gdb_port": 40001})
        _write_slot(w2, {"pid": 102, "gdb_port": 40002})
        both = [x["W"] for x in slots()]
        w2.rmdir()
        check("slots: both register; a deleted W's slot is dropped",
              both == [str(w), str(w2)] and [x["W"] for x in slots()] == [str(w)]
              and not (SLOTS / f"{w2.name}.json").exists())
        procs = {101: "/tmp/azx-grp.a1b2/xemu.app/Contents/MacOS/xemu -config_path /tmp/azx-grp.a1b2/xemu.toml",
                 102: "/private/tmp/azx-s6-old.c3d4/xemu.app/Contents/MacOS/xemu -gdb tcp:127.0.0.1:5",
                 202: "/Applications/xemu.app/Contents/MacOS/xemu",
                 203: "/tmp/play.e5f6/xemu.app/Contents/MacOS/xemu -config_path /tmp/azx-x.1/xemu.toml",
                 301: "/tmp/xt/r3/base.app/Contents/MacOS/xemu -name xemu-fork-auto -config_path /tmp/xbd.1/xemu.toml",
                 302: "/tmp/xt/int/p1.app/Contents/MacOS/xemu -config_path /tmp/xbd.2/xemu.toml -name xemu-fork-auto -S",
                 303: "/tmp/xt/a.app/Contents/MacOS/xemu -name xemu-fork-autox"}
        check("slots: an xemu outside a /tmp/azx-* sandbox is foreign, one inside counts as running, and one "
              "named xemu-fork-auto is the fork's load, not the owner's (D248)",
              foreign_xemus(procs) == [202, 203, 303] and fork_auto_xemus(procs) == [301, 302]
              and sandbox_pids(procs) == {101, 102})
        a = _try_lock()
        b = _try_lock()
        _unlock(a)
        c = _try_lock()
        _unlock(c)
        check("slots: one launch at a time", a is not None and b is None and c is not None)
        helds = []
        for lock in SUITE_LOCKS:   # Modkit's and AzurKit's
            fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o644)
            fcntl.flock(fd, fcntl.LOCK_EX)   # what `lockf -k` or fullsuite.py holds while a suite runs
            helds.append((admission(2, 1.0, 24, 64 * gib), admission(1, 1.0, 24, 64 * gib)))
            os.close(fd)
        check("slots: a third waits while a full suite holds its lock, Modkit's or AzurKit's; the first two don't",
              all("full suite" in (held[0] or "") and str(lock) in (held[0] or "") and held[1] is None
                  for lock, held in zip(SUITE_LOCKS, helds))
              and admission(2, 1.0, 24, 64 * gib) is None, f"{helds}")
        # the first-come queue (Step X.8): a live earlier ticket goes first; a dead or silent one is removed
        other, gone = subprocess.Popen(["sleep", "60"]), subprocess.Popen(["true"])
        gone.wait()
        xemu_pids, w3 = (lambda: []), tmp / "azx-st.3"   # no xemu runs: the queue and the rule decide
        w3.mkdir()
        try:
            first = xemu_queue.take_ticket({"W": "/tmp/azx-other.1", "pid": other.pid}, SLOTS)
            dead = xemu_queue.take_ticket({"W": "/tmp/azx-other.2", "pid": gone.pid}, SLOTS)
            silent = xemu_queue.take_ticket({"W": "/tmp/azx-other.3"}, SLOTS)
            os.utime(silent, (1.0, 1.0))
            live = [t["n"] for t in xemu_queue.tickets(SLOTS)]
            check("queue: tickets are numbered as taken; a dead or silent waiter's ticket is removed",
                  live == [int(first.stem)] and int(first.stem) < int(dead.stem) < int(silent.stem)
                  and not dead.exists() and not silent.exists(), f"{live}")
            admission = lambda n: None   # noqa: E731  the rule would admit at once
            try:
                take_slot(w3, -1)
                behind = "admitted"
            except SystemExit as e:
                behind = str(e)
            admission = lambda n: "1.0 of 24 CPU cores are free (selftest)"   # noqa: E731
            other.kill()
            other.wait()
            try:
                take_slot(w3, -1)
                ruled = "admitted"
            except SystemExit as e:
                ruled = str(e)
            admission = lambda n: None   # noqa: E731
            fd3 = take_slot(w3, -1)
            _unlock(fd3)
            check("queue: a sitting waits behind an earlier live ticket, then for the rule alone, then starts; "
                  "its ticket goes each time",
                  "asked first" in behind and "1.0 of 24" in ruled and fd3 is not None
                  and (SLOTS / f"{w3.name}.json").exists() and not list((SLOTS / "queue").glob("*.json")),
                  f"{behind} | {ruled}")
        finally:
            other.kill()
            other.wait()
            xemu_pids, admission = real_xemu_pids, real_admission
            _drop_slot(w3)
        # leases (Step X.8): a running xemu renews its slot; a stopped one's is kept LEASE_S, then reclaimed;
        # a launcher that died before its xemu started loses its slot at once
        lw = {k: tmp / f"azx-lease.{k}" for k in ("run", "kept", "old", "orphan", "launch")}
        for d in lw.values():
            d.mkdir()
        fake = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", f"{lw['run']}/xemu.app/x"])
        try:
            _drop_slot(w)
            for k, info in (("run", {"pid": fake.pid}), ("kept", {"pid": gone.pid, "holder": gone.pid}),
                            ("old", {"pid": gone.pid, "holder": gone.pid}), ("orphan", {"holder": gone.pid}),
                            ("launch", {"holder": os.getpid()})):
                _write_slot(lw[k], info)
            for k in ("run", "old"):
                os.utime(SLOTS / f"{lw[k].name}.json", (1.0, 1.0))
            got = {Path(s["W"]).name.split(".")[1]: s["state"] for s in slots()}
            renewed = time.time() - (SLOTS / f"{lw['run'].name}.json").stat().st_mtime
            check("leases: running renews; a stopped xemu's slot is kept, then reclaimed; a dead launcher's goes at once",
                  got == {"run": "running", "kept": "kept", "launch": "launching"}
                  and renewed < 60 and sandboxes({}) == 3, f"{got} {sandboxes({})}")
        finally:
            fake.kill()
            fake.wait()
            for d in lw.values():
                _drop_slot(d)
        # batch jobs give way (Step X.8): one task in flight while a sitting waits, every worker otherwise
        import threading
        from concurrent.futures import ThreadPoolExecutor
        guard, live, peak = threading.Lock(), [0], [0]

        def task(i: int, secs: float) -> int:
            with guard:
                live[0] += 1
                peak[0] = max(peak[0], live[0])
            time.sleep(secs)
            with guard:
                live[0] -= 1
            return i
        waiting = xemu_queue.take_ticket({"W": "/tmp/azx-other.5"}, SLOTS)
        xemu_queue.renew_ticket(waiting, "1.0 of 24 CPU cores are free (selftest)")
        with ThreadPoolExecutor(4) as pool, xemu_queue.BatchToken("selftest", 4, root=SLOTS) as tok:
            tok.POLL_S = 0.0
            jobs = [j["name"] for j in xemu_queue.batch_jobs(SLOTS)]
            first = sorted(f.result() for f in tok.completed(pool, task, [(i, 0.02) for i in range(6)]))
            gave_way, peak[0] = peak[0], 0
            xemu_queue.drop_ticket(waiting)
            second = list(tok.ordered(pool, task, [(i, 0.03 * (6 - i)) for i in range(6)]))
        os.environ["PYTEST_CURRENT_TEST"] = "selftest"
        try:
            inert = xemu_queue.BatchToken("selftest", 4)
        finally:
            os.environ.pop("PYTEST_CURRENT_TEST")
        check("batch: a job keeps one task in flight while a sitting waits and all its workers otherwise, results "
              "in order; its token is listed while it runs; inert under pytest",
              gave_way == 1 and peak[0] == 4 and first == second == list(range(6)) and jobs == ["selftest"]
              and not xemu_queue.batch_jobs(SLOTS) and inert.inert and inert.path is None,
              f"{gave_way} {peak[0]} {second} {jobs}")
        envs = [xemu_env(Path("/tmp/azx-h.1"), m).get("XEMU_HEADLESS") for m in (None, "1", "0")]
        argv = [xemu_argv(Path("/tmp/azx-h.1"), 1, d) for d in (True, False)]
        both, old = DETERMINISTIC_MARK + OFFSCREEN_DETERMINISTIC_MARK, DETERMINISTIC_MARK   # v0.14-27, v0.14-12
        modes = [deterministic_mode(b, h, a) for b, h, a in (
            (both, "null", None), (both, "null", False), (both, "1", None), (both, "1", True), (old, "null", None),
            (old, "1", None), (b"", "null", None), (both, "0", None))]
        check("deterministic by default (Step X.22): the null renderer under -S -icount on the fork build unless "
              "'kept'; offscreen deterministic only when asked, on a build whose Vulkan path has it (Step X.26); "
              "a window never; only a build's own line says which display it took",
              envs == ["null", "1", "0"] and refused(xemu_env, Path("/"), "yes") and Sandbox("h").headless == "null"
              and argv[0] == argv[1] + list(ICOUNT_ARGS) and "-icount" not in argv[1]
              and modes == [True, False, False, True, True, False, False, False]
              and refused(deterministic_mode, old, "1", True) and refused(deterministic_mode, b"", "null", True)
              and isinstance(_err(Sandbox, "h", headless="0", deterministic=True), SystemExit)
              and Sandbox("h", headless="1", deterministic=True).deterministic is True
              and (Sandbox("h").app, app_path("kept"), app_path("/x/y.app")) == (FORK_APP, KEPT_APP, Path("/x/y.app"))
              and headless_mode("xemu_version: 0.14\nxemu: headless mode: offscreen\n") == "offscreen"
              and headless_mode("xemu: ignoring XEMU_HEADLESS=yes (use 1 or null)\n") is None, f"{envs} {modes}")
        sticks = [round(pipe_axis(f), 4) for f in (1.0, 0.5, -0.25, 0.0)]
        check("pipe_axis: a ControllerState stick value as the pipe's raw axis, past the game's dead zone",
              sticks == [1.0, 0.6831, -0.5247, 0.0], f"{sticks}")
        short = RSP.__new__(RSP)
        short.cmd = lambda pk: b"00" * 6   # the fork build's readable prefix of an 8-byte read
        try:
            got = f"returned {len(short.read(0x1000, 8))} bytes"
        except OSError as e:
            got = str(e)
        check("RSP.read: a short reply (a partly readable page's prefix) fails, never returns short",
              got == "read 0x1000: 6 of 8 bytes readable", got)

        stub, asked = RSP.__new__(RSP), []
        stub.cmd = lambda pk: asked.append(pk) or (b"OK" if pk[:1] == b"M" else b"00" * int(pk.split(b",")[1], 16))
        nv = [_err(stub.read, 0xFD800000, 4), _err(stub.read, 0xFCFFFFFE, 4), _err(stub.write, 0xFDFFFFFF, b"\0\0"),
              _err(stub.read, 0xFCFFFFFC, 4), _err(stub.read, 0xFE000000, 4), _err(stub.write, 0xFCFFFFFE, b"\0\0")]
        check("RSP: a read or write touching the GPU's register window 0xFD000000-0xFDFFFFFF is refused before any "
              "packet; one either side goes (AZ-308)",
              all(isinstance(e, OSError) and "AZ-308" in str(e) for e in nv[:3]) and nv[3:] == [None] * 3
              and asked == [b"m%x,%x" % (0xFCFFFFFC, 4), b"m%x,%x" % (0xFE000000, 4), b"M%x,%x:0000" % (0xFCFFFFFE, 2)],
              f"{nv} {asked}")

        # Step X.31a: guest RAM read from XEMU_RAM_SHM through the page tables (a real shared memory object, 4 MiB
        # of RAM) gives the bytes the gdbstub gives (a fake stub translating by its own table); only a page past
        # RAM costs a packet; the RAM's hash is the dump's
        shm = shared_memory.SharedMemory(create=True, size=0x400000, name=f"azx-st.{os.getpid()}", track=False)
        try:
            ram = shm.buf
            ram[:] = bytes((i * 7 + i // 4096) & 0xFF for i in range(0x400000))
            for pa, val in ((0xF000 + 4 * 0x300, 0xF003), (0xF000, 0x10003), (0xF000 + 4 * 0x200, 0x83),
                            (0x10000 + 4 * 0x11, 0x20003), (0x10000 + 4 * 0x12, 0x31003),
                            (0x10000 + 4 * 0x13, 0x500003)):
                struct.pack_into("<I", ram, pa, val)
            pages = {0xC0300000: 0xF000, 0x11000: 0x20000, 0x12000: 0x31000, 0x13000: 0x500000}
            mmio = bytes(range(256)) * 16   # the page past RAM, which only the stub serves

            def truth(pk: bytes | str) -> bytes:
                pk = pk.encode() if isinstance(pk, str) else pk
                if pk == b"g":
                    return (bytes(84) + struct.pack("<I", 0xF000) + bytes(256)).hex().encode()
                va, k = (int(x, 16) for x in pk[1:].split(b","))
                pa = (va - 0x80000000 if 0x80000000 <= va < 0x80400000
                      else pages.get(va & ~0xFFF, -1) | (va & 0xFFF) if (va & ~0xFFF) in pages else None)
                if pa is None:
                    return b"E14"
                return (bytes(ram[pa:pa + k]) if pa < 0x400000 else mmio[pa & 0xFFF:(pa & 0xFFF) + k]).hex().encode()
            stub, sent_m = RSP.__new__(RSP), []
            stub.cmd = lambda pk: sent_m.append(pk) or truth(pk)
            sbr = Sandbox("selftest")
            sbr.w, sbr._owner, sbr.st, sbr._g, sbr._halted = w, False, {"W": str(w), "ram_shm": shm.name}, stub, True
            sbr._ram()
            sent_m.clear()
            spans = ((0x11FF0, 0x20), (0x80001234, 0x100), (0xC0300000, 0x1000), (0x12FFC, 4))
            via_shm = [sbr.read(va, n) for va, n in spans]
            quiet = list(sent_m)
            past = sbr.read(0x13010, 0x10)
            by_stub = [stub.read(va, n) for va, n in (*spans, (0x13010, 0x10))]
            missing = (_err(sbr.read, 0x14000, 4), _err(stub.read, 0x14000, 4))
            hashed, want_sha = sbr.ram_sha256(), hashlib.sha256(ram).hexdigest()
            sbr.st["ram_shm"] = None
            sbr.ram_dump = lambda path: path.write_bytes(bytes(ram)) and None
            dumped = sbr.ram_sha256()
            sbr._close_ram()
        finally:
            del ram
            shm.close()
            shm.unlink()
        check("RAM from XEMU_RAM_SHM (Step X.31a): through the page tables (across a page to another frame, a 4 MiB "
              "page, the page directory's self-map) the same bytes as the gdbstub with no packet; a page past RAM "
              "through the gdbstub; a missing page raises as an E14 does; the RAM's sha256 the dump's",
              via_shm + [past] == by_stub and quiet == [] and sent_m[0] == b"m13010,10"
              and all(isinstance(e, OSError) for e in missing)
              and hashed == dumped == want_sha, f"{quiet} {sent_m[:2]} {missing}")

        class Counted(_FakeGuest):   # the fake stub, its packets logged
            def __init__(self):
                super().__init__()
                self.sent: list[str] = []

            def cmd(self, p):
                self.sent.append(p.decode() if isinstance(p, bytes) else p)
                return super().cmd(p)

            def cont(self):
                self.sent.append("c")
                super().cont()
        rg, five = Counted(), [0x1000, 0x1001, 0x2000, 0x3000, 0x4000]
        arm(rg, five)
        rg.eip, rg.sent = 0x1000, []
        resume(rg, five, 0x1000)
        on_bp = (rg.sent, rg.eip, rg.wait_stop(0.0), sorted(rg.bps) == five)
        rg.eip, rg.sent = 0x5000, []
        resume(rg, five)
        check("resume: only the breakpoint under the PC is lifted (z0, s, Z0, c: 4 packets, not 2N + 2), a "
              "breakpoint the step lands on still stops, and from a PC with none it is a plain continue (Step X.31a)",
              on_bp == (["z0,1000,1", "s", "Z0,1000,1", "c"], 0x1001, b"T05", True) and rg.sent == ["c"]
              and sorted(rg.bps) == five, f"{on_bp} {rg.sent}")
        # Step X.32b: v0.15's stub offers step-over and batched reads in its qSupported reply; the client turns
        # step-over on, resumes by a plain c, arms with no identical-byte rewrite, and sends a read's page pieces
        # (and several regions) in one qxemu.read; an older stub's connection keeps z0/s/Z0/c and an m a piece
        def fake_stub(offers: bytes) -> tuple[int, list[bytes]]:   # one client: a gdbstub's replies, its packets kept
            srv, got = socket.socket(), []
            srv.bind(("127.0.0.1", 0))
            srv.listen(1)
            srv.settimeout(5.0)

            def run() -> None:
                c, _ = srv.accept()
                buf = b""
                with c, srv:
                    c.settimeout(5.0)
                    while chunk := c.recv(65536):
                        buf += chunk
                        while (i := buf.find(b"$")) >= 0 and (j := buf.find(b"#", i)) >= 0 and len(buf) >= j + 3:
                            pk, buf = buf[i + 1:j], buf[j + 3:]
                            got.append(pk)
                            if pk.startswith(b"qSupported"):
                                rep = offers
                            elif pk.startswith(b"qxemu.read:"):
                                rep = b";".join(b"ab" * int(x.split(b",")[1], 16) for x in pk[11:].split(b";"))
                            elif pk[:1] == b"m":
                                rep = b"ab" * int(pk.split(b",")[1], 16)
                            else:
                                rep = b"OK"
                            c.sendall(b"+$%s#%02x" % (rep, sum(rep) & 0xFF))
            threading.Thread(target=run, daemon=True).start()
            return srv.getsockname()[1], got
        new_port, new_got = fake_stub(b"PacketSize=1000;qXfer:features:read+;qxemu.read+;Qxemu.stepover+")
        new = RSP(new_port)
        sent_reads = len(new_got)
        across = new.read(0xFF0, 0x20)
        pair = new.read_many([(0x2000, 4), (0x3FFC, 8)])
        new.s.close()
        old_port, old_got = fake_stub(b"PacketSize=1000;qXfer:features:read+")
        old = RSP(old_port)
        old_reads = (len(old_got), old.read(0xFF0, 0x20), old.read_many([(0x2000, 4)]))
        old.s.close()
        rewrites = {}
        for stepover in (False, True):
            sg = Counted()
            sg.stepover, sg.write = stepover, lambda va, data, k=stepover: rewrites.setdefault(k, []).append(va)
            arm(sg, five)
        armed_sent = list(sg.sent)
        sg.eip, sg.sent = 0x1000, []
        resume(sg, five, 0x1000)
        check("gdbstub on v0.15 (Step X.32b): step-over and batched reads taken where the stub offers them; resume a "
              "plain c and arm with no identical-byte rewrite then; a read's page pieces and several regions in one "
              "qxemu.read; an older stub keeps z0/s/Z0/c, the rewrite and an m a piece",
              (new.stepover, new.xread, old.stepover, old.xread) == (True, True, False, False)
              and new_got[:2] == [b"qSupported:swbreak+;hwbreak+;xemu.stepover+", b"Qxemu.stepover:1"]
              and new_got[sent_reads:] == [b"qxemu.read:ff0,10;1000,10", b"qxemu.read:2000,4;3ffc,4;4000,4"]
              and across == b"\xab" * 0x20 and pair == [b"\xab" * 4, b"\xab" * 8]
              and old_got[old_reads[0]:] == [b"mff0,10", b"m1000,10", b"m2000,4"]
              and old_reads[1:] == (b"\xab" * 0x20, [b"\xab" * 4])
              and armed_sent == ["?", *(f"Z0,{va:x},1" for va in five)] and rewrites == {False: five}
              and sg.sent == ["c"], f"{new_got} {old_got} {rewrites}")
        argv = xemu_argv(Path("/tmp/azx-grp.a1b2"), 40001)
        boxes = [Sandbox("h"), Sandbox("h", headless="0", owner_pad=1)]
        for b in boxes:
            b.w, b.st = Path("/tmp/azx-grp.a1b2"), {"owner_pad": b.owner_pad}
        plain, demo_argv = (b.argv(40001) for b in boxes)
        check("launch: xemu under nice -n 10, an owner demo's at normal priority (Step X.34), and either's exec'd "
              "command reads as a sandbox",
              argv[:4] == ["nice", "-n", "10", "nohup"] and _SANDBOX_APP.match(" ".join(argv[4:]))
              and plain == argv and demo_argv == argv[3:], f"{plain[:5]} {demo_argv[:2]}")
        # Step X.32 (v0.15): the fork's run-changing variables are never inherited (PROMPT-8 A's list), and the
        # launch line holds an HMP monitor in W, which hmp_command reads and a hung advance's probe asks (hazard 15)
        prior_env = {k: os.environ.get(k) for k in NOT_INHERITED}
        os.environ.update(dict.fromkeys(NOT_INHERITED, "/elsewhere"))
        try:
            leaked = sorted(set(NOT_INHERITED) & set(xemu_env(w)))
        finally:
            for k, v in prior_env.items():
                if v is None:
                    os.environ.pop(k)
                else:
                    os.environ[k] = v
        hd = tmp / "hmp"
        hd.mkdir()
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(hd / HMP_SOCK))
        srv.listen(2)
        heard: list = []

        def hmp_server() -> None:   # QEMU's banner and prompt, readline's echo (redrawn per key), the reply, a prompt
            for _ in range(2):
                c, _ = srv.accept()
                with c:
                    c.sendall(b"QEMU 10.1.0 monitor - type 'help' for more information\r\n(qemu) ")
                    heard.append(c.recv(64))
                    c.sendall(b"iininfinfo\x1b[Kinfo info sinfo stinfo status\r\nVM status: paused (debug)\r\n(qemu) ")
        threading.Thread(target=hmp_server, daemon=True).start()
        try:
            status = hmp_command(hd / HMP_SOCK, "info status")
            hang_probe(4242, hd, run=lambda argv, **_: subprocess.CompletedProcess(argv, 0, "", ""))
            probed = next(hd.glob("hang-4242-*[0-9].txt")).read_text(encoding="utf-8")
        finally:
            srv.close()
        check("v0.15 fit (Step X.32): no run-changing fork variable is inherited (traces, logs, live pads; v0.16.3's "
              "and v0.16.4's PFIFO and vblank opt-outs, Steps X.71, X.72); the launch line holds an HMP monitor in W; "
              "hmp_command reads its reply, and a hung advance's probe asks it 'info status' after the sample, ps and "
              "lsof",
              leaked == [] and {"XEMU_PFIFO_LOCK_BATCH", "XEMU_VBLANK_KQUEUE", "XEMU_PFIFO_FUSE"} <= set(NOT_INHERITED)
              and ["-monitor", f"unix:/tmp/azx-grp.a1b2/{HMP_SOCK},server,nowait"] == argv[-2:]
              and status == "VM status: paused (debug)" and heard == [b"info status\n"] * 2
              and probed.index("$ lsof") < probed.index("$ hmp info status\nVM status: paused (debug)"),
              f"{leaked} {argv[-2:]} {status!r} {heard}")
        # Step X.58: XEMU_STRICT_CPUID=1 on a build with it (a shim's SSE2 #UDs as on the Pentium III, AZ-021), never
        # inherited; a run log's fault lines give each fault's pc and feature, never its opcode bytes
        fault_log = ("xemu: strict CPUID: instructions the guest CPU lacks raise #UD\n"
                     "xemu: strict CPUID: #UD at 0011a2b4: F2 0F 58 C1 needs SSE2\n"
                     "xemu: strict CPUID: #UD at 0011a2c0: DF 08 needs SSE3 (further faults not reported)\n")
        faults = cpuid_faults(fault_log)
        check("strict CPUID (Step X.58): a sandbox asks XEMU_STRICT_CPUID=1 (never inherited), and its run log's "
              "faults are read as pc and feature with no opcode bytes",
              xemu_env(w, strict_cpuid=True).get("XEMU_STRICT_CPUID") == "1" and "XEMU_STRICT_CPUID" in NOT_INHERITED
              and faults == [{"pc": "0x11a2b4", "feature": "SSE2"}, {"pc": "0x11a2c0", "feature": "SSE3"}]
              and cpuid_faults("xemu: strict CPUID: instructions the guest CPU lacks raise #UD\n") == [], f"{faults}")
        # Step X.61 (v0.16.1): the windowed present's stall lines; a logged version as (major, minor, patch) and the
        # recordings that need v0.16's reset to replay across one; the null-RAM picture mode and the old reset by
        # env (null_ram only offscreen and deterministic); vanilla's GPU ceiling set against a build's heaviest flip;
        # frames in guest seconds by vblank-ns
        null_ok = Sandbox("st", headless="1", deterministic=True, null_ram=True).null_ram
        gb = gpu_budget({"flips": 3, "max": {"begin-end": 694, "triangles": 100, "blits": 2}})
        gs = Sandbox("st")
        gs_s = [gs.guest_s(60)]
        gs._vblank({"frame": 1, "running": False, "vblank-ns": 20_000_000})
        gs_s.append(gs.guest_s(50))
        check("v0.16.1 (Step X.61): present stalls and their lengths read from the run log; versions compared without their commits, "
              "a recording before 0.16.1 replayed across a reset with v0.16's; null_ram (offscreen deterministic "
              "only) and legacy_reset by env; a build's heaviest flip against vanilla's ceiling; frames by vblank-ns",
              present_stalls("xemu: present stall 1: no drawable for 120 ms; dropping frames until one comes\n"
                             "xemu: present stall 1 over after 980 ms, 52 frames dropped\n"
                             "xemu: present stall 2: no drawable for 101 ms; dropping frames until one comes\n")
              == [{"n": 1, "ms": 980}, {"n": 2, "ms": 101}]
              and [xemu_version_key(v) for v in ("0.16.1", "0.16", "v0.13.3-37-gd5ad94f4bf", "0.16-48-gb44bb02f9b",
                                                 None)] == [(0, 16, 1), (0, 16, 0), (0, 13, 3), (0, 16, 0), None]
              and [needs_legacy_reset(v) for v in ("0.16", "0.16.1", "0.17", None)] == [True, False, False, False]
              and null_ok and refused(lambda: Sandbox("st", null_ram=True))
              and refused(lambda: Sandbox("st", headless="1", null_ram=True))
              and xemu_env(w, null_ram=True)["XEMU_RENDER_NULL_RAM"] == "request"
              and xemu_env(w, legacy_reset=True)["XEMU_NV2A_RESET_IRQ"] == "0"
              and gb == {"begin-end": {"max": 694, "vanilla": 347, "ratio": 2.0, "over": True},
                         "triangles": {"max": 100, "vanilla": 213262, "ratio": 0.0, "over": False}}
              and [round(x, 6) for x in gs_s] == [1.0, 1.0], f"{gb} {gs_s}")
        # Step 2.173 (D603, D604): the frame-rate warning, never a refusal. A scene's steady flips (the first, partial,
        # dropped); L1 past vanilla's heaviest (the ceiling raised by the control's own scene), L2's note against the
        # control, L3 on real-time pairs: fell (a request), held, inconclusive (2 pairs; a loaded host) and within
        # the vanilla-vs-vanilla noise; the fork request's draft; ps's CPU time
        def fc(*tris):
            return frame_cost({"flips": len(tris) + 1, "per-flip": [{"triangles": 1, "begin-end": 1}]
                               + [{"triangles": t, "begin-end": 40} for t in tris]}, 2 * (len(tris) + 1))
        ctl, ceil0 = {"a1/idle": fc(100, 400, 200, 150)}, {"triangles": 250, "begin-end": 60}
        fell = {"scene": "a1/idle", "pairs": [{"control": 0.5, "build": 0.4}, {"control": 0.5, "build": 0.41},
                                              {"control": 0.49, "build": 0.42}], "flips_by": "guest"}
        held = {"scene": "a1/idle", "pairs": [{"control": 0.5, "build": b} for b in (0.475, 0.495, 0.48)],
                "flips_by": "display"}
        rows_fw = [  # (name, build triangles, rt, noise) -> (L1 warns, L3 warns, verdict, request, an "above" note)
            ("under", (100, 380, 210, 150), None, None, (0, 0, None, False, False)),
            ("over", (300, 600, 500, 550), None, None, (1, 0, None, False, True)),
            ("fps drop", (300, 600, 500, 550), fell, None, (1, 1, "fell", True, True)),
            ("held", (300, 600, 500, 550), held, None, (1, 0, "held", False, True)),
            ("2 pairs", (100, 380), {**fell, "pairs": fell["pairs"][:2]}, None, (0, 0, "inconclusive", False, False)),
            ("loaded host", (100, 380), {**fell, "pairs": [{**p, "control": 0.45} for p in fell["pairs"]]}, None,
             (0, 0, "inconclusive", False, False)),
            ("within noise", (100, 380), fell, rate_spread(fell["pairs"]), (0, 0, "held", False, False)),
            ("deterministic", (100, 380), {**fell, "mode": "deterministic"}, None, (0, 0, "inconclusive", False, False)),
            ("counted", (300, 600, 500, 550), {**fell, "flips_by": "gpu-counters"}, None,
             (1, 0, "inconclusive", False, True)),
            ("before X.68", (100, 380), {k: v for k, v in fell.items() if k != "flips_by"}, None,
             (0, 0, "inconclusive", False, False))]
        got_fw = {}
        for name, tris, rt_, noise_, want in rows_fw:
            fw_ = frame_warning({"a1/idle": fc(*tris)}, ctl, ceiling=ceil0, rt=rt_, noise=noise_)
            got_fw[name] = (sum(x.startswith("frame cost:") for x in fw_["warn"]),
                            sum(x.startswith("frame rate:") for x in fw_["warn"]), (fw_["fps"] or {}).get("verdict"),
                            fw_["request"], any("above vanilla here" in n_ for n_ in fw_["notes"]))
        w_over = frame_warning({"a1/idle": fc(300, 600, 500, 550)}, ctl, ceiling=ceil0, rt=held)
        how = {"run": {"binary": "e1e1e1e1e1e1", "load": "state vanilla-ig-a1 on a clone of the D98 drive",
                       "reached": "state (a1, the loaded save's level; no warp)"},
               "counts": {"binary": "e2e2e2e2e2e2", "load": "a cold boot at 256 MiB (the walk)",
                          "reached": "warp levels/water/w1"}}
        req = fork_request({"step": "2.173", "scene": "a1/idle", "rt": fell, "build": fc(300, 600, 500, 550),
                            "control": ctl["a1/idle"], "host": "a test Mac", "disc": "aaaaaaaaaaaa", **how})
        less = fork_request({"rt": fell, "build": ctl["a1/idle"], "control": fc(300, 600, 500, 550), "host": "h",
                             **how})
        unsaid = _err(fork_request, {"rt": fell, "host": "h", "run": how["run"],
                                     "counts": {"binary": "e2e2e2e2e2e2", "load": NOT_RECORDED}})
        no_pairs = frame_warning({}, rt={"scene": "a1/idle", "pairs": []})["fps"]
        ctl3 = [{"a1/idle": fc(100, 400, 200, 150 + i)} for i in range(3)]   # three distinct cold boots
        band = [len(frame_warning({"a1/idle": fc(100, t, 210, 150)}, c_, ceiling=ceil0)["warn"])
                for t, c_ in ((480, ctl3[:1]), (480, ctl3[:2]), (480, ctl3), (480, [ctl] * 3), (560, ctl3))]
        cpu = [ps_cpu_s(1, run=lambda argv, t=t, **_: subprocess.CompletedProcess(argv, 0, t, ""))
               for t in ("1-02:03:04.50\n", "0:01.25\n", "")]
        c0 = fc(100, 400, 200, 150)["kinds"]
        check("frame-rate warning (Step 2.173, D603, D604): a scene's steady flips past the partial first; L1 past "
              "vanilla's heaviest with the control's own scene raising the ceiling, L2's note against the control, "
              "L3 on real-time pairs (fell drafts a fork request; held, within the noise and inconclusive: 2 pairs, a "
              "loaded host, deterministic pairs, counted ones or a pair from before Step X.68, do not; no pairs at all "
              "says so); the draft names the scene, both rates, how they counted flips, each arm's binary, load and "
              "warp or state (Step X.68: a draft missing one, or with one not recorded, is refused by name) and the "
              "largest rise's host path (a build that drew less asks for none: the host's time); L1 1.2x past the ceiling within the boot band with 1, 2 or 3 distinct "
              "control boots or 3 warm repeats of one, 1.4x past it a warning with 3 distinct; ps's CPU time read",
              all(got_fw[n_] == want for n_, *_, want in rows_fw)
              and c0 == {"draws": {"begin-end": {"max": 40, "p95": 40, "median": 40}},
                         "geometry": {"triangles": {"max": 400, "p95": 400, "median": 150}}}
              and w_over["warn"] == ["frame cost: a1/idle triangles 600 a flip, 1.50x vanilla's heaviest (400, "
                                     "a1/idle)"]
              and w_over["ceiling"] == {"triangles": 400, "begin-end": 60}
              and "xemu held vanilla's rate here: no request" in w_over["notes"][-1]
              and "WHAT DROPS: a1/idle." in req and "vanilla flips 0.497 a vblank (29.8 fps)" in req
              and "this build 0.410 (24.6 fps)" in req and "triangles 1.50x -> per-draw overhead" in req
              and "a test Mac" in req and "{" not in req and cpu == [93784.5, 1.25, None]
              and "flips counted by the game's present counter, the NV2A counters off." in req
              and "rates (real time): binary e1e1e1e1e1e1; loaded from state vanilla-ig-a1 on a clone of the D98 "
                  "drive; a1/idle reached by state (a1" in req
              and "counts (det null): binary e2e2e2e2e2e2; loaded from a cold boot at 256 MiB (the walk); a1/idle "
                  "reached by warp levels/water/w1." in req
              and isinstance(unsaid, ValueError) and "missing counts.load, counts.reached" in str(unsaid)
              and no_pairs == {"verdict": "inconclusive", "why": "0 pair(s), 3 needed"}
              and "WHAT WE ASK: the host path behind the largest ratio: none of the counts rose" in less
              and band == [0, 0, 0, 0, 1],
              f"{got_fw} {w_over} {cpu} {band} {no_pairs}")
        # Step X.68 (the fork's reply on FRAME-8bffffeb0243, item 1), Step X.69 (its answer's key): a rate arm runs with
        # the NV2A counters off and counts flips without them: the display query's frame-ends (a process's total since
        # its launch, past 32 bits here) where the reply has it, else the game's present counter at this release's
        # address, each a difference within one xemu process (a relaunch mid-arm: no flips); a cost arm keeps the
        # counters and their flips
        def fake_arm(release: str, key: bool, relaunch: bool = False):
            import types
            ctr, asked = {"ends": (1 << 32) + 7, "pc": 100}, []

            def adv(n, gpu=False):
                asked.append(gpu)
                ctr["ends"] += n // 2
                ctr["pc"] += n // 2
                if relaunch:
                    fsb.st["pid"] += 1
                return {"frame": 600 + n, **({"gpu-counters": {"flips": n // 2}} if gpu else {})}
            fsb = types.SimpleNamespace(
                st={"pid": 4242, "release": release, "display_query": True}, host_profile=lambda: None,
                frame_advance=adv, read_u32=lambda va: ctr["pc"] if va == {"usa": PRESENT_COUNT,
                                                                           "europe": 0x1ABB8C}[release] else 0,
                qmp=lambda cmd, **_: {"return": {"frame": 1, "flips": 999, **({FRAME_ENDS: ctr["ends"]} if key
                                                                               else {})}})
            real_ps, globals()["ps_cpu_s"] = ps_cpu_s, lambda pid: None
            try:
                return [timed_advance(fsb, 60, gpu=g)[1] for g in (False, "per-flip")], asked
            finally:
                globals()["ps_cpu_s"] = real_ps
        arms = {f"{rel} {key} {rl}": fake_arm(rel, key, rl)
                for rel, key, rl in (("usa", True, False), ("usa", False, False), ("europe", False, False),
                                     ("usa", True, True))}
        check("rate arms counter-free (Steps X.68, X.69, the fork's item 1): gpu=False asks for no NV2A counters and "
              "counts the flips by the display query's frame-ends where the reply has it (a process's running "
              "total: a difference within one process, never wrapped at 32 bits), else by the game's present "
              "counter at the release's address (Europe's 0x1ABB8C); an arm whose xemu relaunched counts none; a "
              "cost arm keeps the counters' flips",
              all(asked == [False, "per-flip"] for _, asked in arms.values())
              and [[(t.get("flips"), t.get("per_vblank"), t.get("flips_by")) for t in ts] for ts, _ in arms.values()]
              == [[(30, 0.5, "display"), (30, 0.5, "gpu-counters")], [(30, 0.5, "guest"), (30, 0.5, "gpu-counters")],
                  [(30, 0.5, "guest"), (30, 0.5, "gpu-counters")],
                  [(None, None, None), (30, 0.5, "gpu-counters")]],
              f"{arms}")
        # Step X.61: a start parked by a build of a newer savestate stream than the sandbox's is refused by name
        # before anything is loaded (v0.16.1's to v0.16.4's states don't load in v0.16 or the kept build); one of its
        # own stream (Steps X.66, X.71, X.72: v0.16.2's in v0.16.1, v0.16.3's in v0.16.2 and back, v0.16.4's in
        # v0.16.3), an older or an unknown one goes on
        pk = Sandbox("st")
        pk.w, pk.st = w, {"xemu_version": "0.16", "parked": {"p-new": {"disc": "dvd.iso", "xemu": "0.16.1"},
                                                              "p-v2": {"disc": "dvd.iso", "xemu": "0.16.2"},
                                                              "p-v3": {"disc": "dvd.iso", "xemu": "0.16.3"},
                                                              "p-v4": {"disc": "dvd.iso", "xemu": "0.16.4"},
                                                              "p-old": {"disc": "dvd.iso", "xemu": "0.16"}}}
        newer, newer2, newer3 = _err(pk.unpark, "p-new"), _err(pk.unpark, "p-v2"), _err(pk.unpark, "p-v3")
        newer4 = _err(pk.unpark, "p-v4")
        pk.await_ready = lambda: (_ for _ in ()).throw(RuntimeError("past the check"))   # the next step after it
        pk.st["launched_at"] = 1.0
        older = _err(pk.unpark, "p-old")
        pk.st["xemu_version"] = "0.16.1"
        same_stream = _err(pk.unpark, "p-v2")
        pk.st["xemu_version"] = "0.16.2"
        same3, back3 = _err(pk.unpark, "p-v3"), (pk.st.update(xemu_version="0.16.3"), _err(pk.unpark, "p-v2"))[1]
        same4 = _err(pk.unpark, "p-v4")
        check("unpark (Steps X.61, X.66, X.71, X.72): a start parked by a newer savestate stream than the sandbox's is "
              "refused by name; one of its own stream (v0.16.2's in v0.16.1, v0.16.3's in v0.16.2 and back, "
              "v0.16.4's in v0.16.3) or an older one passes the check",
              isinstance(newer, SystemExit) and "parked by xemu 0.16.1, newer than this sandbox's 0.16" in str(newer)
              and isinstance(newer2, SystemExit) and "parked by xemu 0.16.2" in str(newer2)
              and isinstance(newer3, SystemExit) and "parked by xemu 0.16.3" in str(newer3)
              and isinstance(newer4, SystemExit) and "parked by xemu 0.16.4" in str(newer4)
              and isinstance(older, RuntimeError) and isinstance(same_stream, RuntimeError)
              and isinstance(same3, RuntimeError) and isinstance(back3, RuntimeError) and isinstance(same4, RuntimeError)
              and [state_stream(v) for v in ("0.16.4", "0.16.3", "0.16.2", "0.16.1", "0.16", "v0.13.3-37-gd5ad94f4bf",
                                             "0.17", None)] == [1, 1, 1, 1, 0, 0, 1, None],
              f"{newer!r} {newer2!r} {newer3!r} {newer4!r} {older!r} {same_stream!r} {same3!r} {back3!r} {same4!r}")
        # Step X.61 (v0.16.1): the QMP watch monitor on W's own socket, a listen backlog and the guest bugcheck report
        # where the build has them, never inherited; the run log's bugcheck and dead-halt lines read as code,
        # parameters and return address (V22's flagged) or eip and esp, in order
        env61 = xemu_env(w, watch=True, backlog=True, bugcheck=True)
        bc = bugchecks("xemu: guest bugcheck: KeBugCheckEx at 0x80019442 hooked\n"
                       "xemu: guest bugcheck 0x0000000a (0x7ffffff8, 0x00000002, 0x00000000, 0x0018d0fc) from 0x0018d101\n"
                       "xemu: guest halted with interrupts disabled at 0x800151ef (esp 0x8003a9f0)\n"
                       "xemu: guest bugcheck 0x0000001e (0xc000001d, 0x0008ccc0, 0x00000000, 0x00000000) from 0x80012345"
                       " (further bugchecks not reported)\n")
        check("v0.16.1 (Step X.61): a sandbox opens the QMP watch monitor on W's own socket and asks a listen backlog "
              "and the guest bugcheck report (never inherited); a run log's bugchecks and dead halts are read in order, "
              "V22's parameters named",
              env61["XEMU_QMP_WATCH"] == f"unix:{w / WATCH_SOCK},server=on,wait=off"
              and env61["XEMU_SOCKET_BACKLOG"] == str(BACKLOG) and env61["XEMU_GUEST_BUGCHECK"] == "1"
              and not {"XEMU_QMP_WATCH", "XEMU_SOCKET_BACKLOG", "XEMU_GUEST_BUGCHECK"} & set(xemu_env(w))
              and [b["kind"] for b in bc] == ["bugcheck", "halt", "bugcheck"]
              and bc[0] == {"kind": "bugcheck", "code": "0xa", "params": ["0x7ffffff8", "0x2", "0x0", "0x18d0fc"],
                            "ret": "0x18d101", "v22": True}
              and bc[1] == {"kind": "halt", "eip": "0x800151ef", "esp": "0x8003a9f0"} and not bc[2]["v22"]
              and bugcheck_list(bc[1:]) == "halt at 0x800151ef with interrupts off, bugcheck 0x1e (0xc000001d, "
                                           "0x8ccc0, 0x0, 0x0) from 0x80012345", f"{bc}")
        # Step X.94 (0.16.4-3-g95e7ffc7ec): a bugcheck's registers line joins its item; its QMP event's stack (guest
        # memory) is never kept: scrub_event leaves its length, sha256[:12] and the trap frame's EIP decoded in memory
        # (a 0x1E's: the EIP, CS 8, EFLAGS triples whose EIP is p2), and Sandbox.bugchecks adds them, and the event's
        # EIP, to the run log's item by launch and count, nothing of the stack in sandbox.json
        regs94 = ("xemu: guest bugcheck registers: eax=00000001 ecx=00000002 edx=00000003 ebx=00000004 esp=d003eb40 "
                  "ebp=d003eb80 esi=00000005 edi=ffffffff eflags=00000246 (stack: 4096 bytes in the event)\n")
        log94 = ("xemu: guest bugcheck 0x0000001e (0xc0000005, 0x00122261, 0x00000000, 0x00000013) from 0x8001ca36\n"
                 + regs94 + "xemu: guest halted with interrupts disabled at 0x800151ef (esp 0x8003a9f0)\n")
        bc94 = bugchecks(log94)
        stack94 = bytearray(4096)   # a decoy triple, then the trap frame and the context record
        struct.pack_into("<3I", stack94, 0x40, 0x1234, TRAP_CS, 0x246)
        struct.pack_into("<3I", stack94, 0x2A8, 0x122261, TRAP_CS, 0x10246)
        struct.pack_into("<3I", stack94, 0x400, 0x122261, TRAP_CS, 0x10202)
        ev94 = scrub_event({"event": "XEMU_GUEST_BUGCHECK", "data": {
            "code": 0x1E, "params": [0xC0000005, 0x122261, 0, 0x13], "caller": 0x8001CA36, "count": 1,
            "regs": {"eip": 0x80019442, "esp": 0xD003EB40}, "stack": stack94.hex()}})
        other94 = scrub_event({"event": "XEMU_GUEST_BUGCHECK", "data": {"code": 0x8E, "params": [0, 0, 0, 0],
                                                                        "stack": stack94.hex()}})
        hb94 = Sandbox("bc")
        hb94.w, hb94._owner = tmp / "azx-st.bc94", False
        hb94.w.mkdir()
        (hb94.w / "run.log").write_text(log94, encoding="utf-8")
        hb94.st = {"W": str(hb94.w), "launches": 1, "events": []}
        fq94 = type("Q94", (), {"events": collections.deque([ev94, {"event": "XEMU_READY", "data": {}}])})()
        hb94._hear_bugchecks(fq94)
        merged94, saved94 = hb94.bugchecks(), (hb94.w / "sandbox.json").read_text(encoding="utf-8")
        shutil.rmtree(hb94.w)
        check("bugcheck registers (Step X.94): a run log's registers line joins its bugcheck; the event's stack is "
              "scrubbed on arrival to its length, sha256[:12] and trap frame EIP (a 0x1E's: p2's triples), merged into "
              "the run log's item with KeBugCheckEx's EIP, and never stored",
              bc94[0]["regs"] == {"eax": "0x1", "ecx": "0x2", "edx": "0x3", "ebx": "0x4", "esp": "0xd003eb40",
                                  "ebp": "0xd003eb80", "esi": "0x5", "edi": "0xffffffff", "eflags": "0x246"}
              and bc94[0]["stack_bytes"] == 4096 and bc94[1] == {"kind": "halt", "eip": "0x800151ef", "esp": "0x8003a9f0"}
              and "stack" not in ev94["data"] and ev94["data"]["stack_bytes"] == 4096
              and ev94["data"]["stack_sha12"] == hashlib.sha256(stack94).hexdigest()[:12]
              and (ev94["data"]["trap_eip"], ev94["data"]["trap_at"]) == ("0x122261", ["0x2a8", "0x400"])
              and other94["data"]["trap_eip"] == "0x1234" and [e["event"] for e in fq94.events] == ["XEMU_READY"]
              and (merged94[0]["trap_eip"], merged94[0]["eip"], merged94[0]["regs"]["edi"]) == ("0x122261",
                                                                                               "0x80019442", "0xffffffff")
              and '"stack"' not in saved94 and "stack_sha12" in saved94
              and bugcheck_list(merged94[:1]).startswith("bugcheck 0x1e (0xc0000005, 0x122261, 0x0, 0x13) from "
                                                         "0x8001ca36, trap eip 0x122261; regs eax=0x1 ecx=0x2"),
              f"{bc94} {ev94} {merged94} {bugcheck_list(merged94[:1])}")
        # Step X.32b (AZ-475): a demo as played runs under -icount align=on,sleep=on with XEMU_ICOUNT_LIVE_PADS, so its
        # input record replays tick for tick in a deterministic sandbox; the owner's gamepad takes the keyboard pad's
        # port by xemu-input-bind once xemu is ready (nothing plugged: the pad follows its port across loads, no
        # replug), its scratch config binding nothing of the owner's; every sandbox on a build with it loads with
        # XEMU_LOADVM_ADD_PADS, so a demo's state plugs the pads it holds in a replay sandbox
        live_argv = xemu_argv(Path("/tmp/azx-grp.a1b2"), 40001, live_pads=True)
        live_env = xemu_env(w, live_pads=True, add_pads=True)
        bad_live = [_err(Sandbox, "h", live_pads=True, **kw) for kw in (
            {"headless": "1", "deterministic": True}, {"headless": "0", "owner_pad": 1}, {"headless": "null"})]
        lb = Sandbox("h", headless="0", owner_pad=2, live_pads=True)
        lb.w, lb._owner, binds = w, False, []
        lb.st = {"W": str(w), "owner_pad": 2, "owner_guid": "03000000000000000000000000000001", "live_pads": True,
                 "ready_at": 2.0, "ready_s": 0.1, "launched_at": 1.0, "events": []}
        lb.qmp = lambda cmd, **a: binds.append((cmd, a)) or {"return": {"pending": True}}
        lb._bind_owner_pad()
        live_toml = tomllib.loads(scratch_toml(_SAMPLE_TOML.format(fx=fx), str(w), None))["input"]["bindings"]
        check("demos as played (Step X.32b, AZ-475): live pads under -icount align=on,sleep=on; the owner's gamepad "
              "onto the keyboard pad's port by xemu-input-bind, nothing of the owner's in the config; a window or "
              "offscreen, never deterministic, the owner on that port only; loads plug missing pads (ADD_PADS)",
              live_argv[-3:] == list(ICOUNT_LIVE_ARGS) and "-icount" not in argv
              and (live_env["XEMU_ICOUNT_LIVE_PADS"], live_env["XEMU_LOADVM_ADD_PADS"]) == ("1", "1")
              and "XEMU_LOADVM_ADD_PADS" not in xemu_env(w) and all(isinstance(e, SystemExit) for e in bad_live)
              and lb.live_pads and binds == [("xemu-input-bind", {"port": 2, "source": "gamepad",
                                                                  "guid": "03000000000000000000000000000001"})]
              and "pending" in lb.st["events"][-1] and {k: v for k, v in live_toml.items() if k[-1].isdigit()} == {
                  "port2": "keyboard"},
              f"{live_argv[-3:]} {bad_live} {binds} {live_toml}")
        (w / "sandbox.json").write_text(json.dumps(
            {"W": str(w), "group": "st", "app": str(KEPT_APP), "disc": str(fx / "vanilla.iso"),
             "out": None, "hdd": None, "fixtures": str(fx)}), encoding="utf-8")
        typed = w.resolve()   # /private/tmp/..., as `pwd -P` prints it
        check("attach: W is the path up launched xemu by, whatever form the caller typed",
              str(typed) != str(w) and Sandbox.attach(typed).w == w, f"{typed}")
        # held sandboxes (Step X.81d): a sitting's run that ends holds its sandbox (its xemu quit, the sources checked,
        # W and its slot kept, a reaper started); that sitting's next run with the same sandbox arguments claims it
        # (a relaunch on W: no queue), another sitting's or other arguments' doesn't; an unclaimed one is downed by
        # its reaper, or at once for a launch the admission rule refuses
        hws = [tmp / f"azx-held.{i}" for i in (1, 2)]
        stubs = {"_quit": lambda self, relaunch=False: {"quit": "qmp"},
                 "_baselines": lambda self: {"sources_equal": True, "pref_dir_equal": True, "baseline_lines": 1,
                                             "kept": False},
                 "relaunch": lambda self: relaunched.append(self.w.name) or self.st.update(pid=4322)}
        real_stubs, relaunched = {k: getattr(Sandbox, k) for k in stubs}, []
        for k, v in stubs.items():
            setattr(Sandbox, k, v)
        try:
            for hw in hws:
                hw.mkdir()
                shutil.copy(w / "xemu.toml", hw / "xemu.toml")
                (hw / "sandbox.json").write_text(json.dumps(
                    {"W": str(hw), "group": "held", "app": str(KEPT_APP), "disc": str(fx / "vanilla.iso"), "out": None,
                     "hdd": None, "fixtures": str(fx), "launches": 1, "pid": 4321, "events": []}), encoding="utf-8")
                _write_slot(hw, {"pid": 4321})
            first = Sandbox.attach(hws[0]).hold_for_sitting("ev-a", {"headless": None}, hold_s=5.0)
            kept = [(held_dir() / f"{hws[0].name}.json").exists(), (SLOTS / f"{hws[0].name}.json").exists()]
            others = [Sandbox.claim("ev-a", {"headless": "1"}), Sandbox.claim("ev-b", {"headless": None})]
            mine = Sandbox.claim("ev-a", {"headless": None}, out=tmp / "next")
            claimed = [mine is not None and mine.w == hws[0] and mine.out == (tmp / "next").resolve(),
                       list(relaunched), (held_dir() / f"{hws[0].name}.json").exists(),
                       [e.split(" ", 1)[1] for e in mine.st["events"]], mine.st["slot_wait_s"]]
            Sandbox.attach(hws[1]).hold_for_sitting("ev-a", {"headless": None}, hold_s=5.0)
            given = release_held()   # a launch the rule refuses takes it
            mine.hold_for_sitting("ev-a", {"headless": None}, hold_s=0.5)   # no next run: its reaper downs it
            end = time.monotonic() + 30
            while hws[0].exists() and time.monotonic() < end:
                time.sleep(0.2)
        finally:
            for k, v in real_stubs.items():
                setattr(Sandbox, k, v)
        check("held sandbox (Step X.81d): a run's end holds it, W and its slot kept; the sitting's next run with the "
              "same arguments claims it with a relaunch on W (its report only that run's events and wait), no other "
              "does; an unclaimed one is downed by its reaper, or given up to a launch the rule refuses",
              first.get("held") and kept == [True, True] and others == [None, None]
              and claimed == [True, ["azx-held.1"], False, ["claimed by the sitting's next run"], 0.0] and given == 1
              and not any(hw.exists() or (SLOTS / f"{hw.name}.json").exists() for hw in hws)
              and not list(held_dir().glob("azx-*.json")), f"{first.get('held')} {kept} {others} {claimed} {given}")
        cli_loads, real_loadvm = [], Sandbox.loadvm   # AZ-465: the CLI names a load's disc (an owner demo needs it)
        Sandbox.loadvm = lambda _sb, tag, **kw: cli_loads.append((tag, kw)) or {}
        try:
            main(["loadvm", str(w), "vanilla-flat", "--disc", "dvd.iso"])
        finally:
            Sandbox.loadvm = real_loadvm
        check("loadvm CLI (AZ-465): --disc names the disc the load puts in the tray",
              cli_loads == [("vanilla-flat", {"disc": "dvd.iso"})], f"{cli_loads}")
        # the sandbox on a fake gdbstub and a fake QMP
        sb = Sandbox("selftest")
        sb.fixtures, sb.w, sb._owner = fx, w, False
        sb.st = {"W": str(w), "hdd": None, "saved_tags": [], "events": [], "gdb_ready_at": 0.0}
        sb.sc = {"y": 235, "a": 232}
        sb._g, sb._halted = _FakeGuest(), True
        sent: list[str] = []
        sb.send = lambda line, **tag: sent.append(f"{''.join(f'{k}={v} ' for k, v in tag.items() if v is not None)}{line}")
        ts = [r and round(r["t"], 4) for r in (sb.player(), sb.player())]
        check("player() twice: two ticks, not the same one again",
              None not in ts and ts[1] > ts[0], f"t {ts[0]} -> {ts[1]}")
        poked: list[int] = []
        cap = sb.capture(10, {2: "down y", 5: ["up y", "down a", lambda sb_, row, rows_: poked.append(row["k"])]},
                         bps=[JUMP_INIT], label="selftest-capture")
        rows = cap["rows"]
        check("capture: 10 distinct ticks, duplicate hits folded",
              len(rows) == 10 and len({r["t"] for r in rows}) == 10 and cap["meta"]["dups"] > 0,
              f"{cap['meta']['dups']} dups")
        check("capture: a callable in a tick's action list runs, and the labelled JSON is written",
              poked == [5] and json.loads(Path(cap["path"]).read_text(encoding="utf-8"))["meta"]["rows"] == 10)
        check("capture: the schedule, and a held button released at the end",
              sent == ["down 235", "up 235", "down 232", "up 232"], f"{sent}")
        sent.clear()
        sb.capture(3, {0: "trigger lt 1", 1: "clear"})
        check("clear: a capture's clear after 'trigger lt 1' sends the pipe's clear alone (it releases the trigger; "
              "AZ-390 refuted) and has nothing left to release at the end",
              sent == ["trigger lt 1.000000", "clear"], f"{sent}")
        sent.clear()
        sb.capture(4, {1: ["axis lx 0.5", "trigger rt 1"], 2: "axis lx 0"})
        sb.axis("ly", -1.0, after=2)
        try:
            sb.axis("lz", 1.0)
            bad_axis = "taken"
        except ValueError:
            bad_axis = "refused"
        check("capture: the fork build's analog pipe lines, the axes still off rest put back at the end; "
              "a frame-tagged line; an unknown axis refused",
              sent == ["axis lx 0.500000", "trigger rt 1.000000", "axis lx 0.000000", "trigger rt 0",
                       "after=2 axis ly -1.000000"] and bad_axis == "refused", f"{sent} {bad_axis}")
        piped: list[str] = []
        real_send_keys, globals()["send_keys"] = send_keys, lambda fifo, line: piped.append(line)
        try:
            by_name = _err(Sandbox.send, sb, "down start")
            by_tagged_name = _err(Sandbox.send, sb, "+2 up a")
            Sandbox.send(sb, f"down {sb.code('y')}")
        finally:
            globals()["send_keys"] = real_send_keys
        check("send: a button's name refused, naming sb.code(name) (the pipe reads only a scancode: Step 2.153's "
              "'down start' did nothing), behind a line's own frame tag too; a scancode piped",
              isinstance(by_name, ValueError) and "sb.code('start')" in str(by_name)
              and isinstance(by_tagged_name, ValueError) and "sb.code('a')" in str(by_tagged_name)
              and piped == ["down 235"], f"{by_name!r} {by_tagged_name!r} {piped}")
        check("capture: breakpoint hits logged; the chain read",
              cap["hits"] and all(h["va"] == hex(JUMP_INIT) for h in cap["hits"])
              and (rows[0]["hp"], rows[0]["armor_level"], rows[0]["flaps"], rows[0]["fuel"]) == (318, 3, 5, 1.0))
        # AZ-346: a row across a page, which the stub refuses in one piece, reads whole in pieces
        mem = bytes(range(256)) * 32
        page = RSP.__new__(RSP)
        page.cmd = lambda pk: (b"E14" if (int(pk[1:].split(b",")[0], 16) & 0xFFF) + int(pk.split(b",")[1], 16) > 0x1000
                               else mem[int(pk[1:].split(b",")[0], 16) - 0x1653000:][:int(pk.split(b",")[1], 16)].hex()
                               .encode())
        check("RSP.read: an entity row across a page reads whole, in pieces (AZ-346)",
              page.read(0x1653E60, ENT_SPAN) == mem[0xE60:0xE60 + ENT_SPAN])
        want = {"stick": (0.0, 0.0)}
        cap = sb.capture(4, on_tick=lambda sb_, row, rows_: want.update(stick=(0.25 * row["k"], -1.0)), pad=True,
                         hooks={INPUT_BUILD: lambda sb_, r_: sb_.write_pad(l3.Pad(stick=want["stick"]), stick_only=True)})
        pads = [(r["pad"]["lx"], r["pad"]["ly"]) for r in cap["rows"]]
        check("capture hooks: write_pad at INPUT_BUILD puts a stick set at a tick in port 2's ControllerState at "
              "the next one, after the poll, nothing logged",
              pads == [(0.0, 0.0), (0.0, -1.0), (0.25, -1.0), (0.5, -1.0)] and cap["hits"] == [], f"{pads}")
        cap = sb.capture(10, lambda sb_, row, rows_: ["stop"] if row["k"] == 3 else None)
        check("capture: a per-tick callable passed as the schedule runs on every tick, and 'stop' ends it",
              len(cap["rows"]) == 4 and str(cap["meta"]["stop"]).startswith("a stop action"), f"{cap['meta']['stop']}")
        calls: list[tuple[str, dict]] = []
        tray = {"file": f"{w}/mod.iso", "status": "prelaunch"}   # a deterministic launch (-S), never run yet

        def fake_qmp(cmd: str, **args) -> dict:
            calls.append((cmd, args))
            if cmd == "query-block":
                return {"return": [{"device": CD, "inserted": {"file": tray["file"]}}]}
            if cmd == "blockdev-change-medium":
                tray["file"] = args["filename"]
            if cmd == "query-status":
                return {"return": {"status": tray["status"]}}
            if cmd == "cont":
                tray["status"] = "running"
            return {"return": "" if cmd == "human-monitor-command" else {}}
        sb.qmp, sb.alive = fake_qmp, lambda: True
        sb.loadvm("vanilla-flat", halt_at_tick=False)
        del sb.alive
        names = [c for c, _ in calls]
        check("loadvm: the vanilla disc goes back in the tray first; a deterministic launch's first load (-S) "
              "then runs the guest, as any loadvm without halt_at_tick leaves it",
              "blockdev-change-medium" in names and names.index("blockdev-change-medium")
              < names.index("human-monitor-command") and tray["file"] == f"{w}/dvd.iso"
              and names[-1] == "cont" and tray["status"] == "running", f"{names}")
        # AZ-465: a savevm records the disc in the tray and a load of that tag puts it back, never the vanilla disc
        # by default; each load names its disc; an owner demo refuses a load whose disc no one named or recorded
        sb.alive = lambda: True
        tray["file"] = f"{w}/b-abc.iso"
        sb.savevm("s-build")
        tray["file"] = f"{w}/dvd.iso"
        built = sb.loadvm("s-build", halt_at_tick=False)
        in_build, said = tray["file"], sb.st["events"][-1]
        sb.st["owner_pad"], sb.usb = 1, (lambda: {"1.3": "USB Hub", "1.3.1": "gamepad_0"})
        demo_err = str(_err(sb.loadvm, "vanilla-flat", halt_at_tick=False))
        named = sb.loadvm("vanilla-flat", halt_at_tick=False, disc="dvd.iso")["disc"]
        sb.st.pop("owner_pad")
        del sb.alive, sb.usb
        check("loadvm (AZ-465): a tag saved here loads with the disc its savevm had in the tray, named in its event and "
              "result; an oracle tag with the vanilla disc; an owner demo refuses a load whose disc it can't name",
              built["disc"] == "b-abc.iso" and in_build == f"{w}/b-abc.iso" and said.endswith("(disc b-abc.iso)")
              and "AZ-465" in demo_err and named == "dvd.iso" and tray["file"] == f"{w}/dvd.iso"
              and sb.st["tag_discs"]["s-build"] == "b-abc.iso", f"{built.get('disc')} {said} {demo_err[:80]}")
        # AZ-466: an owner demo launches only from an un-niced process; its loads wait for the owner's pad (its hub
        # on USB 1.3 for port 1) and plug the replug watcher's demo hub a state saved here holds; its states are
        # saved under a disc in W, said, with the pads they hold; a load of a state saved elsewhere says when the
        # menu asks (Step X.104: it refuses none, it loads a state whose image the tray holds without asking)
        info = ("  Device 0.1, Port 1, Speed 12 Mb/s, Product USB Hub\n  Device 0.2, Port 1.4, Speed 12 Mb/s, "
                "Product USB Hub\n  Device 0.3, Port 1.4.1, Speed 12 Mb/s, Product Microsoft Gamepad, ID: gamepad_0\n"
                "  Device 0.4, Port 1.1, Speed 12 Mb/s, Product USB Hub, ID: demohub\n")
        seen_usb = [{}, {}, usb_devices(info) | {"1.3": "USB Hub"}]
        sb.st.update(owner_pad=1, events=[])
        sb.alive, sb.usb = (lambda: True), (lambda: seen_usb.pop(0) if len(seen_usb) > 1 else seen_usb[0])
        real_sleep, time.sleep, real_getpriority = time.sleep, (lambda _s: None), os.getpriority
        try:
            calls.clear()
            tray["file"] = f"{w}/b-abc.iso"
            sb.savevm("s-demo")
            saved_said = next(e for e in sb.st["events"] if "savevm s-demo" in e)
            tray["file"], tray["status"], n_calls = "/elsewhere/b-abc.iso", "running", len(calls)
            outside = str(_err(sb.savevm, "s-out"))
            refused_stops = [c for c, _ in calls[n_calls:] if c == "stop"]   # the owner's game left running
            sb.st["tag_usb"]["s-demo"] = {"1.1": "USB Hub", "1.1.1": "demopad", "1.3": "USB Hub"}
            seen_usb[:] = [{}, {}, {"1.3": "USB Hub", "1.4": "USB Hub"}]
            waited = sb.loadvm("s-demo", halt_at_tick=False)
            plugged = [a for c, a in calls if c == "device_add"]
            waits = [e for e in sb.st["events"] if "waiting for the owner's pad on port 1 (USB 1.3" in e]
            sb.loadvm("vanilla-flat", halt_at_tick=False, disc="dvd.iso")
            elsewhere = sb.st["events"][-1]
            sb.alive, os.getpriority = (lambda: False), (lambda *_a: 5)   # a zsh '&' job: up and relaunch refuse
            niced = [str(_err(Sandbox("demo", headless="0", owner_pad=1).up)), str(_err(sb.relaunch))]
        finally:
            time.sleep, os.getpriority = real_sleep, real_getpriority
            sb.st.pop("owner_pad")
            del sb.alive, sb.usb
        check("owner demo (AZ-466): up and relaunch refuse a niced launcher (zsh's bg_nice); a load waits for the "
              "owner's pad's hub (Port 1.3 for port 1), saying so, and plugs the demo hub its state holds; a state "
              "saved under the demo's own disc path, said, and one outside it refused with the game left running; a "
              "load of one saved elsewhere says the Snapshots menu asks (Load Anyway) unless the tray holds its image, "
              "never that it refuses it",
              all("bg_nice" in e for e in niced) and demo_priority(0) is None and not refused_stops
              and usb_devices(info)["1.1"] == "demohub" and usb_devices(info)["1.4.1"] == "gamepad_0"
              and hub_port(1) == "1.3" and hub_port(2) == "1.4" and hub_port(3) == "1.1"
              and "saved under the disc path" in saved_said and f"{w}/b-abc.iso" in saved_said and "AZ-466" in outside
              and waited["pad_wait_s"] is not None and len(waits) == 1
              and plugged == [{"driver": "usb-hub", "port": "1.1", "ports": 3, "id": "demohub"},
                              {"driver": "usb-xbox-gamepad", "index": 0, "port": "1.1.1", "id": "demopad"}]
              and "Load Anyway" in elsewhere and "refuse" not in elsewhere, f"{saved_said[:60]} {plugged} {waits}")
        # AZ-439: the keyboard pad on port 1 (a demo recorded on the owner's port 1 replays as the owner's pad): the
        # scratch config binds it there and nothing on port 2; a replay sandbox on the demo's drive adopts its tags
        # (note_tag's meta: disc, pads, the recorded port), plugs the pad hubs its state holds that the machine lacks
        # before the load (port 2's hub reading player 2, nothing bound: neutral; the demo hub reading player 1),
        # and refuses a recording of another port than the keyboard pad's
        p1 = tomllib.loads(scratch_toml(_SAMPLE_TOML.format(fx=fx), str(w), pad_port=1))["input"]["bindings"]
        p1_demo = tomllib.loads(scratch_toml(two, str(w), 3, pad_port=1))["input"]["bindings"]
        sbr = Sandbox("rp", pad_port=1)
        sbr.w, sbr._owner, sbr.qmp, sbr.alive = w, False, fake_qmp, (lambda: True)
        sbr.st = {"W": str(w), "pid": 1, "pad_port": 1, "events": [], "saved_tags": [], "ready_at": 1.0,
                  "launched_at": 0.0, "ready_s": 0.0}
        sbr.usb = lambda: {"1.3": "USB Hub", "1.3.1": "gamepad_0"}   # the keyboard pad xemu plugged on port 1
        sbr.hdd = tmp / "demo-drive.qcow2"
        demo_tags = {"x-A": {"clk": 5.0, "lvl": "levels/town", "disc": "b-abc.iso", "record_port": 1,
                             "usb": {"1.3": "USB Hub", "1.3.1": "gamepad_0", "1.4": "USB Hub", "1.4.1": "gamepad_1",
                                     "1.1": "USB Hub", "1.1.1": "demopad"}}}
        adopted = sbr.adopt_tags(demo_tags)
        calls.clear()
        replayed = sbr.loadvm("x-A", paused=True)
        replug = [a for c, a in calls if c == "device_add"]
        other_port = str(_err(sbr.play_recording, [], port=2))
        put(0x730000 + 0x18, "<d", 7.25)

        def tag_ram(va: int, n: int) -> bytes:   # the demo recorder's fake guest RAM, above
            base = va & ~0xFFF
            return bytes(regions[base][va - base:va - base + n]) if base in regions else bytes(n)

        class TagBox:   # note_tag's reads: halted at a player tick, its entity, the level; savevm as a sandbox's
            st = {"tag_discs": {}, "tag_usb": {}, "record_port": 1}
            g = type("G", (), {"regs": staticmethod(lambda: {"eip": PLAYER_TICK, "esp": 0x760000})})()
            read, read_u32 = staticmethod(tag_ram), staticmethod(lambda va: struct.unpack("<I", tag_ram(va, 4))[0])

            def savevm(self, tag):
                self.st["tag_discs"][tag], self.st["tag_usb"][tag] = "b-abc.iso", {"1.3": "USB Hub"}
        put(0x760004, "<I", 0x730000)
        meta_p = tmp / "demo-meta.json"
        xd.note_tag(TagBox(), "x-B", meta_p)
        noted = json.loads(meta_p.read_text(encoding="utf-8"))["tags"]["x-B"]
        check("port-1 replay (AZ-439): the keyboard pad bound on port 1 and nothing on port 2 (an owner demo's pads "
              "beside it); a replay on the demo's drive adopts its tags and plugs the hubs the state holds that it "
              "lacks (port 2's neutral, the demo hub reading player 1) before the load, on the tag's own disc; a "
              "recording of another port is refused; note_tag keeps a tag's disc, pads and recorded port",
              {k: v for k, v in p1.items() if re.fullmatch(r"port\d", k)} == {"port1": "keyboard"}
              and p1_demo.get("port1") == "keyboard" and p1_demo.get("port3") == guid and "port2" not in p1_demo
              and isinstance(_err(Sandbox, "h", pad_port=5), SystemExit)
              and isinstance(_err(scratch_toml, two, str(w), 1, 1), SystemExit)
              and adopted == ["x-A"] and replayed["disc"] == "b-abc.iso"
              and replug == [{"driver": "usb-hub", "port": "1.1", "ports": 3, "id": "demohub"},
                             {"driver": "usb-xbox-gamepad", "index": 0, "port": "1.1.1", "id": "demopad"},
                             {"driver": "usb-hub", "port": "1.4", "ports": 3, "id": "plughub14"},
                             {"driver": "usb-xbox-gamepad", "index": 1, "port": "1.4.1", "id": "plugpad14"}]
              and "AZ-439" in other_port
              and noted == {"clk": 7.25, "lvl": "levels/life", "disc": "b-abc.iso", "usb": {"1.3": "USB Hub"},
                            "record_port": 1}, f"{p1} {p1_demo} {replug} {noted}")
        # AZ-510: a section's +N lines go as @<base+N>, base the frame the paused load left (a +N counts from the
        # frame xemu reads it at), other lines as they are; the advance runs through the last line's frame
        piped, stepped_rec = [], []

        def rec_qmp(cmd: str, **args) -> dict:   # the paused load left frame 40
            if cmd == "xemu-frame-advance":
                stepped_rec.append(args)
            return {"return": {"frame": 40, "running": False}}
        real_keys, sbr.qmp = send_keys, rec_qmp
        globals()["send_keys"] = lambda fifo, line: piped.append(line)
        try:
            sbr.play_recording(["+0 axis lx 0.500000", "clear", "+3 down 232", "+12 up 232"], port=1)
        finally:
            globals()["send_keys"], sbr.qmp = real_keys, fake_qmp
        check("play_recording (AZ-510): each +N line written as @<base+N>, base the paused load's frame, other lines "
              "as recorded; the advance runs through the last line's frame",
              piped == ["@40 axis lx 0.500000", "clear", "@43 down 232", "@52 up 232"]
              and stepped_rec == [{"frames": 13}], f"{piped} {stepped_rec}")
        # AZ-539: a section past PIPE_WINDOW bytes goes a window at a time (a paused xemu reads no pipe line): each
        # window's lines, then an advance to a multiple of every from base before the next window's first line
        writes, ends, at = [], [], [40]

        def win_qmp(cmd: str, **args) -> dict:
            if cmd == "xemu-frame-advance":
                at[0] += args["frames"]
                ends.append((at[0], len(writes), args.get("trace-every")))
                return {"return": {"frame": at[0], "running": False, "trace": [{"frame": at[0]}]}}
            return {"return": {"frame": at[0], "running": False}}
        long = [f"+{k // 4} axis lx 0.{k:06d}" for k in range(4000)]   # 4 lines a frame for 1,000 frames
        sbr.qmp = win_qmp
        globals()["send_keys"] = lambda fifo, line: writes.append((at[0], line))
        try:
            got = sbr.play_recording(long, port=1, trace=[{"address": 0, "size": 4}], every=30)
        finally:
            globals()["send_keys"], sbr.qmp = real_keys, fake_qmp
        sizes = [sum(len(ln) + 1 for _, ln in writes[a:b]) for a, b in zip([0] + [e[1] for e in ends], [e[1] for e in ends])]
        check("play_recording (AZ-539): a long section is written a window at a time, each line before its frame "
              "and each window under PIPE_WINDOW bytes, the advances ending on multiples of every from base but the "
              "last, through the last line's frame, their traces joined",
              [ln for _, ln in writes] == [f"@{40 + k // 4} axis lx 0.{k:06d}" for k in range(4000)]
              and all(f <= int(ln[1:].split(" ", 1)[0]) for f, ln in writes)
              and all(f < int(ln[1:].split(" ", 1)[0]) for f, ln in writes if f > 40)
              and len(ends) > 2 and all((e - 40) % 30 == 0 for e, _, _ in ends[:-1]) and ends[-1][0] == 1040
              and all(s <= PIPE_WINDOW for s in sizes) and all(ev == 30 for _, _, ev in ends)
              and got["windows"] == len(ends) and [t["frame"] for t in got["trace"]] == [e for e, _, _ in ends],
              f"{len(writes)} {ends[:4]} {sizes[:4]}")
        # Step X.61 (v0.16.1): on a build with xemu-input-queue a section goes in one call (the same @<base+N> lines),
        # then one advance, nothing through the pipe; lines past the frames replayed aren't sent; a call that didn't
        # take every line raises
        queued, q_adv, skip = [], [], [0]

        def queue_qmp(cmd: str, **args) -> dict:
            if cmd == INPUT_QUEUE:
                queued.append(args["lines"])
                return {"return": {"accepted": len(args["lines"]) - skip[0], "skipped": skip[0], "queued": 4,
                                   "frame": 40}}
            if cmd == "xemu-frame-advance":
                q_adv.append(args)
            return {"return": {"frame": 40, "running": False}}
        sbr.qmp, sbr.st["input_queue"], piped = queue_qmp, True, []
        globals()["send_keys"] = lambda fifo, line: piped.append(line)
        try:
            rec = ["+0 axis lx 0.500000", "clear", "+3 down 232", "+12 up 232"]
            whole = sbr.play_recording(rec, port=1)
            cut = sbr.play_recording(rec, 5, port=1)
            skip[0] = 1
            refused_q = _err(sbr.play_recording, rec, port=1)
        finally:
            globals()["send_keys"], sbr.qmp = real_keys, fake_qmp
            sbr.st.pop("input_queue")
        check("play_recording (Step X.61): xemu-input-queue takes a section in one call (its @<base+N> lines) and one "
              "advance follows, no pipe line written; lines past the replayed frames aren't sent; a call that skipped "
              "a line raises",
              queued[0] == ["@40 axis lx 0.500000", "clear", "@43 down 232", "@52 up 232"] and piped == []
              and q_adv[:2] == [{"frames": 13}, {"frames": 5}] and whole["queued"] == 4 and cut["queued"] == 3
              and queued[1] == queued[0][:3] and isinstance(refused_q, SystemExit) and "1 skipped" in str(refused_q),
              f"{queued} {q_adv} {refused_q}")
        # Step X.14: a fork build is waited on by its readiness lines, not the clock (READY before the first
        # loadvm, LOADED after each), its lost-GPU exit is a crash the supervisor retries, and QMP takes its
        # screenshots and steps its frames
        runlog, loads = w / "run.log", []
        runlog.write_text("xemu_version: 0.14-8-gbb5ce7e3ec\n", encoding="utf-8")
        sb.st.update(ready_line=True, launched_at=time.time() - 1, gdb_ready_at=time.time() - 1)   # a new launch
        sb.st.pop("ready_at")
        READY_S, LOADED_S = 0.3, 0.3
        no_ready = type(_err(sb.await_ready)).__name__
        runlog.write_text(f"xemu_version: 0.14-8-gbb5ce7e3ec\n{READY}\n", encoding="utf-8")

        def loading_qmp(cmd: str, **args) -> dict:   # loadvm prints LOADED (or, for a refused tag, an error)
            if args.get("command-line", "").startswith("loadvm"):
                loads.append(args["command-line"])
                if "refused" in args["command-line"]:
                    return {"return": "Unknown section ... usb-hub"}
                if "silent" not in args["command-line"]:
                    with runlog.open("a", encoding="utf-8") as f:
                        f.write(f"{LOADED}\n")
            if cmd == "screendump":
                Path(args["filename"]).write_bytes(b"\x89PNG\r\n")
            if cmd.startswith(("query-xemu", "xemu-")):
                calls.append((cmd, args))
                return {"return": {"frame": 7, "running": False}}
            return fake_qmp(cmd, **args)
        sb.qmp = loading_qmp
        sb.st["saved_tags"] += ["s-silent", "s-refused"]
        t0 = time.monotonic()
        ok_load = sb.loadvm("vanilla-flat", halt_at_tick=False)["loadvm"]
        errs = [str(_err(sb.loadvm, t, halt_at_tick=False)) for t in ("s-silent", "s-refused")]
        lines_cmds = [c for c, _ in calls]   # Step X.33: a build without query-xemu-status (v0.14-36) is never asked
        check("readiness (fork build): the first loadvm waits for 'xemu: ready' (TimeoutError without it), each "
              "loadvm for 'xemu: state loaded'; a refused one fails at once, never retried at the old 25 s mark",
              no_ready == "TimeoutError" and ok_load == "ok" and LOADED in errs[0] and "usb-hub" in errs[1]
              and len(loads) == 3 and time.monotonic() - t0 < 5 and sb.st["ready_launch_s"] >= 1, f"{no_ready} {errs}")
        shot = sb.screenshot("frame-a")
        sb.st["headless"] = "null"
        no_shot = refused(sb.screenshot, "frame-b")
        sb.st.pop("headless")
        dumps = [a for c, a in calls if c == "screendump"]
        stepped = (sb.frame(), sb.frame_advance(3), [a for c, a in calls if c == "xemu-frame-advance"])
        calls.clear()
        check("screenshots by QMP screendump (a PNG xemu writes in W, moved to the out folder), refused under the "
              "null renderer (it draws nothing); frame stepping",
              shot == w / "frame-a.png" and shot.exists() and not list(w.glob("screendump.*")) and no_shot
              and len(dumps) == 1
              and dumps[0]["format"] == "png" and Path(dumps[0]["filename"]).parent == w
              and stepped == ({"frame": 7, "running": False},) * 2 + ([{"frames": 3}],), f"{dumps} {stepped}")
        # Step X.32 (PROMPT-8 C, AZ-452): a build that dates its pictures is asked just before each screendump; a
        # picture with no flip since the last load is the loaded state's own frame (stale: an event), one after is not
        ages = iter([{"frame": 50, "loads": 2, "flips": 9, "flip-frame": 40, "flip-loads": 1},
                     {"frame": 53, "loads": 2, "flips": 11, "flip-frame": 52, "flip-loads": 2}])
        order: list = []

        def dated_qmp(cmd: str, **args) -> dict:
            order.append(cmd)
            return {"return": next(ages)} if cmd == DISPLAY_QUERY else loading_qmp(cmd, **args)
        sb.qmp, sb.st["display_query"], n_events = dated_qmp, True, len(sb.st["events"])
        try:
            sb.screenshot("frame-c")
            first = dict(sb.last_picture)
            sb.screenshot("frame-d2")
            second = dict(sb.last_picture)
        finally:
            sb.qmp = loading_qmp
            sb.st.pop("display_query")
        said = sb.st["events"][n_events:]
        check("picture age (v0.15, AZ-452): query-xemu-display just before each screendump; no flip since the last "
              "load marks the picture stale with an event, a flip after it doesn't",
              first["stale"] and first["name"] == "frame-c" and not second["stale"]
              and [c for c in order if c in (DISPLAY_QUERY, "screendump")] == [DISPLAY_QUERY, "screendump"] * 2
              and len(said) == 1 and "no flip since the last load (flip-loads 1, loads 2)" in said[0],
              f"{first} {second} {order} {said}")
        # Step X.61 (v0.16.1, AZ-668): picture-stale dates a picture where the query has it (a checkpoint restore,
        # which flip-loads missed): a paused deterministic sandbox advances a vblank at a time until it is fresh, at
        # most PICTURE_STALE_ADVANCE, and raises if it stays stale; a null_ram one first draws RENDER_FLIPS frames by
        # xemu-render-next (fewer in its cap raises), the RAM staying null's
        stale_seq, steps61, render = [], [], [{"frame": 9, "running": False, "render-flips": 2}]

        def stale_qmp(cmd: str, **args) -> dict:
            if cmd == DISPLAY_QUERY:
                return {"return": {"frame": 50, "loads": 3, "flips": 9, "flip-loads": 3,
                                   "picture-stale": stale_seq.pop(0)}}   # flip-loads says fresh: a restore
            if cmd in ("xemu-frame-advance", "xemu-render-next"):
                steps61.append((cmd, args))
                if cmd == "xemu-render-next":
                    return {"return": render[0]}
            if cmd == "query-status":
                return {"return": {"status": "paused"}}
            return loading_qmp(cmd, **args)
        sb.qmp, sb.st["display_query"], sb.st["deterministic"] = stale_qmp, True, True
        try:
            stale_seq[:] = [True, True, False]
            sb.screenshot("frame-s1")
            fresh_pic = dict(sb.last_picture)
            stale_seq[:] = [True] * (PICTURE_STALE_ADVANCE + 1)
            stuck_pic = _err(sb.screenshot, "frame-s2")
            n_adv = len(steps61)
            steps61.clear()
            sb.st["null_ram"], stale_seq[:] = True, [False]
            sb.screenshot("frame-s3")
            drawn_pic = dict(sb.last_picture)
            render[0] = {"frame": 127, "running": False, "render-flips": 1}
            stale_seq[:] = [False]
            undrawn = _err(sb.screenshot, "frame-s4")
            sb.st.pop("deterministic"), sb.st.pop("null_ram")   # real time, the VM paused (a halt after a load)
            rn_first = steps61[0]
            steps61.clear()
            stale_seq[:] = [True, False]
            sb.screenshot("frame-s5")
            rt_pic, rt_steps = dict(sb.last_picture), list(steps61)
        finally:
            sb.qmp = loading_qmp
            for k in ("display_query", "deterministic", "null_ram"):
                sb.st.pop(k, None)
        check("picture age (Step X.61, AZ-668): picture-stale dates the picture; a paused deterministic sandbox "
              "advances a vblank at a time until it is fresh and says how many, raises if it stays stale past "
              "PICTURE_STALE_ADVANCE; a null_ram sandbox draws RENDER_FLIPS frames first, and raises on fewer; a "
              "paused real-time one is advanced too, not polled",
              fresh_pic["advanced"] == 2 and fresh_pic["stale"] is False and isinstance(stuck_pic, SystemExit)
              and "still predates the last load" in str(stuck_pic) and n_adv == 2 + PICTURE_STALE_ADVANCE
              and rn_first == ("xemu-render-next", {"flips": RENDER_FLIPS}) and drawn_pic["render_flips"] == 2
              and drawn_pic["render_frames"] == 2 and drawn_pic["advanced"] == 0
              and isinstance(undrawn, SystemExit) and "drew 1 of 2 frames in its 120 vblanks" in str(undrawn)
              and rt_pic["advanced"] == 1 and rt_pic["stale"] is False
              and rt_steps == [("xemu-frame-advance", {"frames": 1})],
              f"{fresh_pic} | {stuck_pic} | {n_adv} | {drawn_pic} | {undrawn} | {rt_pic} {rt_steps}")
        # PROMPT-8 D (Step X.37): a later build's advance names a VM stop it didn't make ("stopped"; its frame where
        # it stopped): an event with the frames that ran (at most, when the VM ran before it); a breakpoint's stop
        # returns, any other raises. An advance with no reply is sampled first (AZ-451), before anything touches it
        replies = iter([{"frame": 103, "running": False}, {"frame": 101, "running": False, "stopped": "paused"},
                        {"frame": 102, "running": False, "debug-stop": True, "stopped": "debug"},
                        {"frame": 100, "running": False, "stopped": "shutdown"}, TimeoutError("timed out"),
                        {"frame": 106, "running": False, "stopped": "paused"}])
        touched, running = [], [False]   # every QMP call and probe, in order; whether the VM runs at the start

        def stop_qmp(cmd: str, **args) -> dict:   # the advance starts at frame 100
            touched.append(cmd)
            if cmd == "query-xemu-frame":
                return {"return": {"frame": 100, "running": running[0]}}
            if cmd == "xemu-frame-advance":
                if isinstance(r := next(replies), BaseException):
                    raise r
                return {"return": r}
            return fake_qmp(cmd, **args)
        real_probe, real_alive = hang_probe, sb.__dict__.get("alive")
        hang_probe = lambda pid, dest: touched.append(f"probe {pid}") or dest / "hang-4242.sample.txt"  # noqa: E731
        sb.qmp, pid_was, n_events, sb.alive = stop_qmp, sb.st.get("pid"), len(sb.st["events"]), (lambda: True)
        sb.st["pid"] = 4242
        try:
            advanced = [sb.frame_advance(3), _err(sb.frame_advance, 3), sb.frame_advance(3),
                        _err(sb.frame_advance, 3), _err(sb.frame_advance, 3)]
            after_hang = touched[touched.index("xemu-frame-advance", len(touched) - 3):]
            running[0] = True
            advanced.append(_err(sb.frame_advance, 3))
        finally:
            hang_probe = real_probe
            sb.qmp, sb.st["pid"] = loading_qmp, pid_was
            if real_alive is None:
                del sb.alive
            else:
                sb.alive = real_alive
        said, probes = sb.st["events"][n_events:], sb.st.pop("hang_probes", None)
        plain, paused, debug, shutdown, hung, early = advanced
        ran: list = []   # the real probe: sample first, then ps and lsof, all into dest
        probe = hang_probe(4242, tmp, run=lambda argv, **_: ran.append(argv[0]) or subprocess.CompletedProcess(argv, 0,
                                                                                                              "", ""))
        probe_txt = sorted(p_.name for p_ in tmp.glob("hang-4242-*"))
        for p_ in tmp.glob("hang-4242-*"):
            p_.unlink()
        hb = Sandbox("hang")   # down keeps a W holding a hung advance's sample
        hb.w, hb._owner = tmp / "azx-st.hang", False
        hb.w.mkdir()
        hb.st = {"W": str(hb.w), "hang_probes": [str(hb.w / "hang-1.sample.txt")], "events": []}
        hb._quit, hb._baselines = (lambda: {"quit": "qmp"}), (lambda: {"sources_equal": True, "kept": False})
        hang_kept = hb.down().get("kept") is True and hb.w.exists()
        shutil.rmtree(hb.w, ignore_errors=True)
        check("frame_advance (PROMPT-8 D, Step X.37): a reply with no 'stopped' is today's; a stop the advance "
              "didn't make is an event with the frames that ran (its frame less the start's; at most that when the VM "
              "ran at the start): a breakpoint's returns them, a gdbstub attach's (paused) or SIGTERM's (shutdown) "
              "raises AdvanceStopped naming the cause; an advance with no reply is sampled before any later QMP call "
              "(sample, then ps and lsof, into W, which down keeps) and its TimeoutError names the sample",
              plain == {"frame": 103, "running": False} and isinstance(paused, AdvanceStopped)
              and paused.reply["ran"] == 1 and "paused: a gdbstub client attached" in str(paused)
              and debug == {"frame": 102, "running": False, "debug-stop": True, "stopped": "debug", "ran": 2}
              and isinstance(shutdown, AdvanceStopped) and shutdown.reply["ran"] == 0 and "SIGTERM" in str(shutdown)
              and isinstance(hung, TimeoutError) and f"sampled pid 4242 into {w / 'hang-4242.sample.txt'}" in str(hung)
              and after_hang == ["xemu-frame-advance", "probe 4242"]
              and probes == [str(w / "hang-4242.sample.txt")]
              and isinstance(early, AdvanceStopped) and early.reply.get("ran_at_most") == 6 and "ran" not in early.reply
              and ran == ["sample", "ps", "lsof"] and probe.name.endswith(".sample.txt")
              and len(probe_txt) == 1 and probe_txt[0].endswith(".txt") and hang_kept
              and [e.split(" ", 1)[1] for e in said] == [
                  "xemu-frame-advance 3: the VM stopped (paused: a gdbstub client attached, sent ^C or a stray byte) "
                  "after 1 frame(s), at frame 101",
                  "xemu-frame-advance 3: the VM stopped (debug: a gdbstub breakpoint) after 2 frame(s), at frame 102",
                  "xemu-frame-advance 3: the VM stopped (shutdown: SIGTERM: xemu exits) after 0 frame(s), at frame "
                  "100", f"hung advance: sampled pid 4242 into {w / 'hang-4242.sample.txt'} (W is kept)",
                  "xemu-frame-advance 3: the VM stopped (paused: a gdbstub client attached, sent ^C or a stray byte) "
                  "after at most 6 frame(s) (the VM ran before the advance), at frame 106"],
              f"{[type(a).__name__ for a in advanced]} {after_hang} {probes} {ran} {probe_txt} {hang_kept} {said} "
              f"{str(hung)[:200]}")
        # Step X.94 (timeout-ms, 0.16.4-3-g95e7ffc7ec): on a build with TIMEOUT_MARK every advance and run asks
        # advance_bound_s(its frames), the caller's timeout_s or (False) none; a reply xemu paused at it raises
        # AdvanceTimedOut with the frames that ran, kept for down's report, and a deterministic sandbox runs nothing
        # from that host-time point until a checkpoint restore or a load; a boot try retries it ("timed_out")
        to_sent: list = []
        to_replies = iter([{"frame": 105, "running": False}, {"frame": 104, "running": False, "timed-out": True},
                           {"reason": "timeout", "frame": 120}])

        def to_qmp(cmd: str, **a) -> dict:
            to_sent.append((cmd, a.get("timeout-ms")))
            if cmd == "query-xemu-frame":
                return {"return": {"frame": 100, "running": False}}
            if cmd in ("xemu-frame-advance", XEMU_RUN):
                return {"return": next(to_replies)}
            if cmd == "query-block":
                return {"return": [{"device": CD, "inserted": {"file": f"{w}/dvd.iso"}}]}
            return {"return": {"loads": 0} if cmd == XEMU_STATUS else {}}
        tb = Sandbox("to")
        tb.w, tb._owner, tb.qmp = w, False, to_qmp
        tb.st = {"W": str(w), "pid": 7, "deterministic": True, "timeout_ms": True, "checkpoints": True,
                 "xemu_status": True, "events": [], "checkpoints_held": {"pid": 7, "names": {"c": {"disc": "dvd.iso"}}}}
        to_plain = tb.frame_advance(5)
        to_timed = _err(tb.frame_advance, 600, timeout_s=0.5)
        to_refused = [_err(tb.frame_advance, 1), _err(tb._run, 10)]
        to_runs = [c for c, _ in to_sent if c in ("xemu-frame-advance", XEMU_RUN)]
        tb.checkpoint_restore("c")
        to_run = _err(tb._run, 30)
        nb = Sandbox("to2")
        nb.st = {"pid": 7}   # a build without timeout-ms
        check("timeout-ms (Step X.94): every advance and run asks advance_bound_s or the caller's bound; one xemu "
              "paused at it raises AdvanceTimedOut with the frames that ran and is kept for down; a deterministic "
              "sandbox refuses to run on until a checkpoint restore or a load; a boot try retries it",
              to_plain == {"frame": 105, "running": False}
              and [a for c, a in to_sent if c == "xemu-frame-advance"] == [125000, 500]
              and isinstance(to_timed, AdvanceTimedOut) and to_timed.reply["ran"] == 4
              and "timed out after 0.5 s (timeout-ms), 4 frame(s) ran, the VM paused at frame 104" in str(to_timed)
              and all(isinstance(e, SystemExit) and not isinstance(e, AdvanceTimedOut) and "refused" in str(e)
                      and "restore a checkpoint or loadvm first" in str(e) for e in to_refused)
              and to_runs == ["xemu-frame-advance", "xemu-frame-advance"]
              and isinstance(to_run, AdvanceTimedOut) and (XEMU_RUN, 150000) in to_sent and to_run.reply["ran"] == 20
              and [(x["cmd"], x["ran"]) for x in tb.st["timeouts"]] == [("xemu-frame-advance", 4), (XEMU_RUN, 20)]
              and tb.failure_class(to_timed) == "timed_out" and nb._bound(5) == {} and tb._bound(5, False) == {}
              and sum("timed out after" in e for e in tb.st["events"]) == 2,
              f"{to_plain} {to_sent} {to_timed!r} {to_refused} {to_run!r} {tb.st.get('timeouts')}")
        # Step X.96: where boots run on frames and xemu bounds a run (timeout-ms), wait_bp is one xemu-run to the PCs
        # within the timeout's vblanks: halted on one of them it steps off first, the caller's gdbstub client is
        # attached again (the same object), a miss returns None; elsewhere the breakpoint and the host's clock
        class WaitG:   # a gdbstub client: where the guest stands, the packets, its reconnects
            def __init__(self, eip):
                self.eip, self.sent, self.reconnects = eip, [], 0

            def regs(self):
                return {"eip": self.eip}

            def cmd(self, p):
                self.sent.append(p)
                return b"T05"

            def reconnect(self):
                self.reconnects += 1
        wb_runs, wb_out = [], []
        for eip, reply in ((PLAYER_TICK, {"reason": "hit", "pc": PLAYER_TICK, "frame": 9}),
                           (0x11000, {"reason": "budget", "frame": 129})):
            wb = Sandbox("wb")
            wb.st = {"deterministic": True, "xemu_run": True, "debug_advance": True, "timeout_ms": True}
            wg = WaitG(eip)
            wb._g, wb._halted = wg, True
            wb._run = lambda frames, stops=None, lines=None, r=reply: (wb_runs.append((frames, stops)), r)[1]
            wb_out.append((wb.wait_bp([PLAYER_TICK, LOAD_LEVEL], 2.0), wg.sent, wg.reconnects, wb._g is wg,
                           wb._halted))
        old_wb = Sandbox("wb")
        old_wb.st = {"deterministic": True, "xemu_run": True, "debug_advance": True}   # no timeout-ms
        check("wait_bp on frames (Step X.96): one xemu-run to the PCs within the timeout's vblanks, stepping off a PC "
              "it stands on, the caller's gdbstub client attached again and halted; a miss is None; a build "
              "without timeout-ms keeps the breakpoint and the host's clock",
              wb_runs == [(120, [{"pc": PLAYER_TICK}, {"pc": LOAD_LEVEL}])] * 2
              and wb_out == [(PLAYER_TICK, ["s"], 1, True, True), (None, [], 1, True, True)]
              and not old_wb._frame_waits(), f"{wb_runs} {wb_out}")
        with runlog.open("a", encoding="utf-8") as f:
            f.write(f"{DEVICE_LOST}\n")
        check("a headless fork build's exit on a lost GPU device is a crash the supervisor retries, its cause named",
              sb.failure_class(EOFError("the gdbstub closed the connection")) == "xemu_died"
              and exit_cause(w) == DEVICE_LOST)
        # Step X.33 (PROMPT-7 N): the QMP client keeps the events that arrive on its connection (a bounded buffer
        # and wait_event), and a build whose QMP offers query-xemu-status is waited on over QMP, not its run log
        import threading
        qsock = w / "qmp.sock"

        def serve_qmp(answer) -> tuple[socket.socket, threading.Event]:   # a QMP socket in W, one client at a time
            srv, stop = socket.socket(socket.AF_UNIX), threading.Event()
            srv.bind(str(qsock))
            srv.listen(4)
            srv.settimeout(0.05)

            def run() -> None:
                while not stop.is_set():
                    try:
                        c, _ = srv.accept()
                    except TimeoutError:
                        continue
                    except OSError:
                        return
                    with c:
                        c.settimeout(5.0)
                        try:
                            c.sendall(b'{"QMP": {"version": {}, "capabilities": []}}\n')
                            for line in c.makefile("rb"):
                                answer(json.loads(line)["execute"], c.sendall)
                        except OSError:
                            pass
            threading.Thread(target=run, daemon=True).start()
            return srv, stop

        def ev(name: str, **data) -> bytes:
            return json.dumps({"event": name, "data": data,
                               "timestamp": {"seconds": 1, "microseconds": 0}}).encode() + b"\n"

        def status(ready: bool, after: bytes = b"", before: bytes = b""):
            def answer(cmd: str, send) -> None:
                if cmd == "qmp_capabilities":
                    send(b'{"return": {}}\n')
                elif cmd == XEMU_STATUS:
                    send(before + json.dumps({"return": {"ready": ready, "loads": 0}}).encode() + b"\n")
                    if after:
                        time.sleep(0.1)
                        send(after[:9])   # an event split across reads
                        time.sleep(0.05)
                        send(after[9:])
            return answer
        srv, stop = serve_qmp(status(False, b"".join(ev("X_TICK", n=i) for i in range(QMP_EVENTS_KEPT))
                                     + ev("XEMU_READY"), ev("XEMU_CPUID_FAULT", count=1)))
        try:
            q = QMP(qsock, timeout=2.0)
            first = q.execute(XEMU_STATUS)["return"]["ready"]
            kept = [e["event"] for e in q.events]
            got = q.wait_event("XEMU_READY", 2.0)
            n_kept, oldest = len(q.events), q.events[0]["data"]
            none = q.wait_event("XEMU_DEVICE_LOST", 0.05)
            again = "return" in q.execute("qmp_capabilities")
            tick = q.wait_event("X_TICK", 0.0, lambda e: e["data"]["n"] == 5)
            left = len(q.events)
            q.s.close()
        finally:
            stop.set()
            srv.close()
            qsock.unlink()
        check("QMP (Step X.33, PROMPT-7 N): an event before a reply is kept, not dropped; wait_event returns the next "
              "one named (split across reads), keeping the others, the last QMP_EVENTS_KEPT; a wait that times out "
              "leaves the connection usable; a kept event is taken at once",
              first is False and kept == ["XEMU_CPUID_FAULT"] and got and got["event"] == "XEMU_READY"
              and n_kept == QMP_EVENTS_KEPT and oldest == {"n": 0} and none is None and again
              and tick and tick["data"] == {"n": 5} and left == QMP_EVENTS_KEPT - 1, f"{kept} {n_kept} {left}")
        # Step X.32b: a deterministic sandbox keeps one QMP connection (the fork: 0.13 against 0.34 ms a command): its
        # commands share it; one xemu closed after a reply (its SHUTDOWN event sent first, as a quit or SIGTERM from
        # another process sends it) is found before the next command and opened again; one
        # that breaks mid-command is dropped, the error raised (never sent twice), and the next command reconnects;
        # a real-time or recorded sandbox (the demo recorder and replug watcher share W's one QMP) connects per command
        conns = []

        def held(cmd: str, send) -> None:
            if cmd == "qmp_capabilities":
                conns.append(cmd)
            if cmd == "x-break":
                raise OSError("xemu went away mid-command")
            send(b'{"return": {}}\n')
            if cmd == "x-bye":
                time.sleep(0.05)   # the reply read alone; then the quit's event, then the close
                send(ev("SHUTDOWN", guest=False, reason="host-signal"))
                raise OSError("xemu closed it after the reply")
        srv, stop = serve_qmp(held)
        try:
            kb = Sandbox("st")
            kb.w, kb.st = w, {"deterministic": True}
            shared = [kb.qmp("query-status") for _ in range(3)]
            twin = Sandbox("st")   # another Sandbox of the same W in this process (a driver's attach)
            twin.w, twin.st = w, {"deterministic": True}
            shared.append(twin.qmp("query-status"))
            n_shared = len(conns)
            kb.qmp("x-bye")
            time.sleep(0.3)   # the event and the close arrive before the next command
            after_bye = (kb.qmp("query-status"), len(conns))
            broke = _err(kb.qmp, "x-break")
            after_break = (kb.qmp("query-status"), len(conns))
            try:   # a signal's exit (the sitting's Teardown) or ^C while a reply is still on its way
                with kb._qmp_conn() as q:
                    q.s.sendall(b'{"execute": "query-status"}\n')
                    raise KeyboardInterrupt
            except KeyboardInterrupt:
                pass
            after_signal = (kb.qmp("query-status"), len(conns))
            kb._close_qmp()
            for st in ({"deterministic": False}, {"deterministic": True, "record_port": 2},
                       {"deterministic": True, "owner_pad": 2}):
                kb.st = st
                kb.qmp("query-status")
            per_call = len(conns) - after_signal[1]
        finally:
            stop.set()
            srv.close()
            qsock.unlink()
        check("QMP (Step X.32b): a deterministic sandbox's commands share one connection, whichever of its Sandbox "
              "objects sends them; one xemu closed (an event waiting before its end) is opened again before the next "
              "command; one broken mid-command raises and the next reconnects, as after a signal's exit "
              "mid-reply (whose reply would answer the next command); a real-time, recorded or owner-demo sandbox "
              "connects per command",
              shared == [{"return": {}}] * 4 and n_shared == 1 and after_bye == ({"return": {}}, 2)
              and isinstance(broke, (OSError, EOFError)) and after_break == ({"return": {}}, 3)
              and after_signal == ({"return": {}}, 4) and per_call == 3,
              f"{n_shared} {after_bye} {broke!r} {after_break} {after_signal} {per_call}")
        # PROMPT-8 E (Step X.37, AZ-464): a QMP connect that fails says which case it is: the file gone (removed), or
        # there and refusing (a listener with a listen backlog of 1 that one client already holds); either is the
        # OSError it was
        removed = _err(QMP, qsock, 0.5)
        lsn, holder = socket.socket(socket.AF_UNIX), socket.socket(socket.AF_UNIX)
        try:
            lsn.bind(str(qsock))
            lsn.listen(1)
            holder.connect(str(qsock))   # the one client the chardev serves (it never greets here)
            held = _err(QMP, qsock, 0.5)
        finally:
            holder.close()
            lsn.close()
            qsock.unlink()
        lsn = socket.socket(socket.AF_UNIX)
        try:
            lsn.bind(str(qsock))
            lsn.listen(1)   # a listener that is busy elsewhere: the next client waits in its backlog, ungreeted
            ungreeted = _err(QMP, qsock, 0.5)
        finally:
            lsn.close()
            qsock.unlink()
        check("QMP connect (PROMPT-8 E, Step X.37, AZ-464): a socket file that is gone says removed (ENOENT); one that "
              "is there and refuses says held by another client or taken over (ECONNREFUSED); one that connects and "
              "never greets says held; each stays its OSError",
              isinstance(removed, FileNotFoundError) and f"QMP socket {qsock}: removed (ENOENT)" in str(removed)
              and isinstance(held, ConnectionRefusedError)
              and f"QMP socket {qsock}: present, connection refused (ECONNREFUSED): held by another client or taken "
                  "over" in str(held) and isinstance(ungreeted, TimeoutError)
              and f"QMP socket {qsock}: connected, no greeting in 0.5 s: held by another client" in str(ungreeted),
              f"{removed} | {held} | {ungreeted}")
        # Step X.56's sitting: a per-command connect refused (nothing sent) is tried again until the listener takes
        # it, the refusals counted; one refused past QMP_REFUSED_S is raised as before
        import threading   # (the selftest imports it above too: a local name)
        lsn = socket.socket(socket.AF_UNIX)
        lsn.bind(str(qsock))   # the file there, nothing listening yet: ECONNREFUSED

        def listen_late() -> None:
            time.sleep(0.3)
            lsn.listen(1)
            c, _ = lsn.accept()
            with c:
                c.sendall(b'{"QMP": {"version": {}, "capabilities": []}}\n')
                for _line in c.makefile("rb"):
                    c.sendall(b'{"return": {}}\n')
        late = threading.Thread(target=listen_late, daemon=True)
        late.start()
        try:
            dialed, refusals = qmp_dial(qsock, 2.0)
            dialed_ok = dialed.execute("query-status") == {"return": {}}
            dialed.s.close()
        finally:
            late.join(3.0)
            lsn.close()
            qsock.unlink()
        lsn = socket.socket(socket.AF_UNIX)
        real_refused, QMP_REFUSED_S = QMP_REFUSED_S, 0.2
        try:
            lsn.bind(str(qsock))
            t_ref = time.monotonic()
            gave_up = (type(_err(qmp_dial, qsock, 0.5)).__name__, time.monotonic() - t_ref)
        finally:
            QMP_REFUSED_S = real_refused
            lsn.close()
            qsock.unlink()
        check("QMP dial (Step X.56's sitting): a per-command connect refused (nothing sent) is tried again until the "
              "listener takes it, the refusals counted; one refused past QMP_REFUSED_S raises as before",
              dialed_ok and refusals >= 2 and gave_up[0] == "ConnectionRefusedError" and gave_up[1] < 1.0,
              f"{dialed_ok} {refusals} {gave_up}")
        # Step X.61 (v0.16.1): every command carries an id and a late reply to another is skipped (its events kept);
        # the watch socket is a monitor of its own, so W's held connection doesn't refuse it; with a listen backlog
        # (XEMU_SOCKET_BACKLOG) a refused connect means the listener is gone (raised at once, said so) and an
        # ungreeted one is queued behind a held client

        def serve_at(path: Path, answer, greet_s: float = 0.0) -> tuple[socket.socket, threading.Event]:
            srv, done = socket.socket(socket.AF_UNIX), threading.Event()
            srv.bind(str(path))
            srv.listen(4)
            srv.settimeout(0.05)

            def client(c: socket.socket) -> None:   # each client its own thread (a stuck one holds no other)
                with c:   # answer(request, send); greet_s: a greeting that comes late (a client queued before)
                    c.settimeout(5.0)
                    time.sleep(greet_s)
                    with contextlib.suppress(OSError):
                        c.sendall(b'{"QMP": {"version": {}, "capabilities": []}}\n')
                        for line in c.makefile("rb"):
                            answer(json.loads(line), c.sendall)

            def run() -> None:
                while not done.is_set():
                    try:
                        c, _ = srv.accept()
                    except TimeoutError:
                        continue
                    except OSError:
                        return
                    threading.Thread(target=client, args=(c,), daemon=True).start()
            threading.Thread(target=run, daemon=True).start()
            return srv, done

        def stale_first(req: dict, send) -> None:   # a late reply to the request before, an event, then its own
            if req["execute"] == "x-late":
                send(json.dumps({"return": "late", "id": req["id"] - 1}).encode() + b"\n" + ev("X_TICK", n=1))
            send(json.dumps({"return": req["execute"], "id": req["id"]}).encode() + b"\n")
        srv, done = serve_at(qsock, stale_first)
        wsock = w / WATCH_SOCK
        wsrv, wdone = serve_at(wsock, lambda req, send: send(json.dumps({"return": {}, "id": req["id"]}).encode() + b"\n"))
        try:
            q = QMP(qsock, timeout=2.0)
            late = (q.execute("x-late"), [e["event"] for e in q.events], q.execute("query-status"))
            _QMP_HELD[str(w)] = [threading.RLock(), q]   # as a deterministic sandbox holds it
            refused_main, watch_ok = _err(QMP, qsock, 0.5), QMP(wsock, timeout=0.5)
            watch_ok.s.close()
            q.s.close()
        finally:
            _QMP_HELD.pop(str(w), None)
            done.set(); srv.close(); qsock.unlink()
            wdone.set(); wsrv.close(); wsock.unlink()
        lsn = socket.socket(socket.AF_UNIX)
        real_refused, QMP_REFUSED_S = QMP_REFUSED_S, 2.0
        try:
            lsn.bind(str(qsock))   # the file there, no listener: refused
            t_ref = time.monotonic()
            gone = _err(qmp_dial, qsock, 0.5, None, True)
            gone_s = time.monotonic() - t_ref
            lsn.listen(1)   # busy elsewhere: a connect waits in the backlog, ungreeted
            queued = _err(QMP, qsock, 0.3, True)
        finally:
            QMP_REFUSED_S = real_refused
            lsn.close()
            qsock.unlink()
        check("QMP (Step X.61): a reply to another command's id is skipped (its event kept); the watch socket isn't "
              "refused for W's held connection, the main one is; with a backlog a refused connect is raised at once "
              "as no listener, and an ungreeted one is queued behind a held client",
              late == ({"return": "x-late", "id": 2}, ["X_TICK"], {"return": "query-status", "id": 3})
              and isinstance(refused_main, ConnectionRefusedError) and "held by another client" in str(refused_main)
              and isinstance(gone, ConnectionRefusedError) and gone_s < 0.5 and "no listener" in str(gone)
              and isinstance(queued, TimeoutError) and "queued behind a held client" in str(queued),
              f"{late} | {refused_main} | {gone} {gone_s:.2f} | {queued}")
        # AZ-685: on a build with the watch monitor a long command waits as long as the frame moves (a slow
        # background sandbox finishes), its reply split across a slice kept; a frame that stops moving, or a watch
        # that doesn't answer, is a hang after STALL_S; the held connection serves the next command after a reply.
        # Step X.94: one carrying timeout-ms whose frame stopped under a watch that answers gets xemu's timed-out
        # reply at its bound (sitting s94's t03b: the watch's stall had dropped it); a mute watch is still a hang
        frame = {"n": 100, "moving": True}

        def advance_after(delay: float):
            def answer(req: dict, send) -> None:
                if req["execute"] == "xemu-frame-advance":
                    time.sleep(delay)
                    body = json.dumps({"return": {"frame": 160, "running": False}, "id": req["id"]}).encode()
                    send(body[:7])   # split across a wait's slices
                    time.sleep(0.15)
                    send(body[7:] + b"\n")
                elif req["execute"] == "x-forever":
                    time.sleep(3.0)
                elif req["execute"] == "x-bounded":   # xemu pauses it at its timeout-ms and replies
                    time.sleep(req["arguments"]["timeout-ms"] / 1000)
                    send(json.dumps({"return": {"frame": 101, "running": False, "timed-out": True},
                                     "id": req["id"]}).encode() + b"\n")
                else:
                    send(json.dumps({"return": {}, "id": req["id"]}).encode() + b"\n")
            return answer

        def watch_answer(req: dict, send) -> None:
            if frame["moving"]:
                frame["n"] += 1
            send(json.dumps({"return": {"frame": frame["n"], "running": True}, "id": req["id"]}).encode() + b"\n")
        real_stall, STALL_S = STALL_S, 0.5
        lq = Sandbox("st")
        lq.w, lq.st = w, {"deterministic": True, "qmp_watch": True}
        srv, done = serve_at(qsock, advance_after(1.2))
        wsrv, wdone = serve_at(wsock, watch_answer)
        try:
            t_l = time.monotonic()
            slow = lq._long_qmp("xemu-frame-advance", {"frames": 60}, slice_s=0.1)
            slow_s, then = time.monotonic() - t_l, lq.qmp("query-status")
            frame["moving"] = False
            stuck = _err(lq._long_qmp, "x-forever", {}, slice_s=0.1)
            t_b = time.monotonic()
            try:
                bounded = lq._long_qmp("x-bounded", {"timeout-ms": 1500}, slice_s=0.3)
            except TimeoutError as e:   # the bug: the watch's stall dropped xemu's timed-out reply
                bounded = e
            bounded_s = time.monotonic() - t_b
            wdone.set(); wsrv.close(); wsock.unlink()
            mute = _err(lq._long_qmp, "x-forever", {"timeout-ms": 60000}, slice_s=0.1)
        finally:
            STALL_S = real_stall
            lq._close_qmp()
            done.set(); srv.close(); qsock.unlink()
            wdone.set(); wsrv.close()
            wsock.unlink(missing_ok=True)
        rt = Sandbox("st")   # real time: a connection per command, its greeting late past a slice (the backlog)
        rt.w, rt.st, frame["moving"] = w, {"qmp_watch": True}, True
        srv, done = serve_at(qsock, advance_after(0.0), greet_s=0.3)
        wsrv, wdone = serve_at(wsock, watch_answer)
        try:
            queued_rt = rt._long_qmp("xemu-frame-advance", {"frames": 60}, slice_s=0.1)
        except (TimeoutError, OSError) as e:   # the bug: a greeting past the slice taken for a hang
            queued_rt = e
        finally:
            done.set(); srv.close(); qsock.unlink()
            wdone.set(); wsrv.close(); wsock.unlink()
        check("long QMP (AZ-685, Step X.61): an advance past STALL_S returns while the watch monitor's frame moves "
              "(its reply split across a slice); a frame that stops, or a watch that doesn't answer, raises "
              "TimeoutError naming it, but one carrying timeout-ms under a watch that answers gets xemu's timed-out "
              "reply at its bound (Step X.94); a real-time connection greeted after a slice still sends",
              slow == {"return": {"frame": 160, "running": False}, "id": 2} and 1.2 <= slow_s < 2.5
              and then == {"return": {}, "id": 3}
              and isinstance(stuck, TimeoutError) and "no frame moved in 0 s" in str(stuck)
              and "frame 1" in str(stuck) and isinstance(mute, TimeoutError) and "watch monitor: no answer" in str(mute)
              and isinstance(bounded, dict) and bounded.get("return", {}).get("timed-out") is True
              and 1.5 <= bounded_s < 1.8
              and isinstance(queued_rt, dict) and queued_rt.get("return", {}).get("frame") == 160,
              f"{slow} {slow_s:.2f} {then} | {stuck} | {bounded} {bounded_s:.2f} | {mute} | {queued_rt}")
        runlog.write_text("xemu_version: 0.14-138-g3bf46c731e\n", encoding="utf-8")   # no readiness lines
        sb.alive, sb.st["xemu_status"], waited = (lambda: True), True, {}
        for name, answer in (("event", status(False, ev("XEMU_READY"))), ("query", status(True)),
                             ("never", status(False))):
            srv, stop = serve_qmp(answer)
            READY_S = 0.3 if name == "never" else 3.0   # a ready one returns at once: room for a loaded machine
            sb.st.update(launched_at=time.time())
            sb.st.pop("ready_at", None)
            try:
                waited[name] = type(_err(sb.await_ready)).__name__
            finally:
                stop.set()
                srv.close()
                qsock.unlink()
        count = {"loads": 0}

        def status_qmp(cmd: str, **args) -> dict:   # loadvm counts a load (but a silent one) in query-xemu-status
            if cmd == XEMU_STATUS:
                return {"return": {"ready": True, "loads": count["loads"]}}
            if args.get("command-line", "").startswith("loadvm") and "silent" not in args["command-line"]:
                count["loads"] += 1
            return fake_qmp(cmd, **args)
        sb.qmp, sb.st["ready_at"] = status_qmp, time.time()
        by_status = [sb.loadvm("vanilla-flat", halt_at_tick=False)["loadvm"],
                     str(_err(sb.loadvm, "s-silent", halt_at_tick=False))]
        sb.qmp, sb.st["xemu_status"] = loading_qmp, False
        del sb.alive
        listed = [xemu_status_offered(r) for r in (
            {"return": [{"name": "query-commands"}, {"name": "query-xemu-frame"}, {"name": "query-xemu-checkpoints"}]},
            {"return": [{"name": "query-xemu-frame"}, {"name": XEMU_STATUS}]},
            {"error": {"class": "CommandNotFound", "desc": "The command query-commands has not been found"}})]
        check("readiness by QMP (Step X.33): a build whose query-commands lists query-xemu-status (by its exact "
              "name; v0.14-36's other query-xemu-* commands or an error don't) is ready when the query says so or "
              "XEMU_READY arrives on that connection (TimeoutError when neither), and a loadvm is confirmed by its "
              "load count, with no line in the run log; v0.14-36 (no query-xemu-status) is never asked",
              listed == [False, True, False]
              and waited == {"event": "NoneType", "query": "NoneType", "never": "TimeoutError"}
              and by_status[0] == "ok" and "XEMU_STATE_LOADED" in by_status[1] and count["loads"] == 1
              and XEMU_STATUS not in lines_cmds, f"{listed} {waited} {by_status}")
        # Step X.33 (PROMPT-7 P, AZ-293): a later build's Vulkan exits name the failed call or fence wait, and a
        # windowed one's abort its call; v0.14-36's lines read as before
        causes = []
        for text in ("vk_result = -3 in pgraph_vk_finish (../hw/xbox/nv2a/pgraph/vk/command.c:321)\n" + VULKAN_FAILED,
                     "xemu: vkWaitForFences timeout in compositor ring reclaim (>5s). GPU or driver appears hung; "
                     "aborting so the user sees the failure rather than a frozen window.\n" + VULKAN_FAILED,
                     "vk_result = -4 in pgraph_vk_finish (c.c:1)\n" + DEVICE_LOST, "vk_result = -4 in f (c.c:1)",
                     "vk_result = -4\n" + DEVICE_LOST,
                     "xemu: vkWaitForFences failed in pgraph_vk_wait_slot_fence: VkResult=-4\n" + DEVICE_LOST,
                     "vk_result = -3"):
            runlog.write_text(f"xemu_version: 0.14\n{text}\n", encoding="utf-8")
            causes.append(exit_cause(w))
        check("exit_cause (Step X.33, AZ-293): a later fork build's 'Vulkan call failed' and lost-device exits name "
              "the failed call or fence wait, a windowed abort its call; v0.14-36's lines read as before",
              causes == [f"{VULKAN_FAILED} (vk_result = -3 in pgraph_vk_finish "
                         "(../hw/xbox/nv2a/pgraph/vk/command.c:321))",
                         f"{VULKAN_FAILED} (vkWaitForFences timeout in compositor ring reclaim)",
                         f"{DEVICE_LOST} (vk_result = -4 in pgraph_vk_finish (c.c:1))", "vk_result = -4 in f (c.c:1)",
                         DEVICE_LOST, DEVICE_LOST, "no cause in the run log"], f"{causes}")
        # AZ-480: an xemu that quits at launch (upstream on a taken -qmp port) fails by its exit and QEMU's error, not
        # by the proof lines its short log lacks; the failed up still compares its baselines and deletes W by its path
        wq = tmp / "azx-st.quits"
        wq.mkdir()
        (wq / "src.bin").write_bytes(b"x")
        sbq = Sandbox("selftest")
        sbq.w, sbq._owner = wq, False
        sbq.st = {"W": str(wq), "launches": 0, "originals": [str(wq / "src.bin")]}
        (wq / "baseline_before.txt").write_text(baseline([wq / "src.bin"]), encoding="utf-8")
        taken = "-qmp tcp:127.0.0.1:1,server=on,wait=off: Failed to find an available port: Address already in use"
        sbq.argv = lambda _port: [sys.executable, "-c", f"import sys; print('xemu_version: 0.8.136'); "
                                  f"print('xemu: {taken}'); sys.exit(1)"]
        quit_err = _err(sbq._launch)
        sbq.keep = True
        sbq._abort()
        kept = dict(sbq.st.get("abort", {})), wq.exists()
        sbq.keep = False
        sbq._abort()
        check("launch (AZ-480): an xemu that quits at launch fails by its exit code and QEMU's error, not as a sandbox "
              "check; the failed up compares the sources and pref dir with their baseline, says when it keeps W (keep), "
              "and else deletes W by its path",
              isinstance(quit_err, SystemExit) and str(quit_err).startswith(f"xemu exited (1, {taken}) at launch")
              and kept[0].get("kept") is True and kept[1]
              and sbq.st.get("abort", {}).get("sources_equal") is True and "pref_dir_equal" in sbq.st["abort"]
              and sbq.st["abort"]["kept"] is False and not wq.exists(), f"{quit_err} {kept} {sbq.st.get('abort')}")
        # Step X.60: a guest RAM size xemu aborts on or doesn't run is refused by name, with its reason, before xemu
        # starts: 64 and 128 MiB on every build; above 128 only a build with BIG_RAM_MARK, a multiple of 16 to 3840
        ram_cases = {   # name: (argv, mem_limit values, big build, None or what the refusal says)
            "64": ([], ["'64'"], False, None), "128": (["-m", "128"], ["'128'"], False, None),
            "default": ([], [], False, None), "192 big": (["-m", "192"], [], True, None),
            "1G big": (["-m", "1G"], ["'512'"], True, None),
            "96": (["-m", "96"], [], False, "-m 96: not a power of two: NV2A BAR1 aliases all guest RAM and "
                   "pci_register_bar asserts a power-of-two BAR, so xemu aborts at start (SIGABRT from nv2a_init)"),
            "32": (["-m", "size=32M"], [], False, "-m size=32M: below 64 MiB"),
            "192 old": (["-m", "192"], [], False, "-m 192: above 128 MiB: this build has no RAM past 128 MiB"),
            "200 big": (["-m", "200"], [], True, "-m 200: above 128 MiB this build takes a multiple of 16 MiB"),
            "4096 big": (["-m", "4096"], [], True, "3840 MiB at most"),
            "unread": (["-m", "lots"], [], False, "-m lots: not a size in MiB"),
            "256 old": ([], ["'256'"], False, "mem_limit '256': not one of this build's values ('64', '128'), so "
                        "xemu ignores it and runs its default 64 MiB"),
            "192 enum": ([], ["'192'"], True, "mem_limit '192': not one of this build's values ('64', '128', "
                         "'256', '512')"),
            "int": ([], ["128"], False, "mem_limit 128: not one")}
        ram_got = {k: ram_refusal(a, [f"[sys]\nmem_limit = {v}\n" for v in t], big)
                   for k, (a, t, big, _) in ram_cases.items()}
        wr = tmp / "azx-st.ram"
        (wr / "xemu.app/Contents/Resources").mkdir(parents=True)
        for p in (wr / "xemu.toml", wr / "xemu.app/Contents/Resources/xemu.toml"):
            p.write_text(_put(scratch_toml(_SAMPLE_TOML.format(fx=fx), str(wr)), "sys", "mem_limit", "'96'"),
                         encoding="utf-8")
        sbm = Sandbox("selftest")
        sbm.w, sbm._owner, sbm.st = wr, False, {"W": str(wr), "launches": 0}
        sbm.argv = lambda _port: [sys.executable, "-c", f"open({str(wr / 'ran')!r}, 'w')", "-m", "96"]
        ram_err = _err(sbm._launch)
        check("ram_refusal (Step X.60): a guest RAM size xemu aborts on (a non-power-of-two at or below 128 MiB: "
              "pci_register_bar's assert) or doesn't run (below 64; above 128 on a build without the fork's "
              "experimental RAM, or not its multiple of 16 to 3840; a mem_limit outside the build's values) is refused "
              "by name with its reason; 64, 128 and a size a big build takes pass; a launch asking for one never "
              "starts xemu and leaves W as it was",
              all((ram_got[k] is None) if want is None else (ram_got[k] is not None and want in ram_got[k])
                  for k, (*_, want) in ram_cases.items())
              and isinstance(ram_err, SystemExit) and str(ram_err).startswith("not launched: a guest RAM size")
              and "-m 96: not a power of two" in str(ram_err) and "mem_limit '96'" in str(ram_err)
              and sorted(p.name for p in wr.iterdir()) == ["xemu.app", "xemu.toml"], f"{ram_got} {ram_err}")
        # Step X.66 (v0.16.2, D599): the NV2A's DMA address bits a launch runs with, from its run log: 28 with the
        # wide line (256 MiB or more on v0.16.2), 27 without it (below 256, or an older build at any size)
        big_line = ("xemu: guest RAM {} MiB (experimental above 128 MiB): NV2A BAR1 and VGA cover the first 128 MiB, "
                    "NV_PFB_CSTATUS reports 128 MiB\n")
        wide_line = "xemu: NV2A wide addressing: 28 bits (guest RAM 256 MiB or more)\n"
        bits = [nv2a_bits(t) for t in ("xemu_version: 0.16.2\n", big_line.format(256) + wide_line,
                                       big_line.format(192), "xemu_version: 0.16.1\n" + big_line.format(256))]
        check("nv2a_bits (Step X.66): a run log's guest RAM above 128 MiB and its NV2A address bits: 28 with "
              "v0.16.2's wide line, else 27",
              bits == [(None, 27), (256, 28), (192, 27), (256, 27)], f"{bits}")
        # Step X.45: relaunch tells our own quit from a death: after _quit it says "quit"; after a death "died" with
        # its exit and cause (an nv2a assertion's abort, which exit_cause names) and keeps the run log's tail in the
        # sitting's logs before teardown deletes W. And a second QMP connection to a W whose connection this process
        # holds is refused at once (X.43's driver waited out 600 s for its greeting)
        wr = tmp / "azx-st.rl"
        wr.mkdir()
        sbr, up_ = Sandbox("selftest", logs=tmp / "rl-logs"), [True]
        sbr.w, sbr._owner, sbr.st = wr, False, {"W": str(wr), "pid": 4242, "launches": 1, "events": []}
        sbr.alive = lambda: up_[0]
        sbr.qmp = lambda cmd, **_a: up_.__setitem__(0, False) or {"return": {}}   # QMP quit: that xemu exits
        sbr._launch = lambda hold=False: sbr.st.update(pid=sbr.st["pid"] + 1, launches=sbr.st["launches"] + 1) \
            or up_.__setitem__(0, True)
        take_slot = lambda *_a, **_k: None  # noqa: E731
        try:
            sbr._quit()
            sbr.relaunch()
            (wr / "run.log").write_text('xemu_version: 0.16\nUnknown vs param: 0x0\nAssertion failed: (!"Unknown vs '
                                        'param"), function vsh_get_param, file vsh-prog.c, line 320.\n', encoding="utf-8")
            up_[0] = False   # it died: no quit of ours
            sbr.relaunch()
        finally:
            take_slot = real_take_slot
        said = [e.split(" ", 1)[1] for e in sbr.st["events"] if "relaunch after" in e]
        tail = tmp / "rl-logs" / "azx-st.rl-run.2.log.tail"
        (wr / "src.bin").write_bytes(b"x")   # then it dies again right before the teardown, which deletes W
        sbr.st["originals"] = [str(wr / "src.bin")]
        (wr / "baseline_before.txt").write_text(baseline([wr / "src.bin"]), encoding="utf-8")
        up_[0] = False
        sbr.down()
        torn = tmp / "rl-logs" / "azx-st.rl-run.3.log.tail"
        said_down = [e.split(" ", 1)[1] for e in sbr.st["events"] if "down after" in e]
        _QMP_HELD[str(wr)] = [threading.RLock(), object()]   # this process holds W's connection
        t0 = time.monotonic()
        second = _err(QMP, wr / "qmp.sock", timeout=30.0)
        waited = time.monotonic() - t0
        _QMP_HELD.pop(str(wr))
        check("relaunch (Step X.45): our own quit is logged as a quit, a death as died with its exit and cause (an "
              "nv2a assertion's abort) and its run log's tail kept in the sitting's logs, by a relaunch or a teardown; "
              "a second QMP connection to a W this process holds one to is refused at once",
              said == ["relaunch after pid 4242 quit (its slot was reclaimed: queued like a new one)",
                       "relaunch after pid 4243 died (None, abort: Unknown vs param: 0x0; Assertion failed: (!\"Unknown "
                       "vs param\"), function vsh_get_param, file vsh-prog.c, line 320.) (its slot was reclaimed: "
                       "queued like a new one)"]
              and tail.exists() and "Unknown vs param" in tail.read_text(encoding="utf-8")
              and torn.exists() and not wr.exists() and len(said_down) == 1
              and said_down[0].startswith("down after pid 4244 died (None, abort: Unknown vs param")
              and isinstance(second, ConnectionRefusedError) and "held by another client" in str(second)
              and waited < 1.0, f"{said} {second!r} {waited:.1f}")
        # PROMPT-8 F(2) (Step X.37): an owner demo writes the fork's owner-demo.json right after its xemu starts and
        # removes it once that xemu is gone, only while it names that pid (its launcher's thread reaps the xemu, so
        # an exited one never stays a zombie, which kill(pid, 0) counts as running); an agent sandbox never writes
        # it, and its launch waits while the file names a live pid (a demo's doesn't, nor behind the tickets that wait
        # for it); a dead pid, a torn file or a record of ours whose pid is no xemu is no demo
        quits = [sys.executable, "-c", "import sys; print('xemu_version: 0.14-36'); sys.exit(1)"]
        sees = [sys.executable, "-c", "import json, os, sys, time\n"   # the demo's xemu: the file it sees, then quits
                "for _ in range(250):\n"
                "    if os.path.exists(sys.argv[1]):\n"
                "        break\n"
                "    time.sleep(0.02)\n"
                "rec = json.load(open(sys.argv[1])) if os.path.exists(sys.argv[1]) else None\n"
                "mode = os.stat(sys.argv[1]).st_mode & 0o777 if rec else None\n"
                "json.dump({'rec': rec, 'mode': mode, 'pid': os.getpid()}, open(sys.argv[2], 'w'))\n"
                "print('xemu_version: 0.14-36'); sys.exit(1)", str(OWNER_DEMO), str(tmp / "azx-st.demo" / "saw.json")]
        launched, umask = {}, os.umask(0o077)   # the folder's and the file's modes, whatever the umask
        try:
            for name, argv_, kw in (("agent", quits, {}), ("demo", sees, {"headless": "0", "owner_pad": 1})):
                box = Sandbox(name, **kw)
                box.w, box._owner, box.argv = tmp / f"azx-st.{name}", False, (lambda _port, a=argv_: a)
                box.w.mkdir()
                box.st = {"W": str(box.w), "launches": 0, "owner_pad": kw.get("owner_pad")}
                launched[name] = (box, type(_err(box._launch)).__name__, OWNER_DEMO.parent.exists())   # quits at launch
                _drop_slot(box.w)
        finally:
            os.umask(umask)
        demo_box, dpid = launched["demo"][0], launched["demo"][0].st["pid"]
        saw = json.loads((demo_box.w / "saw.json").read_text(encoding="utf-8"))
        if demo_box._demo_reaper is not None:
            demo_box._demo_reaper.join(5.0)
        leases = OWNER_DEMO.parent
        reaped = not OWNER_DEMO.exists()   # by its launcher's thread: nothing called alive()
        listing = sorted(p.name for p in leases.iterdir()) if leases.exists() else None
        mode = leases.stat().st_mode & 0o777 if leases.exists() else None
        owner_demo_begin(dpid, "one")
        with OWNER_DEMO.open(encoding="utf-8") as was:   # a reader that opened it before a rewrite reads it whole
            ino = OWNER_DEMO.stat().st_ino
            owner_demo_begin(dpid, "two")
            atomic = json.loads(was.read())["purpose"] == "one" and OWNER_DEMO.stat().st_ino != ino
        zombie = subprocess.Popen(["true"])
        try:
            os.waitid(os.P_PID, zombie.pid, os.WEXITED | os.WNOWAIT)   # it exited and nothing reaped it
            owner_demo_begin(zombie.pid, "zombie")
            zombie_is_none = (xemu_queue.alive(zombie.pid), owner_demo(), OWNER_DEMO.exists()) == (True, None, False)
        finally:
            zombie.wait()
        OWNER_DEMO.write_text(json.dumps({"pid": dpid, "who": "the owner"}), encoding="utf-8")   # another's, pid gone
        dead_is_none, w4 = owner_demo() is None and OWNER_DEMO.exists(), tmp / "azx-st.wait"
        w4.mkdir()

        def slot_for(demo_: bool, window: bool = False) -> str:
            try:
                _unlock(take_slot(w4, -1, demo=demo_, window=window))
                return "admitted"
            except SystemExit as e:
                return str(e)
            finally:
                _drop_slot(w4)
        other = subprocess.Popen(["sleep", "60"])
        xemu_pids, admission = (lambda: []), (lambda n: None)   # no xemu runs and the rule would admit
        real_budget, busy = xemu_queue.demo_budget, tmp / "azx-st.busy"
        try:
            OWNER_DEMO.write_text(json.dumps({"pid": other.pid, "who": "the owner", "purpose": "x99"}),
                                  encoding="utf-8")
            demo_box.alive()   # our demo's xemu is gone, but the file names another's
            kept_other = (owner_demo() or {}).get("pid") == other.pid
            agent_wait = slot_for(False, window=True)
            beside = slot_for(False)   # D526: headless, it starts beside the demo
            xemu_queue.demo_budget = lambda: 1
            busy.mkdir()
            _write_slot(busy, {"holder": os.getpid()})   # one of ours launching beside it: the budget's one
            try:
                over = slot_for(False)
            finally:
                _drop_slot(busy)
                xemu_queue.demo_budget = real_budget
            held = [xemu_queue.take_ticket({"W": str(tmp / f"azx-st.held{i}")}, SLOTS) for i in range(2)]
            xemu_queue.renew_ticket(held[0], owner_demo_says(owner_demo()), cores=False)   # a window of ours
            xemu_queue.renew_ticket(held[1], f"an owner demo runs (pid {other.pid}; {OWNER_DEMO}): no new xemu until "
                                    "it ends", cores=False)   # an older harness's ticket, held for the demo
            try:   # a headless launch waits behind neither (D526); a window still waits for the demo
                behind = (slot_for(False), slot_for(False, window=True))
            finally:
                for t in held:
                    xemu_queue.drop_ticket(t)
            ahead = xemu_queue.take_ticket({"W": str(tmp / "azx-st.ahead")}, SLOTS)   # an agent waiting for the demo
            try:
                demo_went = slot_for(True)
            finally:
                xemu_queue.drop_ticket(ahead)
            OWNER_DEMO.write_text('{"pid": ', encoding="utf-8")   # half a file
            torn_is_none = owner_demo() is None
            owner_demo_begin(dpid, "demo")
            demo_box.alive()
            ended = not OWNER_DEMO.exists()
        finally:
            other.kill()
            other.wait()
            xemu_pids, admission = real_xemu_pids, real_admission
        check("owner demo (PROMPT-8 F(2), Step X.37; D526): its launch writes the fork's owner-demo.json right after "
              "its xemu starts (its pid, who, purpose; 0o644 in a 0o755 folder whatever the umask; a temp file renamed "
              "in, so a reader never sees it rewritten) and removes it once that xemu is gone, only while the file "
              "names it (its launcher's thread reaps it, with no alive() call); an agent sandbox never writes it; "
              "while the file names a live pid a window of ours waits, saying so, and a headless one starts beside it "
              "until the demo's budget of ours run there, behind no ticket held only for the demo, ours or an older "
              "harness's (a demo's doesn't wait, nor behind tickets that wait for it); a dead pid, a torn file or a "
              "record of ours whose pid is a zombie is no demo",
              launched["agent"][1:] == ("SystemExit", False) and launched["demo"][1:] == ("SystemExit", True)
              and saw == {"rec": {"pid": dpid, "who": OWNER_DEMO_WHO, "purpose": "demo"}, "mode": 0o644, "pid": dpid}
              and reaped and listing == [] and mode == 0o755 and atomic and zombie_is_none and dead_is_none
              and kept_other and agent_wait.startswith(f"STOP: an owner demo runs (pid {other.pid}, who the owner, "
                                                       "purpose x99") and "no new window" in agent_wait
              and beside == "admitted" and over.startswith(f"STOP: an owner demo runs (pid {other.pid}")
              and "1 sandbox(es) run beside it in the background, its budget of 1" in over
              and behind[0] == "admitted" and "no new window" in behind[1]
              and demo_went == "admitted" and torn_is_none and ended,
              f"{[v[1:] for v in launched.values()]} {saw} {reaped} {listing} {mode and oct(mode)} {atomic} "
              f"{zombie_is_none} {dead_is_none} {kept_other} {agent_wait[:90]} {beside[:60]} {over[:140]} "
              f"{[b[:60] for b in behind]} {demo_went[:60]}")
        # AZ-601: a demo's relaunch keeps the lease: its quit names this process (relaunch_of the old xemu), which the
        # old xemu's end (alive(), the reaper) leaves, so waiters still wait; the new launch names its xemu; a marker
        # whose relaunch never launched goes (relaunch's failure, down); one whose pid runs another command than the
        # relaunching one's (a reused pid) is no demo
        waits = [sys.executable, "-c", "import json, os, sys, time\n"   # the new xemu: the file once it names it
                 "rec = None\n"
                 "for _ in range(250):\n"
                 "    try:\n"
                 "        rec = json.load(open(sys.argv[1]))\n"
                 "    except (OSError, ValueError):\n"
                 "        rec = None\n"
                 "    if rec and rec.get('pid') == os.getpid():\n"
                 "        break\n"
                 "    time.sleep(0.02)\n"
                 "json.dump(rec, open(sys.argv[2], 'w'))\n"
                 "print('xemu_version: 0.14-36'); sys.exit(1)", str(OWNER_DEMO), str(demo_box.w / "saw2.json")]
        xemu_pids, admission = (lambda: []), (lambda n: None)
        try:
            demo_box._quit(relaunch=True)   # its xemu (dpid) is gone: the marker alone holds launches now
            marker = json.loads(OWNER_DEMO.read_text(encoding="utf-8"))
            demo_box.alive()
            owner_demo_end(dpid)   # the old xemu's reaper
            held = ((owner_demo() or {}).get("pid"), slot_for(False, window=True), slot_for(True))
            owner_demo_begin(os.getpid(), "demo", relaunch_of=dpid, relaunch_cmd="a process since gone")
            reused = (owner_demo(), OWNER_DEMO.exists())   # the pid now runs another command: no relaunch, removed
            owner_demo_begin(os.getpid(), "demo", **{k: marker[k] for k in ("relaunch_of", "relaunch_cmd")})
            demo_box.argv = lambda _port: waits
            relaunch_type = type(_err(demo_box._launch)).__name__   # the fake quits at launch, as before
            if demo_box._demo_reaper is not None:
                demo_box._demo_reaper.join(5.0)
            _drop_slot(demo_box.w)
            saw2 = json.loads((demo_box.w / "saw2.json").read_text(encoding="utf-8"))
            new_named = saw2 == {"pid": demo_box.st["pid"], "who": OWNER_DEMO_WHO, "purpose": "demo"} \
                and not OWNER_DEMO.exists()
            demo_box._quit(relaunch=True)
            take_slot = lambda *_a, **_k: (_ for _ in ()).throw(SystemExit("STOP: waited"))  # noqa: E731
            never_came = (type(_err(demo_box.relaunch)).__name__, OWNER_DEMO.exists())
            take_slot = real_take_slot
            demo_box._quit(relaunch=True)
            demo_box.st["originals"] = []
            (demo_box.w / "baseline_before.txt").write_text(baseline([]), encoding="utf-8")
            downed = (OWNER_DEMO.exists(), demo_box.down(keep=True).get("sources_equal"), OWNER_DEMO.exists())
            agent_box = launched["agent"][0]
            agent_box._quit(relaunch=True)   # not a demo: no marker
            agent_none = not OWNER_DEMO.exists()
        finally:
            take_slot = real_take_slot
            xemu_pids, admission = real_xemu_pids, real_admission
            OWNER_DEMO.unlink(missing_ok=True)
        check("owner demo (AZ-601): a demo's relaunch keeps the lease: its quit names this process, relaunch_of the "
              "old xemu, which the old xemu's end leaves and waiting launches honour (a demo's own doesn't wait); "
              "the new launch names its xemu, whose end ends it; a relaunch that never launched and a down end a "
              "leftover marker; one whose pid now runs another command is none; an agent sandbox's quit writes none",
              marker == {"pid": os.getpid(), "who": OWNER_DEMO_WHO, "purpose": "demo", "relaunch_of": dpid,
                         "relaunch_cmd": pid_command(os.getpid())}
              and held[0] == os.getpid() and reused == (None, False)
              and held[1].startswith(f"STOP: an owner demo runs (pid {os.getpid()}")
              and held[2] == "admitted" and relaunch_type == "SystemExit" and new_named
              and never_came == ("SystemExit", False) and downed == (True, True, False) and agent_none,
              f"{marker} {held[0]} {held[1][:60]} {reused} {relaunch_type} {saw2} {never_came} {downed}")
        # D526: beside an owner demo our sandbox launches at background priority, the ones already running move there
        # at the demo's start (never the demo's own: its record's pid, or a sandbox.json naming an owner_pad), and its
        # end takes them back out
        calls, real_set_bg, bw, fakes = [], xemu_queue.set_background, {}, {}
        xemu_queue.set_background = lambda pid, on: calls.append((pid, on)) or True
        try:
            for k in ("named", "pad", "plain"):
                bw[k] = d = tmp / f"azx-bg.{k}"
                d.mkdir()
                (d / "sandbox.json").write_text(json.dumps({"owner_pad": 1 if k == "pad" else None}), encoding="utf-8")
                fakes[k] = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", f"{d}/xemu.app/x"])
                _write_slot(d, {"pid": fakes[k].pid})
            owner_demo_begin(fakes["named"].pid, "bg")   # our demo's record names one of them
            began, calls[:] = list(calls), []
            box = Sandbox("bgagent")
            box.w, box._owner, box.argv = tmp / "azx-st.bgagent", False, (lambda _port: quits)
            box.w.mkdir()
            box.st = {"W": str(box.w), "launches": 0, "owner_pad": None}
            launch_err = type(_err(box._launch)).__name__   # quits at launch, past the priority
            _drop_slot(box.w)
            beside_calls, calls[:] = list(calls), []
            ended_bg = owner_demo_end(fakes["named"].pid)
        finally:
            xemu_queue.set_background = real_set_bg
            OWNER_DEMO.unlink(missing_ok=True)
            for k, f in fakes.items():
                f.kill()
                f.wait()
                _drop_slot(bw[k])
        check("owner demo (D526): at its start our running sandboxes go to background priority, not the demo's own "
              "(the record's pid, an owner_pad); one launched beside it starts there, saying so; its end takes every "
              "one but an owner_pad's back out",
              began == [(fakes["plain"].pid, True)] and launch_err == "SystemExit"
              and beside_calls == [(box.st.get("pid"), True)]
              and any("launched at background priority beside an owner demo" in e for e in box.st.get("events", []))
              and ended_bg and calls == [(fakes["named"].pid, False), (fakes["plain"].pid, False)],
              f"{began} {beside_calls} {calls} {box.st.get('events')}")
        # AZ-293's teardown: an xemu whose QMP never greets and that ignores SIGTERM (the flip-stall hang) is quit
        # by SIGTERM, then SIGKILL, to its own pid
        dead_qmp = socket.socket(socket.AF_UNIX)
        dead_qmp.bind(str(qsock))
        dead_qmp.listen(1)   # it accepts a connection, then says nothing
        stall = subprocess.Popen([sys.executable, "-c", "import signal, time; signal.signal(signal.SIGTERM, "
                                  "signal.SIG_IGN); print(1, flush=True); time.sleep(60)",
                                  f"{w}/xemu.app/Contents/MacOS/xemu"], stdout=subprocess.PIPE)
        stall.stdout.readline()   # SIGTERM is ignored from here
        real_teardown, (QMP_S, QUIT_S, TERM_S) = (QMP_S, QUIT_S, TERM_S), (0.2, 0.2, 0.5)
        sbk = Sandbox("selftest")
        sbk.w, sbk._owner, sbk._proc, sbk.st = w, False, stall, {"W": str(w), "pid": stall.pid}
        try:
            quit_res = sbk._quit()
        finally:
            QMP_S, QUIT_S, TERM_S = real_teardown
            dead_qmp.close()
            qsock.unlink()
            if stall.poll() is None:
                stall.kill()
                stall.wait()
            stall.stdout.close()
        check("teardown (AZ-293): an xemu whose QMP never answers and that ignores SIGTERM is ended by the SIGKILL "
              "after it",
              "TimeoutError" in quit_res["quit"] and quit_res["process"] == "killed"
              and stall.returncode == -signal.SIGKILL, f"{quit_res} {stall.returncode}")
        runlog.unlink()
        READY_S, LOADED_S = real_waits
        sb.qmp = fake_qmp
        sb.st["ready_line"] = False
        calls.clear()
        sb.reset_into("mod.iso")
        check("modded-build path: stop, the build in the tray, system_reset, cont",
              [x for x in calls if x[0] != "query-block"] == [
                  ("stop", {}), ("blockdev-change-medium", {"device": CD, "filename": f"{w}/mod.iso", "format": "raw"}),
                  ("system_reset", {}), ("cont", {})] and sb.dvd() == "mod.iso")
        check("tags: a July vm-* state, an unknown tag and a vanilla-rzp-* tag on the D98 drive are refused",
              all(refused(sb.loadvm, t) for t in ("vm-20260704032357", "vanilla-nope", "vanilla-rzp-keys5-w1")))
        sb.savevm("s-scratch")
        check("tags: a tag saved in this sandbox loads; savevm never takes an oracle tag",
              sb.loadable("s-scratch") and refused(sb.savevm, "vanilla-flat") and refused(sb.savevm, "vm-1"))
        # Step X.32 (sitting x32d): a load that halts at its first player tick stops a running VM first, so HMP
        # loadvm keeps it stopped and the halt is the load's own first tick (a VM that ran ran on past a varying
        # number of ticks before the gdbstub attached); a load that runs on leaves the VM running
        sb.wait_bp = lambda vas, timeout: None
        lseq = {}
        for kw in ({}, {"halt_at_tick": False}):
            calls.clear()
            tray["status"] = "running"
            sb.loadvm("s-scratch", **kw)
            lseq[bool(kw)] = [a.get("command-line", c) for c, a in calls if not c.startswith("query-")]
        del sb.wait_bp
        check("loadvm (Step X.32): halting at the first player tick, a running VM is stopped before the load, so the "
              "halt is the load's own first tick; without the halt the load leaves it running",
              lseq == {False: ["stop", "loadvm s-scratch"], True: ["loadvm s-scratch"]}, f"{lseq}")
        # Step X.26: a checkpoint is savevm, then loadvm of that save, then on (a load restarts host audio state
        # no save holds, so a run continued past a bare savevm differs from every load of it); park keeps the
        # guest halted across both
        calls.clear()
        tray["status"] = "running"
        sb.savevm("s-ck")
        seq = [a.get("command-line", c) for c, a in calls if not c.startswith("query-")]
        calls.clear()
        sb._g, sb._halted = _FakeGuest(), True
        sb.persist_parked = lambda: w   # the private store stays out of the selftest
        parked = sb.park("p-ck")
        del sb.persist_parked
        pseq = [a.get("command-line", c) for c, a in calls if not c.startswith("query-")]
        check("checkpoints (Step X.26): savevm stops a running guest, saves, loads that save and runs it on; park "
              "saves and loads with the guest held halted, where it was",
              seq == ["stop", "savevm s-ck", "loadvm s-ck", "cont"] and pseq == ["savevm p-ck", "loadvm p-ck"]
              and "reload_s" in parked and sb._halted, f"{seq} {pseq}")
        # Step X.30: on a build with continuity (v0.14-36), deterministic, a save is the run that goes on: no
        # reload, unless a pipe line written hasn't reached the pad (a load drops it; the continued run would apply
        # it); park also keeps an in-memory checkpoint, which unpark in that xemu restores instead of loadvm
        clock = {"frame": 7}

        def ck_qmp(cmd: str, **args) -> dict:
            if cmd == "query-xemu-frame":
                return {"return": {**clock, "running": False}}
            if cmd.startswith("xemu-checkpoint"):
                calls.append((cmd, args))
                return {"return": {"name": args["name"], "size": 1, "frame": clock["frame"], "disk-sectors": 0}}
            return fake_qmp(cmd, **args)
        real_keys, sb.qmp = send_keys, ck_qmp
        globals()["send_keys"] = lambda fifo, line: None
        sb.st.update(continuity=True, checkpoints=True)
        calls.clear()
        tray["status"] = "running"
        sb.savevm("s-c1")
        cseq = [a.get("command-line", c) for c, a in calls if not c.startswith("query-")]
        Sandbox.send(sb, "down 235", after=3)   # reaches the pad at frame 10 at the latest
        calls.clear()
        sb.savevm("s-c2")
        pending_seq = [a.get("command-line", c) for c, a in calls if not c.startswith("query-")]
        clock["frame"] = 11
        calls.clear()
        sb._g, sb._halted = _FakeGuest(), True
        sb.persist_parked = lambda: w
        cparked = sb.park("p-c")
        sb._g.eip = l3.PLAYER_UPDATE
        unparked = sb.unpark("p-c")
        sb.st["pid"] = -1   # a relaunch: its checkpoints are gone
        relaunched = sb.unpark("p-c")["how"]
        del sb.persist_parked
        cpseq = [a.get("command-line", c) for c, a in calls if not c.startswith("query-")]
        # Step TD.4c: unpark's start check is replay's: a scene start (L3's at "scene") halts at the scene tick's
        # entry, where ECX isn't the entity; an update start at the scene tick is no start
        fg = sb._g
        smeta = {"entity": fg.ent, "clock": struct.unpack("<d", fg.read(fg.ent + 0x18, 8))[0],
                 "start_sha12": start_hash(fg.read, fg.ent)}
        fg.eip = l3.SCENE_TICK
        scene_start = [sb.unpark("p-c", {**smeta, "at": at})["at_start"] for at in ("scene", "update")]
        check("unpark (Step TD.4c): a start parked at the scene tick's entry is at its start, as replay checks it",
              scene_start == [True, False], f"{scene_start}")

        def miss_qmp(cmd: str, **args) -> dict:   # AZ-694: the restore lands elsewhere, the qcow2's load at the start
            if cmd == "xemu-checkpoint-restore":
                fg.eip = 0x12345
            if cmd == "human-monitor-command" and args.get("command-line") == "loadvm p-c":
                fg.eip = l3.SCENE_TICK
            return ck_qmp(cmd, **args)
        sb.qmp = miss_qmp
        sb.st["checkpoints_held"] = {"pid": sb.st.get("pid"), "names": {"p-c": {"disc": sb.dvd()}}}
        fell = sb.unpark("p-c", {**smeta, "at": "scene"})
        sb.qmp = ck_qmp
        check("unpark (AZ-694): a checkpoint restore that misses its start is dropped and the tag loaded from the "
              "qcow2, at its start", fell.get("at_start") is True and fell["how"] == "loadvm" and "missed" in fell
              and "p-c" not in sb.checkpoints(), f"{fell}")

        class Held(_FakeGuest):   # AZ-781: the stub drops a ^C sent to a VM that already stands (no stop reply)
            def interrupt(self):
                self.sent.append("^C")
                if self.status != "running":
                    raise TimeoutError("no stop reply in RSP's 10 s")
                return b"T02"

            def cont(self):
                self.sent.append("c")
        held_ = {}
        for status in ("debug", "running"):
            hsb = Sandbox("st")
            hsb.w, hsb._owner, hsb.st = w, False, {"W": str(w), "events": []}
            hsb.qmp = lambda cmd, _s=status, **a: {"return": {"status": _s} if cmd == "query-status" else {}}
            g_ = hsb._g = Held()
            g_.status, g_.sent, hsb._halted = status, [], False
            took = hsb.halt() is g_ and hsb._halted
            hsb._halted = False
            hsb.release()
            held_[status] = (took, g_.sent, hsb._g)
        check("halt and release (AZ-781): a guest the stub already holds while _halted says running (HMP 'paused "
              "(debug)') is taken as halted with no ^C, and release lets it go (its c); a running one gets the ^C",
              held_ == {"debug": (True, ["c"], None), "running": (True, ["^C", "^C", "c"], None)}, f"{held_}")
        globals()["send_keys"] = real_keys
        sb.st.update(continuity=False, checkpoints=False)
        check("continuity (Step X.30): deterministic on v0.14-36 savevm and park need no reload (a pipe line not "
              "yet at the pad brings it back); park keeps a checkpoint in memory that unpark in that xemu restores, "
              "and a relaunched xemu loads the qcow2's",
              cseq == ["stop", "savevm s-c1", "cont"] and pending_seq == ["stop", "savevm s-c2", "loadvm s-c2", "cont"]
              and cparked["reload_s"] is None and "checkpoint_s" in cparked and unparked["how"] == "checkpoint"
              and relaunched == "loadvm" and cpseq == ["savevm p-c", "xemu-checkpoint-save", "xemu-checkpoint-restore",
                                                       "loadvm p-c"], f"{cseq} {pending_seq} {cpseq}")
        # AZ-732: a deterministic guest the gdbstub holds halted is saved where it is, still held (as park saves):
        # a release first ran it for as long as the stop took on the host, so boot_build's warm save moved its halt
        calls.clear()
        sb._g, sb._halted, sb.st["deterministic"] = _FakeGuest(), True, True
        sb._g.eip, tray["status"] = PLAYER_TICK, "debug"
        sb.savevm("s-held")
        hseq = [a.get("command-line", c) for c, a in calls if not c.startswith("query-")]
        held_at = sb._g.eip if sb._g is not None else None
        sb.st.pop("deterministic")
        check("savevm (AZ-732): a deterministic guest the gdbstub holds halted at a player tick is saved there and "
              "stays held, never let go to run on the host's time first",
              held_at == PLAYER_TICK and sb._halted and "savevm s-held" in hseq and "stop" not in hseq
              and "cont" not in hseq, f"{hseq} {held_at}")
        # Step X.32b: on v0.15 (incremental restores) a load that leaves the VM stopped keeps its load as a checkpoint
        # and loads the tag again in this xemu by an incremental restore (the fork: 4.5-5.8 ms against loadvm's 25.5);
        # a savevm of the tag drops it, so the next load is loadvm's again; a load that runs on keeps nothing
        sb.st.update(checkpoints=True, incremental=True)
        sb.qmp, hows = ck_qmp, []
        calls.clear()
        for kw in ({"paused": True}, {"paused": True}, {"halt_at_tick": False}):
            tray["status"] = "paused"
            hows.append(sb.loadvm("s-scratch", **kw)["how"])
        sb.savevm("s-scratch")
        hows.append(sb.loadvm("s-scratch", paused=True)["how"])
        lcseq = [(c, a.get("name", a.get("command-line")), a.get("incremental")) for c, a in calls
                 if not c.startswith("query-") and c not in ("stop", "cont")]
        sb.st.update(checkpoints=False, incremental=False)
        sb.st.pop("checkpoints_held", None)
        sb.qmp = fake_qmp
        check("loadvm (Step X.32b): on v0.15 a stopped load keeps itself as a checkpoint and the tag loads again by an "
              "incremental restore; one that runs on keeps nothing; savevm of the tag drops it",
              hows == ["loadvm", "checkpoint", "loadvm", "loadvm"] and lcseq == [
                  ("human-monitor-command", "loadvm s-scratch", None),
                  ("xemu-checkpoint-save", "load-s-scratch", None),
                  ("xemu-checkpoint-restore", "load-s-scratch", True),
                  ("human-monitor-command", "loadvm s-scratch", None),
                  ("xemu-checkpoint-delete", "load-s-scratch", None),
                  ("human-monitor-command", "savevm s-scratch", None),
                  ("human-monitor-command", "loadvm s-scratch", None),   # the save's reload (no continuity here)
                  ("human-monitor-command", "loadvm s-scratch", None),
                  ("xemu-checkpoint-save", "load-s-scratch", None)], f"{hows} {lcseq}")
        # Step X.32b's review: an HMP loadvm reverts the qcow2's disk outside the checkpoints' sector records (the
        # fork's record only IDE writes), so it drops every checkpoint but the tag's own load: a load of another tag
        # and an unpark after it load by loadvm, where a restore would put back a state's RAM over another's disk
        sb.st.update(checkpoints=True, incremental=True)
        sb.qmp, hows = ck_qmp, []
        sb.persist_parked = lambda: w
        calls.clear()
        tray["status"] = "paused"
        hows.append(sb.loadvm("s-scratch", paused=True)["how"])
        sb._g, sb._halted = _FakeGuest(), True
        sb.park("p-x")   # its savevm's reload (no continuity here) is no HMP load of another state: nothing dropped
        hows += [sb.loadvm("s-scratch", paused=True)["how"], sb.loadvm("s-ck", paused=True)["how"]]
        sb._g, sb._halted = _FakeGuest(), True
        hows.append(sb.unpark("p-x")["how"])
        del sb.persist_parked
        xseq = [(c, a.get("name", a.get("command-line"))) for c, a in calls
                if not c.startswith("query-") and c not in ("stop", "cont")]
        sb.st.update(checkpoints=False, incremental=False)
        sb.st.pop("checkpoints_held", None)
        sb.qmp = fake_qmp
        check("loadvm (Step X.32b's review): an HMP loadvm drops every checkpoint but the tag's own load, so after "
              "another tag's load a kept load or a parked start loads by loadvm, never over the other's disk",
              hows == ["loadvm", "checkpoint", "loadvm", "loadvm"] and xseq == [
                  ("human-monitor-command", "loadvm s-scratch"), ("xemu-checkpoint-save", "load-s-scratch"),
                  ("human-monitor-command", "savevm p-x"), ("human-monitor-command", "loadvm p-x"),
                  ("xemu-checkpoint-save", "p-x"), ("xemu-checkpoint-restore", "load-s-scratch"),
                  ("xemu-checkpoint-delete", "load-s-scratch"), ("xemu-checkpoint-delete", "p-x"),
                  ("human-monitor-command", "loadvm s-ck"), ("xemu-checkpoint-save", "load-s-ck"),
                  ("xemu-checkpoint-delete", "load-s-ck"), ("human-monitor-command", "loadvm p-x")],
              f"{hows} {xseq}")
        # Step X.32b: Sandbox.replay through the fork's PC hooks (deterministic v0.15, a light observation): the pad
        # queue at the update entry (tick 0's written at the halt), the camera queue at 0x85276, the observation
        # collected at the RETs by address expressions read back as obs.read reads them; the run ends at the entry
        # after the last tick (stop-empty), at a load (run-until's LOAD_LEVEL) or on a stall; a diverge stop it ran
        # past runs again from the start's checkpoint to the entry after the first tick off; a tick whose camera hit
        # went missing falls back to the gdbstub replay from the start
        class World(_FakeGuest):   # the player: each tick the pad's lx moves the body 1 m along x
            def __init__(self, load_at=None, skip_cam=None, stall_at=None):
                super().__init__()
                self.mem[0x600000] = bytearray(0x100)
                self.mem[self.esp] += bytes(0x30)   # the input builder's stack local at [esp+0x14] too
                self.mem[l3.MAIN_RATE] = bytearray(struct.pack("<d", 30.0))
                self.eip, self.t, self.hooks, self.next, self.cks, self.sent = l3.PLAYER_UPDATE, 0, {}, 1, {}, []
                self.load_at, self.skip_cam, self.stall_at, self.want = load_at, skip_cam, stall_at, []
                struct.pack_into("<d", self.mem[self.ent], 0x18, 10.0)

            def regs(self):
                return {**super().regs(), "ecx": self.ent, "ebp": self.ent, "esp": self.esp}

            def snap(self):
                return {k: bytes(v) for k, v in self.mem.items()}, self.t

            def qmp(self, cmd, **a):
                self.sent.append(cmd)
                if cmd == "query-block":
                    return {"return": [{"device": CD, "inserted": {"file": f"{w}/dvd.iso"}}]}
                if cmd == "xemu-checkpoint-save":
                    self.cks[a["name"]] = self.snap()
                elif cmd == "xemu-checkpoint-restore":
                    mem, self.t = self.cks[a["name"]]
                    for k, v in mem.items():
                        self.mem[k][:] = v
                    self.eip = l3.PLAYER_UPDATE
                elif cmd == "xemu-checkpoint-delete":
                    self.cks.pop(a["name"], None)
                elif cmd == "xemu-hooks-set":
                    ids = list(range(self.next, self.next + len(a["hooks"])))
                    self.hooks.update({i: {**h, "queue": list(h.get("set", []))} for i, h in zip(ids, a["hooks"])})
                    self.next += len(ids)
                    return {"return": [{"id": i} for i in ids]}
                elif cmd == "xemu-hooks-clear":
                    for i in a["ids"]:
                        self.hooks.pop(i)
                elif cmd in ("xemu-frame-advance", "xemu-run-until"):
                    return self.run(cmd == "xemu-run-until", a["frames"])
                return {"return": {}}

            def run(self, until: bool, frames: int) -> dict:
                pad, cam, ret = (next((i, h) for i, h in self.hooks.items() if h["pcs"][0] == pc)
                                 for pc in (l3.PLAYER_UPDATE, l3.CAMERA_DIR, l3.UPDATE_RETS[0]))
                u32, recs = (lambda va: self.u32(va)), []
                for _ in range(frames // 2):
                    if self.t == self.stall_at:
                        break
                    if self.t >= 1:   # the entry: the pad's next entry, or stop-empty before it
                        if not pad[1]["queue"]:
                            return {"return": {**({"reason": "empty"} if until else {}), "frame": self.t,
                                               "hooks": {"records": recs, "dropped": 0,
                                                         "stop": {"hook": pad[0], "empty": True}}}}
                        self.write(_hook_expr(pad[1]["write"][0]["addr"], self.regs(), u32),
                                   bytes.fromhex(pad[1]["queue"].pop(0)))
                    at = _hook_expr(cam[1]["collect"][0]["addr"], self.regs(), u32)
                    if self.t != self.skip_cam:
                        recs.append({"hook": cam[0], "data": [self.read(at, 8).hex()]})
                        if cam[1].get("queue") and (c := cam[1]["queue"].pop(0)):
                            self.write(at, bytes.fromhex(c))
                    body = self.mem[0x500000]
                    x = struct.unpack_from("<f", body, 0x15C)[0] + struct.unpack_from("<f", self.mem[CONTROLLER_STATE],
                                                                                    0x54)[0]
                    struct.pack_into("<f", body, 0x15C, x)
                    struct.pack_into("<d", self.mem[self.ent], 0x18, 10.0 + (self.t + 1) / 30)
                    recs.append({"hook": ret[0], "data": [self.read(_hook_expr(c["addr"], self.regs(), u32), c["size"]).hex()
                                                          for c in ret[1]["collect"]]})
                    self.want.append(obs.read(self.read, self.ent, self.read(at, 8) if self.t != self.skip_cam else None,
                                              deep=False))
                    self.t += 1
                    if until and self.t == self.load_at:
                        return {"return": {"reason": "hit", "pc": LOAD_LEVEL, "frame": self.t,
                                           "hooks": {"records": recs, "dropped": 0}}}
                return {"return": {**({"reason": "budget"} if until else {}), "frame": self.t,
                                   "hooks": {"records": recs, "dropped": 0}}}

        class HookBox(Sandbox):
            world: World

            @property
            def g(self):
                if self._g is None:
                    self._g, self._halted = self.world, True
                return self._g

        def hook_replay(world: World, stops=None, diverge_at=None):
            hb = HookBox("st")
            hb.world, hb.qmp = world, world.qmp
            hb.w, hb._owner = w, False
            hb.st = {"W": str(w), "hooks": True, "checkpoints": True, "deterministic": True, "pid": 7, "events": []}
            ent, cams = world.ent, [l3.camera_dir(0.1 * k) for k in range(5)]
            meta = {"label": "hk", "at": "update", "entity": ent, "clock": 10.0,
                    "start_sha12": start_hash(world.read, ent)}
            pads = [l3.Pad(stick=(1.0 if k != 3 else 0.5, 0.0)) for k in range(5)]
            rows = [l3.Row(k, (float(k + 1) + (5.0 if k == diverge_at else 0.0), 0.0, 0.0), 0, 318, None,
                           ((CONTROLLER_STATE + 0x54, b""),), cams[k]) for k in range(5)]
            return hb.replay(pads, rows, meta, deep=False, stops=stops), hb, world
        got, hb, wd = hook_replay(World())
        sent_plain, events_plain = list(wd.sent), list(hb.st["events"])
        left_cks = list(wd.cks)   # the start's checkpoint deleted
        st_div: dict = {"diverge": 0.5}
        got_div, _, wdv = hook_replay(World(), st_div, diverge_at=1)
        st_load: dict = {}
        got_load, _, wdl = hook_replay(World(load_at=3), st_load)
        fb = HookBox("st")
        fbw = World(skip_cam=2)
        fb.world, fb.qmp, fb.w, fb._owner = fbw, fbw.qmp, w, False
        fb.st = {"W": str(w), "hooks": True, "checkpoints": True, "deterministic": True, "pid": 7, "events": []}
        fb_meta = {"label": "hk", "at": "update", "entity": fbw.ent, "clock": 10.0,
                   "start_sha12": start_hash(fbw.read, fbw.ent)}
        fb_rows = [l3.Row(k, (float(k + 1), 0.0, 0.0), 0, 0, None, (), l3.camera_dir(0.0)) for k in range(5)]
        fell = fb._replay_by_hooks([l3.Pad(stick=(1.0, 0.0))] * 5, fb_rows, fb_meta, 5.0, None, 10.0, 30.0)

        class GdbGone(World):   # the gdbstub fails as the run starts, its hooks already in
            def cmd(self, p):
                if self.hooks:
                    raise OSError("the gdbstub went away")
                return super().cmd(p)
        gone_err = _err(hook_replay, gone := GdbGone())
        check("replay by PC hooks (Step X.32b): the pad and camera queues and the observation's regions; it ends at "
              "the entry after the last tick, at a load or at the entry after the first tick off (again from the "
              "start's checkpoint), each tick's observation obs.read's own; a missed camera hit falls back to the "
              "start for the gdbstub; a gdbstub that fails once the hooks are in leaves none (their stop-empty "
              "would end a later advance)",
              [x["k"] for x in got] == list(range(5)) and [x["obs"] for x in got] == wd.want
              and [x["pos"][0] for x in got] == [1.0, 2.0, 3.0, 3.5, 4.5]
              and sent_plain == ["query-block", "xemu-checkpoint-save", "xemu-hooks-set", "xemu-frame-advance",
                                 "xemu-hooks-clear", "xemu-checkpoint-delete"]
              and left_cks == [] and wd.t == 5 and any("replay by PC hooks: 5 ticks" in e for e in events_plain)
              and len(got_div) == 2 and st_div == {"diverge": 0.5, "at": "diverged", "k": 2} and wdv.t == 2
              and "xemu-checkpoint-restore" in wdv.sent and [x["obs"] for x in got_div] == wdv.want[:2]
              and len(got_load) == 3 and st_load == {"at": "load", "k": 3, "level": "levels/water/w1"}
              and "xemu-run-until" in wdl.sent and fell is None and fbw.t == 0 and fbw.hooks == {}
              and any("tick 2 took 0 camera entries" in e for e in fb.st["events"])
              and isinstance(gone_err, OSError) and gone.hooks == {} and gone.cks == {},
              f"{[x['pos'][0] for x in got]} {sent_plain} {st_div} {st_load} {wdl.sent[-4:]} {fb.st['events'][-2:]}")

        class Misses(World):   # AZ-821: xemu's dirty log missed a page; AZ-703: the restore lands off its start
            def __init__(self, n):
                super().__init__(skip_cam=2)   # the camera hit missed: back to the start for the gdbstub
                self.n, self.asked = n, []

            def qmp(self, cmd, **a):
                r = super().qmp(cmd, **a)
                if cmd == "xemu-checkpoint-restore":
                    self.asked.append((a.get("incremental"), a.get("verify")))
                    if self.n:
                        self.n, self.eip = self.n - 1, 0x12345
                    r = {"return": {"pages-copied": 3, "pages-missed": 1}}
                return r
        missed = {}
        for n in (0, 1):
            mb, mw = HookBox("st"), Misses(n)
            mb.world, mb.qmp, mb.w, mb._owner = mw, mw.qmp, w, False
            mb.st = {"W": str(w), "hooks": True, "checkpoints": True, "deterministic": True, "incremental": True,
                     "pid": 7, "events": []}
            m_meta = {**fb_meta, "entity": mw.ent, "start_sha12": start_hash(mw.read, mw.ent)}
            e = _err(mb._replay_by_hooks, [l3.Pad(stick=(1.0, 0.0))] * 5, fb_rows, m_meta, 5.0, None, 10.0, 30.0)
            missed[n] = (type(e).__name__, mw.asked, mw.eip == l3.PLAYER_UPDATE,
                         any("AZ-821" in x and "1 page(s) xemu's dirty log missed" in x for x in mb.st["events"]))
        check("checkpoint restore (AZ-821): every incremental restore compares every page too (verify), the pages "
              "xemu's dirty log missed named in an event, and the replay goes on from its start; a restore that "
              "still misses the start stops it (AZ-703)",
              missed == {0: ("NoneType", [(True, True)], True, True), 1: ("SystemExit", [(True, True)], False, True)},
              f"{missed}")
        # Step X.94 (AZ-822): each verified restore's pages-missed is counted for down and the kit's report; a nonzero is
        # an event, on a build with the fork's fix (DIRTY_LOG_FIX_MARK) a warning naming a fork bug; an unverified
        # restore (no pages-missed in its reply: a build before v0.15) isn't counted. Step X.96: that nonzero drafts the
        # fork's request at once, with the build, the checkpoint, the counts and the calls since its save
        pm_replies = iter([0, 0, 3, None])

        def pm_qmp(cmd: str, **a) -> dict:
            pm._note_call(cmd, a)   # the real qmp's first line
            if cmd == "xemu-checkpoint-restore":
                n = next(pm_replies)
                return {"return": {"pages-copied": 5, **({"pages-missed": n} if n is not None else {})}}
            if cmd == "query-block":
                return {"return": [{"device": CD, "inserted": {"file": f"{w}/dvd.iso"}}]}
            return {"return": {"loads": 0} if cmd == XEMU_STATUS else {}}
        pm = Sandbox("pm")
        pm.w, pm._owner, pm.qmp = w, False, pm_qmp
        pm.st = {"W": str(w), "pid": 7, "incremental": True, "dirty_log_fix": True, "xemu_status": True, "events": [],
                 "checkpoints_held": {"pid": 7, "names": {"c": {"disc": "dvd.iso"}}}, "app": str(tmp / "no.app")}
        pm_g = pm._g = RSP.__new__(RSP)   # a gdbstub that counts its writes, no socket
        class NoSock:
            def close(self):
                pass

            def sendall(self, _b):
                pass
        pm_g.cmd, pm_g.s = (lambda _p: b"OK"), NoSock()
        pm_got = []
        for i in range(4):
            if i == 2:   # the run since the save: a write, an advance (its _let_go drops the client first), the same
                # client attached again (wait_bp's reconnect: its earlier write not counted twice), two pad writes,
                # another; a query isn't a call; then a write, a release, a new client (Sandbox.g's after it) that no
                # call sees, a write on it and an advance whose _let_go drops it: both clients' writes, one entry
                pm_qmp("xemu-checkpoint-save", name="c")
                pm_g.writes += 1
                pm.st["debug_advance"], pm._halted = True, True
                pm._let_go()
                pm_qmp("xemu-frame-advance", frames=300, **{"timeout-ms": 420000})
                pm._g, pm._halted = pm_g, True
                pm._g.writes += 2
                pm_qmp("query-status")
                pm_qmp("human-monitor-command", **{"command-line": "savevm p-c"})
                pm_g.writes += 1
                pm.release()
                pm_g2 = pm._g = RSP.__new__(RSP)
                pm_g2.cmd, pm_g2.s, pm._halted = (lambda _p: b"OK"), NoSock(), True
                pm_g2.write(0x10000, bytes(4))
                pm._let_go()
                pm_qmp("xemu-frame-advance", frames=60)
            pm_got.append(pm.checkpoint_restore("c").get("pages-missed"))
        req = sorted((FORK_REQUESTS / f"xemu-fork-requests-{time.strftime('%Y-%m-%d')}").glob("PAGES-MISSED-*.txt"))
        req_text = req[0].read_text(encoding="utf-8") if req else ""
        req_seq = [ln.split(". ", 1)[1] for ln in req_text.splitlines() if re.match(r"\s+\d+\. ", ln)]
        pm_res: dict = {}
        pm.cpuid_faults = pm.bugchecks = lambda every_launch=False: []
        pm._log_items = lambda parse, every_launch: []
        pm._log_findings(pm_res)
        check("pages missed (Step X.94, AZ-822): every verified restore is counted with the pages xemu's dirty log "
              "missed, down's result keeps the count, and a nonzero on a build with the fork's fix is a warning naming "
              "a fork bug; an unverified restore isn't counted",
              pm_got == [0, 0, 3, None] and pm.st["restores"]["verified"] == 3 and pm.st["restores"]["pages_missed"] == 3
              and [(x["name"], x["pages"]) for x in pm.st["restores"]["missed"]] == [("c", 3)]
              and pm_res.get("restores") == pm.st["restores"]
              and sum("3 page(s) xemu's dirty log missed" in e and "a fork bug, its request drafted in" in e
                      for e in pm.st["events"]) == 1,
              f"{pm_got} {pm.st.get('restores')} {pm.st['events']}")
        check("the standing rule (Step X.96): a restore that missed pages on a build with AZ-822's fix drafts the fork's "
              "request at once, in the day's fork-requests folder, named in the restores' record: the counts and the "
              "calls since the checkpoint's save (queries left out, the gdbstub's writes counted, a client's no call "
              "saw too, those between two calls one entry), no data",
              len(req) == 1 and pm.st["restores"].get("requests") == [str(req[0])]
              and "pages-missed 3, pages-copied 5" in req_text and "verified restores: 3, pages missed in all 3" in req_text
              and req_seq == ["xemu-checkpoint-save name=c", "gdbstub memory writes n=1",
                              "xemu-frame-advance frames=300 timeout-ms=420000", "gdbstub memory writes n=2",
                              "hmp savevm p-c", "gdbstub memory writes n=2", "xemu-frame-advance frames=60",
                              "xemu-checkpoint-restore name=c incremental=True verify=True -> pages-missed 3"],
              f"{req} {req_seq}")
        vk = {mode: Sandbox("st", headless=mode, deterministic=True) for mode in ("1", "null")}
        for box in vk.values():
            box.w, box._owner, box.st = w, False, {"W": str(w), "pid": 7, "deterministic": True, "events": []}
            for what in ("loadvm a", "checkpoint b", "loadvm c"):
                box._load_drops_input(what)
            box.st["pid"] = 8   # a relaunch: its first load again
            box._load_drops_input("loadvm d")
        warned = {m: [e.split(" ", 1)[1].split(" in this")[0] for e in box.st["events"]] for m, box in vk.items()}
        fixed = Sandbox("st", headless="1", deterministic=True)
        fixed.w, fixed._owner = w, False
        fixed.st = {"W": str(w), "pid": 7, "deterministic": True, "load_fix": True, "events": []}
        for what in ("loadvm a", "checkpoint b", "loadvm c"):
            fixed._load_drops_input(what)
        check("D200's guard: on a build before v0.15's load fix, in a deterministic offscreen Vulkan process each "
              "load after its first is warned by name, a relaunch's first isn't, and the null renderer never is "
              "(Step X.31a); on v0.15 (its XEMU_LOAD_VERIFY mark: seven such loads on one RAM, x32 and x40) none is "
              "(Step X.32b)",
              warned == {"1": ["D200: checkpoint b is load 2", "D200: loadvm c is load 3"], "null": []}
              and fixed.st["events"] == [] and fixed.st["loads_in_process"] == 3, f"{warned} {fixed.st['events']}")
        dg, digs = Sandbox("st"), []
        dg.w, dg._owner, dg._halted = w, False, True
        dg.st = {"W": str(w), "ram_digest": True}
        dg.qmp = lambda cmd, **a: digs.append((cmd, a)) or {"return": {"xxh3-128": "ab" * 16}}
        got_digest = dg.ram_digest()
        dg.st["ram_digest"] = False
        check("ram_digest (Step X.32b): xemu's own XXH3-128 of guest RAM; a build without it refuses",
              got_digest == "ab" * 16 and digs == [("xemu-ram-digest", {"algorithm": "xxh3-128"})]
              and isinstance(_err(dg.ram_digest), SystemExit), f"{got_digest} {digs}")
        # Step X.58: Sandbox.watch over v0.16's xemu-watch-*: VAs and writes by default, the fork's limits refused,
        # drains kept, the log stopped at the block's end; a build without it refuses
        wq: list = []
        hit = {"frame": 3, "pc": 0xAB8A1, "address": 0x481C78, "physical": 0x1C81C78, "size": 4, "access": "w"}
        dg.st.update(watch=True, events=[])
        dg.qmp = lambda cmd, **a: wq.append((cmd, a)) or {"return": {} if cmd == WATCH_START else {
            "hits": [hit] * (2 if cmd == "xemu-watch-drain" else 1), "dropped": 1 if cmd == "xemu-watch-stop" else 0}}
        with dg.watch([(0x481C78, 8), {"address": 0x1C81C00, "size": 0x40, "access": "rw", "virtual": False}],
                      max_hits=500) as wt:
            drained = wt.drain()
        bad = [_err(watch_ranges, r) for r in ([], [(0, 0)], [(0xFFFFFFFF, 2)], [(0, WATCH_SIZE + 1)], [(0, 4, "x")],
                                                [{"address": 0, "size": 4, "acess": "w"}], [(0, 1)] * 65)]
        dg.qmp = lambda cmd, **a: {"return": {}} if cmd == WATCH_START else {"error": {"desc": "no access log"}}

        wr = dg.watch([(0x481C78, 8)])

        def _relaunched_block():   # a relaunch inside the block: the new xemu refuses the stop
            with wr:
                raise BootFailed("the block's own")
        block_err = _err(_relaunched_block)
        refused_stop = _err(wr.stop)
        dg.st["watch"] = False
        check("watch (Step X.58): xemu-watch-start on the game's VAs, writes by default (a physical rw range too), "
              "drains kept and the log stopped at the block's end; out-of-range sizes, addresses, accesses, keys and "
              "counts refused; a build without it refuses; a stop xemu refuses never hides the block's own error "
              "and stays retryable",
              [c for c, _ in wq] == [WATCH_START, "xemu-watch-drain", "xemu-watch-stop"]
              and isinstance(block_err, BootFailed) and isinstance(refused_stop, SystemExit) and wr.running
              and wq[0][1] == {"ranges": [{"address": 0x481C78, "size": 8, "access": "w", "virtual": True},
                                          {"address": 0x1C81C00, "size": 0x40, "access": "rw", "virtual": False}],
                               "max": 500}
              and len(drained) == 2 and len(wt.hits) == 3 and wt.dropped == 1 and not wt.running
              and all(isinstance(e, ValueError) for e in bad) and isinstance(_err(dg.watch, [(0, 4)]), SystemExit),
              f"{wq} {bad}")
        tray["status"], sb.st["deterministic"], sb.qmp = "paused", True, loading_qmp
        paused_shot = sb.screenshot("frame-d").exists()
        tray["status"] = "running"
        running_refused = refused(sb.screenshot, "frame-e")
        sb.st.pop("deterministic")
        sb.qmp = fake_qmp
        check("a deterministic offscreen picture is taken paused: a running guest's is refused (Step X.26)",
              paused_shot and running_refused)
        sb.st["hdd"] = str(tmp / "private.qcow2")
        check("tags: vanilla-rzp-* loads on a private drive (Q250)", sb.loadable("vanilla-rzp-keys5-w1"))
        # Step X.9: boot_build's supervisor. Each failure of a boot try (a dead
        # pad AZ-296, a Continue that never runs AZ-302, the boot hang V22) is
        # an incident that quits and relaunches xemu on its W before the next
        # try; every try failing stops the boot; a booted build's state is saved
        # in the sandbox and the same build boots again by one loadvm with its
        # disc in the tray. The menu walk waits on the boot state, and presses A
        # again when the save list didn't take it.
        steps: list[str] = []
        sb.sc.update(start=238, b=233, dpad_right=247)
        g = _FakeGuest()

        def press(fifo, sc, wait):   # noqa: F811  (the FIFO's stand-in: START opens the save list, A loads it)
            steps.append(f"press {sc}")
            if sc == 238 and g.u32(BOOT_STATE) == MENU:
                if g.start_ignored:
                    g.start_ignored -= 1
                else:
                    g.write(BOOT_STATE, struct.pack("<I", 8))
                    g.menu = [INV_RESET, INV_RESET]   # the list previews SaveGame #1 (its burst of two calls)
            elif sc == sb.sc["a"]:
                if g.a_ignored:
                    g.a_ignored -= 1
                else:
                    g.a_on_save()
            elif sc == 247 and g.u32(BOOT_STATE) == 8:
                if g.cursor_lost:
                    g.cursor_lost -= 1   # the list still reads the HDD: the move is dropped
                else:
                    g.cursor = min(g.cursor + 1, len(g.saves) - 1)
                    g.menu = [INV_RESET, INV_RESET]   # it previews the save it moved to

        def fresh(**flags):   # a new launch: a new guest at the title
            nonlocal g
            g = _FakeGuest()
            for k, v in flags.items():
                setattr(g, k, v)
            sb._g, sb._halted = g, True
        sb.loadvm = lambda tag, **kw: steps.append(f"loadvm {tag}" + (f" on {kw['disc']}" if "disc" in kw else "")) \
            or ({"entity": hex(g.ent)} if tag.startswith("b-") else {})
        sb.reset_into = lambda name: steps.append(f"reset into {name}") or fresh(**{k: getattr(g, k) for k in (
            "dead_pad", "no_continue", "hang", "a_ignored", "cursor_lost")})
        sb._quit = lambda relaunch=False: steps.append("quit")
        sb.savevm = lambda tag: steps.append(f"savevm {tag}")
        sb._xbe, sb.shim_data = (lambda name: b""), (lambda name="dvd.iso": [])
        sb.code_identity = lambda name="dvd.iso": {".text": [0x40, 0]}
        sb.st.update(launches=1, events=[])
        (tmp / "build.iso").write_bytes(b"")
        sha12 = hashlib.sha256(b"").hexdigest()[:12]
        sleep, time.sleep, steady, steady_wait = time.sleep, (lambda s: None), STEADY_S, STEADY_WAIT_S
        STEADY_S, STEADY_WAIT_S = 0.05, 0.2   # 3 player ticks of the fake's event clock; the polls' 4 minutes
        try:
            got = {}
            for flag in ("dead_pad", "no_continue", "hang"):
                steps.clear()
                fresh()
                sb.relaunch = lambda: steps.append("relaunch")   # the next reset gets a guest without the flag
                setattr(g, flag, True)
                sb.reset_into = lambda name, flag=flag: steps.append(f"reset into {name}") or fresh(
                    **({flag: True} if "relaunch" not in steps else {}))
                sb.st.pop("warm", None)
                r = sb.boot_build(tmp / "build.iso", "vanilla-ig-w1")
                got[flag] = ([i["class"] for i in r["incidents"]], r["tries"],
                             steps[steps.index("quit"):steps.index("quit") + 3] if "quit" in steps else steps)
            check("boot-build: a dead pad, a Continue that never runs and the boot hang each relaunch xemu before "
                  "the next try, recorded as incidents",
                  got == {"dead_pad": (["dead_pad"], 2, ["quit", "relaunch", "loadvm vanilla-ig-w1 on dvd.iso"]),
                          "no_continue": (["no_continue"], 2, ["quit", "relaunch", "loadvm vanilla-ig-w1 on dvd.iso"]),
                          "hang": (["boot_hang"], 2, ["quit", "relaunch", "loadvm vanilla-ig-w1 on dvd.iso"])}, f"{got}")
            first = steps[steps.index("relaunch") + 1:]
            check("boot-build: the walk presses START once the title is up and A once the save list is, and the "
                  "booted build's state is saved in the sandbox",
                  first[:2] == ["loadvm vanilla-ig-w1 on dvd.iso", f"reset into b-{sha12}.iso"]
                  and first[-3:] == ["press 238", "press 232", f"savevm b-{sha12}-vanilla-ig-w1"]
                  and last_walk["tries"][0]["states"] == [MENU, 8] and last_walk["tries"][0]["preview_s"] is not None,
                  f"{first[-4:]} {last_walk}")
            steps.clear()
            r = sb.boot_build(tmp / "build.iso", "vanilla-ig-w1")
            check("boot-build: the same build boots again warm, by one loadvm with its disc in the tray",
                  r["warm"] and r["tries"] == 0 and steps == [f"loadvm b-{sha12}-vanilla-ig-w1 on b-{sha12}.iso"],
                  f"{steps}")
            # Step X.81d: a sitting's warm store. Only a sandbox whose RAM is null's publishes a cold boot (a plain
            # offscreen one's state would start the sitting's null rows from offscreen RAM); a savevm that failed
            # keeps nothing warm and publishes nothing; a shared state this xemu won't load is booted cold
            # (incident warm_load) and published again in its place
            made_hdd = not (w / xemu_warm.HDD).exists()
            if made_hdd:
                (w / xemu_warm.HDD).write_bytes(b"drive")
            store = xemu_warm.WarmStore(tmp / "warm", {"sitting": "selftest"})
            stub_loadvm, stub_savevm, saves, saved0 = sb.loadvm, sb.savevm, [""], sb.st.get("saved_tags", [])
            sb.st["warm_store"] = {"dir": str(store.dir), "key": store.key, "publish": False}
            sb.savevm = lambda tag: steps.append(f"savevm {tag}") or saves.pop(0)
            sb.reset_into = lambda name: steps.append(f"reset into {name}") or fresh()
            sb.alive = lambda: True
            wkey, pubs = f"b-{sha12}-vanilla-ig-w1", []
            try:
                for publish, out in ((False, ""), (True, "Error: no space left on device"), (True, "")):
                    sb.st["warm_store"]["publish"], saves[:] = publish, [out]
                    sb.st.pop("warm", None)
                    r = sb.boot_build(tmp / "build.iso", "vanilla-ig-w1")
                    pubs.append((r["warm"], r.get("warm_published"), wkey in sb.st.get("warm", {})))
                sb.st.update(warm={}, saved_tags=[])   # a fresh sandbox of the sitting: the store's state, refused
                saves[:] = [""]
                sb.loadvm = lambda tag, **kw: (_ for _ in ()).throw(SystemExit(f"loadvm {tag}: Error: Unknown section")) \
                    if tag == wkey else stub_loadvm(tag, **kw)
                r = sb.boot_build(tmp / "build.iso", "vanilla-ig-w1")
                refused_load = ([i["class"] for i in r["incidents"]], r["tries"], r.get("warm_published"),
                                sorted(json.loads((store.dir / xemu_warm.INDEX).read_text(encoding="utf-8"))["drives"]))
            finally:
                sb.loadvm, sb.savevm = stub_loadvm, stub_savevm
                del sb.alive
                sb.st.pop("warm_store")
                sb.st.pop("warm", None)
                sb.st.pop("warm_drive", None)
                sb.st["saved_tags"] = saved0
                if made_hdd:
                    (w / xemu_warm.HDD).unlink()
            check("warm store (Step X.81d): a null sandbox's cold boot is published, a plain offscreen one's and one "
                  "whose savevm failed aren't (the failed one kept no warm state); a shared state this xemu refuses "
                  "is booted cold (incident warm_load) and published in its place",
                  pubs == [(False, None, True), (False, None, False), (False, "drive-1.qcow2", True)]
                  and refused_load == (["warm_load"], 1, "drive-2.qcow2", ["drive-2.qcow2"]),
                  f"{pubs} {refused_load}")
            steps.clear()
            sb.reset_into = lambda name: steps.append(f"reset into {name}") or fresh(dead_pad=True)
            check("boot-build: a failure on every try stops the boot after its tries",
                  refused(lambda: sb.boot_build(tmp / "build.iso", "vanilla-ig-w1", warm=False))
                  and steps.count("relaunch") == BOOT_TRIES - 1, f"{steps.count('relaunch')}")
            steps.clear()
            sb.reset_into = lambda name: steps.append(f"reset into {name}") or fresh(a_ignored=1, start_ignored=1)
            r = sb.boot_build(tmp / "build.iso", "vanilla-ig-w1", warm=False)
            walked = [{k: t[k] for k in ("states", "presses", "level")} for t in last_walk["tries"]]
            check("menu walk: a START the title didn't take and an A the save list didn't take are pressed again, "
                  "not the route retried",
                  r["tries"] == 1 and steps.count("press 238") == 3
                  and walked == [{"states": [MENU, 8], "presses": 2, "level": "levels/water/w1"}], f"{walked} {steps}")
            steps.clear()
            sb.reset_into = lambda name: steps.append(f"reset into {name}") or fresh(cursor_lost=2)
            r = sb.boot_build(tmp / "build.iso", "vanilla-ig-new", save=2)
            t = last_walk["tries"][0]
            check("menu walk (AZ-354): a cursor move onto SaveGame #2 the list drops while it reads the HDD is pressed "
                  "again until the list previews #2 (the stops of #1's preview let pass), whose level loads; its warm "
                  "state names the save",
                  r["level"] == "levels/water/w2" and r["tries"] == 1 and steps.count("press 247") == 3
                  and [c[0] for c in t["cursor"]] == [3] and t["states"] == [MENU, 8, None]
                  and steps[-1] == f"savevm b-{sha12}-vanilla-ig-new-s2", f"{r.get('level')} {steps} {t}")
            alive = [True]
            sb.alive = lambda: alive[0]
            classes = []
            for e, up in ((DeadPad("x"), True), (MenuMiss("x"), True), (NoSteadyTick("x"), True),
                          (SystemExit("STOP: no slot"), False), (EOFError("gdbstub closed"), False),
                          (TimeoutError("timed out"), True), (SystemExit("the menu walk loaded 'a', not b"), True)):
                alive[0] = up
                classes.append(sb.failure_class(e))
            check("boot-build: failures are classified once; a relaunch can't cure a refusal or a wrong save",
                  classes == ["dead_pad", "menu_miss", "no_steady_tick", None, "xemu_died", "stalled", None],
                  f"{classes}")
            del sb.alive
            # AZ-305: e7's enemies hit the player while boot-build polls for
            # a steady tick (one boot died), so each tick the polls stop at
            # puts the HP back to the first one's
            e7 = _FakeGuest()
            real_interrupt = e7.interrupt

            def hit():   # the guest ran between polls: 60 HP gone after the first tick
                if e7.tick:
                    struct.pack_into("<i", e7.mem[0x500000], 0x210,
                                     struct.unpack_from("<i", e7.mem[0x500000], 0x210)[0] - 60)
                return real_interrupt()
            e7.interrupt = hit
            polls = to_player_tick(e7, w / "input.fifo", {"a": 232})
            check("boot-build: steady play is guest time at every poll, and the polls hold the player's HP at the "
                  "first polled tick's (e7's enemies, AZ-305)",
                  polls == 3 and struct.unpack_from("<ii", e7.mem[0x500000], 0x210) == (318, 400),
                  f"{polls} {struct.unpack_from('<ii', e7.mem[0x500000], 0x210)}")
            # AZ-628: a try that never finds a steady tick says where the guest was (its polls, the ticked ones,
            # the entities, the longest run and the last no-tick polls' EIPs), kept in the boot's incident
            steps.clear()
            sb.reset_into = lambda name: steps.append(f"reset into {name}") or fresh(dialog="relaunch" not in steps)
            r = sb.boot_build(tmp / "build.iso", "vanilla-ig-w1", warm=False)
            diag = (r["incidents"] or [{}])[0].get("diag") or {}
            check("boot-build (AZ-628): a try with no steady player tick keeps its polls, the ticked ones, the "
                  "entities, the longest steady run and the last 8 no-tick polls' EIPs in its incident",
                  [i["class"] for i in r["incidents"]] == ["no_steady_tick"] and r["tries"] == 2
                  and diag.get("ticked") == 2 and diag.get("entities") == 1 and diag.get("best_s") == 0.033
                  and diag.get("polls", 0) >= 10 and len(diag.get("no_tick_eips", ())) == NO_TICK_EIPS
                  and set(diag["no_tick_eips"]) == {"0xaf17a", "0xaf190"}
                  and "polls ticked" in r["incidents"][0]["detail"], f"{r['incidents']}")
            # Step X.58: a boot whose xemu logged a strict-CPUID fault stops by name at once (a relaunch can't cure
            # code the Pentium III lacks), and down keeps every launch's faults
            run_log = sb.w / "run.log"
            had = run_log.read_bytes() if run_log.exists() else None
            run_log.write_text("xemu: strict CPUID: #UD at 0001f000: 66 0F EF C0 needs SSE2\n", encoding="utf-8")
            (sb.w / "run.1.log").write_text("xemu: strict CPUID: #UD at 00012000: 66 0F EF C0 needs SSE2\n",
                                            encoding="utf-8")
            steps.clear()

            def faulting(name):   # the build's code faults during this boot (a line from before it doesn't count)
                steps.append(f"reset into {name}")
                with run_log.open("a", encoding="utf-8") as f:
                    f.write("xemu: strict CPUID: #UD at 0011a2b4: F2 0F 58 C1 needs SSE2\n")
                fresh(hang=True)
            sb.reset_into = faulting
            try:
                err = _err(sb.boot_build, tmp / "build.iso", "vanilla-ig-w1", warm=False)
                every = sb.cpuid_faults(every_launch=True)
            finally:
                (sb.w / "run.1.log").unlink()
                run_log.write_bytes(had) if had is not None else run_log.unlink()
            check("boot-build (Step X.58): a strict-CPUID fault in its xemu's run log stops the boot by name, untried "
                  "again, with no opcode bytes; every launch's run log is read for down",
                  isinstance(err, CpuidFault) and "relaunch" not in steps and str(err).endswith(": SSE2 at 0x11a2b4")
                  and "F2 0F" not in str(err) and [f["pc"] for f in every] == ["0x12000", "0x1f000", "0x11a2b4"],
                  f"{err!r} {every}")
            # Step X.61 (AZ-628): on a build with XEMU_GUEST_BUGCHECK a try ends at its next poll once the run log names
            # a bugcheck or dead halt it didn't hold when the try began (not after the polls' minutes), as class
            # "bugcheck" with them in its incident, and is retried; a line from before the try doesn't count
            had = run_log.read_bytes() if run_log.exists() else None
            run_log.write_text("xemu: guest halted with interrupts disabled at 0x800151ef (esp 0x8003a9f0)\n",
                               encoding="utf-8")
            steps.clear()

            def bugchecking(name):   # the first try's guest bugchecks after its reset, then holds its tick (a dialog)
                steps.append(f"reset into {name}")
                first = "relaunch" not in steps
                if first:
                    with run_log.open("a", encoding="utf-8") as f:
                        f.write("xemu: guest bugcheck 0x0000000a (0x7ffffff8, 0x00000002, 0x00000000, 0x0018d0fc) "
                                "from 0x0018d101\n")
                fresh(dialog=first)
            sb.reset_into, sb.st["bugcheck"] = bugchecking, True
            try:
                r = sb.boot_build(tmp / "build.iso", "vanilla-ig-w1", warm=False)
            finally:
                sb.st["bugcheck"] = False
                run_log.write_bytes(had) if had is not None else run_log.unlink()
            inc = (r["incidents"] or [{}])[0]
            check("boot-build (Step X.61, AZ-628): a guest bugcheck the try's run log gains ends the try at once as "
                  "'bugcheck' (not no_steady_tick), its items in the incident, and the boot is retried; one from before "
                  "the try doesn't count",
                  [i["class"] for i in r["incidents"]] == ["bugcheck"] and r["tries"] == 2
                  and [b.get("code") for b in inc.get("bugchecks", [])] == ["0xa"] and inc["bugchecks"][0]["v22"]
                  and "bugcheck 0xa" in inc["detail"] and "diag" not in inc, f"{r['incidents']}")
            # Step X.61: a no-tick poll halted in the kernel's halt loop reads KeBugCheckEx's five dwords into the diag
            hl = _FakeGuest()
            hl.dialog = True
            hl.mem[BUGCHECK_DATA] = bytearray(struct.pack("<5I", 0x1E, 0xC000001D, 0x8CCC0, 0, 0))
            hl.interrupt = lambda: (setattr(hl, "eip", HALT_LOOP), b"T02")[1]
            halted = _err(to_player_tick, hl, w / "input.fifo", {"a": 232})
            check("to_player_tick (Step X.61, AZ-628): a no-tick poll halted at the kernel's halt loop keeps the "
                  "bugcheck code and parameters KeBugCheckEx stored in its diag",
                  isinstance(halted, NoSteadyTick) and halted.diag.get("bugcheck_data") == [
                      "0x1e", "0xc000001d", "0x8ccc0", "0x0", "0x0"] and "0x800151ef" in halted.diag["no_tick_eips"],
                  f"{getattr(halted, 'diag', halted)}")
            # Step X.58: each boot keeps its host-time counters' difference (query-xemu-host-profile), or the new
            # xemu's own after a relaunch; a build without them keeps none
            asked, plain_qmp = [], sb.qmp
            counters = {"translate-ns": 2_000_000_000, "translations": 900, "apu-ns": 0, "apu-ticks": 0,
                        "idle-ns": 5_000_000_000, "idle-warps": 40}

            def profiled(cmd, **a):
                if cmd != HOST_PROFILE:
                    return plain_qmp(cmd, **a)
                asked.append(cmd)
                return {"return": {k: v * len(asked) for k, v in counters.items()}}
            sb.qmp, sb.st["host_profile"] = profiled, True
            sb.reset_into = lambda name: steps.append(f"reset into {name}") or fresh()
            try:
                r = sb.boot_build(tmp / "build.iso", "vanilla-ig-w1", warm=False)
            finally:
                sb.qmp, sb.st["host_profile"] = plain_qmp, False
            relaunched = host_delta({"launch": 1, "translate-ns": 5 * 10**9},
                                    {"launch": 2, "translate-ns": 7 * 10**9, "apu-ns": 0})
            check("boot-build (Step X.58): a boot keeps its host-time counters' difference (seconds, counts); after a "
                  "relaunch the new xemu's own",
                  r.get("host_profile") == {"since": "boot", "translate_s": 2.0, "translations": 900, "apu_s": 0.0,
                                            "apu_ticks": 0, "idle_s": 5.0, "idle_warps": 40}
                  and len(asked) == 2 and relaunched == {"since": "launch", "translate_s": 7.0, "apu_s": 0.0}
                  and "host_profile" not in sb.boot_build(tmp / "build.iso", "vanilla-ig-w1", warm=False),
                  f"{r.get('host_profile')} {relaunched}")
        finally:
            time.sleep, STEADY_S, STEADY_WAIT_S = sleep, steady, steady_wait
            for k in ("loadvm", "reset_into", "_quit", "savevm", "_xbe", "shim_data", "code_identity", "relaunch"):
                vars(sb).pop(k, None)
        # Step X.64 (AZ-675; AZ-628's flake): a deterministic sandbox boots on guest frames: each press queued at its
        # frame from the reset in the xemu-run that reaches it, each wait a budget of vblanks, so a build boots the same
        # way from any reset (a process's first boot or its second); A on the list at A_FRAME, each retry A_RETRY later

        class FrameBox(Sandbox):
            world: _FrameGuest

            @property
            def g(self):
                if self._g is None:
                    self._g, self._halted = self.world, True
                return self._g

        def frame_boot(*worlds: _FrameGuest, **kw):
            """``boot_build`` on frames at f6, each try's reset into the next of ``worlds`` (a relaunch's guest)."""
            fb, todo = FrameBox("st"), list(worlds)
            fb.w, fb._owner, fb.world = w, False, worlds[0]
            fb.sc = {"a": 232, "b": 233, "start": 238, "dpad_right": 247}
            fb.st = {"W": str(w), "pid": 7, "deterministic": True, "xemu_run": True, "debug_advance": True,
                     "bugcheck": True, "launches": 1, "events": []}

            def reset(name, cont=True):
                fb.world, fb._g = todo.pop(0), None
            fb.qmp = lambda cmd, **a: fb.world.qmp(cmd, **a)
            fb.loadvm, fb.reset_into, fb._save = (lambda tag, **_: {}), reset, (lambda: None)
            fb._quit, fb.relaunch = (lambda relaunch=False: None), (lambda: None)
            fb._xbe, fb.shim_data = (lambda name: b""), (lambda name="dvd.iso": [])
            fb.code_identity = lambda name="dvd.iso": {".text": [0x40, 0]}
            return fb.boot_build(tmp / "build.iso", "vanilla-ig-f6", warm=False, **kw)
        run_log = w / "run.log"
        had = run_log.read_bytes() if run_log.exists() else None
        run_log.write_text("", encoding="utf-8")
        try:
            first, second = _FrameGuest(f0=5000, dialog=True), _FrameGuest(f0=91234, dialog=True)
            r1, r2 = frame_boot(first), frame_boot(second)
            sched = [{k: v for k, v in r["frames"].items() if k != "reset"} for r in (r1, r2)]
            check("boot-build on guest frames (Step X.64, AZ-675): each press goes in the run that reaches it at its "
                  "frame from the reset (START a frame into the movie, a frame after the title is up held PRESS_HOLD, "
                  "A at A_FRAME held A_HOLD frames, A at a poll the player tick didn't run), halted at the steady "
                  "tick; the same schedule from another reset frame",
                  sched[0] == sched[1] and r1["level"] == "levels/water/w1" and r1["tries"] == 1
                  and first.got[:6] == [f"@{5000 + 1351} down 238", f"@{5000 + 1351 + SKIP_HOLD} up 238",
                                        f"@{5000 + 1432} down 238", f"@{5000 + 1432 + PRESS_HOLD} up 238",
                                        f"@{5000 + A_FRAME} down 232", f"@{5000 + A_FRAME + A_HOLD} up 232"]
                  and [p[0] for p in r1["frames"]["presses"]] == ["start", "start", "a", "a"]
                  and r1["frames"]["a"] == A_FRAME and first.eip == PLAYER_TICK and r1["entity"] == hex(first.ent),
                  f"{sched} {first.got[:6]}")
            r = frame_boot(_FrameGuest(f0=40, cursor_lost=2), save=2)
            check("boot-build on guest frames (AZ-354): a move onto SaveGame #2 the list drops is pressed again every "
                  "CURSOR_S until the list previews #2 (#1's burst let pass first), then A",
                  r["level"] == "levels/water/w2" and [p[0] for p in r["frames"]["presses"]].count("dpad_right") == 3
                  and r["frames"]["presses"][-1][0] == "a", f"{r['frames']}")
            r = frame_boot(_FrameGuest(f0=100, run_log=run_log, race=A_FRAME),
                           _FrameGuest(f0=300000, run_log=run_log, race=A_FRAME))
            err = _err(frame_boot, _FrameGuest(f0=7, run_log=run_log, race=1459), a_frame=1459, tries=1)
            check("boot-build on guest frames (AZ-695): a try whose A frame bugchecks the guest ends at once, its "
                  "schedule so far in its incident, and the retry presses A A_RETRY frames later; a_frame presses a "
                  "given frame (tries=1: the race's)",
                  [i["class"] for i in r["incidents"]] == ["bugcheck"] and r["tries"] == 2
                  and r["incidents"][0].get("frames", {}).get("a") == A_FRAME
                  and r["frames"]["a"] == A_FRAME + A_RETRY and isinstance(err, BootFailed) and "0xaf173" in str(err),
                  f"{r['incidents']} {r['frames'].get('a')} {err!r}")
        finally:
            run_log.write_bytes(had) if had is not None else run_log.unlink()
        check("usb_ready: a pad behind the hub is ready; the hub alone isn't",
              usb_ready("  Device 0.1, Port 1, Speed 12 Mb/s, Product USB Hub\n"
                        "  Device 0.2, Port 1.2, Speed 12 Mb/s, Product Microsoft Gamepad")
              and not usb_ready("  Device 0.1, Port 1, Speed 12 Mb/s, Product USB Hub"))
        # Step X.8: that relaunch keeps the slot W still holds (no queue, no
        # admission test), and takes a reclaimed one like a new sandbox; AZ-301:
        # through the CLI it waits as long as boot-build's --wait says
        # either way (sitting sight222's waited 11.2 min, past attach's 240 s)
        waits: list[tuple[float, bool]] = []

        def no_slot(w_: Path, wait_s: float, keep: bool = False, demo: bool = False, window: bool = False) -> int:
            waits.append((wait_s, keep))
            raise SystemExit(f"STOP: no slot (selftest); waited {wait_s:.0f} s and started nothing")
        dead = _FakeGuest()
        dead.dead_pad = True
        stand_ins = {"_xbe": lambda self, name: b"", "shim_data": lambda self, name="dvd.iso": [],
                     "loadvm": lambda self, tag, **_: None, "reset_into": lambda self, name: None,
                     "_quit": lambda self, relaunch=False: {}, "halt": lambda self: dead}
        real_methods = {k: getattr(Sandbox, k) for k in stand_ins}
        (tmp / "build.iso").write_bytes(b"")
        take_slot, stopped = no_slot, []
        for k, v in stand_ins.items():
            setattr(Sandbox, k, v)
        try:
            for held_slot in (True, False):
                (w / "sandbox.json").write_text(json.dumps(   # as `up` left it (sb's saves wrote over it)
                    {"W": str(w), "group": "st", "app": str(KEPT_APP), "disc": str(fx / "vanilla.iso"),
                     "out": None, "hdd": None, "fixtures": str(fx), "launches": 1}), encoding="utf-8")
                _write_slot(w, {"pid": 101}) if held_slot else _drop_slot(w)
                stopped.append(refused(main, ["boot-build", str(w), str(tmp / "build.iso"), "--wait", "14400"]))
        finally:
            take_slot = real_take_slot
            for k, v in real_methods.items():
                setattr(Sandbox, k, v)
        check("boot-build --wait: its dead-pad relaunch keeps a held slot and takes a reclaimed one like a new "
              "sandbox, waiting that long either way",
              stopped == [True, True] and waits == [(14400.0, True), (14400.0, False)], f"{waits}")
        other = subprocess.Popen(["sleep", "60"])
        xemu_pids, admission = (lambda: []), (lambda n: "1.0 of 24 CPU cores are free (selftest)")
        try:
            xemu_queue.take_ticket({"W": "/tmp/azx-other.4", "pid": other.pid}, SLOTS)
            _write_slot(w, {"pid": 101, "gdb_port": 1})
            fd = take_slot(w, -1, keep=True)
            _unlock(fd)
            kept = json.loads((SLOTS / f"{w.name}.json").read_text(encoding="utf-8"))
            check("relaunch: keeping its slot, it starts past a waiting sitting and the free-core rule, its slot as it was",
                  fd is not None and kept.get("gdb_port") == 1 and len(xemu_queue.tickets(SLOTS)) == 1, f"{kept}")
        finally:
            other.kill()
            other.wait()
            xemu_pids, admission = real_xemu_pids, real_admission
        # AZ-300: a running X3 build rewrites its marker in SHIMS every tick,
        # so the code check leaves out the build's shim data, and only that
        xbe = bytearray(0x290)   # an XBE of two zeroed 0x40-byte sections
        xbe[:4] = b"XBEH"
        struct.pack_into("<I", xbe, 0x104, 0x10000)
        struct.pack_into("<2I", xbe, 0x11C, 2, 0x10180)
        for i, (va, name) in enumerate(((0x11000, b".text"), (0x12000, b"SHIMS"))):
            struct.pack_into("<6I", xbe, 0x180 + 56 * i, 0, va, 0x40, 0x210 + 0x40 * i, 0x40, 0x10200 + 8 * i)
            xbe[0x200 + 8 * i:0x200 + 8 * i + len(name)] = name
        g = _FakeGuest()
        g.mem.update({0x11000: bytearray(0x40), 0x12000: bytearray(0x40)})
        sb.halt, sb._xbes["mod.iso"] = (lambda: g), bytes(xbe)
        sb.shim_data = lambda name="dvd.iso": [(0x12010, 0x12020)]
        g.mem[0x12000][0x10:0x20] = b"\xff" * 0x10   # the shim rewrote all its data
        same = sb.code_identity("mod.iso")
        g.mem[0x12000][0x0F] = g.mem[0x12000][0x20] = g.mem[0x11000][0] = 1   # a byte either side, one in .text
        diff = sb.code_identity("mod.iso")
        check("code identity: the build's shim data is left out, and a byte either side of it still counts",
              same == {".text": [0x40, 0], "SHIMS": [0x30, 0]}
              and diff == {".text": [0x40, 1], "SHIMS": [0x30, 2]}, f"{same} {diff}")
        # D146: a Europe disc's VAs come from its address map, every one of them
        eu = bytearray(0x15C)
        eu[:4] = b"XBEH"
        struct.pack_into("<I", eu, 0x158, EUROPE.thunks ^ 0x5B6D40B6)
        try:
            got = (use_release(xbe_layout(bytes(eu))).release.name, PLAYER_TICK, TICK_RETURN, SCENE_PTR)
        except LookupError as e:   # the facts name the VA
            got = str(e)
        finally:
            use_release(USA)
        check("a Europe disc's harness VAs are its own (player tick, its return, the scene pointer)",
              got == ("europe", 0x8CC70, 0x8C332, 0x1C15DC) and PLAYER_TICK == 0x8CCC0, f"{got}")
        # a build of the other release refuses by name before it boots
        import types
        us = bytearray(eu)
        struct.pack_into("<I", us, 0x158, USA.thunks ^ 0x5B6D40B6)
        other_sb = types.SimpleNamespace(st={}, stage=lambda b: ("b-0.iso", "0"), _cpuid_mark=lambda: 0,
                                         host_profile=lambda: {},
                                         _xbe=lambda n: bytes(us if n == "dvd.iso" else eu))
        try:
            Sandbox.boot_build(other_sb, Path("europe-build.iso"))
            why = "it booted"
        except (SystemExit, AttributeError) as e:
            why = str(e)
        check("boot-build: a Europe build in a USA sandbox refuses, naming both releases",
              why == "europe-build.iso is the Europe release; this sandbox's disc and states are the USA one's",
              why)
        # AZ-337: a capture row's non-finite bbox z is a string (fnum)
        def jump(mid_bz):
            ticks = [(0, 0.0, 1.0), (2, 4.5, mid_bz), (2, 4.25, 2.5), (0, 0.0, 1.0)]
            return jump_summary([{"k": k, "state": s, "vz": vz, "bz": bz, "h": 1.1, "air_ctl": 9.0,
                                  "peak_z": 0.0, "hold_t": 0.0} for k, (s, vz, bz) in enumerate(ticks)])
        try:
            js = [(s["apex_bz"], s["airborne_ticks"], s["dvz"]) for s in (jump(fnum(math.nan)), jump(2.0))]
        except TypeError as e:
            js = str(e)
        check("jump_summary: a bbox z that reads as a string gives no apex, and the jump is still summarized",
              js == [(None, 2, [-0.25]), (1.5, 2, [-0.25])], f"{js}")
    finally:
        SLOTS, SUITE_LOCKS, press, (READY_S, LOADED_S), OWNER_DEMO = real_slots, real_suite, real_press, real_waits, \
            real_demo
        xemu_queue.OWNER_DEMO, disk_wait, SHA_CACHE = real_demo, real_disk_wait, real_sha_cache
        FORK_REQUESTS = real_requests
        shutil.rmtree(tmp, ignore_errors=True)     # its own scratch, deleted directly (D147)
    log("selftest: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


# --- CLI ------------------------------------------------------------------

def add_box_args(p: argparse.ArgumentParser) -> None:
    """A launching command's build and display options (the kit's ``serve`` takes them too)."""
    p.add_argument("--app", help="the xemu.app to clone: fork (default, the fork build), kept (the build that "
                   "made the D98 states, the fallback) or a bundle's path")
    m = p.add_mutually_exclusive_group()
    m.add_argument("--headless", choices=HEADLESS, help="XEMU_HEADLESS: null no rendering, deterministic (the "
                   "default), 1 offscreen (pictures; real time unless --deterministic), 0 a window; a build without "
                   "the mode opens its window")
    m.add_argument("--window", dest="headless", action="store_const", const="0", help="a visible window (--headless 0)")
    p.add_argument("--deterministic", action="store_const", const=True, default=None,
                   help="with --headless 1: deterministic offscreen (-icount; screendumps taken paused reproduce, "
                        "about 3x slower than null; Step X.26)")
    p.add_argument("--record", type=int, choices=(1, 2, 3, 4), help="the fork's input recorder (v0.14-36): every "
                   "vblank, what that port's pad gave the guest, as pipe lines into W/input-record.txt, a section per "
                   "load (an owner demo: replay a section with play_recording; Step X.30)")


def add_owner_pad_arg(p: argparse.ArgumentParser) -> None:
    """``--owner-pad PORT`` for the commands that start a sandbox to stay up (``up``, the kit's ``serve``)."""
    p.add_argument("--owner-pad", type=int, choices=(1, 2, 3, 4), help="an owner demo (D205): the owner's pad (the "
                   "fixtures' GUIDs) bound on PORT, with --window only (real time), volume 0; port 2 replaces the "
                   "harness's keyboard pad for the sandbox's life, so the pipe drives nothing (no warp, cheat or "
                   "boot-build: skill section 4.9); devkit/xemu/demo.py records and re-plugs it")
    p.add_argument("--pad-port", type=int, choices=(1, 2, 3, 4), default=2, help="the keyboard pad, which the pipe "
                   "drives, on this port (default 2): 1 replays a demo recorded on the owner's port 1 as the owner's "
                   "pad (AZ-439; play_recording)")
    p.add_argument("--live-pads", action="store_true", help="a demo as played (v0.15, Step X.32b): icount paced in "
                   "real time with live pads (XEMU_ICOUNT_LIVE_PADS), so its --record replays tick for tick in a "
                   "deterministic sandbox; --owner-pad takes the keyboard pad's port by xemu-input-bind")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    j = sub.add_parser("jump", help="cold-boot ISO, jump once in the Training Arena, print v0")
    j.add_argument("--iso", type=Path, help="the ISO to boot, e.g. a build made from vanilla "
                   "(default: the vanilla ISO the resolver finds: AZURKIT_ISO, then "
                   "the user data dir's usa.iso; identity-checked)")
    j.add_argument("--ticks", type=int, default=30, help="player ticks to record (default 30)")
    u = sub.add_parser("up", help="start a sandbox (the fork build, null and deterministic: its guest waits for the "
                       "first loadvm), leave it running and print its W")
    u.add_argument("group", help="a short name for W (/tmp/azx-<group>.*)")
    u.add_argument("--out", type=Path, help="where labelled captures and the baselines go (default W)")
    add_owner_pad_arg(u)
    d = sub.add_parser("down", help="quit, compare the baselines, free the slot, delete W")
    d.add_argument("W", type=Path)
    d.add_argument("--keep", action="store_true", help="keep W (e.g. to read its HDD clone)")
    r = sub.add_parser("relaunch", help="launch again on the same W after xemu died")
    r.add_argument("W", type=Path)
    sub.add_parser("status", help="alive, the QMP status and one player-tick row").add_argument("W", type=Path)
    for name, text in (("loadvm", "load a tag; halt at the first player tick and print its row"),
                       ("savevm", "save a tag into W's HDD clone (never an oracle tag)")):
        p = sub.add_parser(name, help=text)
        p.add_argument("W", type=Path)
        p.add_argument("tag")
        if name == "loadvm":
            p.add_argument("--disc", help="the disc in W to load it with (default: the one it was saved with, as W "
                                          "recorded it, else dvd.iso; an owner demo needs it for a tag it didn't save)")
    p = sub.add_parser("hmp", help="a monitor command (not loadvm, savevm or delvm)")
    p.add_argument("W", type=Path)
    p.add_argument("line")
    p = sub.add_parser("press", help="a wall-clock button press (the guest running)")
    p.add_argument("W", type=Path)
    p.add_argument("btn")
    p.add_argument("seconds", type=float, nargs="?", default=0.5)
    b = sub.add_parser("boot-build", help="boot a build into a vanilla-ig-* state's save (skill section 6)")
    b.add_argument("W", type=Path)
    b.add_argument("iso", type=Path)
    b.add_argument("--tag", default="vanilla-ig-w1")
    b.add_argument("--save", type=int, default=1, help="the save to load, counted from 1 in the save list (the D98 "
                   "drive: 1 the all-powers character, 2 the new-game one)")
    b.add_argument("--cold", action="store_true", help="boot from the menu even if this sandbox holds the build's "
                   "warm state, and save none")
    b.add_argument("--a-frame", type=int, default=None, help=f"(a deterministic sandbox) the frame from the reset A goes "
                   f"down on the save list (default {A_FRAME}; each retry {A_RETRY} later): AZ-695's race")
    for q in (j, u):
        add_box_args(q)
    for q in (j, u, r, b):   # the commands that launch xemu (boot-build: its relaunch before a retry)
        q.add_argument("--wait", type=float, default=WAIT_S,
                       help=f"seconds a launch waits for a slot (load, RAM, another launch; "
                            f"default {WAIT_S:.0f})")
    p = sub.add_parser("snapshot", help="an L3 snapshot of the player's next update into the private store")
    p.add_argument("W", type=Path)
    p.add_argument("label", help="its name in the store (<label>.l3snap)")
    p.add_argument("--store", type=Path, help="the private store (default: the user data dir's "
                   "AzurKit/l3-snapshots, mode 700)")
    p.add_argument("--scene", action="store_true", help="at the scene tick's entry (for L3's whole steps)")
    p.add_argument("--hold", action="store_true", help="leave the guest halted at the start, for replay")
    p = sub.add_parser("replay", help="run an input string in L3 from a snapshot, replay it in xemu, compare")
    p.add_argument("W", type=Path)
    p.add_argument("label", help="the snapshot; the guest halted at its start (snapshot --hold)")
    p.add_argument("inputs", type=Path, help='JSON segments [{"n": 30, "stick": [0, 1], "buttons": ["y"], '
                   '"yaw": 0.5}, ...]')
    p.add_argument("--store", type=Path, help="the private store (default as snapshot's)")
    p.add_argument("--scene", action="store_true", help="L3 runs whole steps (a --scene snapshot)")
    sub.add_parser("tags", help="the oracle tags (the fixtures README's Savestates table)")
    sub.add_parser("slots", help="the running sandboxes, and whether a new one may start now")
    sub.add_parser("selftest", help="offline checks (no xemu)")
    p = sub.add_parser("unhold", help="(hold_for_sitting's reaper) after --after seconds, down a held sandbox no "
                       "run claimed")
    p.add_argument("W", type=Path)
    p.add_argument("--after", type=float, default=HOLD_S)
    p.add_argument("--slots", type=Path, default=SLOTS, help="the slots folder (the hold's)")
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(line_buffering=True)   # progress shows even when redirected
    if a.cmd == "jump":
        if a.ticks < JUMP_AT + 3:   # the press lands 2+ ticks after JUMP_AT
            ap.error(f"--ticks must be at least {JUMP_AT + 3} to see the takeoff")
        try:
            iso = a.iso or vanilla_iso()
        except (OSError, ValueError) as e:   # not found, or not vanilla
            ap.error(str(e))
        return jump(iso, a.ticks, a.wait, a.headless, a.app, a.deterministic)
    if a.cmd == "selftest":
        return selftest()
    if a.cmd == "unhold":
        globals()["SLOTS"] = a.slots
        return unhold(a.W, a.after)
    if a.cmd == "tags":
        log("\n".join(oracle_tags()))
        return 0
    if a.cmd == "slots":
        idle, n, free = idle_fraction(), os.cpu_count() or 1, free_ram()   # measured once, before the verdict
        procs = {p: pid_command(p) for p in xemu_pids()}
        running = sorted(sandbox_pids(procs))
        foreign, auto = foreign_xemus(procs), fork_auto_xemus(procs)
        queue, demo, background = xemu_queue.tickets(SLOTS), owner_demo(), demo_background()
        why = (f"an xemu runs that isn't a sandbox (pids {foreign})" if foreign
               else (demo and demo_admission(demo, procs)) or admission(sandboxes(procs), idle, n, free))
        if queue:
            why = f"{len(queue)} sitting(s) wait first (first come, first served)" + (f"; and {why}" if why else "")
        log(json.dumps({"slots": slots(), "held": sorted(q.stem for q in held_dir().glob("azx-*.json")),
                        "running_sandbox_pids": running, "foreign_xemus": foreign,
                        "fork_auto_xemus": auto, "owner_demo": demo,
                        **({"demo_budget": xemu_queue.demo_budget(), "background_pids": background} if demo else {}),
                        "queue": [{k: t.get(k) for k in ("n", "W", "pid", "why", "cores")}
                                  | {"waiting_s": round(time.time() - t["since"])} for t in queue],
                        "batch_jobs": xemu_queue.batch_jobs(SLOTS),
                        "cpus": n, "free_cores": None if idle is None else round(n * idle, 1),
                        "min_free_cores": MIN_FREE_CORES, "free_ram_gib": round(free / 2**30, 1),
                        **({"load": os.getloadavg()} if idle is None else {}),
                        "admission": why or "a new sandbox may start"}, indent=1))
        return 0
    if a.cmd == "up":
        Sandbox(a.group, app=a.app, out=a.out, wait_s=a.wait, headless=a.headless, deterministic=a.deterministic,
                record=a.record, owner_pad=a.owner_pad, pad_port=a.pad_port, live_pads=a.live_pads).up()
        return 0
    sb = Sandbox.attach(a.W, wait_s=getattr(a, "wait", WAIT_S))
    try:
        if a.cmd == "down":
            return 0 if sb.down(keep=a.keep)["sources_equal"] else 1
        if a.cmd == "relaunch":
            sb.relaunch()
        elif a.cmd == "status":
            st = {"alive": sb.alive(), "pid": sb.st.get("pid"), "last_tag": sb.st.get("last_tag"),
                  "events": sb.st.get("events", [])[-5:]}
            if st["alive"]:
                st["status"] = sb.status()
                row = sb.player()
                st["player"] = Sandbox._jsonrow(row) if row else "no player tick within 5 s"
            log(json.dumps(st))
        elif a.cmd == "loadvm":
            log(json.dumps(sb.loadvm(a.tag, disc=a.disc)))
        elif a.cmd == "savevm":
            log(sb.savevm(a.tag))
        elif a.cmd == "hmp":
            log(sb.hmp(a.line))
        elif a.cmd == "press":
            sb.press(a.btn, seconds=a.seconds)
        elif a.cmd == "boot-build":
            log(json.dumps(sb.boot_build(a.iso, a.tag, save=a.save, warm=not a.cold, a_frame=a.a_frame)))
        elif a.cmd == "snapshot":
            log(json.dumps(sb.snapshot(a.label, store=a.store, scene=a.scene)))
            if a.hold:
                sb.detach()
        elif a.cmd == "replay":
            log(json.dumps(l3_replay(sb, a.label, json.loads(a.inputs.read_text(encoding="utf-8")),
                                     store=a.store, scene=a.scene)))
    finally:
        sb.release()
    return 0


if __name__ == "__main__":
    sys.exit(main())
