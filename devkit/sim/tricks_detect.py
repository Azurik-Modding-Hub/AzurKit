"""The trick detectors and the trace miner (Step TD.3, D253; the trick-discovery plan §3.5): which tricks a string
used, named from its per-tick rows, the same way for an L3 string and an owner's demo trace.

A string's rows become :class:`Tick`\\ s (:func:`from_l3`: L3 rows and the pads that made them; :func:`from_trace`:
``xemu_demo.py``'s recorder rows, whose older traces lack the stored normal and the animation index, so the
rules that need them fall back as below).  :func:`mine` counts a stretch: each button's presses (rising edges),
takeoffs (entries into the airborne states 2 and 0x102 from any other), slope contacts (entries into the slope state
3), slides (into 4), hoists and every label :func:`detect` gives.  The labels, each at its key tick, from the game's
rules (``docs/RE_MOVEMENT.md`` "The contact rules", the roll and the hoist; ``tricks.toml``'s mechanisms):

- ``HOIST``: the airborne tick's ledge hoist 0x86920 (the lip lift): state 0x100 straight from the air (2), the
  ``hoist`` clips 65 (tall, 88 ticks) or 66 (short, 36) where the animation is read [verified xemu X.35: 35 hoist
  starts, each from state 2]; without it, no attack press in the last :data:`ATTACK_TICKS` ticks;
- ``STEP_UP``: the walk's step-up 0x8B1D0, state 0x100 from the ground (0) with clip 53 (``step_up``), or with no
  animation read and no attack press near;
- ``ROLL_CHAIN``: a roll (BLACK's ``roll forward``, clip 102, 21 rows of 0x100 [verified xemu skips-a A1]) chained by
  presses on its ticks 12-20 into one 0x100 run, a roll each :data:`ROLL_PERIOD` ticks [skips-a A4/A5]: two or more;
- ``ROLL_JUMP_AIR`` / ``ROLL_JUMP``: the end-tick jump (0x100 straight to 2 with Y held on the roll's last tick or
  the next: state 0's ground handler runs on the roll's end tick even in mid-air and its jump has no ground test,
  ``tricks.toml`` rjump), in mid-air when the body fell :data:`FALL_M` during the roll or was falling at its end; a
  roll that ends in the air with no Y held is a roll off an edge, unlabelled;
- ``SLOPE_HOP`` (``SLOPE_RECAST_HOP`` with an LT+Y recast in its flight): a jump from the slope or slide state (3, 4;
  the jump goes along the face's normal and keeps the slide speed, 0x89060), a Y press at the takeoff;
- ``STEEP_WALK``: at least :data:`STEEP_TICKS` walking ticks (state 0: on 0.7071 < nz < 0.8 the walk, with step-ups;
  under it the slope state 3/4 unless the face isn't slippery) on a face of 0.6 < nz < 0.8 (off the logic's floor
  rule, nz >= 0.8) rising :data:`STEEP_RISE` m or more (needs the stored normal);
- ``TJUMP_CHARGE``: two or more Y presses in the catch (0x101) with the charge, the velocity along the stored wall
  normal's horizontal, up two presses' worth (``l3_explore.charge``; the charge law, the plan §4's declared leak);
- ``DEFLECT_LAUNCH``: an airborne tick with no Y press whose vz rises :data:`DEFLECT_DV` m/s or more while the
  horizontal speed falls, on a steep stored normal (nz <= 0.6): the contact projection v' = v - (v.n)n turning
  speed into lift (0x47380, verified static).

- ``CANDIDATE`` (the plan §3.5's candidate new option): an 0x100 run no rule above names and no attack press in the
  last :data:`ATTACK_TICKS` ticks explains (e.g. one entered from the slope state), with the state before it and its
  clip; other unrecognised signatures aren't mined.

Not here: ``AIMED_DESCENT`` (an option's control pattern, not a game event) and ``ITRIG`` (a trigger touch needs the
trigger meshes and whole steps: TD.4's miner).  Labels only: no detector steers a search.  A tick holds no position
but the body's height, in memory; the counts and labels are coordinate-free.
"""

from __future__ import annotations

import math
from typing import Iterable, NamedTuple

AIRBORNE = frozenset({2, 0x102})
GROUND, CLIMB, AIR, SLOPE, SLIDE, ATTACK, CATCH = 0, 1, 2, 3, 4, 0x100, 0x101
HOIST_ANIMS = frozenset({65, 66})     # garret4's hoist clips: 65 the tall hoist (88 ticks), 66 the short (36)
STEP_ANIM, ROLL_ANIM = 53, 102        # step_up; roll forward
ROLL_TICKS, ROLL_PERIOD = 21, 19      # a roll's rows of 0x100; a chained roll's start every 19 [verified xemu skips-a]
ATTACKS = frozenset({"a", "b", "x", "rt", "black"})
ATTACK_TICKS = 10                     # an attack press this recent explains an 0x100 the animation doesn't name
ANIM_TICKS = 3                        # an 0x100 run's clip is read over its first ticks
FALL_M = 0.5                          # a roll that dropped this far ended in the air
STEEP_NZ, STEEP_TICKS, STEEP_RISE = (0.6, 0.8), 10, 0.5
DEFLECT_DV, DEFLECT_NZ = 1.0, 0.6
CHARGE_STEP = 0.95 * 4.6434           # l3_explore.CATCH_STEP (copied: the miner loads no L3 or numpy)
HELD = 0.5                            # a recorder pad float at or above this is a held button
_TRACE_BUTTONS = {"a": "a", "b": "b", "x": "x", "y": "y", "blk": "black", "wht": "white", "lt": "lt", "rt": "rt"}
__all__ = ["Tick", "Event", "from_l3", "from_trace", "detect", "mine"]


class Tick(NamedTuple):
    """The player after one tick: its state, the buttons held, velocity (m/s), the body's height (m: in memory
    only), the animation index, flaps used and the stored contact normal (None where the source doesn't read it)."""
    state: int
    buttons: frozenset
    vel: tuple
    z: float
    anim: int | None = None
    flaps_used: int = 0
    normal: tuple | None = None


class Event(NamedTuple):
    """A label at tick ``at`` (an index into the ticks), lasting ``ticks``, with coordinate-free ``info``."""
    name: str
    at: int
    ticks: int
    info: dict


def from_l3(rows, pads) -> list[Tick]:
    """L3 rows (each with its ``obs``) and the pads that made them, one each."""
    out = []
    for r, p in zip(rows, pads):
        o = r.obs
        out.append(Tick(r.state, frozenset(p.buttons), tuple(o.vel), r.pos[2], o.anim, o.flaps_used or 0,
                        None if o.normal is None else tuple(o.normal)))
    return out


def from_trace(rows: Iterable[dict]) -> list[Tick]:
    """``xemu_demo.py``'s recorder rows (those with ``n``): ``st``, ``vel``, ``body``, ``fl``, ``pad`` and,
    from Step TD.0 on, ``nrm`` and ``anim``."""
    out = []
    for r in rows:
        if "n" not in r:
            continue
        pad = r.get("pad") or {}
        out.append(Tick(r["st"], frozenset(b for k, b in _TRACE_BUTTONS.items() if (pad.get(k) or 0.0) >= HELD),
                        tuple(r["vel"]), r["body"][2], r.get("anim"), r.get("fl") or 0,
                        tuple(r["nrm"]) if r.get("nrm") else None))
    return out


def _edges(ticks: list[Tick], button: str) -> list[int]:
    return [k for k, t in enumerate(ticks) if button in t.buttons and (k == 0 or button not in ticks[k - 1].buttons)]


def _runs(ticks: list[Tick], pred) -> list[tuple[int, int]]:
    """(first, last) index of each maximal run of ticks ``pred`` holds for."""
    out, k = [], 0
    while k < len(ticks):
        if pred(ticks[k]):
            j = k
            while j + 1 < len(ticks) and pred(ticks[j + 1]):
                j += 1
            out.append((k, j))
            k = j + 1
        else:
            k += 1
    return out


def _pressed(edges: list[int], k: int, back: int) -> bool:
    return any(k - back <= e <= k for e in edges)


def _charge(t: Tick) -> float | None:
    n = t.normal
    if n is None:
        return None
    h = math.hypot(n[0], n[1])
    return (t.vel[0] * n[0] + t.vel[1] * n[1]) / h if h > 1e-6 else None


def detect(ticks: list[Tick]) -> list[Event]:
    """Every label the module docstring lists, in tick order."""
    ev: list[Event] = []
    attack = sorted(e for b in ATTACKS for e in _edges(ticks, b))
    y, black = _edges(ticks, "y"), _edges(ticks, "black")
    cast = [k for k, t in enumerate(ticks) if {"lt", "y"} <= t.buttons
            and (k == 0 or not {"lt", "y"} <= ticks[k - 1].buttons)]
    for a, b in _runs(ticks, lambda t: t.state == ATTACK):
        before = ticks[a - 1] if a else None
        anims = {t.anim for t in ticks[a:min(b, a + ANIM_TICKS - 1) + 1]} - {None}   # a demo's anim log lags a tick

        def clip(want, otherwise) -> bool:
            return bool(anims & want) if anims else otherwise
        if before is not None and before.state == AIR and clip(HOIST_ANIMS, not _pressed(attack, a, ATTACK_TICKS)):
            ev.append(Event("HOIST", a, b - a + 1, {"anim": min(anims & HOIST_ANIMS, default=None),
                                                    "rise_m": round(ticks[b].z - before.z, 2)}))
            continue
        if before is not None and before.state == GROUND and clip({STEP_ANIM}, not _pressed(attack, a, ATTACK_TICKS)):
            ev.append(Event("STEP_UP", a, b - a + 1, {"rise_m": round(ticks[b].z - before.z, 2)}))
            continue
        if not clip({ROLL_ANIM}, _pressed(black, a, 3)):
            if not _pressed(attack, a, ATTACK_TICKS):
                ev.append(Event("CANDIDATE", a, b - a + 1, {"from": None if before is None else before.state,
                                                            "anim": min(anims, default=None)}))
            continue
        n = b - a + 1
        rolls = 1 + max(0, round((n - ROLL_TICKS) / ROLL_PERIOD))
        if rolls >= 2:
            ev.append(Event("ROLL_CHAIN", a, n, {"rolls": rolls}))
        if b + 1 < len(ticks) and ticks[b + 1].state == AIR and any("y" in t.buttons for t in ticks[b:b + 2]):
            air = ticks[a].z - ticks[b].z >= FALL_M or ticks[b].vel[2] < -1.0
            ev.append(Event("ROLL_JUMP_AIR" if air else "ROLL_JUMP", b + 1, 1,
                            {"rolls": rolls, "vz": round(ticks[b + 1].vel[2], 3)}))
    for a, b in _runs(ticks, lambda t: t.state in AIRBORNE):
        if a == 0 or ticks[a - 1].state not in (SLOPE, SLIDE) or not _pressed(y, a, 2):
            continue
        recasts = sum(a <= c <= b for c in cast)
        ev.append(Event("SLOPE_RECAST_HOP" if recasts else "SLOPE_HOP", a, b - a + 1,
                        {"from": ticks[a - 1].state, "recasts": recasts,
                         "flaps": max(t.flaps_used for t in ticks[a:b + 1]) - ticks[a - 1].flaps_used,
                         "rise_m": round(max(t.z for t in ticks[a:b + 1]) - ticks[a - 1].z, 2)}))
    lo, hi = STEEP_NZ
    for a, b in _runs(ticks, lambda t: t.state == GROUND and t.normal is not None and lo < t.normal[2] < hi):
        rise = ticks[b].z - ticks[a].z
        if b - a + 1 >= STEEP_TICKS and rise >= STEEP_RISE:
            ev.append(Event("STEEP_WALK", a, b - a + 1, {"rise_m": round(rise, 2)}))
    for a, b in _runs(ticks, lambda t: t.state in (CATCH, CLIMB)):
        presses = sum(a <= e <= b and ticks[e].state == CATCH for e in y)
        qs = [q for t in ticks[a:b + 1] if t.state == CATCH and (q := _charge(t)) is not None]
        if presses >= 2 and qs and max(qs) - qs[0] >= 2 * CHARGE_STEP:
            ev.append(Event("TJUMP_CHARGE", a, b - a + 1, {"presses": presses, "charge_mps": round(max(qs), 1)}))
    for k in range(1, len(ticks)):
        t, p = ticks[k], ticks[k - 1]
        n = t.normal
        if t.state != AIR or n is None or n[2] > DEFLECT_NZ or _pressed(y, k, 2):
            continue
        dv = t.vel[2] - p.vel[2]
        if dv >= DEFLECT_DV and t.vel[2] > 0 and math.hypot(*t.vel[:2]) < math.hypot(*p.vel[:2]) - 0.5:
            ev.append(Event("DEFLECT_LAUNCH", k, 1, {"dvz": round(dv, 2), "vz": round(t.vel[2], 2)}))
    return sorted(ev, key=lambda e: (e.at, e.name))


def mine(ticks: list[Tick]) -> dict:
    """A stretch's counts (the module docstring): presses per button, takeoffs, slope contacts, slides, hoists and
    every label's count."""
    def entries(states) -> int:
        return sum(t.state in states and (k == 0 or ticks[k - 1].state not in states) for k, t in enumerate(ticks))
    labels: dict[str, int] = {}
    for e in detect(ticks):
        labels[e.name] = labels.get(e.name, 0) + 1
    buttons = sorted({b for t in ticks for b in t.buttons} | {"black", "y"})
    return {"ticks": len(ticks), "presses": {b: len(_edges(ticks, b)) for b in buttons},
            "takeoffs": entries(AIRBORNE), "slope_contacts": entries({SLOPE}), "slides": entries({SLIDE}),
            "hoists": labels.get("HOIST", 0), "labels": dict(sorted(labels.items()))}
