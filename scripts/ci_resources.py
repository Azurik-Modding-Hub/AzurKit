"""The runner's room during a CI tier, on stdout (Step 4.4ci3): each minute the
free disk under each folder named and the free memory, and as the tier ends
(``STOP`` exists) the lowest of each, so a run the runner shuts down still
names what it ran out of. Those lines are labels and numbers only, never a
folder's path, a file's name or anything read from one.

    python -I scripts/ci_resources.py STOP [--watch=LOG --tier=ID [--until=EPOCH]] LABEL=FOLDER ...

With ``--watch`` it watches the tier too (Step 4.4ci12; run 41521288667's
Windows tier sat silent 3.5 h until the job's limit cut it off, its log never
printed): once ``LOG`` hasn't grown for :data:`STALL_S` (``--stall=SECONDS``
in the tests), or at ``--until`` (seconds since the epoch, the job's clock),
it prints the log's last :data:`TAIL` lines, each cut at :data:`WIDTH`
characters as the step's own tail (the tier's output, never game bytes), and
the tier's processes with their ages, then stops them: xdist's workers
first (each matched by its command line, which is never printed), so
pytest's controller still writes its summary, its failures and the test each
worker was running before it ends, then every process left under the one
``ID`` names (Windows' own id under Git Bash), then that one if it hasn't
ended by itself. So the step ends, prints its summary and fails while the
job has time left; it exits 3 once ``STOP`` exists.

On macOS each line also has Playwright's processes' footprint (its driver and
the browsers it starts, WebKit's pages among them: :func:`footprints`), and
the tier's end what macOS wrote of one that ended (a crash report, a jetsam
kill: :func:`reports`), with the free memory as this watcher last read it
(Step 4.4ci17: the pure tier's WebKit page "Target crashed" on GitHub's 7 GB
Apple Silicon runner, where nothing said its memory).

What a browser's close waits on (:func:`held`, Step 4.4ci18; the ``browser``
fixture's close at its bound and this watch's listing print it): Playwright's
driver answers a close only once the browser's process has ended and every
handle of its stdout, stderr and protocol pipes has closed, and Playwright's
WebKit on Windows starts each of its processes (pages, network, GPU) with
its own stdout and stderr and every handle it may pass on (its
``ProcessLauncherWin.cpp``: ``STARTF_USESTDHANDLES``, ``bInheritHandles``
true), so one that outlives it holds the close, out of reach of the
driver's kill (``taskkill /T`` walks only a live parent's children). So the
listing names, with its memory, each process left running by a parent that
ended, the crash handlers, and the browsers' temporary folders.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

GIB = 1 << 30
SAMPLE_S, PRINT_S = 5, 60
STALL_S = 90 * 60
"""How long the tier's log may stay the same size. pytest writes a dot as each test ends, so a legit quiet stretch
is one test: the slowest is test_characters' variant cases (median 458 s, at most 869 s, in 31 of the gating Mac's
runs). macOS Intel's runner, the slowest, spends about 6x that Mac's time a test: 2 workers x 12138 s on its tier's
210 tests, where the Mac's gate runs them and 360 lighter ones on 8 workers in a median 899 s (the 210 about 60% of
it). So about 45 min there, 87 min at the Mac's worst. Longer than the tier's faulthandler_timeout too (60 min, past
the 45), so a hung test's stacks are in the log before it is printed."""
TAIL, WIDTH = 200, 240
STOPPED = 3
"""The watcher's exit code once it stopped the tier."""
GRACE_S = 10
"""How long the tier's own process has to end by itself once every process under it has been ended."""
SETTLE_S = 120
"""How long pytest's controller has, once its workers have been ended, to write its summary, its failures and the
test each worker was running (xdist's "worker 'gwN' crashed while running ...") and end, the tier with it."""
WORKER = "import sys;exec(eval(sys.stdin.readline()))"
"""On each xdist worker's command line, every OS's, Windows' venv launcher's and its interpreter's alike: execnet's
``gateway_io.popen_bootstrapline``."""
NAMED = re.compile(r"^(?:uv|node|python[\d.]*w?)(?:\.exe)?$|firefox|chrom|webkit|msedge|playwright", re.I)
"""Processes listed even outside the tier's tree (a browser its parent left behind)."""
BROWSER = re.compile(r"firefox|chrom|webkit|msedge|playwright", re.I)
"""A browser's process by its name: Playwright.exe and WebKit's WebKitWebProcess.exe, WebKitNetworkProcess.exe and
WebKitGPUProcess.exe on Windows, firefox.exe, chrome-headless-shell.exe and its crashpad handler."""
CRASH = re.compile(r"^(?:WerFault|WerFaultSecure|wermgr|crashhelper|crashreporter|minidump-analyzer|pingsender|"
                   r"ReportCrash)(?:\.exe)?$", re.I)
"""Crash handlers, always listed: Windows Error Reporting's (a crashed process stays, its handles open, until its
report is written), Firefox's crash helper, reporter, minidump analyzer and ping sender, macOS's ReportCrash."""
MIB = 1 << 20
SAY_S = 10
"""s :func:`held` may take: a listing of the processes and the folders' sizes (``ps`` takes ms; Windows' CIM query 1-3
s on the runner), so a close that never answered still fails promptly, the rest of the folders' sizes left unread."""
LISTED = 20
"""Processes at most in each of :func:`held`'s lists."""
WER = ("CrashDumps", "Microsoft/Windows/WER/ReportQueue", "Microsoft/Windows/WER/ReportArchive")
"""Where Windows Error Reporting writes a crash's dump and report, under the user's and the machine's app data."""
PLAYWRIGHT = re.compile(r"[/\\]playwright[/\\]")
"""On the command line of each of Playwright's processes: its driver (the package's own node) and the browsers it
starts from their folder (``.tools/playwright``), with each process they start, WebKit's pages, network and GPU too,
which launchd starts outside the tier's tree."""
REPORTS = (Path.home() / "Library" / "Logs" / "DiagnosticReports", Path("/Library/Logs/DiagnosticReports"))
"""Where macOS writes a crash report (the user's) and a jetsam event (the system's)."""
ENDINGS = ('subsystem == "com.apple.WebKit" AND (eventMessage CONTAINS "processDidTerminate" OR eventMessage CONTAINS '
           '"MemoryLimit" OR eventMessage CONTAINS "CPULimit" OR eventMessage CONTAINS "kill threshold" OR eventMessage '
           'CONTAINS "nresponsive")')
"""WebKit's own lines (macOS's log) on a process of its that ended or that it ended: why a page's process ended
(``WebPageProxy::processDidTerminate``'s ``reason=``: ``Crash``, ``ExceededMemoryLimit``, ``ExceededCPULimit``...), its
memory and CPU kills and their thresholds, and a process that stopped answering. A WebKit kill writes no report."""


def free_memory() -> tuple[int, int]:
    """(available, total) bytes of this machine's memory, by the system's own count of what it can hand out."""
    if sys.platform == "win32":
        import ctypes

        class Status(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                        ("available", ctypes.c_ulonglong), ("rest", ctypes.c_ulonglong * 5)]
        status = Status(length=ctypes.sizeof(Status))
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            raise ctypes.WinError()
        return status.available, status.total
    pages, size = os.sysconf("SC_PHYS_PAGES"), os.sysconf("SC_PAGE_SIZE")
    if sys.platform == "darwin":
        rows = dict(line.split(":") for line in subprocess.run(["vm_stat"], capture_output=True, text=True, check=True,
                                                               timeout=30).stdout.splitlines() if ":" in line)
        free = sum(int(rows[f"Pages {kind}"].strip(" .")) for kind in ("free", "inactive", "speculative"))
        return free * size, pages * size
    meminfo = dict(line.split(":") for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines())
    return int(meminfo["MemAvailable"].split()[0]) << 10, pages * size


def sample(folders: dict[str, str]) -> dict[str, int]:
    """Each folder's free disk and the free memory, in bytes."""
    room = {label: shutil.disk_usage(folder).free for label, folder in folders.items() if os.path.exists(folder)}
    return room | {"memory": free_memory()[0]}


def line(now: dict[str, int], low: dict[str, int]) -> str:
    return ", ".join(f"{label} {now[label] / GIB:.1f} GiB free (lowest {low[label] / GIB:.1f})" for label in now)


class Growth:
    """A log's quiet time: the seconds since its size last changed (a missing log's size is -1)."""

    def __init__(self, path: str, now: float):
        self.path = path
        self.size, self.since = self._size(), now

    def _size(self) -> int:
        try:
            return os.path.getsize(self.path)
        except OSError:
            return -1

    def quiet(self, now: float) -> float:
        if (size := self._size()) != self.size:
            self.size, self.since = size, now
        return now - self.since


def tail(path: str) -> list[str]:
    """The log's last :data:`TAIL` lines, each cut at :data:`WIDTH` characters."""
    try:
        with open(path, "rb") as f:
            f.seek(max(0, f.seek(0, os.SEEK_END) - (1 << 20)))
            text = f.read().decode("utf-8", "replace")
    except OSError:
        return []
    return [row[:WIDTH] for row in text.splitlines()[-TAIL:]]


def _seconds(age: str) -> int:
    """``ps``'s elapsed time (``[[dd-]hh:]mm:ss``), or plain seconds, in seconds."""
    days, _, clock = age.rpartition("-")
    total = 0
    for part in clock.split(":"):
        total = total * 60 + int(part)
    return total + int(days or 0) * 86400


def _lines(command: list[str], timeout: float = 120) -> list[str]:
    return subprocess.run(command, capture_output=True, text=True, errors="replace", check=True,
                          timeout=timeout).stdout.splitlines()


def processes(timeout: float = 120) -> list[tuple[int, int, int, str, str, int]]:
    """(id, its parent's id, age in seconds, name, command line, memory in bytes: its working set, ``ps``'s rss) of
    each process on this machine, read in at most ``timeout`` s. The command line is read to find xdist's workers
    (:data:`WORKER`) and Playwright's processes (:data:`PLAYWRIGHT`), never printed."""
    if sys.platform == "win32":
        script = ("$now = Get-Date; Get-CimInstance Win32_Process | Where-Object CreationDate | ForEach-Object "
                  "{ ('{0} {1} {2} {3} {4}' -f $_.ProcessId, $_.ParentProcessId, "
                  "[long]($now - $_.CreationDate).TotalSeconds, [long]$_.WorkingSetSize, $_.Name) + [char]9 + "
                  "($_.CommandLine -replace '[\\t\\r\\n]', ' ') }")
        rows = [(*row.partition("\t")[::2], 1) for row in _lines(
            ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand",
             base64.b64encode(script.encode("utf-16-le")).decode()], timeout)]
    else:   # comm last, as macOS's is the program's path, spaces and all; the command lines by id
        commands = dict(row.strip().partition(" ")[::2] for row in _lines(["ps", "-A", "-ww", "-o", "pid=,args="],
                                                                         timeout))
        rows = [(row, commands.get(row.split()[0], ""), 1024) for row in _lines(
            ["ps", "-A", "-o", "pid=,ppid=,etime=,rss=,comm="], timeout) if row.strip()]
    found = []
    for row, command, unit in rows:
        parts = row.split(None, 4)
        if len(parts) == 5 and parts[0].isdigit() and parts[1].isdigit() and parts[3].isdigit():
            found.append((int(parts[0]), int(parts[1]), _seconds(parts[2]), os.path.basename(parts[4].strip()),
                          command, int(parts[3]) * unit))
    return found


def tree(rows: list[tuple[int, int, int, str, str]], root: int) -> list[tuple[int, tuple[int, int, int, str, str]]]:
    """(depth, row) of ``root`` and each process under it, each parent before its children. A child is never older
    than its parent (within the second ``ps`` rounds to): Windows hands an ended parent's id to a new process."""
    children: dict[int, list] = {}
    for row in rows:
        children.setdefault(row[1], []).append(row)
    found, seen = [], set()

    def walk(row, depth):
        seen.add(row[0])
        found.append((depth, row))
        for child in children.get(row[0], ()):
            if child[0] not in seen and child[2] <= row[2] + 1:
                walk(child, depth + 1)
    for row in rows:
        if row[0] == root:
            walk(row, 0)
    return found


def footprints(rows: list[tuple[int, int, int, str, str]]) -> dict[int, tuple[str, int, int]]:
    """{id: (name, footprint, its highest)} in bytes of each of Playwright's processes in ``rows`` (:func:`processes`,
    :data:`PLAYWRIGHT`), by macOS's own count (``proc_pid_rusage``: the phys_footprint that jetsam and WebKit's memory
    kill read); none on the other OSes."""
    if sys.platform != "darwin":
        return {}
    import ctypes
    usage = ctypes.CDLL("/usr/lib/libSystem.B.dylib").proc_pid_rusage
    found = {}
    for pid, _, _, name, command, *_ in rows:
        info = (ctypes.c_uint64 * 40)()   # rusage_info_v4: a 16-byte uuid, then its counters, phys_footprint the 7th
        if PLAYWRIGHT.search(command) and usage(pid, 4, info) == 0:   # (from 0) and lifetime_max_phys_footprint the 28th
            found[pid] = (name, info[9], info[30])
    return found


def reports(since: float, seen: dict[int, tuple[str, int, int, int]]) -> list[str]:
    """What macOS wrote since ``since`` (seconds since the epoch) of a process of Playwright's that ended, of ``seen``
    (``{id: (name, footprint, its highest, the free memory)}`` as this watcher last read each): each crash report's
    exception and each jetsam event's kill with its reason, each with that footprint and free memory, and the free
    memory the jetsam event counted. Names and numbers only."""
    said = []
    for folder, whose in zip(REPORTS, ("the user's", "the system's")):
        try:
            found = sorted((f.stat().st_mtime, f) for f in folder.glob("*.ips") if f.stat().st_mtime >= since)
        except OSError as e:
            said.append(f"{whose} reports unread ({type(e).__name__})")
            continue
        for at, file in found:
            try:
                body = json.loads(file.read_text(encoding="utf-8", errors="replace").partition("\n")[2])
            except (OSError, ValueError) as e:
                said.append(f"a report of {whose} unread ({type(e).__name__})")
                continue
            when = f"at {(at - since) / 60:.0f} min"
            if (pid := body.get("pid")) in seen:   # a crash report
                why = body.get("exception") or {}
                said.append(f"{seen[pid][0]} (id {pid}) crashed {when}: {why.get('type')} ({why.get('signal')}); "
                            + _last(seen[pid]))
            for killed in (p for p in body.get("processes", ()) if p.get("reason") and p.get("pid") in seen):
                status = body.get("memoryStatus") or {}
                free = (status.get("memoryPages") or {}).get("free", 0) * status.get("pageSize", 0)
                said.append(f"{seen[killed['pid']][0]} (id {killed['pid']}) killed by jetsam {when}: {killed['reason']}, "
                            f"memory {free / GIB:.1f} GiB free by its count; " + _last(seen[killed["pid"]]))
    return said


LINE = re.compile(r"^\S+ (\d\d:\d\d:\d\d)\.\d+ +\w+ +([^\[\s]+)\[(\d+)[^\]]*\] \[[^\]]*\] (?:0x[0-9a-f]+ - )?(.*)$",
                  re.M)
"""One of WebKit's lines in macOS's log (``--style compact``): its time, process, process id and message, the
object's address dropped."""


def webkit_said(since: float) -> list[str]:
    """WebKit's lines in macOS's log since ``since`` (seconds since the epoch) on a process that ended (:data:`ENDINGS`),
    each its time, process and message (cut at :data:`WIDTH`), at most 20; past them, every line counted by the call
    that wrote it with its last time (run 41818469100's ended GPU processes were "and 260 more")."""
    try:
        out = subprocess.run(["log", "show", "--style", "compact", "--start",
                              time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(since)), "--predicate", ENDINGS],
                             capture_output=True, text=True, errors="replace", timeout=300).stdout
    except (OSError, subprocess.SubprocessError) as e:
        return [f"its log unread ({type(e).__name__})"]
    lines = LINE.findall(out)
    said = [f"{at} {who}: {what}"[:WIDTH] for at, who, _, what in lines]
    if len(said) <= 20:
        return said
    calls: dict[str, list] = {}
    for at, _, _, what in lines:
        call = calls.setdefault(m[0] if (m := re.search(r"\w+::\w+", what)) else what[:40], [0, at])
        call[0], call[1] = call[0] + 1, at
    return said[:20] + [f"and {len(said) - 20} more; all {len(said)} by the call that wrote them: "
                        + ", ".join(f"{call} {n} (the last at {at})" for call, (n, at) in calls.items())]


GPU_PROCESS = "WebKit.GPU"
"""In the name of WebKit's GPU process (Playwright's macOS build: ``com.apple.WebKit.GPU.Development``), which draws its
pages' layers, canvases and media for their page processes."""
STUCK = re.compile(r"RemoteRenderingBackendProxy::didBecomeUnresponsive|gpuProcessConnectionDidBecomeUnresponsive|"
                   r"GPUProcessProxy::didBecomeUnresponsive|WebProcessProxy::didBecomeUnresponsive")
"""WebKit's lines on a process of its that stopped answering: a page process's wait on its GPU process ran out
(``RemoteRenderingBackendProxy``, 15 s: ``WebProcess::gpuProcessTimeoutDuration``) and it told its UI process, which
ends that GPU process at once; a GPU process that left its UI process's message unanswered 3 s
(``ResponsivenessTimer::defaultResponsivenessTimeout``: its first, a new page process's connection, among them), ended
so too; a page process that left its UI process 3 s (it is not ended). Run 41818469100's Intel runner ended a GPU
process so about 40 times in its WebKit hour, a new one 3 s after the last, every WebKit test after failing."""
SAMPLED = 3
"""Times a tier samples Playwright's processes as WebKit's log says one stopped answering: the first ones say why."""
FRAMES = 8
"""Frames of each watched thread's heaviest stack printed, from the call it was in down."""
WATCHED = re.compile(r"com\.apple\.main-thread|RemoteRenderingBackend|CA::|coreanimation")
"""The threads of a sampled process whose stacks are printed: its main thread, and in a GPU process each page's
drawing queue and CoreAnimation's, which draws their layers and hands them to Metal."""
THREADS = 6
"""Watched threads printed at most, a process."""
FRAME = re.compile(r"^([ +!:|]*)(\d+) (.+?)  \(in ([^)]+)\)")
"""A frame of ``sample``'s call graph: its depth (the marks before its count), its samples, symbol and library."""
TOP = re.compile(r"^\s+(.+?)  \(in ([^)]+)\)\s+(\d+)$", re.M)
"""A row of ``sample``'s calls threads were most often in (its "Sort by top of stack")."""


def stacks(text: str) -> str:
    """What a process was doing, from ``sample``'s report ``text``: the heaviest stack (each frame's heaviest callee)
    of each of its :data:`WATCHED` threads (a dispatch queue whose work ran on several threads, ``Thread_<multiple>``,
    among them), :data:`FRAMES` frames from the call it was in (threads of one name and
    stack once, with their count), and the 3 calls its threads were most often in, each with its library; thread
    names, symbols and library names only, never a path, a source line or an address."""
    graph = text.partition("Call graph:\n")[2].partition("\nTotal number in stack")[0].splitlines()
    said: dict[str, int] = {}
    for i, head in enumerate(graph):
        if not (thread := re.match(r"^ {4}\d+ Thread_(?:\d+|<multiple>)(?:\s+DispatchQueue_\d+)?:? *(.*?)(?:\s+\(serial\))?$",
                                 head)):
            continue
        if not WATCHED.search(name := thread[1]) or len(said) == THREADS:
            continue
        path, depth = [], -1
        for row in graph[i + 1:]:
            if not (frame := FRAME.match(row)) or len(frame[1]) <= depth:
                break
            depth = len(frame[1])
            path.append(f"{frame[3][:100]} ({frame[4]})")
        key = f"{'main thread' if 'main-thread' in name else name}: {' < '.join(reversed(path[-FRAMES:]))}"
        said[key] = said.get(key, 0) + 1
    top = TOP.findall(text.partition("Sort by top of stack, same collapsed (when >= 5):\n")[2].partition("\n\n")[0])
    return "; ".join([f"{n} x {key}" if n > 1 else key for key, n in said.items()] or ["no thread read"]) + (
        "; most often in: ") + (
        ", ".join(f"{name[:100]} ({lib}) {n}" for name, lib, n in top[:3]) or "unread")


def sampled(pid: int, seconds: int = 1) -> str:
    """What process ``pid`` was doing over ``seconds`` s (macOS's ``sample``, :func:`stacks`), or why it is unread."""
    with tempfile.TemporaryDirectory() as folder:
        report = Path(folder) / "sample.txt"
        try:
            subprocess.run(["sample", str(pid), str(seconds), "-mayDie", "-file", str(report)], capture_output=True,
                           timeout=60 + seconds)
            return stacks(report.read_text(encoding="utf-8", errors="replace"))
        except (OSError, subprocess.SubprocessError) as e:
            return f"unsampled ({type(e).__name__})"


class Said:
    """WebKit's lines as macOS's log takes them (``log stream`` on :data:`ENDINGS`), read on a thread of their own."""

    def __init__(self):
        self.rows, self.lock = [], threading.Lock()
        try:
            self.proc = subprocess.Popen(["log", "stream", "--style", "compact", "--predicate", ENDINGS],
                                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, errors="replace")
        except OSError:
            self.proc = None
            return
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        for row in self.proc.stdout:
            with self.lock:
                self.rows.append(row)

    def take(self) -> list[str]:
        with self.lock:
            rows, self.rows = self.rows, []
        return rows

    def close(self) -> None:
        if self.proc:
            self.proc.kill()
            self.proc.wait()


def stuck(rows: list[str], read: dict[int, tuple], left: int) -> tuple[list[str], int]:
    """For each of WebKit's ``rows`` (:class:`Said`) on a process that stopped answering (:data:`STUCK`), while
    ``left`` samples remain: what each of Playwright's GPU processes (``read``, :func:`footprints`) and the process that
    wrote the row, if it is one of Playwright's, were doing (:func:`sampled`), sampled at once, as the UI process
    ends a GPU process that stopped answering at once. The lines to print, and the samples left."""
    from concurrent.futures import ThreadPoolExecutor
    said = []
    for at, who, pid, what in (found.groups() for row in rows if (found := LINE.match(row.rstrip("\n")))):
        if not left or not STUCK.search(what):
            continue
        left -= 1
        gpus = [p for p, row in read.items() if GPU_PROCESS in row[0]]
        chosen = [*gpus, *([int(pid)] if int(pid) in read and int(pid) not in gpus else [])][:4]
        with ThreadPoolExecutor(max(1, len(chosen))) as pool:
            for p, stack in zip(chosen, pool.map(sampled, chosen)):
                said.append(f"--- WebKit's log at {at}, {who}: {what[:120]}; {read[p][0]} (id {p}) sampled 1 s: "
                            f"{stack}")
    return said, left


def gpu_state(read: dict[int, tuple], then: dict[int, tuple[float, float, int]], now: float) -> str:
    """Each of Playwright's GPU processes in ``read`` (:func:`footprints`) for the minute line: its share of a core
    and its page-ins since ``then`` (``{id: (time, CPU seconds, page-ins)}`` as last read, updated), and its footprint;
    then WindowServer's share of a core and the 1-minute load, which say whether a GPU process that stopped answering
    was starved, spinning, waiting on the disk, or waiting on the screen's server."""
    parts = []
    for pid, (name, footprint, *_) in sorted(read.items()):
        if GPU_PROCESS not in name or (used := cpu_used(pid)) is None:
            continue
        at, cpu, pageins = then.get(pid, (now, *used))
        then[pid] = (now, *used)
        share = (used[0] - cpu) / (now - at) if now > at else 0.0
        parts.append(f"id {pid} {share:.0%} of a core, {used[1] - pageins} page-ins, {footprint / MIB:.0f} MiB")
    window, server = cpu_used_ps("WindowServer"), "unread"
    if window is not None:
        at, cpu, _ = then.get(-1, (now, window, 0))
        then[-1] = (now, window, 0)
        server = f"{(window - cpu) / (now - at) if now > at else 0.0:.0%} of a core"
    return (f"; WebKit's GPU processes: {'; '.join(parts) or 'none'}; WindowServer {server}; "
            f"load {os.getloadavg()[0]:.1f}")


def cpu_used(pid: int) -> tuple[float, int] | None:
    """(CPU seconds, page-ins) of one of this user's processes, by macOS's own count (``proc_pid_rusage``)."""
    import ctypes
    lib = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
    info, base = (ctypes.c_uint64 * 40)(), (ctypes.c_uint32 * 2)()
    if lib.proc_pid_rusage(pid, 4, info) != 0:
        return None
    lib.mach_timebase_info(base)   # its times are in the machine's ticks (ns on Intel, 125/3 ns on Apple Silicon)
    return (info[2] + info[3]) * base[0] / base[1] / 1e9, info[6]


def cpu_used_ps(name: str) -> float | None:
    """CPU seconds of the process named ``name`` (``ps``'s, which reads another user's too)."""
    try:
        for row in _lines(["ps", "-A", "-o", "time=,comm="], 30):
            clock, _, comm = row.strip().partition(" ")
            if os.path.basename(comm.strip()) == name:
                whole, _, part = clock.partition(".")
                return _seconds(whole) + float(f"0.{part or 0}")
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return None


def machine_gpu() -> str:
    """The runner's GPU and screens, by macOS's own report (``system_profiler``): its model, its Metal support and
    each screen's resolution; a VM's emulated GPU often has no Metal, which WebKit's GPU process falls back from."""
    try:
        cards = json.loads(subprocess.run(["system_profiler", "-json", "SPDisplaysDataType"], capture_output=True,
                                          text=True, timeout=120).stdout or "{}").get("SPDisplaysDataType", [])
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        return f"unread ({type(e).__name__})"
    said = []
    for card in cards:
        screens = [s.get("_spdisplays_resolution", s.get("_name", "?")) for s in card.get("spdisplays_ndrvs", [])]
        metal = card.get("spdisplays_mtlgpufamilysupport", "none").removeprefix("spdisplays_")
        said.append(f"{card.get('sppci_model', card.get('_name', '?'))}, Metal {metal}, "
                    f"screens: {', '.join(screens) or 'none'}")
    return "; ".join(said) or "none"


def _last(read: tuple[str, int, int, int]) -> str:
    return (f"its footprint last read {read[1] / GIB:.2f} GiB (its highest {read[2] / GIB:.2f}), "
            f"memory then {read[3] / GIB:.1f} GiB free")


def described(row: tuple) -> str:
    """A process as :func:`held` and the watch list it: its name, id, parent's id, age and memory."""
    pid, parent, age, name, *_ = row
    memory = f", {row[5] / MIB:.0f} MiB" if len(row) > 5 else ""
    return f"{name} (id {pid}, parent {parent}): {age // 60} min{memory}"


def orphans(rows: list[tuple], age: int) -> list[tuple]:
    """Each process of ``rows`` (:func:`processes`) at most ``age`` s old whose parent has ended: its parent's id is
    no process's, or a younger one's (Windows hands an ended process's id to a new one). Where a process's end leaves
    its children running (Windows; elsewhere they pass to init, whose id lives), the driver's kill of a browser's tree
    can't reach them."""
    born = {pid: when for pid, _, when, *_ in rows}
    return [row for row in rows if row[2] <= age and row[1] > 4 and (row[1] not in born or born[row[1]] < row[2] - 1)]


def _size(folder: Path, deadline: float) -> str:
    """The bytes and files under ``folder``, as many as are read by ``deadline`` (``time.monotonic``'s)."""
    total = files = 0
    stack = [folder]
    while stack:
        if time.monotonic() > deadline:
            return f"at least {total / MIB:.1f} MiB in {files} files (the rest unread)"
        try:
            entries = os.scandir(stack.pop())
        except OSError:
            continue
        with entries:
            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(Path(entry.path))
                    else:
                        total, files = total + entry.stat(follow_symlinks=False).st_size, files + 1
                except OSError:
                    pass
    return f"{total / MIB:.1f} MiB in {files} files"


def _made(path: Path) -> float:
    st = path.stat()
    return getattr(st, "st_birthtime", st.st_mtime)


def temp_folders(age: float | None, deadline: float) -> list[str]:
    """Each of Playwright's temporary folders (a browser's profile, its artifacts) made in the last ``age`` s (any
    age: ``None``), by kind and age, with its size (:func:`_size`): the driver removes a browser's only once its close
    has heard it end. Labels and numbers only."""
    said, now = [], time.time()
    try:
        found = sorted((_made(p), p) for p in Path(tempfile.gettempdir()).glob("playwright*") if p.is_dir())
    except OSError as e:
        return [f"unread ({type(e).__name__})"]
    for made, folder in found:
        if age is not None and made < now - age - 2:
            continue
        kind = re.match(r"playwright_(\w+?)dev_profile-|playwright-(artifacts)-", folder.name)
        label = (f"{kind[1]}'s profile" if kind and kind[1] else "artifacts" if kind else "another")
        said.append(f"{label} ({(now - made) / 60:.0f} min): {_size(folder, deadline)}")
    return said


def wer_reports(age: float | None) -> list[str]:
    """What Windows Error Reporting wrote in the last ``age`` s (any age: ``None``): each crash dump's program and
    id and each report's kind and program, from their names (the folders of :data:`WER` under the user's and the
    machine's app data); none off Windows."""
    if sys.platform != "win32":
        return []
    said, now = [], time.time()
    for base in filter(None, (os.environ.get("LOCALAPPDATA"), os.environ.get("ProgramData"))):
        for sub in WER:
            try:
                entries = sorted(Path(base, sub).iterdir(), key=_made)
            except OSError:
                continue
            for entry in entries:
                try:
                    if age is not None and _made(entry) < now - age - 2:
                        continue
                except OSError:
                    continue
                said.append(" ".join(entry.name.split("_")[:2]) if "_" in entry.name else entry.name)
    return said[-LISTED:]


def held(driver: int, folders: dict[str, Path] | None = None, seconds: float = SAY_S) -> list[str]:
    """What a browser whose close its driver (id ``driver``) never answered may wait on, a line each, in at most
    about ``seconds`` s: the processes under the driver, each process left running since the driver began by a parent
    that ended (:func:`orphans`), the crash handlers (:data:`CRASH`), each :func:`described`; Playwright's temporary
    folders since then (:func:`temp_folders`), each of ``folders`` (``{label: folder}``) with its size, and what
    Windows Error Reporting wrote since then (:func:`wer_reports`). Never raises: what can't be read says so."""
    deadline, said, age = time.monotonic() + seconds, [], None
    try:
        rows = processes(seconds)
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        said.append(f"its processes unread ({type(e).__name__})")
    else:
        under = tree(rows, driver)
        age = under[0][1][2] if under else None
        said.append("under its driver: " + ("; ".join(described(row) for _, row in under[:LISTED])
                                            or f"none (the driver {driver} is gone)"))
        if age is not None:
            mine = {row[0] for _, row in under}
            left = [row for row in orphans(rows, age) if row[0] not in mine]
            said.append("left running since it began by a parent that ended: "
                        + ("; ".join(described(row) for row in left[-LISTED:]) or "none"))
        said.append("crash handlers: " + ("; ".join(described(row) for row in rows if CRASH.search(row[3]))
                                          or "none"))
    said.append("Playwright's temporary folders since it began: " + ("; ".join(temp_folders(age, deadline)) or "none"))
    for label, folder in (folders or {}).items():
        said.append(f"{label}: {_size(Path(folder), deadline)}")
    if sys.platform == "win32":
        said.append("Windows Error Reporting's since it began: " + ("; ".join(wer_reports(age)) or "none"))
    return said


def left(driver: int) -> list[tuple]:
    """Each browser's process (:data:`BROWSER`) run from Playwright's folders (:data:`PLAYWRIGHT`, so never the user's
    own Chrome or Edge) that a parent that ended left running since the driver (id ``driver``) began (:func:`orphans`),
    none under it: on Windows a closed browser's process left so holds its stdout and stderr (Playwright's WebKit
    hands every process it starts its own), so its driver never hears it end, and the driver's kill, ``taskkill /T``
    of the browser, can't reach it. None if the driver isn't running."""
    rows = processes(SAY_S)
    if not (under := tree(rows, driver)):
        return []
    mine = {row[0] for _, row in under}
    return [row for row in orphans(rows, under[0][1][2])
            if row[0] not in mine and BROWSER.search(row[3]) and PLAYWRIGHT.search(row[4])]


def end_left(driver: int) -> list[tuple]:
    """End each of :func:`left`'s processes; their rows (none if they couldn't be listed)."""
    try:
        found = left(driver)
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    for row in found:
        _end(row[0])
    return found


def _listed() -> list[tuple[int, int, int, str, str, int]]:
    try:
        return processes()
    except (OSError, subprocess.SubprocessError) as e:
        print(f"--- the processes couldn't be listed ({type(e).__name__})", flush=True)
        return []


def _end(pid: int) -> None:
    try:
        os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))
    except OSError:   # ended already, or not this user's (Linux's sudo)
        pass


def _under(members: list, worker) -> list:
    """The members under each one ``worker`` picks, that one included (:func:`tree`'s order puts each one's own right
    after it, deeper)."""
    picked, depth_in = [], None
    for depth, row in members:
        if depth_in is not None and depth <= depth_in:
            depth_in = None
        if depth_in is None and worker(row):
            depth_in = depth
        if depth_in is not None:
            picked.append((depth, row))
    return picked


def _end_all(members: list, mine: set[int]) -> None:
    for _, (pid, *_) in sorted(members, key=lambda member: -member[0]):   # the deepest first
        if pid not in mine:
            _end(pid)


def _running(own: tuple) -> bool | None:
    """Whether the process ``own`` (a row) still runs, it and not a new one with its id; None if the list can't be
    read."""
    if not (rows := _listed()):
        return None
    return any(row[0] == own[0] and row[2] >= own[2] for row in rows)


def stop_tier(why: str, log: str, root: int | None, grace: float = GRACE_S, settle: float = SETTLE_S) -> None:
    """Print the log's tail and the tier's processes, then end xdist's workers under the tier's own (each with what
    runs under it) and give pytest's controller ``settle`` seconds to write its summary and failures and end; then
    end what is left under the tier's own, the deepest first, and the tier's own if it hasn't ended by itself
    within ``grace`` seconds (the step's subshell, which Git Bash tracks as its own). Ending the controller with its
    workers would lose every line it writes once they are gone (Step 4.4ci12's review, F1)."""
    print(f"--- {why}: the log's last {TAIL} lines", flush=True)
    if lines := tail(log):
        print("\n".join(lines), flush=True)
    rows = _listed()
    parents = {pid: parent for pid, parent, *_ in rows}
    mine, pid = set(), os.getpid()
    while pid not in mine and pid in parents:   # this watcher and the processes it runs under
        mine.add(pid)
        pid = parents[pid]
    members = tree(rows, root) if root and root > 1 and root not in mine else []
    print("--- the tier's processes (age, memory), each under its parent", flush=True)
    for depth, (pid, _, age, name, *rest) in members:
        print(f"{'  ' * depth}{name} (id {pid}): {age // 60} min, {rest[1] / MIB:.0f} MiB", flush=True)
    inside = {row[0] for _, row in members}
    left = {row[0] for row in orphans(rows, members[0][1][2])} if members else set()
    others = [row for row in rows if row[0] not in inside
              and (NAMED.search(row[3]) or CRASH.search(row[3]) or row[0] in left)]
    if others:
        print("--- outside the tier: python, node, uv, the browsers, the crash handlers and what a parent that ended "
              "left running since the tier began", flush=True)
        for row in others:
            print(described(row), flush=True)
    print("--- Playwright's temporary folders: " + ("; ".join(temp_folders(None, time.monotonic() + SAY_S))
                                                   or "none"), flush=True)
    if sys.platform == "win32":
        print("--- Windows Error Reporting's since the tier began: " + (
            "; ".join(wer_reports(members[0][1][2] if members else None)) or "none"), flush=True)
    if not members:
        print("--- the tier's process isn't running, isn't known or runs this watcher: nothing stopped", flush=True)
        return
    own = members[0][1]
    if workers := _under(members[1:], lambda row: WORKER in row[4]):
        _end_all(workers, mine)
        print(f"--- xdist's workers stopped ({len(workers)} processes): pytest has {settle:.0f} s to write its "
              "summary and end", flush=True)
        deadline = time.monotonic() + settle
        while (running := _running(own)) is not False and time.monotonic() < deadline:
            time.sleep(min(SAMPLE_S, settle / 5))
        if running is False:
            print(f"--- the tier ended by itself once its workers stopped ({len(members)} processes)", flush=True)
            return
        members = tree(_listed(), own[0])
    _end_all(members[1:], mine)
    time.sleep(grace)
    if _running(own):
        _end(own[0])
    print(f"--- the tier stopped ({len(members)} processes)", flush=True)


def main(argv: list[str]) -> int:
    options = {k: v for k, _, v in (a[2:].partition("=") for a in argv[1:] if a.startswith("--"))}
    stop = argv[0]
    folders = dict(item.split("=", 1) for item in argv[1:] if not item.startswith("--")) | {
        "temp": tempfile.gettempdir()}
    stall = float(options.get("stall", STALL_S))
    until = float(options["until"]) if options.get("until") else None
    root = int(options["tier"]) if options.get("tier") else None
    log = options.get("watch")
    total, start = free_memory()[1], time.monotonic()
    growth = Growth(log, start) if log else None
    stopped = False
    low: dict[str, int] = {}
    told = -PRINT_S
    began, seen, most = time.time(), {}, [0, 0, ""]   # Playwright's processes as last read; their most together, one's
    said, left, gpus = (Said(), SAMPLED, {}) if sys.platform == "darwin" else (None, 0, {})
    try:
        while True:
            now = sample(folders)
            low = {label: min(value, low.get(label, value)) for label, value in now.items()}
            elapsed = time.monotonic() - start
            read = footprints(_listed()) if sys.platform == "darwin" else {}
            seen |= {pid: (*row, now["memory"]) for pid, row in read.items()}
            biggest = max(read.values(), key=lambda row: row[1], default=("", 0, 0))
            most[0] = max(most[0], together := sum(row[1] for row in read.values()))
            if (top := max(read.values(), key=lambda row: row[2], default=None)) and top[2] > most[1]:
                most[1:] = top[2], top[0]
            if said:
                for row in (printed := stuck(said.take(), read, left))[0]:
                    print(row, flush=True)
                left = printed[1]
            if os.path.exists(stop):
                print(f"resources, the lowest of the tier in {elapsed / 60:.0f} min: "
                      + ", ".join(f"{label} {value / GIB:.1f} GiB free" for label, value in low.items())
                      + f" (memory of {total / GIB:.1f})"
                      + (f"; Playwright's processes at most {most[0] / GIB:.1f} GiB together, one {most[1] / GIB:.1f} "
                         f"({most[2]})" if sys.platform == "darwin" else ""), flush=True)
                if sys.platform == "darwin":
                    print("--- what macOS wrote of Playwright's processes that ended: "
                          + ("; ".join(reports(began, seen)) or "nothing"), flush=True)
                    print("--- what WebKit's log says of a process that ended: "
                          + ("; ".join(webkit_said(began)) or "nothing"), flush=True)
                    print(f"--- the runner's GPU: {machine_gpu()}", flush=True)
                return STOPPED if stopped else 0
            if elapsed - told >= PRINT_S:
                told = elapsed
                print(f"resources at {elapsed / 60:.0f} min: {line(now, low)}"
                      + (f"; Playwright's processes {together / GIB:.1f} GiB in {len(read)}, the largest "
                         f"{biggest[1] / GIB:.1f} ({biggest[0]})" + gpu_state(read, gpus, time.monotonic())
                         if sys.platform == "darwin" else ""), flush=True)
            if growth and not stopped:
                if (quiet := growth.quiet(time.monotonic())) >= stall:
                    stop_tier(f"the tier's log hasn't grown in {quiet / 60:.0f} min", log, root, min(GRACE_S, stall),
                              min(SETTLE_S, stall))
                    stopped = True
                elif until is not None and time.time() >= until:
                    stop_tier("the tier ran to its deadline, the job's limit less the time its end needs", log, root,
                              min(GRACE_S, stall), min(SETTLE_S, stall))
                    stopped = True
            time.sleep(min(SAMPLE_S, stall / 5))
    finally:
        if said:
            said.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(errors="backslashreplace")
    sys.exit(main(sys.argv[1:]))
