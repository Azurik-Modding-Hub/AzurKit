"""The perf gate's registry and drivers (D980-D985): every player-facing
operation by its id (round 1's table: ``A01``-``A30`` the app's, ``S01``-``S25``
the site's; wave 2's from ``A31`` and ``S26``), each with a start (a click, a launch, a file set) and a
done-state (a DOM condition), and the scenarios that drive them in the app's
serve mode and on the site, headless (D839). ``scripts/perf.py`` runs them
and judges the times; this module only drives and clocks.

The clock is the page's ``performance.now()`` from the action to the
done-state, polled with ``page.evaluate`` (Chromium's headless shell never
fires ``requestAnimationFrame``, and the page's CSP refuses eval:
``tests/_page.py``); a launch is this process's monotonic clock from the
spawn to the page's ready flag, a page start the page's own clock from its
navigation. An init script (outside the page's CSP) logs every change of
the status lines and of any ``<progress>``, so each sample says whether a
bar moved and whether the page showed progress (a bar, or a "k of n" or
"N %" text, changing at least once).

A run is one of :data:`RUNS`: the app (``python -m azurkit serve`` from the
worktree's wheel in a scratch venv, :func:`venv`, so it reads the randomizer
database the wheel ships as a player's install does; with a fresh HOME, its
page in WebKit), the app capped
(``AZURKIT_CORES=4``), the site (``scripts/web_tools.py``'s, served on
127.0.0.1 from port 8900 up) in WebKit, Chromium or Firefox, and the site with each
File read 200 ms late (Safari's read model: one checked substitution in the
served ``worker.mjs``, so no source carries a test hook). First-time ops
take a fresh state each sample (a new HOME or browser context), so a
scenario runs again until each of its ops has its samples. Not collected
(no ``test_`` prefix). No game bytes are printed or kept: times, texts of
the page's status lines, sizes."""

from __future__ import annotations

import contextlib
import dataclasses
import functools
import http.server
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GROUPS = ("start", "image", "build", "characters", "randomizer", "tracker")
LONG = 30.0          # an op with a sample over this runs once (its median is that sample)
SAVE_DIALOG = 3.0    # a player's Save comes this long after the build (the save dialog)
LAG_MS = 200         # Safari's read model: each File read this late (Step 4.1g2 measured about 200 ms)
PORTS = 8900         # the site's server takes the first free port from here


@dataclasses.dataclass(frozen=True)
class Op:
    id: str
    title: str
    group: str            # one of GROUPS
    first: bool = True    # each sample in a fresh state (a new HOME or browser context); else repeated in one
    bar: bool = False     # D982: may pass 3 s with a moving bar (an image's first identity check, the first engine load)
    content: bool = False  # reads a clone of Azurik-Custom-Content
    untimed: str = ""     # why the gate can't time it (it is listed as such)

    @property
    def host(self) -> str:
        return "app" if self.id.startswith("A") else "site"


OPS = {op.id: op for op in (
    Op("A01", "launch -> page ready, first launch", "start"),
    Op("A02", "launch -> ready, remembered setup and plan", "start"),
    Op("A03", "choose the image, first time", "image", bar=True),
    Op("A04", "choose it again", "image", first=False),
    Op("A05", "tabs, a pack's Settings, Copy link (the slowest)", "start"),
    Op("A06", "Randomizer tab, first open", "randomizer"),
    Op("A07", "seed typed, its ask", "randomizer"),
    Op("A08", "Characters tab, no image", "characters"),
    Op("A09", "Characters tab with the image", "characters"),
    Op("A10", "choose keylord (options and pictures)", "characters"),
    Op("A11", "G4 match, keylord", "characters"),
    Op("A12", "Build, defaults", "build"),
    Op("A13", "Save, defaults, after the save dialog", "build"),
    Op("A14", "Save, defaults, clicked at once", "build"),
    Op("A15", "Build keylord, first", "build"),
    Op("A16", "Build keylord again", "build", first=False),
    Op("A17", "Save keylord, after the save dialog", "build"),
    Op("A18", "a variant's pictures (booblord), first", "characters", content=True),
    Op("A19", "a variant's pictures again", "characters", first=False, content=True),
    Op("A20", "Build booblord, first", "build", content=True),
    Op("A21", "Build booblord again", "build", first=False, content=True),
    Op("A22", "Save booblord, after the save dialog", "build", content=True),
    Op("A23", "Track this seed (plan and tracker)", "tracker"),
    Op("A24", "the Tracker's maps, first view", "tracker"),
    Op("A25", "the Tracker at a second launch", "tracker"),
    Op("A26", "Build a seed after Track", "randomizer"),
    Op("A27", "Build a seed, no Track first", "randomizer"),
    Op("A28", "Save the seed, after the save dialog", "randomizer"),
    Op("A29", "Cancel a build, then Build", "randomizer"),
    Op("A30", "a small ask while a build runs (a model's pictures)", "randomizer"),
    Op("A31", "Build booblord reshaped (one slider moved), first", "build", bar=True, content=True),   # D999
    Op("A32", "the same reshape at the next launch", "build", content=True),
    Op("S01", "page start, first visit (the engine load)", "start", bar=True),
    Op("S02", "page start, a return visit", "start", first=False),
    Op("S03", "choose the image, first time", "image", bar=True),
    Op("S04", "choose the same image after a reload", "image", first=False),
    Op("S05", "Build, defaults", "build"),
    Op("S06", "Save (the browser's download)", "build"),
    Op("S07", "Characters tab, no image", "characters"),
    Op("S08", "Characters tab with the image", "characters"),
    Op("S09", "pick -> the weapons answer (the Characters tab open)", "characters"),
    Op("S10", "choose keylord (its info)", "characters"),
    Op("S11", "keylord's pictures", "characters"),
    Op("S12", "a reshaped variant's pictures (beamlord)", "characters", content=True),
    Op("S13", "Install beamlord, the list again", "characters", content=True),
    Op("S14", "Build keylord", "build"),
    Op("S15", "booblord on the site", "build",
       untimed="out of memory on the site (D835): booblord is the app's until the site can hold it"),
    Op("S16", "Randomizer tab, first ask", "randomizer"),
    Op("S17", "seed typed, its ask", "randomizer"),
    Op("S18", "Track this seed", "tracker"),
    Op("S19", "Track click -> the world map with its pictures", "tracker"),
    Op("S20", "the maps' first draw", "tracker"),
    Op("S21", "the tracker, a reopen", "tracker"),
    Op("S22", "a level's map", "tracker", first=False),
    Op("S23", "Build a seed after Track", "randomizer"),
    Op("S24", "Build a seed, no Track first", "randomizer"),
    Op("S25", "the spoiler's View", "randomizer", first=False),
)}


@dataclasses.dataclass(frozen=True)
class Run:
    name: str
    host: str              # app | site
    browser: str           # the page's engine
    cores: int | None = None   # AZURKIT_CORES for the app (the capped profile)
    lag: bool = False      # the site's File reads LAG_MS late
    memory: bool = False   # sample our processes' peak resident size


RUNS = {run.name: run for run in (
    Run("app", "app", "webkit"),
    Run("app-capped", "app", "webkit", cores=4, memory=True),
    Run("webkit", "site", "webkit"),
    Run("chromium", "site", "chromium"),
    Run("firefox", "site", "firefox"),
    Run("lag", "site", "webkit", lag=True),
)}

# ---- the page side: the init script and the done-states ------------------------------------------------------------

WATCH = ("status", "track-status", "track-art", "track-head", "char-preview-note", "char-content-note", "char-g4-note")
INIT = """(() => {
  const ev = globalThis.__perf = [], last = new Map(), watch = %s;
  const look = () => {
    const t = performance.now();
    for (const id of watch) {
      const e = document.getElementById(id);
      const v = e ? e.textContent.slice(0, 160) : null;
      if (e && last.get(id) !== v) { last.set(id, v); ev.push([t, id, v]); }
    }
    document.querySelectorAll("progress").forEach((p, i) => {
      const k = "progress:" + (p.id || i), v = p.closest("[hidden]") ? "hidden" : String(p.getAttribute("value"));
      if (last.get(k) !== v) { last.set(k, v); ev.push([t, k, v]); }
    });
  };
  new MutationObserver(look).observe(document, { subtree: true, childList: true, characterData: true,
                                                  attributes: true, attributeFilter: ["hidden", "value"] });
})();""" % json.dumps(list(WATCH))

ERROR = ("document.querySelector('#status')?.classList.contains('error') "
         "&& 'error: ' + document.querySelector('#status').textContent")
READY = "() => globalThis.azurkit?.ready"
USA = "() => azurkit.vanilla?.release === 'usa'"
BUILT = f"() => azurkit.build ? 'built' : {ERROR}"
SAVED = f"() => azurkit.saved ? 'saved' : {ERROR}"
PICTURES = ("(document.getElementById('char-preview-note').textContent.startsWith('From the') "
            "|| document.getElementById('char-preview-note').textContent.includes('no '))")
TRACKED = "() => !azurkit.tracker.state.running && !azurkit.tracker.state.queue.length && azurkit.tracker.state.view"
ART_DONE = ("() => { const a = azurkit.tracker.art.status; "   # the shipped maps' index read (web/art.mjs)
            "return (a.error && 'error: ' + a.error) || Boolean(a.index); }")
WORLD = ("() => !document.getElementById('track-maps').hidden && azurkit.tracker.map.level === null "
         "&& Boolean(azurkit.tracker.map.pictures?.[0]?.bitmap)")
LEVEL = ("() => !document.getElementById('track-maps').hidden && azurkit.tracker.map.level === 'w1' "
         "&& azurkit.tracker.map.pictures.length > 0 && azurkit.tracker.map.pictures.every((p) => p.bitmap)")
SPECIES = "() => azurkit.characters.state.view?.species.length === 178"
# The lag model: each File read worker.mjs makes, and that read made LAG_MS late (a FileReaderSync read by a busy wait
# before it, as WebKit's blocks the worker; an awaited one by a timer before it). lagged() refuses a worker with a read
# of a File this doesn't list (READS outside these and NOT_FILE), so a lane that adds one adds it here.
_WAIT = f"new Promise((late) => setTimeout(late, {LAG_MS})).then(() => "
LAG = (
    ("data = new Uint8Array(WORKERFS.reader.readAsArrayBuffer(file.slice(index * unit, (index + 1) * unit)));",
     f"{{ const late = performance.now() + {LAG_MS}; while (performance.now() < late); }} "
     "data = new Uint8Array(WORKERFS.reader.readAsArrayBuffer(file.slice(index * unit, (index + 1) * unit)));"),
    ("await ends.arrayBuffer()", f"await {_WAIT}ends.arrayBuffer())"),   # identify's sample of the File
    ("await file.slice(run.start, run.end).arrayBuffer()",   # prime's hashers
     f"await {_WAIT}file.slice(run.start, run.end).arrayBuffer())"),
)
READS = re.compile(r"readAsArrayBuffer\(|\.arrayBuffer\(\)")
NOT_FILE = ("await wheel.arrayBuffer()",)   # the wheel's fetch
COUNTED = re.compile(r"\d+ of \d+|\d+(?:\.\d+)? ?%")


def click(id_: str) -> str:
    return f"() => document.getElementById({json.dumps(id_)}).click()"


def typed(id_: str, text: str) -> str:
    return (f"() => {{ const b = document.getElementById({json.dumps(id_)}); b.value = {json.dumps(text)}; "
            "b.dispatchEvent(new Event('input')); }")


def model(name: str) -> str:
    return (f"() => document.querySelector('#char-species .model[data-model=\"{name}\"], "
            f"#char-community .model[data-model=\"{name}\"]').click()")


def chosen(name: str, pictures: bool = True) -> str:
    return (f"() => azurkit.characters.state.view?.chosen.name === '{name}'"
            + (f" && {PICTURES}" if pictures else ""))


def build_js() -> str:
    return "() => { azurkit.build = null; document.querySelector('#build').click(); }"


# The seed's ask: typing a seed asks nothing, ticking Randomize asks the engine (MS's "tick Randomize + seed").
SEED_ASK = ("() => { azurkit.rando.view = null; const b = document.getElementById('rando-seed'); b.value = 'azurkit'; "
            "b.dispatchEvent(new Event('input')); const on = document.getElementById('rando-on'); "
            "if (!on.checked) on.click(); }")
UNTICK = ("() => { azurkit.rando.view = null; const on = document.getElementById('rando-on'); "
          "if (on.checked) on.click(); }")


# ---- samples ------------------------------------------------------------------------------------------------------

def progress_of(events: list, t0: float, t1: float) -> tuple[int, bool]:
    """(the most values one shown ``<progress>`` took, whether the page showed
    progress) over ``[t0, t1]`` of the init script's events: a bar's value,
    or a watched line's "k of n" or "N %" text, changing at least once."""
    values: dict[str, set] = {}
    counted: dict[str, set] = {}
    for t, key, value in events:
        if not t0 - 1 <= t <= t1 + 1 or value is None:
            continue
        if key.startswith("progress:"):
            if value != "hidden":
                values.setdefault(key, set()).add(value)
        elif found := COUNTED.findall(value):
            counted.setdefault(key, set()).add(" ".join(found))
    bar = max((len(v) for v in values.values()), default=0)
    return bar, bar >= 2 or any(len(v) >= 2 for v in counted.values())


class Page:
    """A page with the init script: actions timed by its clock."""

    def __init__(self, page):
        self.page = page

    def js(self, fn: str, arg=None):
        return self.page.evaluate(fn, arg)

    def now(self) -> float:
        return self.page.evaluate("() => performance.now()")

    def wait(self, done: str, timeout: float = 900, arg=None) -> tuple[float, object]:
        """(the page's clock, the value) once ``done`` is truthy; polled every 50 ms, then 200 ms after 5 s."""
        probe = f"(a) => {{ const v = ({done})(a); return v ? [performance.now(), v] : null; }}"
        start = time.monotonic()
        while not (got := self.page.evaluate(probe, arg)):
            waited = time.monotonic() - start
            if waited > timeout:
                raise TimeoutError(f"timed out after {timeout:.0f} s: {done[:100]}")
            time.sleep(0.05 if waited < 5 else 0.2)
        return got[0], got[1]

    def events(self) -> list:
        return self.page.evaluate("() => (globalThis.__perf ?? []).splice(0)")


class Driver:
    """One run's samples: ``targets`` says how many each wanted op needs;
    a scenario's steps time an op only while it needs more."""

    def __init__(self, run: Run, targets: dict[str, int], scratch: Path, iso: Path, content: Path | None):
        self.run, self.targets, self.scratch, self.iso, self.content = run, targets, scratch, iso, content
        self.samples: dict[str, list[dict]] = {}
        self.log: list[str] = []
        self.ev: list = []

    def need(self, op: str) -> bool:
        got = self.samples.get(op, [])
        return op in self.targets and len(got) < self.targets[op] and not any(
            s["s"] > LONG or s.get("error") for s in got)

    def needed(self, ops) -> bool:
        return any(self.need(op) for op in ops)

    def record(self, op: str | None, seconds: float, events: list, t0: float, t1: float, error: str | None = None):
        if op is None or not self.need(op):
            return
        bar, shown = progress_of(events, t0, t1)
        sample = {"s": round(seconds, 3), "bar": bar, "progress": shown}
        if error:
            sample["error"] = error[:300]
        self.samples.setdefault(op, []).append(sample)
        self.log.append(f"{self.run.name} {op} {seconds:.2f} s{' bar ' + str(bar) if bar else ''}"
                        f"{' progress' if shown else ''}{' ' + error[:120] if error else ''}")
        print(self.log[-1], flush=True)

    def act(self, p: Page, op: str | None, action: str | Callable[[], None] | None, done: str,
            timeout: float = 900, arg=None) -> tuple[float, float]:
        """Do ``action`` (a page function, a Python callable, or nothing) and
        wait for ``done``; time it as ``op`` by the page's clock. A done-state
        that reads ``error: …`` (the page's error line) fails the sample."""
        if callable(action):
            t0 = p.now()
            action()
        elif action:
            t0 = p.js(f"(a) => {{ const t = performance.now(); ({action})(a); return t; }}", arg)
        else:
            t0 = p.now()
        return t0, self.until(p, op, t0, done, timeout)

    def until(self, p: Page, op: str | None, t0: float, done: str, timeout: float = 900) -> float:
        """Wait for ``done`` and time it as ``op`` from ``t0`` (the page's clock)."""
        try:
            t1, value = p.wait(done, timeout)
        except TimeoutError as exc:
            t1 = p.now()
            self.ev += p.events()
            self.record(op, (t1 - t0) / 1000, self.ev, t0, t1, str(exc))
            raise
        self.ev += p.events()
        error = value if isinstance(value, str) and value.startswith("error: ") else None
        self.record(op, (t1 - t0) / 1000, self.ev, t0, t1, error)
        if error:
            raise RuntimeError(f"{op}: {error[:200]}")
        return t1


# ---- the hosts ----------------------------------------------------------------------------------------------------

def free_port(start: int = PORTS) -> int:
    port = start
    while True:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
        port += 1


def kill_tree(pid: int) -> None:
    """SIGTERM a process and its descendants, walked from its exact pid."""
    kids = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True).stdout.split()
    for kid in kids:
        kill_tree(int(kid))
    with contextlib.suppress(ProcessLookupError):
        os.kill(pid, signal.SIGTERM)


class Memory:
    """The peak resident size of the trees under ``roots(rows)`` (``rows``:
    ps's ``(pid, ppid, command)``), sampled every 0.2 s."""

    def __init__(self, roots: Callable[[list[tuple[int, int, str]]], list[int]]):
        self.roots, self.peak, self._stop = roots, 0, threading.Event()
        self._thread = threading.Thread(target=self._sample, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join(5)

    @staticmethod
    def rows(rss: dict[int, int] | None = None) -> list[tuple[int, int, str]]:
        """ps's ``(pid, ppid, command)`` rows (each resident KiB into ``rss``)."""
        out = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,rss=,comm="], capture_output=True, text=True).stdout
        rows = []
        for row in out.splitlines():
            if len(f := row.split(None, 3)) == 4 and f[0].isdigit():
                rows.append((int(f[0]), int(f[1]), f[3]))
                if rss is not None:
                    rss[int(f[0])] = int(f[2])
        return rows

    def _sample(self):
        while not self._stop.wait(0.2):
            rss: dict[int, int] = {}
            rows = self.rows(rss)
            kids: dict[int, list[int]] = {}
            for pid, ppid, _ in rows:
                kids.setdefault(ppid, []).append(pid)
            seen, todo = set(), list(self.roots(rows))
            while todo:
                if (pid := todo.pop()) not in seen:
                    seen.add(pid)
                    todo += kids.get(pid, [])
            self.peak = max(self.peak, sum(rss.get(pid, 0) for pid in seen) * 1024)


def browser_pids(rows: list[tuple[int, int, str]], before: set[int]) -> list[int]:
    """The browsers Playwright's driver (a node child of this process)
    started, and WebKit's own processes (its pages, network and GPU: XPC
    services launchd starts, so outside the tree) that weren't running
    before this run (``before``): a WebKit another run starts meanwhile is
    counted too, never one of ours left out."""
    drivers = [pid for pid, ppid, comm in rows if ppid == os.getpid() and "node" in comm]
    return [pid for pid, ppid, comm in rows if ppid in drivers or pid not in before and ".xpc/" in comm
            and "/playwright/webkit" in comm]


class App:
    """``python -m azurkit serve`` from the scratch venv ``python`` is
    (:func:`venv`), in its own fresh HOME (its config and user cache, and its
    cwd), no image named (``AZURKIT_ISO`` dropped), the clone as its Content
    from; quit by closing its input."""

    def __init__(self, python: str, home: Path, run: Run, content: Path | None):
        self.python, self.home, self.run = python, home, run
        config = home / "Library" / "Application Support" / "AzurKit"
        config.mkdir(parents=True, exist_ok=True)
        if content is not None:
            (config / "app.json").write_text(json.dumps({"content_source": str(content)}), encoding="utf-8")
        self.env = {k: v for k, v in os.environ.items()
                    if k not in ("AZURKIT_ISO", "AZURKIT_ISO_EUROPE", "VIRTUAL_ENV", "PYTHONPATH", "AZURKIT_CORES")}
        self.env |= {"HOME": str(home), "AZURKIT_NO_WINDOW": "1"}
        if run.cores:
            self.env["AZURKIT_CORES"] = str(run.cores)
        self.proc = None

    def launch(self, d: Driver, ctx, op: str | None) -> Page:
        """Spawn the server and open its page: ``op`` timed from the spawn to the page's ready flag."""
        t = time.monotonic()
        err = self.home / "serve.err"
        with open(err, "a", encoding="utf-8") as errors:
            self.proc = subprocess.Popen([self.python, "-m", "azurkit", "serve"], cwd=self.home, env=self.env,
                                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors, text=True,
                                         start_new_session=True)
        url = self.proc.stdout.readline().strip()
        if not url.startswith("http://127.0.0.1:"):
            raise RuntimeError(f"azurkit serve gave no address: {err.read_text(encoding='utf-8')[-300:]!r}")
        p = Page(ctx.new_page())
        p.page.goto(url)
        t1, _ = p.wait(READY, 600)
        d.ev = p.events()   # a new page: its own clock
        d.record(op, time.monotonic() - t, d.ev, 0, t1)
        return p

    def quit(self, p: Page | None = None) -> None:
        if p is not None:
            p.page.close()
        if self.proc and self.proc.poll() is None:
            self.proc.stdin.close()
            try:
                self.proc.wait(60)
            except subprocess.TimeoutExpired:
                kill_tree(self.proc.pid)
                self.proc.wait(30)
        self.proc = None

    def pid(self) -> list[int]:
        return [self.proc.pid] if self.proc and self.proc.poll() is None else []


class _Quiet(http.server.SimpleHTTPRequestHandler):
    worker: str | None = None   # the lag model's worker.mjs, served in place of the file

    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.worker is not None and self.path.split("?")[0] == "/worker.mjs":
            body = self.worker.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/javascript")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):   # a page closed mid-reply
            super().do_GET()


@contextlib.contextmanager
def served(site: Path, lag: bool = False) -> Iterator[str]:
    """The site on 127.0.0.1 (the first free port from :data:`PORTS`); with
    ``lag`` its ``worker.mjs`` answers each File read :data:`LAG_MS` late
    (:func:`lagged`)."""
    worker = lagged((site / "worker.mjs").read_text(encoding="utf-8")) if lag else None
    handler = type("Handler", (_Quiet,), {"worker": worker})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", free_port()),
                                             functools.partial(handler, directory=str(site)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/"
    finally:
        server.shutdown()
        server.server_close()


def lagged(text: str) -> str:
    """``worker.mjs``'s ``text`` with each File read :data:`LAG` lists made
    :data:`LAG_MS` late: each must be there once, and no other read of a
    File (:data:`READS` but :data:`NOT_FILE`), else a SystemExit names it."""
    rest = text
    for read, late in LAG:
        if text.count(read) != 1:
            raise SystemExit(f"perf: the lag model's read is in worker.mjs {text.count(read)} times, not once: "
                             f"{read!r} (tests/_perf.py LAG)")
        text, rest = text.replace(read, late), rest.replace(read, "")
    for other in NOT_FILE:
        rest = rest.replace(other, "")
    if unknown := [line.strip() for line in rest.splitlines() if READS.search(line)]:
        raise SystemExit(f"perf: worker.mjs reads a File the lag model doesn't make late: {unknown[0]!r} "
                         "(tests/_perf.py LAG)")
    return text


# ---- the scenarios ------------------------------------------------------------------------------------------------
# Each takes the driver, a fresh state's maker and a fresh browser context; the order of each mirrors the measure
# seats' drivers (round 1's measure-app-start, -app-build, -app-characters, -build, -seed, -tracker, -characters).

def app_start(d: Driver, app: App, ctx) -> None:
    p = app.launch(d, ctx, "A01")
    parts = []
    for action, done in ((click("tab-about"), "() => !document.getElementById('about').hidden"),
                         (click("tab-patches"), "() => !document.getElementById('patches').hidden"),
                         ("""() => [...document.querySelectorAll('#packs .pack .toggle')].filter((b) => !b.hidden
                              && b.getAttribute('aria-expanded') === 'false')[0].click()""",
                          "() => document.querySelectorAll('#packs .toggle[aria-expanded=true]').length"),
                         ("() => { azurkit.link = null; document.getElementById('share').click(); }",
                          "() => azurkit.link && azurkit.link.length")):
        parts.append(d.act(p, None, action, done))
    if parts:   # A05: the slowest of them
        t0, t1 = max(parts, key=lambda span: span[1] - span[0])
        d.record("A05", (t1 - t0) / 1000, d.ev, t0, t1)
    d.act(p, "A08", click("tab-characters"), "() => azurkit.characters.state.view?.species.length")
    d.act(p, "A06", click("tab-randomizer"), "() => azurkit.rando.view")
    d.act(p, "A07", SEED_ASK, "() => azurkit.rando.view")
    d.act(p, None, UNTICK, "() => azurkit.rando.view")
    p.js(click("tab-patches"))
    d.act(p, "A03", typed("iso-path", str(d.iso)), USA)
    while d.need("A04"):   # the page asks an image once: forgetting that it asked makes it ask again
        p.js("() => { azurkit.vanilla = null; azurkit.asked = null; }")
        d.act(p, "A04", typed("iso-path", str(d.iso)), USA)
    d.act(p, "A09", click("tab-characters"), f"() => azurkit.characters.state.view?.species.length === 178 && {PICTURES}")
    d.act(p, "A10", model("keylord"), chosen("keylord"))
    d.act(p, "A11", click("char-g4-scale"), "() => !azurkit.characters.state.matching && "
                    "document.getElementById('char-scale').value !== '1' && document.getElementById('char-scale').value")
    app.quit(p)


def _out(d: Driver, name: str) -> Path:
    out = d.scratch / f"{name}.iso"
    out.unlink(missing_ok=True)
    return out


def _save(d: Driver, p: Page, op: str | None, name: str, dialog: bool = True) -> None:
    out = _out(d, name)
    p.js(typed("out-path", str(out)))
    if dialog:
        time.sleep(SAVE_DIALOG)
    try:
        d.act(p, op, "() => { azurkit.saved = null; document.querySelector('#save').click(); }", SAVED, 1800)
    finally:
        out.unlink(missing_ok=True)


def app_build(d: Driver, app: App, ctx) -> None:
    p = app.launch(d, ctx, None)
    d.act(p, None, typed("iso-path", str(d.iso)), USA)
    d.act(p, "A12", build_js(), BUILT)
    _save(d, p, "A13", "defaults")
    d.act(p, None, build_js(), BUILT)
    _save(d, p, "A14", "defaults", dialog=False)
    p.js(click("tab-characters"))
    p.wait(SPECIES)
    d.act(p, None, model("keylord"), chosen("keylord"))
    d.act(p, "A15", build_js(), BUILT, 1800)
    _save(d, p, "A17", "keylord")
    d.act(p, "A16", build_js(), BUILT, 1800)
    app.quit(p)


def _seeded(d: Driver, p: Page, randomize: bool = True) -> None:
    """The Randomizer tab open with seed ``azurkit``, Randomize ticked (its ask answered) or not."""
    p.js(click("tab-randomizer"))
    p.wait("() => azurkit.rando.view?.share")
    if randomize:
        d.act(p, None, SEED_ASK, "() => azurkit.rando.view && document.getElementById('rando-on').checked", 900)
    else:
        p.js(typed("rando-seed", "azurkit"))


def app_seed(d: Driver, app: App, ctx) -> None:
    p = app.launch(d, ctx, None)
    d.act(p, None, typed("iso-path", str(d.iso)), USA)
    _seeded(d, p)
    d.act(p, "A27", build_js(), BUILT, 1800)
    if d.need("A28"):   # a slow step another pass doesn't need is skipped
        _save(d, p, "A28", "seed")
    if d.need("A29"):
        d.act(p, None, """() => { azurkit.build = null; document.querySelector('#build').click();
                           setTimeout(() => document.querySelector('#cancel').click(), 3000); }""",
              "() => /Cancelled/.test(document.querySelector('#status').textContent)", 600)
        d.act(p, "A29", build_js(), BUILT, 1800)
    p.js(click("tab-characters"))
    p.wait(SPECIES)
    p.js(build_js())
    time.sleep(1.0)
    d.act(p, "A30", model("keylord"), chosen("keylord"), 1800)
    p.wait(BUILT, 1800)
    app.quit(p)


def app_track(d: Driver, app: App, ctx) -> None:
    p = app.launch(d, ctx, None)
    _seeded(d, p, randomize=False)
    p.js(click("rando-view-tracker"))
    d.act(p, "A23", click("track-seed"), "() => document.getElementById('track-head').textContent.trim()", 1800)
    p.js(click("rando-view-settings"))
    d.act(p, None, typed("iso-path", str(d.iso)), USA)
    d.act(p, None, "() => { azurkit.rando.view = null; const on = document.getElementById('rando-on'); "
                   "if (!on.checked) on.click(); }",
          "() => azurkit.rando.view && document.getElementById('rando-on').checked")
    d.act(p, "A26", build_js(), BUILT, 1800)
    if d.need("A24"):
        d.act(p, "A24", click("rando-view-tracker"), ART_DONE, 3600)
    app.quit(p)
    p = app.launch(d, ctx, "A02")
    if d.need("A25"):
        d.act(p, "A25", "() => { document.getElementById('tab-randomizer').click(); "
                        "document.getElementById('rando-view-tracker').click(); }",
              "() => document.getElementById('track-head').textContent.trim() && !azurkit.tracker.state.running", 1800)
    app.quit(p)


def app_booblord(d: Driver, app: App, ctx) -> None:
    p = app.launch(d, ctx, None)
    d.act(p, None, typed("iso-path", str(d.iso)), USA)
    p.js(click("tab-characters"))
    p.wait(SPECIES)   # the shipped view lists no community entry: booblord's Install comes with the engine's answer
    p.wait("""() => document.querySelector('#char-community .entry[data-entry="booblord"] button')""", 600)
    d.act(p, None, """() => document.querySelector('#char-community .entry[data-entry="booblord"] button').click()""",
          """() => document.querySelector('#char-community .entry[data-entry="booblord"] .model')""", 600)
    d.act(p, "A18", model("booblord"), chosen("booblord"), 3600)
    d.act(p, "A20", build_js(), BUILT, 3600)
    _save(d, p, "A22", "booblord")
    d.act(p, "A21", build_js(), BUILT, 3600)
    while d.need("A19"):   # again in one state: another model, then booblord
        d.act(p, None, model("garret4"), chosen("garret4"), 600)
        d.act(p, "A19", model("booblord"), chosen("booblord"), 3600)
    app.quit(p)


# D999: a shape no build has made (booblord with one slider moved) builds first with a bar (A31); at the next launch
# the same shape is the app's kept answer (A32, strict). Her own pictures are drawn first, untimed.
RESHAPE = """() => { const s = azurkit.characters.state.view.chosen.shapes[0].name, b = document.getElementById(
  `char-shape:${s}`); b.value = "1.25"; b.dispatchEvent(new Event("change")); }"""
RESHAPED = ("() => azurkit.characters.state.character.shapes && azurkit.characters.state.view?.asked "
            "=== JSON.stringify(azurkit.characters.state.character)")


def app_reshape(d: Driver, app: App, ctx) -> None:
    p = app.launch(d, ctx, None)
    d.act(p, None, typed("iso-path", str(d.iso)), USA)
    p.js(click("tab-characters"))
    p.wait("""() => document.querySelector('#char-community .entry[data-entry="booblord"] button')""", 600)
    d.act(p, None, """() => document.querySelector('#char-community .entry[data-entry="booblord"] button').click()""",
          """() => document.querySelector('#char-community .entry[data-entry="booblord"] .model')""", 600)
    d.act(p, None, model("booblord"), chosen("booblord"), 3600)
    d.act(p, None, RESHAPE, RESHAPED, 600)
    d.act(p, "A31", build_js(), BUILT, 3600)
    app.quit(p)
    p = app.launch(d, ctx, None)   # the same HOME: the remembered setup wears the reshape
    d.act(p, None, typed("iso-path", str(d.iso)), USA)
    p.js(click("tab-characters"))
    p.wait(f"() => azurkit.characters.state.character.species === 'booblord' && ({RESHAPED[6:]})", 600)
    d.act(p, "A32", build_js(), BUILT, 1800)
    app.quit(p)


def _site_page(d: Driver, ctx, url: str, op: str | None) -> Page:
    """A new page on ``url``, ``op`` timed by its own clock from its navigation to the engine's ready flag."""
    p = Page(ctx.new_page())
    p.page.goto(url)
    t1, _ = p.wait(READY, 600)
    d.ev = p.events()   # a new page: its own clock
    d.record(op, t1 / 1000, d.ev, 0, t1)
    return p


def _pick(d: Driver, p: Page, op: str | None, done: str = USA) -> None:
    d.act(p, op, lambda: p.page.set_input_files("#iso", str(d.iso)), done, 1800)


def _download(d: Driver, p: Page, op: str | None) -> None:
    t0 = p.now()
    with p.page.expect_download(timeout=1_800_000) as caught:
        p.js("() => document.querySelector('#save').click()")
    caught.value.path()
    t1 = p.now()
    d.ev += p.events()
    d.record(op, (t1 - t0) / 1000, d.ev, t0, t1)
    caught.value.delete()


def site_start(d: Driver, ctx, url: str) -> None:
    p = _site_page(d, ctx, url, "S01")
    d.act(p, "S16", click("tab-randomizer"), "() => azurkit.rando.view")
    d.act(p, "S17", SEED_ASK, "() => azurkit.rando.view")
    d.act(p, None, UNTICK, "() => azurkit.rando.view")
    p.js(click("tab-patches"))
    _pick(d, p, "S03")
    d.act(p, "S05", build_js(), BUILT, 1800)
    _download(d, p, "S06")
    p.wait(READY, 600)   # the site's engine is replaced after each build
    d.act(p, "S08", click("tab-characters"), SPECIES, 1800)
    if d.needed(("S10", "S11", "S14")):   # slow steps another pass doesn't need are skipped
        t0, _ = d.act(p, "S10", model("keylord"), chosen("keylord", pictures=False), 1800)
        d.until(p, "S11", t0, chosen("keylord"), 1800)
        if d.need("S14"):
            d.act(p, "S14", build_js(), BUILT, 1800)
            p.wait(READY, 600)
    p.page.close()
    while d.needed(("S02", "S04")):
        p = _site_page(d, ctx, url + "?again", "S02")
        _pick(d, p, "S04")
        p.page.close()


def site_characters(d: Driver, ctx, url: str) -> None:
    p = _site_page(d, ctx, url, None)
    d.act(p, "S07", click("tab-characters"), "() => { const t = document.getElementById('char-content-note')"
                    ".textContent; return t && !t.startsWith('Reading') && document.querySelectorAll("
                    "'#char-species .model').length; }", 600)
    if d.content is not None:
        d.act(p, None, "() => { const b = document.getElementById('char-source'); b.value = './content-source/'; "
                       "b.dispatchEvent(new Event('change')); }",
              "() => document.querySelector('#char-community .entry[data-entry=beamlord]')", 600)
    _pick(d, p, "S09", "() => azurkit.characters.state.view?.species.length === 178 && "
                       "document.querySelectorAll('#char-species .model').length === 178")
    if d.content is not None:
        d.act(p, "S13", """() => { azurkit.characters.state.view.perfOld = true;
                            document.querySelector('#char-community .entry[data-entry="beamlord"] button').click(); }""",
              """() => document.querySelector('#char-community .entry[data-entry="beamlord"] .model')
                   && !azurkit.characters.state.installing && azurkit.characters.state.view
                   && !azurkit.characters.state.view.perfOld""", 1800)
        d.act(p, "S12", model("beamlord"), chosen("beamlord"), 1800)
    p.page.close()


def site_track(d: Driver, ctx, url: str) -> None:
    p = _site_page(d, ctx, url, None)
    _pick(d, p, None)
    _seeded(d, p, randomize=False)
    p.js(click("rando-view-tracker"))
    t0, t1 = d.act(p, "S18", click("track-seed"), TRACKED, 1800)
    if d.needed(("S19", "S20")):
        d.until(p, "S20", t1, ART_DONE, 3600)
        d.until(p, "S19", t0, WORLD, 600)
    else:
        p.wait(ART_DONE, 3600)
        p.wait(WORLD, 600)
    while d.need("S22"):
        d.act(p, "S22", "() => azurkit.tracker.map.show('w1', true)", LEVEL, 600)
        d.act(p, None, click("map-back"), WORLD, 600)
    p.js(click("rando-view-settings"))
    d.act(p, None, "() => { azurkit.rando.view = null; const on = document.getElementById('rando-on'); "
                   "if (!on.checked) on.click(); }",
          "() => azurkit.rando.view && document.getElementById('rando-on').checked")
    d.act(p, "S23", build_js(), BUILT, 1800)
    while d.need("S25"):
        d.act(p, "S25", click("spoiler-view"),
              "() => !document.getElementById('spoiler').hidden && document.getElementById('spoiler').textContent.length")
        p.js(click("spoiler-view"))
    p.page.close()
    p = _site_page(d, ctx, url + "?reopen", None)
    d.act(p, "S21", "() => { document.getElementById('tab-randomizer').click(); "
                    "document.getElementById('rando-view-tracker').click(); }", TRACKED, 1800)
    p.page.close()


def site_seed(d: Driver, ctx, url: str) -> None:
    p = _site_page(d, ctx, url, None)
    _pick(d, p, None)
    _seeded(d, p)
    d.act(p, "S24", build_js(), BUILT, 1800)
    p.page.close()


SCENARIOS = {   # name: (host, its ops, the driver)
    "app-start": ("app", ("A01", "A03", "A04", "A05", "A06", "A07", "A08", "A09", "A10", "A11"), app_start),
    "app-build": ("app", ("A12", "A13", "A14", "A15", "A16", "A17"), app_build),
    "app-seed": ("app", ("A27", "A28", "A29", "A30"), app_seed),
    "app-track": ("app", ("A02", "A23", "A24", "A25", "A26"), app_track),
    "app-booblord": ("app", ("A18", "A19", "A20", "A21", "A22"), app_booblord),
    "app-reshape": ("app", ("A31", "A32"), app_reshape),
    "site-start": ("site", ("S01", "S02", "S03", "S04", "S05", "S06", "S08", "S10", "S11", "S14", "S16", "S17"),
                   site_start),
    "site-characters": ("site", ("S07", "S09", "S12", "S13"), site_characters),
    "site-track": ("site", ("S18", "S19", "S20", "S21", "S22", "S23", "S25"), site_track),
    "site-seed": ("site", ("S24",), site_seed),
}
assert sorted(op for _, ops, _ in SCENARIOS.values() for op in ops) == sorted(
    op.id for op in OPS.values() if not op.untimed)


def venv(wt: Path, folder: Path, wheel: Path | None = None) -> str:
    """The app's Python as a player installs it: a venv in the new folder
    ``folder`` holding the worktree's wheel (``wheel``, else built now:
    ``web_tools.wheel``) and its declared dependencies, so the app reads the
    randomizer database the wheel ships (its RECORD lists it; a checkout
    checks it again, round 1's A06 7.8 s against the frozen app's 3.5 s), and
    a copy of the worktree's ``web/`` where the installed app looks for its
    page (``azurkit.app.PAGE``: beside ``site-packages``). Its python."""
    from scripts import web_tools
    wheel = wheel or web_tools.wheel(folder / "dist", wt)
    env = {k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "PYTHONPATH")}
    run = functools.partial(subprocess.run, env=env, capture_output=True, text=True, check=True, timeout=600)
    run(["uv", "venv", "--quiet", "--python", "3.14", str(folder / "venv")])
    python = str(folder / "venv" / ("Scripts" if os.name == "nt" else "bin") / "python")
    run(["uv", "pip", "install", "--offline", "--quiet", "--python", python, str(wheel)])
    purelib = run([python, "-I", "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"]).stdout.strip()
    shutil.copytree(wt / "web", Path(purelib).parent / "web")
    return python


def drive(wt: Path, run: Run, targets: dict[str, int], iso: Path, content: Path | None, site: Path | None,
          python: str | None = None, passes: int = 7) -> dict:
    """``run``'s samples for ``targets`` (``{op: samples wanted}``): ``{"samples":
    {op: [{"s", "bar", "progress"[, "error"]}]}, "memory_peak": bytes or None,
    "memory_shared" (another Playwright ran meanwhile), "wall_s", "log"}``. Each scenario holding a wanted op runs, in a fresh
    state each pass, until its ops have their samples (at most ``passes``). An app run serves the app from ``python``
    (:func:`venv`'s; else one made for this run)."""
    from playwright.sync_api import sync_playwright

    from scripts import web_tools
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(web_tools.browsers_dir(ROOT))
    t = time.monotonic()
    scratch = Path(tempfile.mkdtemp(prefix=f"azurkit-perf-{run.name}.", dir="/tmp"))
    d = Driver(run, targets, scratch, iso, content)
    python = python or (venv(wt, scratch / "app") if run.host == "app" else None)
    current: list[App] = []
    before, shared = {pid for pid, _, comm in Memory.rows() if ".xpc/" in comm}, []

    def site_roots(rows):   # another Playwright driver alive: a new WebKit process may be its (said, not dropped)
        if any(comm.endswith("playwright/driver/node") and ppid != os.getpid() for _, ppid, comm in rows):
            shared.append(True)
        return browser_pids(rows, before)
    roots = (lambda rows: [pid for app in current for pid in app.pid()]) if run.host == "app" else site_roots
    try:
        with sync_playwright() as pw, (Memory(roots) if run.memory else contextlib.nullcontext()) as memory, \
                (served(site, run.lag) if run.host == "site" else contextlib.nullcontext()) as url:
            browser = getattr(pw, run.browser).launch(headless=True, downloads_path=str(scratch))
            for name, (host, ops, scenario) in SCENARIOS.items():
                if host != run.host:
                    continue
                for n in range(passes):
                    if not d.needed(ops):
                        break
                    if content is None and (missing := [op for op in ops if OPS[op].content and d.need(op)]):
                        for op in missing:
                            d.record(op, 0.0, [], 0, 0, "needs a clone of Azurik-Custom-Content (perf.py --content)")
                    ctx = browser.new_context(accept_downloads=True)
                    ctx.add_init_script(INIT)
                    d.ev = []
                    try:
                        if run.host == "app":
                            current[:] = [App(python, scratch / f"home-{name}-{n}", run, content)]
                            scenario(d, current[0], ctx)
                        else:
                            scenario(d, ctx, url)
                    except Exception as exc:   # the op being timed has its error; the rest of this pass is lost
                        d.log.append(f"{run.name} {name} pass {n + 1}: {type(exc).__name__}: {str(exc)[:300]}")
                        print(d.log[-1], flush=True)
                        for op in ops:
                            if d.need(op):
                                d.record(op, 0.0, [], 0, 0, f"{name} stopped: {type(exc).__name__}: {str(exc)[:200]}")
                    finally:
                        for app in current:
                            app.quit()
                        current.clear()
                        ctx.close()
            browser.close()
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return {"samples": d.samples, "memory_peak": memory.peak if run.memory else None,
            "memory_shared": bool(shared), "wall_s": round(time.monotonic() - t, 1), "log": d.log}
