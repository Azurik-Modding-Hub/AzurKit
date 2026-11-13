"""The app's work ahead (Step 4.3w; D1006, D1007, D1014): ``app.ahead``'s
slots, keyed by the recipe, the image, the content folder's
``installed.json`` and the page's change number, whose answer a click
takes; the Cancel that keeps a seed's fill; and ``core.host``'s
background priority and memory on each OS. The jobs here are stand-ins
for the engine's build (``tests/test_hosts.py`` holds the wiring), keeping
their fill the way the randomizer keeps its own: once it is whole."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time
import types

import pytest

from azurkit.app import ahead
from azurkit.app.ahead import Ahead
from azurkit.app.engine import Cancelled
from azurkit.core import host
from azurkit.core.progress import record
from azurkit.tools.characters import content


class Stand:
    """A stand-in build: a seed's fill of :attr:`FILL` placements (stage
    ``plan``, a record each), kept by seed once whole, then a record per
    pack; its answer the sha256 of the fill, the packs and the content
    folder's record. :attr:`hold` is the record a run waits at until
    :attr:`go` is set (:attr:`held` once it has reached it)."""

    FILL = 4

    def __init__(self, root):
        self.root, self.fills, self.fillings, self.runs, self.running, self.most = root, {}, 0, 0, 0, 0
        self.hold, self.held, self.go, self.lock = None, threading.Event(), threading.Event(), threading.Lock()

    def fn(self, recipe):
        return lambda job: self.make(recipe, job.progress)

    def make(self, recipe, progress=lambda step: None) -> str:
        with self.lock:
            self.runs, self.running = self.runs + 1, self.running + 1
            self.most = max(self.most, self.running)
        try:
            h = hashlib.sha256(json.dumps(content.installed(self.root), sort_keys=True).encode())
            if (seed := recipe.get("seed")) is not None:
                if (fill := self.fills.get(seed)) is None:
                    self.fillings += 1
                    placed = []
                    for i in range(self.FILL):
                        self._at(progress, record("plan", None, i, self.FILL))
                        placed.append(hashlib.sha256(f"{seed}:{i}".encode()).hexdigest())
                    fill = self.fills[seed] = placed   # whole, or not at all
                h.update("".join(fill).encode())
            for i, pack in enumerate(recipe["packs"]):
                self._at(progress, record("pack", f"Applying {pack}", i, len(recipe["packs"])))
                h.update(pack.encode())
            return h.hexdigest()
        finally:
            with self.lock:
                self.running -= 1

    def _at(self, progress, step: dict) -> None:
        progress(step)
        if self.hold == (step["stage"], step["done"]):
            self.held.set()
            assert self.go.wait(10)


class Click:
    """``Ahead.take`` on a thread of its own: its answer or what it raised, and the records it followed."""

    def __init__(self, slots: Ahead, kind: str, key: str | None, fn):
        self.got, self.value, self.error = [], None, None
        self.thread = threading.Thread(target=self._run, args=(slots, kind, key, fn), daemon=True)
        self.thread.start()

    def _run(self, slots, kind, key, fn):
        try:
            self.value = slots.take(kind, key, fn, self.got.append)
        except BaseException as exc:
            self.error = exc

    def end(self, within: float = 10):
        self.thread.join(within)
        assert not self.thread.is_alive()
        return self


def _until(test, within: float = 10) -> None:
    end = time.monotonic() + within
    while not test():
        assert time.monotonic() < end
        time.sleep(0.01)


@pytest.fixture
def setup(tmp_path):
    """A content folder, an image to stamp, a seed's recipe, another
    recipe, and their keys over that folder."""
    root, image = tmp_path / "content", tmp_path / "in.iso"
    root.mkdir()
    image.write_bytes(b"stand-in image")
    seeded = {"iso": str(image), "packs": ["fps_unlock", "gravity"], "seed": "2"}
    other = {"iso": str(image), "packs": ["gravity"]}
    return types.SimpleNamespace(root=root, seeded=seeded, other=other, stand=Stand(root),
                                 key=lambda recipe: ahead.key(recipe, root=root))


@pytest.mark.parametrize("when", ["mid-flight", "after it ends", "stopped, then remade", "after an Update",
                                  "a recipe file's character"])
def test_a_click_takes_the_work_ahead_of_its_key_and_answers_as_a_plain_run(setup, when):
    """A Build that finds its recipe worked out ahead takes that job,
    running (its records followed from the last) or done, and answers as a
    plain run does; an offer of another recipe at a newer change stops the
    job at its next record, keeping nothing of its fill, and starts once it
    has ended (never two jobs of a slot at once), while an older change's
    offer is refused; an Update changes the key, so the click after it
    runs again, on the content as it is now (C6). A recipe file's
    character has no key (the file's contents aren't in one), so nothing
    of it goes ahead and its click runs its own."""
    s, slots = setup.stand, Ahead()
    k = setup.key(setup.seeded)
    if when == "mid-flight":
        s.hold = ("pack", 0)
        assert slots.offer("build", 1, k, s.fn(setup.seeded)) and s.held.wait(10)
        click = Click(slots, "build", k, s.fn(setup.seeded))
        _until(lambda: click.got)
        s.go.set()
        assert click.end().got[0] == record("pack", "Applying fps_unlock", 0, 2) and s.runs == 1
    elif when == "after it ends":
        assert slots.offer("build", 1, k, s.fn(setup.seeded))
        assert slots.job("build").done.wait(10)
        click = Click(slots, "build", k, s.fn(setup.seeded)).end()
        assert (click.got, s.runs) == ([], 1)
    elif when == "stopped, then remade":
        s.hold = ("plan", 1)
        assert slots.offer("build", 1, k, s.fn(setup.seeded)) and s.held.wait(10)
        first = slots.job("build")
        assert slots.offer("build", 3, setup.key(setup.other), s.fn(setup.other))
        assert not slots.offer("build", 2, k, s.fn(setup.seeded))   # an older change's, arriving late
        s.go.set()
        assert first.done.wait(10) and isinstance(first.error, Cancelled) and first.step["stage"] == "plan"
        assert "2" not in s.fills and slots.job("build").done.wait(10)   # the other recipe's, once it ended
        assert slots.offer("build", 4, k, s.fn(setup.seeded))
        click = Click(slots, "build", k, s.fn(setup.seeded)).end()
        assert (s.runs, s.most) == (3, 1)
    elif when == "after an Update":
        assert slots.offer("build", 1, k, s.fn(setup.seeded)) and slots.job("build").done.wait(10)
        stale = slots.job("build").value
        (setup.root / content.INSTALLED).write_text(json.dumps({"booblord": {"version": "2", "files": {}}}))
        assert setup.key(setup.seeded) != k
        click = Click(slots, "build", setup.key(setup.seeded), s.fn(setup.seeded)).end()
        assert click.value != stale and s.runs == 2
    else:
        worn = setup.seeded | {"character": {"species": "mine", "variant_file": str(setup.root / "recipes.json")}}
        assert setup.key(worn) is None and not slots.offer("build", 1, setup.key(worn), s.fn(worn))
        click = Click(slots, "build", setup.key(worn), s.fn(worn)).end()
        assert s.runs == 1
    assert (click.error, click.value) == (None, Stand(setup.root).make(setup.seeded))


@pytest.mark.parametrize("then", ["Build while its fill runs on", "Build after its fill", "a change", "silence",
                                  "an offer before it"])
def test_cancel_answers_at_once_and_keeps_the_seeds_fill_for_the_same_settings(setup, then, monkeypatch):
    """The player's Cancel answers Cancelled at once, mid-fill; the job runs
    on through its fill, kept for the next Build of the same settings, and
    stops at its first record past it: a Build meanwhile takes the job
    back, one after it takes the kept fill, each the plain run's answer.
    A change stops it at its next record, mid-fill, keeping nothing; one
    that reaches no record within ``GRACE`` is the host's ``kill``. An
    offer of another recipe while the click runs is refused, so the
    Cancel after it still finds the click's job."""
    if then == "silence":
        monkeypatch.setattr(ahead, "GRACE", 0.3)
    s, killed = setup.stand, []
    slots, k = Ahead(kill=killed.append), setup.key(setup.seeded)
    s.hold = ("plan", 1)
    first = Click(slots, "build", k, s.fn(setup.seeded))
    assert s.held.wait(10)
    job = slots.job("build")
    if then == "an offer before it":
        assert not slots.offer("build", 1, setup.key(setup.other), s.fn(setup.other)) and slots.job("build") is job
    began = time.monotonic()
    assert slots.cancel() and isinstance(first.end().error, Cancelled) and time.monotonic() - began < 1
    plain = Stand(setup.root).make(setup.seeded)
    if then == "Build while its fill runs on":
        again = Click(slots, "build", k, s.fn(setup.seeded))
        _until(lambda: job.state == "taken")
        s.go.set()
        assert (again.end().value, s.runs, s.fillings) == (plain, 1, 1)
    elif then == "Build after its fill":
        s.go.set()
        assert job.done.wait(10) and isinstance(job.error, Cancelled) and job.step["stage"] == "pack"
        again = Click(slots, "build", k, s.fn(setup.seeded)).end()
        assert (again.value, s.runs, s.fillings) == (plain, 2, 1)
    elif then == "a change":
        assert slots.offer("build", 1, setup.key(setup.other), s.fn(setup.other))
        s.go.set()
        assert job.done.wait(10) and isinstance(job.error, Cancelled) and job.step == record("plan", None, 2, 4)
        assert "2" not in s.fills
    elif then == "silence":
        _until(lambda: killed)
        s.go.set()
        assert job.done.wait(10)
    else:
        s.go.set()
        assert job.done.wait(10) and isinstance(job.error, Cancelled) and (slots.job("build"), s.runs) == (job, 1)
    assert killed == ([job] if then == "silence" else [])


def test_work_ahead_runs_at_background_priority_and_past_its_fill_waits_at_its_records_for_another_call(
        setup, monkeypatch):
    """A job ahead runs on its thread at the host's background priority,
    back to normal at its next record once a click takes it. While a click
    or another call is in flight (``Ahead.turn``) it runs on through a
    seed's fill (a Build of that seed may wait on it) and waits at its
    first record past it, going on once the call ends. A recipe whose last
    run peaked over 2 GiB isn't worked ahead on a machine under 16 GiB
    (``ahead.room``), which ``$AZURKIT_RAM`` makes of any machine."""
    calls, s, slots = [], setup.stand, Ahead()
    monkeypatch.setattr(host, "background", lambda process=False: calls.append(("low", threading.current_thread()))
                        or 7)
    def foreground(was, process=False):   # the record its job is at
        job = slots.job("build")
        calls.append((was, threading.current_thread(), job.step["done"] if job._thread is threading.current_thread()
                      else None))
    monkeypatch.setattr(host, "foreground", foreground)
    s.hold = ("plan", 1)
    assert slots.offer("build", 1, setup.key(setup.seeded), s.fn(setup.seeded)) and s.held.wait(10)
    job = slots.job("build")
    with slots.turn():
        s.go.set()
        _until(lambda: job.records == Stand.FILL + 1)
        time.sleep(0.2)
        assert (job.step["stage"], job.records, job.done.is_set()) == ("pack", Stand.FILL + 1, False)
    assert job.done.wait(10)
    three = {"iso": setup.other["iso"], "packs": ["a", "b", "c"]}
    s.hold, s.held, s.go = ("pack", 0), threading.Event(), threading.Event()
    assert slots.offer("build", 3, setup.key(three), s.fn(three)) and s.held.wait(10)
    click, taken = Click(slots, "build", setup.key(three), s.fn(three)), slots.job("build")
    _until(lambda: click.got)
    s.go.set()
    assert click.end().error is None
    assert calls == [("low", job._thread), (7, job._thread, 1), ("low", taken._thread),
                     (7, taken._thread, 1)]   # taken's at its next record, not at its end's (2)
    slots.peaked(setup.key(three), 3 << 30)
    monkeypatch.setattr(host, "ram", lambda: 8 << 30)
    assert slots.offer("build", 4, setup.key(setup.seeded), s.fn(setup.seeded)) and slots.job("build").done.wait(10)
    assert not slots.offer("build", 5, setup.key(three), s.fn(three))
    assert [ahead.room(3 << 30, memory) for memory in (8 << 30, 192 << 30, None)] + [ahead.room(1 << 30, 8 << 30)] \
        == [False, True, False, True]
    monkeypatch.undo()
    monkeypatch.setattr(host, "_physical", lambda: 192 << 30)
    monkeypatch.setenv(host.RAM, str(8 << 30))
    assert (host.ram(), ahead.room(3 << 30)) == (8 << 30, False)


class _Libc:   # macOS's calls, recorded
    def __init__(self, log):
        self.log = log

    def __getattr__(self, name):
        answers = {"qos_class_self": 0x15, "getpriority": 0}
        return lambda *args: self.log.append((name, *args)) or answers.get(name, 0)


class _Kernel32:   # Windows' calls, recorded
    def __init__(self, log):
        self.log = log

    def GlobalMemoryStatusEx(self, ref):
        ref._obj.ullTotalPhys = 8 << 30
        return 1

    def K32GetProcessMemoryInfo(self, process, ref, size):
        self.log.append(("K32GetProcessMemoryInfo", process, size == ref._obj.cb))
        ref._obj.PeakWorkingSetSize = 3 << 30
        return 1

    def __getattr__(self, name):
        answers = {"GetCurrentThread": "thread", "GetCurrentProcess": "process", "GetThreadPriority": 0,
                   "GetPriorityClass": 0x20, "SetThreadPriority": 1, "SetPriorityClass": 1}
        return lambda *args: self.log.append((name, *args)) or answers[name]


def _posix(log):   # Linux's nice, recorded: a lower nice needs privilege
    state = {"nice": 0}

    def setpriority(which, who, nice):
        log.append(("setpriority", which, who, nice))
        if nice < state["nice"]:
            raise PermissionError(13, "Permission denied")
        state["nice"] = nice
    return types.SimpleNamespace(PRIO_PROCESS=0, environ={}, setpriority=setpriority, sysconf={"SC_PHYS_PAGES": 4,
                                 "SC_PAGE_SIZE": 1 << 30}.__getitem__,
                                 getpriority=lambda which, who: log.append(("getpriority", which, who)) or state["nice"])


def _no_sysconf(name):   # Pyodide's
    raise ValueError(name)


@pytest.mark.parametrize("platform, process, calls, was, back, ram", [
    ("darwin", False, [("qos_class_self",), ("pthread_set_qos_class_self_np", 0x15, -15),
                       ("pthread_set_qos_class_self_np", 0x15, 0)], 0x15, True, 4 << 30),
    ("darwin", True, [("getpriority", 4, 0), ("setpriority", 4, 0, 0x1000), ("setpriority", 4, 0, 0)], 0, True,
     4 << 30),
    ("win32", False, [("GetCurrentThread",), ("GetThreadPriority", "thread"), ("SetThreadPriority", "thread", -1),
                      ("GetCurrentThread",), ("SetThreadPriority", "thread", 0)], 0, True, 8 << 30),
    ("win32", True, [("GetCurrentProcess",), ("GetPriorityClass", "process"), ("SetPriorityClass", "process", 0x4000),
                     ("GetCurrentProcess",), ("SetPriorityClass", "process", 0x20)], 0x20, True, 8 << 30),
    ("linux", False, [("getpriority", 0, 0), ("setpriority", 0, 0, 10), ("getpriority", 0, 0),
                      ("setpriority", 0, 0, 0)], 0, False, 4 << 30),
    ("emscripten", False, [], None, False, None),
])
def test_the_hosts_background_priority_goes_down_and_back_and_its_memory_reads_per_os(
        monkeypatch, platform, process, calls, was, back, ram):
    """``core.host`` on each OS: macOS's thread QoS class and process
    PRIO_DARWIN_BG, Windows' below-normal thread and process priority, each
    back to what it was; POSIX's nice 10, which can't come back without
    privilege; nothing under Pyodide; the machine's memory from sysconf or
    GlobalMemoryStatusEx. On this host, a thread's own calls go down and
    back as its OS's row says."""
    log = []
    monkeypatch.setattr(host, "sys", types.SimpleNamespace(platform=platform))
    monkeypatch.setattr(host, "_libc", lambda: _Libc(log))
    monkeypatch.setattr(host, "_kernel32", lambda: _Kernel32(log))
    if platform == "emscripten":
        monkeypatch.setattr(host, "os", types.SimpleNamespace(environ={}, sysconf=_no_sysconf))
    else:
        monkeypatch.setattr(host, "os", _posix(log))
    got = host.background(process)
    assert (got, host.foreground(got, process), log, host.ram()) == (was, back, calls, ram)


def test_the_pools_peak_reads_this_processs_own_peak_on_every_os(monkeypatch):
    """``host.peak``, which retires a pool child past ``RETIRE`` and keeps a
    heavy job's work ahead off a small machine (``ahead.room``): on this
    host, in bytes, past what this process has touched; on Windows, its
    peak working set from ``K32GetProcessMemoryInfo``."""
    touched = bytearray(b"\x01") * (64 << 20)
    assert host.peak() >= len(touched)
    del touched
    log = []
    monkeypatch.setattr(host, "sys", types.SimpleNamespace(platform="win32"))
    monkeypatch.setattr(host, "_kernel32", lambda: _Kernel32(log))
    assert (host.peak(), log) == (3 << 30, [("GetCurrentProcess",), ("K32GetProcessMemoryInfo", "process", True)])


def _reads():
    """This host's way to read the calling thread's priority, and whether a read is low."""
    if sys.platform == "darwin":
        import ctypes

        libc = ctypes.CDLL(None)
        libc.pthread_self.restype = ctypes.c_void_p
        libc.pthread_get_qos_class_np.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]

        def read():   # the thread's relative priority
            qos, relative = ctypes.c_uint(), ctypes.c_int()
            libc.pthread_get_qos_class_np(libc.pthread_self(), ctypes.byref(qos), ctypes.byref(relative))
            return relative.value

        return read, lambda now: now == host.QOS_LOWEST
    if sys.platform == "win32":
        k = host._kernel32()
        return (lambda: k.GetThreadPriority(k.GetCurrentThread())), (lambda now: now == host.THREAD_BELOW_NORMAL)
    return (lambda: os.getpriority(os.PRIO_PROCESS, 0)), (lambda now: now >= host.NICE)


def test_this_hosts_thread_goes_to_background_priority_and_back():
    """The real calls on this host (``core.host``): a thread's priority read
    back low, then as it was; POSIX's stays low (its known flaw) unless it
    was low already."""
    read, low = _reads()
    seen = []

    def run():
        before = read()
        was = host.background()
        seen.extend([low(read()), host.foreground(was), read() == before,
                     sys.platform in ("darwin", "win32") or before >= host.NICE])
    thread = threading.Thread(target=run)
    thread.start()
    thread.join(10)
    assert seen[:3] == [True, seen[3], seen[3]] and host.ram() > 0


def _is_low(here: int | None = None, item: int = 0) -> bool:   # a pool child's part (``here``: its parent, which fails it)
    assert os.getpid() != here
    read, low = _reads()
    return low(read())


def test_a_fill_or_a_builds_hash_a_player_waits_on_comes_up_to_normal_priority(monkeypatch):
    """Work ahead runs low, but what a call the player waits on waits on comes up (audit pass 2's C2: a priority
    inversion): a seed's fill ahead (its records of a stage ``ahead.KEEPS`` names, which never wait) at its next
    record while such a call is in flight in the engine (a Build of that seed waits on it), and a build's hash,
    started low by a build ahead, at its next tick once a Save waits on it."""
    import collections
    import multiprocessing

    from azurkit.app import engine, procpool
    from azurkit.core import native
    from azurkit.tools.randomizer.planner import fill

    calls = []
    monkeypatch.setattr(native, "CALLS", collections.Counter())   # none an earlier test left: no count before an answer
    monkeypatch.setattr(host, "background", lambda process=False: calls.append(("low", threading.current_thread()))
                        or 7)
    monkeypatch.setattr(host, "foreground", lambda was, process=False: calls.append(
        ("normal", threading.current_thread())) or True)
    monkeypatch.setattr(engine, "orphaned", lambda: None)   # the loop on a thread of this process, not its own
    monkeypatch.setattr(procpool, "install", lambda: None)
    for name in ("WIDTH", "BESIDE"):   # the engine's, put back after
        monkeypatch.setattr(fill, name, getattr(fill, name))
    noted, go, started, release, threads = threading.Event(), threading.Event(), threading.Event(), threading.Event(), []

    def plan(recipe, progress) -> dict:   # a seed's fill ahead, two records of its stage
        threads.append(threading.current_thread())
        progress(record("plan", "Placing the items", 1, 2))
        noted.set()
        assert go.wait(10)
        progress(record("plan", "Placing the items", 2, 2))
        noted.set()
        assert release.wait(10)
        return {}

    def image(recipe) -> dict:   # the player's Build, waiting on that fill
        started.set()
        assert release.wait(10)
        return {}
    monkeypatch.setitem(engine.JOBS, "plan", plan)
    monkeypatch.setitem(engine.JOBS, "image", image)
    here, there = multiprocessing.Pipe()
    loop = threading.Thread(target=engine._main, args=(there,), daemon=True)
    loop.start()
    try:
        here.send(("call", 1, "plan", ({"seed": "2"},), True, False))   # ahead: no click follows it
        assert noted.wait(10)
        alone = list(calls)
        noted.clear()
        here.send(("call", 2, "image", ({"seed": "2"},), False, None))
        assert started.wait(10)
        go.set()
        assert noted.wait(10)
        waited = list(calls)
    finally:
        release.set()
        heard = [here.recv()[:2] for _ in range(4)]   # each record and answer, so the loop never blocks on its pipe
        here.close()
        loop.join(10)
    assert (alone, waited) == ([("low", threads[0])], [("low", threads[0]), ("normal", threads[0])])
    assert sorted(heard) == [("done", 1), ("done", 2), ("progress", 1), ("progress", 1)]

    calls.clear()
    hashing, hashed, built = threading.Event(), threading.Event(), []

    def digest(made, tick) -> str:   # the build's hash: ticks until the test lets it end
        while not hashed.is_set():
            tick(1, 2)
            hashing.set()
            time.sleep(0.01)
        return "ab" * 32
    monkeypatch.setattr(engine.iso, "digest", digest)

    def ahead_build() -> None:   # a build ahead, low, keeps its image
        procpool.Low()(True)
        built.append(engine._Built(types.SimpleNamespace(size=2), {}))
    thread = threading.Thread(target=ahead_build)
    thread.start()
    thread.join(10)
    assert hashing.wait(10)
    saving = threading.Thread(target=lambda: built.append(built[0].sha256(lambda step: None)))
    saving.start()
    try:
        _until(lambda: any(how == "normal" and at.name == "azurkit-hash-build" for how, at in calls))
    finally:
        hashed.set()
        saving.join(10)
    assert [(how, at.name) for how, at in calls if at is not thread] == [
        ("low", "azurkit-hash-build"), ("normal", "azurkit-hash-build")] and built[1] == "ab" * 32


def test_a_low_jobs_pool_parts_and_the_threads_it_starts_run_low_and_a_normal_calls_parts_dont(monkeypatch, tmp_path):
    """What a job ahead no click follows starts runs at its priority (review
    D3 of Step 4.3r4g: D1007's every core at low priority held its own
    thread alone): a part in a pool child, a ``later`` thread and its parts, a
    build's hash, the sdk's two hash pools. The child comes back up after the part, so a call the
    player waits on gets normal priority from the same children (POSIX's
    nice has no way back: a low part's child leaves instead)."""
    from azurkit import sdk
    from azurkit.app import engine, procpool
    from azurkit.tools.characters import pool

    monkeypatch.delenv(procpool.CORES, raising=False)
    monkeypatch.setattr(engine.iso, "digest", lambda made, tick: _is_low())
    for module, name in ((sdk, "INHERIT"), (pool, "MAP"), (pool, "LATER")):   # the engine's install, put back after
        monkeypatch.setattr(module, name, getattr(module, name))
    procpool.install()
    here, parts, seen = os.getpid(), [0, 1], {}
    (tmp_path / "a").write_bytes(b"a")

    def checked() -> list[bool]:   # sdk._digests' threads, as each file's hash reports
        lows = []
        steps = types.SimpleNamespace(counter=lambda stage, label: lambda done, total: lows.append(_is_low()))
        sdk._digests(str(tmp_path / "a"), steps, [("a", 0, 1)])
        return lows

    def run(low: bool) -> None:
        if low:
            ahead.Low()(True)
        kept = engine._Built(None, {})
        kept.ended.wait(60)
        seen[low] = (procpool.map_(_is_low, here, parts), procpool.later(_is_low).result(),
                     procpool.later(procpool.map_, _is_low, here, parts).result(), kept.sha,
                     sdk._map(_is_low, parts), checked())
    procpool.stop()
    try:
        for low in (True, False):
            thread = threading.Thread(target=run, args=(low,))
            thread.start()
            thread.join(120)
            if low and sys.platform in ("darwin", "win32"):
                assert len(procpool._IDLE) >= 2   # the same children, for the normal call's parts
    finally:
        procpool.stop()
    normal = _is_low()
    assert (seen[True], seen[False]) == (([True, True], True, [True, True], True, [True, True], [True]),
                                         ([normal, normal], normal, [normal, normal], normal, [normal, normal], [normal]))
