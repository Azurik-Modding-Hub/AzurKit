"""perf: the perf gate (D980-D985): every player-facing operation timed in
the app and on the site, each against 3 s (D981), the over-budget ones
against their ceilings in ``tests/perf_ceilings.toml``, a list that only
shrinks.

    uv run --locked python scripts/perf.py WORKTREE [--select HOST:GROUP,..] [--base REF] [--all]
                                           [--profiles P,..] [--browsers B,..] [--ops ID,..]
                                           [--update-ceilings] [--json FILE] [--keep DIR] [--content CLONE]
                                           [--repeats N]

What it times: ``tests/_perf.py``'s registry (``A01``-``A30`` the app's,
``S01``-``S25`` the site's), the ops of the groups the worktree's changes
reach (:func:`select`: ``--base``, default main; or ``--select``; ``--all``
every op), in the profiles named: ``app`` (the app's serve mode with a fresh
HOME, its page in WebKit), ``site`` (the site served on 127.0.0.1, in each of
``--browsers``), ``lag`` (the site in WebKit with each File read 200 ms
late, Safari's read model) and ``capped`` (the app with ``AZURKIT_CORES=4``
and the site in WebKit, against 9 s, with our processes' peak resident size
at most 6 GiB). Default: ``app`` and ``site`` in WebKit (a changed area's);
``--all`` every profile and browser (main's full runs).

The verdicts (:func:`judge`): each op runs :data:`R` times (an op with a
sample over 30 s once), first-time ops each in a fresh state, and its median
decides. An op over its budget or ceiling runs :data:`R` more times (one more
past 30 s) and fails only if the median of all of them is still over. An op
not in the list fails over its budget; D982's first-time ops (an image's
first identity check, the site's first engine load) may pass it only with a
moving bar (the progress element seen at 2 or more values). A listed op fails
over its ceiling. An op whose median passes 1 s must show progress (a bar or a
"k of n" / "N %" line changing at least once, D980) unless it is one of the
list's progress debts. The list itself fails when it adds an op or a debt or
raises a ceiling against main's (:func:`check_list`).

``--update-ceilings`` rewrites the list from this run (:func:`updated`): it
lowers a ceiling to the new median x 1.15 (rounded up to 0.1 s) and drops an
op back under its budget and a debt that now shows progress; with no list on
main (its first record) it records every over-budget op and every debt.
``--json FILE`` writes the result (``scripts/fullsuite.py``'s receipt block).
``--keep DIR`` keeps each run's samples there and reuses them, so a stopped
run resumes. Exit 0 passed, 1 failed, 2 can't run. No game bytes printed.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import os
import re
import signal
import statistics
import subprocess
import sys
import time
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CEILINGS = "tests/perf_ceilings.toml"
BUDGET = 3.0          # D981: a player-facing op's seconds on this Mac
CAPPED = 9.0          # D984: the capped profile's
PROGRESS = 1.0        # D980: an op past this shows progress
MEMORY = 6 * 2**30    # the capped profile's peak resident size
R = 3                 # samples an op (the median decides)
LONG = 30.0           # an op past this runs once, and once more on a re-run
MARGIN = 1.15         # a ceiling is the median times this, rounded up to 0.1 s
LOAD_LINE = 40.0      # D926/D975: the gate's perf stage starts under this normal-priority load
PROFILES = ("app", "site", "lag", "capped")
BROWSERS = ("webkit", "chromium")
#: Which ops a changed path reaches (section 2.4 of round 1's plan): ``(prefix, hosts, groups)``, the first match;
#: an unlisted path under ``src/`` reaches every op; any other path none.
REACH = (("src/azurkit/app/", ("app",), None), ("src/azurkit/__main__.py", ("app",), None),
         ("src/azurkit/tools/randomizer/", ("app", "site"), ("randomizer", "tracker")),
         ("src/azurkit/tools/characters/", ("app", "site"), ("characters", "build")),
         ("src/", ("app", "site"), None), ("web/", ("app", "site"), None), ("scripts/web_tools.py", ("site",), None))
GROUPS = ("start", "image", "build", "characters", "randomizer", "tracker")   # tests/_perf.py's


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


def budget_of(context: str) -> float:
    return CAPPED if context == "capped" else BUDGET


def ceil(seconds: float) -> float:
    """A ceiling: ``seconds`` x :data:`MARGIN`, rounded up to 0.1 s."""
    return math.ceil(round(seconds * MARGIN * 10, 6)) / 10


def judge(samples: list[dict], budget: float, ceiling: float | None = None, debt: bool = False,
          bar: bool = False) -> dict:
    """One op's verdict in one context from its samples (``{"s", "bar",
    "progress"[, "error"]}``): ``pass``, ``listed`` (over its budget, within
    its ceiling), ``bar`` (D982: over 3 s with a moving bar), and the
    failures ``over`` (unlisted, over its budget), ``regressed`` (over its
    ceiling), ``no progress`` (past 1 s with none shown and not a debt) and
    ``error``."""
    seconds = [s["s"] for s in samples]
    out = {"n": len(samples), "budget": budget, "ceiling": ceiling, "samples": seconds}
    if errors := [s["error"] for s in samples if s.get("error")]:
        return out | {"verdict": "error", "ok": False, "error": errors[-1]}
    if not samples:
        return out | {"verdict": "error", "ok": False, "error": "no sample"}
    median = statistics.median(seconds)
    over = [s for s in samples if s["s"] > budget]
    moved = bool(over) and all(s["bar"] >= 2 for s in over)
    shown = all(s["progress"] for s in samples if s["s"] > PROGRESS)
    out |= {"median": round(median, 3), "spread": round(max(seconds) - min(seconds), 3), "progress": shown,
            "moved": moved}
    if ceiling is not None and median > ceiling:
        verdict = "regressed"
    elif median > budget:
        verdict = "listed" if ceiling is not None else "bar" if bar and moved else "over"
    else:
        verdict = "pass"
    if verdict in ("pass", "listed", "bar") and median > PROGRESS and not shown and not debt:
        verdict = "no progress"
    return out | {"verdict": verdict, "ok": verdict in ("pass", "listed", "bar")}


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
    lines = ["# The perf gate's list (scripts/perf.py; D980-D985): each op still over its budget (3 s, the capped",
             "# profile's 9 s) with its ceiling, the median x 1.15 rounded up to 0.1 s, as \"<op>/<context>\"",
             "# (tests/_perf.py's ids; app, webkit, chromium, lag, capped); the ops past 1 s that show no progress",
             "# yet (D980); the capped profile's peak memory over 6 GiB; the ops the gate can't time. It only",
             "# shrinks: `perf.py --update-ceilings` lowers and drops, and the gate fails an added op, debt or a",
             "# raised ceiling against main's. Empty for a release (scripts/land.py --release).", "", "[ceilings]"]
    lines += [f'"{k}" = {lst["ceilings"][k]}' for k in sorted(lst["ceilings"], key=order)]
    lines += ["", "[debts]", "keys = ["]
    lines += [f'    "{k}",' for k in sorted(lst["debts"], key=order)]
    lines += ["]", "", "[memory]   # GiB"]
    lines += [f'"{k}" = {math.ceil(v / 2**30 * 10) / 10}' for k, v in sorted(lst["memory"].items())]
    lines += ["", "[untimed]"]
    lines += [f'{k} = {json.dumps(v)}' for k, v in sorted(lst["untimed"].items())]
    return "\n".join(lines) + "\n"


def count(lst: dict) -> int:
    return len(lst["ceilings"]) + len(lst["debts"]) + len(lst["memory"]) + len(lst["untimed"])


def check_list(mine: dict, main: dict | None) -> list[str]:
    """What the worktree's list adds or raises against main's (none on the first record)."""
    if main is None:
        return []
    bad = [f"{k}: added to the list (ceiling {v} s)" for k, v in mine["ceilings"].items() if k not in main["ceilings"]]
    bad += [f"{k}: its ceiling raised, {main['ceilings'][k]} -> {v} s" for k, v in mine["ceilings"].items()
            if k in main["ceilings"] and v > main["ceilings"][k]]
    bad += [f"{k}: a new progress debt" for k in mine["debts"] if k not in main["debts"]]
    bad += [f"memory {k}: added or raised" for k, v in mine["memory"].items() if v > main["memory"].get(k, -1)]
    bad += [f"{k}: newly untimed" for k in mine["untimed"] if k not in main["untimed"]]
    return bad


def updated(lst: dict, results: dict, memory: dict, first: bool) -> dict:
    """The list after this run: a measured ceiling lowered to its median's
    (:func:`ceil`) or dropped once under its budget, a debt dropped once it
    shows progress or stays under 1 s, a memory peak likewise (its ceiling
    the peak x 1.15); ``first`` (no list on
    main) records every over-budget op and debt. A failed or unmeasured op
    keeps its entry."""
    out = {"ceilings": dict(lst["ceilings"]), "debts": list(lst["debts"]), "memory": dict(lst["memory"]),
           "untimed": dict(lst["untimed"])}
    for k, r in results.items():
        if "median" not in r or r["verdict"] == "error":
            continue
        over = r["median"] > r["budget"] and r["verdict"] != "bar"
        if k in out["ceilings"]:
            if not over:
                del out["ceilings"][k]
            elif r["verdict"] != "regressed":
                out["ceilings"][k] = min(out["ceilings"][k], ceil(r["median"]))
        elif first and over:
            out["ceilings"][k] = ceil(r["median"])
        quiet = r["median"] > PROGRESS and not r["progress"]
        if k in out["debts"] and not quiet:
            out["debts"].remove(k)
        elif first and quiet and k not in out["debts"]:
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


def rerun(results: dict, samples: list[dict]) -> int:
    """How many more samples a failing time verdict takes (a spike can't fail it): :data:`R`, one past 30 s."""
    if results["verdict"] not in ("over", "regressed"):
        return 0
    return 1 if max(s["s"] for s in samples) > LONG else R


def verdicts(cases: list[tuple[str, str]], samples: dict, lst: dict, bars=frozenset()) -> dict:
    """``{key: verdict}`` for ``cases`` from ``{(run, op): samples}`` against the list ``lst``."""
    return {key(op, c): judge(samples.get((run_of(op, c), op), []), budget_of(c), lst["ceilings"].get(key(op, c)),
                              key(op, c) in lst["debts"], op in bars) for op, c in cases}


def measure(cases: list[tuple[str, str]], drive, lst: dict, untimed=frozenset(), bars=frozenset(),
            again: bool = True) -> tuple[dict, dict, dict]:
    """``({key: verdict}, {run: memory peak}, {(run, op): samples})`` for ``cases`` (``(op,
    context)``): ``drive(run, {op: target})`` returns that run's ``{"samples":
    {op: every sample so far}, "memory_peak"}`` once each op has
    :func:`taken` its target; a failing time verdict drives its op again
    (:func:`rerun`; not with ``again`` false: the first record lists every
    over-budget op as it is) and is judged on all its samples."""
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
        first.setdefault(run_of(op, c), {})[op] = R
    go(first)
    more: dict[str, dict[str, int]] = {}
    judged = verdicts(timed, samples, lst, bars)
    for op, c in timed:
        got = samples.get((run_of(op, c), op), [])
        if again and (n := rerun(judged[key(op, c)], got)):
            targets = more.setdefault(run_of(op, c), {})
            targets[op] = max(targets.get(op, 0), taken(got) + n)
    if more:
        go(more)
    return verdicts(timed, samples, lst, bars), {run: (peak, shared.get(run, False)) for run, peak in peaks.items()}, samples


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
    ap.add_argument("--browsers", help="the site's browsers (default webkit; --all both)")
    ap.add_argument("--ops", help="only these op ids")
    ap.add_argument("--update-ceilings", action="store_true", help=f"rewrite {CEILINGS} from this run")
    ap.add_argument("--json", type=Path, help="write the result here")
    ap.add_argument("--keep", type=Path, help="keep each run's samples here, and reuse them")
    ap.add_argument("--content", type=Path, help="a clone of Azurik-Custom-Content (default: beside the checkout)")
    ap.add_argument("--repeats", type=int, default=R, help=f"samples an op (default {R}; fewer only to try a driver)")
    args = ap.parse_args(argv)
    globals()["R"] = args.repeats
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))   # a stopped run still deletes its scratch
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
    browsers = (args.browsers or ("webkit,chromium" if args.all else "webkit")).split(",")
    if bad := set(profiles) - set(PROFILES) | set(browsers) - set(BROWSERS):
        ap.error(f"unknown profiles or browsers: {sorted(bad)}")
    ops = [op for op in _perf.OPS.values() if (op.host, op.group) in pairs
           and (not args.ops or op.id in args.ops.split(","))]
    cases = [(op.id, c) for op in ops for c in contexts(profiles, browsers)
             if (c == "app") == (op.host == "app") or c == "capped"]
    mine = listed((wt / CEILINGS).read_text(encoding="utf-8") if (wt / CEILINGS).is_file() else None)
    on_main = _git(wt, "show", f"main:{CEILINGS}")
    main_list = listed(on_main) if on_main is not None else None
    t0 = time.monotonic()
    block = {"profiles": profiles, "browsers": browsers, "pairs": sorted(f"{h}:{g}" for h, g in pairs),
             "cases": {}, "memory": {}, "list": check_list(mine, main_list), "untimed": {}}
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
        scratch = Path(tempfile.mkdtemp(prefix="azurkit-perf-site.", dir="/tmp"))
        built: list[Path] = []

        def site() -> Path:   # built once, the first time a site run drives
            if not built:
                from scripts import web_tools
                built.append(web_tools.site(scratch / "site", root=wt, content=content))
            return built[0]
        try:
            def drive(run: str, targets: dict[str, int]) -> dict:
                spec = _perf.RUNS[run]
                if run == "webkit" and "capped" in profiles:
                    spec = dataclasses.replace(spec, memory=True)
                kept = args.keep / f"{run}.json" if args.keep else None
                old = json.loads(kept.read_text(encoding="utf-8")) if kept and kept.is_file() else {"samples": {}}
                have = {op: [s for s in got if not s.get("error")] for op, got in old["samples"].items()}
                todo = {op: n - taken(have.get(op, [])) for op, n in targets.items() if n > taken(have.get(op, []))}
                got = (_perf.drive(wt, spec, todo, iso, content, site() if spec.host == "site" else None) if todo
                       else {"samples": {}, "log": []})
                for op, more in got["samples"].items():
                    have.setdefault(op, []).extend(more)
                peak = max(filter(None, (old.get("memory_peak"), got.get("memory_peak"))), default=None)
                shared = bool(old.get("memory_shared") or got.get("memory_shared"))
                if kept:
                    kept.parent.mkdir(parents=True, exist_ok=True)
                    kept.write_text(json.dumps({"samples": have, "memory_peak": peak, "memory_shared": shared,
                                                "log": old.get("log", []) + got.get("log", [])}, indent=1),
                                    encoding="utf-8")
                return {"samples": {op: have.get(op, []) for op in targets}, "memory_peak": peak,
                        "memory_shared": shared}

            bars = {op.id for op in ops if op.bar}
            block["cases"], peaks, samples = measure(cases, drive, mine, untimed, bars,
                                                     again=not (args.update_ceilings and main_list is None))
        finally:
            import shutil
            shutil.rmtree(scratch, ignore_errors=True)
        for run, (peak, others) in peaks.items():
            if "capped" in profiles and run in ("app-capped", "webkit"):
                name = "capped-app" if run == "app-capped" else "capped-site"
                ceiling = mine["memory"].get(name)
                block["memory"][name] = {"peak": peak, "ok": peak <= max(MEMORY, ceiling or 0), "ceiling": ceiling,
                                         "shared": others}   # the site's: another Playwright's WebKit may be in it
    if args.update_ceilings:
        new = updated(mine, block["cases"], {k: v["peak"] for k, v in block["memory"].items()}, main_list is None)
        new["untimed"] = (dict(mine["untimed"]) | block["untimed"]) if main_list is None else {
            k: v for k, v in mine["untimed"].items() if k in block["untimed"] or k not in _perf.OPS}
        (wt / CEILINGS).write_text(render(new), encoding="utf-8")
        block["list"] = check_list(new, main_list)
        if cases:   # judged again against the list it wrote
            block["cases"] = verdicts([oc for oc in cases if oc[0] not in untimed], samples, new, bars)
            for name, mem in block["memory"].items():
                mem |= {"ceiling": new["memory"].get(name), "ok": mem["peak"] <= max(MEMORY, new["memory"].get(name, 0))}
    failing = [f"{k}: {r['verdict']}" + (f" ({r.get('median')} s, budget {r['budget']}"
                                         + (f", ceiling {r['ceiling']}" if r["ceiling"] else "") + ")"
                                         if "median" in r else f" ({r.get('error')})")
               for k, r in block["cases"].items() if not r["ok"]]
    failing += [f"memory {k}: {v['peak'] / 2**30:.2f} GiB" for k, v in block["memory"].items() if not v["ok"]]
    block |= {"failures": failing + block["list"], "passed": not failing and not block["list"],
              "wall_s": round(time.monotonic() - t0, 1)}
    for k, r in block["cases"].items():
        print(f"{k:16} {r['verdict']:12} {r.get('median', '-')!s:>8} s  n {r['n']}  budget {r['budget']}"
              + (f"  ceiling {r['ceiling']}" if r["ceiling"] else ""))
    print(f"perf: {'passed' if block['passed'] else 'failed'}, {len(block['cases'])} cases in {block['wall_s']} s"
          + "".join(f"\n  {line}" for line in block["failures"]))
    if args.json:
        args.json.write_text(json.dumps(block, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if block["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
