"""The world hold (Step 4.77e): a zone witness its frozen hold kept counts only where its whole-step replay holds.

The hold (:mod:`.hold`) replays a witness in player ticks: the player's own update on the snapshot's world, every
other object of the scene frozen, so an enemy never moves and a body still falling or sliding where the world would
carry it stands.  Whole steps (a scene FastL3, every object updated) agree with the game on 320 of Step 4.77d's 322
control rows, and 9 of those 322 that hold in player ticks don't in whole steps: an enemy's hit on 6, a false start
(w1 5212: the body still falling at the settle's end, then a level exit), an L3 fault and a hint popup.  So with
``reach-engine graph|witness --world`` each zone witness whose frozen hold answer stays (and which the router, under
``--rigs``, sent to no trip of its own) is replayed in whole steps (:func:`replay`, ``rigs.replay_trip``'s shape):
from the snapshot on a scene FastL3 that never ran (``rigs.fresh``) each try, idle 0, 15, 30 ... ticks first
(``rigs.EVERY``, at most ``rigs.PHASES`` tries), R6 onto its start, the settle, the kit, the string and ``hold.HOLD``
idle ticks, judged by the witness check v1's own rule (``witness_check.stands`` and ``judge``: the start stands in
its from-zone, alive throughout, in the to-zone at the string's end and settled there ``HOLD`` ticks on) with no level
exit (a fire's ``Row.exit`` or an unload).  The first try that holds is the answer (``held``, its ``wait``: the
witness then owes those idle ticks before its R6, as a routed one does); a witness no try holds is refused, and its
pair takes its next candidate.

A whole-step stop the game doesn't make on the first try is no refusal: an L3 fault (``stop`` ``fault``, as f2
a3191's ``unmapped@0x80023120`` two ticks after its R6, a whole-step emulation gap) or the game's hint popup, which
nothing here clears (``stop`` ``popup``: no player update, as w1 a1171's at tick 237).  The witness then keeps its
frozen hold's answer and its record names the stop (``held`` None), so the world refuses no witness for a defect of
its own (refusing the two would cost 2 of the game's 316 passes there, over the 0.5 % bar).  A later try's stop is
passed over.  A step stopped for time (``worker.TIME_SITES``: the host's load, never the game) is tried once more on
a new simulator, then raised as ``worker.StepTimeout``: no answer cached, so a re-run asks again.

Answers are cached apart (``world/``, :func:`key`: the hold's key, the snapshot's ``meta_sha12``, the zones judged,
the zoning and :func:`code12`), each holding the tries' verdicts, ticks and HP, no position.
"""

from __future__ import annotations

import functools
import hashlib
import json
import time
from pathlib import Path

from devkit.reach.engine import cache, hold, runner
from devkit.sim import l3
from devkit.sim.l3 import L3Error, Pad

POPUP = "no player update"   # L3's site for a step whose player update didn't run: the game's popup or a fade
EXIT = "level exit"          # ``l3.LevelExit``'s site: an unload's entry
HIT = 0x102                  # entity+0x94: the hit handler's state (witness_check.HIT): a diagnostic only

_ZONES: dict = {}            # each worker's level zone_at, once (``reach_engine._nodes``)


@functools.cache
def code12() -> str:
    """sha256[:12] of what a world answer depends on besides its hold key: this file's code, the whole-step pieces
    it runs (``rigs.fresh``, ``capped``, ``Clock``, ``_place``), the check's rule (``witness_check.stands``,
    ``judge``) and their constants, and the L3 core."""
    import inspect
    from devkit.reach import witness_check as wc
    from devkit.reach.engine import rigs
    h = hashlib.sha256(cache.core().encode() + cache.code_bytes(Path(__file__)))
    for f in (rigs.fresh, rigs.capped, rigs.Clock, rigs._place, wc.stands, wc.judge, wc._settled, wc._fields,
              wc._feet):
        h.update(inspect.getsource(f).encode())
    h.update(repr((rigs.EVERY, rigs.PHASES, rigs.CAP_US, hold.HOLD, wc.HOLD, wc.DEAD, runner.SETTLE_START,
                   runner.START_XY, runner.START_Z)).encode())
    return h.hexdigest()[:12]


def key(hold_key: str, meta_sha12: str, to: str, frm: str | None, zoning: str) -> str:
    """A world answer's cache key: its witness's hold key, the snapshot, the zones it is judged in (``to``, and
    ``frm`` its start's), the zoning they are named under and :func:`code12`."""
    doc = {"hold": hold_key, "snap": meta_sha12, "to": to, "from": frm, "zoning": zoning, "code": code12()}
    return hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest()[:12]


def pairs(path) -> set[tuple[str, str]]:
    """The zone pairs a ``--world-pairs`` file lists: a JSON list (or ``{"pairs": [...]}``) of ``[from, to]`` pairs
    or ``"from>to"`` strings."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    out = set()
    for p in doc["pairs"] if isinstance(doc, dict) else doc:
        a, b = p.split(">") if isinstance(p, str) else p
        out.add((str(a), str(b)))
    return out


def _try(sim, st: dict, heading: float, o: dict, pads: list, wait: int, to: str, frm: str | None, zone_at) -> dict:
    """One try of :func:`replay` on ``sim`` (a scene FastL3 that never ran): its verdict (``held``, else ``cause``
    or ``stop``), the site that stopped it, the ticks from its R6 (``ticks``), the HP, the first hit-state and exit
    ticks and its whole steps."""
    from devkit.reach import witness_check as wc
    from devkit.reach.engine import rigs
    sim.deep = True                       # the check's settled rule reads the observation (AZ-737)
    clock = rigs.Clock(sim)
    rows, step = [], sim.step

    def traced(*a, **k):
        r = step(*a, **k)
        rows.append(r)
        return r
    sim.step, site, n_kit = traced, None, 0
    try:
        clock.at(wait)
        rigs._place(sim, st["feet"], st.get("yaw", heading), st["cell"])
        n_kit = len(runner.set_kit(sim, o["kit"]))
        for p in [*pads, *[Pad()] * hold.HOLD]:
            sim.step(p, timeout_us=rigs.CAP_US)
    except L3Error as exc:
        site = l3.fault_site(exc)
    finally:
        sim.step = step
    at = wait + runner.SETTLE_START          # the settle's last row (row ``wait`` is the R6's)
    s = wc.stands(rows[at] if len(rows) > at else None, st["feet"], zone_at, frm)
    j = wc.judge(rows, wait + 1 + runner.SETTLE_START + n_kit + len(pads), to, zone_at)
    ex = next((k for k, r in enumerate(rows) if r.exit is not None), None)
    hit = next((k for k in range(wait, len(rows)) if rows[k].state == HIT), None)
    t = {"wait": wait, "ticks": max(len(rows) - wait, 0), "steps": clock.steps + len(rows) - wait,
         "stands": s["stands"], "hp_min": j["hp_min"], "alive": j["alive"], "in_to_end": j["in_to_end"],
         "settled_in_to": j["held"], "hit_tick": None if hit is None else hit - wait,
         "exit_tick": None if ex is None else ex - wait}
    if site is not None:
        t["site"] = site
    if s["stands"] is False:
        return t | {"held": False, "cause": "start"}
    if site is not None and site != EXIT:
        return t | {"held": None, "stop": "popup" if site == POPUP else "fault"}
    if site == EXIT or ex is not None:
        return t | {"held": False, "cause": "exit"}
    if j["pass"]:
        return t | {"held": True}
    return t | {"held": False, "cause": "dead" if not j["alive"] else "left" if j["in_to_end"] else "path"}


def replay(make, st: dict, heading: float, o: dict, to: str, frm: str | None, zone_at, waits: int | None = None) -> dict:
    """Witness ``o`` of start ``st`` (at its ``yaw``, else ``heading``) in whole steps (the module docstring): each
    try on a new scene FastL3 (``make()``), idle 0, ``rigs.EVERY``, 2 ``rigs.EVERY`` ... ticks first (``waits``
    tries, by default ``rigs.PHASES``), judged in zone ``to`` from ``frm`` (None: its start's zone isn't asked) by
    ``zone_at``: ``held`` True (``wait`` the first try's that held), False (refused: no try held, ``cause`` the first
    try's) or None (the first try stopped: ``stop``, ``site`` and its ``tick`` from the R6), with ``tries``, every
    try's verdict and the whole steps."""
    from devkit.reach.engine import rigs, worker
    pads, out, steps = l3.pads(o["segments"]), [], 0
    for k in range(rigs.PHASES if waits is None else waits):
        for again in (False, True):
            t = _try(make(), st, heading, o, pads, k * rigs.EVERY, to, frm, zone_at)
            steps += t["steps"]
            if not t.get("site", "").startswith(worker.TIME_SITES):
                break
            if again:
                raise worker.StepTimeout(f"a whole step stopped for time twice ({t['site']}): the host's load")
        out.append(t)
        if t["held"] or (t["held"] is None and k == 0):
            break
    first, last = out[0], out[-1]
    got = {"held": last["held"] if last["held"] or len(out) == 1 else False, "tries": len(out), "steps": steps,
           "trace": [{x: t.get(x) for x in ("wait", "held", "cause", "stop", "site", "ticks", "hp_min", "hit_tick",
                                              "exit_tick")} for t in out]}
    if got["held"]:
        return got | {"wait": last["wait"]}
    if got["held"] is None:
        return got | {"stop": first["stop"], "site": first["site"], "tick": first["ticks"]}
    return got | {"cause": first["cause"]}


def summary(got: dict) -> dict:
    """What a witness record's ``l3`` keeps of world answer ``got`` (``"world"``): held and its wait, or the stop."""
    if got["held"]:
        return {"held": True, "wait": got["wait"], "code": code12()}
    return {"held": None, "stop": got["stop"], "site": got["site"], "tick": got["tick"], "code": code12()}


def _zone_at(level: str):
    if level not in _ZONES:
        from devkit.reach.reach_engine import _nodes
        _ZONES.clear()
        _ZONES[level] = _nodes(level).zone_at
    return _ZONES[level]


def task(w, items: list, base: str, level: str, meta_sha12: str, zoning: str) -> tuple[int, float]:
    """A pool task: :func:`replay` each (job key, outcome, to-zone, from-zone) of ``items`` on new scene FastL3s
    (``rigs.fresh``) in ``level``'s zones, each answer cached under :func:`key` with its CPU-s; their whole steps
    and CPU-s."""
    from devkit.reach.engine import rigs
    b, rec, steps, cpu = Path(base), None, 0, 0.0
    (b / "world").mkdir(mode=0o700, exist_ok=True)
    zone_at = _zone_at(level)
    for job, k, to, frm in items:
        rec = rec if rec is not None and rec["key"] == job else cache.get(b, job)
        o, c0 = rec["outcomes"][k], time.process_time()
        got = replay(lambda: rigs.fresh(w), rec["starts"][o["start"]], rec["heading"], o, to, frm, zone_at)
        got["cpu_s"] = round(time.process_time() - c0, 3)
        cache.put(b / "world", key(hold.key(job, k), meta_sha12, to, frm, zoning), got)
        steps, cpu = steps + got["steps"], cpu + got["cpu_s"]
    return steps, cpu
