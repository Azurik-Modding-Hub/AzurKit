"""The reach engine's pool workers (Step R2.19b): what each runs once as it starts (:func:`setup`, ``l3_pool.Pool``'s
``setup`` in every pool ``devkit/reach/reach_engine.py`` opens), and the audits' task.  In no cache key
(``cache.CORE_FILES``): a change here re-runs no job.

A step L3's watchdog stops for time (a site of :data:`TIME_SITES`) says how busy the host was, not what the game did:
a worker the host starves (an owner demo, a game, nice 19) passes a step's deadline anywhere (AZ-813: 18 of round 1's
w1 records ended launches ``fault:runaway@`` at scattered EIPs, written while a demo held the pool at background
priority; each re-run gives none).  So a worker's simulator raises it as :class:`StepTimeout`, no ``L3Error``, which
no launch, start, kit or hold takes for the game's fault: ``runner.job_task`` keeps it as the job's ``error`` (no
record written, so a later run tries it again) and a hold task raises it (no answer cached: the command stops, and a
re-run asks again).  A step the game itself never ends stops the same way, and is never recorded.

Each job record a worker writes carries ``l3_impl`` (:func:`impl`): which simulator ran it (FastL3 with the sha of its
code, or base L3), the sha of the libunicorn the worker loaded and the switches it ran with.  A field, not a key part:
a record is the same whichever ran it (Step R2.19a's gate), and a record a new ``l3_impl`` wrote is found by it.  FastL3
is the proof, so a fast run is audited (:func:`audited`, PLAN-v2 §1.5c): about 1 job in :data:`BASE_EVERY` it ran is
run again on base L3 on the stock wheel and 1 in :data:`X87_EVERY` on FastL3 with the patched library's x87 check
mode on (``UC_X87_CHECK=1``: softfloat beside every fast result, the count that differ written as the worker exits,
:func:`x87_counts`) and the C walk's check mode (Step R2.19m: every face decided beside the game's, no face dropped),
each record compared with the one the run wrote (:func:`audit_task`, nothing written).  Since Step R2.19f+ (X1) a hold
answer is stamped so too (``hold.task``) and the holds a graph replays are audited alike, by their hold key
(:func:`hold_audit_task`).
"""

from __future__ import annotations

import atexit
import hashlib
import os
import re
import sys
from pathlib import Path

from devkit.reach.engine import cache, hold, runner
from devkit.sim.l3 import L3Error, fault_site

TIME_SITES = ("runaway@", "render timeout@")   # L3._run's sites for a step its watchdog stopped
BASE_EVERY, X87_EVERY = 500, 1000   # [PLAN-v2 §1.5c] a fast run's jobs re-run on base L3 (0.2 %), with the x87 check
X87_LINE = re.compile(r"x87 fast path: (\d+) fast results, (\d+) differ from softfloat")   # the patch's exit line
WALK_LINE = re.compile(r"walk check: (\d+) checked, (\d+) differ")   # an audit worker's exit line (_walk_report)
IMPL: dict = {}                     # this worker's :func:`impl`, once :func:`setup` has run


class StepTimeout(RuntimeError):
    """A step L3's watchdog stopped for time: the job's error, never an outcome (the module docstring)."""


def timed(sim):
    """``sim`` with each step's time stop raised as :class:`StepTimeout` (once a simulator; its R6 placement steps
    too)."""
    if not getattr(sim, "_timed", False):
        step = sim.step

        def guarded(*a, **k):
            try:
                return step(*a, **k)
            except L3Error as exc:
                if (site := fault_site(exc)).startswith(TIME_SITES):
                    raise StepTimeout(f"a step stopped for time ({site}): the host's load, not the game") from None
                raise
        sim.step, sim._timed = guarded, True
    return sim


def _sha12(*paths: Path) -> str:
    h = hashlib.sha256()
    for p in paths:
        h.update(p.read_bytes())
    return h.hexdigest()[:12]


def impl(fast: bool) -> dict:
    """What this process's reach engine runs on (a record's ``l3_impl``): ``l3`` fast or base, with fast the
    sha256[:12] of FastL3's code (``devkit/reach/l3_fast.py``, ``engine/fast.py``, the C step ``fastl3_step.c``) and
    whether its ticks run on the C step (``step``, Step R2.19m) and its collision walk's mode (``walk``); the libunicorn
    it loaded (sha12) and the switches set
    in its environment (the patched library's, and the x87 check)."""
    from devkit.reach import l3_fast
    out = {"l3": "fast" if fast else "base", "library": _sha12(l3_fast.loaded()),
           "switches": {k: os.environ[k] for k in (*l3_fast.SWITCHES, "UC_X87_CHECK") if k in os.environ}}
    if fast:
        from devkit.reach.engine import fast as cuts
        out["code"] = cache.code_sha12(Path(l3_fast.__file__), Path(cuts.__file__), l3_fast.STEP_SRC)
        out["step"] = "c" if l3_fast.step_on() and l3_fast.step_lib() is not None else "python"
        if out["step"] == "c":
            out["walk"] = os.environ.get("FASTL3_WALK", "1")
    return out


def setup(fast: bool = False, x87: str | None = None) -> None:
    """A worker's start: ``reach_engine.fast``'s driver cuts (``fast.install_driver``, every pool: a launch's
    touches found once, FastL3's placement answers kept, Step R2.19l) and with ``fast`` its tick cuts
    (``fast.install``); then each job's and each hold's simulator :func:`timed` and each job record stamped
    ``l3_impl``.  ``x87`` (a folder): the x87 check mode on, this worker's stderr (where the library writes its count
    as the process exits) in a file there."""
    from devkit.reach.engine import fast as cuts
    if x87 is not None:
        os.environ["UC_X87_CHECK"] = "1"     # read by the library at its first x87 op, after this
        os.environ["FASTL3_WALK"] = "check"  # FastL3's C walk decides every face beside the game (Step R2.19m)
        fd = os.open(Path(x87) / f"{os.getpid()}.log", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.dup2(fd, 2)
        os.close(fd)
        atexit.register(_walk_report)
    cuts.install_driver()
    if fast:
        cuts.install()
    IMPL.clear()
    IMPL.update(impl(fast))
    run_job, replay = runner.run_job, hold.replay

    def job(sim, *a, **k):
        return run_job(timed(sim), *a, **k) | {"l3_impl": dict(IMPL)}

    def held(sim, *a, **k):
        return replay(timed(sim), *a, **k)
    runner.run_job, hold.replay = job, held


def _walk_report() -> None:
    """An x87 audit worker's exit line: the C walk's face decisions its FastL3s checked against the game's and those
    that differed (``l3_fast.FastL3.walk``), on stderr (the audit's file)."""
    from devkit.reach import l3_pool
    sims = l3_pool._W._sims.values() if l3_pool._W is not None else ()
    walks = [getattr(s, "walk", None) or {} for s in sims]
    print(f"walk check: {sum(w.get('checked', 0) for w in walks)} checked, "
          f"{sum(w.get('differ', 0) for w in walks)} differ", file=sys.stderr, flush=True)


def audited(key: str, every: int) -> bool:
    """Whether the job ``key`` (a sha12) is one of about 1 in ``every`` an audit runs again (by its key: the same
    jobs whichever run ran them)."""
    return int(key, 16) % every == 0


def bare(rec: dict) -> str:
    """A record's sha12 without its ``l3_impl``: what the audits compare."""
    return cache.sha12({k: v for k, v in rec.items() if k != "l3_impl"})


def audit_task(w, jobs: list[dict], base: str, touch: str | None = None, zones: str | None = None) -> list[dict]:
    """A pool task: run ``jobs`` again on the worker's simulator (nothing written) and say of each whether its record
    is the one the cache folder ``base`` holds (:func:`bare`: ``same``); a job that raises is its ``error``."""
    sim = w.sim(False, deep=False)
    if getattr(w, "_reach_here", None) is None:
        w._reach_here = runner.here_cell(sim)
    out = []
    for job in jobs:
        try:
            rec = runner.run_job(sim, job, runner._touch(w, touch), w._reach_here, runner._zones(w, zones))
        except Exception as exc:          # noqa: BLE001 (a step stopped for time, or a bug: kept by name)
            out.append({"key": job["key"], "id": job["id"], "error": f"{type(exc).__name__}: {exc}"[:300]})
            continue
        want = cache.get(Path(base), job["key"])
        out.append({"key": job["key"], "id": job["id"], "same": want is not None and bare(rec) == bare(want)})
    return out


def hold_audit_task(w, items, base: str) -> list[dict]:
    """A pool task (Step R2.19f+'s X1: the hold answers in the audits): replay each (job key, outcome) of ``items``
    again on the worker's simulator (``hold.replay``, nothing written) and say of each whether its answer is the one
    the cache folder ``base``'s ``hold`` holds (:func:`bare`: ``same``); one that raises is its ``error``."""
    sim, b, rec, out = w.sim(False, deep=False), Path(base), None, []
    for job, k in items:
        rec = rec if rec is not None and rec["key"] == job else cache.get(b, job)
        o = rec["outcomes"][k]
        try:
            got = hold.replay(sim, rec["starts"][o["start"]], rec["heading"], o)
        except Exception as exc:          # noqa: BLE001 (a step stopped for time, or a bug: kept by name)
            out.append({"job": job, "outcome": k, "error": f"{type(exc).__name__}: {exc}"[:300]})
            continue
        want = cache.get(b / "hold", hold.key(job, k))
        out.append({"job": job, "outcome": k, "same": want is not None and bare(got) == bare(want)})
    return out


def x87_counts(folder: str | Path) -> dict:
    """The x87 check's counts the audit's workers wrote into ``folder`` as they exited (:func:`setup`): fast results
    and those that differ from softfloat, summed, and the workers that wrote a count; and the C walk's face decisions
    checked and those that differed from the game's (Step R2.19m)."""
    text = [p.read_text(encoding="utf-8", errors="replace") for p in sorted(Path(folder).glob("*.log"))]
    got = [m for t in text for m in X87_LINE.finditer(t)]
    walk = [m for t in text for m in WALK_LINE.finditer(t)]
    return {"results": sum(int(m[1]) for m in got), "differ": sum(int(m[2]) for m in got), "workers": len(got),
            "walk_checked": sum(int(m[1]) for m in walk), "walk_differ": sum(int(m[2]) for m in walk)}
