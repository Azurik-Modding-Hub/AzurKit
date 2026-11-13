"""The machine a host runs on (Step 4.3w; D1007: work ahead takes "every
core at low priority"): a thread's or this process's priority set low for
work no one waits on yet, and back for a click that waits on it, and the
machine's memory.

:func:`background` lowers the calling thread (or, with ``process``, this
process) and returns what it was, which :func:`foreground` puts back. Each
is a call a process makes on itself: macOS reads nothing back from a
parent's call on its child's pid, so a child lowers itself. Per OS:

- **macOS:** a thread's priority within the default QoS class
  (``pthread_set_qos_class_self_np``, the lowest relative priority, and back
  to the class it had): under the utility class's scheduling priority, on
  every core, where the background class holds a thread to the efficiency
  cores (keylord's build on a loaded Mac: 2.2 s normal and here, 3 s
  utility, 7-10 s background, D1007); a process's ``PRIO_DARWIN_BG``
  (``setpriority(PRIO_DARWIN_PROCESS)``, which throttles its disk too). Both
  go down and back up from the process itself.
- **Windows:** ``SetThreadPriority`` and ``SetPriorityClass`` below
  normal, and back to what they were.
- **Linux and other POSIX:** nice at least :data:`NICE`
  (``os.setpriority``; on Linux a thread's own, so a process lowers itself
  from its first thread before it starts others, which take it). One way
  only: POSIX refuses a lower nice without privilege, so
  :func:`foreground` gives ``False`` there and the work stays low (a known
  flaw, D835).
- **Pyodide** and anything else: nothing (the page's worker has no
  priority of its own).

:func:`ram` is the machine's physical memory in bytes, ``None`` where it
can't be read, and :func:`peak` this process's peak resident size. Nothing
here starts a thread or a process."""

from __future__ import annotations

import functools
import os
import sys

NICE = 10
"""POSIX's low priority: at least this nice."""
QOS_DEFAULT, QOS_LOWEST = 0x15, -15                  # <sys/qos.h>: its class and QOS_MIN_RELATIVE_PRIORITY
PRIO_DARWIN_PROCESS, PRIO_DARWIN_BG = 4, 0x1000     # <sys/resource.h>
THREAD_BELOW_NORMAL, PROCESS_BELOW_NORMAL = -1, 0x4000   # <winbase.h>
_THREAD_ERROR = 0x7FFFFFFF                          # GetThreadPriority's THREAD_PRIORITY_ERROR_RETURN


@functools.cache
def _libc():
    """macOS's libSystem (the process's own symbols: ``dlopen(NULL)``)."""
    import ctypes

    libc = ctypes.CDLL(None, use_errno=True)
    libc.setpriority.argtypes = [ctypes.c_int, ctypes.c_uint, ctypes.c_int]
    libc.getpriority.argtypes = [ctypes.c_int, ctypes.c_uint]
    libc.qos_class_self.restype = ctypes.c_uint
    libc.pthread_set_qos_class_self_np.argtypes = [ctypes.c_uint, ctypes.c_int]
    return libc


@functools.cache
def _kernel32():
    """Windows' kernel32, its handles typed as pointers."""
    import ctypes

    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.GetCurrentThread.restype = k.GetCurrentProcess.restype = ctypes.c_void_p
    k.GetThreadPriority.argtypes = k.GetPriorityClass.argtypes = [ctypes.c_void_p]
    k.SetThreadPriority.argtypes = [ctypes.c_void_p, ctypes.c_int]
    k.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    k.K32GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
    return k


def background(process: bool = False) -> int | None:
    """Lower the calling thread (``process``: this process) to the OS's
    background priority; what it was, for :func:`foreground`, or ``None``
    when nothing changed (the OS has no such call, or refused it)."""
    try:
        if sys.platform == "darwin":
            libc = _libc()
            if process:
                was = libc.getpriority(PRIO_DARWIN_PROCESS, 0)
                return was if libc.setpriority(PRIO_DARWIN_PROCESS, 0, PRIO_DARWIN_BG) == 0 else None
            was = libc.qos_class_self() or QOS_DEFAULT   # unspecified: the default class it runs at
            return was if libc.pthread_set_qos_class_self_np(QOS_DEFAULT, QOS_LOWEST) == 0 else None
        if sys.platform == "win32":
            k = _kernel32()
            if process:
                handle = k.GetCurrentProcess()
                was = k.GetPriorityClass(handle)
                return was if was and k.SetPriorityClass(handle, PROCESS_BELOW_NORMAL) else None
            handle = k.GetCurrentThread()
            was = k.GetThreadPriority(handle)
            return was if was != _THREAD_ERROR and k.SetThreadPriority(handle, THREAD_BELOW_NORMAL) else None
        if hasattr(os, "setpriority") and sys.platform != "emscripten":
            was = os.getpriority(os.PRIO_PROCESS, 0)
            if was < NICE:
                os.setpriority(os.PRIO_PROCESS, 0, NICE)
            return was
    except (OSError, AttributeError):   # a call this OS's version lacks, or refuses
        pass
    return None


def foreground(was: int | None, process: bool = False) -> bool:
    """Put the calling thread (``process``: this process) back to ``was``,
    :func:`background`'s answer; whether it is back (``False`` for
    ``None``, and where the OS refuses: POSIX's nice)."""
    if was is None:
        return False
    try:
        if sys.platform == "darwin":
            libc = _libc()
            if process:
                return libc.setpriority(PRIO_DARWIN_PROCESS, 0, PRIO_DARWIN_BG if was else 0) == 0
            return libc.pthread_set_qos_class_self_np(was, 0) == 0
        if sys.platform == "win32":
            k = _kernel32()
            if process:
                return bool(k.SetPriorityClass(k.GetCurrentProcess(), was))
            return bool(k.SetThreadPriority(k.GetCurrentThread(), was))
        if hasattr(os, "setpriority") and sys.platform != "emscripten":
            if os.getpriority(os.PRIO_PROCESS, 0) != was:
                os.setpriority(os.PRIO_PROCESS, 0, was)
            return True
    except (OSError, AttributeError):   # PermissionError: POSIX's way back needs privilege
        pass
    return False


RAM = "AZURKIT_RAM"
"""A positive whole number of bytes: the most memory :func:`ram` reports (the capped profile's 8 GiB, D984/D1017), as
``$AZURKIT_CORES`` caps the cores."""


def ram() -> int | None:
    """The machine's physical memory in bytes, at most ``$AZURKIT_RAM``;
    ``None`` where it can't be read and no cap is set."""
    try:
        cap = int(os.environ.get(RAM) or 0)
    except ValueError:
        cap = 0
    real = _physical()
    return (min(real, cap) if real else cap) if cap > 0 else real


def _physical() -> int | None:
    """The machine's physical memory in bytes (``sysconf``'s pages, or
    Windows' ``GlobalMemoryStatusEx``); ``None`` where it can't be read."""
    try:
        if sys.platform == "win32":
            import ctypes

            class Status(ctypes.Structure):   # MEMORYSTATUSEX
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            *((name, ctypes.c_ulonglong) for name in (
                                "ullTotalPhys", "ullAvailPhys", "ullTotalPageFile", "ullAvailPageFile",
                                "ullTotalVirtual", "ullAvailVirtual", "ullAvailExtendedVirtual"))]
            status = Status()
            status.dwLength = ctypes.sizeof(Status)
            if not _kernel32().GlobalMemoryStatusEx(ctypes.byref(status)):
                return None
            return int(status.ullTotalPhys) or None
        pages, size = os.sysconf("SC_PHYS_PAGES"), os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, AttributeError):
        return None
    return pages * size if pages > 0 and size > 0 else None


def peak() -> int:
    """This process's peak resident size in bytes, 0 where it can't be read
    (Pyodide): macOS's ``getrusage``; Linux's ``VmHWM``, as its
    ``getrusage`` starts a spawned child at its parent's peak (exec keeps
    it), past the line whatever the child did; Windows' peak working set
    (``K32GetProcessMemoryInfo``)."""
    if sys.platform == "darwin":
        import resource

        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "win32":
        import ctypes

        class Counters(ctypes.Structure):   # PROCESS_MEMORY_COUNTERS
            _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                        *((name, ctypes.c_size_t) for name in (
                            "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                            "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
                            "PagefileUsage", "PeakPagefileUsage"))]
        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        try:
            k = _kernel32()
            if not k.K32GetProcessMemoryInfo(k.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
                return 0
        except (OSError, AttributeError):
            return 0
        return int(counters.PeakWorkingSetSize)
    try:
        with open("/proc/self/status", encoding="utf-8") as status:
            return next(int(line.split()[1]) * 1024 for line in status if line.startswith("VmHWM:"))
    except (OSError, StopIteration):
        return 0
