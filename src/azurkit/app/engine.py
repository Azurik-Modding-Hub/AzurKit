"""The app's engine (Step 4.3i): where the page's long calls run (:data:`JOBS`:
a build, a save, a seed's plan and its build's spoiler, a plan file's spoiler,
a character's pictures and its G4 match).

:class:`Here` runs them on the caller's thread, the server's request thread
(:func:`azurkit.app.serve`'s default, as the app ran them before). :class:`Spawned`,
the app's (:func:`azurkit.app.main`), runs them in one process of its own,
spawned (never forked), each call on a thread of that process as the server
ran them, so the server's own answers (the image's check, the species list,
the setup, the Randomizer tab, the tracker) never wait on a build's Python;
the process keeps what a call keeps for the next (a dressed body, the
randomizer's logic), and reads ahead what the page's next calls will
(:meth:`Spawned.warm`: the image it picked, the randomizer; the image's once
the logic's read and every build are done, :func:`_warm_image`). A call the
server's work ahead makes (``fore=``, :mod:`.ahead`) runs there at background
priority and, past a seed's fill, waits at its records while a call the player
waits on is in flight. The player's Cancel lets the build go on as work ahead
(``ahead.Ahead.cancel``), keeping this process, its logic and its fill; a job
that reaches no record within ``ahead.GRACE`` kills it (:meth:`Spawned.cancel`)
and another starts at once (a build writes nothing, D35), which reads the logic
before the image; a call the player waits on that the kill cut short runs again
in the new one. A save is cancelled from its
progress, as before: it removes its own part file. A build keeps its image
in the process that made it (the last build's only, a new Build drops it),
hashed there on a thread from the moment it is made, so its Save writes
that image (``sdk.save``) without planning it again and takes the hash
(or waits on it); a save whose build that process no longer keeps (a
cancel's new process) or whose input changed since builds it again
(``sdk.build``), as before. The app's (``Spawned(stores=True)``) keeps
what it works out across launches (:mod:`.swapcache`: the images it
checked, the swap's answers, and a character's pictures and G4 match by
the same key). Closing kills the
process (the server first waits on a save); a process whose parent is gone
exits too (Cmd-Q runs no ``finally``), and ignores Ctrl-C, which the
server answers. Every result and refusal crosses as a pickle, so
a call's refusal is the sdk's own exception, with its message."""

from __future__ import annotations

import base64
import contextlib
import itertools
import multiprocessing
import multiprocessing.connection
import os
import pickle
import queue
import secrets
import signal
import threading
from collections.abc import Callable, Mapping
from pathlib import Path

from azurkit import sdk
from azurkit.core import gate, iso, native
from azurkit.core.progress import Steps, noting, record
from azurkit.edits import files as replaced
from azurkit.tools import characters, randomizer
from azurkit.tools.characters import pool
from azurkit.tools.randomizer.planner import difficulty, fill

from . import procpool


class Cancelled(BaseException):
    """The page cancelled the build or the save, or a change stopped work
    ahead: a BaseException, as KeyboardInterrupt is, so no broad ``except
    Exception`` on its way up swallows it."""


class Gone(Exception):
    """The engine's process ended before it answered: closed, or it died."""


_WARM = threading.Lock()   # held while the randomizer's logic is built, so a seed's build or plan waits on it
_BUILDING = threading.Condition()   # held to count _BUILDS
_BUILDS = 0   # the builds (KILLS' calls) this process has read and not yet answered, which an image's warm waits out
_PLANS = 0   # the plan calls in flight, which the openers ahead wait out too
_NEWEST: list = [None]   # the plan this process finished last: whose spoiler openers are worth working out ahead
_WARMING: list[dict] = []   # that warm-up's records, the newest last, which a call waiting on it shows
_READING = "Reading the randomizer's logic"   # its stage's line


class _Built:
    """A build's image, kept in this process for its Save, with its report,
    and its sha256 hashed on a thread of its own from the moment it is made
    (``iso.digest``: hashlib lets go of the GIL), which the Save takes, or
    waits on, or (a failed or stopped hash) hashes again as it writes."""

    def __init__(self, made, report: dict):
        self.made, self.report = made, report
        self.done, self.sha, self.stopped = 0, None, False
        self.ended = threading.Event()
        threading.Thread(target=self._hash, args=(procpool.inherit(),), name="azurkit-hash-build", daemon=True).start()

    def _hash(self, lower: Callable[[], object]) -> None:
        lower()   # as low as the job that built it, if it is

        def tick(done: int, total: int) -> None:
            self.done = done
            if self.stopped:
                raise Cancelled
        try:
            self.sha = iso.digest(self.made, tick)
        except BaseException:   # stopped, or an image that can't be read now: the Save hashes as it writes
            pass
        finally:
            self.ended.set()

    def holds(self) -> bool:
        """Whether its input is as the build read it (``iso.Image.origin``)."""
        try:
            at = os.stat(self.made.source)
        except (OSError, AttributeError, TypeError):
            return False
        return (at.st_size, at.st_mtime_ns, at.st_ctime_ns) == getattr(self.made, "origin", None)

    def sha256(self, progress: Callable[[dict], object]) -> str:
        """``iso.pack``'s ``sha256=``: the hash, once its thread ends, its
        progress the save's meanwhile (whose cancel stops the wait)."""
        while not self.ended.wait(0.1):
            progress(record("write", "Hashing the saved image", self.done, self.made.size))
        if self.sha is not None:
            return self.sha
        return iso.digest(self.made, lambda done, total: progress(record("write", "Hashing the saved image", done,
                                                                         total)))


_BUILT: dict[str, _Built] = {}   # the last build's image, by its build id (random: a new process never reuses one)
_FOLLOWED = threading.local()    # this thread's call: its progress, the record it reported last, the last tick's percent


@contextlib.contextmanager
def _following(progress: Callable[[dict], object] | None):
    """This thread's call followed by ``progress`` (``None``: by no one):
    the progress it reports through, each record kept as the stage
    :func:`_ticked` counts the swap's items on (``pool.TICK``, set here)."""
    if progress is None:
        yield None
        return
    pool.TICK = _ticked
    _FOLLOWED.progress, _FOLLOWED.last, _FOLLOWED.percent = progress, None, None

    def report(step: dict) -> None:
        _FOLLOWED.last, _FOLLOWED.percent = step, step["percent"]
        progress(step)
    try:
        yield report
    finally:
        _FOLLOWED.progress = _FOLLOWED.last = None


def _ticked(done: int, total: int) -> None:
    """``pool.TICK``: the swap's items done of total (``pool.each``'s, in
    the thread of the call that runs it), on the stage that call reported
    last (else ``dress``), each percent once. On a counted step (a note's k
    of n: ``sdk.match``'s dress) they count inside it, so its bar never goes
    back, a second ``pool.each`` in the step included."""
    if (progress := getattr(_FOLLOWED, "progress", None)) is None:
        return
    last = _FOLLOWED.last or record("dress")
    if last["total"]:
        step = record(last["stage"], last["label"], last["done"] * total + done, last["total"] * total)
        if step["percent"] < (_FOLLOWED.percent or 0):
            return
    else:
        step = record(last["stage"], last["label"], done, total)
    if step["percent"] != _FOLLOWED.percent:
        _FOLLOWED.percent = step["percent"]
        progress(step)


def _drop() -> None:
    """Forget the kept build (a new Build), its hash stopped."""
    for kept in _BUILT.values():
        kept.stopped = True
    _BUILT.clear()


def _picked(recipe: Mapping) -> tuple[dict, dict]:
    """``recipe`` less the server's ``picked`` (``{image's path: the computer
    path the player picked this session}``), and those files' bytes as
    ``sdk.image``'s ``picked``: read here, in the job, so a recipe names a
    file and only a build holds it."""
    recipe = dict(recipe)
    held = recipe.pop("picked", None)
    return recipe, {"picked": {path: Path(replaced.source(file)).read_bytes() for path, file in held.items()}} if held else {}


def _image(recipe: Mapping, progress: Callable[[dict], object] | None = None) -> dict:
    from . import procpool

    _drop()   # before the build: never two builds' images held at once
    recipe, picked = _picked(recipe)
    made, report = sdk.image(recipe, progress=progress, spoiler=False, **picked)   # a seed's spoiler when asked: JOBS' spoiler
    ident = secrets.token_hex(8)
    _BUILT[ident] = _Built(made, report)
    return {"size": made.size, "report": report, "build": ident, "peak": procpool._peak()}


def _save(recipe: Mapping, out: str, build: str | None = None,
          progress: Callable[[dict], object] | None = None) -> dict:
    """Write ``build``'s image (``_image``'s id) when this process keeps it
    and its input is as it read it (``sdk.save``: the report with the
    output's path, size and sha256, as ``sdk.build`` gives), else build
    ``recipe`` again and write it (``sdk.build``). ``progress(record)``
    follows the write; an exception it raises cancels it."""
    report = progress or (lambda _: None)
    kept = _BUILT.get(build) if isinstance(build, str) else None
    if kept is not None and kept.holds():
        return kept.report | sdk.save(kept.made, out, progress=report, sha256=lambda: kept.sha256(report))
    recipe, picked = _picked(recipe)
    return sdk.build(recipe, out, progress=lambda done, total: report(record("write", None, done, total)), **picked)


def _kept(job: str, fn: Callable[[Mapping, Callable | None], dict]) -> Callable[..., dict]:
    """``fn`` (``sdk.preview``, ``sdk.match``), its answer kept in
    ``tools.characters.CACHE`` (the app's store, across launches) under the
    swap's key (``characters.cache_key``: the swap's code, the vanilla
    release the image was checked as, the character, the packs as asked and
    the content folder), where there is one and the image is one the gate
    vouched for as it is now (``gate.vouched``); else ``fn``'s answer."""
    def run(recipe: Mapping, progress: Callable[[dict], object] | None = None) -> dict:
        key = None
        if characters.CACHE is not None and isinstance(recipe, Mapping) and isinstance(recipe.get("iso"), str):
            try:
                stamp = gate.vouched(recipe["iso"], whole=False)
                if stamp is not None:   # a recipe file's character (variant_file) is never kept: cache_key's None
                    key = characters.cache_key(job, characters.normalize(recipe.get("character")), stamp.release,
                                               extra=recipe.get("packs"))
            except (OSError, ValueError, TypeError):
                key = None   # fn names what it refuses
        if key is not None and (blob := characters.CACHE.get(key)) is not None:
            try:
                return pickle.loads(blob)
            except Exception:   # a store from another AzurKit: worked out again
                pass
        found = fn(recipe, progress)
        if key is not None:
            characters.CACHE.put(key, pickle.dumps(found, pickle.HIGHEST_PROTOCOL))
        return found
    return run


_previewed = _kept("preview", lambda recipe, progress=None: sdk.preview(recipe))


def _preview(recipe: Mapping, progress: Callable[[dict], object] | None = None) -> dict:
    return {k: base64.b64encode(v).decode() for k, v in _previewed(recipe).items()}


def _warmed(job: Callable, always: bool = False) -> Callable:
    """``job``, run once a warm-up in flight has built the randomizer's
    logic, when ``always`` or its recipe has a randomizer (its ``progress``
    told the warm-up's records meanwhile, its checks counted)."""
    def run(recipe, *args, **kwargs):
        if always or not isinstance(recipe, Mapping) or recipe.get("randomizer"):
            told, report = None, kwargs.get("progress")
            while not _WARM.acquire(timeout=0.05):
                newest = _WARMING[-1:]   # a slice: the warm-up may clear it meanwhile
                if report is not None and newest and newest[0] is not told:
                    report(told := newest[0])
            _WARM.release()
            if told is not None:   # the warm-up's read was told: the call's own (at once now) isn't, from 0 again
                kwargs["progress"] = lambda step: None if step["label"] == _READING else report(step)
        return job(recipe, *args, **kwargs)
    return run


def _plan(recipe: Mapping, progress: Callable[[dict], object] | None = None) -> dict:
    """A seed's plan; a shaped one's spoiler openers then go on ahead, low, for the spoiler's View, past any build or
    other plan (they share this process's GIL: beside them a Build went from 1.4 s to 3.7 s at the click, a Track's fill
    from 5.4 s to 10.5 s). A call waiting on those
    openers goes first: they run on at its priority, or a build ahead parked for that call and they, paused for the
    build, would hold each other and the call for good. Only the newest plan's are worth working out: a plan with
    another answer ends the last one's at its next note, and the same plan again leaves them running."""
    global _PLANS
    with _BUILDING:
        _PLANS += 1
    try:
        doc = sdk.plan(recipe, progress=progress)
    finally:
        with _BUILDING:
            _PLANS -= 1
    again, _NEWEST[0] = doc == _NEWEST[0], doc
    if doc["settings"].get("seed_difficulty") and not again:
        threading.Thread(target=_openers_ahead, args=(doc,), name="azurkit-openers", daemon=True).start()
    return doc


def _openers_ahead(doc: Mapping) -> None:
    def past_others(_step: dict) -> None:
        with _BUILDING:
            while (_BUILDS or _PLANS) and not difficulty.WAITING and _NEWEST[0] is doc:
                _BUILDING.wait(0.2)
        if _NEWEST[0] is not doc:
            raise Cancelled
        low(not difficulty.WAITING)
    low = procpool.Low()
    low(True)
    with contextlib.suppress(Exception, Cancelled), noting(Steps(past_others)) as steps:   # a head start: the View names its refusal
        steps("spoiler")
        randomizer.openers_ahead(doc)


JOBS: dict[str, Callable] = {"image": _warmed(_image), "save": _warmed(_save), "plan": _warmed(_plan, always=True),
                             "preview": _preview, "match": _kept("match", lambda recipe, progress=None:
                                                                    sdk.match(recipe, progress=progress)),
                             "spoiler": lambda plan, progress=None: sdk.spoiler(plan, built=True, progress=progress),
                             "plan_spoiler": _warmed(lambda plan, progress=None: sdk.spoiler(plan, progress=progress),
                                                     always=True)}
"""The calls an engine runs: ``{name: fn}``, ``fn(*args)`` (``progress=`` too for ``image``, ``save``, ``plan``,
``preview``, ``match``, ``spoiler`` and ``plan_spoiler``: ``core.progress`` records, the swap's items counted on them, :func:`_following`;
``spoiler``: the last build's, which ``image`` leaves out; ``plan_spoiler``: a plan file's, the Tools tab's)."""
KILLS = {"image"}
"""The calls a cancel kills (a save cancels itself; the rest the page can't cancel)."""


class Here:
    """The engine on the caller's thread: a build runs on after Cancel (its
    answer is the server's to refuse); a save sees it in its progress."""

    def call(self, job: str, *args, progress: Callable[[dict], object] | None = None,
             fore: threading.Event | None = None):
        with _following(progress) as report:
            return JOBS[job](*args, **({"progress": report} if report is not None else {}))

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

    def __init__(self, stores: bool = False):
        self._context = multiprocessing.get_context("spawn")
        self._stores = stores   # the process keeps its stamps and swap answers across launches (:mod:`.swapcache`)
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
        process = self._context.Process(target=_main, args=(there, self._stores), name="azurkit-engine")
        process.start()
        there.close()
        child = _Child(process, here)
        threading.Thread(target=self._read, args=(child,), name="azurkit-engine-reader", daemon=True).start()
        with child.lock:
            for message in _warm_messages(self._warms):
                child.send(message)
        return child

    @staticmethod
    def _read(child: _Child) -> None:
        """The child's answers to the calls waiting on them, until it ends."""
        try:
            while True:
                kind, ident, value = child.conn.recv()
                if kind == "calls":   # the server's native.report shows them, whichever process the kill leaves
                    native.CALLS.update(value)
                    continue
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

    def call(self, job: str, *args, progress: Callable[[dict], object] | None = None,
             fore: threading.Event | None = None):
        """``JOBS[job](*args)`` in the engine's process: its result, or what
        it raised; :class:`Cancelled` when a kill cut short a build or work
        ahead no click follows (one the player waits on runs again),
        :class:`Gone` when the process ended otherwise (a later call spawns
        another). ``fore``: a slot's job's (``ahead.Job.fore``), a click
        following it while it is set: the call runs low and waits behind the
        player's calls while it isn't."""
        while True:
            with self._lock:
                if self._closed:
                    raise Gone("AzurKit is quitting")
                if self._child.dead:
                    self._child = self._spawn()
                child = self._child
            ident, answers = next(self._ids), queue.SimpleQueue()
            with child.lock:
                sent = not child.dead and child.send(("call", ident, job, args, progress is not None,
                                                      None if fore is None else fore.is_set()))
                if sent:
                    child.calls[ident] = (job, answers)
                else:
                    child.dead = True
            if not sent:
                continue
            try:
                done, value = self._wait(child, ident, job, answers, progress, fore)
            finally:
                with child.lock:
                    child.calls.pop(ident, None)
            if done:
                return value
            if self._closed:
                raise Gone("AzurKit is quitting")
            if child.killed and (job in KILLS if fore is None else not fore.is_set()):
                raise Cancelled
            if not child.killed:
                raise Gone("AzurKit's engine stopped (out of memory?): try again")
            # cut short by a kill of another call: run again in the new process

    @staticmethod
    def _wait(child: _Child, ident: int, job: str, answers: queue.SimpleQueue, progress,
              fore: threading.Event | None = None) -> tuple[bool, object]:
        """``(True, the call's result)``, raising what it raised; ``(False,
        None)`` when its process ended first. ``fore``'s changes are sent
        on as they come (polled)."""
        stopping, told = False, None if fore is None else fore.is_set()
        while True:
            try:
                kind, value = answers.get(timeout=None if fore is None else 0.05)
            except queue.Empty:
                kind = None
            if fore is not None and fore.is_set() != told:
                told = fore.is_set()
                with child.lock:
                    child.send(("fore", ident, told))
            if kind is None:
                continue
            if kind == "gone":
                return False, None
            if kind == "progress":
                try:
                    if not stopping:
                        progress(value)
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
        """Kill the process (work ahead that reaches no record:
        ``ahead.Ahead``'s kill) and spawn the next engine; nothing when no
        call is in flight."""
        with self._lock:
            child = self._child
            with child.lock:
                calling = bool(child.calls)
            if self._closed or not calling:
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
    """Build the randomizer's logic, :data:`_WARM` held (taken by the caller), each record in :data:`_WARMING`."""
    try:
        sdk.randomizer_logic(progress=lambda step: _WARMING.append(step))
    finally:
        _WARMING.clear()
        _WARM.release()


def _warm_image(iso: str) -> None:
    """Check and read the image at ``iso`` as the pictures do (``sdk.pickers``),
    once the randomizer's logic read in flight (:data:`_WARM`) and every build
    this process has read (:data:`_BUILDS`) are done: after a cancel, the next
    engine reads its logic and builds the seed with no pictures' read beside
    them (about 0.3 s of the GIL off "Cancel a build, then Build", A29). A
    refusal is the page's own call's."""
    with _WARM:
        pass
    with _BUILDING:
        _BUILDING.wait_for(lambda: not _BUILDS)
    try:
        sdk.pickers({"iso": iso})
    except (OSError, ValueError):
        pass


WARMS = {"randomizer": _warm_logic, "image": _warm_image}
"""What :meth:`Spawned.warm` reads ahead: ``{what: fn(*args)}``."""


def _warm_messages(warms: Mapping[str, tuple]) -> list[tuple]:
    """The ``warm`` messages a new engine gets for ``warms`` (:meth:`Spawned.warm`'s
    ``{what: args}``), the randomizer's first: a cancel's next engine reads
    its logic before the image (:func:`_warm_image`)."""
    return [("warm", what, args) for what, args in sorted(warms.items(), key=lambda warm: warm[0] != "randomizer")]


def _main(conn, stores: bool = False) -> None:
    """The engine's process: each call on a thread of its own, its answers
    and its save's progress sent back as they come; with ``stores``, what it
    works out kept across launches (:mod:`.swapcache`)."""
    global _BUILDS
    from . import ahead, swapcache

    orphaned()
    procpool.install()   # the swap's parallel work in children of this process
    fill.WIDTH, fill.LOWERED, fill.LOW = sdk.cores(4), procpool.lowered, procpool.Low   # a shaped fill's attempts past its first at once
    if stores:
        swapcache.install()
    sending, stops, fores = threading.Lock(), {}, {}   # fores: each call's ahead.Job.fore (None: the player's)

    def waited(ident: int) -> bool:
        """Whether a call the player waits on, other than ``ident``, is in flight."""
        return any(other != ident and (fore is None or fore.is_set()) for other, fore in list(fores.items()))

    def send(kind: str, ident: int, value) -> None:
        if kind != "progress":
            try:
                value = pickle.dumps(value, pickle.HIGHEST_PROTOCOL)
            except Exception as exc:   # a result or an error that doesn't pickle: its type and message
                kind, value = "raised", pickle.dumps(RuntimeError(f"{type(value).__name__}: {value} ({exc})"))
        with sending:
            if kind != "progress" and (calls := native.taken()):   # before the answer: a kill loses none answered
                conn.send(("calls", ident, calls))
            conn.send((kind, ident, value))

    def run(ident: int, job: str, args: tuple, follows: bool) -> None:
        global _BUILDS
        stop, fore, low = stops[ident], fores[ident], ahead.Low()
        low(fore is not None and not fore.is_set())

        def progress(step: dict) -> None:
            send("progress", ident, step)
            if fore is not None and not (isinstance(step, dict) and step.get("stage") in ahead.KEEPS):
                while not fore.is_set() and not stop.is_set() and waited(ident):   # never within a fill
                    stop.wait(0.05)
            if stop.is_set():
                raise Cancelled
            low(fore is not None and not fore.is_set())
        try:
            with _following(progress if follows else None) as report:
                value = JOBS[job](*args, **({"progress": report} if follows else {}))
        except BaseException as exc:
            send("raised", ident, exc)
        else:
            send("done", ident, value)
        finally:
            low(False)
            stops.pop(ident, None)
            fores.pop(ident, None)
            if job in KILLS:
                with _BUILDING:
                    _BUILDS -= 1
                    _BUILDING.notify_all()

    while True:
        try:
            message = conn.recv()
        except (EOFError, OSError):
            return
        if message[0] == "cancel":
            if (stop := stops.get(message[1])) is not None:
                stop.set()
            continue
        if message[0] == "fore":
            if (fore := fores.get(message[1])) is not None:
                fore.set() if message[2] else fore.clear()
            continue
        if message[0] == "warm":
            _, what, args = message
            if what == "randomizer":   # taken here, before any call this loop reads after it starts
                _WARM.acquire()
                _WARMING[:] = [record("plan", _READING)]
            threading.Thread(target=WARMS[what], args=args, name=f"azurkit-warm-{what}", daemon=True).start()
            continue
        _, ident, job, args, follows, followed = message
        stops[ident], fores[ident] = threading.Event(), None if followed is None else threading.Event()
        if followed:
            fores[ident].set()
        if job in KILLS:   # counted as it is read, so an image's warm waiting on the logic's read waits it out too
            with _BUILDING:
                _BUILDS += 1
        threading.Thread(target=run, args=(ident, job, args, follows), name=f"azurkit-{job}", daemon=True).start()
