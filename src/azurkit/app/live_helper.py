"""A minimal, read-only root helper the app's Live runs on macOS (Modkit's
``live_helper``, D257).

The player may start xemu themselves (upstream, no QMP, no shared RAM). On macOS
a same-user process can't take another's mach task port without root, and the
hardened runtime locks even root out, but the fork's and upstream's unsigned
macOS builds are ad-hoc signed without it, so a root process may read them. This
helper is that root process. The app asks for the admin password once (an
``osascript ... with administrator privileges`` prompt, ``azurkit.app.xemu``'s
``start_helper``); the privileged shell copies this file into a **root-owned**
temp directory and runs that copy with macOS's own root-owned Python (``-I -S``,
an empty environment), so no code root runs can be changed by the user
afterwards. The helper:

- reads only a process of the app's own user (its uid and real uid both,
  checked first: another account's process is refused, even one that took a
  quit xemu's pid);
- takes xemu's mach task port (``task_for_pid``), finds its guest-RAM region (64
  or 128 MiB, the page directory self-mapping) and reads it **read-only**
  (``mach_vm_read_overwrite``); it never writes the task, launches anything or
  reads any file but xemu's own memory;
- listens on a unix socket in the app's private ``0700`` directory (the socket
  the app's user's, ``0600``), serves one connection at a time and only from
  the app's own process (``LOCAL_PEERPID``), so Live may drop and reconnect
  without a new prompt, and answers just the **physical** byte ranges Live asks
  for: the page walk and every game read stay in the unprivileged app;
- exits once the app's process or xemu's is gone, the socket is removed (the
  app quit, or attached again), or no connection came within :data:`FIRST_S`.

The protocol: a ``{"ok":true,"size":S,"pd":P}`` line (or ``{"ok":false,...}``),
then, per request, ``<pa:u32 LE><n:u32 LE>`` from the client and ``<status:u8>``
plus ``n`` bytes (status 0) or nothing (status 1, out of range) back
(``azurkit.tools.randomizer.live.link``'s ``MacHelperLink``). Self-contained:
stdlib and ctypes only, no ``azurkit`` import (the app never imports it: it
copies this file), and Python 3.9 (the Command Line Tools'), so the copy root
runs needs nothing else.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import shutil
import socket
import struct
import sys
import time

PAGE = 0x1000
CR3 = 0xF000
PDE_BASE = 0xC0300000
RAM_SIZES = (64 << 20, 128 << 20)
READ_MAX = PAGE                       # Live never asks for more than a page at once (AZ-346)
FIRST_S = 30.0                        # the app connects within this of the prompt, or the helper exits
TICK_S = 1.0                          # how often a waiting helper checks the app, xemu and its socket


# ---------------------------------------------------------------- the page directory (self-contained)

def maps_itself(reader, pd: int) -> bool:
    """Whether physical page ``pd`` is a page directory: its ``PDE_BASE`` entry is
    present, a 4 KiB mapping, and its own frame."""
    if pd % PAGE:
        return False
    try:
        pde = struct.unpack("<I", reader(pd + 4 * (PDE_BASE >> 22), 4))[0]
    except OSError:
        return False
    return pde & 0x81 == 1 and pde & 0xFFFFF000 == pd


def page_directory(reader, size: int) -> int | None:
    """The guest's page directory: ``CR3`` when it self-maps, else the first
    page-aligned frame that does; None while the kernel hasn't set paging up."""
    if maps_itself(reader, CR3):
        return CR3
    return next((pa for pa in range(0, size - PAGE + 1, PAGE) if maps_itself(reader, pa)), None)


def validate(reader, size: int) -> int | None:
    """``pd`` when a region of ``size`` bytes is an Xbox guest RAM (a sane size and
    a page directory), else None."""
    return page_directory(reader, size) if size in RAM_SIZES else None


# ---------------------------------------------------------------- the peer check

def peer_pid(conn: socket.socket) -> int | None:
    """The pid of the process at the other end of the unix socket ``conn``
    (``LOCAL_PEERPID`` on macOS, ``SO_PEERCRED`` on Linux); None if unknown
    (always on Windows, which has no unix sockets here)."""
    if sys.platform == "win32":
        return None
    try:
        if sys.platform == "darwin":
            return struct.unpack("<i", conn.getsockopt(0, 0x002, 4))[0]   # SOL_LOCAL, LOCAL_PEERPID
        buf = conn.getsockopt(socket.SOL_SOCKET, getattr(socket, "SO_PEERCRED", 17), 12)
        return struct.unpack_from("<iII", buf, 0)[0]                      # struct ucred: pid, uid, gid
    except (OSError, AttributeError):
        return None


def alive(pid: int) -> bool:
    """Whether process ``pid`` still exists (a signal-0 probe)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True                                        # it exists, only not ours to signal
    return True


# ---------------------------------------------------------------- the protocol

def _recvall(conn: socket.socket, n: int) -> bytes:
    out = bytearray()
    while len(out) < n:
        chunk = conn.recv(n - len(out))
        if not chunk:
            break
        out += chunk
    return bytes(out)


def _hello(conn: socket.socket, doc: dict) -> None:
    conn.sendall(json.dumps(doc).encode() + b"\n")


def serve(conn: socket.socket, reader, size: int) -> None:
    """Greet ``conn`` with the guest's page directory and serve its physical reads
    until EOF; every read is bounded and read-only."""
    pd = validate(reader, size)
    if pd is None:
        _hello(conn, {"ok": False, "error": "xemu's guest RAM has no page directory yet (is it booting?)"})
        return
    _hello(conn, {"ok": True, "size": size, "pd": pd})
    while True:
        head = _recvall(conn, 8)
        if len(head) < 8:
            return                                         # EOF: Live closed, or the app quit
        pa, n = struct.unpack("<II", head)
        if n == 0 or n > READ_MAX or pa + n > size:
            conn.sendall(b"\x01")
            continue
        try:
            data = reader(pa, n)
        except OSError:
            conn.sendall(b"\x01")
            continue
        conn.sendall(b"\x00" + data)


def listen(srv: socket.socket, reader, size: int, allowed, going, first_s: float = FIRST_S,
           error: str = "") -> None:
    """Serve ``srv``'s connections one at a time while ``going()``: a peer that
    ``allowed(conn)`` refuses is told so and dropped; ``error`` (not empty) is
    the first peer's only answer. Returns when ``going()`` turns false, ``srv``
    closes, or no connection came within ``first_s``."""
    srv.settimeout(TICK_S)
    end, served = time.monotonic() + first_s, False
    while going():
        try:
            conn, _ = srv.accept()
        except socket.timeout:                             # TimeoutError from 3.10; socket.timeout on 3.9
            if not served and time.monotonic() > end:
                return
            continue
        except OSError:
            return                                         # the listener closed
        served = True
        conn.settimeout(None)
        try:
            if not allowed(conn):
                _hello(conn, {"ok": False, "error": "peer is not the app"})
            elif error:
                _hello(conn, {"ok": False, "error": error})
            else:
                serve(conn, reader, size)
        except OSError:
            pass                                           # that peer went away: wait for the next
        finally:
            conn.close()
        if error:
            return


def owner(pid: int) -> tuple[int, int] | None:
    """``(uid, real uid)`` of process ``pid`` (macOS ``proc_pidinfo``'s
    ``PROC_PIDTBSDINFO``: ``pbi_uid`` and ``pbi_ruid``); None when it is gone or
    unknown (not macOS)."""
    size = 136                                             # sizeof(struct proc_bsdinfo)
    try:
        buf = ctypes.create_string_buffer(size)
        n = ctypes.CDLL(None, use_errno=True).proc_pidinfo(ctypes.c_int(pid), 3, ctypes.c_uint64(0), buf, size)
    except (OSError, AttributeError, TypeError):
        return None
    if n != size or struct.unpack_from("<I", buf, 12)[0] != pid:
        return None
    uid, _gid, ruid = struct.unpack_from("<III", buf, 20)
    return uid, ruid


# ---------------------------------------------------------------- mach (the real root path; not unit-tested)

class _VmRegion:
    """``task_for_pid`` and ``mach_vm_read_overwrite`` through libc; a reader over
    one region's physical bytes."""

    def __init__(self, pid: int):
        libc = ctypes.CDLL(None, use_errno=True)
        self._libc = libc
        task = ctypes.c_uint(0)
        kr = libc.task_for_pid(libc.mach_task_self(), ctypes.c_int(pid), ctypes.byref(task))
        if kr != 0:
            raise OSError(f"task_for_pid failed ({kr}): run the app's helper as root, or the build has the "
                          "hardened runtime")
        self._task = task.value

    def regions(self):
        """Each ``(base, size)`` sub-map of the task, in address order."""
        libc = self._libc
        addr = ctypes.c_ulonglong(0)
        while True:
            size = ctypes.c_ulonglong(0)
            info = (ctypes.c_uint * 10)()
            count = ctypes.c_uint(10)
            obj = ctypes.c_uint(0)
            # mach_vm_region(task, &addr, &size, VM_REGION_BASIC_INFO_64(9), info, &count, &obj)
            kr = libc.mach_vm_region(self._task, ctypes.byref(addr), ctypes.byref(size), 9,
                                     ctypes.byref(info), ctypes.byref(count), ctypes.byref(obj))
            if kr != 0:
                return
            yield addr.value, size.value
            addr = ctypes.c_ulonglong(addr.value + size.value)

    def reader_at(self, base: int):
        libc = self._libc

        def read(pa: int, n: int) -> bytes:
            buf = ctypes.create_string_buffer(n)
            out = ctypes.c_ulonglong(0)
            kr = libc.mach_vm_read_overwrite(self._task, ctypes.c_ulonglong(base + pa),
                                             ctypes.c_ulonglong(n), ctypes.cast(buf, ctypes.c_void_p),
                                             ctypes.byref(out))
            if kr != 0 or out.value != n:
                raise OSError(f"mach_vm_read_overwrite failed ({kr}) at {pa:#x}")
            return buf.raw
        return read


def _find_guest_ram(vm: _VmRegion) -> tuple[int, int] | None:
    """The ``(base, size)`` of xemu's guest RAM: a region the right size whose
    bytes hold a page directory."""
    for base, size in vm.regions():
        if size in RAM_SIZES and validate(vm.reader_at(base), size) is not None:
            return base, size
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="the app's Live: its read-only macOS attach helper (D257)")
    ap.add_argument("--pid", type=int, required=True, help="xemu's process id")
    ap.add_argument("--socket", required=True, help="the unix socket to listen on (in the app's 0700 dir)")
    ap.add_argument("--uid", type=int, required=True, help="the app's uid: the socket's owner")
    ap.add_argument("--peer", type=int, required=True, help="the app's pid: no other process is served")
    args = ap.parse_args(argv)

    error, reader, size = "", None, 0
    try:
        if owner(args.pid) != (args.uid, args.uid):
            raise OSError("that process isn't the app's user's (or it quit): the helper reads only yours")
        vm = _VmRegion(args.pid)
        region = _find_guest_ram(vm)
        if region is None:
            error = "no Xbox guest RAM in that process (is it running the game?)"
        else:
            base, size = region
            reader = vm.reader_at(base)
    except OSError as exc:
        error = str(exc)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        if os.path.lexists(args.socket):
            os.unlink(args.socket)
        srv.bind(args.socket)
        os.chown(args.socket, args.uid, -1)                # the app's user may connect, nobody else
        os.chmod(args.socket, 0o600)
        srv.listen(1)
        going = lambda: (os.path.exists(args.socket) and alive(args.peer)       # noqa: E731
                         and (bool(error) or alive(args.pid)))
        listen(srv, reader, size, lambda c: peer_pid(c) == args.peer, going, error=error)
    finally:
        srv.close()
        try:
            os.unlink(args.socket)
        except OSError:
            pass
        _remove_own_copy()
    return 1 if error else 0


def _remove_own_copy() -> None:
    """Remove the root-owned temp dir this copy was run from, so nothing of the
    helper is left behind (only its own ``azurik-live-helper.*`` dir)."""
    here = os.path.dirname(os.path.abspath(__file__))
    if os.path.basename(here).startswith("azurik-live-helper."):
        shutil.rmtree(here, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
