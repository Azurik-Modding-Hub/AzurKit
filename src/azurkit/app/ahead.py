"""The app's work ahead (Step 4.3w; D1006, D1007, D1014): what the page
will ask next, worked out before it asks, so its click waits only for the
rest.

:class:`Ahead` keeps one slot per kind (:data:`KINDS`: a seed's plan, its
first tracker view, a build), each holding one :class:`Job`: ``fn(job)``
on a thread of its own, reporting through ``job.progress``, whose records
(``core.progress``) are its checkpoints. A job is keyed by :func:`key`: the
recipe's canonical JSON, what else its answer comes from (``extra``: the
sliders' share string, a plan's sha256), the image's stamp, the content
folder's ``installed.json`` and AzurKit's version, so a key that matches is
the same answer, and a key that misses an input only misses.

- **Work ahead** (:meth:`Ahead.offer`: the page's ``api/prefetch`` and
  ``api/speculate``, once its settings settle) carries the page's change
  number, ``gen``, which every change bumps (an Install, Update or Remove
  too). An offer older than the newest is refused; one of the same key
  keeps its job (a letter typed and deleted costs nothing); one of another
  key stops the job at its next record, and the new job starts once that
  one has ended, so a slot never runs two (a build holds GiBs). While a
  click follows the slot's job, nothing else goes ahead of it there (the
  offer is refused), so its Cancel finds it.
  :meth:`Ahead.change` stops every job of an older change no click
  follows. Work ahead runs at the host's background priority
  (``core.host``, :class:`Low`) and, past a seed's fill (which another
  call may be waiting on), waits at its records while a click or another
  call is in flight in this process (:meth:`Ahead.turn`: they share its
  GIL).
- **The click** (:meth:`Ahead.take`: Build, Track, the tracker's first
  view) takes a job of its key, running (its records followed from the
  last, at normal priority) or done; else it runs its own, in the slot.
  A job that raised is never taken: the click works it out again.
- **Cancel** (:meth:`Ahead.cancel`): the click gets :class:`Cancelled` at
  once and its job is demoted to work ahead: it runs on through the stages
  :data:`KEEPS` names (a seed's fill, kept for the next Build of the same
  settings) and stops at its first record of another stage, or at any
  change; a Build of the same settings takes it back. A stopped or
  demoted job that reaches no record within :data:`GRACE` seconds is the
  host's ``kill(job)`` (the app's engine process, killed and spawned again,
  as before).

A taken answer is what a plain run of the same ``fn`` gives: the engine's
stores assign only once a call ends (the kept fill, the kept build, the
swap's cache), so a job stopped at a record leaves nothing half kept. The
jobs live in this process and end with it (D1012)."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import threading
from collections.abc import Callable, Mapping
from pathlib import Path

from azurkit import __version__
from azurkit.core import host

from .engine import Cancelled

KINDS = ("plan", "view", "build")
"""The slots: a seed's plan, its first tracker view, a build."""
KEEPS = frozenset({"plan"})
"""The stages a cancelled job runs on through: the randomizer's logic read and its fill, which it keeps."""
GRACE = 2.0
"""Seconds a stopped or demoted job has to reach its next record before the host's ``kill``."""
PEAK, SMALL_RAM = 2 << 30, 16 << 30
"""A job whose last run peaked over ``PEAK`` bytes runs ahead only on a machine with ``SMALL_RAM`` or more
(:func:`room`): memory, not cores, is what a heavy job ahead takes from a small machine (it runs at background
priority, so a 4-core machine's player keeps the foreground; the site's second worker runs at 4 cores too)."""


def installed(root: Path | None = None) -> str:
    """The sha256 of the content folder's ``installed.json`` record
    (``content.installed``: every entry's version and files)."""
    from azurkit.tools.characters import content as kit

    return hashlib.sha256(json.dumps(kit.installed(root), sort_keys=True).encode()).hexdigest()


def key(recipe: object, extra: object = None, root: Path | None = None) -> str | None:
    """The key of ``recipe``'s answer: its canonical JSON, ``extra``, the
    stamp of the image it names (``iso``: its path, size, modification and
    change times), :func:`installed` and AzurKit's version; ``None`` (no
    work ahead: the click names what it refuses) when that image can't be
    read now or the recipe isn't JSON, and for a recipe file's character
    (``variant_file``: its contents aren't in the key, as
    ``characters.cache_key``)."""
    if isinstance(recipe, Mapping) and isinstance(character := recipe.get("character"), Mapping) \
            and "variant_file" in character:
        return None
    stamp = None
    if isinstance(recipe, Mapping) and "iso" in recipe:
        if not isinstance(path := recipe["iso"], str):
            return None
        try:
            at = os.stat(path)
        except (OSError, ValueError):
            return None
        stamp = [os.path.realpath(path), at.st_size, at.st_mtime_ns, at.st_ctime_ns]
    try:
        text = json.dumps([__version__, recipe, extra, stamp, installed(root)], sort_keys=True)
    except (TypeError, ValueError, RecursionError):
        return None
    return hashlib.sha256(text.encode()).hexdigest()


def room(peak: int | None, memory: int | None = None) -> bool:
    """Whether a job whose last run peaked at ``peak`` bytes may run ahead:
    always, but over :data:`PEAK` only with ``memory`` (``host.ram``:
    ``$AZURKIT_RAM`` too; an unknown is small) of :data:`SMALL_RAM` or more."""
    if peak is None or peak <= PEAK:
        return True
    memory = host.ram() if memory is None else memory
    return memory is not None and memory >= SMALL_RAM


class Low:
    """A thread's background priority (``core.host``), lowered and put
    back on that thread alone (made on it: an OS sets a thread's own)."""

    def __init__(self):
        self.thread, self.was, self.on = threading.current_thread(), None, False

    def __call__(self, on: bool) -> None:
        """Lower the thread (``on``) or put it back, once each way."""
        if threading.current_thread() is not self.thread or on == self.on:
            return
        if on:
            self.was, self.on = host.background(), True
        else:
            host.foreground(self.was)
            self.on = False


class Job:
    """One run of a slot's work, ``fn(job)``: its kind, key and change
    number, its :attr:`state` (``ahead``; ``taken``, a click follows it;
    ``demoted``, cancelled, running on through :data:`KEEPS`; ``stopped``,
    at its next record), its last record (:attr:`step`), :attr:`fore` (set
    while a click follows it: what an engine process of its own reads), and
    once :attr:`done` its answer (:attr:`value`) or what it raised
    (:attr:`error`)."""

    def __init__(self, owner: Ahead, kind: str, key: str | None, gen: int, fn: Callable[[Job], object],
                 then: Callable[[Job], object] | None, state: str):
        self.kind, self.key, self.gen, self.fn, self.then, self.state = kind, key, gen, fn, then, state
        self.step: dict | None = None
        self.records = 0
        self.fore = threading.Event()
        self.done = threading.Event()
        self.value: object = None
        self.error: BaseException | None = None
        self._owner, self._follow, self._claims, self._cancels = owner, None, 0, 0
        self._started, self._thread, self._low = False, None, None

    def progress(self, step: dict) -> None:
        """The job's record: its checkpoint (:class:`Cancelled` once it is
        stopped), its click's bar, its wait while another call is in
        flight."""
        self._owner._checkpoint(self, step)

    def usable(self) -> bool:
        """Whether a click of its key may take it: not stopped, and not ended raising."""
        return self.state != "stopped" and not (self.done.is_set() and self.error is not None)


class Ahead:
    """The slots (the module's docstring); ``kill(job)``, the host's end of
    a job that stops answering (``None``: it runs on to its next record)."""

    def __init__(self, kill: Callable[[Job], object] | None = None):
        self.kill = kill
        self.gen = 0   # the newest change an offer or a change carried
        self._cond = threading.Condition()
        self._calls = 0   # the clicks and other calls in flight (turn())
        self._slots: dict[str, Job] = {}
        self._peaks: dict[str, int] = {}
        self._closed = False

    def job(self, kind: str) -> Job | None:
        """The slot's job, running or done (its last record for the page's bar)."""
        with self._cond:
            return self._slots.get(_kind(kind))

    def offer(self, kind: str, gen: int, key: str | None, fn: Callable[[Job], object],
              then: Callable[[Job], object] | None = None) -> bool:
        """Work ``key``'s answer out ahead with ``fn`` at the page's change
        ``gen``, ``then(job)`` once it is done; whether it is being (or has
        been) worked out. ``key`` ``None``: nothing ahead of ``kind`` now.
        Refused while a click follows the slot's job of another key (its
        Cancel and :meth:`close` read the slot)."""
        with self._cond:
            kind = _kind(kind)
            if self._closed or gen < self.gen:
                return False   # an older change's, arriving late
            self.gen = gen
            job = self._slots.get(kind)
            if key is not None and job is not None and job.key == key and job.usable():
                job.gen = gen
                if job.state == "demoted":   # wanted again: its rest too
                    job.state = "ahead"
                return True
            if job is not None and job.state == "taken" and not job.done.is_set():
                return False   # a click follows it: nothing else ahead of it in the slot until it ends
            self._stop(job)
            if key is None or not room(self._peaks.get(key)):
                return False
            self._start(Job(self, kind, key, gen, fn, then, "ahead"), job)
            return True

    def take(self, kind: str, key: str | None, fn: Callable[[Job], object], report: Callable[[dict], object] | None
             = None, then: Callable[[Job], object] | None = None) -> object:
        """The click's answer: the slot's job of ``key`` (its records
        replayed to ``report`` from its last), else ``fn``'s, run in the
        slot; what it raised; :class:`Cancelled` once :meth:`cancel` or
        :meth:`close` let it go. Other work ahead waits meanwhile
        (:meth:`turn`)."""
        with self._cond:
            kind = _kind(kind)
            if self._closed:
                raise Cancelled
            job = self._slots.get(kind)
            if key is None or job is None or job.key != key or not job.usable():
                self._stop(job)
                job, after = Job(self, kind, key, self.gen, fn, then, "taken"), job
                self._start(job, after)
            else:
                job.state = "taken"
                job.then = job.then or then
            job._follow, job._claims = report, job._claims + 1
            mine, step = job._claims, job.step
            job.fore.set()
            self._cond.notify_all()   # it goes on, at its next record, if it waited
        with self.turn():
            if report is not None and step is not None and not job.done.is_set():
                report(step)   # its bar, from its last record (D1006)
            with self._cond:
                self._cond.wait_for(lambda: job.done.is_set() or job._cancels >= mine)
                if not job.done.is_set():
                    raise Cancelled
        if job.error is not None:
            raise job.error
        return job.value

    def cancel(self, kind: str = "build") -> bool:
        """The player's Cancel of the click following ``kind``'s job: it
        gets :class:`Cancelled` at once and the job is demoted; whether
        there was one."""
        with self._cond:
            job = self._slots.get(_kind(kind))
            if job is None or job.state != "taken" or job.done.is_set():
                return False
            job.state, job._follow, job._cancels = "demoted", None, job._claims
            job.fore.clear()
            self._arm(job)
            self._cond.notify_all()
            return True

    def change(self, gen: int) -> None:
        """The page's change ``gen`` with nothing to offer (an Install,
        Update or Remove): every job of an older change no click follows
        stops at its next record."""
        with self._cond:
            if self._closed or gen < self.gen:
                return
            self.gen = gen
            for job in self._slots.values():
                if job.gen < gen:
                    self._stop(job)

    @contextlib.contextmanager
    def turn(self):
        """A call in this process (``with ahead.turn(): ...``) that work
        ahead waits at its records for, past a seed's fill."""
        with self._cond:
            self._calls += 1
        try:
            yield
        finally:
            with self._cond:
                self._calls -= 1
                self._cond.notify_all()

    def peaked(self, key: str, peak: int) -> None:
        """``key``'s last run peaked at ``peak`` bytes (:func:`room`)."""
        with self._cond:
            self._peaks[key] = peak

    def close(self) -> None:
        """Stop every job at its next record and let every click go (the app quits, D1012)."""
        with self._cond:
            self._closed = True
            for job in self._slots.values():
                if not job.done.is_set():
                    job.state, job._cancels = "stopped", job._claims
            self._cond.notify_all()

    def _start(self, job: Job, after: Job | None) -> None:
        """Put ``job`` in its slot and run it once ``after`` has ended (:attr:`_cond` held)."""
        self._slots[job.kind] = job
        job._thread = threading.Thread(target=self._run, args=(job, after), name=f"azurkit-ahead-{job.kind}",
                                       daemon=True)
        job._thread.start()

    def _run(self, job: Job, after: Job | None) -> None:
        if after is not None:
            after.done.wait()
        with self._cond:
            job._started = job.state != "stopped"
            low = job.state != "taken"
        try:
            if not job._started:
                raise Cancelled
            job._low = Low()
            job._low(low)
            job.value = job.fn(job)
        except BaseException as exc:   # the click that takes it raises it as its own
            job.error = exc
        finally:
            if job._low is not None:
                job._low(False)
            with self._cond:
                job.done.set()
                self._cond.notify_all()
        if job.error is None and job.then is not None and job.state != "stopped":
            with contextlib.suppress(Exception):   # a head start only: its click works it out
                job.then(job)

    def _checkpoint(self, job: Job, step: dict) -> None:
        fill = isinstance(step, Mapping) and step.get("stage") in KEEPS
        with self._cond:
            job.step, job.records = step, job.records + 1
            if job.state == "demoted" and not fill:
                self._stop(job)
            if not fill:   # another call may wait on a fill: it never waits
                self._cond.wait_for(lambda: not self._calls or job.state in ("taken", "stopped"))
            state, follow = job.state, job._follow
        if state == "stopped":
            raise Cancelled
        if job._low is not None:
            job._low(state != "taken")
        if follow is not None:
            follow(step)

    def _stop(self, job: Job | None) -> None:
        """Stop ``job`` at its next record unless a click follows it (:attr:`_cond` held)."""
        if job is not None and job.state in ("ahead", "demoted"):
            job.state = "stopped"
            if not job.done.is_set():
                self._arm(job)
            self._cond.notify_all()

    def _arm(self, job: Job) -> None:
        """``kill(job)`` if it reaches no record within :data:`GRACE` seconds and is still stopped or demoted."""
        if self.kill is None:
            return
        seen = job.records

        def watch() -> None:
            if job.done.wait(GRACE):
                return
            with self._cond:
                quiet = job._started and not job.done.is_set() and (
                    job.state == "stopped" or job.state == "demoted" and job.records == seen)
            if quiet:
                self.kill(job)
        threading.Thread(target=watch, name="azurkit-ahead-grace", daemon=True).start()


def _kind(kind: str) -> str:
    if kind not in KINDS:
        raise ValueError(f"ahead: no kind {kind!r} (its kinds: {', '.join(KINDS)})")
    return kind
