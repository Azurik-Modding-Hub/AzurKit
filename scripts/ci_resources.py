"""The runner's room during a CI tier, on stdout (Step 4.4ci3): each minute the
free disk under each folder named and the free memory, and as the tier ends
(``STOP`` exists) the lowest of each, so a run the runner shuts down still
names what it ran out of. Labels and numbers only, never a folder's path, a
file's name or anything read from one.

    python -I scripts/ci_resources.py STOP LABEL=FOLDER ...
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

GIB = 1 << 30
SAMPLE_S, PRINT_S = 5, 60


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


def main(stop: str, named: list[str]) -> None:
    folders = dict(item.split("=", 1) for item in named) | {"temp": tempfile.gettempdir()}
    total, start = free_memory()[1], time.monotonic()
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
            return
        if elapsed - told >= PRINT_S:
            told = elapsed
            print(f"resources at {elapsed / 60:.0f} min: {line(now, low)}", flush=True)
        time.sleep(SAMPLE_S)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
