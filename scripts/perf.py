"""perf: the perf gate (D980-D985): every player-facing operation timed in
the app and on the site, each against its tier's line (D981, D1244: 3 s for
what players do often, 10 s for what they rarely do; a Check's and a new
shape's bound past a moving bar), the over-budget ones against their
ceilings in ``tests/perf_ceilings.toml``, a list that only shrinks.

    uv run --locked python scripts/perf.py WORKTREE [--select HOST:GROUP,..] [--base REF] [--all]
                                           [--profiles P,..] [--browsers B,..] [--ops ID,..]
                                           [--update-ceilings] [--json FILE] [--keep DIR] [--content CLONE]
                                           [--repeats N] [--reference META]

What it times: ``tests/_perf.py``'s registry (``A01``-``A30`` the app's,
``S01``-``S25`` the site's), the ops of the groups the worktree's changes
reach (:func:`select`: ``--base``, default main; or ``--select``; ``--all``
every op), in the profiles named: ``app`` (the app's serve mode from the
worktree's wheel in a scratch venv, so it reads the database the wheel ships
as players get it, with a fresh HOME, its page in WebKit), ``site`` (the site
built from the same wheel and served on 127.0.0.1, in each of
``--browsers``), ``lag`` (the site in WebKit with each File read 200 ms
late, Safari's read model) and ``capped`` (the app with ``AZURKIT_CORES=4``
and the site in WebKit, against 9 s, with our processes' peak resident size
at most 6 GiB). Default: ``app`` and ``site`` in WebKit (a changed area's);
``--all`` every profile and browser (:data:`BROWSERS`: WebKit, Chromium and
Firefox, D994; main's full runs). Firefox's run logs its tree's peak resident
size (``tree_peaks``); no verdict reads it.

The verdicts (:func:`judge`): each op runs :data:`R` times (an op with a
sample over 30 s once), first-time ops each in a fresh state, and its median
decides; a changed area's run (``--select``, ``--base``: not ``--all``, main's
and the release's reference) times an op once, and only an op whose first
sample is at or past 1 s or froze takes the rest (:func:`alone`, D1215: one
under 1 s can't fail on time or progress), the block's ``one_sample`` naming
the cases that took one. Timings are advisory (D1170): an op over its budget (an unlisted
one, or a listed one over its ceiling), one whose median passes 1 s with no
progress shown, or one a sample of which froze in a gap (``_perf.FREEZE_MS``)
is a perf-debt row (the block's ``debt``, :func:`debt_rows`; a Save's with
the free disk its run left), which fails nothing, and so is an op the last
release never measured (none in ``--reference``) that errors, with its error.
The tiers (D1244, ``_perf.Op.tier`` and ``heavy``): an op's budget is its
tier's line (:func:`budget_of`: :data:`BUDGET` for what players do often,
:data:`RARE` for what they rarely do; a first-time op keeps 3 s in either);
a heavy op (a dress's work the page asks for: a Check, a new shape's first
build or pictures) passes that line only with a moving bar, as D982's do, and
past its bound (:func:`bound_of`, :data:`HEAVY`) its verdict is ``beyond``,
a debt row too.
A run fails only on a clear regression against the last release
(:func:`blocking`): with ``--reference`` (a receipt of the last release's run,
``scripts/fullsuite.py``'s ``release_reference``), an op whose median is over
its budget and over that run's for the same op and context by more than both
:data:`REGRESSION` of it and :data:`REGRESSION_S` runs :data:`R` more times
(one more past 30 s) and fails (``slower``) if the median of all of them still
is (an op within its budget never fails on time), and an op that run measured
that errors; and on a memory peak, a native failure or a list that grows, as
before. Like with like (Step 4.47d): the driver tags each sample with its
place (``first_on_page``: its op's first on its page or app run, as a cold
Check is, or a later one there), and each place is judged against the
release's same place (:func:`reference_of` reads an untagged release's as it
took them), so how many of an op's samples were a page's first moves no
verdict; the re-run then leaves each place :data:`R` samples at least.
The release's tree beside (Step 4.47e): an op that reads slower than that run
has the release's own commit (the receipt's ``head``: a ``git archive`` of
it, its wheel, site and app built as the worktree's) timed beside it in the
same stage, page for page, the two sides alternating (:func:`pair`, in
place of the re-run), and its regression verdict holds the head's samples
taken there to the release's taken there, each place to its own (the
case's ``beside``), the same line: over its budget and over the release's
by more than both :data:`REGRESSION` and :data:`REGRESSION_S`; one still
slower after :data:`R` pages a side takes R more, and is judged on all of
them. The receipt's verdict stands where the release's tree can't be built
or driven (its ``beside`` says why). The box a gate runs on moves through
an hour (a Save's sample is the browser's write of a 2.8 GB download; a
Check's, the cores a nice-10 process gets), so only the release timed in
the same minutes tells a slower product from a busier box; nothing of the
release's side enters the native check, a memory peak or ``--keep``.
D982's first-time ops
(an image's first identity check, the site's first engine load) may pass
their budget only with a moving bar (the progress element seen at 2 or more
values). An op whose median passes 1 s shows progress (a bar or a
"k of n" / "N %" line changing at least once, D980) unless it is one of the
list's progress debts; a download (an op's ``browser_bar``: the browser writes
the file the page handed it, shown by its own download indicator) shows it
when each sample's page part, the click to the download's start, is within
1 s or moved the page's own bar. The list itself fails when it adds an op or
a debt or raises a ceiling against main's (:func:`check_list`), but for a
browser main's perf.py doesn't time (:func:`new_browsers`), whose first
record may add its own ops and debts once; it fails too for a stack that
moves an op main holds frequent to the rare tier, drops a heavy op's bound,
raises a line or loses the tiers (D1244, :func:`check_tiers`), but against a
main with no tiers, the owner's first record. A run whose engine answers without the compiled kernels' library
the worktree ships for its host
(:func:`native_failures`: its pages' ``sdk.catalog`` ``native``, loaded,
that library, those bytes, and as each page leaves no reach call its twin
answered) fails, its ops with it, so a time the Python twins took is never
a sample or a ceiling.

``--update-ceilings`` rewrites the list from this run (:func:`updated`): it
lowers a ceiling to the new median x 1.15 (rounded up to 0.1 s) and drops an
op back under its budget and a debt that now shows progress; with no list on
main (its first record), and for a browser new to main, it records every
over-budget op and every debt as measured (no re-run).
``--json FILE`` writes the result (``scripts/fullsuite.py``'s receipt block).
``--keep DIR`` keeps each run's samples there and reuses them, so a stopped
run resumes. Exit 0 passed, 1 failed, 2 can't run. No game bytes printed.
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import hashlib
import json
import math
import os
import re
import shutil
import signal
import statistics
import subprocess
import sys
import time
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CEILINGS = "tests/perf_ceilings.toml"
BUDGET = 3.0          # D981: a player-facing op's seconds on this Mac (D1244: what players do often)
RARE = 10.0           # D1244: a rarely used op's line (``_perf.Op.tier``)
CAPPED = 9.0          # D984: the capped profile's: three times each line (:func:`budget_of`, :func:`bound_of`)
#: D1194, D1244: a heavy op (``_perf.Op.heavy``: a dress's work the page asks for, a Check or a new shape's first
#: build or pictures) passes its tier's line only with a moving bar, and past this bound, by tier and host, is a debt
#: row (``beyond``); a browser's rare bound is D1244's 90 s at most
HEAVY = {"frequent": {"app": 15.0, "site": 30.0}, "rare": {"app": 45.0, "site": 90.0}}
PROGRESS = 1.0        # D980: an op past this shows progress
MEMORY = 6 * 2**30    # the capped profile's peak resident size
R = 3                 # samples an op (the median decides)
LONG = 30.0           # an op past this runs once, and once more on a re-run
MARGIN = 1.15         # a ceiling is the median times this, rounded up to 0.1 s
REGRESSION = 0.25     # D1170: a clear regression: the median over the last release's run's by more than this share of it
REGRESSION_S = 0.5    # and by more than these seconds (both)
DEBTS = ("listed", "over", "regressed", "no progress", "beyond")   # D1170: the verdicts that are perf-debt rows
#: A sample's place (Step 4.47d), as the driver tags it (``first_on_page``): its op's first on its page (a site page or
#: an app run: a cold Check, a first preview) or a later one there; the regression verdict judges each against its own
PLACES = {"first": "its first sample on a page", "later": "its later samples there"}
LOAD_LINE = 40.0      # D926/D975: the gate's perf stage starts under this normal-priority load
STOPPED = 143         # the exit a SIGTERM gives (main's handler): a stopped run still deletes its scratch
PROFILES = ("app", "site", "lag", "capped")
BROWSERS = ("webkit", "chromium", "firefox")   # the site's (D994: Firefox)
#: The groups the Tracker's modules and pictures reach: app.mjs imports tracker.mjs (and through it art.mjs and
#: mapview.mjs) and makes the tracker as the page starts, index.html loads art/icons.css and sw.js keeps art/ at its
#: install (start); each image chosen asks the tracker to draw its maps (image); a seed's build opens its plan in the
#: tracker and the Randomizer tab's items show art/'s icons (randomizer). No build or characters op calls it.
TRACKED = ("start", "image", "randomizer", "tracker")
#: Which ops a changed path reaches (section 2.4 of round 1's plan): ``(prefix, hosts, groups)``, the first match;
#: an unlisted path under ``src/`` or ``web/`` reaches every op, and so does the perf gate's own driver (``_perf``
#: and the page calls it makes, ``_page``) and judge (this file), whose fault can reach any op (Step 4.46a); any other
#: path none. A narrower row stands on what
#: loads its path (Step 4.43a): ``_stacks.py`` is imported by the app's processes alone (``__main__``, ``app`` and
#: ``app.engine``), and ``parts.mjs`` by the site's engine worker alone (worker.mjs: its start), whose Check with
#: game data alone calls it. characters.mjs and variants.mjs stay every op: every build, the work ahead and each
#: image chosen ask them.
REACH = (*((path, ("app", "site"), None) for path in ("tests/_perf.py", "tests/_page.py", "scripts/perf.py")),
         ("src/azurkit/app/", ("app",), None), ("src/azurkit/__main__.py", ("app",), None),
         ("src/azurkit/_stacks.py", ("app",), None),
         ("src/azurkit/tools/randomizer/", ("app", "site"), ("randomizer", "tracker")),
         ("src/azurkit/tools/characters/", ("app", "site"), ("characters", "build")),
         ("src/", ("app", "site"), None),
         *((path, ("app", "site"), TRACKED) for path in ("web/tracker.mjs", "web/mapview.mjs", "web/art.mjs", "web/art/")),
         ("web/parts.mjs", ("site",), ("start", "characters")),
         ("web/", ("app", "site"), None), ("scripts/web_tools.py", ("site",), None))
GROUPS = ("start", "image", "build", "characters", "randomizer", "tracker")   # tests/_perf.py's
NATIVE = "src/azurkit/core/_native"   # the compiled kernels' libraries a worktree ships (core/native.py)
SIDE_MODULE = "emscripten-wasm32.so"  # the site's (its Pyodide's); the app's is this machine's, core.native.target()
#: What of the release's commit its tree beside is made from (Step 4.47e): the wheel's inputs (``web_tools.wheel``'s
#: key), the site's ``web/``, the lock its app's venv installs from and the ``web_tools.py`` that builds all three
#: (:func:`tools_of`), so a lane's change there is timed as the head's alone
RELEASE_TREE = ("src", "web", "pyproject.toml", "uv.lock", "README.md", "LICENSE", "NOTICE.md", "scripts/web_tools.py")


def select(paths: list[str]) -> set[tuple[str, str]]:
    """The ``(host, group)`` pairs the changed ``paths`` reach (:data:`REACH`)."""
    pairs = set()
    for rel in paths:
        if hit := next((rule for rule in REACH if rel == rule[0] or rule[0].endswith("/") and rel.startswith(rule[0])),
                       None):
            pairs |= {(host, group) for host in hit[1] for group in hit[2] or GROUPS}
    return pairs


def contexts(profiles, browsers) -> list[str]:
    """The judged contexts: ``app``, each browser of the site, ``lag``, ``capped``."""
    out = []
    for profile in profiles:
        out += ["app"] if profile == "app" else list(browsers) if profile == "site" else [profile]
    return out


def run_of(op: str, context: str) -> str:
    """The run (``tests/_perf.py`` RUNS) whose samples judge ``op`` in ``context``."""
    if context == "capped":
        return "app-capped" if op.startswith("A") else "webkit"
    return context


def budget_of(context: str, tier: str = "frequent") -> float:
    """An op's line in ``context`` (D981, D1244): :data:`BUDGET`, a rare op's :data:`RARE`; the capped profile's three
    times each (D984)."""
    line = RARE if tier == "rare" else BUDGET
    return line * CAPPED / BUDGET if context == "capped" else line


def bound_of(op: str, context: str, tier: str = "frequent") -> float:
    """A heavy op's bound in ``context`` (:data:`HEAVY`, D1244): its tier's for its host (an ``A`` op's the app's, the
    site's in each browser and the lag profile), the capped profile's three times."""
    line = HEAVY[tier]["app" if op.startswith("A") else "site"]
    return line * CAPPED / BUDGET if context == "capped" else line


def tiered(ops) -> tuple[set[str], set[str]]:
    """``(rare, heavy)``: the ids of ``ops`` (``_perf.Op``) judged at the rare line and the heavy ones (D1244); a
    first-time op (a bar op that isn't heavy: D982, D1008) keeps 3 s in either tier, as it stood."""
    return ({op.id for op in ops if op.tier == "rare" and (op.heavy or not op.bar)},
            {op.id for op in ops if op.heavy})


def ceil(seconds: float) -> float:
    """A ceiling: ``seconds`` x :data:`MARGIN`, rounded up to 0.1 s."""
    return math.ceil(round(seconds * MARGIN * 10, 6)) / 10


def placed(samples: list[dict]) -> dict[str, list[float]] | None:
    """Each place's seconds (:data:`PLACES`) from the driver's ``first_on_page`` tags, or None when a sample has none
    (an older driver's)."""
    if not samples or any("first_on_page" not in s for s in samples):
        return None
    out: dict[str, list[float]] = {}
    for s in samples:
        out.setdefault("first" if s["first_on_page"] else "later", []).append(s["s"])
    return out


def reference_of(case: dict, op=None) -> dict:
    """An op's reference from the last release's case (Step 4.47d): its median and each place's
    (:data:`PLACES`); a case whose samples carry no place (an older perf.py's) is read as the release took them,
    :data:`R` to a page with the first there first, and each its own page's for an op of fresh states
    (``_perf.Op.first``)."""
    seconds = case.get("samples") or []
    firsts = case.get("first_on_page") or [op is None or op.first or i % R == 0 for i in range(len(seconds))]
    at = placed([{"s": s, "first_on_page": f} for s, f in zip(seconds, firsts)]) or {}
    return {"median": case["median"], "places": {p: round(statistics.median(v), 3) for p, v in at.items()}}


def regression(median: float, reference: float | None, budget: float) -> bool:
    """D1170's clear regression: ``median`` over its ``budget`` and over ``reference`` by more than both
    :data:`REGRESSION` of it and :data:`REGRESSION_S`."""
    return (reference is not None and median > budget and median > reference * (1 + REGRESSION)
            and median - reference > REGRESSION_S)


def judge(samples: list[dict], budget: float, ceiling: float | None = None, debt: bool = False,
          bar: bool = False, browser_bar: bool = False, reference: float | dict | None = None,
          beside: dict | None = None, bound: float | None = None, rare: bool = False) -> dict:
    """One op's verdict in one context from its samples (``{"s", "bar",
    "progress"[, "page"][, "froze"][, "error"]}``): ``pass``, ``listed`` (over its
    budget, within its ceiling), ``bar`` (D982: over 3 s with a moving bar), ``over``
    (unlisted, over its budget), ``regressed`` (over its
    ceiling), ``no progress`` (past 1 s with none shown and not a debt) and
    ``error``; a heavy op's (D1244: a ``bound``, :func:`bound_of`) ``bar``,
    ``listed`` or ``over`` whose median passes its bound is ``beyond``.
    Its ``debt`` (D1170): a verdict of :data:`DEBTS` or a sample
    whose page froze in a gap (the case's ``froze``), and an error with no
    ``reference`` (an op the last release never measured), a perf-debt row
    that fails nothing; ``ok`` is false only as :func:`blocks` says: an error
    on an op with a ``reference`` median (the last release's run's), or
    ``slower``: its median over its ``budget`` and over that one by more
    than both :data:`REGRESSION` of it and :data:`REGRESSION_S`
    (:func:`regression`): a frequent op's budget, a ``rare`` one's line
    (its budget, or its bound for a heavy one), so a rare op blocks only as a
    clear regression past it. Like with like (Step 4.47d): with a ``reference``
    of places (:func:`reference_of`) and samples the driver placed
    (:func:`placed`), each place both hold is judged so on its own median
    (the case's ``places``), and the op is ``slower`` when one is, so how
    many of its samples were a page's first can't move the verdict.
    The release's tree beside (Step 4.47e): with ``beside`` (:func:`pair`:
    ``{"head": {place: seconds}, "release": {place: seconds}}``, the two
    sides' samples taken page for page in one stage), ``slower`` is
    :func:`regression` of the head's median there against the release's
    there, each place both hold on its own (the case's ``beside`` gains
    their ``places`` and ``slower``); everything else, ``places`` against
    the stored reference too, is judged on all the samples as before. A
    ``beside`` of ``{"error"}`` (the release's tree unbuilt or undriven)
    leaves the stored reference's verdict standing, and the case says why.
    A ``browser_bar`` op's sample (a download) shows progress when
    its page part, ``"page"``, is within 1 s: the browser's own bar shows its
    write; the case keeps the page parts. A sample the driver tagged
    ``starved`` (it waited for a core, ``_perf.starved``) is named in the
    case; no verdict reads it."""
    seconds = [s["s"] for s in samples]
    whole = reference.get("median") if isinstance(reference, dict) else reference
    line = bound if rare and bound is not None else budget   # D1244: the regression's line
    out = {"n": len(samples), "budget": budget, "ceiling": ceiling, "samples": seconds, "reference": whole}
    if bound is not None:
        out["bound"] = bound
    if line != budget:
        out["line"] = line
    if (at := placed(samples)) is not None:
        out["first_on_page"] = [s["first_on_page"] for s in samples]
    if browser_bar:
        out["page"] = [s.get("page") for s in samples]
    if (errors := [s["error"] for s in samples if s.get("error")]) or not samples:
        out |= {"verdict": "error", "slower": False, "debt": whole is None,
                "error": errors[-1] if errors else "no sample"}
        return out | {"ok": not blocks(out)}
    median = statistics.median(seconds)
    over = [s for s in samples if s["s"] > budget]
    moved = bool(over) and all(s["bar"] >= 2 for s in over)
    shown = all(s["progress"] or browser_bar and s.get("page", math.inf) <= PROGRESS
                for s in samples if s["s"] > PROGRESS)
    out |= {"median": round(median, 3), "spread": round(max(seconds) - min(seconds), 3), "progress": shown,
            "moved": moved}
    if starved := [s["s"] for s in samples if s.get("starved")]:
        out["starved"] = starved
    if ceiling is not None and median > ceiling:
        verdict = "regressed"
    elif median > budget:
        verdict = "bar" if bar and moved else "listed" if ceiling is not None else "over"   # D982 before the list
    else:
        verdict = "pass"
    if bound is not None and verdict in ("bar", "listed", "over") and median > bound:
        verdict = "beyond"   # D1244: past its tier's bound
    if verdict in ("pass", "listed", "bar") and median > PROGRESS and not shown and not debt:
        verdict = "no progress"
    if froze := [s["froze"] for s in samples if s.get("froze")]:
        out["froze"] = froze
    theirs = reference.get("places") if isinstance(reference, dict) else None
    if at and theirs and (both := [p for p in PLACES if p in at and p in theirs]):
        out["places"] = {p: {"median": round(statistics.median(at[p]), 3), "reference": theirs[p],
                             "slower": regression(statistics.median(at[p]), theirs[p], line)} for p in both}
        slower = any(v["slower"] for v in out["places"].values())
    else:
        slower = regression(median, whole, line)
    if beside is not None:
        out["beside"] = dict(beside)
        both = [p for p in (*PLACES, "all") if beside.get("head", {}).get(p) and beside.get("release", {}).get(p)]
        if both and "error" not in beside:
            out["beside"]["places"] = {p: {"head": round(statistics.median(beside["head"][p]), 3),
                                           "release": round(statistics.median(beside["release"][p]), 3)} for p in both}
            for v in out["beside"]["places"].values():
                v["slower"] = regression(v["head"], v["release"], line)
            slower = out["beside"]["slower"] = any(v["slower"] for v in out["beside"]["places"].values())
    return out | {"verdict": verdict, "ok": not slower, "slower": slower, "debt": verdict in DEBTS or bool(froze)}


def blocks(case: dict) -> bool:
    """Whether a case's verdict blocks (D1170): a clear regression against the last release's run, an op ``slower``
    than its median there, or one it measured (a ``reference``) that errors. An error row with no ``reference`` key
    (an older perf.py's, whose judge returned before it set one) blocks too: only a ``None`` reference is debt."""
    return bool(case.get("slower")) or case.get("verdict") == "error" and case.get("reference", 0) is not None


def blocking(block: dict | None) -> list[str]:
    """What in a perf block blocks a landing (D1170): its cases :func:`blocks` names, a memory peak over its line, a
    native failure and a list that grows; a block with no cases (its stage never ran) blocks on its own failures. The
    rest, an op over its budget, past 1 s with no progress, frozen in a gap or new to the release and erring, is
    debt (:func:`debt_rows`)."""
    if not block:
        return ["no perf block"]
    if block.get("deferred"):
        return ["its perf stage is deferred to its batch's (fullsuite.py --perf-later, D1215)"]
    if "cases" not in block:
        return [] if block.get("passed") is True else list(block.get("failures") or ["no perf verdicts"])
    def stored(r: dict, p: str) -> float | None:   # the receipt's figure for a place
        return r.get("places", {}).get(p, {}).get("reference", r.get("reference"))
    out = ["; ".join(f"{k}: slower than the release's tree timed beside it ({v['head']} s against {v['release']} s"
                     f" at {PLACES.get(p, 'every sample')}, over its {r.get('line', r['budget'])} s budget and the "
                     f"release's by "
                     f"{REGRESSION:.0%} and {REGRESSION_S} s: D1170; its receipt: {stored(r, p)} s)"
                     for p, v in r["beside"]["places"].items() if v["slower"])
           if r.get("slower") and (r.get("beside") or {}).get("slower")
           else "; ".join(f"{k}: slower than the release's {v['reference']} s" + (f" at {PLACES[p]}" if p else "")
                          + f" ({v['median']} s, over its {r.get('line', r['budget'])} s budget and the release's by "
                          f"{REGRESSION:.0%}"
                          f" and {REGRESSION_S} s: D1170)"
                          + (f"; the release's tree beside it: {r['beside']['error']}"
                             if (r.get("beside") or {}).get("error") else "")
                          for p, v in [(p, v) for p, v in r.get("places", {}).items() if v["slower"]] or [(None, r)])
           if r.get("slower")
           else f"{k}: error ({r.get('error')}), " + (f"an op the release measured ({r['reference']} s)"
                                                       if "reference" in r else "judged by an older perf.py")
           for k, r in block["cases"].items() if blocks(r)]
    out += [f"memory {k}: {v['peak'] / 2**30:.2f} GiB" for k, v in block.get("memory", {}).items() if not v["ok"]]
    return out + list(block.get("native_failures", [])) + list(block.get("list", []))


def shipped(wt: Path, library: str | None) -> tuple[str | None, str | None]:
    """(``library``, the sha256[:12] of the worktree's copy, or None when it ships none)."""
    path = wt / NATIVE / library if library else None
    return library, hashlib.sha256(path.read_bytes()).hexdigest()[:12] if path and path.is_file() else None


def native_failures(natives: dict[str, list], want: dict[str, tuple[str | None, str | None]]) -> list[str]:
    """A failure for each run (``{run: the engine reports its pages gave}``)
    with no report or one whose engine answered without the library the
    worktree ships for its host (``want``: ``{run: (library, sha256[:12])}``,
    :func:`shipped`), loaded, with those bytes, or whose Python twin answered
    any reach call (``calls``: a per-call fallback, or an engine process that
    loads apart from its server), or that holds no count: a time its twins
    took is never a sample or a ceiling."""
    out = []
    for run, reports in sorted(natives.items()):
        library, sha12 = want[run]
        if not reports:
            out.append(f"native {run}: its engine reported no compiled kernels")
        for r in reports:
            r = r or {}
            if not (r.get("loaded") and (r.get("library"), r.get("sha12")) == (library, sha12) and sha12):
                out.append(f"native {run}: the engine ran {r.get('library') or 'no library'} "
                           f"({r.get('sha12') or r.get('why')}), not the shipped {library} ({sha12})")
            elif twin := (r.get("calls") or {}).get("twin", "an unknown count"):
                out.append(f"native {run}: its Python twin answered {twin} of the engine's reach calls")
    return out


def key(op: str, context: str) -> str:
    return f"{op}/{context}"


def listed(text: str | None) -> dict:
    """``tests/perf_ceilings.toml``'s ``{"ceilings": {key: s}, "debts": [key],
    "memory": {run: bytes}, "untimed": {op: why}}`` (all empty for none)."""
    data = tomllib.loads(text) if text else {}
    return {"ceilings": dict(data.get("ceilings", {})), "debts": list(data.get("debts", {}).get("keys", [])),
            "memory": {k: int(v * 2**30) for k, v in data.get("memory", {}).items()},
            "untimed": dict(data.get("untimed", {}))}


def render(lst: dict) -> str:
    """The list as ``tests/perf_ceilings.toml``."""
    order = lambda k: (k.split("/")[0], k)   # noqa: E731
    lines = ["# The perf gate's list (scripts/perf.py; D980-D985): each op still over its line (3 s, a rare op's 10 s,",
             "# D1244; the capped profile's three times) with its ceiling, the median x 1.15 rounded up to 0.1 s, as",
             "# \"<op>/<context>\"",
             "# (tests/_perf.py's ids; app, webkit, chromium, lag, capped); the ops past 1 s that show no progress",
             "# yet (D980); the capped profile's peak memory over 6 GiB; the ops the gate can't time. It only",
             "# shrinks: `perf.py --update-ceilings` lowers and drops, and the gate fails an added op, debt or a",
             "# raised ceiling against main's. Over its budget, an op is a perf-debt row too (D1170).", "",
             "[ceilings]"]
    lines += [f'"{k}" = {lst["ceilings"][k]}' for k in sorted(lst["ceilings"], key=order)]
    lines += ["", "[debts]", "keys = ["]
    lines += [f'    "{k}",' for k in sorted(lst["debts"], key=order)]
    lines += ["]", "", "[memory]   # GiB"]
    lines += [f'"{k}" = {math.ceil(v / 2**30 * 10) / 10}' for k, v in sorted(lst["memory"].items())]
    lines += ["", "[untimed]"]
    lines += [f'{k} = {json.dumps(v)}' for k, v in sorted(lst["untimed"].items())]
    return "\n".join(lines) + "\n"


def context_of(k: str) -> str:
    return k.rpartition("/")[2]


def browsers_of(source: str | None) -> tuple[str, ...]:
    """The :data:`BROWSERS` a perf.py's ``source`` names (``()`` for none)."""
    for node in ast.parse(source or "").body:
        if isinstance(node, ast.Assign) and any(getattr(n, "id", None) == "BROWSERS" for n in node.targets):
            return tuple(ast.literal_eval(node.value))
    return ()


def new_browsers(repo: Path, base: str | None, head: str) -> set[str]:
    """The browsers ``head``'s perf.py times that ``base``'s doesn't (none
    when ``base`` has no perf.py): each gets one first record (D994)."""
    if base is None or (old := _git(repo, "show", f"{base}:scripts/perf.py")) is None:
        return set()
    return set(browsers_of(_git(repo, "show", f"{head}:scripts/perf.py"))) - set(browsers_of(old))


def tiering(perf_source: str | None, registry_source: str | None) -> dict | None:
    """The tiers a ``tests/_perf.py`` holds and the lines its ``scripts/perf.py`` does (D1244), read with ``ast``:
    ``{"tiers": {op: tier}, "heavy": [op, ...], "lines": {name: seconds}}``, the lines the capped profile derives
    from them (``RARE capped``, ``HEAVY rare site capped``: :func:`budget_of`, :func:`bound_of`) among them; None
    for a registry whose ``Op`` has no ``tier`` (before D1244's first record)."""
    try:
        tree, script = ast.parse(registry_source or ""), ast.parse(perf_source or "")
    except SyntaxError:
        return None
    op = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Op"), None)
    fields = {n.target.id: n.value for n in (op.body if op else ()) if isinstance(n, ast.AnnAssign)
              and isinstance(n.target, ast.Name)}
    if "tier" not in fields:
        return None
    default = {f: ast.literal_eval(v) if v is not None else None for f, v in fields.items() if f in ("tier", "heavy")}
    tiers, heavy = {}, []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Op" and node.args
                and isinstance(node.args[0], ast.Constant)):
            given = {k.arg: ast.literal_eval(k.value) for k in node.keywords if k.arg in default}
            tiers[node.args[0].value] = given.get("tier", default["tier"])
            if given.get("heavy", default.get("heavy")):
                heavy.append(node.args[0].value)
    lines = {}
    for node in script.body:
        for name in (getattr(t, "id", None) for t in getattr(node, "targets", ())):
            if name in ("BUDGET", "RARE", "CAPPED"):
                lines[name] = ast.literal_eval(node.value)
            elif name == "HEAVY":
                lines |= {f"HEAVY {tier} {host}": v for tier, hosts in ast.literal_eval(node.value).items()
                          for host, v in hosts.items()}
    if lines.get("BUDGET") and "CAPPED" in lines:   # the capped profile's three times each: a lowered BUDGET raises it
        lines |= {f"{name} capped": round(v * lines["CAPPED"] / lines["BUDGET"], 6) for name, v in list(lines.items())
                  if name == "RARE" or name.startswith("HEAVY ")}
    return {"tiers": tiers, "heavy": sorted(heavy), "lines": lines}


def tiering_at(repo: Path, rev: str | None) -> dict | None:
    """``rev``'s :func:`tiering` (None for no ``rev``)."""
    return None if rev is None else tiering(_git(repo, "show", f"{rev}:scripts/perf.py"),
                                            _git(repo, "show", f"{rev}:tests/_perf.py"))


def check_tiers(mine: dict | None, main: dict | None) -> list[str]:
    """What the head's tiers loosen against main's (D1244, :func:`tiering`): an op main holds at the frequent tier
    moved to the rare one, an op main holds heavy no longer heavy (its bound gone), a line raised (the capped
    profile's too), or the registry's tiers gone. None against a main whose registry has no tiers: that first record
    is the owner's tiering (D1244); a later move needs an owner's decision and a change here that lets it through
    once, as a browser's first record has :func:`new_browsers`. A new op may start at either tier."""
    if not main:
        return []
    if not mine:
        return ["the registry's tiers: gone against main's (D1244)"]
    bad = [f"{op}: moved to the rare tier against main's (D1244: an owner's decision)"
           for op, tier in sorted(mine["tiers"].items()) if tier == "rare" and main["tiers"].get(op, "rare") != "rare"]
    bad += [f"{op}: no longer heavy against main's (D1244: its bound)"
            for op in sorted(set(main.get("heavy", ())) & (set(mine["tiers"]) - set(mine["heavy"])))]
    return bad + [f"{name}: raised against main's, {main['lines'][name]} -> {v} s (D1244)"
                  for name, v in sorted(mine["lines"].items()) if v > main["lines"].get(name, v)]


def check_list(mine: dict, main: dict | None, new: frozenset[str] | set[str] = frozenset(),
               tiers: tuple[dict | None, dict | None] = (None, None)) -> list[str]:
    """What the worktree's list adds or raises against main's: none on the
    first record (no list on main), and none of a context in ``new`` (a
    browser main's perf.py doesn't time: its first record); and what its
    ``tiers`` (the head's and main's :func:`tiering`) loosen (:func:`check_tiers`)."""
    bad = check_tiers(*tiers)
    if main is None:
        return bad
    old = [k for k in mine["ceilings"] if context_of(k) not in new]
    bad += [f"{k}: added to the list (ceiling {mine['ceilings'][k]} s)" for k in old if k not in main["ceilings"]]
    bad += [f"{k}: its ceiling raised, {main['ceilings'][k]} -> {v} s" for k, v in mine["ceilings"].items()
            if k in main["ceilings"] and v > main["ceilings"][k]]
    bad += [f"{k}: a new progress debt" for k in mine["debts"] if k not in main["debts"] and context_of(k) not in new]
    bad += [f"memory {k}: added or raised" for k, v in mine["memory"].items() if v > main["memory"].get(k, -1)]
    bad += [f"{k}: newly untimed" for k in mine["untimed"] if k not in main["untimed"]]
    return bad


def updated(lst: dict, results: dict, memory: dict, first: bool, new: frozenset[str] | set[str] = frozenset()) -> dict:
    """The list after this run: a measured ceiling lowered to its median's
    (:func:`ceil`) or dropped once under its budget, a debt dropped once it
    shows progress or stays under 1 s, a memory peak likewise (its ceiling
    the peak x 1.15); ``first`` (no list on main) records every over-budget
    op and debt, and so does a context in ``new`` (a browser new to main) for
    its own. A failed or unmeasured op keeps its entry."""
    out = {"ceilings": dict(lst["ceilings"]), "debts": list(lst["debts"]), "memory": dict(lst["memory"]),
           "untimed": dict(lst["untimed"])}
    for k, r in results.items():
        if "median" not in r or r["verdict"] == "error":
            continue
        over, fresh = r["median"] > r["budget"] and r["verdict"] != "bar", first or context_of(k) in new
        if k in out["ceilings"]:
            if not over:
                del out["ceilings"][k]
            elif r["verdict"] != "regressed":
                out["ceilings"][k] = min(out["ceilings"][k], ceil(r["median"]))
        elif fresh and over:
            out["ceilings"][k] = ceil(r["median"])
        quiet = r["median"] > PROGRESS and not r["progress"]
        if k in out["debts"] and not quiet:
            out["debts"].remove(k)
        elif fresh and quiet and k not in out["debts"]:
            out["debts"].append(k)
    for run, peak in memory.items():
        if peak is None:
            continue
        if run in out["memory"] and peak <= MEMORY:
            del out["memory"][run]
        elif run in out["memory"]:
            out["memory"][run] = min(out["memory"][run], int(peak * MARGIN))
        elif first and peak > MEMORY:
            out["memory"][run] = int(peak * MARGIN)
    return out


def taken(samples: list[dict]) -> int:
    """The samples an op has taken toward its target: one past 30 s counts as :data:`R` (it runs once)."""
    return len(samples) + (R - 1 if any(s["s"] > LONG for s in samples) else 0)


def alone(samples: list[dict]) -> bool:
    """Whether a changed area's op stands on its one sample (D1215): it is under :data:`PROGRESS` and clean (no
    freeze, no error). Under 1 s an op is within its budget and needs no progress shown, so more samples move no
    verdict but through a median past 1 s (Step 4.40a's count of the gate's runs from 11-01: 32 of 12,239 cases
    whose first sample was under 1 s, one with a verdict other than ``pass``); an error takes no more, as before
    (it ends an op's samples)."""
    return (any(s.get("error") for s in samples) or not samples
            or all(s["s"] < PROGRESS and not s.get("froze") for s in samples))


def rerun(results: dict, samples: list[dict], again: bool = False) -> int:
    """How many more samples a failing time verdict (``slower``, D1170) takes (a spike can't fail it): :data:`R`,
    one past 30 s; ``again`` (its R taken), R more while a place of its samples (:func:`placed`) holds fewer than R
    (a page adds one to its first place, Step 4.47d), none past 30 s."""
    if not results.get("slower"):
        return 0
    if max(s["s"] for s in samples) > LONG:
        return 0 if again else 1
    return R if not again or min(map(len, (placed(samples) or {"": samples}).values())) < R else 0


def verdicts(cases: list[tuple[str, str]], samples: dict, lst: dict, bars=frozenset(),
             browser_bars=frozenset(), reference: dict | None = None, beside: dict | None = None,
             rare=frozenset(), heavy=frozenset()) -> dict:
    """``{key: verdict}`` for ``cases`` from ``{(run, op): samples}`` against the list ``lst`` and the ``reference``
    (``{key: s}`` or :func:`reference_of`'s, the last release's run's) and, for a key ``beside`` holds, the release's
    tree timed beside it (:func:`pair`); each op at its tier's line (D1244, :func:`tiered`: an op of ``rare`` at
    :data:`RARE`, one of ``heavy`` held to its bound); Firefox's whole Save passes 3 s on its moving bar (D1053: its
    download writer alone takes that), never its page part."""
    def tier(op: str) -> str:
        return "rare" if op in rare else "frequent"
    return {key(op, c): judge(samples.get((run_of(op, c), op), []), budget_of(c, tier(op)),
                              lst["ceilings"].get(key(op, c)), key(op, c) in lst["debts"],
                              op in bars or op in browser_bars and c == "firefox", op in browser_bars,
                              (reference or {}).get(key(op, c)), (beside or {}).get(key(op, c)),
                              bound_of(op, c, tier(op)) if op in heavy else None, op in rare)
            for op, c in cases}


def sides(samples: list[dict]) -> dict[str, list[float]]:
    """A side's seconds by place (:func:`placed`; an untagged driver's all under ``"all"``)."""
    return placed(samples) or {"all": [s["s"] for s in samples]}


def tools_of(tree: Path, where: Path):
    """``tree``'s own ``scripts/web_tools.py`` as a module of its own (the release's tree beside, Step 4.47e), so its
    wheel, site and app's venv are built as the release built them (its Pyodide, its wheel's steps, its site's
    assembly, its install), Pyodide's core and the browsers read from the ``.tools`` folder ``where`` (the
    worktree's: an archive is no checkout, whose lookup asks git)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("azurkit_release_web_tools", tree / "scripts" / "web_tools.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module._tools = lambda root: where
    return module


def stopped(error: BaseException) -> bool:
    """Whether ``error`` is a SIGTERM's (:data:`STOPPED`), which no catch of the release's side may keep."""
    return isinstance(error, SystemExit) and error.code == STOPPED


def pair(slow: list[tuple[str, str]], samples: dict, go, beside, repeat=frozenset(), judged=None) -> dict:
    """The release's tree timed beside the head for the ``slow`` cases (Step 4.47e): ``{key: {"head": {place:
    seconds}, "release": {place: seconds}}}``, or ``{key: {"error": why}}`` where the release's side can't be had.
    Per run, a page at a time, the two sides alternate (the release, the head; the head, the release; ...: one
    ``go({run: targets})`` of the head's, one ``beside(run, targets)`` of the release's, its every sample so far as
    ``drive`` returns them), until each side holds :data:`R` pages of each op (an op of fresh states one sample a
    page, one repeated in one state, ``repeat``, R there, a first and its later ones; an op past 30 s one page a
    side); the cases still ``slower`` by ``judged(record)`` (:func:`verdicts` on these) take one more round. A head
    sample that errs ends its op's pages (its verdict is the error's); a release side that errs or raises ends its
    op's, or its run's, with ``error``, but a SIGTERM's exit (:func:`stopped`) ends the run."""
    ops: dict[str, dict[str, list[str]]] = {}   # run: {op: its cases' keys}
    for op, c in slow:
        ops.setdefault(run_of(op, c), {}).setdefault(op, []).append(key(op, c))
    head = {(run, op): [] for run, m in ops.items() for op in m}
    theirs = {k: [] for k in head}
    broken: dict[tuple[str, str], str] = {}
    done: set[tuple[str, str]] = set()   # a head sample erred

    def record() -> dict:
        return {k: {"error": broken[(run, op)]} if (run, op) in broken
                else {"head": sides(head[(run, op)]), "release": sides(theirs[(run, op)])}
                for run, m in ops.items() for op, keys in m.items() for k in keys}
    page, live = dict.fromkeys(ops, 0), {run: list(m) for run, m in ops.items()}   # each run's pages so far
    for rnd in range(2):
        if rnd:
            now = judged(record()) if judged else {}
            live = {run: [op for op in names if any(now.get(k, {}).get("slower") for k in ops[run][op])]
                    for run, names in live.items()}
        for run, names in live.items():
            longs = {op for op in names if any(s["s"] > LONG for s in samples.get((run, op), []))}
            for i in range(R):
                want = [op for op in names if (run, op) not in broken and (run, op) not in done
                        and (i == 0 or op not in longs)]
                if not want:
                    break
                unit = {op: R if op in repeat and op not in longs else 1 for op in want}
                for side in ("release", "head") if page[run] % 2 == 0 else ("head", "release"):
                    want = [op for op in want if (run, op) not in broken]
                    if side == "head" and want:
                        seen = {op: {id(s) for s in samples.get((run, op), [])} for op in want}
                        go({run: {op: taken(samples.get((run, op), [])) + unit[op] for op in want}})
                        for op in want:
                            new = [s for s in samples.get((run, op), []) if id(s) not in seen[op]]
                            head[(run, op)] += [s for s in new if not s.get("error")]
                            if any(s.get("error") for s in new):
                                done.add((run, op))
                    elif want:
                        try:
                            got = beside(run, {op: taken(theirs[(run, op)]) + unit[op] for op in want})["samples"]
                        except (Exception, SystemExit) as error:   # unbuilt or undriven: the receipt's verdict stands
                            if stopped(error):   # a SIGTERM, not the release's fault: the run ends
                                raise
                            why = f"the release's tree: {type(error).__name__}: {str(error)[:300]}"
                            broken |= {(run, op): why for op in names if (run, op) not in broken}
                            continue
                        for op in want:
                            theirs[(run, op)] = [s for s in got.get(op, []) if not s.get("error")]
                            if err := next((s["error"] for s in got.get(op, []) if s.get("error")), None):
                                broken[(run, op)] = f"the release's tree: {err}"
                page[run] += 1
    return record()


def debt_rows(results: dict, saves=frozenset(), free: dict | None = None) -> list[dict]:
    """The perf-debt rows (D1170) of ``results``: each case whose ``debt`` is set, with its verdict (``froze`` for
    one within its budget whose page froze), median, budget, a heavy op's bound (D1244), first freeze and error (an op
    new to the release that errs); a Save's (``saves``) with the free disk in GiB its run left (``free``: ``{run:
    bytes}``)."""
    rows = []
    for k, r in results.items():
        if not r.get("debt"):
            continue
        op, _, context = k.partition("/")
        row = {"op": k, "verdict": r["verdict"] if r["verdict"] in (*DEBTS, "error") else "froze",
               "median": r.get("median"), "budget": r["budget"]} | ({"froze": r["froze"][0]} if r.get("froze") else {})
        if r.get("bound") is not None:
            row["bound"] = r["bound"]
        if r.get("error"):
            row["error"] = r["error"]
        if op in saves and (free or {}).get(run_of(op, context)) is not None:
            row["free_disk_gib"] = round(free[run_of(op, context)] / 2**30, 1)
        rows.append(row)
    return rows


def debt_line(row: dict) -> str:
    """A perf-debt row as one printed line."""
    return (f"{row['op']}: {row['verdict']} "
            + (f"({row['error']})" if "error" in row else f"({row['median']} s, budget {row['budget']}"
               + (f", bound {row['bound']})" if row.get("bound") is not None else ")"))
            + (f"; {row['froze']}" if row.get("froze") else "")
            + (f"; {row['free_disk_gib']} GiB free" if "free_disk_gib" in row else ""))


def measure(cases: list[tuple[str, str]], drive, lst: dict, untimed=frozenset(), bars=frozenset(),
            fresh=frozenset(), browser_bars=frozenset(), reference: dict | None = None,
            once: bool = False, beside=None, repeat=frozenset(), rare=frozenset(),
            heavy=frozenset()) -> tuple[dict, dict, dict]:
    """``({key: verdict}, {run: memory peak}, {(run, op): samples})`` for ``cases`` (``(op,
    context)``): ``drive(run, {op: target})`` returns that run's ``{"samples":
    {op: every sample so far}, "memory_peak"}`` once each op has
    :func:`taken` its target; with ``once`` (a changed area's run, D1215) each
    op's target is one sample, then :data:`R` for each op not :func:`alone`; a
    failing time verdict (``slower`` than its
    ``reference``) drives its op again, R more and then R more while a place
    holds fewer than R
    (:func:`rerun`; not in a context of ``fresh``: a first record lists every
    over-budget op as it is) and is judged on all its samples. With ``beside``
    (the release's tree's ``drive``, Step 4.47e) a slower op is timed beside
    the release's instead (:func:`pair`; ``repeat``: the ops repeated in one
    state) and judged against it; one whose release side errs re-runs as
    before, against the reference. ``rare`` and ``heavy``: :func:`tiered`'s
    (D1244), each op judged at its tier's line."""
    timed = [(op, c) for op, c in cases if op not in untimed]
    samples: dict[tuple[str, str], list[dict]] = {}
    peaks: dict[str, int | None] = {}
    shared: dict[str, bool] = {}

    def go(wanted: dict[str, dict[str, int]]) -> None:
        for run, targets in wanted.items():
            got = drive(run, targets)
            for op, every in got["samples"].items():
                samples[(run, op)] = list(every)
            if got.get("memory_peak") is not None:
                peaks[run] = max(peaks.get(run) or 0, got["memory_peak"])
                shared[run] = shared.get(run, False) or bool(got.get("memory_shared"))

    first: dict[str, dict[str, int]] = {}
    for op, c in timed:
        first.setdefault(run_of(op, c), {})[op] = 1 if once else R
    go(first)
    rest: dict[str, dict[str, int]] = {}
    for op, c in timed if once else ():
        if not alone(samples.get((run_of(op, c), op), [])):
            rest.setdefault(run_of(op, c), {})[op] = R
    if rest:
        go(rest)
    tiers = {"rare": rare, "heavy": heavy}
    judged = verdicts(timed, samples, lst, bars, browser_bars, reference, **tiers)
    paired = {} if beside is None else pair(
        [(op, c) for op, c in timed if c not in fresh and judged[key(op, c)].get("slower")], samples, go, beside,
        repeat, lambda record: verdicts(timed, samples, lst, bars, browser_bars, reference, record, **tiers))
    if paired:
        judged = verdicts(timed, samples, lst, bars, browser_bars, reference, paired, **tiers)
    for again in (False, *[True] * (R - 1)):   # R more, then R more while a place holds fewer (:func:`rerun`)
        more: dict[str, dict[str, int]] = {}
        for op, c in timed:
            got = samples.get((run_of(op, c), op), [])
            if "head" in paired.get(key(op, c), {}):   # timed beside the release's tree: judged on those pages
                continue
            if c not in fresh and (n := rerun(judged[key(op, c)], got, again)):
                targets = more.setdefault(run_of(op, c), {})
                targets[op] = max(targets.get(op, 0), taken(got) + n)
        if not more:
            break
        go(more)
    peaks_of = {run: (peak, shared.get(run, False)) for run, peak in peaks.items()}
    return verdicts(timed, samples, lst, bars, browser_bars, reference, paired, **tiers), peaks_of, samples


def normal_load(samples: int = 8, span: float = 4.0) -> float:
    """The normal-priority 5-min load (D975): vm.loadavg's 5-min value times
    the nice <= 0 share of the runnable threads (``ps -A -M``, ``samples``
    times over ``span`` s); a failed ps counts every thread (never under)."""
    runnable = normal = 0
    for i in range(samples):
        try:
            out = subprocess.run(["ps", "-A", "-M", "-o", "pid=,nice=,state="], capture_output=True, text=True,
                                 timeout=30).stdout
        except (OSError, subprocess.SubprocessError):
            return os.getloadavg()[1]
        for row in out.splitlines():
            f = row.split()
            if len(f) >= 3 and f[-1].startswith("R") and f[-3].isdigit():
                runnable += 1
                normal += not re.fullmatch(r"-?\d+", f[-2]) or int(f[-2]) <= 0
        if i < samples - 1:
            time.sleep(span / max(1, samples - 1))
    return round(os.getloadavg()[1] * (normal / runnable if runnable else 1.0), 2)


def _git(wt: Path, *args: str) -> str | None:
    done = subprocess.run(["git", "-C", str(wt), *args], capture_output=True, text=True)
    return done.stdout if done.returncode == 0 else None


def changed(wt: Path, base: str) -> list[str]:
    return sorted(set((_git(wt, "diff", "--name-only", base) or "").split()
                      + (_git(wt, "ls-files", "--others", "--exclude-standard") or "").split()))


def clone_of(wt: Path) -> Path | None:
    """The Azurik-Custom-Content clone beside the main checkout, if there is one."""
    common = (_git(wt, "rev-parse", "--path-format=absolute", "--git-common-dir") or "").strip()
    guess = Path(common).parent.parent / "Azurik-Custom-Content" if common else None
    return guess if guess and (guess / "manifest.json").is_file() else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="perf", description=__doc__.split("\n\n")[0])
    ap.add_argument("worktree", type=Path)
    ap.add_argument("--select", help="HOST:GROUP pairs, comma-separated (default: what --base's changes reach)")
    ap.add_argument("--base", default="main", help="the changes' base for the selection (default main)")
    ap.add_argument("--all", action="store_true", help="every op, every profile and browser (main's full runs)")
    ap.add_argument("--profiles", help=f"comma-separated of {', '.join(PROFILES)} (default app,site)")
    ap.add_argument("--browsers", help=f"the site's browsers, of {', '.join(BROWSERS)} (default webkit; --all each)")
    ap.add_argument("--ops", help="only these op ids")
    ap.add_argument("--update-ceilings", action="store_true", help=f"rewrite {CEILINGS} from this run")
    ap.add_argument("--json", type=Path, help="write the result here")
    ap.add_argument("--keep", type=Path, help="keep each run's samples here, and reuse them")
    ap.add_argument("--content", type=Path, help="a clone of Azurik-Custom-Content (default: beside the checkout)")
    ap.add_argument("--repeats", type=int, default=R, help=f"samples an op (default {R}; fewer only to try a driver)")
    ap.add_argument("--reference", type=Path, metavar="META",
                    help="a receipt of the last release's run: an op slower than its there, or erring, fails (D1170)")
    args = ap.parse_args(argv)
    globals()["R"] = args.repeats
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(STOPPED))   # a stopped run still deletes its scratch
    wt = args.worktree.resolve()
    sys.path[:0] = [str(ROOT)]
    from tests import _perf

    if args.all:
        pairs = {(h, g) for h in ("app", "site") for g in GROUPS}
    elif args.select:
        pairs = {tuple(p.split(":", 1)) for p in args.select.split(",") if p}
    else:
        pairs = select(changed(wt, args.base))
    profiles = (args.profiles or ("app,site,lag,capped" if args.all else "app,site")).split(",")
    browsers = (args.browsers or (",".join(BROWSERS) if args.all else "webkit")).split(",")
    if bad := set(profiles) - set(PROFILES) | set(browsers) - set(BROWSERS):
        ap.error(f"unknown profiles or browsers: {sorted(bad)}")
    ops = [op for op in _perf.OPS.values() if (op.host, op.group) in pairs
           and (not args.ops or op.id in args.ops.split(","))]
    cases = [(op.id, c) for op in ops for c in contexts(profiles, browsers)
             if (c == "app") == (op.host == "app") or c == "capped"]
    mine = listed((wt / CEILINGS).read_text(encoding="utf-8") if (wt / CEILINGS).is_file() else None)
    on_main = _git(wt, "show", f"main:{CEILINGS}")
    main_list = listed(on_main) if on_main is not None else None
    new = new_browsers(wt, "main", "HEAD")   # each one's first record may add its own ops
    tiers = (tiering_at(wt, "HEAD"), tiering_at(wt, "main"))   # D1244: a line rises only by the owner's tiering
    rare, heavy = tiered(ops)
    t0 = time.monotonic()
    block = {"profiles": profiles, "browsers": browsers, "pairs": sorted(f"{h}:{g}" for h, g in pairs),
             "cases": {}, "memory": {}, "list": check_list(mine, main_list, new, tiers), "untimed": {},
             "new": sorted(new),
             "tree_peaks": {}}
    reference, free = None, {}   # the last release's run's medians; the free disk each run left (a Save's debt)
    release = None   # the release's commit, whose tree is timed beside an op that reads slower (Step 4.47e)
    if args.reference:
        against = json.loads(args.reference.read_text(encoding="utf-8"))
        reference = {k: reference_of(r, _perf.OPS.get(k.partition("/")[0]))
                     for k, r in against["perf"]["cases"].items() if "median" in r}
        block["reference"] = {"receipt": args.reference.name, "head": against.get("head", "")[:12]}
        if (commit := against.get("head")) and _git(wt, "cat-file", "-e", f"{commit}^{{commit}}") is not None:
            release = commit
        block["reference"]["beside"] = bool(release)
    untimed = {op.id for op in ops if op.untimed}
    block["untimed"] = {op.id: op.untimed for op in ops if op.untimed}
    if cases:
        from azurkit.core import gate
        iso = gate.find(gate.USA)
        if iso is None or iso.stat().st_size != gate.USA.iso_size:
            print(f"perf: the USA image: {gate.missing(gate.USA)}", file=sys.stderr)
            return 2
        content = args.content or clone_of(wt)
        import tempfile
        # Not macOS's $TMPDIR, which a daily sweep empties of what looks 3 days old (this venv keeps uv's cache's times).
        scratch = Path(tempfile.mkdtemp(prefix="azurkit-perf-site.", dir=None if os.name == "nt" else "/tmp"))
        built: dict = {}   # (tree, what): made; ("failed", what): the error the release's failed with
        natives: dict[str, list] = {}
        held: dict[str, dict] = {}   # each run's record so far: a re-run's samples join its first ones (measure)

        from scripts import web_tools

        def made(what: str, tree: Path = wt, into: Path = scratch, tools=web_tools) -> Path | str:   # each made once,
            if (tree, what) not in built:   # as a run needs it, by ``tools`` (a web_tools): one wheel for both hosts
                built[(tree, what)] = (tools.wheel(into / "wheel", tree) if what == "wheel"
                                       else tools.site(into / "site", root=tree, built=made("wheel", tree, into, tools),
                                                       content=content)
                                       if what == "site"
                                       else _perf.venv(tree, into / "app", made("wheel", tree, into, tools), tools))
            return built[(tree, what)]

        def made_release(what: str) -> Path | str:   # the release's tree beside (Step 4.47e): its commit's files,
            if (failed := built.get(("failed", what))) is not None:   # built by its own web_tools
                raise failed
            tree = scratch / "release" / "tree"
            try:
                if not tree.is_dir():
                    import tarfile
                    (part := scratch / "release" / "tree.part").mkdir(parents=True, exist_ok=True)
                    tar = scratch / "release" / "tree.tar"
                    subprocess.run(["git", "-C", str(wt), "archive", "--format=tar", "-o", str(tar), release,
                                    *RELEASE_TREE], check=True, capture_output=True, timeout=600)
                    with tarfile.open(tar) as archive:
                        archive.extractall(part, filter="data")
                    tar.unlink()
                    part.rename(tree)
                if (tree, "tools") not in built:
                    built[(tree, "tools")] = tools_of(tree, web_tools._tools(wt))
                return made(what, tree, scratch / "release", built[(tree, "tools")])
            except (Exception, SystemExit) as error:   # unbuilt: its ops slower than the receipt are judged by it
                if not stopped(error):
                    built[("failed", what)] = error
                raise
        try:
            def drive_on(tree: Path, maker, store: dict, run: str, targets: dict[str, int], kept: Path | None = None):
                """``run``'s record on ``tree`` (the worktree, or the release's beside it) after its ``targets``."""
                spec = _perf.RUNS[run]
                if run == "firefox" or run == "webkit" and "capped" in profiles:
                    spec = dataclasses.replace(spec, memory=True)
                old = store.get(run) or (json.loads(kept.read_text(encoding="utf-8")) if kept and kept.is_file()
                                         else {"samples": {}})
                have = {op: [s for s in got if not s.get("error")] for op, got in old["samples"].items()}
                todo = {op: n - taken(have.get(op, [])) for op, n in targets.items() if n > taken(have.get(op, []))}
                got = (_perf.drive(tree, spec, todo, iso, content, maker("site") if spec.host == "site" else None,
                                   maker("app") if spec.host == "app" else None) if todo
                       else {"samples": {}, "log": []})
                for op, more in got["samples"].items():
                    have.setdefault(op, []).extend(more)
                return old, got, have

            theirs: dict[str, dict] = {}   # the release's runs' records (none of it kept, checked or peaked)

            def beside(run: str, targets: dict[str, int]) -> dict:
                _, got, have = drive_on(scratch / "release" / "tree", made_release, theirs, run, targets)
                theirs[run] = {"samples": have, "log": got.get("log", [])}
                return {"samples": {op: have.get(op, []) for op in targets}}

            def drive(run: str, targets: dict[str, int]) -> dict:
                kept = args.keep / f"{run}.json" if args.keep else None
                old, got, have = drive_on(wt, made, held, run, targets, kept)
                free[run] = shutil.disk_usage(scratch).free
                seen = natives.setdefault(run, [])
                seen += [r for r in old.get("native", []) + got.get("native", []) if r not in seen]
                peak = max(filter(None, (old.get("memory_peak"), got.get("memory_peak"))), default=None)
                shared = bool(old.get("memory_shared") or got.get("memory_shared"))
                held[run] = {"samples": have, "native": list(seen), "memory_peak": peak, "memory_shared": shared,
                             "log": old.get("log", []) + got.get("log", [])}
                if kept:
                    kept.parent.mkdir(parents=True, exist_ok=True)
                    kept.write_text(json.dumps(held[run], indent=1), encoding="utf-8")
                return {"samples": {op: have.get(op, []) for op in targets}, "memory_peak": peak,
                        "memory_shared": shared}

            bars, browser_bars = {op.id for op in ops if op.bar}, {op.id for op in ops if op.browser_bar}
            fresh = (set(contexts(profiles, browsers)) if main_list is None else new) if args.update_ceilings else ()
            block["cases"], peaks, samples = measure(cases, drive, mine, untimed, bars, fresh, browser_bars, reference,
                                                     once=not args.all, beside=beside if release else None,
                                                     repeat={op.id for op in ops if not op.first}, rare=rare,
                                                     heavy=heavy)
            if not args.all:   # D1215: the cases whose one sample stood (under 1 s, clean)
                block["one_sample"] = sorted(k for k, r in block["cases"].items()
                                             if r["n"] == 1 and r.get("median") is not None and r["median"] < PROGRESS)
            from azurkit.core import native
            block["native"] = natives
            block["native_failures"] = native_failures(natives, {
                run: shipped(wt, native.target() if _perf.RUNS[run].host == "app" else SIDE_MODULE) for run in natives})
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
        for run, (peak, others) in peaks.items():
            if "capped" in profiles and run in ("app-capped", "webkit"):
                name = "capped-app" if run == "app-capped" else "capped-site"
                ceiling = mine["memory"].get(name)
                block["memory"][name] = {"peak": peak, "ok": peak <= max(MEMORY, ceiling or 0), "ceiling": ceiling,
                                         "shared": others}   # the site's: another Playwright's WebKit may be in it
            elif run == "firefox":   # logged, no verdict reads it: the 6 GiB line is the capped profile's
                block["tree_peaks"][run] = peak
    if args.update_ceilings:
        lst = updated(mine, block["cases"], {k: v["peak"] for k, v in block["memory"].items()}, main_list is None,
                      new)
        lst["untimed"] = (dict(mine["untimed"]) | block["untimed"]) if main_list is None else {   # the registry's
            k: v for k, v in mine["untimed"].items() if k not in _perf.OPS or _perf.OPS[k].untimed}   # not the run's
        (wt / CEILINGS).write_text(render(lst), encoding="utf-8")
        block["list"] = check_list(lst, main_list, new, tiers)
        if cases:   # judged again against the list it wrote
            block["cases"] = verdicts([oc for oc in cases if oc[0] not in untimed], samples, lst, bars, browser_bars,
                                      reference, {k: {f: v for f, v in r["beside"].items() if f in ("head", "release",
                                                                                                     "error")}
                                                  for k, r in block["cases"].items() if "beside" in r}, rare, heavy)
            for name, mem in block["memory"].items():
                mem |= {"ceiling": lst["memory"].get(name), "ok": mem["peak"] <= max(MEMORY, lst["memory"].get(name, 0))}
    block["failures"] = blocking(block)
    block |= {"passed": not block["failures"],
              "debt": debt_rows(block["cases"], {op.id for op in ops if op.title.startswith("Save")}, free),
              "wall_s": round(time.monotonic() - t0, 1)}
    for k, r in block["cases"].items():
        print(f"{k:16} {r['verdict']:12} {r.get('median', '-')!s:>8} s  n {r['n']}  budget {r['budget']}"
              + (f"  bound {r['bound']}" if r.get("bound") is not None else "")
              + (f"  ceiling {r['ceiling']}" if r["ceiling"] else "")
              + (f"  release's {r['reference']}" if r.get("reference") is not None else "")
              + "".join(f"  {p} {v['median']} ({v['reference']})" for p, v in r.get("places", {}).items())
              + "".join(f"  beside {p} {v['head']} (the release's {v['release']})"
                        for p, v in (r.get("beside") or {}).get("places", {}).items())
              + (f"  beside: {r['beside']['error']}" if (r.get("beside") or {}).get("error") else "")
              + ("  debt" if r.get("debt") else "") + ("  SLOWER" if r.get("slower") else "")
              + (f"  starved {r['starved']}" if r.get("starved") else ""))
    for run, peak in block["tree_peaks"].items():
        print(f"{run} tree peak {peak / 2**30:.2f} GiB (logged)")
    print(f"perf: {'passed' if block['passed'] else 'failed'}, {len(block['cases'])} cases in {block['wall_s']} s"
          + (f", {len(block['one_sample'])} of them on one sample under {PROGRESS:g} s (D1215)"
             if block.get("one_sample") else "")
          + "".join(f"\n  {line}" for line in block["failures"])
          + (f"\nperf debt: {len(block['debt'])} rows, failing nothing (D1170)" if block["debt"] else "")
          + "".join(f"\n  {debt_line(row)}" for row in block["debt"]))
    if args.json:
        args.json.write_text(json.dumps(block, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if block["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
