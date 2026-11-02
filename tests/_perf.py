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
"N %" text, changing at least once). A download's sample also keeps its
page part, the click to the browser's download starting (Playwright's
download event): the rest is the browser's own write, which its download
indicator shows (an op's ``browser_bar``).

A run is one of :data:`RUNS`: the app (``python -m azurkit serve`` from the
worktree's wheel in a scratch venv, :func:`venv`, so it reads the randomizer
database the wheel ships as a player's install does; with a fresh HOME, its
page in WebKit), the app capped
(``AZURKIT_CORES=4``), the site (``scripts/web_tools.py``'s, served on
127.0.0.1 from port 8900 up) in WebKit, Chromium or Firefox, and the site with each
File read 200 ms late (Safari's read model: one checked substitution in the
served ``worker.mjs``, so no source carries a test hook). First-time ops
take a fresh state each sample (a new HOME, or a browser context: the
site's a persistent one on a new folder, with the storage a player's
browser has), so a scenario runs again until each of its ops has its
samples.

The clock is the click's (D1006): a Track or Build that follows a change
the player makes (a typed seed, the Randomize tick, an image pick, a
model's pick, a slider) is clicked :data:`HEAD_START` after it (D1014),
and the init script's freeze probe, a :data:`TICK_MS` timer, fails a
sample whose page froze over :data:`FREEZE_MS` in a gap between actions
(a head start, a dialog's wait, the warm-up's); late ticks inside an
action's own wait are its work, logged (:class:`Driver`). Not collected
(no ``test_`` prefix). No game bytes are printed or kept: times, texts of
the page's status lines, sizes."""

from __future__ import annotations

import contextlib
import dataclasses
import functools
import hashlib
import http.server
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

from tests import _page

ROOT = Path(__file__).resolve().parent.parent
GROUPS = ("start", "image", "build", "characters", "randomizer", "tracker")
LONG = 30.0          # an op with a sample over this runs once (its median is that sample)
STARVED = 1.3        # a sample past 1 s whose wall is over this x its tree's CPU seconds waited for a core
SAVE_DIALOG = 3.0    # a player's Save comes this long after the build (the save dialog)
DOWNLOAD_BAR = "its download indicator (Safari's toolbar button, Chrome's download bubble, Firefox's downloads arrow)"
HEAD_START = 3.0     # D1014: a Track or Build after the player's last change comes this long after it
TICK_MS = 50         # the freeze probe's timer (timers fire in Chromium's headless shell, rAF doesn't)
FREEZE_MS = 250      # D1006: a page late this long in a gap between actions froze (the sample fails)
LAG_MS = 200         # Safari's read model: each File read this late (Step 4.1g2 measured about 200 ms)
PORTS = 8900         # the site's server takes the first free port from here


@dataclasses.dataclass(frozen=True)
class Op:
    id: str
    title: str
    group: str            # one of GROUPS
    first: bool = True    # each sample in a fresh state (a new HOME or browser context); else repeated in one
    bar: bool = False     # D982: may pass 3 s with a moving bar (an image's first identity check, the first
    #                       engine load; D999 a new shape's first build; D1008 the randomizer's logic's first read)
    content: bool = False  # reads a clone of Azurik-Custom-Content
    browser_bar: str = ""  # D980: the browser's own bar for its write of a file the page handed it (a download only)
    untimed: str = ""     # why the gate can't time it (it is listed as such)
    head_start: bool = False   # D1014: a Track or Build clicked HEAD_START after the scenario's last change

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
    Op("A12", "Build, defaults", "build", head_start=True),
    Op("A13", "Save, defaults, after the save dialog", "build"),
    Op("A14", "Save, defaults, clicked at once", "build"),
    Op("A15", "Build keylord, first", "build", head_start=True),
    Op("A16", "Build keylord again", "build", first=False),
    Op("A17", "Save keylord, after the save dialog", "build"),
    Op("A18", "a variant's pictures (booblord), first", "characters", content=True),
    Op("A19", "a variant's pictures again", "characters", first=False, content=True),
    Op("A20", "Build booblord, first", "build", content=True, head_start=True),
    Op("A21", "Build booblord again", "build", first=False, content=True),
    Op("A22", "Save booblord, after the save dialog", "build", content=True),
    Op("A23", "Track this seed (plan and tracker)", "tracker", head_start=True),
    Op("A24", "the Tracker's maps, first view", "tracker"),
    Op("A25", "the Tracker at a second launch", "tracker"),
    Op("A26", "Build a seed after Track", "randomizer", head_start=True),
    Op("A27", "Build a seed, no Track first", "randomizer", head_start=True),
    Op("A28", "Save the seed, after the save dialog", "randomizer"),
    Op("A29", "Cancel a build, then Build", "randomizer"),
    Op("A30", "a small ask while a build runs (a model's pictures)", "randomizer"),
    Op("A31", "Build booblord reshaped (one slider moved), first", "build", bar=True, content=True,   # D999
       head_start=True),
    Op("A32", "the same reshape at the next launch", "build", content=True),
    Op("A59", "a slider moved: the reshape's nearest shape, marked Preview (D1011)", "characters", first=False,
       content=True),
    Op("A60", "the reshape's exact pictures, first", "characters", bar=True, content=True),   # D999's kind, by D1011
    Op("A61", "the same reshape's exact pictures again", "characters", first=False, content=True),
    Op("A33", "the Patches tab's community group, first open -> its list", "build"),   # Step 4.3k: community packs
    Op("A34", "Install a community pack -> its row tickable", "build"),
    Op("A35", "tick it -> its rows set and locked", "build"),
    Op("A36", "Build with it", "build", head_start=True),
    Op("A77", "Track, Seed difficulty Standard at Standard movement and skips", "tracker", head_start=True),
    Op("A78", "Build, Seed difficulty Standard at Hard movement and skips, no Track first", "randomizer", head_start=True),
    Op("A79", "Track, Seed difficulty Hard at Hard movement and skips", "tracker", head_start=True),
    Op("A80", "Build, Seed difficulty Hard at Hard movement and skips, no Track first", "randomizer", head_start=True),
    Op("A70", "Track, Seed difficulty Hard at Hard movement, Standard skips", "tracker", head_start=True),
    Op("A71", "Track, Seed difficulty Hard at Hard movement and skips, the fragments kept", "tracker", head_start=True),
    Op("A72", "Track, Seed difficulty Frame-perfect at Frame-perfect movement and skips", "tracker", head_start=True),
    Op("A73", "Build, Seed difficulty Frame-perfect at Frame-perfect movement and skips, no Track first", "randomizer",
       head_start=True),
    Op("A74", "Track, Seed difficulty Hard at Hard movement with a movement slider, no skip (jump 1.3: "
              "Frame-perfect's seed)", "tracker", head_start=True),
    Op("A75", "the spoiler's View clicked as Build ends, Seed difficulty Hard at Hard movement and skips (its openers)",
       "randomizer"),
    Op("A76", "the tracker's Spoiler ticked as Track ends, Seed difficulty Hard at Hard movement and skips (its openers)",
       "tracker"),
    Op("A37", "w1 zoomed past its map's pixels: its detail picture drawn, first", "tracker"),
    Op("A38", "w1 zoomed again after Fit (the detail held)", "tracker", first=False),
    Op("A39", "Data tab, first open (the index and the Player view)", "build"),   # Step 4.7a: the Data tab
    Op("A40", "a critter picked, its view", "build", first=False),
    Op("A41", "the picker's search, a few letters", "build", first=False),
    Op("A42", "All tables: critters_damage's grid", "build", first=False),
    Op("A43", "an edit committed (the engine's check, the view again)", "build", first=False),
    Op("A44", "Undo (the view again)", "build", first=False),
    Op("A45", "Build, defaults and 100 data edits", "build", head_start=True),
    Op("A46", "Load a mods file of 1,000 data edits, its view", "build"),
    Op("A47", "Tools tab, the image's info (the kept check)", "image"),   # Step 4.7c: the Tools tab
    Op("A48", "Verify every file, first", "image", bar=True),
    Op("A49", "Verify every file again", "image", first=False),
    Op("A50", "the image's file list", "image"),
    Op("A51", "Extract the largest file", "image"),
    Op("A52", "Open a build… (its recipe)", "build"),
    Op("A53", "Save a mods file, then Load it (the slower)", "build"),
    Op("A54", "a plan file's spoiler, ready to View (the logic's first read: D1008)", "build", bar=True),
    Op("A55", "the last build's report, View", "build", first=False),
    Op("A56", "Track a median seed (plan and tracker)", "tracker", head_start=True),   # AM-HUB-A: the app's work ahead
    Op("A57", "Build a median seed, no Track first", "randomizer", head_start=True),
    Op("A58", "Build a median seed, another seed's work ahead going stale 1 s into the head start", "randomizer",
       head_start=True),
    Op("A62", "Replace files: a 148 MB file picked, its sha256", "build"),   # Step 4.7d
    Op("A63", "Build with one 148 MB file replaced", "build", head_start=True),
    Op("A64", "Saves: a slot's folder opened", "build"),   # Step 4.7e
    Op("A65", "Saves: the slots of an xemu HDD image", "build"),
    Op("A66", "Saves: a line edited, then the slot saved", "build"),
    Op("S01", "page start, first visit (the engine load)", "start", bar=True),
    Op("S02", "page start, a return visit", "start", first=False),
    Op("S03", "choose the image, first time", "image", bar=True),
    Op("S04", "choose the same image after a reload", "image", first=False),
    Op("S05", "Build, defaults", "build", head_start=True),
    Op("S06", "Save (the browser's download)", "build", browser_bar=DOWNLOAD_BAR),
    Op("S07", "Characters tab, no image", "characters"),
    Op("S08", "Characters tab with the image", "characters"),
    Op("S09", "pick -> the weapons answer (the Characters tab open)", "characters"),
    Op("S10", "choose keylord (its info)", "characters"),
    Op("S11", "keylord's pictures", "characters"),
    Op("S12", "a reshaped variant's pictures (beamlord)", "characters", content=True),
    Op("S13", "Install beamlord, the list again", "characters", content=True),
    Op("S51", "a slider moved: the reshape's nearest shape, marked Preview (D1011)", "characters", first=False,
       content=True),
    Op("S52", "the reshape's exact pictures, first", "characters", bar=True, content=True),   # D999's kind, by D1011
    Op("S53", "the same reshape's exact pictures again", "characters", first=False, content=True),
    Op("S14", "Build keylord", "build", head_start=True),
    Op("S15", "booblord on the site", "build", head_start=True,
       untimed="3.7 s under the lag model (X6, 4.3r4f; WebKit 2.2, Chromium 1.9): timed once the reads ahead come (4.3r4k)"),
    Op("S16", "Randomizer tab, first ask", "randomizer"),
    Op("S17", "seed typed, its ask", "randomizer"),
    Op("S18", "Track this seed", "tracker", head_start=True),
    Op("S19", "the Tracker view's world map, first open", "tracker"),   # the view's click: no Track work (C10)
    Op("S20", "the maps' first draw", "tracker"),
    Op("S21", "the tracker, a reopen", "tracker"),
    Op("S22", "a level's map", "tracker", first=False),
    Op("S23", "Build a seed after Track", "randomizer", head_start=True),
    Op("S24", "Build a seed, no Track first", "randomizer", head_start=True),
    Op("S25", "the spoiler's View", "randomizer", first=False),
    Op("S26", "the Patches tab's community group, first open -> its list", "build"),   # Step 4.3k: community packs
    Op("S27", "Install a community pack -> its row tickable", "build"),
    Op("S28", "tick it -> its rows set and locked", "build"),
    Op("S29", "Build with it", "build", head_start=True),
    Op("S30", "w1 zoomed past its map's pixels: its detail picture drawn, first", "tracker"),
    Op("S31", "w1 zoomed again after Fit (the detail held)", "tracker", first=False),
    Op("S32", "Data tab, first open (the index and the Player view)", "build"),   # Step 4.7a: the Data tab
    Op("S33", "a critter picked, its view", "build", first=False),
    Op("S34", "the picker's search, a few letters", "build", first=False),
    Op("S35", "All tables: critters_damage's grid", "build", first=False),
    Op("S36", "an edit committed (the engine's check, the view again)", "build", first=False),
    Op("S37", "Undo (the view again)", "build", first=False),
    Op("S38", "Build, defaults and 100 data edits", "build", head_start=True),
    Op("S39", "Load a mods file of 1,000 data edits, its view", "build"),
    Op("S40", "Tools tab, the image's info (the kept check)", "image"),   # Step 4.7c: the Tools tab
    Op("S41", "Verify every file, first", "image", bar=True),
    Op("S42", "Verify every file again", "image", first=False),
    Op("S43", "the image's file list", "image"),
    Op("S44", "Extract the largest file (the browser's download)", "image"),
    Op("S45", "Open a build… (its recipe)", "build"),
    Op("S46", "Save a mods file, then Load it (the slower)", "build"),
    Op("S47", "a plan file's spoiler, ready to View (the logic's first read: D1008)", "build", bar=True),
    Op("S48", "the last build's report, View", "build", first=False),
    Op("S49", "Save keylord's build (the browser's download)", "build", browser_bar=DOWNLOAD_BAR),   # X5
    Op("S50", "Save a seed's build (the browser's download)", "randomizer", browser_bar=DOWNLOAD_BAR),
    Op("S54", "Replace files: a 148 MB file picked, its sha256", "build"),   # Step 4.7d
    Op("S55", "Build with one 148 MB file replaced", "build", head_start=True),
    Op("S56", "Saves: a slot's folder opened", "build"),   # Step 4.7e
    Op("S57", "Saves: the slots of an xemu HDD image", "build"),
    Op("S58", "Saves: a line edited, then the slot saved", "build"),
    Op("R14", "the engine ready again after Build keylord", "build"),   # the next op's wait: the same or a new worker
    Op("R24", "the engine ready again after a seed's build", "randomizer"),
)}


@dataclasses.dataclass(frozen=True)
class Run:
    name: str
    host: str              # app | site
    browser: str           # the page's engine
    cores: int | None = None   # AZURKIT_CORES for the app (the capped profile)
    ram: int | None = None     # AZURKIT_RAM for the app (the capped profile's 8 GiB)
    lag: bool = False      # the site's File reads LAG_MS late
    memory: bool = False   # sample our processes' peak resident size


RUNS = {run.name: run for run in (
    Run("app", "app", "webkit"),
    Run("app-capped", "app", "webkit", cores=4, ram=8 << 30, memory=True),
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
  const late = globalThis.__late = [];   // the freeze probe (D1006): [due, ms] of each tick a tick or more late
  let tick = performance.now();
  setInterval(() => { const t = performance.now(); if (t - tick >= 2 * %d) late.push([tick + %d, t - tick - %d]);
                      tick = t; }, %d);
})();""" % (json.dumps(list(WATCH)), TICK_MS, TICK_MS, TICK_MS, TICK_MS)

ERROR = ("document.querySelector('#status')?.classList.contains('error') "
         "&& 'error: ' + document.querySelector('#status').textContent")
READY = "() => globalThis.azurkit?.ready"
# RS4's steady memory (D17: logged beside the resident peak, which stays the gate's line): the heap the site's engine
# reported with its build and the bytes of the build's pieces, which the browser holds in Blobs.
STEADY = """() => { const a = globalThis.azurkit;
  return a?.heap == null ? null : (a.build?.segments ?? []).reduce((n, s) => n + (s.kind === "bytes" ? s.size : 0), a.heap); }"""
NATIVE = "() => globalThis.azurkit?.packs?.native ?? null"   # sdk.catalog's: the compiled kernels the engine runs
# And as a page leaves, with the calls each path answered by then: the app's server holds its engine process's, the
# site's page its workers'.
CALLS = """() => azurkit.app ? fetch("host.json").then((r) => r.json()).then((host) => host.catalog.native)
  : { ...azurkit.packs?.native, calls: azurkit.calls ?? { kernel: 0, twin: 0 } }"""
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
# w1 at the top zoom (Step 4.3l): drawn from its main floor's detail picture (shown and zoomed at once, so the
# picture is read whatever the fit fetched before)
TOP = "() => { const m = azurkit.tracker.map; m.view(m.top()); }"
SHOWN_TOP = "() => { const m = azurkit.tracker.map; m.show('w1', true); m.view(m.top()); }"
DETAILED = ("() => { const m = azurkit.tracker.map, f = m.drawnFor; "
            "return f?.level === 'w1' && f.floor === m.entry('w1').main && f.detail; }")
# The lag model: each File read worker.mjs (and hasher.mjs, for it and for the page's Save) makes, and that read made
# LAG_MS late (a FileReaderSync read by a busy wait before it, as WebKit's blocks the worker; an awaited one by a timer
# before it). lagged() refuses a file with a read of a File this doesn't list (READS outside these and NOT_FILE), so a
# lane that adds one adds it here.
_WAIT = f"new Promise((late) => setTimeout(late, {LAG_MS})).then(() => "
LAG = (
    ("data = new Uint8Array(WORKERFS.reader.readAsArrayBuffer(file.slice(index * unit, (index + 1) * unit)));",
     f"{{ const late = performance.now() + {LAG_MS}; while (performance.now() < late); }} "
     "data = new Uint8Array(WORKERFS.reader.readAsArrayBuffer(file.slice(index * unit, (index + 1) * unit)));"),
    ("await ends.arrayBuffer()", f"await {_WAIT}ends.arrayBuffer())"),   # identify's sample of the File
    ("await picked.arrayBuffer()", f"await {_WAIT}picked.arrayBuffer())"),   # Replace files' picked file
    ("await file.slice(index * PAGE, (index + 1) * PAGE).arrayBuffer()",   # the folders' tables read ahead (R2.5)
     f"await {_WAIT}file.slice(index * PAGE, (index + 1) * PAGE).arrayBuffer())"),
    ("await file.slice(i * PAGE, (i + 1) * PAGE).arrayBuffer()",   # a seed's sections read ahead (AM-HUB-E)
     f"await {_WAIT}file.slice(i * PAGE, (i + 1) * PAGE).arrayBuffer())"),
)
HASHER_LAG = (("await source.slice(run.start, run.end).arrayBuffer()",   # the image's check, a seed's levels, a Save's
               f"await {_WAIT}source.slice(run.start, run.end).arrayBuffer())"),)
READS = re.compile(r"readAsArrayBuffer\(|\.arrayBuffer\(\)")
NOT_FILE = ("await wheel.arrayBuffer()", "await module.arrayBuffer()")   # the wheel's fetch, md5.wasm's
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
    """A page with the init script: actions timed by its clock, and the
    freeze probe's late ticks (``[due, ms]`` by its clock, :attr:`late`)
    gathered at each read of its events."""

    def __init__(self, page):
        self.page = page
        self.late: list = []

    def js(self, fn: str, arg=None):
        return self.page.evaluate(fn, arg)

    def now(self) -> float:
        return self.page.evaluate("() => performance.now()")

    def do(self, action: str, arg=None) -> float:
        """Do the page function ``action``: the page's clock as it starts."""
        return self.page.evaluate(f"(a) => {{ const t = performance.now(); ({action})(a); return t; }}", arg)

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

    def poll(self, dones: list[str]) -> tuple[float, list]:
        """(the page's clock, each of ``dones``' values: an error text, else true or false) in one evaluate."""
        each = ", ".join(f"b(({done})())" for done in dones)
        return self.page.evaluate(f"() => {{ const b = (v) => typeof v === 'string' ? v : Boolean(v); "
                                  f"return [performance.now(), [{each}]]; }}")

    def settled(self) -> float:
        """The page's clock once the timers already due have run (a tick the page owes is in the next read)."""
        return self.page.evaluate("() => new Promise((done) => setTimeout(() => done(performance.now()), 0))")

    def events(self) -> list:
        events, late = self.page.evaluate("() => [(globalThis.__perf ?? []).splice(0), "
                                          "(globalThis.__late ?? []).splice(0)]")
        self.late += late
        return events

    def worst(self, t0: float, t1: float) -> float:
        """The freeze probe's worst lateness (ms) of a tick due in ``[t0,
        t1]``: a page already busy before ``t0`` is the work before it."""
        return max((ms for due, ms in self.late if t0 <= due <= t1), default=0.0)


WARM = "() => !globalThis.azurkit?.warm || azurkit.warm.done"   # D1008's warm-up over (none yet: at once)


def starved(seconds: float, cpu: float) -> bool:
    """Whether a sample past 1 s (D980's line) waited for a core: its wall
    passes :data:`STARVED` x the CPU seconds its tree used."""
    return seconds > 1.0 and seconds > STARVED * cpu


class Driver:
    """One run's samples: ``targets`` says how many each wanted op needs;
    a scenario's steps time an op only while it needs more.

    The click's clock (D1006, D1014): a scenario marks each change the
    player makes (``change=True``: a typed seed, the Randomize tick, an image
    pick, a model's pick, a slider), and an op with ``head_start`` (a Track
    or Build that follows one) is clicked :data:`HEAD_START` after it, the
    clock still starting at the click. A gap between actions (:meth:`idle`:
    a head start, a dialog's wait, the warm-up's) in which a tick of the
    freeze probe was due and came :data:`FREEZE_MS` late fails the next
    sample the pass records (a head start's: its op's, timed from the
    change); one no sample takes stops the pass (:meth:`over`). Lateness in
    an action's own wait is its work: its sample logs it (``late_ms``), as
    each logs its gaps' worst (``gap_ms``).

    The click's CPU (:attr:`memory`, a run's :class:`Memory`): an op timed
    from a click keeps the CPU seconds its tree used (``cpu``). A
    :func:`starved` sample (a busy machine, not the op's work) is taken once
    more; the next one takes its place (``retook``: its seconds), and, starved
    too, is recorded with its tag (``starved``), as one past :data:`LONG` is at
    once (it runs once)."""

    sleep = staticmethod(time.sleep)   # a stub clock's in the tests

    def __init__(self, run: Run, targets: dict[str, int], scratch: Path, iso: Path, content: Path | None):
        self.run, self.targets, self.scratch, self.iso, self.content = run, targets, scratch, iso, content
        self.samples: dict[str, list[dict]] = {}
        self.log: list[str] = []
        self.native: list[dict | None] = []   # each engine report its pages gave (:meth:`engine`)
        self.ev: list = []
        self.p: Page | None = None           # the page the pass drives
        self.changed: float | None = None    # the page's time of the pass's last change
        self.gap: tuple[float, str, float | None] | None = None   # the worst gap since the last sample: its ms,
        #                                                           where, and the change a head start counted from
        self.memory: Memory | None = None    # the run's tree's CPU seconds (none: its samples have no ``cpu``)
        self.clicked = 0.0                   # those seconds at the last click
        self.retaking: dict[str, dict] = {}  # each op's starved sample, while it is taken once more

    def need(self, op: str) -> bool:
        got = self.samples.get(op, [])
        return op in self.targets and len(got) < self.targets[op] and not any(
            s["s"] > LONG or s.get("error") for s in got)

    def needed(self, ops) -> bool:
        return any(self.need(op) for op in ops)

    def engine(self, p: Page) -> None:
        """The compiled kernels the page's engine runs (``sdk.catalog``'s
        ``native``), kept for the run's record (:attr:`native`): one running
        without its library stops the pass, its ops failing, so no time its
        Python twins take is ever a sample or a ceiling."""
        report = p.js(NATIVE)
        if report not in self.native:
            self.native.append(report)
        if not (report or {}).get("loaded"):
            raise RuntimeError(f"the engine runs without its native library ({(report or {}).get('why')})")

    def leave(self, p: Page) -> None:
        """Close ``p``, its engine's report (:data:`CALLS`) kept first: a twin
        that answered beside a loaded library shows there, and
        ``perf.native_failures`` fails the run for it."""
        report = p.js(CALLS)
        if report not in self.native:
            self.native.append(report)
        p.page.close()

    def fresh(self, p: Page) -> None:
        """A new page (its own clock): the events it has logged, no change pending."""
        self.p, self.changed = p, None
        self.ev = p.events()

    def record(self, op: str | None, seconds: float, events: list, t0: float, t1: float, error: str | None = None,
               page: float | None = None, cpu: float | None = None, steady: int | None = None):
        if op is None or not self.need(op):
            if self.gap and self.gap[2] is not None:   # a head start whose op takes no sample: a gap as any other
                self.gap = (*self.gap[:2], None)
            return
        gap, self.gap = self.gap, None
        if gap and gap[0] > FREEZE_MS:
            error = f"the page froze {gap[0]:.0f} ms in {gap[1]}" + (f"; {error}" if error else "")
            if gap[2] is not None:   # in its own head start: no head start (D1006), timed from the change
                seconds = (t1 - gap[2]) / 1000
        bar, shown = progress_of(events, t0, t1)
        sample = {"s": round(seconds, 3), "bar": bar, "progress": shown,
                  "late_ms": round(self.p.worst(t0, t1)) if self.p else 0}
        if page is not None:
            sample["page"] = round(page, 3)
        if gap:
            sample["gap_ms"] = round(gap[0])
        if error:
            sample["error"] = error[:300]
        if cpu is not None:
            sample["cpu"] = round(cpu, 3)
            if not error and starved(seconds, cpu):
                sample["starved"] = True
        if steady is not None:
            sample["steady"] = steady
            if self.memory:
                sample["resident"] = self.memory.peak
        retake = sample.get("starved") and op not in self.retaking and seconds <= LONG
        self.log.append(f"{self.run.name} {op} {seconds:.2f} s{f' (page {page:.2f} s)' if page is not None else ''}"
                        f"{f' cpu {cpu:.2f} s' if cpu is not None else ''}"
                        f"{' starved' if sample.get('starved') else ''}{', taken once more' if retake else ''}"
                        f"{' bar ' + str(bar) if bar else ''}{' progress' if shown else ''}"
                        f"{f' steady {steady / 2**30:.2f} GiB' if steady is not None else ''}"
                        f"{f' peak {sample['resident'] / 2**30:.2f} GiB' if 'resident' in sample else ''}"
                        f"{' ' + error[:120] if error else ''}")
        print(self.log[-1], flush=True)
        if retake:
            self.retaking[op] = sample
            return
        if first := self.retaking.pop(op, None):
            sample["retook"] = first["s"]
        self.samples.setdefault(op, []).append(sample)

    def spent(self, op: str | None) -> float | None:
        """The CPU seconds since the last click, for ``op`` while it needs a sample."""
        return self.memory.take() - self.clicked if self.memory and self.need(op) else None

    def finish(self) -> None:
        """The run is over: a starved sample whose second take never came stands."""
        for op, sample in self.retaking.items():
            self.samples.setdefault(op, []).append(sample)
        self.retaking.clear()

    def change(self, t: float) -> None:
        """The page's time ``t`` is the pass's last change: D1014's head start counts from it."""
        self.changed = t

    def idle(self, p: Page, why: str, seconds: float = 0.0, done: str | None = None,
             since: float | None = None) -> None:
        """A gap between actions (``why``): ``seconds`` slept, then ``done``
        waited for; the freeze probe's worst tick due in it is the gap's
        (``since``: the change a head start counts from)."""
        g0 = p.now()
        if seconds > 0:
            self.sleep(seconds)
        if done:
            p.wait(done)
        g1 = p.settled()
        self.ev += p.events()
        worst = p.worst(g0, g1)
        if self.gap is None or worst >= self.gap[0]:
            self.gap = (worst, why, since)

    def warmed(self, p: Page) -> None:
        """Wait, as a gap, for D1008's warm-up to end (at once until the page has one)."""
        self.idle(p, "the warm-up", done=WARM)

    def state(self, name: str, make: Callable[[Path], None]) -> Path:
        """A fresh copy of a state (a HOME, a browser profile) made once a
        run: ``make(folder)`` fills it the first time (one pass), and each
        call clones it anew (``cp -c``, APFS's clones, on macOS)."""
        made = self.scratch / "states" / name
        if not made.is_dir():
            making = made.with_name(name + ".making")
            shutil.rmtree(making, ignore_errors=True)   # a make that stopped
            making.mkdir(parents=True)
            make(making)
            making.rename(made)
        clone = Path(tempfile.mkdtemp(prefix=f"{name}.", dir=made.parent))
        clone.rmdir()
        if sys.platform == "darwin":
            subprocess.run(["cp", "-cR", str(made), str(clone)], check=True)
        else:
            shutil.copytree(made, clone, symlinks=True)
        return clone

    def over(self) -> None:
        """The pass is over: a freeze no sample took stops it (its ops still needing samples get the error)."""
        gap, self.gap = self.gap, None
        if gap and gap[0] > FREEZE_MS:
            raise RuntimeError(f"the page froze {gap[0]:.0f} ms in {gap[1]}")

    def start(self, p: Page, op: str | None, action: str | Callable[[], None] | None, arg=None) -> float:
        """Do ``action`` (a page function, a Python callable, or nothing), as
        ``op``'s click: an op with ``head_start`` comes :data:`HEAD_START`
        after the pass's last change (slept to: at once when that is past,
        or with none). The page's clock at the click."""
        if op in OPS and OPS[op].head_start and self.changed is not None:
            if (wait := self.changed + HEAD_START * 1000 - p.now()) > 0:
                self.idle(p, f"the head start before {op}", wait / 1000, since=self.changed)
            self.changed = None
        if self.memory:   # the sampler's last figure, up to its 0.2 s old: nothing between the head start and the click
            self.clicked = self.memory.used
        if callable(action):
            t0 = p.now()
            action()
            return t0
        return p.do(action, arg) if action else p.now()

    def act(self, p: Page, op: str | None, action: str | Callable[[], None] | None, done: str,
            timeout: float = 900, arg=None, change: bool = False) -> tuple[float, float]:
        """Do ``action`` (:meth:`start`) and wait for ``done``; time it as
        ``op`` by the page's clock (``change``: the action is a change the
        player makes). A done-state that reads ``error: …`` (the page's error
        line) fails the sample."""
        t0 = self.start(p, op, action, arg)
        if change:
            self.change(t0)
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
        self.record(op, (t1 - t0) / 1000, self.ev, t0, t1, error, cpu=self.spent(op),
                    steady=p.js(STEADY) if done == BUILT and self.run.host == "site" and self.need(op) else None)
        if error:
            raise RuntimeError(f"{op}: {error[:200]}")
        return t1

    def race(self, p: Page, op: str, action: str, dones: dict[str, str], timeout: float = 900,
             after: dict[str, str] | None = None) -> dict[str, float]:
        """One click's done-states raced (``dones``: ``{op: done}``): ``action``
        done as ``op``'s click (:meth:`start`), then every done-state polled
        in one evaluate; each op is its own first true poll, from the click
        or, for an op ``after`` names (``{op: another}``), from that one's
        done. ``{op: the page's clock at its done}``."""
        t0 = self.start(p, op, action)
        got: dict[str, tuple[float, object]] = {}
        began = time.monotonic()
        while len(got) < len(dones):
            t, values = p.poll(list(dones.values()))
            got |= {name: (t, value) for name, value in zip(dones, values) if value and name not in got}
            if errors := [v for _, v in got.values() if isinstance(v, str) and v.startswith("error: ")]:
                raise RuntimeError(f"{op}: {errors[0][:200]}")
            if len(got) < len(dones):
                if (waited := time.monotonic() - began) > timeout:
                    raise TimeoutError(f"timed out after {timeout:.0f} s: {[n for n in dones if n not in got]}")
                self.sleep(0.05 if waited < 5 else 0.2)
        self.ev += p.events()
        cpu = self.spent(op)   # the click's own op's, read at the race's end: its other dones' CPU in it, never under
        for name in sorted(dones, key=lambda name: name != op):   # the click's own op first: its head start is its
            t, begin = got[name][0], got[after[name]][0] if after and name in after else t0
            self.record(name, max(0.0, t - begin) / 1000, self.ev, begin, max(t, begin),
                        cpu=cpu if name == op else None)
        return {name: t for name, (t, _) in got.items()}


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
    ps's ``(pid, ppid, command, its start)``), sampled every 0.2 s, and the
    CPU seconds they have used (:attr:`used`): each process's highest figure
    stays when it exits, so a child gone mid-op keeps what it used."""

    def __init__(self, roots: Callable[[list[tuple[int, int, str, str]]], list[int]]):
        self.roots, self.peak, self.used, self._stop = roots, 0, 0.0, threading.Event()
        self._cpu: dict[tuple[int, str], float] = {}   # by pid and start: a pid reused is another process
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._sample, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join(5)

    @staticmethod
    def rows(rss: dict[int, int] | None = None, cpu: dict[int, float] | None = None) -> list[tuple[int, int, str, str]]:
        """ps's ``(pid, ppid, command, its start)`` rows (each resident KiB into ``rss``, CPU seconds into ``cpu``)."""
        out = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,rss=,time=,lstart=,comm="], capture_output=True,
                             text=True).stdout
        rows = []
        for row in out.splitlines():   # lstart is five words: "Sun Nov  1 08:22:00 2026"
            if len(f := row.split(None, 9)) == 10 and f[0].isdigit():
                rows.append((int(f[0]), int(f[1]), f[9], " ".join(f[4:9])))
                if rss is not None:
                    rss[int(f[0])] = int(f[2])
                if cpu is not None:   # [[dd-]hh:]mm:ss.cc: user + system
                    cpu[int(f[0])] = functools.reduce(lambda s, part: s * 60 + float(part),
                                                      f[3].replace("-", ":").split(":"), 0.0)
        return rows

    def take(self) -> float:
        """One sample now: :attr:`used`, as it stands."""
        with self._lock:
            rss: dict[int, int] = {}
            cpu: dict[int, float] = {}
            rows = self.rows(rss, cpu)
            kids: dict[int, list[int]] = {}
            for pid, ppid, *_ in rows:
                kids.setdefault(ppid, []).append(pid)
            seen, todo = set(), list(self.roots(rows))
            while todo:
                if (pid := todo.pop()) not in seen:
                    seen.add(pid)
                    todo += kids.get(pid, [])
            self.peak = max(self.peak, sum(rss.get(pid, 0) for pid in seen) * 1024)
            for pid, _, _, start in rows:
                if pid in seen:   # the most seen: a zombie, a killed child not reaped yet, reads 0:00.00
                    self._cpu[pid, start] = max(self._cpu.get((pid, start), 0.0), cpu[pid])
            self.used = sum(self._cpu.values())
            return self.used

    def _sample(self):
        while not self._stop.wait(0.2):
            self.take()


MARK = f"/nonexistent/azurkit-perf-{os.getpid()}"   # this run's mark in the browsers' PATH (:func:`browser_pids`)
_launched: dict[tuple[int, str], bool] = {}


def ours(pid: int, started: str) -> bool:
    """Whether launchd started the WebKit XPC process ``pid``, which started
    at ``started``, for this run's browser: its record (``launchctl print
    pid/N``) holds the PATH of the UI process that asked for it, which
    carries :data:`MARK` (macOS). Where launchctl can't say it is counted,
    and a pid reused is asked about again: never one of ours left out."""
    if (pid, started) not in _launched:
        try:
            out = subprocess.run(["launchctl", "print", f"pid/{pid}"], capture_output=True, text=True, timeout=10).stdout
        except (OSError, subprocess.TimeoutExpired):
            out = ""
        path = re.search(r"PATH => (\S+)", out)
        _launched[pid, started] = path is None or MARK in path.group(1)
    return _launched[pid, started]


def browser_pids(rows: list[tuple[int, int, str, str]], before: set[tuple[int, str]]) -> list[int]:
    """The browsers Playwright's driver (a node child of this process)
    started, and WebKit's own processes (its pages, network and GPU: XPC
    services launchd starts, so outside the tree) that weren't running
    before this run (``before``, each by its pid and start, so a pid reused
    is new) and that launchd started for this run's browser (:func:`ours`):
    another seat's WebKit, started meanwhile, isn't counted."""
    drivers = [pid for pid, ppid, comm, _ in rows if ppid == os.getpid() and "node" in comm]
    return [pid for pid, ppid, comm, started in rows if ppid in drivers or (pid, started) not in before
            and ".xpc/" in comm and "/playwright/webkit" in comm and ours(pid, started)]


class App:
    """``python -m azurkit serve`` from the scratch venv ``python`` is
    (:func:`venv`), in its own fresh HOME (its config and user cache, and its
    cwd), no image named (``AZURKIT_ISO`` dropped), the clone as its Content
    from; quit by closing its input."""

    def __init__(self, python: str, home: Path, run: Run, content: Path | None):
        self.python, self.home, self.run, self.content = python, home, run, content
        self.first_time()
        self.env = {k: v for k, v in os.environ.items()
                    if k not in ("AZURKIT_ISO", "AZURKIT_ISO_EUROPE", "VIRTUAL_ENV", "PYTHONPATH", "AZURKIT_CORES", "AZURKIT_RAM")}
        self.env |= {"HOME": str(home), "AZURKIT_NO_WINDOW": "1"}
        if run.cores:
            self.env["AZURKIT_CORES"] = str(run.cores)
        if run.ram:
            self.env["AZURKIT_RAM"] = str(run.ram)
        self.proc = None

    def first_time(self) -> None:
        """The home as a first launch finds it: no setup, tracker or cache of a launch before."""
        shutil.rmtree(self.home, ignore_errors=True)
        config = self.home / "Library" / "Application Support" / "AzurKit"
        config.mkdir(parents=True)
        if self.content is not None:
            (config / "app.json").write_text(json.dumps({"content_source": str(self.content)}), encoding="utf-8")

    def launch(self, d: Driver, ctx, op: str | None) -> Page:
        """Spawn the server and open its page: ``op`` timed from the spawn to the page's ready flag."""
        self.driver = d
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
        d.engine(p)
        d.fresh(p)
        d.record(op, time.monotonic() - t, d.ev, 0, t1)
        return p

    def quit(self, p: Page | None = None) -> None:
        if p is not None:
            self.driver.leave(p)
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


class _Quiet(_page.Static):
    late: dict[str, str] = {}   # the lag model's worker.mjs and hasher.mjs, by path, served in place of the files

    def log_message(self, *args):
        pass

    def do_GET(self):
        if (text := self.late.get(self.path.split("?")[0])) is not None:
            body = text.encode()
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
    ``lag`` its ``worker.mjs`` and ``hasher.mjs`` answer each File read
    :data:`LAG_MS` late (:func:`lagged`)."""
    late = {} if not lag else {
        "/worker.mjs": lagged((site / "worker.mjs").read_text(encoding="utf-8")),
        "/hasher.mjs": lagged((site / "hasher.mjs").read_text(encoding="utf-8"), HASHER_LAG)}
    handler = type("Handler", (_Quiet,), {"late": late})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", free_port()),
                                             functools.partial(handler, directory=str(site)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/"
    finally:
        server.shutdown()
        server.server_close()


def lagged(text: str, reads: tuple = LAG) -> str:
    """A module's ``text`` (``worker.mjs``'s, ``hasher.mjs``'s) with each File
    read ``reads`` lists made :data:`LAG_MS` late: each must be there once,
    and no other read of a File (:data:`READS` but :data:`NOT_FILE`), else a
    SystemExit names it."""
    rest = text
    for read, late in reads:
        if text.count(read) != 1:
            raise SystemExit(f"perf: the lag model's read is there {text.count(read)} times, not once: "
                             f"{read!r} (tests/_perf.py LAG)")
        text, rest = text.replace(read, late), rest.replace(read, "")
    for other in NOT_FILE:
        rest = rest.replace(other, "")
    if unknown := [line.strip() for line in rest.splitlines() if READS.search(line)]:
        raise SystemExit(f"perf: a module reads a File the lag model doesn't make late: {unknown[0]!r} "
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
        d.idle(p, f"the save dialog before {op}", SAVE_DIALOG)
    try:
        d.act(p, op, "() => { azurkit.saved = null; document.querySelector('#save').click(); }", SAVED, 1800)
    finally:
        out.unlink(missing_ok=True)


def app_build(d: Driver, app: App, ctx) -> None:
    p = app.launch(d, ctx, None)
    d.act(p, None, typed("iso-path", str(d.iso)), USA, change=True)
    d.act(p, "A12", build_js(), BUILT)
    _save(d, p, "A13", "defaults")
    d.act(p, None, build_js(), BUILT)
    _save(d, p, "A14", "defaults", dialog=False)
    p.js(click("tab-characters"))
    p.wait(SPECIES)
    d.act(p, None, model("keylord"), chosen("keylord"), change=True)
    d.act(p, "A15", build_js(), BUILT, 1800)
    _save(d, p, "A17", "keylord")
    d.act(p, "A16", build_js(), BUILT, 1800)
    app.quit(p)


def _seeded(d: Driver, p: Page, randomize: bool = True, seed: str = "azurkit") -> None:
    """The Randomizer tab open with ``seed``, Randomize ticked (its ask answered) or not."""
    p.js(click("tab-randomizer"))
    p.wait("() => azurkit.rando.view?.share")
    if randomize:
        d.act(p, None, SEED_ASK.replace("'azurkit'", f"'{seed}'"),
              "() => azurkit.rando.view && document.getElementById('rando-on').checked", 900, change=True)
    else:
        d.act(p, None, typed("rando-seed", seed), "() => document.getElementById('rando-seed').value", change=True)


# The build's first stage record (its ask's record: the bar's first stage)
STAGED = "() => [...azurkit.asks.values()].some((a) => a.kind === 'build' && a.record)"
# Build, then Cancel at its first stage record, else 1 s after
CANCEL_EARLY = """() => { azurkit.build = null; document.querySelector('#build').click(); const t = performance.now();
  const at = setInterval(() => { if ((%s)() || performance.now() - t >= 1000) {
      clearInterval(at); document.querySelector('#cancel').click(); } }, 20); }""" % STAGED
# The build's own answer, its ask over: its "Ready" line or its error, whatever came after it (a change once it has
# answered, a model's pick, forgets azurkit.build, which BUILT reads)
ANSWERED = (f"() => !azurkit.building && (document.querySelector('#status').textContent.startsWith('Ready') "
            f"? 'built' : {ERROR})")


def app_seed(d: Driver, app: App, ctx) -> None:
    p = app.launch(d, ctx, None)
    d.act(p, None, typed("iso-path", str(d.iso)), USA)
    _seeded(d, p)
    d.act(p, "A27", build_js(), BUILT, 1800)
    if d.need("A28"):   # a slow step another pass doesn't need is skipped
        _save(d, p, "A28", "seed")
    if d.need("A29"):   # a seed no build has made, so its build runs (D13), cancelled; then Build, no head start
        d.act(p, None, typed("rando-seed", "2"), "() => document.getElementById('rando-seed').value === '2'",
              change=True)
        d.act(p, None, CANCEL_EARLY, "() => /Cancelled/.test(document.querySelector('#status').textContent)", 600)
        d.act(p, "A29", build_js(), BUILT, 1800)
    # A30's build: a seed no build has made, so it still runs at the pick (one of a kept plan answers within 1 s)
    d.act(p, None, typed("rando-seed", "3"), "() => document.getElementById('rando-seed').value === '3'",
          change=True)
    p.js(click("tab-characters"))
    p.wait(SPECIES)
    p.js(build_js())
    d.idle(p, "the build's first stage before A30", done=STAGED)
    d.act(p, "A30", model("keylord"), chosen("keylord"), 1800)
    p.wait(ANSWERED, 1800)
    app.quit(p)


MEDIAN = "42"   # the median seed's fill (RS1), A56-A58's


def app_ahead_track(d: Driver, app: App, ctx) -> None:
    """Track, on a seed no build has filled."""
    p = app.launch(d, ctx, None)
    _seeded(d, p, randomize=False, seed=MEDIAN)
    d.act(p, None, click("rando-view-tracker"), WORLD, 600)
    d.act(p, "A56", click("track-seed"), "() => document.getElementById('track-head').textContent.trim()", 1800)
    app.quit(p)


def app_ahead_build(d: Driver, app: App, ctx) -> None:
    """Build, on a seed no plan has filled."""
    p = app.launch(d, ctx, None)
    d.act(p, None, typed("iso-path", str(d.iso)), USA)
    _seeded(d, p, seed=MEDIAN)
    d.act(p, "A57", build_js(), BUILT, 1800)
    app.quit(p)


def app_ahead_stale(d: Driver, app: App, ctx) -> None:
    """Build after a change 1 s into the head start, which also times how fast the stale job drops."""
    p = app.launch(d, ctx, None)
    d.act(p, None, typed("iso-path", str(d.iso)), USA)
    _seeded(d, p)                                       # "azurkit": its work ahead starts
    d.idle(p, "the stale seed's second", 1.0)
    d.act(p, None, typed("rando-seed", MEDIAN), f"() => document.getElementById('rando-seed').value === '{MEDIAN}'",
          change=True)
    d.act(p, "A58", build_js(), BUILT, 1800)
    app.quit(p)


# Seed difficulty's ops (its design's sec. 4.3): Track or Build at a level's costliest settings, each op's seed the one
# of "0".."99" whose plan there takes the most fill reaches (scripts/seed_forcing.py --rows; A74's with no slider):
# op: (Track or Build, A80's the spoiler's View after it, movement tier, skip ceiling, level, categories kept, seed)
SHAPED = {
    "A77": ("track", "standard", 2, 2, (), "80"),
    "A78": ("build", "hard", 3, 2, (), "77"),
    "A79": ("track", "hard", 3, 3, (), "53"),
    "A80": ("build", "hard", 3, 3, (), "53"),
    "A70": ("track", "hard", 2, 3, (), "19"),
    "A71": ("track", "hard", 3, 3, ("fragments",), "31"),
    "A72": ("track", "frame_perfect", 4, 4, (), "15"),
    "A73": ("build", "frame_perfect", 4, 4, (), "15"),
    "A74": ("track", "hard", 0, 3, (), "83"),
}
SHAPED_SLIDER = """() => { const box = document.querySelector('#packs input[data-pack="player_physics"]');
  if (!box.checked) box.click();
  const field = document.getElementById('player_physics.jump_speed_scale');
  field.value = '1.3'; field.dispatchEvent(new Event('input', { bubbles: true })); }"""


def _shaped_share(tier: str, ceiling: int, level: int, kept: tuple) -> str:
    from azurkit.tools.randomizer.planner.settings import Settings, share_encode

    return share_encode(Settings(ceiling, tier, {}, frozenset(kept), seed_difficulty=level), [])


def app_shaped(d: Driver, app: App, ctx) -> None:
    """Each op on a first launch (a remembered setup would be on, a remembered tracker's head already its done-state):
    its share string typed (the page's select is the next lane's), its seed typed, then the click after the head start."""
    for op, (kind, tier, ceiling, level, kept, seed) in SHAPED.items():
        if not d.needed({"A80": (op, "A75"), "A79": (op, "A76")}.get(op, (op,))):
            continue
        p = app.launch(d, ctx, None)
        if kind == "build":
            d.act(p, None, typed("iso-path", str(d.iso)), USA)
        if op == "A74":
            p.js(SHAPED_SLIDER)
        p.js(click("tab-randomizer"))
        p.wait("() => azurkit.rando.view?.share")
        if kind == "build":
            d.act(p, None, UNTICK.replace("if (on.checked)", "if (!on.checked)"),
                  "() => azurkit.rando.view && document.getElementById('rando-on').checked", 900)
        share = _shaped_share(tier, ceiling, level, kept)
        d.act(p, None, "() => { const b = document.getElementById('rando-share'); b.value = %s; "
                       "b.dispatchEvent(new Event('change')); }" % json.dumps(share),
              "() => azurkit.rando.view?.settings.seed_difficulty === %d" % level, 900, change=True)
        d.act(p, None, typed("rando-seed", seed), "() => document.getElementById('rando-seed').value === %s" % json.dumps(seed),
              change=True)
        if kind == "track":
            d.act(p, None, click("rando-view-tracker"), WORLD, 600)
            d.act(p, op, click("track-seed"),
                  "() => /seed difficulty/.test(document.getElementById('track-head').textContent)", 1800)
            if op == "A79" and d.need("A76"):
                d.act(p, "A76", click("track-spoiler"), "() => azurkit.tracker.state.view?.head.requires?.openers "
                                                        "&& !azurkit.tracker.state.running", 900)
        else:
            d.act(p, op, build_js(), BUILT, 1800)
            if op == "A80" and d.need("A75"):
                d.act(p, "A75", click("spoiler-view"), "() => !document.getElementById('spoiler').hidden "
                                                       "&& document.getElementById('spoiler').textContent.length", 900)
        app.quit(p)
        app.first_time()


def _detail(d: Driver, p: Page, first: str, again: str) -> None:
    """w1's map opened and zoomed past its pixels until its detail picture is drawn (``first``), then Fit and the
    same zoom (``again``: the picture held), back on the world map."""
    d.act(p, first, SHOWN_TOP, DETAILED, 600)
    while d.need(again):
        p.js(click("map-fit"))
        d.act(p, again, TOP, DETAILED, 600)
    d.act(p, None, click("map-back"), WORLD, 600)


def app_track(d: Driver, app: App, ctx) -> None:
    p = app.launch(d, ctx, None)
    _seeded(d, p, randomize=False)
    d.act(p, None, click("rando-view-tracker"), WORLD, 600)   # its own work, before the head start
    d.act(p, "A23", click("track-seed"), "() => document.getElementById('track-head').textContent.trim()", 1800)
    p.js(click("rando-view-settings"))
    d.act(p, None, typed("iso-path", str(d.iso)), USA)
    d.act(p, None, "() => { azurkit.rando.view = null; const on = document.getElementById('rando-on'); "
                   "if (!on.checked) on.click(); }",
          "() => azurkit.rando.view && document.getElementById('rando-on').checked", change=True)
    d.act(p, "A26", build_js(), BUILT, 1800)
    if d.need("A24"):
        d.act(p, "A24", click("rando-view-tracker"), ART_DONE, 3600)
    if d.needed(("A37", "A38")):
        p.js(click("rando-view-tracker"))
        p.wait(WORLD, 600)
        _detail(d, p, "A37", "A38")
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
    d.act(p, "A18", model("booblord"), chosen("booblord"), 3600, change=True)
    d.act(p, "A20", build_js(), BUILT, 3600)
    _save(d, p, "A22", "booblord")
    d.act(p, "A21", build_js(), BUILT, 3600)
    while d.need("A19"):   # again in one state: another model, then booblord
        d.act(p, None, model("garret4"), chosen("garret4"), 600)
        d.act(p, "A19", model("booblord"), chosen("booblord"), 3600)
    app.quit(p)


# D999: a shape no build has made (booblord with one slider moved) builds first with a bar (A31); at the next launch
# the same shape is the app's kept answer (A32, strict). Her own pictures are drawn first, untimed.
def reshape(value: str) -> str:
    return ("() => { const s = azurkit.characters.state.view.chosen.shapes[0].name, b = document.getElementById("
            f"`char-shape:${{s}}`); b.value = '{value}'; b.dispatchEvent(new Event('change')); }}")


RESHAPE = reshape("1.25")
# D1011: what the pictures show of the shape the tab holds: its Preview, or the exact ones
SHOWS = ("(() => { const c = azurkit.characters.state, s = c.shown; return s && s.shape === JSON.stringify("
         "Object.entries(c.character.shapes ?? {}).sort()) && s.name === c.character.species && s.preview === %s; })()")
PREVIEWED, EXACT = f"() => {SHOWS % 'true'}", f"() => {SHOWS % 'false'}"
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
    d.act(p, None, RESHAPE, RESHAPED, 600, change=True)
    d.act(p, "A31", build_js(), BUILT, 3600)
    app.quit(p)
    p = app.launch(d, ctx, None)   # the same HOME: the remembered setup wears the reshape
    d.act(p, None, typed("iso-path", str(d.iso)), USA)
    p.js(click("tab-characters"))
    p.wait(f"() => azurkit.characters.state.character.species === 'booblord' && ({RESHAPED[6:]})", 600)
    d.act(p, "A32", build_js(), BUILT, 1800)
    app.quit(p)


def _reshape_pictures(d: Driver, p: Page, preview: str, first: str, again: str) -> None:
    """D1011, booblord installed: a slider's moves each show the nearest shape at once, the dress waiting until it rests
    (preview); the exact pictures replace it (first, from the last move, a bar's); back on her shipped shape, the
    same shape is exact at once (again)."""
    d.act(p, None, """() => document.querySelector('#char-community .entry[data-entry="booblord"] button').click()""",
          """() => document.querySelector('#char-community .entry[data-entry="booblord"] .model')""", 1800)
    d.act(p, None, model("booblord"), chosen("booblord"), 3600)
    for stop in ("1.15", "1.2", "1.25"):
        t0, _ = d.act(p, preview, reshape(stop), PREVIEWED, 600, change=True)
    d.until(p, first, t0, EXACT, 3600)
    while d.need(again):
        d.act(p, None, reshape("1"), EXACT, 600)
        d.act(p, again, RESHAPE, EXACT, 600)


def app_reshape_pictures(d: Driver, app: App, ctx) -> None:
    p = app.launch(d, ctx, None)
    d.act(p, None, typed("iso-path", str(d.iso)), USA)
    p.js(click("tab-characters"))
    p.wait("""() => document.querySelector('#char-community .entry[data-entry="booblord"] button')""", 600)
    _reshape_pictures(d, p, "A59", "A60", "A61")
    app.quit(p)


def _site_page(d: Driver, ctx, url: str, op: str | None) -> Page:
    """A new page on ``url``, ``op`` timed by its own clock from its navigation to the engine's ready flag."""
    p = Page(ctx.new_page())
    p.page.goto(url)
    t1, _ = p.wait(READY, 600)
    d.engine(p)
    d.fresh(p)
    d.record(op, t1 / 1000, d.ev, 0, t1)
    return p


def _pick(d: Driver, p: Page, op: str | None, done: str = USA) -> None:
    d.act(p, op, lambda: p.page.set_input_files("#iso", str(d.iso)), done, 1800, change=True)


def _download(d: Driver, p: Page, op: str | None) -> None:
    """The click to the file downloaded and checked against the build (the page's own check, its bar moving), its page
    part to the download's start (the browser's own bar after)."""
    t0 = p.now()
    with p.page.expect_download(timeout=1_800_000) as caught:
        p.js("() => document.querySelector('#save').click()")
    started = p.now()
    caught.value.path()
    t1, check = p.wait("() => azurkit.saveCheck !== 'running' && azurkit.saveCheck", 1800)
    d.ev += p.events()
    d.record(op, (t1 - t0) / 1000, d.ev, t0, t1, None if check == "held" else check, (started - t0) / 1000)
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
    if d.needed(("S10", "S11", "S14", "R14", "S49")):   # slow steps another pass doesn't need are skipped
        t0, _ = d.act(p, "S10", model("keylord"), chosen("keylord", pictures=False), 1800, change=True)
        d.until(p, "S11", t0, chosen("keylord"), 1800)
        if d.needed(("S14", "R14", "S49")):
            _, built = d.act(p, "S14", build_js(), BUILT, 1800)
            d.until(p, "R14", built, READY, 600)
            if d.need("S49"):
                _download(d, p, "S49")
    d.leave(p)
    while d.needed(("S02", "S04")):
        p = _site_page(d, ctx, url + "?again", "S02")
        _pick(d, p, "S04")
        d.leave(p)


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
                       "document.querySelectorAll('#char-species .model').length === "
                       "azurkit.characters.state.view.species.filter((s) => !s.object).length")
    if d.content is not None:
        d.act(p, "S13", """() => { azurkit.characters.state.view.perfOld = true;
                            document.querySelector('#char-community .entry[data-entry="beamlord"] button').click(); }""",
              """() => document.querySelector('#char-community .entry[data-entry="beamlord"] .model')
                   && !azurkit.characters.state.installing && azurkit.characters.state.view
                   && !azurkit.characters.state.view.perfOld""", 1800)
        d.act(p, "S12", model("beamlord"), chosen("beamlord"), 1800)
    d.leave(p)


def site_reshape_pictures(d: Driver, ctx, url: str) -> None:
    p = _site_page(d, ctx, url, None)
    _pick(d, p, None)
    p.js(click("tab-characters"))
    p.wait(SPECIES, 1800)
    d.act(p, None, "() => { const b = document.getElementById('char-source'); b.value = './content-source/'; "
                   "b.dispatchEvent(new Event('change')); }",
          """() => document.querySelector('#char-community .entry[data-entry="booblord"] button')""", 600)
    _reshape_pictures(d, p, "S51", "S52", "S53")
    d.leave(p)


def site_track(d: Driver, ctx, url: str) -> None:
    p = _site_page(d, ctx, url, None)
    _pick(d, p, None)
    _seeded(d, p, randomize=False)
    d.act(p, "S19", click("rando-view-tracker"), WORLD, 600)   # a tab's open: no head start, its work its own
    d.race(p, "S18", click("track-seed"), {"S18": TRACKED, "S20": ART_DONE}, 3600, after={"S20": "S18"})
    while d.need("S22"):
        d.act(p, "S22", "() => azurkit.tracker.map.show('w1', true)", LEVEL, 600)
        d.act(p, None, click("map-back"), WORLD, 600)
    if d.needed(("S30", "S31")):
        _detail(d, p, "S30", "S31")
    p.js(click("rando-view-settings"))
    d.act(p, None, "() => { azurkit.rando.view = null; const on = document.getElementById('rando-on'); "
                   "if (!on.checked) on.click(); }",
          "() => azurkit.rando.view && document.getElementById('rando-on').checked", change=True)
    d.act(p, "S23", build_js(), BUILT, 1800)
    while d.need("S25"):
        d.act(p, "S25", click("spoiler-view"),
              "() => !document.getElementById('spoiler').hidden && document.getElementById('spoiler').textContent.length")
        p.js(click("spoiler-view"))
    d.leave(p)
    p = _site_page(d, ctx, url + "?reopen", None)
    d.act(p, "S21", "() => { document.getElementById('tab-randomizer').click(); "
                    "document.getElementById('rando-view-tracker').click(); }", TRACKED, 1800)
    d.leave(p)


def site_seed(d: Driver, ctx, url: str) -> None:
    p = _site_page(d, ctx, url, None)
    _pick(d, p, None)
    _seeded(d, p)
    _, built = d.act(p, "S24", build_js(), BUILT, 1800)
    d.until(p, "R24", built, READY, 600)
    if d.need("S50"):
        _download(d, p, "S50")
    d.leave(p)


# ---- the Tools tab (Step 4.7c): the image's info, Verify every file (first, with its bar, D982; again: the kept
# check), the file list, Extract the largest file, Open a build… (a build of the defaults, saved untimed), a mods file
# saved and loaded back, a plan file's spoiler and the last build's report.
INFO = "() => azurkit.tools?.state.info"
WHOLE = "() => azurkit.tools.state.info?.whole"
LISTED = "() => azurkit.tools.state.files && !document.getElementById('tools-files').hidden"
LARGEST = """() => { const f = azurkit.tools.state.files.reduce((a, b) => b[2] > a[2] ? b : a);
  const box = document.getElementById("tools-filter"); box.value = f[0]; box.dispatchEvent(new Event("input"));
  document.querySelector("#tools-rows button").click(); }"""
STATUS = "document.getElementById('status').textContent"
OPENED = "() => azurkit.tools.state.opened"
SPOILED = "() => azurkit.tools.state.spoiler"
REPORTED = "() => !document.getElementById('tools-report-text').hidden"


def _plan_file(d: Driver) -> Path:
    """A plan file (seed ``azurkit``, the default settings), made once a run (``azurkit plan``)."""
    plan = d.scratch / "azurkit plan.json"
    if not plan.is_file():
        subprocess.run([sys.executable, "-m", "azurkit", "plan", "--seed", "azurkit", "--out", str(plan)], cwd=ROOT,
                       env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}, capture_output=True,
                       check=True, timeout=900)
    return plan


def _tools(d: Driver, p: Page, ops: tuple[str, ...], plan: Path) -> None:
    """The Tools tab's first ops (the image picked): its info as the tab opens, a plan file's spoiler asked at once
    (cold, as a player who goes straight to Tools gets it: nothing has read the randomizer's logic but what the tab's
    opening started), Verify every file first and again, the file list."""
    info, spoiler, first, again, listed = ops
    d.act(p, info, click("tab-tools"), INFO, 600)
    d.act(p, spoiler, lambda: p.page.set_input_files("#tools-plan-file", str(plan)), SPOILED, 900)
    d.act(p, first, click("tools-verify"), WHOLE, 1800)
    while d.need(again):   # the engine's check is whole now: asked again, it hashes nothing
        p.js("() => { azurkit.tools.state.info = { ...azurkit.tools.state.info, whole: false }; }")
        d.act(p, again, click("tools-verify"), WHOLE, 600)
    d.act(p, listed, click("tools-list"), LISTED, 600)


def _shown_report(d: Driver, p: Page, op: str) -> None:
    while d.need(op):
        d.act(p, op, click("tools-report-view"), REPORTED)
        p.js(click("tools-report-view"))


def app_tools(d: Driver, app: App, ctx) -> None:
    plan = _plan_file(d)   # made before the launch: untimed, no head start
    p = app.launch(d, ctx, None)
    d.act(p, None, typed("iso-path", str(d.iso)), USA, change=True)
    _tools(d, p, ("A47", "A54", "A48", "A49", "A50"), plan)
    d.act(p, "A51", LARGEST, f"() => /^Saved .* sha256 /.test({STATUS}) ? 'saved' : {ERROR}", 900)
    p.js(click("tab-patches"))
    d.act(p, None, build_js(), BUILT, 1800)
    out = _out(d, "opened")   # the build, saved untimed: the open below reads it
    p.js(typed("out-path", str(out)))
    d.act(p, None, "() => { azurkit.saved = null; document.querySelector('#save').click(); }", SAVED, 1800)
    p.js(click("tab-tools"))
    p.js(typed("tools-open-path", str(out)))
    d.act(p, "A52", click("tools-open"), OPENED, 600)
    _shown_report(d, p, "A55")
    mods = app.home / "Downloads" / "AzurKit mods.json"
    t0, t1 = d.act(p, None, click("tools-mods-save"), f"() => {STATUS}.startsWith('Saved the mods file')", 600)
    t2, t3 = d.act(p, None, lambda: p.page.set_input_files("#tools-mods-file", str(mods)),
                   f"() => {STATUS}.startsWith('Loaded') ? 'loaded' : {ERROR}", 600)
    t0, t1 = max((t0, t1), (t2, t3), key=lambda span: span[1] - span[0])
    d.record("A53", (t1 - t0) / 1000, d.ev, t0, t1)
    out.unlink(missing_ok=True)
    app.quit(p)


def site_tools(d: Driver, ctx, url: str) -> None:
    plan = _plan_file(d)   # made before the page: untimed, no head start
    p = _site_page(d, ctx, url, None)
    _pick(d, p, None)
    _tools(d, p, ("S40", "S47", "S41", "S42", "S43"), plan)
    if d.need("S44"):
        t0 = p.now()
        with p.page.expect_download(timeout=900_000) as caught:
            p.js(LARGEST)
        caught.value.path()
        t1 = p.now()
        d.ev += p.events()
        d.record("S44", (t1 - t0) / 1000, d.ev, t0, t1)
        caught.value.delete()
    p.js(click("tab-patches"))
    d.act(p, None, build_js(), BUILT, 1800)
    with p.page.expect_download(timeout=1_800_000) as caught:
        p.js("() => document.querySelector('#save').click()")
    built = Path(caught.value.path())
    p.wait(READY, 600)   # the site's engine is replaced after each build
    p.js(click("tab-tools"))
    d.act(p, "S45", lambda: p.page.set_input_files("#tools-open-file", str(built)), OPENED, 900)
    caught.value.delete()
    _shown_report(d, p, "S48")
    t0 = p.now()
    with p.page.expect_download(timeout=600_000) as saved:
        p.js(click("tools-mods-save"))
    mods, t1 = saved.value.path(), p.now()
    t2, t3 = d.act(p, None, lambda: p.page.set_input_files("#tools-mods-file", str(mods)),
                   f"() => {STATUS}.startsWith('Loaded') ? 'loaded' : {ERROR}", 600)
    t0, t1 = max((t0, t1), (t2, t3), key=lambda span: span[1] - span[0])
    d.record("S46", (t1 - t0) / 1000, d.ev, t0, t1)
    saved.value.delete()
    d.leave(p)


# ---- community packs (Step 4.3k): the Patches tab's group opened (a list of one fixture pack, no pack ships: D997),
# its Install, its tick and a Build with it, the source a folder (the app) or the site's own address.
PACK = {"format": "azurkit-preset", "schema_version": 1, "layers": [
    {"tool": "mods", "kind": "packs", "recipe": {"enemy_scaling": {"enemy_damage_dealt_scale": 1.5},
                                                 "player_max_hp": {"starting_hp": 150}}},
    {"tool": "data", "kind": "xbr", "recipe": {"ops": [{"op": "set", "file": "gamedata/config.xbr", "table":
                                                        "critters_damage", "entity": "golem", "prop": "hitPoints",
                                                        "value": 321}]}}]}
PACK_ROW = """document.querySelector('.cpack[data-community="perf_hard"]')"""


def _pack_source(folder: Path) -> Path:
    """A content repository of the one fixture pack, in ``folder``."""
    text = json.dumps(PACK).encode()
    (folder / "packs/perf_hard").mkdir(parents=True, exist_ok=True)
    (folder / "packs/perf_hard/pack.json").write_bytes(text)
    (folder / "manifest.json").write_text(json.dumps({"format": "azurik-custom-content", "schema_version": 1, "entries": [
        {"id": "perf_hard", "kind": "pack", "title": "Perf Hard", "author": "AzurKit's tests", "licence": "MIT",
         "version": 1, "requires": [], "files": [{"path": "packs/perf_hard/pack.json", "size": len(text),
                                                  "sha256": hashlib.sha256(text).hexdigest()}]}]}), encoding="utf-8")
    return folder


def _community(d: Driver, p: Page, ops: tuple[str, str, str, str], url: str, pick: Callable[[], None]) -> None:
    listed, install, tick, build = ops
    d.act(p, listed, f"""() => {{ document.getElementById('community-group').open = true;
      const b = document.getElementById('community-source'); b.value = {json.dumps(url)};
      b.dispatchEvent(new Event('change')); }}""", f"() => {PACK_ROW}", 300)   # the source's one read: the group's first
    d.act(p, install, f"() => {PACK_ROW}.querySelector('button').click()",
          f"() => {PACK_ROW}?.querySelector('input') && !{PACK_ROW}.querySelector('input').disabled", 300)
    d.act(p, tick, f"() => {PACK_ROW}.querySelector('input').click()",
          """() => document.getElementById('player_max_hp.starting_hp').disabled""", 60, change=True)
    pick()
    d.act(p, build, build_js(), BUILT, 900)


def app_community(d: Driver, app: App, ctx) -> None:
    source = _pack_source(d.scratch / "pack-source")
    p = app.launch(d, ctx, None)
    _community(d, p, ("A33", "A34", "A35", "A36"), str(source),
               lambda: d.act(p, None, typed("iso-path", str(d.iso)), USA, change=True))
    app.quit(p)


def site_community(d: Driver, ctx, url: str) -> None:
    _pack_source(d.site / "perf-content")
    p = _site_page(d, ctx, url, None)
    _community(d, p, ("S26", "S27", "S28", "S29"), "./perf-content/", lambda: _pick(d, p, None))
    d.leave(p)


# ---- Replace files (Step 4.7d): a file of the size of the image's largest picked to replace it, then a Build with it.
def _replacement(d: Driver) -> tuple[str, Path]:
    """The image's largest file that may be replaced, and a file of its size, made once a run (no game bytes)."""
    from azurkit.core import gate
    name = max(gate.USA.files, key=lambda p: gate.USA.files[p][0])   # movies/Credits.bik
    made = d.scratch / "replacement.bin"
    if not made.is_file():
        made.write_bytes(os.urandom(1 << 20) * (gate.USA.files[name][0] >> 20) + os.urandom(gate.USA.files[name][0] & 0xFFFFF))
    return name, made


REPLACED = "() => /will be replaced/.test(document.getElementById('status').textContent) && 'held'"


def app_replace(d: Driver, app: App, ctx) -> None:
    name, made = _replacement(d)
    p = app.launch(d, ctx, None)
    d.act(p, None, typed("iso-path", str(d.iso)), USA)
    p.js(click("tab-tools"))
    p.js(f"""() => {{ document.getElementById('replace-path').value = {json.dumps(name)};
                     document.getElementById('replace-from').value = {json.dumps(str(made))}; }}""")
    d.act(p, "A62", click("replace-use"), REPLACED, 300, change=True)
    p.js(click("tab-patches"))
    d.act(p, "A63", build_js(), BUILT, 900)
    app.quit(p)


def site_replace(d: Driver, ctx, url: str) -> None:
    name, made = _replacement(d)
    p = _site_page(d, ctx, url, None)
    _pick(d, p, None)
    p.js(click("tab-tools"))
    p.js(f"() => {{ document.getElementById('replace-path').value = {json.dumps(name)}; }}")
    d.act(p, "S54", lambda: p.page.set_input_files("#replace-file", str(made)), REPLACED, 300, change=True)
    p.js(click("tab-patches"))
    d.act(p, "S55", build_js(), BUILT, 900)
    d.leave(p)


# ---- Saves (Step 4.7e): a synthetic slot and a two-slot qcow2 (tests/test_saves.py's builders; never a player's), read,
# one line edited and the slot saved; the signing's share is 3 ms by hand (it needs a player's BIOS files, no fixture).
def _save_fixtures(d: Driver) -> tuple[Path, Path]:
    from tests import test_saves as made

    folder, hdd = d.scratch / "save-slot" / made.ID, d.scratch / "hdd.qcow2"
    if not hdd.is_file():
        for path, data in made._files().items():
            (folder / path).parent.mkdir(parents=True, exist_ok=True)
            (folder / path).write_bytes(data)
        made._qcow2(hdd, made._Fatx({"UDATA": {"4d530007": {"TitleMeta.xbx": made.META, made.ID: made._slot_tree(1),
                                                            "FEDCBA987654": made._slot_tree(2)}}}).chunks())
    return folder, hdd


SLOT_READ = "() => azurkit.saves.state.slots.length >= 1 && !azurkit.saves.state.asking"
SAVE_LINE = """() => { const box = document.querySelector('#saves-rows input[data-file="magic.sav"]');
  box.value = '2.000000'; box.dispatchEvent(new Event('change', { bubbles: true })); }"""
SLOT_EDITED = "() => /changed: sign it again/.test(document.getElementById('status').textContent)"
SLOT_SAVED = "() => /^Saved /.test(document.getElementById('status').textContent)"


def app_saves(d: Driver, app: App, ctx) -> None:
    folder, hdd = _save_fixtures(d)
    p = app.launch(d, ctx, None)
    p.js(click("tab-tools"))
    p.js(f"() => {{ document.getElementById('saves-folder-path').value = {json.dumps(str(folder))}; }}")
    d.act(p, "A64", click("saves-open"), SLOT_READ, 300)
    p.js(f"() => {{ document.getElementById('saves-hdd-path').value = {json.dumps(str(hdd))}; }}")
    p.js("() => { azurkit.saves.state.slots = []; }")
    d.act(p, "A65", click("saves-read"), SLOT_READ, 300)
    t0, _ = d.act(p, None, SAVE_LINE, SLOT_EDITED, 300)
    _, t1 = d.act(p, None, click("saves-save"), SLOT_SAVED, 300)
    d.record("A66", (t1 - t0) / 1000, d.ev, t0, t1)
    app.quit(p)


def site_saves(d: Driver, ctx, url: str) -> None:
    folder, hdd = _save_fixtures(d)
    p = _site_page(d, ctx, url, None)
    p.js(click("tab-tools"))
    d.act(p, "S56", lambda: p.page.set_input_files("#saves-folder", str(folder)), SLOT_READ, 300)
    p.js("() => { azurkit.saves.state.slots = []; }")
    d.act(p, "S57", lambda: p.page.set_input_files("#saves-hdd", str(hdd)), SLOT_READ, 300)
    t0, _ = d.act(p, None, SAVE_LINE, SLOT_EDITED, 300)
    _, t1 = d.act(p, None, click("saves-save"), SLOT_SAVED, 300)
    d.record("S58", (t1 - t0) / 1000, d.ev, t0, t1)
    d.leave(p)


# ---- the Data tab (Step 4.7a): its first open (the index and the Player view, no image), a critter's view, the
# picker's search, critters_damage's grid, an edit committed and its Undo (each the engine's check or view again), a
# Build of the defaults and 100 data edits (the site's loaded in the Tools tab, the app's its remembered setup at the
# next launch) and a mods file of 1,000 loaded (the Tools tab's Load), each made once a run (untimed).
VIEWED = "() => !document.getElementById('data').hidden && azurkit.data?.state.answer"
CRITTERS = ("air_elemental", "golem")


def _view(kind: str, name: str | None = None) -> str:
    return (f"() => azurkit.data.state.answer?.{'name' if kind == 'table' else 'kind'} === "
            f"{json.dumps(name if kind == 'table' else kind)}" + (f" && azurkit.data.state.answer.name === "
                                                                  f"{json.dumps(name)}" if kind != "table" and name
                                                                  else ""))


def _views(label: str) -> str:   # one of the tab's views, by its button's label
    return (f"() => [...document.querySelectorAll('#data .views button')].find((b) => b.textContent === "
            f"{json.dumps(label)}).click()")


def _entry(name: str) -> str:   # a picker entry's click, the answer dropped first so the done-state waits for its own
    return (f"() => {{ azurkit.data.state.answer = null; "
            f"document.querySelector('#data .picker-entry[data-name={json.dumps(name)}]').click(); }}")


HP_EDIT = """(text) => { const td = [...document.querySelectorAll("#data td.cell")].find((n) => {
    const c = JSON.parse(n.dataset.cell); return c.ref[0] === "settings_foo" && c.name === "initial hp"; });
  azurkit.data.state.answer = null; td.click(); const box = td.querySelector("input"); box.value = text;
  box.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })); }"""
UNDO = """() => { azurkit.data.state.answer = null;
  [...document.querySelectorAll("#data .data-bar button")].find((b) => b.textContent === "Undo").click(); }"""
SEARCH = """(text) => { const box = document.querySelector("#data .picker-search input"); box.value = text;
  box.dispatchEvent(new Event("input")); }"""
MODS_FILE = """
import json, sys
from azurkit import sdk
grid = sdk.data({"what": "table", "table": "critters_damage"})
ops = [{"op": "set", "file": "gamedata/config.xbr", "table": "critters_damage", "entity": entity, "prop": prop,
        "value": value + 1} for c, entity in enumerate(grid["cols"]) if entity and grid["cols"].count(entity) == 1
       for r, prop in enumerate(grid["rows"][1:], 1)
       if prop and isinstance(value := grid["cells"][c][r], (int, float)) and grid["rows"].count(prop) == 1]
n, kind = int(sys.argv[1]), sys.argv[2]
assert len(ops) >= n, len(ops)
packs = {p["name"]: {} for p in sdk.catalog()["packs"] if p["default_on"]}
sys.stdout.write(sdk.mods_file({"recipe": {"packs": packs, "xbr": ops[:n]}})["text"] if kind == "mods"
                 else json.dumps({"ticked": list(packs), "values": {}, "xbr": ops[:n]}))
"""


def _data_mods(d: Driver, n: int, kind: str = "mods") -> Path:
    """A mods file (``kind`` mods) or a page's remembered setup (``setup``) of the packs on by default and ``n`` edits
    of critters_damage's number cells (each its vanilla value plus 1), made once a run."""
    mods = d.scratch / f"data {n} edits.{kind}.json"
    if not mods.is_file():
        done = subprocess.run([sys.executable, "-c", MODS_FILE, str(n), kind], cwd=ROOT, capture_output=True,
                              text=True, env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}, check=True,
                              timeout=600)
        mods.write_text(done.stdout, encoding="utf-8")
    return mods


def _data(d: Driver, p: Page, ops: tuple[str | None, ...], pick: Callable[[], None] | None) -> None:
    """The Data tab's ops in one page; with a Build op, ``pick`` picks the image (untimed) and the Tools tab loads a
    mods file of 100 edits before it. The Tools tab, whose Load reads the mods files, is opened first."""
    first, critter, search, grid, edit, undo, build, load = ops
    thousand = _data_mods(d, 1000)
    p.js(click("tab-tools"))
    d.act(p, first, click("tab-data"), f"() => ({VIEWED})() && ({_view('player')})()", 600)
    k = 0
    while d.need(edit) or d.need(undo):   # each edit another value, so the engine checks it and the view is asked again
        k += 1
        d.act(p, edit, HP_EDIT, f"() => azurkit.data.state.answer && azurkit.xbr[0]?.value === {300 + k}", 600,
              str(300 + k))
        d.act(p, undo, UNDO, "() => azurkit.data.state.answer && azurkit.xbr.length === 0", 600)
    p.js(_views("Critters"))
    p.wait(VIEWED)
    k = 0
    while d.need(critter):
        k += 1
        name = CRITTERS[k % 2]
        d.act(p, critter, _entry(name), _view("critter", name), 600)
    while d.need(search):
        d.act(p, search, SEARCH, "() => / of /.test(document.querySelector('#data .picker-search .note').textContent)",
              60, "elem")
        p.js(SEARCH, "")
    p.js(_views("All tables"))
    p.wait(VIEWED)
    while d.need(grid):
        p.js(_entry("magic"))
        p.wait(_view("table", "magic"))
        d.act(p, grid, _entry("critters_damage"), _view("table", "critters_damage"), 600)
    if build is not None and d.need(build):
        pick()
        p.js(click("tab-tools"))
        d.act(p, None, lambda: p.page.set_input_files("#tools-mods-file", str(_data_mods(d, 100))),
              f"() => azurkit.xbr.length === 100 || {ERROR}", 600, change=True)
        d.act(p, build, build_js(), BUILT, 1800)
        p.wait(READY, 600)   # the site's engine may be replaced after a build
    p.js(click("tab-data"))   # critters_damage's grid shown, whichever ops ran before: the load's view
    p.js(_views("All tables"))
    p.wait(VIEWED)
    p.js(_entry("critters_damage"))
    p.wait(_view("table", "critters_damage"))
    p.js(click("tab-tools"))
    d.act(p, load, lambda: p.page.set_input_files("#tools-mods-file", str(thousand)),
          "() => azurkit.xbr.length === 1000 && azurkit.data.state.answer?.name === 'critters_damage' "
          f"&& azurkit.data.state.answer.changed.length === 1000 || {ERROR}", 900)


def app_data(d: Driver, app: App, ctx) -> None:
    """A45 at a second launch, from its remembered setup: a Build right after the Tools tab opened would share the
    engine process with the randomizer's logic it reads ahead (from a checkout 1.1-2.8 s, against 0.12 s once read)."""
    p = app.launch(d, ctx, None)
    _data(d, p, ("A39", "A40", "A41", "A42", "A43", "A44", None, "A46"), None)
    app.quit(p)
    if not d.need("A45"):
        return
    config = app.home / "Library" / "Application Support" / "AzurKit" / "app.json"
    kept = json.loads(config.read_text(encoding="utf-8")) if config.is_file() else {}
    setup = json.loads(_data_mods(d, 100, "setup").read_text(encoding="utf-8"))
    config.write_text(json.dumps(kept | {"setup": setup}), encoding="utf-8")
    p = app.launch(d, ctx, None)
    p.wait("() => azurkit.ready && azurkit.xbr.length === 100", 600)
    d.act(p, None, typed("iso-path", str(d.iso)), USA, 900, change=True)
    d.act(p, "A45", build_js(), BUILT, 1800)
    app.quit(p)


def site_data(d: Driver, ctx, url: str) -> None:
    p = _site_page(d, ctx, url, None)
    _data(d, p, ("S32", "S33", "S34", "S35", "S36", "S37", "S38", "S39"), lambda: _pick(d, p, None))
    d.leave(p)


SCENARIOS = {   # name: (host, its ops, the driver)
    "app-start": ("app", ("A01", "A03", "A04", "A05", "A06", "A07", "A08", "A09", "A10", "A11"), app_start),
    "app-build": ("app", ("A12", "A13", "A14", "A15", "A16", "A17"), app_build),
    "app-community": ("app", ("A33", "A34", "A35", "A36"), app_community),
    "app-replace": ("app", ("A62", "A63"), app_replace),
    "app-saves": ("app", ("A64", "A65", "A66"), app_saves),
    "app-seed": ("app", ("A27", "A28", "A29", "A30"), app_seed),
    "app-track": ("app", ("A02", "A23", "A24", "A25", "A26", "A37", "A38"), app_track),
    "app-ahead-track": ("app", ("A56",), app_ahead_track),
    "app-ahead-build": ("app", ("A57",), app_ahead_build),
    "app-ahead-stale": ("app", ("A58",), app_ahead_stale),
    "app-shaped": ("app", (*SHAPED, "A75", "A76"), app_shaped),
    "app-booblord": ("app", ("A18", "A19", "A20", "A21", "A22"), app_booblord),
    "app-reshape": ("app", ("A31", "A32"), app_reshape),
    "app-reshape-pictures": ("app", ("A59", "A60", "A61"), app_reshape_pictures),
    "app-tools": ("app", ("A47", "A48", "A49", "A50", "A51", "A52", "A53", "A54", "A55"), app_tools),
    "app-data": ("app", ("A39", "A40", "A41", "A42", "A43", "A44", "A45", "A46"), app_data),
    "site-start": ("site", ("S01", "S02", "S03", "S04", "S05", "S06", "S08", "S10", "S11", "S14", "R14", "S49", "S16",
                             "S17"),
                   site_start),
    "site-community": ("site", ("S26", "S27", "S28", "S29"), site_community),
    "site-replace": ("site", ("S54", "S55"), site_replace),
    "site-saves": ("site", ("S56", "S57", "S58"), site_saves),
    "site-characters": ("site", ("S07", "S09", "S12", "S13"), site_characters),
    "site-reshape-pictures": ("site", ("S51", "S52", "S53"), site_reshape_pictures),
    "site-track": ("site", ("S18", "S19", "S20", "S21", "S22", "S23", "S25", "S30", "S31"), site_track),
    "site-seed": ("site", ("S24", "R24", "S50"), site_seed),
    "site-tools": ("site", ("S40", "S41", "S42", "S43", "S44", "S45", "S46", "S47", "S48"), site_tools),
    "site-data": ("site", ("S32", "S33", "S34", "S35", "S36", "S37", "S38", "S39"), site_data),
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
    python = web_tools.install(wheel, folder / "venv", wt, env)
    purelib = subprocess.run([python, "-I", "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"], env=env,
                             capture_output=True, text=True, check=True, timeout=600).stdout.strip()
    shutil.copytree(wt / "web", Path(purelib).parent / "web")
    return python


def drive(wt: Path, run: Run, targets: dict[str, int], iso: Path, content: Path | None, site: Path | None,
          python: str | None = None, passes: int = 7) -> dict:
    """``run``'s samples for ``targets`` (``{op: samples wanted}``): ``{"samples":
    {op: [{"s", "bar", "progress", "late_ms"[, "page"][, "gap_ms"][, "error"][, "cpu"][, "starved"][, "retook"]
    [, "steady", "resident"]}]},
    "native" (the engine reports its
    pages gave, :meth:`Driver.engine`), "memory_peak": bytes or None,
    "memory_shared" (another Playwright ran meanwhile), "wall_s", "log"}``. Each scenario holding a wanted op runs, in a fresh
    state each pass, until its ops have their samples (at most ``passes``). An app run serves the app from ``python``
    (:func:`venv`'s; else one made for this run)."""
    from playwright.sync_api import sync_playwright

    from scripts import web_tools
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(web_tools.browsers_dir(ROOT))
    if MARK not in os.environ.get("PATH", ""):   # the browsers inherit it; launchd's record of their processes keeps it
        os.environ["PATH"] = f"{MARK}{os.pathsep}{os.environ.get('PATH', '')}"
    t = time.monotonic()
    scratch = Path(tempfile.mkdtemp(prefix=f"azurkit-perf-{run.name}.", dir="/tmp"))
    d = Driver(run, targets, scratch, iso, content)
    d.site = site
    python = python or (venv(wt, scratch / "app") if run.host == "app" else None)
    current: list[App] = []
    before, shared = {(pid, started) for pid, _, comm, started in Memory.rows() if ".xpc/" in comm}, []

    def site_roots(rows):   # another Playwright driver alive: a new WebKit process may be its (said, not dropped)
        if any(comm.endswith("playwright/driver/node") and ppid != os.getpid() for _, ppid, comm, _ in rows):
            shared.append(True)
        return browser_pids(rows, before)
    roots = (lambda rows: [pid for app in current for pid in app.pid()]) if run.host == "app" else site_roots
    try:
        with sync_playwright() as pw, Memory(roots) as memory, \
                (served(site, run.lag) if run.host == "site" else contextlib.nullcontext()) as url:
            d.memory = None if run.lag else memory   # the lag run's reads wait by design: not a busy machine's waits
            engine = getattr(pw, run.browser)
            browser = engine.launch(headless=True, downloads_path=str(scratch)) if run.host == "app" else None
            for name, (host, ops, scenario) in SCENARIOS.items():
                if host != run.host:
                    continue
                for n in range(passes):
                    if not d.needed(ops):
                        break
                    d.ev, d.p, d.changed, d.gap = [], None, None, None
                    if content is None and (missing := [op for op in ops if OPS[op].content and d.need(op)]):
                        for op in missing:
                            d.record(op, 0.0, [], 0, 0, "needs a clone of Azurik-Custom-Content (perf.py --content)")
                    if browser:
                        profile, ctx = None, browser.new_context(accept_downloads=True)
                    else:   # the site's in a persistent context on a new folder: an ephemeral one is WebKit's 1 GiB
                        profile = Path(tempfile.mkdtemp(prefix=f"profile-{name}-{n}.", dir=scratch))   # with no OPFS
                        ctx = engine.launch_persistent_context(str(profile), headless=True, accept_downloads=True,
                                                               downloads_path=str(scratch))
                    ctx.add_init_script(INIT)
                    try:
                        if run.host == "app":
                            current[:] = [App(python, scratch / f"home-{name}-{n}", run, content)]
                            scenario(d, current[0], ctx)
                        else:
                            scenario(d, ctx, url)
                        d.over()
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
                        if profile:
                            shutil.rmtree(profile, ignore_errors=True)
            if browser:
                browser.close()
            d.finish()
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return {"samples": d.samples, "native": d.native, "memory_peak": memory.peak if run.memory else None,
            "memory_shared": bool(shared), "wall_s": round(time.monotonic() - t, 1), "log": d.log}
