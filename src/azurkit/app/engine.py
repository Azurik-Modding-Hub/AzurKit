"""The app's engine (Step 4.3i): where the page's long calls run (:data:`JOBS`:
a build, a save, a seed's plan, a character's pictures and its G4 match).

:class:`Here` runs them on the caller's thread, the server's request thread
(:func:`azurkit.app.serve`'s default, as the app ran them before). :class:`Spawned`,
the app's (:func:`azurkit.app.main`), runs them in one process of its own,
spawned (never forked), each call on a thread of that process as the server
ran them, so the server's own answers (the image's check, the species list,
the setup, the Randomizer tab, the tracker) never wait on a build's Python;
the process keeps what a call keeps for the next (a dressed body, the
randomizer's logic), and reads ahead what the page's next calls will
(:meth:`Spawned.warm`: the image it picked, the randomizer). Cancelling a build kills that process and spawns
another at once (a build writes nothing, D35); a call of another kind that
the kill cut short runs again in the new one. A save is cancelled from its
progress, as before: it removes its own part file. Closing kills the
process (the server first waits on a save); a process whose parent is gone
exits too (Cmd-Q runs no ``finally``), and ignores Ctrl-C, which the
server answers. Every result and refusal crosses as a pickle, so
a call's refusal is the sdk's own exception, with its message."""

from __future__ import annotations

import base64
import itertools
import multiprocessing
import multiprocessing.connection
import os
import pickle
import queue
import signal
import threading
from collections.abc import Callable, Mapping

from azurkit import sdk
from azurkit.tools import randomizer


class Cancelled(Exception):
    """The page cancelled the build or the save."""


class Gone(Exception):
    """The engine's process ended before it answered: closed, or it died."""


_WARM = threading.Lock()   # held while the randomizer's logic is built, so a seed's build or plan waits on it


def _image(recipe: Mapping) -> dict:
    made, report = sdk.image(recipe)
    return {"size": made.size, "report": report}


def _save(recipe: Mapping, out: str, progress: Callable[[int, int], object] | None = None) -> dict:
    return sdk.build(recipe, out, progress=progress)


def _preview(recipe: Mapping) -> dict:
    return {k: base64.b64encode(v).decode() for k, v in sdk.preview(recipe).items()}


def _warmed(job: Callable, always: bool = False) -> Callable:
    """``job``, run once a warm-up in flight has built the randomizer's
    logic, when ``always`` or its recipe has a randomizer."""
    def run(recipe, *args, **kwargs):
        if always or not isinstance(recipe, Mapping) or recipe.get("randomizer"):
            with _WARM:
                pass
        return job(recipe, *args, **kwargs)
    return run


JOBS: dict[str, Callable] = {"image": _warmed(_image), "save": _warmed(_save),
                             "plan": _warmed(lambda recipe: sdk.plan(recipe), always=True),
                             "preview": _preview, "match": lambda recipe: sdk.match(recipe)}
"""The calls an engine runs: ``{name: fn}``, ``fn(*args)`` (``progress=`` too for ``save``)."""
KILLS = {"image"}
"""The calls a cancel kills (a save cancels itself; the rest the page can't cancel)."""


class Here:
    """The engine on the caller's thread: a build runs on after Cancel (its
    answer is the server's to refuse); a save sees it in its progress."""

    def call(self, job: str, *args, progress: Callable[[int, int], object] | None = None):
        return JOBS[job](*args, **({"progress": progress} if progress is not None else {}))

    def cancel(self) -> None:
        pass

    def warm(self, what: str, *args) -> None:
        pass

    def close(self) -> None:
        pass


class _Child:
    """One spawned engine process: its pipe and the calls waiting on it
    (:attr:`lock`: them, :attr:`dead` and the pipe's sends)."""

    def __init__(self, process, conn):
        self.process, self.conn, self.lock = process, conn, threading.Lock()
        self.calls: dict[int, tuple[str, queue.SimpleQueue]] = {}
        self.killed = False   # by a cancel: its calls of KILLS are cancelled, the others run again
        self.dead = False

    def send(self, message: tuple) -> bool:
        """Send ``message`` (:attr:`lock` held); ``False`` once the process is gone."""
        try:
            self.conn.send(message)
            return True
        except (OSError, ValueError):
            return False


class Spawned:
    """The engine in a process of its own (the module's docstring)."""

    def __init__(self):
        self._context = multiprocessing.get_context("spawn")
        self._lock = threading.Lock()   # the process in use, spawning the next, closing
        self._ids = itertools.count(1)
        self._closed, self._warms = False, {}
        with self._lock:
            self._child = self._spawn()

    @property
    def pid(self) -> int | None:
        """The process in use's id."""
        return self._child.process.pid

    def _spawn(self) -> _Child:
        here, there = self._context.Pipe()
        process = self._context.Process(target=_main, args=(there,), name="azurkit-engine")
        process.start()
        there.close()
        child = _Child(process, here)
        threading.Thread(target=self._read, args=(child,), name="azurkit-engine-reader", daemon=True).start()
        with child.lock:
            for what, args in self._warms.items():
                child.send(("warm", what, args))
        return child

    @staticmethod
    def _read(child: _Child) -> None:
        """The child's answers to the calls waiting on them, until it ends."""
        try:
            while True:
                kind, ident, value = child.conn.recv()
                with child.lock:
                    waiting = child.calls.get(ident)
                if waiting is not None:
                    waiting[1].put((kind, value))
        except (EOFError, OSError):
            pass
        with child.lock:
            child.dead, waiting = True, list(child.calls.values())
            child.calls.clear()
        for _, answers in waiting:
            answers.put(("gone", None))
        child.process.join()
        child.conn.close()

    def call(self, job: str, *args, progress: Callable[[int, int], object] | None = None):
        """``JOBS[job](*args)`` in the engine's process: its result, or what
        it raised; :class:`Cancelled` when a cancel killed it, :class:`Gone`
        when the process ended otherwise (a later call spawns another)."""
        while True:
            with self._lock:
                if self._closed:
                    raise Gone("AzurKit is quitting")
                if self._child.dead:
                    self._child = self._spawn()
                child = self._child
            ident, answers = next(self._ids), queue.SimpleQueue()
            with child.lock:
                sent = not child.dead and child.send(("call", ident, job, args, progress is not None))
                if sent:
                    child.calls[ident] = (job, answers)
                else:
                    child.dead = True
            if not sent:
                continue
            try:
                done, value = self._wait(child, ident, job, answers, progress)
            finally:
                with child.lock:
                    child.calls.pop(ident, None)
            if done:
                return value
            if self._closed:
                raise Gone("AzurKit is quitting")
            if child.killed and job in KILLS:
                raise Cancelled
            if not child.killed:
                raise Gone("AzurKit's engine stopped (out of memory?): try again")
            # cut short by a cancel of another call: run again in the new process

    @staticmethod
    def _wait(child: _Child, ident: int, job: str, answers: queue.SimpleQueue, progress) -> tuple[bool, object]:
        """``(True, the call's result)``, raising what it raised; ``(False,
        None)`` when its process ended first."""
        stopping = False
        while True:
            kind, value = answers.get()
            if kind == "gone":
                return False, None
            if kind == "progress":
                try:
                    if not stopping:
                        progress(*value)
                except Cancelled:   # the save stops at its next chunk and removes its part file
                    stopping = True
                    with child.lock:
                        child.send(("cancel", ident))
                continue
            try:
                value = pickle.loads(value)
            except Exception as exc:   # an answer this process can't read
                raise RuntimeError(f"the engine's answer to {job}: {exc}") from None
            if kind == "raised":
                raise value
            return True, value

    def cancel(self) -> None:
        """Kill a build in flight (the process, at once) and spawn the next
        engine; nothing when none is in flight."""
        with self._lock:
            child = self._child
            with child.lock:
                building = any(job in KILLS for job, _ in child.calls.values())
            if self._closed or not building:
                return
            child.killed = True
            child.process.kill()
            self._child = self._spawn()

    def warm(self, what: str, *args) -> None:
        """Read now what the engine's calls will (:data:`WARMS`: the
        randomizer's logic, as the server builds its own, so a seed's build
        or plan never builds it; the image the page picked, as the server
        checks it, so its pictures never wait on that), in this process and
        in each one a cancel spawns."""
        with self._lock:
            if self._closed or self._warms.get(what) == args:
                return
            self._warms[what], child = args, self._child
            with child.lock:
                child.send(("warm", what, args))

    def close(self) -> None:
        """End the engine at once (it holds nothing to finish: the server
        waits on a save before it closes it), and return once it has ended."""
        with self._lock:
            self._closed, child = True, self._child
        child.process.kill()
        child.process.join()


def orphaned() -> None:
    """End this process when its parent's ends (a thread that waits on the
    parent's sentinel), and leave Ctrl-C to the parent: a spawned child's."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    if (parent := multiprocessing.parent_process()) is not None:
        threading.Thread(target=lambda: (multiprocessing.connection.wait([parent.sentinel]), os._exit(1)),
                         name="azurkit-orphaned", daemon=True).start()


def _warm_logic() -> None:
    """Build the randomizer's logic, :data:`_WARM` held (taken by the caller)."""
    try:
        randomizer.kept_logic()
    finally:
        _WARM.release()


def _warm_image(iso: str) -> None:
    """Check and read the image at ``iso`` as the pictures do (``sdk.pickers``); a refusal is the page's own call's."""
    try:
        sdk.pickers({"iso": iso})
    except (OSError, ValueError):
        pass


WARMS = {"randomizer": _warm_logic, "image": _warm_image}
"""What :meth:`Spawned.warm` reads ahead: ``{what: fn(*args)}``."""


def _main(conn) -> None:
    """The engine's process: each call on a thread of its own, its answers
    and its save's progress sent back as they come."""
    orphaned()
    sending, stops = threading.Lock(), {}

    def send(kind: str, ident: int, value) -> None:
        if kind != "progress":
            try:
                value = pickle.dumps(value, pickle.HIGHEST_PROTOCOL)
            except Exception as exc:   # a result or an error that doesn't pickle: its type and message
                kind, value = "raised", pickle.dumps(RuntimeError(f"{type(value).__name__}: {value} ({exc})"))
        with sending:
            conn.send((kind, ident, value))

    def run(ident: int, job: str, args: tuple, follows: bool) -> None:
        stop = stops[ident]

        def progress(done: int, total: int) -> None:
            send("progress", ident, (done, total))
            if stop.is_set():
                raise Cancelled
        try:
            value = JOBS[job](*args, **({"progress": progress} if follows else {}))
        except BaseException as exc:
            send("raised", ident, exc)
        else:
            send("done", ident, value)
        finally:
            stops.pop(ident, None)

    while True:
        try:
            message = conn.recv()
        except (EOFError, OSError):
            return
        if message[0] == "cancel":
            if (stop := stops.get(message[1])) is not None:
                stop.set()
            continue
        if message[0] == "warm":
            _, what, args = message
            if what == "randomizer":   # taken here, before any call this loop reads after it starts
                _WARM.acquire()
            threading.Thread(target=WARMS[what], args=args, name=f"azurkit-warm-{what}", daemon=True).start()
            continue
        _, ident, job, args, follows = message
        stops[ident] = threading.Event()
        threading.Thread(target=run, args=(ident, job, args, follows), name=f"azurkit-{job}", daemon=True).start()
