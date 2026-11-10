"""FastL3 (Step R2.19a, from R2.17's emulator prototype): L3's steps, rows and memory on less host CPU.

:class:`FastL3` is :class:`~devkit.sim.l3.L3` with Unicorn's store slow path off.  Unicorn 2.1.4 marks every
writable RAM page TLB_NOTDIRTY and clears the mark (``notdirty_write``) only for a TLB entry with no code access
whose page no memory hook covers; L3 maps every page UC_PROT_ALL under a UC_HOOK_MEM_UNMAPPED hook over every
address, and x86 with paging off fills every entry R+W+X, so each guest store (pushes too) took the region lookup
and the self-modifying-code check, forever (R2.16e round 2's speed seat: about a third of a tick's CPU).  Here:

- ``vtlb``: Unicorn's virtual TLB (UC_TLB_VIRTUAL) filled by a hook, identity VA = PA: the code pages (the XBE's
  executable sections, the kernel stub pages L3 hooks, the _STOP page) R+W+X, every other page R+W, so a data
  entry is cleaned by its first store;
- ``bound``: the UC_HOOK_MEM_UNMAPPED hook over [_DATA, 4 GiB) only, what its callback serves (an unmapped access
  below gets Unicorn's own error, an ``L3Error`` as in L3, but a write's site is another EIP: Unicorn syncs EIP
  only inside a hook covering the address, so it names the last EIP synced, the block's end with the exit check
  skipped; never a find, and none on the bench);
- ``rw_data``: every page outside the code pages mapped R+W (no UC_PROT_EXEC), so a store to it skips the SMC check;
- ``code_inval``: L3's translation drops (``write``, ``reset``) only over code pages, since no translation lives on
  another page; each drop over a data page cost a fetch-type TLB fill and a refill of the data entry it replaced.

A fetch from a page outside the code set (none expected: the game runs from its sections; none on the bench) is
counted (``data_fetch``) and faults (``fetch_prot``: ``rw_data`` maps the page without exec) where L3 runs the code:
a lost find, never a false one.  An overlay is refused (its appended sections would need adding to the code set).
Whole steps (``scene``: rigs, lifts, the render, MMIO, high pages) are L3's too: Step R2.19b's compare on a5's
reach-live snapshot, on the patched library, gave base L3's every row, every platform owner's pose and the end memory
over 3,600 whole steps, and every row of 30 launches from them; so ``l3_pool.Pool``'s ``fast`` builds it for both.

The patched library (:data:`PATCH`, built by ``devkit/reach/unicorn/build_unicorn.py`` into :func:`library`'s folder, loaded by a
process that starts with :func:`worker_env` set) adds, each behind its own switch (none set: it runs as stock):
``UC_SKIP_MEM_EXIT_CHECK=1`` drops the exit-request check after every guest load and store (kept after code hooks,
which stop or move EIP, and at each block's start); ``UC_TB_EXIT_INLINE=1`` (Step R2.19m) makes the block-start
check QEMU's own inline load and branch, not a helper call (a request seen there leaves with EIP the block's start, as
the helper's restore gives); ``UC_TLB_BITS=12`` keeps a 4,096-entry TLB (the 256-entry one
thrashed: hot heap and .rdata pages share slots modulo 1 MiB); ``UC_X87_FAST=1`` an exact fast path for x87 add,
sub, mul, div, sqrt, loads, stores and compares where the control word is 53-bit round-to-nearest and the operands
are doubles exactly (there the host's IEEE double result is softfloat's floatx80 result bit for bit; anything else
takes softfloat (Step R2.19m's lean path: inlined, the precision test cached where the control word is set, no check
code), and the check flavour (:data:`CHECK`, the same source built with the check code, :func:`worker_env`'s
``check``) with ``UC_X87_CHECK=1`` runs softfloat beside every fast result and prints the count that differ at exit.  Exactness is gated by records (Step R2.19a's bench: every record round 1's, byte for
byte), so neither this file nor the patch is in the reach cache's key (``reach_engine.cache.CORE_FILES``).

The C step (Step R2.19m m2, ``fastl3_step.c``, built by :func:`step_lib` with the ziglang wheel's zig cc): the TLB
fill in C, and a player tick without ``deep`` (the reach engine's: its pools' simulators read without it) stepped in
C, its poll, clock, return slot, register batch, watchdog and ``emu_start`` and the update's entry, camera and exit
hooks; the row is decoded after by ``obs.read`` itself from the blocks the exit hook copied out.  Whole steps,
``deep`` ticks and a tick that meets a pending stream request run L3's Python step (the Python hooks swapped back in).
``FASTL3_STEP=python`` (:func:`step_on`) turns the C step off, the collision walk's face loop with it, and leaves
``UC_TB_EXIT_INLINE`` out of :func:`worker_env`: R2.19a's FastL3 on R2.19b's switches, for X1's re-proof (PLAN-v3).
Dev tooling, never in pytest's tiers but its own test.
"""

from __future__ import annotations

import ctypes
import functools
import hashlib
import importlib.util
import os
import re
import struct
import subprocess
import sys
import weakref
from pathlib import Path

from unicorn import (UC_HOOK_CODE, UC_HOOK_MEM_UNMAPPED, UC_HOOK_TLB_FILL, UC_MEM_FETCH, UC_PROT_READ, UC_PROT_WRITE,
                     UC_TLB_VIRTUAL, UcError)
from unicorn import x86_const as X
from unicorn.unicorn_const import UC_CTL_IO_WRITE, UC_CTL_TB_REMOVE_CACHE, UC_CTL_TLB_FLUSH
from unicorn.unicorn_py3.arch.intel import UcIntel

from devkit.sim import l3
from devkit.sim import obs as _obs
from devkit.sim.l3 import (_DATA, _STACK, _STACK_SIZE, _STOP, ACTIVE_PAD, CAMERA_DIR, CONTROLLER_STATE, HIGH,
                               PAD_SIZE, PAGE, PLAYER_UPDATE, STREAM_PENDING, UPDATE_RETS, UPDATE_US, L3, L3Error,
                               LevelExit, Pad, Row, _code_sections, camera_dir, kernel_names, pad_floats)

RW = UC_PROT_READ | UC_PROT_WRITE
# The patched libunicorn's patch (the module docstring): beside its builder, out of the wheel (Unicorn is GPL: none
# of it ships, devkit/reach/unicorn/NOTICE.md).
PATCH = Path(__file__).resolve().parent / "unicorn" / "unicorn_fastl3.patch"
SWITCHES = {"UC_SKIP_MEM_EXIT_CHECK": "1", "UC_TLB_BITS": "12", "UC_X87_FAST": "1", "UC_TB_EXIT_INLINE": "1"}
LIB_NAME = {"darwin": "libunicorn.2.dylib", "linux": "libunicorn.so.2"}.get(sys.platform, "unicorn.dll")
CHECK = "check"   # library()'s subfolder: the x87 check flavour (Step R2.19m; the audit's workers load it)


def library(root: str | Path | None = None) -> Path:
    """The folder the patched libunicorn of this :data:`PATCH` is built into: ``root`` (default the user cache
    dir's ``AzurKit``) ``/unicorn-fastl3/<the patch's sha256[:12]>``."""
    from platformdirs import user_cache_dir
    base = Path(root) if root is not None else Path(user_cache_dir("AzurKit"))
    return base / "unicorn-fastl3" / hashlib.sha256(PATCH.read_bytes()).hexdigest()[:12]


def worker_env(root: str | Path | None = None, check: bool = False) -> dict[str, str]:
    """What a process sets before it imports unicorn to run the patched library with its :data:`SWITCHES` on
    (``LIBUNICORN_PATH``; with ``check`` its x87 check flavour, :data:`CHECK`, which alone reads ``UC_X87_CHECK``),
    or {} when it isn't built (the stock wheel then: FastL3 on it is as exact, slower).  With the C step off
    (:func:`step_on`) its inline exit test, ``UC_TB_EXIT_INLINE``, is left out."""
    lib = library(root) / CHECK if check else library(root)
    on = {k: v for k, v in SWITCHES.items() if step_on() or k != "UC_TB_EXIT_INLINE"}
    return {"LIBUNICORN_PATH": str(lib), **on} if (lib / LIB_NAME).is_file() else {}


def loaded() -> Path:
    """The libunicorn this process loaded (unicorn's ctypes library: the patched one only in a process that started
    with :func:`worker_env` set)."""
    from unicorn.unicorn_py3 import unicorn as u
    return Path(u.uclib._name)


def probe(check: bool = False) -> dict:
    """What a fresh process with :func:`worker_env` (``check``) set loads, as the reach engine's FastL3 workers do
    (Step R2.19b; Modkit's ``doctor`` named it): the library's path and sha256[:12], unicorn's version and the
    switches set."""
    import json
    import os
    import subprocess
    code = ("import json, unicorn; from unicorn.unicorn_py3 import unicorn as u; "
            "print(json.dumps({'lib': u.uclib._name, 'version': unicorn.__version__}))")
    env = worker_env(check=check)
    got = json.loads(subprocess.run([sys.executable, "-I", "-c", code], env={**os.environ, **env}, check=True,
                                    capture_output=True, text=True).stdout)
    return got | {"sha12": hashlib.sha256(Path(got["lib"]).read_bytes()).hexdigest()[:12],
                  "switches": {k: v for k, v in env.items() if k in SWITCHES}}


def code_pages(xbe: bytes | None, kernel: dict[int, str], extra=()) -> set[int]:
    """The page numbers (VA >> 12) code runs from: the XBE's executable sections (and ``extra``), the kernel's entry
    points' pages (L3's stubs and hooks) and L3's _STOP page and the one below it."""
    pages = {p for s in (_code_sections(xbe) if xbe is not None else ())
             for p in range(s["vaddr"] >> 12, (s["vaddr"] + s["vsize"] + 0xFFF) >> 12)} | set(extra)
    return pages | {a >> 12 for a in kernel} | {_STOP >> 12, (_STOP - 1) >> 12}   # Unicorn drops the TBs before
                                                                                # emu_start's exit too


# The C step (Step R2.19m m2, ``fastl3_step.c``, its header says what it stands in for): built by the pinned ziglang
# wheel's zig cc (the native kernel's toolchain) into the AzurKit user cache, once per source, flags and compiler.
STEP_SRC = Path(__file__).with_name("fastl3_step.c")
STEP_FLAGS = ("-O2", "-shared", "-fPIC", "-ffp-contract=off")   # no fused multiply-add: the game's rounding
NEED_PY, BATCH_ERR = 1, 2           # fl3_step's statuses beside 0: run the Python step; the register batch failed
# The collision walk's face loop (Step R2.19m m4, fastl3_step.c's h_walk; docs/RE_MOVEMENT.md): the static level's walk
# 0xD1B80 puts each face of a chunk's x range through the query's matrix and drops it when all three vertices lie
# beyond one bound, else calls the face test 0xB9E60 at WALK_CALL; both paths meet at WALK_MERGE.
WALK_HEAD, WALK_CALL, WALK_MERGE = 0xD1E80, 0xD22B0, 0xD22EE
WALK_MODES = {"0": 0, "1": 1, "check": 2}   # $FASTL3_WALK: off, the C walk drops faces (the default), check mode
MAXW, WBUF, NOB, OBN, NREG = 16, 2048, 5, 0x170, 16


class _Spec(ctypes.Structure):
    _fields_ = [*((n, ctypes.c_void_p) for n in ("hook_add", "hook_del", "reg_read", "reg_write", "reg_write_batch",
                                                 "mem_read", "mem_write", "emu_start", "emu_stop", "ctl", "touch")),
                *((n, ctypes.c_int32) for n in ("r_ecx", "r_esp", "r_ebp", "r_eip", "hook_code", "hook_tlb_fill",
                                                "mem_fetch", "ctl_remove_cache", "code_inval")),
                *((n, ctypes.c_uint32) for n in ("player_update", "camera_dir", "update_ret0", "update_ret1", "stop",
                                                 "stack_esp", "active_pad", "controller_state", "pad_size",
                                                 "stream_pending", "entity", "high")),
                ("nfixed", ctypes.c_int32), ("fixed_ids", ctypes.c_int32 * NREG),
                ("fixed_wide", ctypes.c_int32 * NREG), ("fixed_vals", ctypes.c_uint32 * NREG),
                ("r_ebx", ctypes.c_int32), ("r_fpcw", ctypes.c_int32), ("walk_head", ctypes.c_uint32),
                ("walk_call", ctypes.c_uint32), ("walk_merge", ctypes.c_uint32)]


class _Io(ctypes.Structure):
    _fields_ = [("pad", ctypes.c_uint8 * 72), ("nw", ctypes.c_int32), ("wva", ctypes.c_uint32 * MAXW),
                ("wlen", ctypes.c_uint32 * MAXW), ("wdata", ctypes.c_uint8 * WBUF), ("cam_set", ctypes.c_int32),
                ("cam", ctypes.c_uint8 * 8), ("do_poll", ctypes.c_int32), ("timeout_s", ctypes.c_double),
                ("status", ctypes.c_int32), ("emu_err", ctypes.c_int32), ("hook_err", ctypes.c_int32),
                ("eip", ctypes.c_uint32), ("pv", ctypes.c_uint32), ("in_", ctypes.c_int32),
                ("row_done", ctypes.c_int32), ("cam_used_set", ctypes.c_int32), ("cam_used", ctypes.c_uint8 * 8),
                ("nob", ctypes.c_int32), ("ob_va", ctypes.c_uint32 * NOB), ("ob_n", ctypes.c_uint32 * NOB),
                ("ob", ctypes.c_uint8 * OBN * NOB)]


class _Stats(ctypes.Structure):
    _fields_ = [("fills", ctypes.c_uint64), ("data_fetch", ctypes.c_uint64), ("inval_skipped", ctypes.c_uint64),
                ("steps", ctypes.c_uint64), ("host", ctypes.c_int32), ("walk_mode", ctypes.c_int32),
                *((n, ctypes.c_uint64) for n in ("walk_heads", "walk_dropped", "walk_unsafe", "walk_checked",
                                                 "walk_differ"))]


_TOUCH = ctypes.CFUNCTYPE(None, ctypes.c_uint64, ctypes.c_uint64)


def step_sha12() -> str:
    """sha256[:12] of the C step's source, flags and compiler (its build's name; a record's ``l3_impl`` names it)."""
    from importlib.metadata import version
    h = hashlib.sha256(f"{version('ziglang')} {' '.join(STEP_FLAGS)} {sys.platform}\n".encode())
    h.update(STEP_SRC.read_bytes())
    return h.hexdigest()[:12]


def step_on() -> bool:
    """Whether a FastL3 steps in C where :func:`step_lib` builds: ``$FASTL3_STEP`` ``c`` (the default) or ``python``
    (the C step, its walk and the inline exit test off: PLAN-v3's m2 and m4, for X1's re-proof)."""
    mode = os.environ.get("FASTL3_STEP", "c")
    if mode not in ("c", "python"):
        raise ValueError(f"FASTL3_STEP is {mode!r}: c or python")
    return mode == "c"


@functools.cache
def step_lib() -> ctypes.CDLL | None:
    """The C step, compiled once per :func:`step_sha12` into the AzurKit user cache's ``fastl3-step`` and loaded (a
    process that compiled it beside another loads the one installed first); None where the ziglang wheel isn't
    installed (FastL3 then steps in Python, as exact)."""
    from platformdirs import user_cache_dir
    spec = importlib.util.find_spec("ziglang")
    if spec is None:
        return None
    d = Path(user_cache_dir("AzurKit")) / "fastl3-step"
    d.mkdir(mode=0o700, parents=True, exist_ok=True)
    out = d / f"fastl3_step-{step_sha12()}.so"
    if not out.exists():
        tmp = out.with_suffix(f".{os.getpid()}.part")
        env = {"ZIG_GLOBAL_CACHE_DIR": str(d / "zig-cache"), "ZIG_LOCAL_CACHE_DIR": str(d / "zig-cache")}
        done = subprocess.run([str(Path(spec.origin).with_name("zig")), "cc", *STEP_FLAGS, "-o", str(tmp),
                               str(STEP_SRC)], env=os.environ | env, capture_output=True, text=True)
        if done.returncode != 0:
            raise RuntimeError(f"zig cc failed on {STEP_SRC.name}:\n{done.stderr.strip()}")
        try:
            os.replace(tmp, out)
        except PermissionError:      # Windows: another process built it at once and has loaded it (same name:
            if not out.exists():     # same source, flags and compiler), which Windows won't replace
                raise
            tmp.unlink()
    lib = ctypes.CDLL(str(out))
    lib.fl3_new.restype = ctypes.c_void_p
    lib.fl3_new.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Spec), ctypes.POINTER(ctypes.c_uint32), ctypes.c_int64]
    lib.fl3_free.argtypes = [ctypes.c_void_p]
    lib.fl3_io_of.restype = ctypes.POINTER(_Io)
    lib.fl3_io_of.argtypes = [ctypes.c_void_p]
    lib.fl3_stats_of.restype = ctypes.POINTER(_Stats)
    lib.fl3_stats_of.argtypes = [ctypes.c_void_p]
    lib.fl3_fetched.restype = ctypes.c_int64
    lib.fl3_fetched.argtypes = [ctypes.c_void_p, ctypes.c_int64, ctypes.POINTER(ctypes.c_uint32), ctypes.c_int64]
    lib.fl3_fill_hook.restype = lib.fl3_hooks.restype = lib.fl3_step.restype = lib.fl3_walk.restype = ctypes.c_int
    lib.fl3_fill_hook.argtypes = [ctypes.c_void_p]
    lib.fl3_hooks.argtypes = lib.fl3_walk.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.fl3_step.argtypes = [ctypes.c_void_p]
    return lib


class _Uc(UcIntel):
    """Unicorn as :class:`FastL3` builds it: data pages mapped R+W, the unmapped hook bounded and translation drops
    over code pages only, as its options say."""

    def __new__(cls, arch, mode, owner: FastL3):   # Uc.__new__ hands back a plain UcIntel
        return object.__new__(cls)

    def __init__(self, arch, mode, owner: FastL3) -> None:
        super().__init__(arch, mode)
        self._owner = owner

    def _split(self, address: int, size: int):
        """``[address, address + size)`` as runs of code pages and of data pages: (va, size, code)."""
        self._owner._sync()
        code, va, end = self._owner.code, address, address + size
        while va < end:
            c = (va >> 12) in code
            w = va + PAGE
            while w < end and ((w >> 12) in code) == c:
                w += PAGE
            yield va, w - va, c
            va = w

    def mem_map(self, address, size, perms=7):
        if not self._owner.rw_data:
            return super().mem_map(address, size, perms)
        for va, n, c in self._split(address, size):
            super().mem_map(va, n, perms if c else perms & RW)

    def mem_map_ptr(self, address, size, perms, ptr):
        if not self._owner.rw_data:
            return super().mem_map_ptr(address, size, perms, ptr)
        for va, n, c in self._split(address, size):
            super().mem_map_ptr(va, n, perms if c else perms & RW, ptr + va - address)

    def hook_add(self, htype, callback, user_data=None, begin=1, end=0, *a, **k):
        o = self._owner
        if o.bound and htype == UC_HOOK_MEM_UNMAPPED and (begin, end) == (1, 0):
            begin, end = _DATA, 0xFFFFFFFF
        h = super().hook_add(htype, callback, user_data, begin, end, *a, **k)
        if callback in (o._update_entry, o._camera, o._update_exit):   # the C step's hooks stand in for these
            o._py_hooks.append((h, htype, callback, user_data, begin, end))
        return h

    def mem_unmap(self, address, size):
        o = self._owner
        o._host = True                    # Unicorn drops the region's translations: a fetch-type lookup, no fetch
        if o._st is not None:
            o._st.host = 1
        try:
            return super().mem_unmap(address, size)
        finally:
            o._host = False
            if o._st is not None:
                o._st.host = 0

    def ctl_remove_cache(self, lbound, ubound):
        o = self._owner
        if o.code_inval:
            o._sync()
            a, b, code = lbound >> 12, (ubound - 1) >> 12, o.code
            if (a not in code and b not in code) if b - a <= 1 else not any(p in code for p in range(a, b + 1)):
                o._inval_skipped += 1
                return None
        return super().ctl_remove_cache(lbound, ubound)


class FastL3(L3):
    """:class:`L3` with the options above (all on by default); ``fills``, ``data_fetch`` and ``inval_skipped``
    count the TLB fills, fetches outside the code pages and translation drops skipped since it was built.  The code
    set is the XBE's (``kernel`` the XBE), or with a kernel mapping ``code``'s page numbers (a synthetic snapshot).
    ``native`` (Step R2.19m m2; on where :func:`step_lib` builds; by default :func:`step_on`): the TLB fill in C, and
    each player tick without ``deep`` (the reach engine's) stepped by the C step with its update entry, camera and exit
    hooks (``native_steps`` counts them); a whole step, a ``deep`` tick or a tick that meets a pending stream request
    runs the Python step with the Python hooks (swapped in and out as the mode changes)."""

    def __init__(self, snap, kernel, *, vtlb: bool = True, bound: bool = True, rw_data: bool = True,
                 code_inval: bool = True, code=None, native: bool | None = None, **kw) -> None:
        if kw.get("overlay") is not None:
            raise ValueError("FastL3 takes no overlay (its appended sections aren't in the code set)")
        if not isinstance(kernel, bytes) and code is None:
            raise ValueError("FastL3 needs the XBE (its code sections are the code set) or the code pages")
        self.vtlb, self.bound, self.rw_data, self.code_inval = vtlb, bound, rw_data, code_inval
        self.code = (code_pages(kernel, kernel_names(kernel, snap)) if isinstance(kernel, bytes)
                     else code_pages(None, kernel, code))
        self._fills = self._data_fetch = self._inval_skipped = 0
        self._fetched: list[int] = []     # those pages, in order (the Python fill's)
        self._host = False                # in a host call whose TB drop looks a page up as a fetch
        self._lib = step_lib() if (step_on() if native is None else native) else None
        self._ctx = self._io = self._st = None
        self._py_hooks: list[tuple] = []  # the Python update entry, camera and exit hooks: (handle, add's arguments)
        self._hooks_c, self._seen = False, 0
        made = l3.Uc
        l3.Uc = lambda arch, mode: _Uc(arch, mode, self)
        try:
            super().__init__(snap, kernel, **kw)
        finally:
            l3.Uc = made
        if self._lib is not None:
            self._native_init()
        if vtlb:
            if self._ctx is not None:
                if (err := self._lib.fl3_fill_hook(self._ctx)) != 0:
                    raise UcError(err)
            else:
                self.uc.hook_add(UC_HOOK_TLB_FILL, self._fill)
            self.uc.ctl_set_tlb_mode(UC_TLB_VIRTUAL)
            self.uc.ctl(UC_CTL_TLB_FLUSH, UC_CTL_IO_WRITE)

    # -- counters (the Python fill's and the C step's) --
    @property
    def fills(self) -> int:
        return self._fills + (self._st.fills if self._st is not None else 0)

    @property
    def data_fetch(self) -> int:
        return self._data_fetch + (self._st.data_fetch if self._st is not None else 0)

    @property
    def inval_skipped(self) -> int:
        return self._inval_skipped + (self._st.inval_skipped if self._st is not None else 0)

    @property
    def fetched(self) -> list[int]:
        self._sync()
        return self._fetched

    @property
    def native_steps(self) -> int:
        """The ticks the C step ran."""
        return self._st.steps if self._st is not None else 0

    @property
    def walk(self) -> dict:
        """The collision walk's face loop in C (Step R2.19m m4): its mode and counts (heads seen, faces dropped,
        heads or faces outside the exact envelope, and in check mode the faces checked and those whose decision
        differed from the game's)."""
        st = self._st
        if st is None:
            return {"mode": 0}
        return {"mode": st.walk_mode, "heads": st.walk_heads, "dropped": st.walk_dropped, "unsafe": st.walk_unsafe,
                "checked": st.walk_checked, "differ": st.walk_differ}

    def _sync(self) -> None:
        """The pages the C fill made code since the last look (a fetch from a data page), into ``code``."""
        st = self._st
        if st is not None and st.data_fetch > self._seen:
            n = st.data_fetch - self._seen
            buf = (ctypes.c_uint32 * n)()
            got = self._lib.fl3_fetched(self._ctx, self._seen, buf, n)
            self._fetched += list(buf[:got])
            self.code.update(buf[:got])
            self._seen += got

    def _fill(self, uc, vaddr, access, entry, _) -> bool:
        self._fills += 1
        p = vaddr >> 12
        entry.paddr = vaddr & ~0xFFF
        if p in self.code:
            entry.perms = 7
        elif access == UC_MEM_FETCH:
            if self.code_inval and not self._host:   # a fetch, not a drop's lookup: counted; with rw_data it faults
                self._data_fetch += 1
                self._fetched.append(p)
                self.code.add(p)
                entry.perms = 7
            else:                        # uc_invalidate_tb's lookup (a drop over a data page, an unmap): X alone
                entry.perms = 4
        else:
            entry.perms = 3
        return True

    # -- the C step (Step R2.19m m2) --
    def _native_init(self) -> None:
        """The C step's context on this simulator's engine: Unicorn's API (the library this process loaded), the
        constants and the code pages; freed with the simulator."""
        from unicorn.unicorn_py3 import unicorn as u
        api = u.uclib
        sp = _Spec()
        for name in ("hook_add", "hook_del", "reg_read", "reg_write", "reg_write_batch", "mem_read", "mem_write",
                     "emu_start", "emu_stop", "ctl"):
            setattr(sp, name, ctypes.cast(getattr(api, f"uc_{name}"), ctypes.c_void_p).value)
        self._touch_cb = _TOUCH(lambda va, n: self._touch(va, n))   # kept: C holds its address
        sp.touch = ctypes.cast(self._touch_cb, ctypes.c_void_p).value
        sp.r_ecx, sp.r_esp, sp.r_ebp, sp.r_eip = (X.UC_X86_REG_ECX, X.UC_X86_REG_ESP, X.UC_X86_REG_EBP,
                                                  X.UC_X86_REG_EIP)
        sp.hook_code, sp.hook_tlb_fill, sp.mem_fetch = UC_HOOK_CODE, UC_HOOK_TLB_FILL, UC_MEM_FETCH
        sp.ctl_remove_cache = (UC_CTL_IO_WRITE << 30) | (2 << 26) | UC_CTL_TB_REMOVE_CACHE
        sp.code_inval = int(self.code_inval)
        sp.player_update, sp.camera_dir, (sp.update_ret0, sp.update_ret1) = PLAYER_UPDATE, CAMERA_DIR, UPDATE_RETS
        sp.stop, sp.stack_esp = _STOP, _STACK + _STACK_SIZE - 0x400
        sp.active_pad, sp.controller_state, sp.pad_size = ACTIVE_PAD, CONTROLLER_STATE, PAD_SIZE
        sp.stream_pending, sp.entity, sp.high = STREAM_PENDING, self.entity or 0, HIGH
        sp.r_ebx, sp.r_fpcw = X.UC_X86_REG_EBX, X.UC_X86_REG_FPCW
        sp.walk_head, sp.walk_call, sp.walk_merge = WALK_HEAD, WALK_CALL, WALK_MERGE
        if len(self._fixed) > NREG:
            raise ValueError(f"the register batch has {len(self._fixed)} registers, the C step {NREG}")
        sp.nfixed = len(self._fixed)
        narrow = {X.UC_X86_REG_FPCW, X.UC_X86_REG_FPSW, X.UC_X86_REG_FPTAG}
        for i, (rid, val) in enumerate(self._fixed):
            sp.fixed_ids[i], sp.fixed_wide[i], sp.fixed_vals[i] = rid, rid not in narrow, val & 0xFFFFFFFF
        pages = sorted(self.code)
        arr = (ctypes.c_uint32 * len(pages))(*pages)
        ctx = self._lib.fl3_new(self.uc._uch, ctypes.byref(sp), arr, len(pages))
        if not ctx:
            raise MemoryError("the C step's context")
        self._ctx, self._io, self._st = ctx, self._lib.fl3_io_of(ctx).contents, self._lib.fl3_stats_of(ctx).contents
        weakref.finalize(self, self._lib.fl3_free, ctx)
        mode = WALK_MODES.get(os.environ.get("FASTL3_WALK", "1"))
        if mode is None:
            raise ValueError(f"FASTL3_WALK is {os.environ['FASTL3_WALK']!r}: 0, 1 or check")
        if (err := self._lib.fl3_walk(ctx, mode)) != 0:
            raise UcError(err)

    def _hooks(self, c: bool) -> None:
        """The update entry, camera and exit hooks: the C step's (``c``) or the Python ones."""
        if c == self._hooks_c:
            return
        if c:
            for h, *_ in self._py_hooks:
                self.uc.hook_del(h)
            if (err := self._lib.fl3_hooks(self._ctx, 1)) != 0:
                raise UcError(err)
        else:
            self._lib.fl3_hooks(self._ctx, 0)
            self._py_hooks = [(UcIntel.hook_add(self.uc, ht, cb, ud, b, e), ht, cb, ud, b, e)
                              for _h, ht, cb, ud, b, e in self._py_hooks]
        self._hooks_c = c

    def step(self, pad: Pad = Pad(), *, writes=(), timeout_us: int | None = None) -> Row:
        """:meth:`L3.step`: a player tick without ``deep`` on the C step (the class docstring), else L3's."""
        if self._ctx is None or self.scene or self.deep or self.entity is None:
            if self._ctx is not None:
                self._hooks(False)
            return super().step(pad, writes=writes, timeout_us=timeout_us)
        pf = pad_floats(pad)
        ws = tuple((va, bytes(d)) for va, d in writes)
        if len(ws) > MAXW - 1 or sum(len(d) for _, d in ws) > WBUF:
            self._hooks(False)
            return super().step(pad, writes=writes, timeout_us=timeout_us)
        self._hooks(True)
        io = self._io
        ctypes.memmove(io.pad, pf, 72)
        off = 0
        for i, (va, d) in enumerate(ws):
            io.wva[i], io.wlen[i] = va, len(d)
            ctypes.memmove(ctypes.addressof(io.wdata) + off, d, len(d))
            off += len(d)
        io.nw = len(ws)
        if pad.cam is not None:
            self._cam = struct.pack("<2f", *pad.cam)
        elif pad.yaw is not None:
            self._cam = camera_dir(pad.yaw)
        if self._cam is not None:
            io.cam_set = 1
            ctypes.memmove(io.cam, self._cam, 8)
        else:
            io.cam_set = 0
        io.do_poll = not self._polled and self.k > self._first
        timeout_us = timeout_us or UPDATE_US
        io.timeout_s = timeout_us / 1e6
        self._row = self._cam_used = self._exit = None
        self._in = False
        self._assert, self._tsc, self._quiet, self._leaving = None, 0, 0, False
        uc = self.uc
        uc._hook_exception = None
        rc = self._lib.fl3_step(self._ctx)
        if rc == NEED_PY:
            self._hooks(False)
            return super().step(pad, writes=writes, timeout_us=timeout_us)
        self._polled = False
        if rc == BATCH_ERR:
            raise UcError(io.emu_err)
        self._entry = entry = ((io.pv, pf), *ws)
        self._in = bool(io.in_)
        exc = UcError(io.emu_err) if io.emu_err else UcError(io.hook_err) if io.hook_err else uc._hook_exception
        if exc is not None:
            if not isinstance(exc, UcError):
                raise exc
            kind = m[1].lower() if (m := re.search(r"UC_ERR_(\w+)", str(exc))) else "cpu error"
            raise L3Error(f"{exc} at {io.eip:#x}", f"{'unmapped' if 'unmapped' in kind else kind}@{io.eip:#x}")
        if self._assert:
            raise L3Error(*self._assert)
        if self._leaving:
            raise LevelExit(f"{PLAYER_UPDATE:#x} reached a level exit's unload {l3.UNLOAD:#x}(scene, 0): stopped at "
                            "its entry")
        if io.eip != _STOP:
            raise L3Error(f"{PLAYER_UPDATE:#x} did not return within {timeout_us} us (at {io.eip:#x})",
                          f"runaway@{io.eip:#x}")
        if not io.row_done:
            raise L3Error(f"step {self.k}: the player's update didn't run", "no player update")
        cam_used = self._cam_used = bytes(io.cam_used) if io.cam_used_set else None
        blocks = iter([(io.ob_va[i], bytes(io.ob[i][:io.ob_n[i]])) for i in range(io.nob)])

        def read(va: int, n: int) -> bytes:        # obs.read's reads, in its order: the hook's blocks
            at, data = next(blocks)
            if (at, len(data)) != (va, n):
                raise AssertionError(f"the C step's blocks aren't obs.read's: {va:#x}+{n:#x}")
            return data
        o = _obs.read(read, self.entity, cam_used, deep=False)
        zone = self.zone_at(o.feet) if self.zone_at else None
        self._row = row = Row(self.k, o.pos, o.state, o.hp, zone, entry, cam_used, frozenset(self.taint), o)
        self.k += 1
        return row if self._exit is None else row._replace(exit=self._exit)
