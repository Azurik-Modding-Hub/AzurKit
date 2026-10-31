"""The xemu sittings' first-come queue, and the batch token that gives way to it (Step X.8, D173; from Modkit, Step 4.14a1).

The harness (Modkit's ``scripts/xemu_oracle.py`` until Step 4.14a2 ports it) admits sandboxes under D108's rule as D174
and D263 amend it: two may always run, whatever the load; each one after
them only while no full suite runs, at least four CPU cores are free
(measured idle, not the load average) and 8 GiB of RAM is free. A sandbox that asks takes a numbered ticket
here, and only the lowest live ticket may start when the rule allows, so
waiting sittings start in the order they asked, not by who polls first
after cores come free.

The tickets live in ``<root>/queue/`` (``root`` is the harness's slot
folder, ``/tmp/azx-xemu-slots``): a subfolder, so the slot listing
(``azx-*.json`` in the root) never reads one. A waiter
renews its ticket at every poll; a ticket whose process is gone, or
that went unrenewed for ``STALE_S``, is removed by whoever reads the
queue next.

CPU-heavy batch jobs (the L3 search pools and the randomizer database's
derive, soak and impact benches, Modkit's until their ports) take a
:class:`BatchToken`: while a sitting waits for free cores, each keeps one
task in flight, so cores come free and the sitting starts under the rule
as written (a niced thread's CPU time counts as busy, so nicing them
doesn't help); a task that runs for hours (the trick explorer's) also
calls :func:`give_way` between its steps. A sitting that waits for
anything freed cores can't give it (RAM, a full suite's lock, another
launch, an xemu not ours) is not given way to (AZ-620: the explorer slept
an hour behind a ticket an owner demo held). While an owner demo plays
(D526: the fork's owner-demo file names a live pid) a job keeps at most
:func:`demo_budget` tasks in flight and runs its workers at macOS
background priority (:func:`set_background`), so the demo keeps its
cores; once the demo ends they are taken back out. Stdlib only;
for dev tools, never the runtime.
"""

from __future__ import annotations

import collections
import contextlib
import functools
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/tmp/azx-xemu-slots")   # the harness's SLOTS
STALE_S = 120.0   # a waiter renews its ticket every poll (5 s); one silent this long is gone
# The fork's owner-demo file (PROMPT-8 F(2); the harness's OWNER_DEMO, which writes it): while it names a live pid an
# owner plays (D205). Read at each call, so a driver that simulates a demo points this and the harness's at its own.
OWNER_DEMO = Path("/tmp/xemu-leases/owner-demo.json")
OWNER_DEMO_WHO = "azurik-modkit"   # the record the harness's own demos write (its owner_demo_begin): Modkit's
#                                    name, kept for the port, so each harness reads the other's records as its own
PRIO_DARWIN_PROCESS, PRIO_DARWIN_BG = 4, 0x1000   # <sys/resource.h>: setpriority's darwin background


def alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def pid_command(pid: int) -> str:
    return subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True).stdout.strip()


def stale_ours(rec: dict, pid: int) -> bool:
    """Whether the owner-demo record ``rec`` (naming ``pid``) is one of the harness's own demos whose pid no longer
    runs it: neither an xemu (``ps`` shows an ``xemu.app``; a zombie shows ``<defunct>``, a reused pid another
    command) nor, a relaunch's (``relaunch_of``, AZ-601), the command it recorded (``relaunch_cmd``)."""
    if rec.get("who") != OWNER_DEMO_WHO:
        return False
    cmd = pid_command(pid) if pid > 0 else ""
    return not ("/xemu.app/" in cmd or (rec.get("relaunch_of") and cmd and cmd == rec.get("relaunch_cmd")))


def _write(path: Path, doc: dict) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}")
    tmp.write_text(json.dumps(doc), encoding="utf-8")
    os.replace(tmp, path)


def take_ticket(info: dict, root: Path = ROOT) -> Path:
    """A new ticket for this process, numbered after every earlier one
    (a counter under the queue's own lock); ``info`` (its W) is kept in
    it. Returns its path. POSIX only, like the harness."""
    import fcntl
    q = root / "queue"
    q.mkdir(parents=True, exist_ok=True)
    fd = os.open(q / ".lock", os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            n = int((q / ".next").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            n = 1
        _write(q / ".next", n + 1)
        path = q / f"{n:09d}.json"
        _write(path, {"n": n, "pid": os.getpid(), "since": time.time(), "why": None, **info})
    finally:
        os.close(fd)   # closing the descriptor drops its flock
    return path


def renew_ticket(path: Path, why: str, cores: bool | None = True) -> None:
    """Renew this waiter's ticket and record why it waits and whether
    freed cores would end that wait (``cores``: the free-core test; batch
    jobs give way only to such a ticket, :func:`core_waits`; None, a wait
    that says nothing of cores such as another launch's lock, leaves it as
    it was); a ticket removed as stale (its process was stopped) is
    written again under its own number, so it keeps its place."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        doc = {"n": int(path.stem), "pid": os.getpid(), "since": time.time()}
    _write(path, {**doc, "why": why, "cores": doc.get("cores", False) if cores is None else cores})


def drop_ticket(path: Path) -> None:
    path.unlink(missing_ok=True)


def tickets(root: Path = ROOT) -> list[dict]:
    """The live tickets, first come first: each with its number ``n``,
    ``pid``, ``since``, ``why`` (None until its first refusal) and
    ``path``. A ticket whose process is gone, or unrenewed for
    ``STALE_S``, is removed."""
    out = []
    for p in sorted((root / "queue").glob("*.json")):
        try:
            t = json.loads(p.read_text(encoding="utf-8"))
            age = time.time() - p.stat().st_mtime
        except (OSError, ValueError):
            continue
        if alive(t.get("pid")) and age <= STALE_S:
            out.append({**t, "path": str(p)})
        else:
            p.unlink(missing_ok=True)
    return out


def core_waits(root: Path = ROOT) -> int:
    """The live tickets whose latest refusal was for want of free cores (one for the launch lock, which says nothing of
    cores, leaves it as it was), the waits a batch job ends by giving way (AZ-620). A refused ticket with no
    ``cores`` (an older harness's) counts, as every refused ticket did."""
    return sum(t.get("why") is not None and t.get("cores", True) for t in tickets(root))


def demo_pid(path: Path | None = None) -> int | None:
    """The owner demo's pid while one plays: the live pid ``path`` (default :data:`OWNER_DEMO`) names, as the fork's
    launchers read it, but for a record of ours whose pid no longer runs its demo (:func:`stale_ours`, as the harness's
    ``owner_demo`` reads it); else None (no file, a torn one, a dead pid)."""
    try:
        rec = json.loads(Path(path or OWNER_DEMO).read_text(encoding="utf-8"))
        pid = None if isinstance(rec["pid"], bool) else int(rec["pid"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return pid if pid and pid > 0 and alive(pid) and not stale_ours(rec, pid) else None


@functools.cache
def demo_budget() -> int:
    """D526: how many of our sandboxes run beside an owner demo, and how many tasks a batch job keeps in flight
    meanwhile: the efficiency cores (``hw.perflevel1.logicalcpu``, 8 of the M2 Ultra's 24), where macOS runs
    background QoS on Apple silicon [inferred: a background process did 0.44x a normal one's work per CPU second,
    Step X.59's probe], so the demo keeps the performance cores; a quarter of the CPUs on a Mac of one core type."""
    try:
        levels, eff = subprocess.run(["sysctl", "-n", "hw.nperflevels", "hw.perflevel1.logicalcpu"],
                                     capture_output=True, text=True, timeout=10).stdout.split()[:2]
        if int(levels) >= 2 and int(eff) > 0:
            return int(eff)
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return max(1, (os.cpu_count() or 4) // 4)


def set_background(pid: int, on: bool) -> bool:
    """D526: process ``pid`` into macOS background QoS, ``setpriority(PRIO_DARWIN_PROCESS, pid, PRIO_DARWIN_BG)`` as
    ``taskpolicy -b -p`` does (the lowest CPU priority, every thread at 4, and throttled disk I/O), or back out
    (``on`` False, ``taskpolicy -B``). Set from another process it is that process's external policy, which its exec
    keeps and this can lift again; set on a process by itself it would pass to its children for good, so never this
    process (measured 2026-10-22: a child of a background process stays at 4 when its parent's lifts it). False when
    it fails (the process is gone or not ours; not macOS)."""
    if pid == os.getpid():
        raise ValueError("set_background: not this process (its children would inherit it for good)")
    try:
        os.setpriority(PRIO_DARWIN_PROCESS, pid, PRIO_DARWIN_BG if on else 0)
    except (OSError, AttributeError, ValueError):
        return False
    return True


def descendants(pid: int | None = None) -> list[int]:
    """The processes under ``pid`` (this one): its children, theirs and so on (``ps``)."""
    kids = collections.defaultdict(list)
    ps = subprocess.Popen(["ps", "-A", "-o", "pid=,ppid="], stdout=subprocess.PIPE, text=True)
    for line in ps.communicate()[0].splitlines():
        with contextlib.suppress(ValueError):
            child, parent = map(int, line.split())
            if child != ps.pid:   # ps itself, gone by now
                kids[parent].append(child)
    found, todo = set(), [pid or os.getpid()]
    while todo:
        for child in kids.get(todo.pop(), ()):
            if child not in found:
                found.add(child)
                todo.append(child)
    return sorted(found)


def batch_jobs(root: Path = ROOT) -> list[dict]:
    """The batch jobs holding a token: each one's name, pid, workers and
    tasks ``allowed`` in flight now. A dead job's token is removed."""
    out = []
    for p in sorted((root / "batch").glob("*.json")):
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if alive(j.get("pid")):
            out.append(j)
        else:
            p.unlink(missing_ok=True)
    return out


class BatchToken:
    """A CPU-heavy batch job's token: ``with BatchToken("rando derive",
    workers) as tok:`` registers the job (``<root>/batch/<pid>.json``,
    which the harness's ``slots`` lists), and :meth:`allowed` says how many
    tasks it may keep in flight: ``workers``, one while a sitting
    waits for free cores (:func:`core_waits`), and at most
    :func:`demo_budget` while an owner demo plays (D526), when its
    processes below it (the pool's workers) run at background priority
    (:func:`set_background`; this process stays as it is) until the demo
    ends. :meth:`completed` and :meth:`ordered` run a ``concurrent.futures``
    pool's tasks under that cap, checked at each task boundary and at
    least every poll (:meth:`wait`), so a job gives way within one task's
    time and takes its workers back within a poll or two of the queue
    emptying. Inert (always ``workers``, no file) off macOS, where
    no sandbox runs, and under pytest: a full suite already holds a
    third sandbox back, so giving way there gains nothing. ``lease``: the
    owner-demo file read (default :data:`OWNER_DEMO`)."""

    POLL_S = 2.0   # the queue is read at most this often

    def __init__(self, name: str, workers: int, *, root: Path | None = None, lease: Path | None = None) -> None:
        self.name, self.workers = name, max(1, workers)
        self.root, self.lease = root or ROOT, lease
        self.inert = root is None and (sys.platform != "darwin" or "PYTEST_CURRENT_TEST" in os.environ)
        self.cap, self._read_at, self.path = self.workers, -math.inf, None
        self.demo, self._bg = False, set()   # an owner demo plays; the workers this job put in the background
        if not self.inert:
            (self.root / "batch").mkdir(parents=True, exist_ok=True)
            self.path = self.root / "batch" / f"{os.getpid()}.json"
            self._save()

    def _save(self) -> None:
        _write(self.path, {"name": self.name, "pid": os.getpid(), "workers": self.workers, "allowed": self.cap,
                           "background": self.demo})

    def __enter__(self) -> BatchToken:
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def close(self) -> None:
        if self._bg:
            self._background(None)
        if self.path is not None:
            self.path.unlink(missing_ok=True)
            self.path = None

    def allowed(self) -> int:
        """The tasks this job may keep in flight now."""
        self._poll()
        return self.cap

    def _poll(self) -> None:
        """Read the queue and the owner demo, at most every ``POLL_S``: the cap, and the workers' priority."""
        if self.inert or time.monotonic() - self._read_at < self.POLL_S:
            return
        self._read_at = time.monotonic()
        waiting, demo = core_waits(self.root), demo_pid(self.lease)
        cap = 1 if waiting else min(self.workers, demo_budget()) if demo else self.workers
        self._background(demo)
        if (cap, demo is not None) != (self.cap, self.demo):
            self.cap, self.demo = cap, demo is not None
            self._save()
            said = (f"{waiting} xemu sitting(s) wait for free cores; giving way: {cap} task(s) in flight" if waiting
                    else f"{cap} task(s) in flight" if demo
                    else f"no xemu sitting waits for cores and no owner demo plays; {cap} task(s) in flight again")
            print(f"{self.name}: {said}" + ("; an owner demo plays: its workers at background priority (D526)"
                                            if demo else ""), file=sys.stderr, flush=True)

    def _background(self, demo: int | None) -> None:
        """While the owner demo ``demo`` (its pid) plays, every process below this one (the pool's workers, a new one
        within a poll) at background priority; once it ends, the ones this job put there back out (D526)."""
        if demo is not None:
            for pid in descendants():
                if pid not in self._bg and pid != demo and set_background(pid, True):
                    self._bg.add(pid)
        elif self._bg:
            for pid in sorted(self._bg & set(descendants())):
                set_background(pid, False)
            self._bg.clear()

    def wait(self, running) -> set:
        """The futures of ``running`` that finished within a poll (``POLL_S``, at least 0.05 s), maybe none: a loop
        that tops its pool up to :meth:`allowed` between waits takes its workers back within about two polls of the
        last waiting sitting going, not only when a task ends (AZ-563); the owner demo is followed meanwhile too."""
        from concurrent.futures import FIRST_COMPLETED, wait
        self._poll()
        return wait(running, timeout=max(self.POLL_S, 0.05), return_when=FIRST_COMPLETED)[0]

    def _stream(self, pool, fn, argses):
        todo = list(enumerate(argses))[::-1]
        running: dict = {}
        while todo or running:
            while todo and len(running) < self.allowed():
                i, args = todo.pop()
                running[pool.submit(fn, *args)] = i
            for f in self.wait(running):
                yield running.pop(f), f

    def completed(self, pool, fn, argses):
        """Each future of ``fn(*args)`` for ``args`` in ``argses``, submitted
        to ``pool`` with at most :meth:`allowed` in flight, as it finishes."""
        for _, f in self._stream(pool, fn, argses):
            yield f

    def ordered(self, pool, fn, argses):
        """The results of ``fn(*args)`` in ``argses``' order, run as
        :meth:`completed` runs them."""
        done, nxt = {}, 0
        for i, f in self._stream(pool, fn, argses):
            done[i] = f
            while nxt in done:
                yield done.pop(nxt).result()
                nxt += 1


_WAY_AT = -math.inf   # when give_way last read the queue (in this process)


def give_way(stop=None, *, root: Path | None = None) -> float:
    """For a batch task that runs for hours (a trick exploration, which
    BatchToken's per-task cap can't hold back), called between its steps:
    while a sitting waits for free cores (:func:`core_waits`), sleep until none does or ``stop()``;
    the seconds slept. The queue is read at most every ``POLL_S``; inert
    where BatchToken is (off macOS, under pytest) unless ``root`` is given."""
    global _WAY_AT
    if root is None and (sys.platform != "darwin" or "PYTEST_CURRENT_TEST" in os.environ):
        return 0.0
    t0 = time.monotonic()
    if t0 - _WAY_AT < BatchToken.POLL_S:
        return 0.0
    _WAY_AT = t0
    while core_waits(root or ROOT) and not (stop is not None and stop()):
        time.sleep(BatchToken.POLL_S)
    return time.monotonic() - t0
