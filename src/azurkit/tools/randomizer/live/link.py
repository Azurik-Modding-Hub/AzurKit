"""The live tracker's link to a running xemu's guest memory (Step R1.26, D249).

Live attaches to an xemu that is already running (it never launches one: the app's Play does, :mod:`azurkit.app.xemu`)
and only reads guest memory (it never writes it), with no pause, through the first of the ways in that answers as xemu
(:func:`open_first`; the macOS admin attach's helper too, :class:`MacHelperLink`):

1. the fork's shared guest RAM (``XEMU_RAM_SHM``; macOS and Linux): read through a read-only view (Python maps
   it read-write), a VA through the guest's page tables (:mod:`azurik_mod.sim.pages`);
2. QMP (``-qmp tcp:127.0.0.1:4444,server=on,wait=off`` at launch; any xemu): HMP ``x`` only, which reads a VA
   while the game runs.

Live reads no gdbstub (D257, the owner: "i dont want slow mode": it stops the game for each read): a ``gdb:``
endpoint is refused by name (:data:`NO_GDB`), and a saved list loses its ``gdb:`` items with a note
(:func:`without_gdb`). The endpoints come from ``AZURIK_XEMU_LIVE`` (:func:`endpoints`: ``shm:<name>``,
``qmp:<host>:<port>`` and ``qmp:unix:<path>``, comma-separated), else the list the tracker saved, else
:data:`DEFAULT` (shared RAM, then QMP). Live never binds or listens, and by discovery it reads no automated xemu
(``-name xemu-fork-auto``, D248): an endpoint the user names is read whatever its name. A link knows nothing of
the game (:mod:`azurkit.tools.randomizer.live` reads it); ``str()`` of a :class:`LiveError` is the tracker's text,
naming one fix. Guest bytes stay in memory: nothing here prints them.
"""

from __future__ import annotations

import json
import os
import re
import socket
import struct
import sys
import time
from dataclasses import dataclass
from multiprocessing import shared_memory

from azurkit.tools.randomizer.live import pages
from azurkit.tools.randomizer.live.errors import LiveError

ENV = "AZURIK_XEMU_LIVE"
SHM_NAME = "azurik-live"
QMP_PORT = 4444
DEFAULT = f"shm:{SHM_NAME},qmp:127.0.0.1:{QMP_PORT}"
NO_GDB = "Live reads no gdbstub (it pauses the game, D257): name xemu's QMP, qmp:<host>:<port>"
AUTOMATED = "xemu-fork-auto"        # the fork's agent and bench xemus' -name (D248)
QMP_ARG = f"-qmp tcp:127.0.0.1:{QMP_PORT},server=on,wait=off"
PORT_TAKEN = (f"If xemu closes at once, port {QMP_PORT} is taken: use another port in the line, and enter it "
              f"in Endpoints… (right-click).")
RAM_SIZES = (64 << 20, 128 << 20)   # the Xbox's RAM: xemu.toml's mem_limit, 64 or 128 MiB
CONNECT_S, GREET_S, REPLY_S = 0.3, 1.0, 1.0
SCAN_EVERY_S = 2.0                  # a shared RAM with no page directory yet (booting) is searched this often


class LinkLost(LiveError):
    """The link closed: xemu quit, or its socket or shared memory went away."""


ATTACH = "Attach to xemu with admin…"   # the status line's right-click on macOS (D257)


def no_xemu(platform: str = sys.platform) -> str:
    """The status when nothing answers: on macOS the admin attach comes first (D257), else the QMP line."""
    if platform == "darwin":
        return (f"No xemu answers. Right-click: {ATTACH} reads the xemu you started; or click to copy a QMP "
                f"launch line (hover for how).")
    return "No xemu answers. Start xemu with QMP: click to copy its launch line (hover for how)."


NO_XEMU = no_xemu()
ONLY_AUTOMATED = f"Only an automated xemu ({AUTOMATED}) answers: Live never reads those. Start your own xemu."


def not_xemu(where: str) -> str:
    return f"{where} answers but isn't xemu: quit what holds it, or set another port in Endpoints… (right-click)."


def in_use(what: str, where: str) -> str:
    return f"xemu's {what} at {where} is in use by another client: detach it."


def monitor_not_qmp(where: str) -> str:
    return (f"{where} is xemu's -monitor, not -qmp: start xemu with -qmp instead (right-click copies the "
            f"line).")


AUTOMATION = f'[automation]\nram_shm = "{SHM_NAME}"\nqmp = "tcp:127.0.0.1:{QMP_PORT},server=on,wait=off"'
"""The fork v0.15's ``[automation]`` table, Live's own endpoints (docs/RANDOMIZER.md#live): set once in xemu's own
``xemu.toml`` with xemu closed, it opens shared RAM and QMP at every launch, so no launch line is needed."""


def automation_line(platform: str = sys.platform) -> str | None:
    """The tracker's hover line for :data:`AUTOMATION` (Step X.32b): once, not per launch, for the owner's fork from
    v0.15 on, on the systems it runs (the launch lines stay for every other xemu and older fork builds)."""
    if platform == "win32":
        return None
    where = "~/Library/Application Support/xemu/xemu/xemu.toml" if platform == "darwin" else "its xemu.toml"
    return f"Or once, for the xemu fork v0.15 and later (then no launch line): with xemu closed, add to {where}:\n" \
           f"{AUTOMATION}"


def setup_lines(platform: str = sys.platform) -> list[tuple[str, str]]:
    """This OS's one step to a Live that never pauses the game, once per launch: (what to do, the line),
    the first for any xemu (docs/RANDOMIZER.md#live)."""
    if platform == "darwin":
        return [("quit xemu, then paste this into Terminal", f"open -n -a xemu --args {QMP_ARG}"),
                ("the fork: quit it, then", f'open -n -a "<the fork\'s xemu.app>" --env XEMU_RAM_SHM={SHM_NAME}')]
    if platform == "win32":
        return [("start xemu from a shortcut to xemu.exe with this after its Target's closing quote",
                 f" {QMP_ARG}")]
    return [("add this to the line that starts xemu (xemu, flatpak run app.xemu.xemu or the AppImage)", QMP_ARG)]


@dataclass(frozen=True)
class Endpoint:
    """Where Live looks for xemu: ``kind`` "shm" or "qmp"; ``target`` a shared-memory name, a unix
    socket's path or (host, port); ``explicit`` when the user named it (an automated xemu is read too)."""
    kind: str
    target: str | tuple[str, int]
    explicit: bool = False

    @property
    def where(self) -> str:
        """How texts name it: ``127.0.0.1:4444``, ``unix:<path>``, ``shared memory azurik-live``."""
        if self.kind == "shm":
            return f"shared memory {self.target}"
        if self.kind == "helper":
            return "the admin helper"
        return f"unix:{self.target}" if isinstance(self.target, str) else "%s:%d" % self.target

    @property
    def short(self) -> str:
        """``:4444`` on this machine's loopback, else :attr:`where`."""
        return f":{self.target[1]}" if isinstance(self.target, tuple) and self.target[0] == "127.0.0.1" \
            else self.where

    def __str__(self) -> str:
        if self.kind == "shm":
            return f"shm:{self.target}"
        if self.kind == "helper":
            return f"helper:{self.target}"
        return f"{self.kind}:" + (f"unix:{self.target}" if isinstance(self.target, str) else "%s:%d" % self.target)


def _items(text: str) -> list[str]:
    return [s for s in (s.strip() for s in text.split(",")) if s]


def parse(text: str, explicit: bool = True) -> list[Endpoint]:
    """``AZURIK_XEMU_LIVE``'s grammar: the endpoints in the order given; ``ValueError`` naming an item it
    can't read, a ``gdb:`` one with :data:`NO_GDB`."""
    out = []
    for item in _items(text):
        kind, _, rest = item.partition(":")
        if kind == "shm" and re.fullmatch(r"[A-Za-z0-9._-]{1,30}", rest):
            out.append(Endpoint("shm", rest, explicit))
        elif kind == "qmp" and rest.startswith("unix:") and rest[5:]:
            out.append(Endpoint("qmp", rest[5:], explicit))
        elif kind == "qmp" and (m := re.fullmatch(r"([^:\s,]+):(\d{1,5})", rest)) and 0 < int(m[2]) < 65536:
            out.append(Endpoint("qmp", (m[1], int(m[2])), explicit))
        elif kind == "gdb":
            raise ValueError(f"{item!r}: {NO_GDB}")
        else:
            raise ValueError(f"{item!r} is none of shm:<name>, qmp:<host>:<port>, qmp:unix:<path>")
    return out


def without_gdb(saved: str) -> tuple[str, str]:
    """A list saved before D257 with its ``gdb:`` items taken out: (the rest, a note naming them; "" when it
    had none)."""
    items = _items(saved)
    gone = [s for s in items if s.partition(":")[0] == "gdb"]
    if not gone:
        return saved, ""
    return ",".join(s for s in items if s not in gone), f"Endpoints… dropped {', '.join(gone)}: {NO_GDB}."


def endpoints(env=None, saved: str = "") -> list[Endpoint]:
    """The endpoints Live probes, in order: ``AZURIK_XEMU_LIVE``'s when it is set, else ``saved`` (the
    tracker's Endpoints…), else :data:`DEFAULT`'s. Named endpoints replace the defaults and are explicit
    (D-m). :class:`LiveError` naming a list it can't read."""
    env = os.environ if env is None else env
    named = (env.get(ENV) or "").strip()
    try:
        eps = parse(named or saved)
    except ValueError as exc:
        raise LiveError(f"{ENV if named else 'Endpoints…'}: {exc}") from None
    return eps or parse(DEFAULT, explicit=False)


class _Probe(Exception):
    """An endpoint that didn't answer as xemu: ``rank`` orders the texts (the most useful wins), 1 being
    "nothing there"."""

    def __init__(self, rank: int, text: str = NO_XEMU):
        super().__init__(text)
        self.rank, self.text = rank, text


def _pieces(va: int, n: int):
    """(va, length) pieces of ``[va, va + n)`` that never cross a 4 KiB page (AZ-346: one unmapped page fails
    its own piece, as every link's read does)."""
    while n > 0:
        k = min(n, pages.PAGE - (va & 0xFFF))
        yield va, k
        va, n = va + k, n - k


class Link:
    """A read-only view of a running xemu's guest memory."""

    kind = ""
    period = 1.0          # s between polls

    def __init__(self, ep: Endpoint):
        self.ep, self.fork, self.name = ep, False, ""

    def label(self) -> str:
        """Which xemu, and how: ``xemu fork, shared RAM``, ``xemu, QMP :4444``."""
        raise NotImplementedError

    def read(self, va: int, n: int) -> bytes:
        """``n`` bytes at guest VA ``va``; ``OSError`` for an unmapped page, :class:`LinkLost` once closed."""
        raise NotImplementedError

    def read_many(self, wants: list[tuple[int, int]]) -> list[bytes | None]:
        """Each (va, n) of ``wants`` read, None where it isn't mapped."""
        out = []
        for va, n in wants:
            try:
                out.append(self.read(va, n))
            except OSError:
                out.append(None)
        return out

    def refresh(self) -> None:
        """Look again: the shared memory's name is opened anew (:class:`LinkLost` when it is gone)."""

    def close(self) -> None:
        pass


class SharedRamLink(Link):
    """The fork's ``XEMU_RAM_SHM``: guest RAM in named POSIX shared memory, read through a read-only view
    (Python maps POSIX shared memory read-write, so that view is the guard), each VA through the guest's page
    tables. An xemu still booting has none: its reads fail until the kernel sets paging up."""

    kind, period = "shm", 0.25

    def __init__(self, ep: Endpoint):
        super().__init__(ep)
        self.fork = True
        self._open(_Probe(1))

    def _open(self, absent: Exception) -> None:
        self._view = self._read = self._pd = None
        self._scanned = -SCAN_EVERY_S
        try:
            shm = shared_memory.SharedMemory(self.ep.target, track=False)
        except FileNotFoundError:
            raise absent from None
        except OSError:
            raise _Probe(3, not_xemu(self.ep.where)) from None
        if shm.size not in RAM_SIZES:
            shm.close()
            raise _Probe(3, not_xemu(self.ep.where))
        self._shm, self._view = shm, shm.buf.toreadonly()

    def label(self) -> str:
        return "xemu fork, shared RAM"

    def _reader(self):
        if self._view is None:
            raise LinkLost(f"{self.ep.where} is closed")
        if self._pd is None or not pages.maps_itself(self._view, self._pd):
            self._read = None
            if time.monotonic() - self._scanned < SCAN_EVERY_S:
                raise OSError("guest RAM has no page directory yet")
            self._scanned = time.monotonic()
            if (pd := pages.find_page_directory(self._view)) is None:
                raise OSError("guest RAM has no page directory yet")
            self._pd, self._read = pd, pages.ram_reader(self._view, pd)
        return self._read

    def read(self, va: int, n: int) -> bytes:
        return self._reader()(va, n)

    def refresh(self) -> None:
        """A crashed xemu leaves its name behind with its RAM frozen, and a new one replaces the object under
        an old mapping: open the name again."""
        self.close()
        self._open(LinkLost(f"{self.ep.where} is gone: xemu quit"))

    def close(self) -> None:
        if self._view is not None:
            self._read = None
            self._view.release()
            self._view = None
            self._shm.close()


class QmpLink(Link):
    """QMP, any xemu: HMP ``x /<N>xw <va>`` reads a VA through CPU 0's page tables with no pause. Only the
    commands in :data:`ALLOWED` are sent, ``x`` the only HMP one."""

    kind, period = "qmp", 0.5
    ALLOWED = frozenset({"qmp_capabilities", "query-name", "query-xemu-status", "human-monitor-command"})
    X = re.compile(r"x /\d+xw 0x[0-9a-f]+")

    def __init__(self, ep: Endpoint):
        super().__init__(ep)
        self._sock, self._buf = _connect(ep), b""
        try:
            try:
                greeting = self._line(GREET_S)
            except TimeoutError:      # a second client waits in the backlog
                raise _Probe(4, in_use("QMP", ep.short)) from None
            except LinkLost:
                raise _Probe(3, not_xemu(ep.where)) from None
            if _HMP_BANNER.search(greeting):
                raise _Probe(5, monitor_not_qmp(ep.where))
            try:
                hello = json.loads(greeting)
                assert isinstance(hello, dict) and "QMP" in hello
                self._cmd("qmp_capabilities")
                self.name = (self._cmd("query-name") or {}).get("name", "")
            except (ValueError, AssertionError, TimeoutError, LinkLost, _QmpError):
                raise _Probe(3, not_xemu(ep.where)) from None
            if self.name == AUTOMATED and not ep.explicit:
                raise _Probe(2, ONLY_AUTOMATED)
            try:
                self._cmd("query-xemu-status")       # the fork's own command
                self.fork = True
            except _QmpError as exc:
                if exc.cls != "CommandNotFound":
                    raise _Probe(3, not_xemu(ep.where)) from None
            except (ValueError, TimeoutError, LinkLost):
                raise _Probe(3, not_xemu(ep.where)) from None
        except BaseException:
            self._sock.close()
            raise

    def label(self) -> str:
        return f"xemu{' fork' if self.fork else ''}, QMP {self.ep.short}"

    def _line(self, timeout: float) -> bytes:
        return _line(self, timeout)

    def _cmd(self, execute: str, arguments: dict | None = None):
        if execute not in self.ALLOWED or (
                execute == "human-monitor-command" and not self.X.fullmatch(arguments["command-line"])):
            raise RuntimeError(f"QMP {execute} {arguments or ''} is not a read Live may send")
        msg = {"execute": execute} | ({"arguments": arguments} if arguments else {})
        _send(self._sock, json.dumps(msg).encode() + b"\n")
        while True:
            reply = json.loads(self._line(REPLY_S))
            if "return" in reply:
                return reply["return"]
            if "error" in reply:
                raise _QmpError(reply["error"].get("class", ""), reply["error"].get("desc", ""))
            # an asynchronous event ("event"): skipped

    def read(self, va: int, n: int) -> bytes:
        out = bytearray()
        for a, k in _pieces(va, n):
            start = a & ~3
            words = (a + k - start + 3) // 4
            try:
                text = self._cmd("human-monitor-command", {"command-line": f"x /{words}xw {start:#x}"})
            except (TimeoutError, ValueError):
                raise LinkLost(f"xemu's QMP at {self.ep.short} stopped answering") from None
            except _QmpError as exc:
                raise OSError(f"read {a:#x}: {exc}") from None
            out += x_words(text, start, words)[a - start:a - start + k]
        return bytes(out)

    def close(self) -> None:
        self._sock.close()


class _QmpError(Exception):
    def __init__(self, cls: str, desc: str):
        super().__init__(f"{cls}: {desc}")
        self.cls = cls


_HMP_BANNER = re.compile(rb"QEMU .*monitor")      # searched: a telnet -monitor sends IAC options first


def x_words(text: str, start: int, words: int) -> bytes:
    """HMP ``x /<words>xw <start>``'s output (``<addr>: 0x%08x ...``, 16 bytes a line) as little-endian
    bytes; ``OSError`` where it says "Cannot access memory" (an unmapped page) or stops short."""
    vals: list[int] = []
    for line in text.splitlines():
        if not (m := re.match(r"\s*([0-9a-fA-F]+):(.*)", line)):
            continue
        if "Cannot access memory" in m[2]:
            raise OSError(f"read {int(m[1], 16):#x}: not mapped")
        if int(m[1], 16) == start + 4 * len(vals):
            vals += [int(v, 16) for v in re.findall(r"0x([0-9a-fA-F]+)", m[2])]
    if len(vals) < words:
        raise OSError(f"read {start:#x}: x gave {len(vals)} of {words} words")
    return struct.pack(f"<{words}I", *(v & 0xFFFFFFFF for v in vals[:words]))


def _connect(ep: Endpoint) -> socket.socket:
    """A connection to ``ep`` (only ever a client: Live never binds or listens)."""
    try:
        if isinstance(ep.target, str):
            sock = socket.socket(getattr(socket, "AF_UNIX"), socket.SOCK_STREAM)
            sock.settimeout(CONNECT_S)
            sock.connect(ep.target)
        else:
            sock = socket.create_connection(ep.target, timeout=CONNECT_S)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except (OSError, AttributeError):
        raise _Probe(1) from None
    return sock


def _send(sock: socket.socket, data: bytes) -> None:
    try:
        sock.sendall(data)
    except OSError as exc:
        raise LinkLost(f"xemu closed the connection ({exc.__class__.__name__})") from None


def _recv(link, end: float) -> None:
    """More of ``link``'s socket into its buffer by ``end`` (monotonic); ``TimeoutError`` past it,
    :class:`LinkLost` when it closed."""
    left = end - time.monotonic()
    if left <= 0:
        raise TimeoutError
    link._sock.settimeout(left)
    try:
        data = link._sock.recv(65536)
    except TimeoutError:
        raise
    except OSError as exc:
        raise LinkLost(f"xemu closed the connection ({exc.__class__.__name__})") from None
    if not data:
        raise LinkLost("xemu closed the connection")
    link._buf += data


def _line(link, timeout: float) -> bytes:
    end = time.monotonic() + timeout
    while (k := link._buf.find(b"\n")) < 0:
        _recv(link, end)
    line, link._buf = link._buf[:k + 1], link._buf[k + 1:]
    return line


class _PhysProxy:
    """A bytes-like view of guest RAM over a :class:`MacHelperLink`: each slice is
    one physical read request the helper answers, so the page walk
    (:func:`pages.ram_reader`) runs unprivileged in the tracker."""

    def __init__(self, link: "MacHelperLink", size: int):
        self._link, self._size = link, size

    def __len__(self) -> int:
        return self._size

    def __getitem__(self, s: slice) -> bytes:
        return self._link._phys(s.start or 0, (s.stop or 0) - (s.start or 0))


class MacHelperLink(Link):
    """The macOS admin helper (D257): a unix socket to a root helper
    (:mod:`azurkit.app.live_helper`) that reads xemu's process memory. The
    helper serves physical reads only; this link walks the guest's page tables
    over them (:func:`pages.ram_reader`), so no game read leaves the
    unprivileged app. The helper is started before this link opens, by the one
    admin prompt (:func:`azurkit.app.xemu.start_helper`, the app's Attach)."""

    kind, period = "helper", 0.25

    def __init__(self, ep: Endpoint):
        super().__init__(ep)
        self._sock, self._buf = _connect(ep), b""
        try:
            try:
                hello = json.loads(self._line(GREET_S))
            except (ValueError, TimeoutError, LinkLost):
                raise _Probe(3, not_xemu(ep.where)) from None
            if not hello.get("ok"):          # the next endpoint is still tried; this text, if none answers
                raise _Probe(4, f"The admin helper can't read xemu: {hello.get('error', 'unknown')}.")
            self._size, self._pd = int(hello["size"]), int(hello["pd"])
            self._reader = pages.ram_reader(_PhysProxy(self, self._size), self._pd)
        except BaseException:
            self._sock.close()
            raise

    def label(self) -> str:
        return "xemu, admin helper"

    def _line(self, timeout: float) -> bytes:
        return _line(self, timeout)

    def _take(self, n: int, timeout: float) -> bytes:
        end = time.monotonic() + timeout
        while len(self._buf) < n:
            _recv(self, end)
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def _phys(self, pa: int, n: int) -> bytes:
        """``n`` physical bytes at ``pa`` from the helper; ``OSError`` when it is
        out of the region (the page walk decides what is present)."""
        _send(self._sock, struct.pack("<II", pa, n))
        try:
            if self._take(1, REPLY_S) == b"\x01":
                raise OSError(f"helper: physical {pa:#x} is out of range")
            return self._take(n, REPLY_S)
        except TimeoutError:
            raise LinkLost("the admin helper stopped answering") from None

    def read(self, va: int, n: int) -> bytes:
        return self._reader(va, n)

    def close(self) -> None:
        self._sock.close()


LINKS = {"shm": SharedRamLink, "qmp": QmpLink, "helper": MacHelperLink}


def open_first(eps: list[Endpoint]) -> Link:
    """The link of the first of ``eps`` that answers as xemu, whatever its guest runs; else
    :class:`LiveError` with the most useful text of those that didn't (:data:`NO_XEMU` when nothing
    answers)."""
    best = _Probe(1)
    for ep in eps:
        try:
            return LINKS[ep.kind](ep)
        except _Probe as p:
            best = max(best, p, key=lambda x: x.rank)
    raise LiveError(best.text)
