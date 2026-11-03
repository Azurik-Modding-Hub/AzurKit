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
the tier's processes with their ages, then stops them (every process under
the one ``ID`` names, Windows' own id under Git Bash, then that one if it
hasn't ended by itself), so the step ends, prints its summary and fails while
the job has time left; it exits 3 once ``STOP`` exists.
"""

from __future__ import annotations

import base64
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
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
NAMED = re.compile(r"^(?:uv|node|python[\d.]*w?)(?:\.exe)?$|firefox|chrom|webkit|msedge|playwright", re.I)
"""Processes listed even outside the tier's tree (a browser its parent left behind)."""


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


def processes() -> list[tuple[int, int, int, str]]:
    """(id, its parent's id, age in seconds, name) of each process on this machine."""
    if sys.platform == "win32":
        script = ("$now = Get-Date; Get-CimInstance Win32_Process | Where-Object CreationDate | ForEach-Object "
                  "{ '{0} {1} {2} {3}' -f $_.ProcessId, $_.ParentProcessId, "
                  "[long]($now - $_.CreationDate).TotalSeconds, $_.Name }")
        command = ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand",
                   base64.b64encode(script.encode("utf-16-le")).decode("ascii")]
    else:
        command = ["ps", "-A", "-o", "pid=,ppid=,etime=,comm="]
    found = []
    for row in subprocess.run(command, capture_output=True, text=True, errors="replace", check=True,
                              timeout=120).stdout.splitlines():
        parts = row.split(None, 3)
        if len(parts) == 4 and parts[0].isdigit() and parts[1].isdigit():
            found.append((int(parts[0]), int(parts[1]), _seconds(parts[2]), os.path.basename(parts[3].strip())))
    return found


def tree(rows: list[tuple[int, int, int, str]], root: int) -> list[tuple[int, tuple[int, int, int, str]]]:
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


def _listed() -> list[tuple[int, int, int, str]]:
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


def stop_tier(why: str, log: str, root: int | None, grace: float = GRACE_S) -> None:
    """Print the log's tail and the tier's processes, then end those under the tier's own, the deepest first, and
    the tier's own if it hasn't ended by itself within ``grace`` seconds (the step's subshell, which Git Bash
    tracks as its own)."""
    print(f"--- {why}: the log's last {TAIL} lines", flush=True)
    if lines := tail(log):
        print("\n".join(lines), flush=True)
    rows = _listed()
    parents = {pid: parent for pid, parent, _, _ in rows}
    mine, pid = set(), os.getpid()
    while pid not in mine and pid in parents:   # this watcher and the processes it runs under
        mine.add(pid)
        pid = parents[pid]
    members = tree(rows, root) if root and root > 1 and root not in mine else []
    print("--- the tier's processes (age), each under its parent", flush=True)
    for depth, (pid, _, age, name) in members:
        print(f"{'  ' * depth}{name} (id {pid}): {age // 60} min", flush=True)
    inside = {row[0] for _, row in members}
    others = [row for row in rows if row[0] not in inside and NAMED.search(row[3])]
    if others:
        print("--- outside the tier: python, node, uv and the browsers", flush=True)
        for pid, parent, age, name in others:
            print(f"{name} (id {pid}, parent {parent}): {age // 60} min", flush=True)
    if not members:
        print("--- the tier's process isn't running, isn't known or runs this watcher: nothing stopped", flush=True)
        return
    for _, (pid, *_) in sorted(members[1:], key=lambda member: -member[0]):
        if pid not in mine:
            _end(pid)
    time.sleep(grace)
    own = members[0][1]
    if any(row[0] == own[0] and row[2] >= own[2] for row in _listed()):   # still it, not a new one with its id
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
    while True:
        now = sample(folders)
        low = {label: min(value, low.get(label, value)) for label, value in now.items()}
        elapsed = time.monotonic() - start
        if os.path.exists(stop):
            print(f"resources, the lowest of the tier in {elapsed / 60:.0f} min: "
                  + ", ".join(f"{label} {value / GIB:.1f} GiB free" for label, value in low.items())
                  + f" (memory of {total / GIB:.1f})", flush=True)
            return STOPPED if stopped else 0
        if elapsed - told >= PRINT_S:
            told = elapsed
            print(f"resources at {elapsed / 60:.0f} min: {line(now, low)}", flush=True)
        if growth and not stopped:
            if (quiet := growth.quiet(time.monotonic())) >= stall:
                stop_tier(f"the tier's log hasn't grown in {quiet / 60:.0f} min", log, root, min(GRACE_S, stall))
                stopped = True
            elif until is not None and time.time() >= until:
                stop_tier("the tier ran to its deadline, the job's limit less the time its end needs", log, root,
                          min(GRACE_S, stall))
                stopped = True
        time.sleep(min(SAMPLE_S, stall / 5))


if __name__ == "__main__":
    sys.stdout.reconfigure(errors="backslashreplace")
    sys.exit(main(sys.argv[1:]))
