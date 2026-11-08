"""The D172 chain driver (Step X.12, D173's T7): snapshot -> L3 search -> xemu replay, segment after segment, in one
sandbox, with no player update between two segments left unrecorded.

A chain is a list of segments, each a start, a goal, a kit and a tier: a plan's spoiler paths
(``azurkit.tools.randomizer.planner.plan.chain_segments``: each hop of an item's obtain path on its level-file edge, the
pickup, and the hops of its return path), R1.16's input.  For each segment the driver

1. takes its start: an L3 snapshot where the chain stands (the first after the start's set-up; then ``here=True``, exactly
   at the player's update entry where the last replay or drain halted: D172's exact join), linked to its parent
   (that start's metadata hash, the string that left it and the drained ticks), and parks it (``Sandbox.park``:
   ``savevm`` into the sandbox's own HDD clone, the guest held halted) so the sandbox can be released during a long
   search and the start brought back bit-identical (``Sandbox.unpark``);
2. searches a string in L3 (``l3_search.solve`` on a worker pool kept for the start, ``l3_pool``; the goal
   ``l3_goal``'s: a walk's to-node, an exit's trigger, a pickup's location), seeded by the route planner's plan and by
   the strings that failed before; a search that found nothing is inconclusive when any run was tainted; each run's
   cost-to-go curve, stall and steps a second go in the record, and ``--plateau N`` (Step X.95; off by default) ends
   a seed whose best cost to go hasn't fallen in N steps on every rung (``Limits.plateau``: a cut of the same run,
   so a string found before it is the same string), the 4x rung passed over when every seed ended at its plateau
   (the same seeds would end there again); ``--l3 fast`` runs the pool's searches on FastL3 (``sim.l3_fast``, as
   the reach engine's pool: its records are base L3's), ``--l3 base`` on round 1's L3;
3. replays it in xemu from that same start (``Sandbox.replay`` with ``stops``): a popup or a dialog on the way (a
   first gem, a power-up) is cleared with A through the pad FIFO and the replay resumes at the next tick; a level
   load ends it; the outcome is checked: the replay equal to L3 tick for tick and the goal reached (a walk; a
   diverged one by xemu's own last tick), the destination loaded (an exit), the inventory changed (a pickup); each
   replay goes into the private conformance corpus (``devkit.sim.corpus``);
4. drains from where the replay halted: the neutral pad at each of the player's updates (each one counted in the
   chain), through a level load and any popup, until the player has stood ``SETTLE`` ticks in the new level or
   after the pickup, halted at an update entry: the next segment's start;
5. repairs a failure: a search that found nothing again with 4x the budget, then a broader exploration, then the
   phys profile's graph; a replay that diverged or missed its goal is re-anchored (a new snapshot where it halted, its
   ticks kept in the chain as a piece, or the parked start brought back when the player died or left the level)
   and searched again; after ``repairs`` the chain stops, naming the segment and why.

A hop on d1's central elevator (``rig``, Step R1.16d) is no search: :meth:`Chain.ride` reads the elevator's wiring
live (each colour's floor, the floor switches' toggles and keys), plans the fewest presses and rides
(:func:`lift_plan`) and plays them with real pad input in closed loop, planning again after each: a floor switch
pressed with X, a call field walked into until the deck has come, the deck boarded and its colour's button pressed.

The public record (``chain.json``, in the sitting's evidence folder) holds per segment its start (metadata and
pages hashes, the parent link, the parked tag), each attempt (the search's counts, seconds and robustness, the
replay's comparison, the outcome, the drain), and its input string (run-length pads: sticks, buttons, the camera as
f32 pairs; ``input = "analog-ram"``) with its sha12: no position, no RAM.  Snapshots go to the private L3 store
(deleted at the sitting's teardown unless kept); parked states live in the sandbox's HDD clone (W, mode 700) and go
with it.

    uv run --locked python -m devkit xemu chain segments [--plan PLAN] [--sphere N] [--item I] [--back] [--tour S...]
    uv run --locked python -m devkit xemu chain run BUILD [--plan PLAN] [--sphere N] [--item I] [--back] [--tour S...]
                                  [--segments FILE] [--tag T] [--save S] [--first K] [--hop LEVEL SPOT] [--no-park]
                                  [--release no|yes|waiting] [--robust N] [--jobs N] [--steps S] [--scene yes|no|diverged]
                                  [--plateau N] [--l3 fast|base]
    uv run --locked python -m devkit xemu chain park-check      # the parked-start measurement (one short sitting)

In a sitting (``sitting.Sitting``, or its exec server): ``xc.park_check(s)``, then the start (``boot_start``:
the build booted, the plan's kit), optionally an R7 hop (``s.hop``), and ``xc.Chain(s, segs, out=...).run()``.  The
sitting's sandbox is deterministic by default (Step X.22: the null renderer under -icount, so a replay from a parked
start gives the same RAM every time; ``chain.json``'s settings say whether it was).  Dev only (devkit, Step 4.13d2),
never a player's verb and never in pytest (D11); the sandbox rules are the azurik-xemu-oracle skill's.  Nothing here prints game bytes or
positions.
"""

from __future__ import annotations

import argparse
import collections
import contextlib
import hashlib
import json
import math
import os
import struct
import sys
import time
from pathlib import Path

from azurkit.tools.randomizer.live import recipes
from devkit.reach import l3_certify as lc   # the private folder, the goal module
from devkit.sim import corpus, douse as dz, l3
from devkit.sim.douse import ELEM_BTN, THROUGH_EVERY, THROUGH_IN, THROUGH_MAX
from devkit.sim.l3 import Pad
from devkit.sim.l3_search import Limits, Seg, Segment, expand, seg_list, segments as run_length, solve, \
    start_of, string_sha12
from devkit.xemu import oracle as xo
from devkit.xemu import sitting as xs

FORMAT = "azurik-chain/1"
SETTLE = 6            # ticks at rest (standing or swimming) after a level load or a pickup before a drain joins
STALL_S = 4.0         # no player update for this long: a popup, a dialog or a cutscene (A clears it)
LOAD_S = 90.0         # a level load's longest wait for the player's first update
A_MAX = 8             # A presses a drain makes at most
POPUPS = 6            # popups a replay clears and resumes after, at most
DRAIN_MAX = 900       # neutral ticks a drain writes at most (30 s)
DIVERGE_M = 0.1      # a replay this far off L3's body centre (or in another state or HP) stops there: re-anchor
DEEP_TICKS = 600      # a replay this long or shorter reads the deep observation (the kit, inventory, flags: about 40
                      # more debugger reads a tick, X.10); a longer one the core (body, velocity, state, HP, flaps)
# robustness -> the tier it supports (devkit/reach/l3_certify.py's, D259, replacing P13's proposal); a plan's safe tier asks
# standard's (Safe folds into Standard)
TIERS = lc.TIERS
RANK = {t: i for i, (t, _) in enumerate(TIERS)} | {"safe": 0}
ROBUST = ({"seg": 12}, {"seg": 5, "pursue": 0.8})   # the re-search's shapes (another problem, other seeds) when a
                                                    # winner's tier is harder than the plan's (Step X.19)
SCENE_TRIALS = 8      # a whole-step winner's robustness trials (each a whole-step run of the string: x19d's took ~15 min
                      # at 16 trials)
ROBUST_S = 600.0      # each re-search's wall cap (sitting x19: whole-step searches by w1's rocks took ~20 min each)
EXITS = ("exit", "cart", "teleport")                # segments a level load ends (an ExitGoal on the exit's trigger)
ACTIONS = ("minigame", "barrier", "button", "event", "warp")   # an approach (a walk to the object), then real input
ACT_DRAIN = 2400      # neutral ticks a drain after an action writes at most (a cutscene, a cart ride, a teleport)
GEN_LIST, GEN_LINK = 0x44, 0x1EC   # a critterGenerator node's list of its critters; that link's offset in a critter
TOUCH_WAIT = 30      # ticks a touch event's shape is watched for its touch, standing where the approach ended
TOUCH_PLUG = 5       # a shape's plug its touch drives links from (d1.xbr: walkwayGenerator:BaseShape > its combiner)
TOUCH_TRIES = (("centre", 90), ("hop", 60), ("across", 120))   # a platform stood on and untouched: these ways, each at
                     # most these ticks (AZ-497), watched as the stand is
TOUCH_MID = 0.3      # metres (horizontal) from a platform's middle its ``centre`` try stands within
SPAWN_TICKS = 450     # a boss fight's wait for its generator's critter (15 s), then once more after a call field's touch
FIGHT_TICKS = 9000    # a boss fight's closed loop: at most these player ticks (5 min), in FIGHT_CHUNK pieces
FIGHT_CHUNK = 450
FIGHT_STAFFS = (("water",), ("earth", "fire"), ("earth", "air"), ("earth", "water"), ("fire", "water"))
                      # an unassisted fight's staffs, one a piece in turn: config.xbr's magic rows of type staff that
                      # cost 1 fuel a hit from each element (W watr, EF fire, EA wind, EW acid, FW stem); E, A and F
                      # alone are armors (AZ-499: R1.16f's fire, air and earth "staffs" cast the armor and spent fuel)
FIGHT_REACH = 2.6     # metres (horizontal, centre to centre) the player closes to before swinging; down to FIGHT_CLOSE
                      # when the swings stop landing; an unassisted fight holds ground while he is beyond it
FIGHT_CLOSE = 1.4     # the reach's floor (in the kept fights his HP fell in pieces at a 1.4 m reach, once by 160 at
                      # 2.2 m: R1.16f's chain-review/results/fight-reach)
FIGHT_SWING = 2.2     # where an unassisted fight swings from: he attacks from his attackRange 2 m and came no nearer
                      # than 1.8 m in sitting r125-full-h (0 swings in 2,080 ticks at 1.4 m)
PILOT_TICKS = 4800    # the route pilot's closed-loop walk (``pilot``): at most these player ticks (160 s; r116-final-b: town's
                      # grate elevator hop used 2,400 and stood on the rig leg when they ran out)
# the repair ladder for a search that finds nothing: (budget multiplier, route profile, the search's shape): the
# budget, 4x the budget, a broader exploration (cells picked less greedily, less guidance: a hand edge the derive has
# no way for, whose straight-line guidance leads to a wall), the phys profile's graph
LADDER = ((1, "logic", {}), (4, "logic", {}), (4, "logic", {"temp": 30.0, "pursue": 0.3}), (4, "phys", {}))
SCENE_COST = 10       # a whole step costs about this many player ticks (X.6: 10-25x): a whole-step search's budget is
                      # the steps over this, so it takes about the same time
STUCK_CELLS = 8       # a failed search from a re-anchor whose every run kept this few cells: the body is stuck there
                      # (sitting x19: on w2's slippery ice-cave stairs, 4 cells in 2 h): back to the start before it
SCENE_AFTER = 300     # a replay that diverges this many ticks in or later keeps player ticks from its re-anchor (sitting
                      # x19: the hose console's 2,700-tick approach left L3 at tick 1,139; whole steps for the rest
                      # ran 2 h): ``scene="diverged"`` switches only when the world pushes the player sooner
BEACH = [{"n": 20, "stick": [0, 1]}, {"n": 6, "stick": [0, 1], "buttons": ["y"]}, {"n": 40, "stick": [0.5, 0.8]},
         {"n": 40, "stick": [-1, 0], "yaw": 1.0}]   # sittings/l3-replay.toml's string (X.6: replayed exactly)


L3_DEFAULT = "fast"   # the searches' simulator by default (``--l3``; the reach engine's too, Step R2.19a)


def l3_library(mode: str) -> str:
    """Which libunicorn a ``mode`` search pool's workers load: the patched build (``l3_fast.worker_env``) for fast
    once it is built, else the stock wheel."""
    from devkit.reach import l3_fast
    return "patched" if mode == "fast" and l3_fast.worker_env() else "wheel"


def tier_of(robustness: float | None) -> str | None:
    """The movement tier a string's robustness supports (D259; under 5%, or only an exact string, frame_perfect)."""
    if robustness is None:
        return None
    return next(t for t, floor in TIERS if robustness >= floor)


_ROUTERS: dict[tuple, object] = {}


def router(level: str, prof: str = "logic"):
    """The level's route graph for ``prof`` from the reach model of the current derive's zoning
    (``l3_certify._reach_path``), kept per process."""
    from devkit.rando.draft.l3_goal import load_router
    key = (str(lc._reach_path(level)), prof)
    if key not in _ROUTERS:
        _ROUTERS[key] = load_router(key[0], prof)
    return _ROUTERS[key]


def golden_plan(db) -> dict:
    """The golden seed's plan file under the database's defaults (the seed ``devkit/rando/restack.py`` keeps at
    ``devkit.rando.DEFAULT_SEED``: it moves when the data stops filling the old one), as ``azurkit plan`` writes it."""
    from devkit.rando import DEFAULT_SEED
    from azurkit.tools.randomizer.planner.fill import fill
    from azurkit.tools.randomizer.planner.plan import plan_doc
    from azurkit.tools.randomizer.planner.solver import Logic
    return plan_doc(fill(Logic(db), DEFAULT_SEED, db.defaults), db)


def plan_segments(plan: Path | str | None = None, sphere: int = 1, item: int = 0, back: bool = False,
                  tour: list[int] | None = None, *, merge: bool = True, counted: bool = True, victory: bool = False,
                  start: str | None = None) -> tuple[list[dict], dict]:
    """(the segments of a plan's progression item ``item`` of sphere ``sphere``, or with ``tour`` the tour of those
    spheres from ``start`` (the world's start; ``plan.tour_segments``: item to item, the counted ones with
    ``counted``, the actions the logic only credits, back to the start with ``back``, to the victory with
    ``victory``), its consecutive plain walks merged with ``merge`` (``plan.merge_walks``, Step R1.16), the plan's
    identity, with ``discs`` the disc fragments the tour's first sphere holds: a placed start's kit).  ``plan``
    None: the golden seed's (:func:`golden_plan`); the build a chain plays must be that plan's (``azurkit build
    --seed`` of its seed)."""
    from azurkit.tools.randomizer.planner.plan import chain_segments, load_plan, merge_walks, spheres, tour_segments
    from azurkit.tools.randomizer.planner.solver import Logic
    db = database()
    p = load_plan(Path(plan) if plan is not None else golden_plan(db), db)
    ident = {"sha256": p.doc["sha256"], "seed": p.doc["seed"], "share": p.doc["share"], "sphere": sphere,
             "item": item}
    if tour:
        logic = Logic(db)
        played = spheres(p, logic)
        segs = tour_segments(p, logic, tour, back=back, counted=counted, victory=victory, start=start, played=played)
        held = played[min(tour) - 1].counters
        discs = {e: min(4, held.get(f"disc{e[0]}", 0)) for e in ("earth", "air", "fire", "water", "life")}
        return (merge_walks(segs) if merge else segs), {
            **ident, "tour": sorted(tour), "item": None, "merged": merge, "counted": counted, "victory": victory,
            "start": start, "discs": {e: n for e, n in discs.items() if n}, "keys": tour_keys(segs, held, db)}
    return chain_segments(p, Logic(db), sphere, item, back=back), ident


def read_segments(path: Path) -> tuple[list[dict], dict]:
    """(the segments, the plan's identity) a ``segments`` run printed into ``path``: its identity line, then one
    segment a line.  A plan another database made (``load_plan`` refuses it: the frozen plans after a logic change)
    plays from the segments the code that made it printed (Step R1.25)."""
    lines = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    if not lines or "sha256" not in lines[0] or not all("index" in sg for sg in lines[1:]):
        raise SystemExit(f"{path}: not a `segments` print (the plan's identity, then a segment a line)")
    return lines[1:], {**lines[0], "segments_file": path.name}


def tour_keys(segs: list[dict], held: dict, db=None) -> dict[str, int]:
    """A placed start's keys (R2, Step R1.16): {key fourcc: count} for the keylocks the tour's button segments use,
    each type no more than the start holds (``held``, the counters before the tour's first sphere; a key the tour
    picks up itself is played, not given)."""
    locks = {k["id"]: k for doc in (db or database()).generated.values() for k in doc.get("keylocks", ())}
    need: dict[str, list] = {}
    for sg in segs:
        if sg["kind"] == "button" and (k := locks.get(sg["goal"])):
            need.setdefault(k["key_fourcc"], [k["consumes"], 0])[1] += 1
    return {tag: min(n, held.get(counter, 0)) for tag, (counter, n) in need.items() if held.get(counter, 0)}


def segs_of(runs: list[dict]) -> list[tuple]:
    """A run-length pad string (``l3_search.segments``'s: a proof's or a chain record's) as seed segments
    ``(n, heading, hold, roll, cast)``: the heading the stick and the camera give (``inputs.stick`` inverted, within
    its 5-degree snap), Y held for the run when it holds Y, BLACK a roll, LT+Y a cast."""
    out = []
    for r in runs:
        sx, sy = r["stick"]
        if "cam" in r:
            cam = math.atan2(-r["cam"][0], r["cam"][1])
        else:
            cam = r.get("yaw") or 0.0
        h = None if math.hypot(sx, sy) < 1e-6 else cam + math.atan2(-sx, sy)
        b = set(r.get("buttons", ()))
        cast = r["n"] if {"lt", "y"} <= b else 0
        out.append((r["n"], h, 0 if cast else r["n"] * ("y" in b), r["n"] * ("black" in b), cast))
    return out


_KNOWN: list | None = None


def known_strings(seg: dict) -> list[list]:
    """Seed strings for a hop from what was played before (Step X.19): the winners of earlier chains' segments of
    the same kind, level, from-node and goal (every ``results/chain*.json`` under the evidence folder: run-length
    pads, no positions), newest first, for a merged walk first its hops' winners one after another (Step R1.16),
    and the strings of the proofs ``seg["seeds"]`` names (``proofs.jsonl``)."""
    global _KNOWN
    if _KNOWN is None:
        _KNOWN = []
        for f in sorted(xs.EV.glob("*/results/chain*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                rec = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            for top in rec.get("segments", ()):
                for sg in [top] + [st["approach"] for st in top.get("stations", ()) if st.get("approach")]:
                    won = [a for a in sg.get("attempts", ()) if a.get("ok") and a.get("string")]
                    if won:
                        _KNOWN.append(((sg.get("kind"), sg.get("level"), sg.get("from"),
                                        sg.get("object") or sg.get("goal")), won[-1]["string"]["segments"]))
    def known(key: tuple) -> list:
        return [segs_of(runs) for k, runs in _KNOWN if k == key]
    out = known((seg["kind"], seg["level"], seg["from"], seg.get("object") or seg["goal"]))[:3]
    if seg.get("parts"):           # a merged walk (plan.merge_walks): its hops' known strings one after another
        each = [known(("walk", seg["level"], a, b)) for a, b in seg["parts"]]
        if all(each):
            out.insert(0, [x for e in each for x in e[0]])
    refs = [h["proof"] for h in seg.get("seeds", ()) if "proof" in h]
    if refs:
        proofs = database().proofs
        out += [segs_of(proofs[r]["string"]["segments"]) for r in refs if r in proofs]
    return out


def no_jump(string) -> list[list]:
    """A seed string with no Y: each segment's jump (``hold``) and armor cast (``cast``, LT+Y) dropped, for a walk
    that carries a stored power (Y with LT held toggles air: AZ-500)."""
    return [seg_list(Seg(*s)._replace(hold=0, cast=0)) for s in string]


def ride_seeds(goal, feet, seg: dict, fall: int) -> list[list]:
    """Seed strings for a ride the hints name (``{"ride": volume, "every": n}``, Step X.19; X.15's spout): the
    planner's walk onto the volume's foot (the walk vertices under it, the two nearest the start a metre or more
    apart), then a jump every ``n`` ticks (Y for one tick, the stick at rest) for the ride's ``fall`` ticks."""
    import numpy as np

    from devkit.rando.draft.l3_goal import heading_to, object_points, route_seed
    R, out = goal.R, []
    for h in seg.get("seeds", ()):
        if "ride" not in h:
            continue
        try:
            p = object_points(R.lv, h["ride"])
        except KeyError:
            continue
        lo, hi = p.min(axis=0), p.max(axis=0)
        v = np.nonzero((R.X >= lo[0]) & (R.X <= hi[0]) & (R.Y >= lo[1]) & (R.Y <= hi[1]) & (R.Z >= lo[2] - 1.5)
                       & (R.Z <= lo[2] + 4.0))[0]
        if not len(v):
            continue
        d = np.hypot(R.X[v] - feet[0], R.Y[v] - feet[1])
        picked: list = []
        for j in v[np.argsort(d)]:
            q = R.pt(int(j))
            if all(math.dist(q, r) >= 1.0 for r in picked):
                picked.append(q)
            if len(picked) == 2:
                break
        every = int(h.get("every", 8))
        for q in picked:
            walk = route_seed(R, feet, tuple(q), air=int(seg.get("kit", {}).get("air", 0))) or [
                (math.ceil(math.dist(feet[:2], q[:2]) * 30 / 7.0) + 2, heading_to(feet, q), 0)]
            out.append(walk + [(every, None, 1)] * max(1, fall // every))
    return out


def boot_start(s, build: Path | str, kit: dict | None = None, tag: str = "vanilla-ig-w1", *, save: int = 1,
               quiet: bool = True, level: str | None = None, discs: dict | None = None,
               keys: dict | None = None) -> dict:
    """The chain's start on the build itself: ``s.boot`` (``Sandbox.boot_build``: the build reset from ``tag``'s menu
    state into SaveGame #``save``, by default #1, the all-powers character on w1's save platform nearest the beach;
    ``tag="vanilla-ig-new", save=2`` is the D98 drive's new-game character, AZ-354; warm after its first boot),
    then the plan's kit at the first segment (R2: these element levels, the others 0) and, with
    ``quiet``, every first-pickup popup marked seen (as ``devkit/reach/l3_certify.py``'s kit does: a popup's wall-clock time to
    clear lets the world drift near enemies).  A [placed] start: the save's character with the plan's elements.
    The build must boot: a vanilla state ``loadvm``'d with the build in the tray plays the levels its own boot
    cached on the HDD (vanilla's; hazard 8), so a randomized item would read as vanilla's.  ``level``: the level
    the save must load (``w1``: the chain's first segment's), else a boot try fails and is retried (AZ-363).
    ``discs``: {element: n}, disc fragments 1..n held (R2; a later sphere's placed start, Step R1.16); ``keys``:
    {key fourcc: count} in the key slots (R2, :func:`tour_keys`).  Halted at a player tick."""
    res = s.boot(Path(build), tag, save=save, quiet=quiet, **({"want": level_path(level)} if level else {}))
    levels = s.kit(**(kit or {}))
    for e, n in (discs or {}).items():
        levels |= {f"frags.{e}": s.frags(e, n)}
    if keys:
        levels |= {"keys": s.keys(keys)}
    return {**{k: res.get(k) for k in ("build", "iso_sha12", "xbe_sha256", "tag", "save", "level", "s", "tries",
                                        "warm", "incidents", "host_profile")}, "kit": levels, "quiet": quiet}


def level_path(level: str) -> str:
    """A level's path as the game loads it (``levels/water/w1``), from the generated exits' destinations."""
    for doc in database().generated.values():
        for x in doc.get("exits", ()):
            if x.get("dest_level") == level:
                return x["dest"]
    raise KeyError(f"no exit leads to {level}")


GEMS = ("emer", "diam", "ruby", "sapp")


_DB = None


def database():
    """The randomizer's database (loaded once)."""
    global _DB
    if _DB is None:
        from azurkit.tools.randomizer.planner.loader import load_database
        _DB = load_database()
    return _DB


def nodes() -> dict:
    return database().nodes


def zones(node: str) -> set[str]:
    """The derive's zones a level-file node anchors."""
    return {a[5:] for a in nodes()[node][1].get("anchors", []) if a.startswith("zone:")}


def item_touch_of(seg: dict) -> tuple | None:
    """A pickup segment's touch (``l3_goal.item_touch``, AZ-483): the species the build spawns there, the location's
    own template when it holds its vanilla item, else the item's name (a ``_move`` template's other item is the
    item's ``<item>_move`` when the table has one [inferred from RE_DATA's live reads]); None when it isn't a pickup
    or the table has no such species."""
    from devkit.rando.draft.l3_goal import item_touch
    if seg.get("kind") not in ("pickup", "reach") or str(seg.get("goal")).count("/") != 2:
        return None
    loc = lc.location(seg["goal"]) or {}
    item, tmpl = seg.get("item") or loc.get("item"), loc.get("template")
    names = [tmpl] if item in (None, loc.get("item")) else (
        [f"{item}_move", item] if str(tmpl).endswith("_move") else [item]) + [tmpl]
    engine = lc._engine()
    return next((tch for nm in names if nm and (tch := item_touch(engine, nm)) is not None), None)


def event_object(seg: dict) -> str:
    """An event's object as a record of its own: the generated id its flag names (``d1.BeamShape_g0r451.touch`` ->
    ``d1/g0/r451``: d1 has four records named ``BeamShape``, so the name alone reads none and aims at all four);
    a walkway generator's base, the same walkway's pressure plate (AZ-497: ``walkwayGenerator2:BaseShape`` ->
    ``walkwayGenerator2:PressurePlateShape``: the base is a box whose top is the floor, so a standing body centre is
    never inside it, and both feed one combiner into the toggle's OR, the next walk's need naming either); else its
    ``object``."""
    import re
    if m := re.search(r"_g(\d+)r(\d+)\.touch$", seg.get("flag") or ""):
        return f"{seg['level']}/g{m.group(1)}/r{m.group(2)}"
    return re.sub(r"^(walkwayGenerator\d*):BaseShape$", r"\1:PressurePlateShape", seg["object"])


def toggles(m, rec: int) -> dict[str, tuple[int, int, str]]:
    """The toggles a shape's touch drives (its touch plug's links, through combiners, to the first ``*_toggle`` on
    each way: d1's walkway generators' and beams' ``EW``, ``W1``, ``W3`` toggles), each by name: (its record, the
    last ``*_orCombiner`` the touch's way enters before it, else the last node, and the plug it enters there: the
    event's own input of the toggle's OR).  d1's are ``switch`` nodes (onTime, offTime 3.0), each turned on through
    an OR of three inputs (a beam's touch and two walkway generators'), so a toggle on shows only that one of its
    OR's inputs fired (AZ-501); ``EW_toggle``'s OR feeds it through ``DeathBridge_disable_andCombiner``, whose
    input from the OR every OR input turns on, so the way's input is read at the OR (the R1.16f review)."""
    todo, seen, out, entered, orc = [rec], set(), {}, {}, {}
    while todo and len(seen) < 16:
        i = todo.pop(0)
        if i in seen:
            continue
        seen.add(i)
        for lk in m.g.links(i):
            if i == rec and lk.src_plug != TOUCH_PLUG:
                continue
            name, way = m.g.names[lk.dst], (lk.dst, m.g.plug_name(lk.dst, lk.dst_plug))
            if name.endswith("_toggle"):
                out[name] = (lk.dst, *orc.get(i, entered[i])) if i != rec else (lk.dst, *way)
            else:
                entered.setdefault(lk.dst, way)
                if name.endswith("_orCombiner") or i in orc:
                    orc.setdefault(lk.dst, way if name.endswith("_orCombiner") else orc[i])
                todo.append(lk.dst)
    return out


def _record(m, obj: str):
    """An object as ``Minigames.use`` takes it: a generated id's record in the live graph, else its name."""
    if "/" in obj:
        _, gs, rs = obj.split("/")
        if int(gs[1:]) != m.gi:
            raise SystemExit(f"{obj}: not in the live graph (g{m.gi})")
        return int(rs[1:])
    return obj


def barrier_switches(seg: dict) -> list[str]:
    """A barrier segment's switches (the generated barrier's ``switches``: the switch nodes its shape's magic
    drives, w1's IceMelt_toggle1 r1434 for IceBlock_01, FireWall_01's OpenNCloseToggle r1374), as generated ids."""
    db = database()
    o = db.hand.get(seg.get("goal"), (None, None, {}))[2]
    return list(db.generated_objects.get(o.get("of"), (None, None, {}))[2].get("switches", ()))


def _live(m, gid: str) -> int | None:
    """A generated id's record in the live graph, None when it's in another graph."""
    try:
        return _record(m, gid)
    except xs.Teardown:   # a signal ends the chain, never a miss (AZ-701)
        raise
    except SystemExit:
        return None


def _generated(m, rec: int) -> int | None:
    """The critter on a generator's list (the record ``rec`` of the live graph) once its init ran (max HP set,
    current HP at most that), None before: the node's list head at +0x44 points at the critter's link at +0x1EC
    (sitting balthazar's boss probe, 2026-10-12); r116-final-h read Spideyzar's HP at the tick he was linked, before
    his init, as two words of something else."""
    nd = m.sb.read_u32(m.vec + 4 * rec)
    head = m.sb.read_u32(nd + GEN_LIST)
    if not head or head == nd + GEN_LIST:
        return None
    cr = head - GEN_LINK
    if m.sb.read_u32(cr + GEN_LINK) != nd + GEN_LIST:
        return None
    hp, top = struct.unpack("<ii", m.sb.read(cr + recipes.CR_HP, 8))
    return cr if 0 < top < 1_000_000 and 0 <= hp <= top else None


def _solved(r: dict) -> dict:
    """A minigame solver's result as an action's: ``done`` when it reports the minigame won, its scalars."""
    return {"done": any(bool(r.get(k)) for k in ("solved", "won", "toppled")),
            **{k: v for k, v in r.items() if isinstance(v, (bool, int, float, str))}}


def _hose_rest(m) -> dict:
    """The hose's second station (the player at its joystick): X on it, the fires (``hose_solve``), X off it."""
    r = {"engage": m.hose_engage()}
    r.update(m.hose_solve())
    m.run(12, stick=(0.0, 0.0), schedule={2: "down x", 6: "up x"})
    return _solved({**r, "engaged": r["engage"]["done"]})


# a minigame played at more than one place: (its object, the action there) per station (Step X.19): the hose's console
# and joystick are ~95 m apart in w2 (sitting r18f placed the player at each)
STATIONS = {"hose": (("LightShape", lambda m: m.hose_on()), ("HoseStuff:PublicJoystickShape", _hose_rest))}


def _row(r: dict):
    """An xemu replay row as an L3 row (no zone, writes or camera), for a goal's test."""
    return l3.Row(r["k"], tuple(r["pos"]), r["state"], r["hp"], None, (), None)


# d1's central elevator (Step R1.16d; RE_DATA §8, read from the vanilla d1.xbr's main graph, g0; X34-INTAKE §2.1 and
# RP-E): records of the live graph.  Each floor switch (its public_switchShape, pressed with X): the floor it stands
# on, the colour it programs, its FloorNtoAorB toggle, the floor its goal 0 and 1 give the colour (a press flips the
# toggle and gives the colour the new goal's floor [observed: X34's switch6 sent red to 8, then back to 1]), and its
# Key_toggle (switch7's, switch4's and switch9's start off: death_keylock1, death_keylock and death_keylock2 turn them
# on; every other starts on).
LIFT_SWITCHES = {613: (2, "red", 616, (1, 7), 614),       # switch
                 622: (6, "red", 624, (1, 10), 618),      # switch5
                 629: (7, "red", 632, (1, 8), 630),       # switch6
                 651: (8, "green", 659, (3, 2), 657),     # switch7 (death_keylock1)
                 664: (5, "green", 672, (3, 4), 670),     # switch4 (death_keylock)
                 679: (4, "green", 682, (4, 6), 680),     # switch3
                 688: (10, "green", 691, (4, 11), 689),   # switch8
                 706: (3, "blue", 709, (5, 7), 707),      # switch2
                 714: (11, "blue", 722, (5, 9), 720)}     # switch9 (death_keylock2)
# each colour: its timesCombiner (inputs[1]: the floor the colour's maxCombiner holds, no curve) and the deck's button
LIFT_COLOURS = {"red": (647, 644), "green": (702, 700), "blue": (733, 731)}
LIFT_CALLS = {1: 735, 2: 597, 3: 595, 4: 593, 5: 607, 6: 605, 7: 762, 8: 603, 9: 601, 10: 599, 11: 771}  # CallFieldN
LIFT_CALLED = 787     # CallFloor_orCombiner: inputs[14] is its own output, the floor called last
LIFT_DAMPER = 793     # Elevator_damper: goal and output, the deck's height called and now
LIFT_DECK = 1843      # ElevatorShape, the deck
LIFT_STEPS = 16       # actions a ride plans at most
LIFT_WAIT = 1200      # ticks a call or a ride waits for the deck at most (r116c: about 330 from floor 1 to 9)
LIFT_AT = 10          # ticks the deck stands at its goal before it counts as there
LIFT_BY = 1.5         # metres (horizontal) from the deck's footprint a body boards from (else from the call field)
LIFT_OFF = 0.5        # metres off the deck's footprint the walk vertex a step-off walks to stands at least
OFF_STUCK = 20        # ticks with no headway (0.1 m) toward a step-off's vertex before its jump, or its next side
OFF_TICKS = 150       # ticks a step-off walks toward one side's vertex at most
KEYLOCK_R = 0.5       # a keylock's approach radius (R1.16e's 34: 1.2 m left the body 3.04 m off; 0.5 m pressed), and
#                       a floor switch's after X's walk-up from 1.2 m stalled out of reach (sitting r125b's 35: 1.74 m)
KEYLOCK_STANDOFF = 0.7   # metres outside a keylock's sphere its second try presses X from (sitting r125-d1: r669 took
                         # from 0.69 m outside; from 0.25 to 0.01 m inside it didn't, 840 ticks in two runs)
RIDE_NEAR = 30.0      # metres (horizontal) within which a ride's switch or call field is walked to from where the body
RIDE_NEAR_Z = 3.0     # stands (no search; its searched approach after a miss), and up or down


def lift_plan(at: int, to: int, programs: dict[str, int], toggles: dict[int, int], keys: dict[int, bool],
              most: int = LIFT_STEPS) -> list[tuple] | None:
    """The fewest actions that take the player on d1's elevator from floor ``at`` to floor ``to`` (breadth first,
    at most ``most``): ``("press", shape)``, a floor switch on the player's floor whose key is in (``keys``: shape ->
    on), which flips its toggle (``toggles``: toggle record -> goal) and gives its colour the toggle's new floor;
    ``("ride", colour)`` to the floor the colour holds (``programs``: colour -> floor), which the call, the deck
    and the colour's button play.  No ride leaves floor 9 (the call there disables the elevator, RE_DATA §8).
    [] when ``at`` is ``to``; None when no way is that short."""
    colours, sw = sorted(LIFT_COLOURS), sorted(LIFT_SWITCHES)
    start = (at, tuple(programs[c] for c in colours), tuple(int(toggles[LIFT_SWITCHES[x][2]]) for x in sw))
    prev: dict = {start: None}
    todo = collections.deque([(start, 0)])
    while todo:
        st, n = todo.popleft()
        floor, prog, tog = st
        if floor == to:
            out = []
            while prev[st] is not None:
                st, act = prev[st]
                out.append(act)
            return out[::-1]
        if n >= most:
            continue
        nexts = []
        for j, x in enumerate(sw):
            fl, colour, _, ab, _ = LIFT_SWITCHES[x]
            if fl == floor and keys.get(x, True):
                t = tog[:j] + (1 - tog[j],) + tog[j + 1:]
                c = colours.index(colour)
                nexts.append(((floor, prog[:c] + (ab[t[j]],) + prog[c + 1:], t), ("press", x)))
        if floor != 9:
            nexts += [((prog[c], prog, tog), ("ride", colour)) for c, colour in enumerate(colours) if prog[c] != floor]
        for nst, act in nexts:
            if nst not in prev:
                prev[nst] = (st, act)
                todo.append((nst, n + 1))
    return None


def lift_state(m) -> tuple[dict, dict, dict]:
    """d1's elevator read live (a ``Minigames`` on d1): each colour's floor (the input its timesCombiner's attribute
    block holds [inferred: a combiner's block holds its inputs as the links deliver them]), each floor toggle's goal,
    each floor switch's key (its Key_toggle's goal) - :func:`lift_plan`'s ``programs``, ``toggles`` and ``keys``.
    Raises SystemExit when a colour doesn't read as a floor."""
    programs = {c: round(m.get(rec, "inputs[1]")) for c, (rec, _) in LIFT_COLOURS.items()}
    if not all(1 <= f <= 11 for f in programs.values()):
        raise SystemExit(f"the colours read {programs}: not floors (the program read is inferred)")
    toggles = {t: int(m.get(t, "goal") >= 0.5) for _, _, t, _, _ in LIFT_SWITCHES.values()}
    keys = {x: m.get(key, "goal") >= 0.5 for x, (_, _, _, _, key) in LIFT_SWITCHES.items()}
    return programs, toggles, keys


def lift_here(m) -> bool:
    """Whether the deck stands at the height its call asks (Elevator_damper's output at its goal)."""
    return abs(m.get(LIFT_DAMPER, "goal") - m.get(LIFT_DAMPER, "output")) < 0.05


def lift_box(level: str, rec: int) -> tuple:
    """The (low, high) corners of an elevator record's mesh in the level file (the deck at its rest, a call
    field: a 20 m square round the shaft, 5.4 m tall, holding the deck's 15.2 m footprint)."""
    from devkit.rando.draft.l3_goal import object_points
    q = object_points(router(level).lv, f"{level}/g0/r{rec}")
    return q.min(axis=0), q.max(axis=0)


def player_rate(read) -> float:
    """The player's ticks a second in the running build: the main loop's rate (``l3.MAIN_RATE``, an f64: 30 in
    vanilla, ``fps_unlock``'s F), read from guest RAM; 30 where it doesn't read as a positive number."""
    rate = struct.unpack("<d", read(l3.MAIN_RATE, 8))[0]
    return rate if math.isfinite(rate) and rate > 0 else 30.0


class Chain:
    """One chain in a sitting ``s`` (``xemu_sitting.Sitting``, its sandbox where the chain starts, halted at a
    player tick, the build booted: ``boot_start``).  ``segs``: the segments (:func:`plan_segments`);
    ``out``: chain.json; L3 runs the tray's build's ``default.xbe``; ``park``: savevm each start
    (``release``: quit xemu during each search, relaunching to replay; ``"waiting"``: only while another sitting
    waits for a slot).  ``jobs``, ``steps``: the search's processes and each seed's step budget; ``repairs``: the
    re-anchors a segment may take; ``hints``: {a segment's ``index`` (an action's station k's approach:
    ``"<index>.<k>"``): [strings]}, seed strings for a segment (an earlier run's winner from about the same start),
    tried first; ``progress``: a progress file (:func:`mark`) whose ``sample`` entries this chain's segments update
    as each ends (Step R1.16).  ``scene``: search and run whole steps (the scene tick:
    enemies, movers, push volumes; Step X.15) for every segment (True), never (False), or from a segment's first
    replay that xemu's world pushed off L3's trajectory within ``SCENE_AFTER`` ticks (``"diverged"``, the
    default); a segment with ``"scene":
    true`` (a mover on a timer on its way, as w1's spout) always runs in whole steps, and one with ``"fall": n``
    lets a branch stay in the air n ticks (a ride: the spout's lift to W1_W2_Fall is ~150 airborne ticks; the
    search's default ends a branch after 120).

    Step X.19 (R1.16's driver): a segment's hints (``plan.chain_segments``/``tour_segments``: ``scene``, ``fall``,
    ``seeds``) set its search; seed strings are its known strings (:func:`known_strings`) and a ride's
    (:func:`ride_seeds`) after ``hints``'; a winner whose robustness supports a harder tier than the plan's is
    searched again ``robust`` times in other shapes (:data:`ROBUST`) and the most robust kept; ``cart`` and
    ``teleport`` play as exits; ``minigame``, ``barrier``, ``button`` and ``event`` walk up to their object (an
    ``ObjectGoal``: searched and replayed as a walk) and then act with real input in closed loop (:meth:`act`:
    ``xemu_minigames``' solvers, a staff cast and attacks, X, a pad's touch); ``warp`` is ``Sitting.warp``'s
    debug-menu level warp ([placed]: only where the plan allows a placed start).  The sandbox is held by default
    (``release=False``: a long chain's relaunches queue behind other sittings).

    A segment with ``"carry"`` (Step R1.17a, AZ-500: a stored power, the elements LT holds pending, carried to its
    gate) is played with LT held and no jump, as Y with LT held toggles air: its searches have no Y
    (``Limits(hold=0)``, its seeds' jumps and casts dropped, :func:`no_jump`), its replay's settle tick and string,
    its drains and the pipe between them hold LT (again after a relaunch), and it takes no route pilot; a
    ``carry`` barrier releases LT where a cast would (:meth:`staff`), and nothing is held after it."""

    _held: frozenset = frozenset()   # the buttons every pad of the chain holds: LT while a segment carries a store
    assisted: bool = True            # a boss fight enters the game's no-damage and refill cheats (``fight``)
    _before: dict | None = None      # a touch event's toggles read before its approach (``toggles_before``)
    plateau: int | None = None       # a search's stall stop in player steps, every rung (``--plateau``), or none
    l3: str = "base"                 # the search pool's simulator (``--l3``): FastL3 (fast) or round 1's L3 (base)

    def __init__(self, s, segs: list[dict], *, out: Path, name: str = "x12", ident: dict | None = None,
                 park: bool = True, release: bool | str = False, jobs: int | None = None, steps: int = 200_000,
                 ticks: int = 3600, wall_cap: float = 1800.0, repairs: int = 2, deep: bool | None = None,
                 hints: dict | None = None, log=None, scene: bool | str = "diverged", robust: int = 2,
                 progress: Path | None = None, seg_cap: float | None = None, pilot: bool = False,
                 on_miss: str = "stop", assisted: bool = True, plateau: int | None = None, l3: str = L3_DEFAULT):
        from devkit.reach.l3_pool import default_workers
        jobs = jobs or default_workers()
        self.s, self.segs, self.out, self.name = s, segs, Path(out), xs.slug(name)
        self.park, self.release, self.jobs, self.steps, self.ticks = park, release, jobs, steps, ticks
        self.wall_cap, self.repairs, self.deep, self.scene = wall_cap, repairs, deep, scene
        self.hints = {str(k): v for k, v in (hints or {}).items()}
        self.robust, self.progress = robust, progress
        self.seg_cap, self.pilot, self.on_miss, self.assisted = seg_cap, pilot, on_miss, assisted
        self.plateau, self.l3 = plateau, l3
        self._pool = None        # (label, l3_pool.Pool) on the current start
        self.log = log or s.log
        self.xbe_name = s.sb.st.get("build") or "dvd.iso"
        self.rec = {"format": FORMAT, "step": "X.19", "name": self.name, "started": xs.stamp(), "plan": ident or {},
                    "build": {"disc": self.xbe_name, "iso_sha12": s.sb.disc_sha12(),
                              "xbe_sha12": hashlib.sha256(self.xbe()).hexdigest()[:12], "w": s.sb.w.name},
                    "settings": {"park": park, "release": release, "jobs": jobs, "steps": steps, "ticks": ticks,
                                 "repairs": repairs, "settle": SETTLE, "deep": deep, "scene": scene,
                                 "robust": robust, "deterministic": s.sb.st.get("deterministic", False),
                                 "seg_cap": seg_cap, "pilot": pilot, "on_miss": on_miss, "assisted": assisted,
                                 "plateau": plateau, "l3": l3, "l3_library": l3_library(l3)},
                    "segments": [], "ticks": 0, "result": None}
        self.k = 0               # player updates since the root, every one under a recorded pad
        self.halted_at_start = False
        self._seg_start = None   # the current segment's first start (searched), where a miss moves on from
        self._walk_up = False    # the current button's approach was skipped: act()'s X loop walks up itself
        self._rate: float | None = None

    @property
    def sb(self):
        return self.s.sb

    def rate(self) -> float:
        """The build's player ticks a second (``player_rate``), read once per chain: its replay and action ticks
        are counted at it and its search's robustness trials jitter at it (AZ-379: a 60 fps ``fps_unlock`` build's
        chain counted 30 and reported a lost tick; AZ-388's trials moved a press by half the time)."""
        if self._rate is None:
            self._rate = player_rate(self.sb.read)
        return self._rate

    def xbe(self) -> bytes:
        return self.sb._xbe(self.xbe_name)

    def disc(self) -> str:
        """The image in the tray, whose files L3 serves the game's reads from."""
        return str(self.sb.w / self.xbe_name)

    def save(self) -> None:
        self.out.parent.mkdir(parents=True, exist_ok=True)
        self.out.write_text(json.dumps(self.rec, indent=1, default=str) + "\n", encoding="utf-8")

    def pool(self, label: str):
        """The L3 worker pool on start ``label`` (one per start, kept across its searches): with ``l3`` fast its
        workers run FastL3 (``sim.l3_fast``, Step X.95: as the reach engine's ``--l3 fast`` pool, on the patched
        libunicorn once ``devkit/reach/unicorn/build_unicorn.py`` has built it, its switches set in this process's environment for
        the workers it spawns; else on the stock wheel), with base round 1's L3 on the stock wheel."""
        from devkit.reach import l3_fast
        from devkit.reach.l3_pool import Pool
        if self._pool is None or self._pool[0] != label:
            self.close_pool()
            for k in ("LIBUNICORN_PATH", *l3_fast.SWITCHES):
                os.environ.pop(k, None)
            if self.l3 == "fast":
                os.environ.update(l3_fast.worker_env())
            self._pool = (label, Pool(label, self.xbe(), workers=self.jobs, name="x12 chain", disc=self.disc(),
                                      fast=self.l3 == "fast"))
        return self._pool[1]

    def close_pool(self) -> None:
        if self._pool is not None:
            self._pool[1].close()
            self._pool = None

    # -- 1. the start ----------------------------------------------------------------------------------------------
    def take_start(self, i: int, n: int, parent: dict | None) -> dict:
        """An L3 snapshot where the chain stands (``here`` once a replay or drain left the guest at an update entry),
        linked to ``parent``, parked when ``park``.  Returns the start (its label and hashes; its metadata kept in
        memory under ``meta``)."""
        label = f"{self.name}-s{i:02d}-{n}-{time.strftime('%H%M%S')}"
        here = parent is not None
        info = self.sb.snapshot(label, here=here, parent=parent)
        path = Path(info["path"])
        self.s.snapshots.append(path)
        meta = l3.read_meta(path)
        st = {"label": label, "how": "here" if here else "root", "meta_sha12": l3.meta_sha12(meta),
              "pages_sha12": info["sha12"], "pages": info["pages"], "level": meta["level"], "hp": meta["hp"],
              "state": meta["state"], "snapshot_s": info["seconds"], "parent": parent, "meta": meta}
        if self.park:
            p = self.sb.park(f"p-{label}")
            st.update(parked=p["tag"], park_s=p["savevm_s"])   # a checkpoint: savevm, loadvm, on (X.26)
        self.halted_at_start = True
        self.log(f"start {label}: {st['how']}, {info['pages']} pages, sha12 {info['sha12']}"
                 + (f", parked in {st['park_s']} s" if self.park else ""))
        return st

    def bring_back(self, start: dict) -> dict | None:
        """The start again, halted (after a release, or after a replay moved the guest): unpark it."""
        if self.halted_at_start:
            return None
        if not self.park:
            raise SystemExit(f"{start['label']}: the guest moved on and the start isn't parked")
        if not self.sb.alive():
            t0 = time.monotonic()
            self.sb.relaunch()
            relaunch_s = round(time.monotonic() - t0, 1)
        else:
            relaunch_s = None
        u = self.sb.unpark(start["parked"], start["meta"])
        if not u.get("at_start"):
            raise SystemExit(f"{start['parked']}: loadvm didn't bring back {start['label']}'s start")
        if self._held and relaunch_s is not None:     # a carry's LT on the new xemu's pipe (the state's own
            self.sb.hold("ltrigger")                  # held keys come back with it too, hazard 13)
        self.halted_at_start = True
        return {**{k: u[k] for k in ("loadvm_s", "ready_s", "at_start")}, "relaunch_s": relaunch_s}

    def maybe_release(self) -> bool:
        """Quit xemu for the search (the start parked; the slot kept for its lease, then freed: Step X.8)."""
        want = self.release is True or (self.release == "waiting" and xo.xemu_queue.tickets(xo.SLOTS))
        if not (want and self.park and self.sb.alive()):
            return False
        self.rate()   # read while the guest is up: the search grades at it
        self.sb._quit()
        self.halted_at_start = False
        self.log("released the sandbox for the search (the start is parked)")
        return True

    # -- 2. the search ---------------------------------------------------------------------------------------------
    def goal(self, seg: dict, prof: str, **kw):
        from devkit.rando.draft.l3_goal import ExitGoal, ObjectGoal, RouteGoal
        r = router(seg["level"], prof)
        air = 0 if self._held else int(seg.get("kit", {}).get("air", 0))   # a carry's walk flies nothing
        if seg["kind"] in EXITS:
            return ExitGoal(r, seg["goal"], air=air, **kw)
        if seg.get("object"):
            return ObjectGoal(r, seg["object"], radius=seg.get("radius", 2.0), side=seg.get("side"), air=air,
                              inside=bool(seg.get("inside")))
        return RouteGoal(r, seg["goal"], air=air, touch=item_touch_of(seg))

    def search(self, seg: dict, start: dict, mult: int, prof: str, shape: dict, strings: list,
               scene: bool = False, wall: float | None = None) -> dict:
        from devkit.rando.draft.l3_goal import exit_nodes, route_seed
        lvl = seg["level"]
        air = 0 if self._held else int(seg.get("kit", {}).get("air", 0))
        sim = l3.L3(l3.read_snapshot(l3.snapshot_path(start["label"])), self.xbe(), disc=self.disc(), scene=scene)
        _, row, _, _, _ = start_of(sim, Segment(start["label"], settle=1, scene=scene))
        goal = self.goal(seg, prof)
        feet = lc._feet(row)
        fall = int(seg.get("fall") or 0)
        if seg["kind"] in EXITS:
            target = exit_nodes(goal.R, seg["goal"])
        elif seg.get("object"):         # the object's reachable vertex nearest the start
            import numpy as np
            v = np.nonzero(goal.dist == 0)[0]
            target = tuple(goal.R.pt(int(v[np.argmin(np.hypot(goal.R.X[v] - feet[0], goal.R.Y[v] - feet[1]))])))
        else:
            target = seg["goal"]
        seeds = [x for x in [route_seed(goal.R, feet, target, air=air)] if x] + strings
        seeds += ride_seeds(goal, feet, seg, fall or 120) + known_strings(seg)
        if self._held:                  # a carry: no Y (AZ-500)
            seeds, shape = [no_jump(x) for x in seeds], {**shape, "hold": 0}
        kw = {"reach": str(lc._reach_path(lvl)), "prof": prof, "air": air}
        if seg["kind"] in EXITS:
            kw["exit_id"], factory = seg["goal"], "make_exit_goal"
        elif seg.get("object"):
            kw.update(obj=seg["object"], radius=seg.get("radius", 2.0), side=seg.get("side"),
                      **({"inside": True} if seg.get("inside") else {}))
            factory = "make_object_goal"
        else:
            kw["target"], factory = seg["goal"], "make_goal"
            if (tch := item_touch_of(seg)) is not None:
                kw["touch"] = list(tch)
        spec = {"module": lc.GOAL_MODULE, "factory": factory, "kwargs": kw}
        per = SCENE_COST if scene else 1      # a whole-step search's budget and stall stop in whole steps
        limits = Limits(steps=self.steps * mult // per, wall_cap_s=wall or self.wall_cap * mult,
                        ticks=self.ticks, **({"fall": fall} if fall else {}), **shape,
                        plateau=None if self.plateau is None else max(1, self.plateau // per))
        res = solve(Segment(start["label"], settle=1, scene=scene), spec, self.xbe(), limits=limits, seeds=self.jobs,
                    strings=seeds, pool=self.pool(start["label"]), trials=SCENE_TRIALS if scene else 16,
                    rate=self.rate())
        w = res["winner"]
        out = {"reached": res["reached"], "seconds": res["seconds"], "problem": res["problem"], "prof": prof,
               "scene": scene,
               "steps_budget": limits.steps, "shape": shape, "seeds": len(seeds),
               "start_cost_s": res["runs"][0].get("start_cost_s") if res["runs"] else None,
               "start_zone": res["runs"][0].get("start_zone") if res["runs"] else None,
               "runs": [{k: r.get(k) for k in ("index", "why", "steps", "cells", "best_cost_s", "faults", "taint",
                                               "steps_per_s", "curve", "stall")} for r in res["runs"]]}
        out["taint"] = sorted({t for r in res["runs"] for t in r.get("taint", ())})
        if not w:
            out["inconclusive"] = bool(out["taint"])   # a tainted "not found" proves nothing (X.10)
        if w:
            out.update(ticks=w["ticks"], robustness=w["robustness"], winner_index=w["index"], segs=w["segs"],
                       cam=w["cam"], tier=tier_of(w["robustness"]),
                       **({"trial_errors": w["trial_errors"]} if w.get("trial_errors") else {}))
        return out

    # -- 3. the replay ---------------------------------------------------------------------------------------------
    def l3_run(self, start: dict, segs: list, deep: bool, scene: bool = False) -> tuple[list[Pad], list]:
        """The segment's pads (the settle tick, then the string) and L3's rows for them, from the start, read as
        deep as the replay will read them, in the mode the string was found in."""
        sim = l3.L3(l3.read_snapshot(l3.snapshot_path(start["label"])), self.xbe(), deep=deep, disc=self.disc(),
                    scene=scene)
        if self._held:                  # a carry: the settle tick holds LT too (one tick up would cast the store)
            pads = [Pad(buttons=self._held)]
            rows = [sim.step(pads[0])]
            cx, cy = struct.unpack("<2f", rows[-1].cam)
            cam = math.atan2(-cx, cy)
        else:
            _, _, cam, pads, rows = start_of(sim, Segment(start["label"], settle=1, scene=scene))
        more, _ = expand([Seg(*x) for x in segs], cam)
        more = [p._replace(buttons=p.buttons | self._held) for p in more]
        return pads + more, rows + [sim.step(p) for p in more]

    def replay(self, pads: list, rows: list, meta: dict, deep: bool) -> tuple[list[dict], dict]:
        """``Sandbox.replay`` from the halted start, clearing popups on the way: (xemu's rows, how it stopped)."""
        sb, got, m, popups = self.sb, [], meta, 0
        while True:
            stops: dict = {"diverge": DIVERGE_M}
            part = sb.replay(pads[len(got):], rows[len(got):], m, timeout=STALL_S, deep=deep, stops=stops)
            got += [{**r, "k": r["k"] + len(got)} for r in part]
            if stops["at"] != "stall" or len(got) >= len(rows) or popups >= POPUPS:
                return got, {**{k: v for k, v in stops.items() if k != "diverge"}, "k": len(got), "popups": popups}
            popups += 1
            d = self.drain(lambda c: True, max_ticks=0)     # A until the player's next update; nothing written
            if d["stop"] != "join":
                return got, {"at": "stall", "k": len(got), "popups": popups, "drain": d["stop"]}
            g, ent = sb.halt(), meta["entity"]
            clock = struct.unpack("<d", g.read(ent + 0x18, 8))[0]
            if g.regs()["ecx"] != ent or round((clock - meta["clock"]) * self.rate()) != len(got):
                return got, {"at": "lost", "k": len(got), "popups": popups}
            m = {**meta, "clock": clock, "start_sha12": xo.start_hash(g.read, ent)}
            self.log(f"a popup at tick {len(got)} cleared; the replay resumes")

    # -- 4. the drain ----------------------------------------------------------------------------------------------
    def drain(self, until, *, max_ticks: int = DRAIN_MAX) -> dict:
        """From the guest halted anywhere: at each of the player's update entries ``until(ctx)`` decides
        (``ctx``: the entity, its state, the level, the ticks drained, the ticks at rest, the loads); if it holds, halt
        there (``stop = "join"``: the next start, nothing written), else write the neutral pad (a drained tick).
        Level loads are waited out; when no update comes for ``STALL_S`` A goes through the pad FIFO (a popup, a
        dialog). ``stop``: join, max_ticks or stalled."""
        sb = self.sb
        g = sb.halt()
        vas = [l3.PLAYER_UPDATE, xo.LOAD_LEVEL]
        res = {"ticks": 0, "a_presses": 0, "loads": [], "settled": 0, "stop": None}
        t0, player, last, loading = time.monotonic(), None, None, False
        xo.arm(g, vas)
        try:
            r = g.regs()
            while True:
                if r["eip"] == xo.LOAD_LEVEL:
                    res["loads"].append(xo.level_path(g))
                    loading, player, last, res["settled"] = True, None, None, 0
                elif r["eip"] == l3.PLAYER_UPDATE:
                    ent = r["ecx"]
                    if not player:
                        try:
                            player = recipes.chain(sb.read_u32)["player"]
                        except OSError:
                            player = None
                    if player and sb.read_u32(ent + 0x20) == player:
                        loading = False
                        clock = struct.unpack("<d", g.read(ent + 0x18, 8))[0]
                        if clock != last:                   # a new tick (a repeated report of one entry folds)
                            last = clock
                            state = sb.read_u32(ent + 0x94)
                            res["settled"] = res["settled"] + 1 if state in (0, 6) else 0
                            ctx = {"ent": ent, "state": state, "level": recipes.level_path(sb.read, sb.read_u32),
                                   "ticks": res["ticks"], "settled": res["settled"], "loads": res["loads"]}
                            if until(ctx):
                                res["stop"] = "join"
                                break
                            if res["ticks"] >= max_ticks:
                                res["stop"] = "max_ticks"
                                break
                            sb.write_pad(Pad(buttons=self._held))
                            res["ticks"] += 1
                            self.k += 1
                xo.resume(g, vas)
                sb._halted = False
                while not sb._wait(LOAD_S if loading else STALL_S):
                    if loading or res["a_presses"] >= A_MAX:
                        res["stop"] = "stalled"
                        return res
                    g.cont()                               # a popup or a dialog: A, the breakpoints armed
                    sb._halted = False
                    sb.hold("a")
                    time.sleep(0.3)
                    sb.release_btn("a")
                    res["a_presses"] += 1
                r = g.regs()
        finally:
            g.cmd("?")
            res["s"] = round(time.monotonic() - t0, 1)
        return res

    # -- the outcome -----------------------------------------------------------------------------------------------
    def inventory(self) -> dict:
        return recipes.inventory(self.sb.read(recipes.chain(self.sb.read_u32)["inv"], recipes.INV_SAVED))

    def play(self, i: int, seg: dict, start: dict, found: dict) -> dict:
        """Replay the winner from the start, check the outcome and drain to the next join."""
        t0 = time.monotonic()
        deep = self.deep if self.deep is not None else found["ticks"] + 1 <= DEEP_TICKS
        pads, rows = self.l3_run(start, found["segs"], deep, found.get("scene", False))
        nxt = self.segs[i + 1] if i + 1 < len(self.segs) else None
        back = self.bring_back(start)
        inv0 = self.inventory()
        t1 = time.monotonic()
        got, stop = self.replay(pads, rows, start["meta"], deep)
        xemu_s = time.monotonic() - t1
        self.halted_at_start = False
        self.k += len(got)
        corpus.record(start["meta"], found.get("scene", False), pads[:len(got)], rows[:len(got)], got,   # its mode
                      disc=self.sb.disc_source(self.xbe_name))
        cmp = xo.l3_compare(rows, got)
        cmp.pop("err_at", None)
        cmp["path_m"] = round(cmp["path_m"], 1)
        exact = (cmp["ticks"] == cmp["l3_ticks"] and cmp["max_err_m"] == 0.0 and not cmp["states_differ"]
                 and not cmp["hp_differ"])
        close = (cmp["ticks"] == cmp["l3_ticks"] and (cmp["max_err_m"] or 0.0) <= DIVERGE_M
                 and not cmp["states_differ"] and not cmp["hp_differ"])
        out = {"replay": {**cmp, "stop": stop, "exact": exact, "within_m": close, "exact_prefix": cmp["max_err_m"] == 0.0
                          and not cmp["states_differ"] and not cmp["hp_differ"],
                          "deep": deep, "xemu_s": round(xemu_s, 1),
                          "ms_per_tick": round(1000 * xemu_s / max(1, len(got)), 1)},
               "string": {"sha12": string_sha12(pads[:len(got)], rows=rows[:len(got)]), "ticks": len(pads),
                          "replayed": len(got),
                          "input": "analog-ram", "segments": run_length(pads[:len(got)], rows[:len(got)])},
               "bring_back": back}
        kind, ok, why = seg["kind"], False, None
        loaded = stop.get("level") if stop["at"] == "load" else None
        cap, want = DRAIN_MAX, recipes.item_fields(seg["item"]) if kind == "pickup" else None
        if stop["at"] == "diverged":                  # xemu left L3's trajectory: join at once, re-anchor there
            until = (lambda c: True)
        elif kind in EXITS:
            dest, cap = seg["dest"], DRAIN_MAX if loaded else 300   # a trigger that hasn't fired: 10 s more, no longer
            until = (lambda c: c["level"] == dest and c["settled"] >= SETTLE)
        elif kind == "pickup":
            def got_item() -> bool:
                now = self.inventory()
                return any(now[f] != inv0[f] for f in (want or [f for f in now if f not in GEMS]))
            until = (lambda c: c["settled"] >= SETTLE and got_item())
        elif loaded and nxt and nxt["kind"] in EXITS and nxt.get("dest") == loaded:
            until = (lambda c: c["level"] == loaded and c["settled"] >= SETTLE)   # the next segment's exit fired
        else:
            until = (lambda c: True)
        d = self.drain(until, max_ticks=cap)
        out["drain"] = d
        inv1 = self.inventory()
        if kind in EXITS:
            ok = d["stop"] == "join" and (loaded == seg["dest"] or seg["dest"] in d["loads"])
            why = None if ok else f"no load of {seg['dest']} (replay {stop['at']}, drain {d['stop']}, loads {d['loads']})"
        elif kind == "pickup":
            changed = {k: [inv0[k], inv1[k]] for k in inv0 if inv0[k] != inv1[k]}
            out["inventory_changed"] = changed
            ok = bool(set(changed) & (want or set(changed) - set(GEMS)))
            why = None if ok else (f"{seg['item']} not taken: the inventory changed {sorted(changed) or 'nothing'} "
                                   f"(replay {stop['at']}, drain {d['stop']})")
        elif loaded:
            ok = bool(nxt and nxt["kind"] in EXITS and nxt.get("dest") == loaded and d["stop"] == "join")
            out["next_exit_fired"] = ok
            why = None if ok else f"an unplanned level load ({loaded}) at tick {stop['k']}"
        else:
            g = self.goal(seg, found["prof"])
            ok = d["stop"] == "join" and stop["at"] == "entry" and (   # a carry's LT wasn't searched: its own goal
                close and not self._held or bool(got) and g.reached(_row(got[-1])))
            why = None if ok else (f"the replay stopped ({stop['at']}) at tick {stop['k']} of {len(rows)}"
                                   if stop["at"] != "entry" else "xemu's last tick isn't in the goal")
        if stop["at"] == "diverged" and not ok:
            why = f"xemu left L3's trajectory at tick {stop['k'] - 1} of {len(rows)} (re-anchored there)"
        out.update(ok=ok, why=why, seconds=round(time.monotonic() - t0, 1))
        return out

    # -- 5. the loop -----------------------------------------------------------------------------------------------
    def where(self) -> dict:
        """Where the chain stands after a failed piece: halted at the player's update entry, alive, the level."""
        g = self.sb.halt()
        r = g.regs()
        st = self.sb.read_u32(r["ecx"] + 0x94) if r["eip"] == l3.PLAYER_UPDATE else None
        hp = struct.unpack("<i", self.sb.read(self.sb.read_u32(r["ecx"] + 0x20) + recipes.CR_HP, 4))[0] \
            if st is not None else None
        return {"entry": r["eip"] == l3.PLAYER_UPDATE, "alive": st not in (None, 7) and (hp or 0) > 0,
                "level": recipes.level_path(self.sb.read, self.sb.read_u32)}

    def carry(self, seg: dict) -> None:
        """LT held (every pad, and the pipe between them) while ``seg`` carries a stored power, let go where the
        carry ends without its barrier (AZ-500)."""
        held = frozenset({"lt"}) if seg.get("carry") else frozenset()
        if held != self._held:
            (self.sb.hold if held else self.sb.release_btn)("ltrigger")
            self._held = held

    def segment(self, i: int, seg: dict, parent: dict | None) -> dict:
        rec = {k: v for k, v in seg.items()}
        rec.update(starts=[], attempts=[], ok=False)
        self.rec["segments"].append(rec)
        self.carry(seg)
        if seg.get("rig") == "d1.elevator":
            return self.ride(i, seg, parent, rec)
        if seg["kind"] in ACTIONS:
            return self.action(i, seg, parent, rec)
        if seg["kind"] not in ("walk", "pickup", *EXITS):
            rec["why"] = f"a {seg['kind']} segment: the driver doesn't play it"
            return rec
        return self.searched(i, seg, parent, rec)

    def searched(self, i: int, seg: dict, parent: dict | None, rec: dict) -> dict:
        """A segment by search and replay (a walk, an exit, a pickup, an approach): its start, the ladder, the
        robustness re-search, the replay, the re-anchors."""
        start = self.take_start(i, 0, parent)
        self._seg_start = start                                # a miss moves on from here (:meth:`move_on`)
        rec["starts"].append({k: v for k, v in start.items() if k != "meta"})
        if not start["level"].endswith("/" + seg["level"]):
            rec["why"] = f"the chain stands in {start['level']}, not {seg['level']}"
            return rec
        key = f"{seg.get('index', i)}" + (f".{seg['station']}" if "station" in seg else "")
        strings, step, fails, n = [[tuple(x) for x in h] for h in self.hints.get(key, [])], 0, 0, 0
        scene = self.scene is True or bool(seg.get("scene"))   # a segment may ask for whole steps (a timed mover)
        kept = [start]                                         # the starts in use, the segment's first at the bottom
        while True:                                            # a goal the route graph can hold (Step R1.16)
            try:
                self.goal(seg, "logic")
                break
            except (KeyError, ValueError) as e:
                if seg.get("object") and "no walk vertex" in str(e) and seg.get("radius", 2.0) < 4.0:
                    seg = {**seg, "radius": 4.0 if seg.get("radius", 2.0) >= 2.5 else 2.5}   # an object over a
                    rec["radius"] = seg["radius"]                                         # pit or on a wall
                    continue
                return self.missed(i, seg, start, rec, f"no goal on the route graph: {str(e)[:200]}")
        if phys := self.off_logic(seg, start):
            rec["profile"] = "phys: the logic graph's cost field doesn't reach the start (the phys one does)"
        if self.pilot and not self._held and "rig" in seg.get("mech", ()) and self.piloted(i, seg, kept[0], rec):
            return rec                                         # a ride: the pilot stands on it (no search)
        spent = 0.0                                            # the segment's search seconds (``seg_cap``, D240)
        while True:
            n += 1
            mult, prof, shape = LADDER[step]
            prof = "phys" if phys else prof
            left = None if self.seg_cap is None else self.seg_cap - spent
            if left is not None and left <= 0:
                return self.missed(i, seg, kept[0], rec, f"the segment's search cap ({self.seg_cap:.0f} s, D240) "
                                                         f"ran out after {n - 1} searches")
            released = self.maybe_release()
            found = self.search(seg, start, mult, prof, shape, strings, scene,
                                wall=None if left is None else min(self.wall_cap * mult, left))
            self.stop_on_signal()
            spent += found["seconds"]
            att = {"n": n, "start": start["label"], "released": released,
                   "search": {k: v for k, v in found.items() if k not in ("segs", "cam")}}
            rec["attempts"].append(att)
            self.save()
            self.log(f"segment {i} ({seg['kind']} {seg['from']} > {seg.get('object') or seg['goal']}) attempt {n}: "
                     + (f"found {found['ticks']} ticks, robustness {found['robustness']}, {found['seconds']} s"
                        if found["reached"] else f"no string ({[r['why'] for r in found['runs']][:3]})"))
            if not found["reached"]:
                if found.get("inconclusive"):
                    att["note"] = f"tainted ({found['taint']}): inconclusive, not a refutation"
                if len(kept) > 1 and self.park and max((r.get("cells") or 0 for r in found["runs"]), default=0) \
                        <= STUCK_CELLS:                           # the body doesn't move from this re-anchor: back
                    kept.pop()                                    # to the start before it, the piece undone
                    rec["starts"][[s_["label"] for s_ in rec["starts"]].index(start["label"])]["dropped"] = \
                        f"stuck: every run kept {STUCK_CELLS} cells or fewer"
                    start, step, self.halted_at_start = kept[-1], 0, False
                    att["undone"] = "stuck"
                    continue
                costs = [r["best_cost_s"] for r in found["runs"] if r.get("best_cost_s") is not None]
                whys = [str(r.get("why", "")) for r in found["runs"]]
                if LADDER[step][0] == 1 and costs and max(costs) - min(costs) <= 0.5:
                    step += 1                                     # every seed stalled at one cost: more budget
                    att["skipped"] = "the 4x budget: every seed stalled at the same cost to go"   # won't move it
                elif LADDER[step][0] == 1 and any(w.startswith("plateau") for w in whys) and all(
                        w.startswith(("plateau", "exhausted")) for w in whys):
                    step += 1                                     # the 4x rung is the same problem: its seeds would
                    att["skipped"] = "the 4x budget: every seed ended at its plateau"   # end where these did
                step += 1
                if step >= len(LADDER):
                    return self.missed(i, seg, kept[0], rec, "the search found no string on every rung of the ladder")
                continue
            found = self.more_robust(seg, start, found, att, mult, prof, shape, scene)
            played = self.play(i, seg, start, found)
            att.update(played)
            self.save()
            self.log(f"segment {i} attempt {n}: replay {played['replay']['stop']['at']}, exact "
                     f"{played['replay']['exact']}, max error {played['replay']['max_err_m']}, ok {played['ok']}"
                     + (f" ({played['why']})" if played["why"] else ""))
            if played["ok"]:
                rec.update(ok=True, robustness=found["robustness"], tier_measured=found["tier"],
                           string_sha12=played["string"]["sha12"], ticks=played["string"]["replayed"],
                           drained=played["drain"]["ticks"], search_s=sum(a["search"]["seconds"]
                                                                          + sum(r.get("seconds") or 0 for r in a.get("robust", ()))
                                                                          for a in rec["attempts"]),
                           reanchors=sum(not s.get("dropped") for s in rec["starts"][1:]))
                return rec
            fails += 1
            if fails > self.repairs:
                return self.missed(i, seg, kept[0], rec, f"{fails} replays failed: {played['why']}")
            stop, nxt = played["replay"]["stop"], (self.segs[i + 1] if i + 1 < len(self.segs) else {})
            if stop["at"] == "load" and stop.get("level") not in (seg.get("dest"), nxt.get("dest")):
                if scene:                                        # AZ-702: a load the segment doesn't plan, which the
                    return self.missed(i, seg, kept[0], rec,     # same string meets again: whole steps run its
                                       f"an unplanned level load ({stop.get('level')}) at tick {stop['k']}, in "
                                       "whole steps too")        # trigger (X.52b), else placed past
                scene, step = True, 0
                att["next"] = "whole steps: an unplanned level load (AZ-702)"
            else:
                strings, step = strings + [found["segs"]], 0    # another start or mode: the ladder from its first rung
            if played["replay"]["stop"]["at"] == "diverged" and self.scene == "diverged" and not scene:
                if played["replay"]["stop"]["k"] < SCENE_AFTER:  # the world moved the player soon: whole steps
                    scene = True
                    att["next"] = "whole steps"
                else:                                            # a long exact prefix: player ticks from the
                    att["next"] = "player ticks again"           # re-anchor, whole steps once one diverges soon
            w = self.where()
            if w["entry"] and w["alive"] and w["level"].endswith("/" + seg["level"]):
                parent = {"meta_sha12": start["meta_sha12"], "string_sha12": played["string"]["sha12"],
                          "drained": played["drain"]["ticks"], "piece": "a failed attempt's ticks"}
                new = self.take_start(i, n, parent)              # re-anchor where xemu stands: a new snapshot
                rec["starts"].append({k: v for k, v in new.items() if k != "meta"})
                if self.park and self.lost_ground(seg, start, new, found["prof"]):
                    rec["starts"][-1]["dropped"] = "farther from the goal than its parent: the parked start again"
                    self.halted_at_start = False                  # the piece undone (sitting x19: pushed off w1's
                    att["undone"] = "lost ground"                 # ridge into the water, the rocks to climb again)
                else:
                    start = new
                    kept.append(new)
            elif self.park:
                self.halted_at_start = False                      # back to the parked start, the piece undone
                att["undone"] = w
            else:
                rec["why"] = f"the replay left the player where no re-anchor helps ({w})"
                return rec

    def missed(self, i: int, seg: dict, start: dict, rec: dict, why: str) -> dict:
        """A segment the search and the replays didn't play: with ``pilot`` the route pilot from its first start
        (:meth:`piloted`, once), else the miss ``why``."""
        if self.pilot and not self._held and not rec.get("pilot") and self.piloted(i, seg, start, rec):   # its Y
            rec["after"] = why
            return rec
        rec["why"] = why + (f"; the route pilot: {rec['pilot']['why']}" if rec.get("pilot") else "")
        return rec

    def body(self) -> tuple:
        """The player's body centre, the guest halted (in memory only)."""
        self.sb.halt()
        return struct.unpack("<3f", self.sb.read(recipes.chain(self.sb.read_u32)["player"] + recipes.CR_BODY, 12))

    def body_row(self):
        """The player halted at an update entry as an L3 row (its body centre, state, HP), for a goal's test."""
        g = self.sb.halt()
        ent = g.regs()["ecx"]
        crit = self.sb.read_u32(ent + 0x20)
        centre = struct.unpack("<3f", self.sb.read(crit + recipes.CR_BODY, 12))
        hp = struct.unpack("<i", self.sb.read(crit + recipes.CR_HP, 4))[0]
        return l3.Row(0, tuple(centre), self.sb.read_u32(ent + 0x94), hp, None, (), None)

    def target_of(self, seg: dict, goal, start: dict):
        """The route pilot's target for a segment: its goal (a node, a zone, a generated id: an exit's trigger, a
        pickup's point), or for an object without an id the goal's vertex nearest the start (a point, in memory)."""
        import numpy as np
        obj = seg.get("object")
        if not obj or "/" in obj:
            return obj or seg["goal"]
        pos = start["meta"]["pos"]
        v = np.nonzero(goal.dist == 0)[0]
        return tuple(goal.R.pt(int(v[np.argmin(np.hypot(goal.R.X[v] - pos[0], goal.R.Y[v] - pos[1]))])))

    def piloted(self, i: int, seg: dict, start: dict, rec: dict) -> bool:
        """The route pilot (``xemu_route.walk_to``: closed loop, the analog stick written at the input builder,
        buttons through the FIFO, decoded rides ridden from their trigger pads) from the segment's ``start`` to its
        goal, then a drain to the next join as :meth:`play` drains a replay; recorded under ``pilot``.  Step R1.16
        (D240): first for a hop that rides a rig (the whole-step searches of town's grate elevator hit their 1,800 s
        wall cap), else after a miss.  Real pad input with no string: the next start links to the join."""
        from devkit.xemu import route as xr
        t0 = time.monotonic()
        back = self.bring_back(start)
        try:
            goal = self.goal(seg, "logic")
        except (KeyError, ValueError) as e:      # an exit whose trigger the router can't place: the load decides
            goal = None
            rec["pilot_goal"] = str(e)[:200]
        air = int(seg.get("kit", {}).get("air", 0))
        inv0 = self.inventory()
        R = router(seg["level"])
        if "_lists" not in R.__dict__:      # load_router drops the planner's lists (the workers' memory)
            R._lists = (R.indptr.tolist(), R.dst.tolist(), R.cost.tolist())
        try:
            target = self.target_of(seg, goal, start)
            R.goal(target)
        except (KeyError, ValueError, IndexError) as e:
            rec["pilot"] = {"ok": False, "why": f"no target for the pilot: {str(e)[:200]}"}
            self.log(f"segment {i} route pilot: {rec['pilot']['why']}")
            return False
        self.halted_at_start = False
        res = xr.walk_to(self.sb, R, target, tier="hard", air=air, ticks=PILOT_TICKS)
        self.k += res["ticks"]
        kind = seg["kind"]
        if kind in EXITS:
            until, cap = (lambda c: c["level"] == seg["dest"] and c["settled"] >= SETTLE), DRAIN_MAX
        elif kind == "pickup":
            want = recipes.item_fields(seg["item"])
            until, cap = (lambda c: c["settled"] >= SETTLE and any(
                v != inv0[f] for f, v in self.inventory().items() if f in (want or set(inv0) - set(GEMS)))), 300
        else:
            until, cap = (lambda c: True), DRAIN_MAX
        d = self.drain(until, max_ticks=cap)
        if kind in EXITS:
            ok = d["stop"] == "join" and seg["dest"] in d["loads"]
        elif kind == "pickup":
            ok = d["stop"] == "join"
        else:
            ok = d["stop"] == "join" and (res["reached"] or goal is not None and goal.reached(self.body_row()))
        rec["pilot"] = {"ok": ok, "why": None if ok else f"{res['why']} ({res['left_m']} m left, drain {d['stop']})",
                        "bring_back": back, "drain": d, "seconds": round(time.monotonic() - t0, 1),
                        **{k: res[k] for k in ("reached", "why", "left_m", "end_zone", "ticks", "replans", "hops",
                                               "sidesteps", "retreats", "dialogs", "hp")},
                        "legs": [{k: leg.get(k) for k in ("kind", "how", "ticks")} for leg in res["legs"]]}
        self.save()
        self.log(f"segment {i} ({kind} {seg['from']} > {seg.get('object') or seg['goal']}) route pilot: ok {ok}, "
                 f"{res['why']}, {res['ticks']} ticks, {res['replans']} replans, drain {d['stop']}")
        if ok:
            rec["starts"].append({"meta_sha12": rec["starts"][-1]["meta_sha12"] if rec["starts"] else None,
                                  "how": "after the route pilot"})
            rec.update(ok=True, ticks=res["ticks"], drained=d["ticks"], string_sha12=None,
                       input="route pilot: real pad in closed loop (not a replayed string)",
                       search_s=sum(a["search"]["seconds"] for a in rec["attempts"]))
        return ok

    def move_on(self, i: int) -> dict:
        """After a miss (``on_miss="place"``, D240: record it and move on): stand at the next segment's start.
        A missed exit: the player placed (R6) onto a walk vertex inside its trigger, which fires the game's own level
        load; else, when the feet aren't in the next segment's from-node, placed onto its vertex nearest the node's
        middle.  Then a drain to a join.  [placed]: what follows starts placed, not played.  A move-on that finds no
        player tick to place at goes again once from the segment's start loaded from the drive in a new xemu (sitting
        r125-full-g, segment 29: the start restored from memory after the route pilot's retreat ended in a death, the
        guest bugchecked 0x1E and the chain ended; a resume that loaded the same start from the drive moved on,
        AZ-819)."""
        try:
            return self._move_on(i)
        except xs.Teardown:   # a signal ends the chain, never a miss (AZ-701)
            raise
        except SystemExit as e:
            if getattr(self, "_seg_start", None) is None or not self.park:
                raise
            self.log(f"segment {i} move-on: {e}; again from its start loaded from the drive (xemu relaunched)")
            self.sb._quit()                                   # bring_back relaunches and loads the parked tag
            self.halted_at_start = False
            return {**self._move_on(i), "again": f"xemu relaunched after: {str(e)[:160]}"}

    def _move_on(self, i: int) -> dict:
        import numpy as np
        seg, nxt = self.segs[i], self.segs[i + 1]
        if getattr(self, "_seg_start", None) is not None and self.park:
            self.bring_back(self._seg_start)                   # the segment's (or its approach's) first start
        if self.sb.halt().regs()["eip"] != l3.PLAYER_UPDATE:
            self.drain(lambda c: True, max_ticks=0)            # to the player's next update entry
        lvl = recipes.level_path(self.sb.read, self.sb.read_u32)
        out: dict = {"placed": None}
        if not lvl.endswith("/" + seg["level"]):
            return {**out, "ok": False, "why": f"the chain stands in {lvl}, not {seg['level']}"}
        R = router(seg["level"])
        if seg["kind"] in EXITS:
            return self._exit_on(i, seg, R, out)
        return self._onto(i, R, nxt, out)

    def _in(self, R, want: set, ent: int | None = None) -> bool:
        """Whether the player's feet stand in one of the zones ``want`` (halted at an update entry, or ``ent``)."""
        ent = ent or self.sb.halt().regs()["ecx"]
        crit = self.sb.read_u32(ent + 0x20)
        c = struct.unpack("<3f", self.sb.read(crit + recipes.CR_BODY, 12))
        st = self.sb.read_u32(ent + 0x94)
        return R.zone_at((c[0], c[1], c[2] - 1.0), prefer_water=st == 6) in want

    def _onto(self, i: int, R, nxt: dict, out: dict) -> dict:
        """Stand in the next segment's from-node: where the player stands already; else after up to 600 neutral
        ticks (the world may carry it there: d1's arrival rides the grate elevator down into the seal's chamber);
        else R6 onto one of up to four of the node's vertices (the middle first), each checked: the player settles
        in the node within 150 ticks, else its start is brought back and the next one tried (L3 certify's check:
        a place in another room may not hold)."""
        import numpy as np
        want = zones(nxt["from"])
        if self.sb.halt().regs()["eip"] != l3.PLAYER_UPDATE:   # an R7 hop halts at the player tick, whose ECX
            self.drain(lambda c: True, max_ticks=0)            # isn't the entity: to its update entry first
        if self._in(R, want):
            return self._join(i, out, None)
        d = self.drain(lambda c: c["settled"] >= SETTLE and self._in(R, want, c["ent"]), max_ticks=600)
        if d["stop"] == "join":
            out.update(placed=None, carried=d["ticks"])
            return self._join(i, out, None)
        from devkit.rando.draft.l3_goal import RouteGoal
        v = np.nonzero(RouteGoal(R, nxt["from"]).dist == 0)[0]
        if not len(v):
            return {**out, "ok": False, "why": f"no walk vertex of {nxt['from']} to place onto"}
        mid = np.array([R.X[v].mean(), R.Y[v].mean()])
        order = v[np.argsort(np.hypot(R.X[v] - mid[0], R.Y[v] - mid[1]))]
        tries = [order[0]] + [order[k] for k in np.linspace(len(order) // 4, len(order) - 1, 3).astype(int).tolist()
                              if len(order) > 1]
        out["tries"] = []
        for n, j in enumerate(tries[:4]):
            if n and self._seg_start is not None and self.park:
                self.halted_at_start = False
                self.bring_back(self._seg_start)
            self.sb.halt()
            pl = self.s.place(tuple(R.pt(int(j))), 0.0, settle=4)
            d = self.drain(lambda c: c["settled"] >= SETTLE and self._in(R, want, c["ent"]), max_ticks=150)
            out["tries"].append({"place": pl, "drain": d["stop"]})
            if d["stop"] == "join":
                out.update(placed=f"onto {nxt['from']} (try {n + 1})")
                return self._join(i, out, None)
        return {**out, "ok": False, "why": f"no placement onto {nxt['from']} settled in it ({len(out['tries'])} tries)"}

    def _place_mid(self, R, v, out: dict) -> None:
        """R6 onto the vertex of ``v`` nearest their middle."""
        import numpy as np
        mid = np.array([R.X[v].mean(), R.Y[v].mean()])
        j = int(v[np.argmin(np.hypot(R.X[v] - mid[0], R.Y[v] - mid[1]))])
        self.sb.halt()
        out["place"] = self.s.place(tuple(R.pt(j)), 0.0, settle=4)

    def _join(self, i: int, out: dict, dest: str | None) -> dict:
        """A drain to a join after a placement (in ``dest`` once it loaded): the move-on's outcome."""
        d = self.drain(lambda c: c["settled"] >= SETTLE and (dest is None or dest in c["loads"]), max_ticks=DRAIN_MAX)
        self.halted_at_start = False                     # (the level's path may name the destination before its
        out.update(drain=d, ok=d["stop"] == "join" and (dest is None or dest in d["loads"]))   # load: wait for it)
        if not out["ok"]:
            out["why"] = f"the drain after the placement: {d['stop']}, loads {d['loads']}"
        self.log(f"segment {i} missed: moved on {out['placed'] or 'from where it stood'} [placed], ok {out['ok']}")
        return out

    def _exit_on(self, i: int, seg: dict, R, out: dict) -> dict:
        """A missed exit: R6 into its trigger (a walk vertex inside it), the game's own load; when it has none or
        the load doesn't come, R7: the request its levelSwitch posts (the destination, its spot)."""
        import numpy as np
        try:
            v = np.nonzero(self.goal(seg, "logic").dist == 0)[0]
        except (KeyError, ValueError):
            v = np.array([], dtype=int)
        if len(v):
            out["placed"] = f"into {seg['goal']}'s trigger"
            self._place_mid(R, v, out)
            res = self._join(i, out, seg["dest"])
            if res["ok"]:
                return res
            out = {"placed": None, "trigger": {k: res.get(k) for k in ("placed", "place", "why")}}
        ex = next((x for doc in database().generated.values() for x in doc.get("exits", ())
                   if x["id"] == seg["goal"]), None)
        if not (ex and ex.get("spot")):
            return {**out, "ok": False, "why": "no walk vertex in the trigger and no spot to hop to"}
        self.sb.halt()
        try:
            h = self.s.hop(seg["dest"], ex["spot"])
        except xs.Teardown:   # a signal ends the chain, never a miss (AZ-701)
            raise
        except SystemExit as e:                           # no player tick to post it at
            return {**out, "ok": False, "why": f"the R7 hop: {str(e)[:200]}"}
        out.update(placed=f"R7 hop to {seg['dest']} at {ex['spot']}", hop={k: h.get(k) for k in ("ok", "loads", "s")})
        if not h["ok"]:
            return {**out, "ok": False, "why": "the R7 hop didn't settle"}
        nxt = self.segs[i + 1]
        if nxt["level"] == seg["dest"].rsplit("/", 1)[-1]:
            self._seg_start = None                       # the arrival is the start now: no bringing back across a load
            return self._onto(i, router(nxt["level"]), nxt, out)
        return self._join(i, out, None)

    def lost_ground(self, seg: dict, start: dict, new: dict, prof: str) -> bool:
        """Whether a re-anchored start ``new`` is farther from the segment's goal than ``start`` (the goal's cost to
        go, its fallback off the graph included, plus 2 s): then the parked start is brought back instead."""
        import types

        def row(m):
            return types.SimpleNamespace(pos=tuple(m["pos"]), state=m["state"], zone=None)
        try:
            g = self.goal(seg, prof)
            return g.cost(row(new["meta"])) > g.cost(row(start["meta"])) + 2.0
        except (KeyError, ValueError):
            return False

    def off_logic(self, seg: dict, start: dict) -> bool:
        """Whether the logic profile's cost field doesn't reach the start and the phys one's does (Step X.19: the
        w2 hose's console from the pool): the ladder then searches on the phys graph from its first rung."""
        import types
        m = start["meta"]
        row = types.SimpleNamespace(pos=tuple(m["pos"]), state=m["state"], zone=None)
        try:
            return not self.goal(seg, "logic").finite_at(row) and self.goal(seg, "phys").finite_at(row)
        except (KeyError, ValueError):
            return False

    def more_robust(self, seg: dict, start: dict, found: dict, att: dict, mult: int, prof: str, shape: dict,
                    scene: bool) -> dict:
        """A winner whose robustness supports a harder tier than the plan's (``seg["tier"]``) is searched again in
        :data:`ROBUST`'s shapes (``robust`` of them, other problems so other seeds); the most robust is kept, the
        first that meets the plan's tier ends it; each try stops at :data:`ROBUST_S`.  Each is recorded under the
        attempt's ``robust``.  Not where the plan's tier isn't needed (Step R1.16): a hop in logic at the safe tier
        (``difficulty`` 1: a pickup, an approach, an edge with no movement tier), nor a whole-step winner."""
        want = RANK.get(seg.get("tier"), len(TIERS) - 1)
        best = found
        if seg.get("difficulty", 1) < 2 and RANK[best["tier"]] > want:   # Step R1.16: the plan's tier isn't needed
            att["robust"] = [{"skipped": "the hop is in logic at the safe tier: the plan's tier isn't needed"}]
            return best
        if scene and RANK[best["tier"]] > want:   # whole steps: a re-search and its trials cost ~30 min (x19d)
            att["robust"] = [{"skipped": "whole steps"}]
            return best
        for extra in ROBUST[:self.robust]:
            if RANK[best["tier"]] <= want:
                break
            alt = self.search(seg, start, mult, prof, {**shape, **extra}, [], scene, wall=ROBUST_S)
            att.setdefault("robust", []).append({k: alt.get(k) for k in ("reached", "seconds", "ticks", "robustness",
                                                                          "tier", "shape")})
            if alt["reached"] and alt["robustness"] > best["robustness"]:
                best = alt
        if best is not found:
            att["robust_kept"] = {"robustness": best["robustness"], "tier": best["tier"], "ticks": best["ticks"]}
        return best

    # -- the actions (Step X.19) -------------------------------------------------------------------------------------
    def stations(self, seg: dict) -> list[tuple[dict | None, object]]:
        """An action's stations, each (the walk up to its object as a segment, an ``ObjectGoal``: {} when none is
        needed, None when the driver doesn't play it; the action there, a callable on a ``Minigames``): a
        minigame's from :data:`STATIONS` (the hose: X at the console, then the joystick and the fires), else one."""
        kind, how = seg["kind"], seg.get("how")
        base = {k: seg[k] for k in ("index", "level", "from", "kit", "tier") if k in seg}
        base |= {"kind": "walk", "to": seg["from"], "goal": seg["from"], "scene": bool(seg.get("scene"))}

        def near(obj: str, radius: float) -> dict:
            return base | ({"goal": obj} if obj in nodes() else {"object": obj, "radius": radius})
        if kind == "warp":
            return [({}, lambda m: self.act(seg))]
        if kind == "minigame":
            if seg["solver"] in STATIONS:
                return [(near(obj, 2.5), fn) for obj, fn in STATIONS[seg["solver"]]]
            return [(near(seg["goal"], 2.5), lambda m: _solved(getattr(m, seg["solver"])()))]
        if kind == "barrier":
            return [(base | {"object": seg["shapes"][0], "side": sorted(zones(seg["from"])), "radius": 3.0},
                     lambda m: self.act(seg, m))]
        if kind == "button":
            if (touch := self.touch_of(seg)) is not None:          # a seal: stand on its shape (radius 0)
                return [(near(touch, 0.0), lambda m: self.act(seg, m))]
            return [(near(seg["goal"], KEYLOCK_R if seg.get("lock_toggle") else 1.2), lambda m: self.act(seg, m))]
        if kind == "event" and how in ("touch", "hit", "action") and seg.get("object"):
            seg = {**seg, "object": event_object(seg)}
            approach = near(seg["object"], 0.0 if how == "touch" else 1.5)   # a touch of a trigger volume: the body
            if how == "touch" and "object" in approach:                      # centre in it; a platform: stood on
                from devkit.rando.draft.l3_goal import holds_body
                if holds_body(router(seg["level"]), seg["object"]):
                    approach |= {"inside": True}
                else:
                    seg = {**seg, "platform": True}
            return [(approach, lambda m: self.act(seg, m))]
        if kind == "event" and how == "killed" and self.boss(seg) is not None:
            return [(base, lambda m: self.fight(m, seg, self.assisted))]   # the walk into its node parks its start
        return [(None, None)]

    def action(self, i: int, seg: dict, parent: dict | None, rec: dict) -> dict:
        """An action segment: at each station (:meth:`stations`) the approach (searched and replayed as a walk; its
        record under ``approach``), the action with real input in closed loop, a drain to the next join."""
        from devkit.xemu import minigames as mg
        rec["stations"] = []
        self._before = self.toggles_before(seg) if seg["kind"] == "event" and seg.get("how") == "touch" \
            and seg.get("object") else None             # a touch event's toggles, read before its approach
        if seg["kind"] == "barrier":          # a wall behind the body (the hop's zone path only touches it): skipped,
            from devkit.rando.draft.l3_goal import object_points   # recorded so (not done: AZ-500)
            p = object_points(router(seg["level"]).lv, seg["shapes"][0])
            if self.in_the_way(seg, (p.min(axis=0) + p.max(axis=0)) / 2, self.body()) is False:
                rec.update(ok=False, drained=0, act_ticks=0, act_s=0.0, string_sha12=None,
                           skipped="the wall isn't between the body and the to-node: the hop's walk routes on")
                rec["starts"].append({"meta_sha12": parent.get("meta_sha12") if parent else None,
                                      "how": "a skipped action"})
                self.log(f"segment {i} (barrier {seg['goal']}): not in the way, skipped")
                return rec
        for k, (app, fn) in enumerate(self.stations(seg)):
            if app is None:
                rec["why"] = f"a {seg['kind']} ({seg.get('how') or seg.get('solver')}) the driver doesn't play"
                return rec
            if (parent := self.station(i, seg, k, app, fn, parent, rec)) is None:
                return rec
        return self.acted(seg, parent, rec)

    def acted(self, seg: dict, parent: dict | None, rec: dict) -> dict:
        """An action segment's stations all played: its record ok, the next start linked to the join the last
        drain halted at (no string: the action's input isn't one).  A barrier its approach left behind the body
        (:meth:`staff`'s ``not_in_the_way``) is recorded skipped, not ok (AZ-500)."""
        if any((st.get("act") or {}).get("not_in_the_way") for st in rec["stations"]):
            rec["skipped"] = "the wall isn't between the body and the to-node where its approach ended"
        rec.update(ok=not rec.get("skipped"), drained=0,
                   act_ticks=sum(st.get("act_ticks") or 0 for st in rec["stations"]),
                   act_s=round(sum(st.get("act_s") or 0.0 for st in rec["stations"]), 1),
                   input="real pad in closed loop (not a replayed string)" + (" [placed]" if seg["kind"] == "warp"
                                                                             else ""))
        rec["starts"].append({"meta_sha12": parent.get("meta_sha12") if parent else None, "how": "after an action"})
        rec["string_sha12"] = None
        return rec

    def station(self, i: int, seg: dict, k: int, app: dict, fn, parent: dict | None, rec: dict) -> dict | None:
        """One station of an action (:meth:`action`, :meth:`ride`): the approach ``app`` (searched and replayed as a
        walk, recorded under ``approach``; {} for none), ``fn`` with real input in closed loop on a ``Minigames`` of
        the level, a drain to the next join.  A button or a ride's object with no floor near it on the route graph
        is acted on from where the player stands (X's own walk-up).  A ride's station the player died in
        (:meth:`_lost`) failed, whatever its act read.  The next start's parent; None when it failed (``rec["why"]``
        says why)."""
        from devkit.xemu import minigames as mg
        st: dict = {}
        rec["stations"].append(st)
        if app:
            sub = {**app, "station": k, "starts": [], "attempts": [], "ok": False}
            st["approach"] = sub
            self.searched(i, app, parent, sub)
            if not sub["ok"] and (seg["kind"] == "button" or seg.get("rig")) \
                    and "no goal on the route graph" in (sub.get("why") or ""):
                st["approach_skipped"] = ("the route graph holds no floor near it (d1's seal): X's own walk-up "
                                          "from where the player stands")
                self._walk_up = True                      # act(): a longer X loop (it walks up first)
                if self._seg_start is not None:
                    self.halted_at_start = False
                    self.bring_back(self._seg_start)
            elif not sub["ok"]:
                rec["why"] = f"station {k}'s approach failed: {sub.get('why')}"
                return None
            else:
                parent = {"meta_sha12": sub["starts"][-1]["meta_sha12"], "string_sha12": sub["string_sha12"],
                          "drained": sub["drained"]}
        t0 = time.monotonic()
        g = self.sb.halt()
        clock0 = struct.unpack("<d", g.read(g.regs()["ecx"] + 0x18, 8))[0]
        try:
            res = fn(None if seg["kind"] == "warp" else mg.Minigames(self.sb, self.disc(), seg["level"]))
        except xs.Teardown:   # a signal ends the chain, never a miss (AZ-701)
            raise
        except SystemExit as e:
            res = {"done": False, "error": str(e)[:300]}
        finally:
            self._walk_up = False
        level = seg.get("dest") if seg["kind"] == "warp" else None
        killed = seg.get("how") == "killed"       # the fight drains itself, into the victory's movies
        if killed:
            d = res.pop("drain", None) or {"stop": None, "ticks": 0}
        else:
            d = self.drain(lambda c: c["settled"] >= SETTLE and (level is None or c["level"] == level),
                           max_ticks=ACT_DRAIN)
        g = self.sb.halt()
        clock1 = struct.unpack("<d", g.read(g.regs()["ecx"] + 0x18, 8))[0] if d["stop"] == "join" else None
        ticks = round((clock1 - clock0) * self.rate()) if clock1 is not None and seg["kind"] != "warp" else None
        if ticks:
            self.k += ticks - d["ticks"]          # the drain counted its own; the action's are the clock's
        # a death mid-ride reloads the save, and the act's reads after it are another level's: no outcome (sitting
        # r125s, segment 35: a switch press counted done with the body 487 m off, in w1)
        lost = self._lost(seg) if seg.get("rig") else None
        st.update(act=res, drain=d, act_ticks=ticks if not killed else res.get("ticks"),
                  act_s=round(time.monotonic() - t0, 1),
                  ok=bool(res.get("done")) and lost is None and (killed or d["stop"] == "join"))
        if lost is not None:
            st["lost"] = lost
        self.save()
        self.log(f"segment {i} ({seg['kind']}) station {k}: done {res.get('done')}, {ticks} ticks, "
                 f"{st['act_s']} s, drain {d['stop']}" + (f", {lost}" if lost else ""))
        if not st["ok"]:
            rec["why"] = (f"station {k} of the {seg['kind']} didn't take: "
                          f"{lost or res.get('error') or res.get('why') or 'not done'} (drain {d['stop']})")
            return None
        return {"meta_sha12": parent.get("meta_sha12") if parent else None, "after": f"station {k}"}

    def ride(self, i: int, seg: dict, parent: dict | None, rec: dict) -> dict:
        """A ride on d1's elevator (Step R1.16d; ``seg["rig"]``: a hop between two of its floors, ``plan.ELEVATORS``,
        or a ride the logic leaves out, ``plan.RIDES``), real pad input in closed loop: the elevator read live
        (:func:`lift_state`), :func:`lift_plan`'s first action played as a station (:meth:`station`), planned again,
        until the player stands on the to-node's floor, then a walk into the to-node.  A press walks up to its
        floor switch (searched, radius 1.2 m) and presses X until its toggle flips; a ride walks into the floor's
        call field (searched) and stands there until the deck has come (unless the deck stands there already and
        the body within :data:`LIFT_BY` of it: R1.16d's straight stick from d1_z081 to a deck already called never
        reached it), then walks onto the deck, presses the colour's button (X), stands until the deck has stopped at
        the colour's floor and steps off it into that floor's call field (:meth:`step_off`, AZ-498: the route graph
        holds the deck only at its rest, so the next approach searched from it found no route).  Recorded under
        ``lift``: each action, the plan's length and the colours' floors before it."""
        from azurkit.tools.randomizer.planner.plan import ELEVATORS
        from devkit.xemu import minigames as mg
        floors = ELEVATORS[seg["rig"]]
        at, to = floors[seg["from"]], floors[seg["to"]]
        self._air = int(seg.get("kit", {}).get("air", 0))     # the route pilot's air to a landing (_pilot_to)
        rec["stations"], rec["lift"] = [], {"from": at, "to": to, "actions": []}
        base = {k: seg[k] for k in ("index", "level", "kit", "tier") if k in seg} | {"kind": "walk", "scene": False}
        k = 0
        while at != to:
            if (lost := self._lost(seg)) is not None:  # sitting r125-d1, segment 35: a death on floor 11 reloaded
                rec["why"] = lost                       # the save and the next read of d1's graph ended the chain
                return rec
            try:
                m = mg.Minigames(self.sb, self.disc(), seg["level"])
            except xs.Teardown:   # a signal ends the chain, never a miss (AZ-701)
                raise
            except SystemExit as e:
                rec["why"] = str(e)
                return rec
            if m.gi != 0:
                rec["why"] = f"the live graph is g{m.gi}, not the wiring's g0"
                return rec
            try:
                programs, toggles, keys = lift_state(m)
            except xs.Teardown:   # a signal ends the chain, never a miss (AZ-701)
                raise
            except SystemExit as e:
                rec["why"] = str(e)
                return rec
            plan = lift_plan(at, to, programs, toggles, keys)
            entry = {"at": at, "programs": programs, "plan": None if plan is None else len(plan)}
            rec["lift"]["actions"].append(entry)
            if not plan or len(rec["lift"]["actions"]) > 2 * LIFT_STEPS:
                rec["why"] = (f"no ride from floor {at} to {to} within {LIFT_STEPS} actions (colours {programs}, "
                              f"keys off: {sorted(x for x, on in keys.items() if not on)})" if not plan else
                              f"{2 * LIFT_STEPS} actions and not on floor {to}")
                return rec
            entry["act"] = list(plan[0])
            self.log(f"segment {i} ride: floor {at} > {to}, {len(plan)} actions left, next {plan[0]}")
            if plan[0][0] == "press":
                x = plan[0][1]
                app = base | {"from": seg["from"], "to": seg["from"], "goal": seg["from"],
                              "object": f"{seg['level']}/g0/r{x}", "radius": 1.2}
                fn, before = (lambda m_, x=x: self.press(m_, x)), parent
                parent, k = self._near_first(i, seg, k, m, app, fn, parent, rec)
                if parent is None and "stalled" in str((rec["stations"][-1].get("act") or {}).get("why")) \
                        and self._lost(seg) is None:    # X's walk-up stalled out of reach: an approach to KEYLOCK_R
                    rec.pop("why", None)                # (sitting r125b, 35: switch9 from 1.2 m stalled 1.74 m off)
                    parent, k = self.station(i, seg, k, app | {"radius": KEYLOCK_R}, fn, before, rec), k + 1
                if parent is None:
                    return rec
                continue
            colour = plan[0][1]
            if not (round(m.get(LIFT_CALLED, "inputs[14]")) == at and lift_here(m) and self.by_deck(m)):
                app = base | {"from": seg["from"], "to": seg["from"], "goal": seg["from"],
                              "object": f"{seg['level']}/g0/r{LIFT_CALLS[at]}", "radius": 0.0}
                parent, k = self._near_first(i, seg, k, m, app, lambda m_, f=at: self.call(m_, f), parent, rec)
                if parent is None:
                    return rec
            goal = programs[colour]
            if (parent := self.station(i, seg, k, {}, lambda m_, c=colour, f=goal, a=at: self.board(m_, c, f, a),
                                       parent, rec)) is None:
                return rec
            k += 1
            at = goal
            if (parent := self.station(i, seg, k, {}, lambda m_, f=goal: self.step_off(m_, f), parent, rec)) is None:
                return rec
            k += 1
        R = router(seg["level"])
        if not self._in(R, zones(seg["to"])):          # off the deck into the to-node (searched, replayed)
            app = base | {"from": seg["to"], "to": seg["to"], "goal": seg["to"]}
            if (parent := self.station(i, seg, k, app, lambda m_: {"done": True, "walked": True}, parent,
                                       rec)) is None:
                return rec
        return self.acted(seg, parent, rec)

    def _lost(self, seg: dict) -> str | None:
        """Why a ride can't go on from where the chain halted: the player dead (HP 0, or state 7, at an update
        entry) or another level than the segment's loaded (a death reloads the save); None when it can."""
        w = self.where()
        if not str(w.get("level") or "").endswith("/" + seg["level"]):
            return f"the level changed ({w.get('level')}): the player died [inferred]"
        return "the player died" if w.get("entry") and not w.get("alive") else None

    def _near_first(self, i: int, seg: dict, k: int, m, app: dict, fn, parent: dict | None,
                    rec: dict) -> tuple[dict | None, int]:
        """A ride's station at an object on the player's floor: played from where the player stands first (no
        search: X's own walk-up, the call's walk into its field) when the object is within :data:`RIDE_NEAR` m
        (horizontally, :data:`RIDE_NEAR_Z` up or down) of the body, then with its searched approach if that didn't
        take (sitting r125-d1: each approach on a floor searched to its 480 s cap and the route pilot walked it).
        (the next start's parent, None when neither took; the next station's number)."""
        from devkit.rando.draft.l3_goal import object_points
        try:
            q = object_points(router(seg["level"]).lv, app["object"])
            c, b = (q.min(axis=0) + q.max(axis=0)) / 2, m.body()
            near = math.hypot(c[0] - b[0], c[1] - b[1]) <= RIDE_NEAR and abs(c[2] - b[2]) <= RIDE_NEAR_Z
        except (KeyError, ValueError, OSError):
            near = False
        if near:
            self._walk_up = True                       # X's longer loop: it walks up first (station resets it)
            if (got := self.station(i, seg, k, {}, fn, parent, rec)) is not None:
                return got, k + 1
            rec["stations"][-1]["direct"] = True
            rec.pop("why", None)
            k += 1
            if (lost := self._lost(seg)) is not None:
                rec["why"] = lost
                return None, k
        return self.station(i, seg, k, app, fn, parent, rec), k + 1

    def press(self, m, x: int) -> dict:
        """A floor switch of d1's elevator pressed: X at its shape until its toggle flips."""
        toggle = LIFT_SWITCHES[x][2]
        before = m.get(toggle, "goal")
        r = m.use(x, lambda: abs(m.get(toggle, "goal") - before) >= 0.5, n=480 if self._walk_up else 300)
        return {**r, "switch": x}

    def call(self, m, floor: int) -> dict:
        """d1's elevator called to ``floor``: the stick toward the middle of the floor's call field until the call
        reads that floor, then neutral until the deck has stood there :data:`LIFT_AT` ticks (``LIFT_WAIT`` at
        most).  A body outside the field's footprint first takes the route pilot to the floor's landing nearest it
        (sitting r125-full-f, segment 27: the deck stood called at floor 5 and the call ended at once 20-45 m from
        it, so the boarding's walks never reached it).  A death (HP 0) or another level loaded ends it, its tick
        recorded (``lost_at``, the pilot's ticks counted) with the largest floor the call read before
        (``called_max``; sitting r125b, 35: the end read and the tick count came from w1 after the reload)."""
        from devkit.rando.draft.l3_goal import object_points
        q = object_points(router(m.level).lv, f"{m.level}/g0/r{LIFT_CALLS[floor]}")
        lo, hi = q.min(axis=0), q.max(axis=0)
        c = (lo + hi) / 2
        st = {"k": 0, "here": 0, "in": 0, "hp": [m.hp()] * 2}
        lvl, b = m.loaded(), m.body()
        if not (lo[0] <= b[0] <= hi[0] and lo[1] <= b[1] <= hi[1]) and (near := self.landings(m, floor)):
            st["pilot"] = self._pilot_to(m, near[0][2], st)

        def fn(sb, row, rows):
            st["k"] += 1
            hp = m.hp()
            st["hp"][1] = min(st["hp"][1], hp)
            if hp <= 0 or m.loaded() != lvl:
                st["lost_at"] = st["k"]
                m.stick = (0.0, 0.0)
                return ["stop"]
            p = m.body()
            st["in"] += int(lo[0] <= p[0] <= hi[0] and lo[1] <= p[1] <= hi[1])
            now = round(m.get(LIFT_CALLED, "inputs[14]"))
            st["most"] = max(st.get("most", now), now)
            if now == floor:
                m.stick = (0.0, 0.0)
                st["here"] = st["here"] + 1 if lift_here(m) else 0
                return ["stop"] if st["here"] >= LIFT_AT else []
            m.toward(c, 0.6)
            return []
        m.run(LIFT_WAIT, on_tick=fn, hook_at=xo.INPUT_BUILD)
        m.stick = (0.0, 0.0)
        called = round(m.get(LIFT_CALLED, "inputs[14]")) if m.loaded() == lvl else None
        why = (f"the player died at tick {st['lost_at']} before the deck came (called {st.get('most')} at most)"
               if "lost_at" in st else f"the deck didn't come (called {called})")
        return {"done": st["here"] >= LIFT_AT, "called": called, "called_max": st.get("most"), "ticks": st["k"],
                "in_field": st["in"], "hp": [*st["hp"], m.hp()], **({"pilot": st["pilot"]} if "pilot" in st else {}),
                **({"lost_at": st["lost_at"]} if "lost_at" in st else {}),
                **({} if st["here"] >= LIFT_AT else {"why": why})}

    def board(self, m, colour: str, floor: int, at: int | None = None) -> dict:
        """The ride itself: the stick toward the deck's middle until the feet are in its footprint (the deck only
        moves up and down the shaft) for 8 ticks, X at the colour's button (where it stands now) until the call reads
        ``floor``, then neutral until the deck has stood at its goal :data:`LIFT_AT` ticks, the player still in its
        footprint and 1 m or more from the height the ride left (d1's floors stand 15 m apart or more).  A straight
        walk that makes no headway goes by the floor ``at``'s landings instead (:meth:`landings`, each at the deck's
        edge, the one nearest the body first: the route pilot to it, then straight onto the deck; sitting
        r125-full-b, segment 27: 629 ticks at floor 5 from where the walk before ended and never onto the deck,
        which a step-off left by its -x landing in r125-d1; r125-full-d: straight walks to the landings nearest the
        body stalled too)."""
        import numpy as np

        from devkit.rando.draft.l3_goal import object_points
        q = object_points(router(m.level).lv, f"{m.level}/g0/r{LIFT_DECK}")
        lo, hi = q.min(axis=0), q.max(axis=0)
        c = (lo + hi) / 2
        pad = min(0.3, float(np.min(hi[:2] - lo[:2])) / 4)
        st = {"k": 0}

        def on() -> bool:
            b = m.body()
            return lo[0] + pad <= b[0] <= hi[0] - pad and lo[1] + pad <= b[1] <= hi[1] - pad
        ways = [None] + ([v for _, _, v in self.landings(m, at, near=c)] if at is not None else [])
        tried = []
        for via in ways:
            if via is not None:                        # to the landing at the deck's edge by the route pilot
                tried.append(self._pilot_to(m, via, st))
            tried.append(self._walk(m, c, on, st, mag=0.5 if via is None else 1.0, jump=via is not None))
            if tried[-1]["done"]:
                break
        m.stick = (0.0, 0.0)
        if not tried[-1]["done"]:
            return {"done": False, "why": "not onto the deck", "ticks": st["k"], "ways": tried}
        r = m.use(LIFT_COLOURS[colour][1], lambda: round(m.get(LIFT_CALLED, "inputs[14]")) == floor, n=300)
        if not r["done"]:
            return {"done": False, "why": f"{colour}'s button didn't call floor {floor}", "use": r}
        z0 = m.body()[2]
        wait = {"k": 0, "here": 0}

        def ride(sb, row, rows):
            wait["k"] += 1
            wait["here"] = wait["here"] + 1 if lift_here(m) else 0
            return ["stop"] if wait["here"] >= LIFT_AT else []
        m.run(LIFT_WAIT, stick=(0.0, 0.0), on_tick=ride, hook_at=xo.INPUT_BUILD)
        b = m.body()
        rode = lo[0] <= b[0] <= hi[0] and lo[1] <= b[1] <= hi[1] and abs(b[2] - z0) >= 1.0
        stopped = wait["here"] >= LIFT_AT and round(m.get(LIFT_CALLED, "inputs[14]")) == floor
        ok = stopped and rode
        return {"done": ok, "colour": colour, "floor": floor, "ticks": st["k"] + r["ticks"] + wait["k"],
                **({} if ok else {"why": f"the deck didn't stop at floor {floor}" if not stopped else
                                  f"the deck stopped at floor {floor} without the player"})}

    def by_deck(self, m) -> bool:
        """Whether the body stands within :data:`LIFT_BY` (horizontally) of the deck's footprint."""
        lo, hi = lift_box(m.level, LIFT_DECK)
        b = m.body()
        return lo[0] - LIFT_BY <= b[0] <= hi[0] + LIFT_BY and lo[1] - LIFT_BY <= b[1] <= hi[1] + LIFT_BY

    def landings(self, m, floor: int, near=None) -> list[tuple[float, str, tuple]]:
        """A floor's landings by d1's deck: per side of the deck, the walk vertex of the floor's call field
        :data:`LIFT_OFF` or more off the deck's footprint nearest the body (or the point ``near``: the deck's middle
        for a boarding, the landing at its edge), as (its distance from the body, the side, the point), nearest the
        body first; [] when the field has none."""
        import numpy as np
        R = router(m.level)
        lo, hi = lift_box(m.level, LIFT_CALLS[floor])
        dlo, dhi = lift_box(m.level, LIFT_DECK)
        X, Y, Z = R.X, R.Y, R.Z
        field = (X >= lo[0]) & (X <= hi[0]) & (Y >= lo[1]) & (Y <= hi[1]) & (Z >= lo[2] - 2.0) & (Z <= hi[2] + 1.0)
        deck = (X >= dlo[0] - LIFT_OFF) & (X <= dhi[0] + LIFT_OFF) & (Y >= dlo[1] - LIFT_OFF) & \
            (Y <= dhi[1] + LIFT_OFF)
        js = np.nonzero(field & ~deck & (R.node >= 0))[0]
        if not len(js):
            return []
        b, dc = m.body(), (dlo + dhi) / 2
        dx, dy = X[js] - dc[0], Y[js] - dc[1]
        sides = {"+x": (dx > 0) & (abs(dx) >= abs(dy)), "-x": (dx < 0) & (abs(dx) >= abs(dy)),
                 "+y": (dy > 0) & (abs(dy) > abs(dx)), "-y": (dy < 0) & (abs(dy) > abs(dx))}
        q = b if near is None else near
        d = np.hypot(X[js] - q[0], Y[js] - q[1])
        out = []
        for name, sel in sides.items():
            if sel.any():
                v = int(js[sel][np.argmin(d[sel])])
                out.append((float(math.hypot(X[v] - b[0], Y[v] - b[1])), name, (float(X[v]), float(Y[v]), float(Z[v]))))
        return sorted(out)

    def _pilot_to(self, m, point, st: dict) -> dict:
        """The route pilot (``xemu_route.walk_to``, closed loop on the level's route graph) to ``point``, at most
        :data:`OFF_TICKS` x 4 ticks (``st["k"]`` counts them): {done, ticks, left_m}."""
        from devkit.xemu import route as xr
        R = router(m.level)
        if "_lists" not in R.__dict__:      # load_router drops the planner's lists (the workers' memory)
            R._lists = (R.indptr.tolist(), R.dst.tolist(), R.cost.tolist())
        res = xr.walk_to(self.sb, R, tuple(point), tier="hard", air=getattr(self, "_air", 0), ticks=4 * OFF_TICKS)
        st["k"] += res["ticks"]
        return {"done": bool(res["reached"]), "ticks": res["ticks"], "left_m": res.get("left_m"), "pilot": True}

    @staticmethod
    def _walk(m, target, until, st: dict, *, mag: float = 1.0, n: int = OFF_TICKS, jump: bool = False) -> dict:
        """The stick toward ``target`` until ``until()`` holds 8 ticks running, or no headway (0.1 m) comes in
        :data:`OFF_STUCK` ticks (with ``jump``, the first such stall gets a jump instead: the deck's edge, which a
        step-off at floor 5 crossed only with one), at most ``n`` ticks (``st["k"]`` counts them):
        {done, ticks, left_m, jumped}."""
        t = {"k": 0, "in": 0, "best": 1e9, "best_k": 0, "y": 0, "jumped": False}

        def fn(sb, row, rows):
            st["k"] += 1
            t["k"] += 1
            t["in"] = t["in"] + 1 if until() else 0
            if t["in"] >= 8:
                m.stick = (0.0, 0.0)
                return ["stop"] + (["up y"] if t["y"] else [])
            p = m.body()
            left = math.hypot(target[0] - p[0], target[1] - p[1])
            if left < t["best"] - 0.1:
                t["best"], t["best_k"] = left, t["k"]
            acts = []
            if t["y"] and t["k"] - t["y"] >= 6:
                t["y"] = 0
                acts.append("up y")
            if t["k"] - t["best_k"] >= OFF_STUCK:
                if not (jump and not t["jumped"]):
                    m.stick = (0.0, 0.0)
                    return acts + ["stop"] + (["up y"] if t["y"] else [])
                t["jumped"], t["y"], t["best_k"] = True, t["k"], t["k"]
                acts.append("down y")
            m.toward(target, mag)
            return acts
        m.run(n, on_tick=fn, hook_at=xo.INPUT_BUILD)
        m.stick = (0.0, 0.0)
        return {"done": t["in"] >= 8, "ticks": t["k"], "left_m": round(t["best"], 1), "jumped": t["jumped"]}

    def step_off(self, m, floor: int) -> dict:
        """Off d1's deck after a ride, into the floor's call field (AZ-498: the route graph holds the deck only at its
        rest, so an approach searched from it at another floor found no route, R1.16e's 27, 33 and 35).  The field's
        box holds the deck's footprint, so the walk aims at a walk vertex of the field :data:`LIFT_OFF` or more off
        the deck: one per side of the deck (the nearest the body on that side), nearest first, each with the stick
        full toward it until the feet stand in the field off the deck for 8 ticks; a side where the body makes no
        headway for :data:`OFF_STUCK` ticks gets a jump (Y) when its vertex stands higher than the feet, then the
        next side (sitting r116f-final-c: at floors 5 and 3 one vertex at half stick for 300 ticks never got off,
        at floor 1 it did in 61).  No deck wait: the deck stands at this floor.  The record keeps each side tried,
        its ticks, the distance left, whether it jumped, the landing's rise over the feet where it ended and, in metres
        from the deck's middle, where it started, ended and aimed (sitting r125b: the rides leave the body at the
        deck's middle, by its colour buttons)."""
        lo, hi = lift_box(m.level, LIFT_CALLS[floor])
        dlo, dhi = lift_box(m.level, LIFT_DECK)
        targets = self.landings(m, floor)
        if not targets:
            return {"done": False, "floor": floor, "why": f"no walk vertex of CallField{floor} off the deck"}
        st = {"k": 0, "off": 0}
        tried = []

        def off_deck() -> bool:
            p = m.body()
            on = dlo[0] <= p[0] <= dhi[0] and dlo[1] <= p[1] <= dhi[1]
            ins = lo[0] <= p[0] <= hi[0] and lo[1] <= p[1] <= hi[1] and lo[2] - 2.0 <= p[2] - 1.0 <= hi[2] + 1.0
            return ins and not on
        for _, side, target in targets:
            b0, dc0 = m.body(), (dlo + dhi) / 2
            t = {"side": side, "ticks": 0, "jumped": False, "best": 1e9, "best_k": 0, "y": 0,
                 "from": [round(float(b0[0] - dc0[0]), 1), round(float(b0[1] - dc0[1]), 1)]}

            def fn(sb, row, rows, t=t, target=target):
                st["k"] += 1
                t["ticks"] += 1
                st["off"] = st["off"] + 1 if off_deck() else 0
                if st["off"] >= 8:
                    m.stick = (0.0, 0.0)
                    return ["stop"] + (["up y"] if t["y"] else [])
                p = m.body()
                left = math.hypot(target[0] - p[0], target[1] - p[1])
                if left < t["best"] - 0.1:
                    t["best"], t["best_k"] = left, t["ticks"]
                acts = []
                if t["y"] and t["ticks"] - t["y"] >= 6:
                    t["y"] = 0
                    acts.append("up y")
                if t["ticks"] - t["best_k"] >= OFF_STUCK:
                    if not t["jumped"] and target[2] > p[2] - 1.0 + 0.3:
                        t["jumped"], t["y"], t["best_k"] = True, t["ticks"], t["ticks"]
                        acts.append("down y")
                    else:
                        m.stick = (0.0, 0.0)
                        return acts + ["stop"]
                m.toward(target, 1.0)
                return acts
            m.run(OFF_TICKS, on_tick=fn, hook_at=xo.INPUT_BUILD)
            m.stick = (0.0, 0.0)
            p, dc = m.body(), (dlo + dhi) / 2                  # relative metres: the deck's middle, the landing
            tried.append({"side": t["side"], "ticks": t["ticks"], "left_m": round(t["best"], 1), "jumped": t["jumped"],
                          "rise_m": round(target[2] - (p[2] - 1.0), 2), "from": t["from"],
                          "at": [round(float(p[0] - dc[0]), 1), round(float(p[1] - dc[1]), 1)],
                          "to": [round(float(target[0] - dc[0]), 1), round(float(target[1] - dc[1]), 1)]})
            if st["off"] >= 8:
                break
        ok = st["off"] >= 8
        return {"done": ok, "floor": floor, "ticks": st["k"], "sides": tried, **({} if ok else {"why": "not off the deck"})}

    def act(self, seg: dict, m=None) -> dict:
        """The action itself at its object, real pad input (``xemu_minigames``' closed loops; positions stay in
        memory): ``done`` and counts."""
        kind, how = seg["kind"], seg.get("how")
        if kind == "warp":
            r = self.s.warp(seg["dest"], seg.get("spot"))
            return {"done": bool(r.get("ok")), **{k: r.get(k) for k in ("s", "taps", "spot_written", "loads")}}
        if kind == "barrier":
            return self.staff(m, seg)
        if kind == "button" and (touch := self.touch_of(seg)) is not None:
            rec, st = _record(m, seg["goal"]), {"k": 0}      # the approach stood on the shape: its toggle's goal

            def fn(sb, row, rows):
                st["k"] += 1
                return ["stop"] if m.get(rec, "goal") >= 1 else []
            m.run(90, stick=(0.0, 0.0), on_tick=fn, hook_at=xo.INPUT_BUILD)
            return {"done": m.get(rec, "goal") >= 1, "checked": True, "touch": touch, "ticks": st["k"]}
        if kind == "button":
            rec = None
            if seg.get("lock_toggle"):
                _, gs, rs = seg["lock_toggle"].split("/")
                rec = int(rs[1:]) if int(gs[1:]) == m.gi else None
            obj = _record(m, seg["goal"])
            done = (lambda: m.get(rec, "goal") >= 1) if rec is not None else (lambda: False)
            r = m.use(obj, done, n=300 if rec is not None else 240 if self._walk_up else 60)
            if rec is not None and not r["done"]:      # AZ-498 (r669, 25 X presses from inside its sphere): once
                again = m.use(obj, done, n=240, standoff=KEYLOCK_STANDOFF)   # more from outside it, faced afresh
                r = {**again, "first": {k: r[k] for k in ("ticks", "gap_m", "why") if k in r}}
            if rec is not None and (ab := self._action_toggle(m, obj)) is not None:
                r["action_button"] = round(m.get(ab, "goal"), 2)   # X taken as the lock's use (its key aside)
            return {**r, "done": r["done"] if rec is not None else True, "checked": rec is not None}
        if how == "touch":
            return self.touched(m, seg["object"], self._before, platform=bool(seg.get("platform")))
        if how == "action":
            r = m.use(_record(m, seg["object"]), lambda: False, n=48)
            return {**r, "done": True, "checked": False}
        if how == "hit":
            return self.attack(m, seg["object"])
        return {"done": False, "why": f"no way to set {seg.get('flag')}"}

    @staticmethod
    def _action_toggle(m, obj) -> int | None:
        """The toggle a keylock's shape turns on with X (its ``actionButton`` plug: ``ActionButton_toggle``, on
        whether or not a key opens it), None when it has none or can't be read."""
        try:
            i = m.find(obj)
            return next((lk.dst for lk in m.g.links(i) if m.g.plug_name(i, lk.src_plug) == "actionButton"), None)
        except (KeyError, ValueError, AttributeError):
            return None

    def toggles_before(self, seg: dict) -> dict[str, float] | None:
        """A touch event's toggles (:func:`toggles`) read where its approach starts (AZ-501): {name: goal}, None
        when they can't be read (no single record, another graph)."""
        from devkit.xemu import minigames as mg
        try:
            self.sb.halt()
            m = mg.Minigames(self.sb, self.disc(), seg["level"])
            rec = _record(m, event_object(seg))
            return {n: m.get(t, "goal") for n, (t, _, _) in toggles(m, m.find(rec)).items()}
        except xs.Teardown:   # a signal ends the chain, never a miss (AZ-701)
            raise
        except (KeyError, ValueError, OSError, SystemExit):
            return None

    def touched(self, m, obj: str, before: dict | None = None, platform: bool = False) -> dict:
        """A touch event's outcome (AZ-483): the shape node's ``touch``, which the game sets in the player's tick
        while the body centre is inside the shape (the touch query 0x60BD0 from 0x85587, the platform's 0x7A167)
        and a scheduled event clears a tick later; read at each tick's state machine, standing still, up to
        :data:`TOUCH_WAIT` ticks.  Else a rise of a toggle the touch drives (:func:`toggles`) during the wait that
        the event's own input explains (AZ-501): the toggle off ``before`` (read before the approach,
        :meth:`toggles_before`) or at a tick of the wait, then on at a tick its OR's input from this shape's way
        reads on.  A toggle on with no reading before, on before the approach, or set by another input of its OR
        (sitting R1.16e: d1's W1_toggle came on during the approach to BeamShape r523, whose own touch never read
        on; each toggle is a 3 s switch on an OR of a beam and two walkways) is no outcome: the miss says which, and
        the record keeps each toggle's reading before, the wait's tick it read on and its own input's, and the
        other inputs on then.  A ``platform`` (stood on, not a volume the body centre stands in: d1's walkway
        plates, AZ-497) that stand left untouched is tried again in :data:`TOUCH_TRIES`' ways, watched the same
        way, until one takes (``how``): onto the middle of its mesh (an approach to its box's footprint may end in a
        corner of a turned plate's box, off the plate: segment 23's), a hop there (a landing on it), and a walk
        across it and back (onto it moving: segment 8's EW_toggle rose as its approach walked on, standing never
        fired one)."""
        try:
            rec = _record(m, obj)
            m.get(rec, "touch")
        except (KeyError, ValueError) as e:              # no single record of that name: say so, unchecked
            return {"done": True, "checked": False, "why": f"its touch can't be read: {e}"}
        tg = toggles(m, rec if isinstance(rec, int) else m.by[rec][0])
        st = {"k": 0, "seen": False, "low": set(), "on": {}, "own": {}, "others": {}, "rose": set()}

        def read(node: int, plug: str) -> float:
            try:
                return m.get(node, plug)
            except (KeyError, ValueError, OSError):
                return 0.0

        def fn(sb, row, rows):
            st["k"] += 1
            st["seen"] = st["seen"] or m.get(rec, "touch") >= 1
            for n, (t, node, plug) in tg.items():
                if m.get(t, "goal") < 0.5:
                    st["low"].add(n)
                    continue
                if n not in st["on"]:
                    st["on"][n] = st["k"]
                    st["others"][n] = sorted(m.g.names[i] for i, _, _, _, dp in m.ins(node)
                                             if dp != plug and read(node, dp) >= 0.5)
                if read(node, plug) >= 0.5:
                    st["own"].setdefault(n, st["k"])
                    if n in st["low"] or before is not None and before.get(n, 1.0) < 0.5:
                        st["rose"].add(n)
            return bool(st["seen"] or st["rose"])

        tries = [("stand", None)] + (list(TOUCH_TRIES) if platform else [])
        centre = self._platform_centre(m, obj) if platform else None
        out_tries = []
        for how, n in tries:
            if how != "stand" and how != "hop" and centre is None:
                continue
            k0, steer = st["k"], self._touch_steer(m, how, centre)
            m.run(n or TOUCH_WAIT, stick=(0.0, 0.0), on_tick=lambda sb, row, rows: (
                ["stop"] + (["up y"] if st.pop("y", False) else []) if fn(sb, row, rows) else steer(st)),
                hook_at=xo.INPUT_BUILD)
            m.stick = (0.0, 0.0)
            out_tries.append({"how": how, "ticks": st["k"] - k0})
            if st["seen"] or st["rose"]:
                break
        done = st["seen"] or bool(st["rose"])
        out = {"done": done, "checked": True, "ticks": st["k"],
               **({"tries": out_tries, "how": out_tries[-1]["how"] if done else None} if platform else {})}
        if tg:
            out["toggles"] = {n: {"before": None if before is None or n not in before else round(before[n], 2),
                                  "on_at": st["on"].get(n), "own_on_at": st["own"].get(n),
                                  **({"others_on": st["others"][n]} if st["others"].get(n) else {})} for n in tg}
        if not st["seen"] and st["rose"]:
            out["by"] = f"{', '.join(sorted(st['rose']))} rose, its OR's input from this touch on"
        if not done:
            why = []
            for n in sorted(tg):
                if n not in st["on"]:
                    why.append(f"{n} stayed off")
                elif n not in st["own"]:
                    why.append(f"{n} came on, not by this touch's input"
                               + (f" ({', '.join(st['others'][n])} on)" if st["others"].get(n) else ""))
                elif before is None:
                    why.append(f"{n} on, not read before the approach")
                else:
                    why.append(f"{n} on before the approach")
            out["why"] = "its touch never fired" + (f": {'; '.join(why)}" if why else
                                                    ": the body centre isn't inside the shape")
        return out

    @staticmethod
    def _platform_centre(m, obj: str):
        """(the middle of a platform's mesh: its vertices' mean, on a plate, not in its box's corner; half its box's
        diagonal), None when the level file holds no mesh of that name."""
        from devkit.rando.draft.l3_goal import object_points
        try:
            q = object_points(router(m.level).lv, obj)
        except (KeyError, ValueError, AttributeError):
            return None
        return q.mean(axis=0), float(math.hypot(*(q.max(axis=0) - q.min(axis=0))[:2])) / 2

    @staticmethod
    def _touch_steer(m, how: str, mid):
        """The pad of one way a platform's touch is tried (:meth:`touched`), a tick at a time on its state: the
        stick neutral (``stand``); onto the mesh's middle ``c`` until within :data:`TOUCH_MID` m 4 ticks running
        (``centre``); Y for 6 ticks (``hop``); off the plate's far side, 1 m past its box's half diagonal ``r`` from
        ``c`` the way the body faces it (``mid`` is ``(c, r)``), then back to ``c`` (``across``)."""
        c, r = mid if mid is not None else (None, 0.0)

        def steer(st: dict) -> list:
            k = st.setdefault(how, 0) + 1
            st[how] = k
            if how == "stand":
                return []
            if how == "hop":
                if k == 1:
                    st["y"] = True
                    return ["down y"]
                if k == 7 and st.pop("y", False):
                    return ["up y"]
                return []
            p = m.body()
            if how == "centre":
                if math.hypot(c[0] - p[0], c[1] - p[1]) < TOUCH_MID:
                    st["mid"] = st.get("mid", 0) + 1
                    m.stick = (0.0, 0.0)
                    return ["stop"] if st["mid"] >= 4 else []
                st["mid"] = 0
                m.toward(c, 0.4)
                return []
            if "far" not in st:                                           # across: off the far side, past c
                d = math.hypot(c[0] - p[0], c[1] - p[1])
                u = ((c[0] - p[0]) / d, (c[1] - p[1]) / d) if d > 0.05 else (1.0, 0.0)
                st["far"] = (c[0] + u[0] * (r + 1.0), c[1] + u[1] * (r + 1.0), c[2])
            to = c if st.get("back") else st["far"]
            if math.hypot(to[0] - p[0], to[1] - p[1]) < 0.4:
                if st.get("back"):
                    m.stick = (0.0, 0.0)
                    return ["stop"]
                st["back"] = True
            m.toward(to, 0.6)
            return []
        return steer

    def staff(self, m, seg: dict) -> dict:
        """A barrier crossed (r113's recipe, closed loop): face its shape, cast the staff's elements (LT, each
        element's button, release LT; a ``carry`` barrier only releases the LT held since its store, at the same
        tick), then walk toward the shape's mirror point attacking every :data:`THROUGH_EVERY` ticks, until the
        feet stand in the hop's to-node (its zones) for :data:`THROUGH_IN` ticks, at most :data:`THROUGH_MAX` ticks
        of walking.  An attack only opens the wall within its reach and the approach may end 7-9 m short of it,
        with enemies knocking the body back (R1.16's FireWall_03: three attacks from there, then a fixed 60-tick
        walk, never got through; attacking on the way did, 3 of 3 variants).  Passed when the feet end in the
        to-node.  The barrier's own switches (:func:`barrier_switches`) are read before and after; a barrier whose
        from-node is its to-node (the tour's ``.destroyed`` need or an item inside it: R1.16e's IceBlock_01, AZ-500)
        has no node to cross, so its walk ends, done, when a switch has moved, and isn't done when none did."""
        from devkit.rando.draft.l3_goal import object_points
        R = router(seg["level"])
        p = object_points(R.lv, seg["shapes"][0])
        c = (p.min(axis=0) + p.max(axis=0)) / 2
        carry = bool(self._held)
        cast = [] if carry else [ELEM_BTN[e] for e in seg.get("cast", ())]     # a carry casts what it stored
        to, same = zones(seg["to"]), seg["from"] == seg["to"]
        if self.in_the_way(seg, c, m.body()) is False:
            return {"done": True, "passed": None, "not_in_the_way": True, "ticks": 0, "cast": None}
        sw = {g: r for g in barrier_switches(seg) if (r := _live(m, g)) is not None}
        if same and not sw:
            return {"done": False, "ticks": 0, "why": "a barrier with no node to cross and no switch in the live "
                                                      "graph: whether it opened can't be read"}
        before = {g: m.get(r, "goal") for g, r in sw.items()}
        st = {"k": 0, "far": None, "in": 0}
        lt_up = 18 + 3 * len(cast)                     # LT released (21 for one element, as the variants)
        at = lt_up + 4                                 # the walk's first tick

        def moved() -> bool:
            return any(abs(m.get(r, "goal") - before[g]) >= 0.5 for g, r in sw.items())

        def fn(sb, row, rows):
            st["k"] += 1
            k, acts = st["k"], []
            if k <= 12:
                m.toward(c, 0.15)
            elif k < at:
                m.stick = (0.0, 0.0)
            else:
                b = m.body()
                if st["far"] is None:
                    st["far"] = (2 * c[0] - b[0], 2 * c[1] - b[1], c[2])
                here = moved() if same else R.zone_at((b[0], b[1], b[2] - recipes.LIFT)) in to
                st["in"] = st["in"] + 1 if here else 0
                if st["in"] >= (1 if same else THROUGH_IN) or k >= at + THROUGH_MAX:
                    m.stick = (0.0, 0.0)
                    return ["up a", "stop"]
                m.toward(st["far"], 1.0)
                j = (k - at) % THROUGH_EVERY
                acts += ["down a"] if j == 0 and not st["in"] else ["up a"] if j == 4 else []
            if cast and k == 14:
                acts.append("down ltrigger")
            for j, b in enumerate(cast):
                acts += [f"down {b}"] if k == 16 + 3 * j else [f"up {b}"] if k == 17 + 3 * j else []
            if (cast or carry) and k == lt_up:
                acts.append("up ltrigger")
            return acts
        meta = m.run(at + THROUGH_MAX + 4, on_tick=fn, hook_at=xo.INPUT_BUILD)
        m.stick = (0.0, 0.0)
        if carry:
            self._held = frozenset()                   # released: the store cast (the pipe's LT up)
        b = m.body()
        z = R.zone_at((b[0], b[1], b[2] - recipes.LIFT))
        passed = z in to
        after = {g: m.get(r, "goal") for g, r in sw.items()}
        opened = any(abs(after[g] - before[g]) >= 0.5 for g in sw) if sw else None
        out = {"done": bool(opened) if same else passed, "passed": None if same else passed,
               "zone_in_to": passed, "ticks": st["k"], "stop": meta.get("stop"), "cast": seg.get("cast"),
               **({"released_at": lt_up} if carry else {}),
               **({"switches": {g: [round(before[g], 2), round(after[g], 2)] for g in sw}, "opened": opened}
                  if sw else {})}
        if same and not opened:
            out["why"] = "no switch of the barrier moved"
        return out

    def in_the_way(self, seg: dict, c, body) -> bool | None:
        """Whether a barrier hop's wall (centre ``c``) stands between the body and the hop's to-node: crossing to
        its mirror point brings the to-node nearer (the logic graph's cost to go, ``sim.douse.in_the_way``).  A
        hop's ``through`` list names a barrier its derived zone path touches, which the walk may not cross (R1.16:
        w2_z034 > w2_z011 lists FireWall_02, 28 m behind the body, with the to-node 20 m ahead); then the action is
        skipped and the hop's walk segment routes on.  A barrier whose from-node is its to-node is always in the
        way (AZ-500): the tour asks it for its own sake (a hop's ``.destroyed`` need, an item it contains), and the
        cost test can't tell, the body standing in the to-node already (``douse.in_the_way`` stays an edge's test,
        ``l3_certify``'s douse crossing only edges).  None when the graph can't tell."""
        if seg.get("from") == seg.get("to"):
            return True
        try:
            g = self.goal({"kind": "walk", "level": seg["level"], "goal": seg["to"], "kit": seg.get("kit", {})},
                          "logic")
            return dz.in_the_way(g.cost, c, body)
        except (KeyError, ValueError):
            return None

    def attack(self, m, obj: str) -> dict:
        """A hit on an object (a gem stone, a crystal): face it, then A three times."""
        from devkit.rando.draft.l3_goal import object_points
        p = object_points(router(m.level).lv, obj)
        c = (p.min(axis=0) + p.max(axis=0)) / 2
        st = {"k": 0}

        def fn(sb, row, rows):
            st["k"] += 1
            k = st["k"]
            if k <= 10:
                m.toward(c, 0.12)
            else:
                m.stick = (0.0, 0.0)
            return ["down a"] if k in (12, 26, 40) else ["up a"] if k in (16, 30, 44) else ["stop"] if k >= 60 else []
        m.run(64, on_tick=fn, hook_at=xo.INPUT_BUILD)
        m.stick = (0.0, 0.0)
        return {"done": True, "checked": False, "ticks": st["k"]}

    @staticmethod
    def touch_of(seg: dict) -> str | None:
        """A button whose object fires on a touch of a shape, not on X (d1's seal: ``SealActivate_andCombiner`` is
        a touch of ``discDeath:SealShape`` AND the five disc counts; its toggle r390 has no mesh to press X at):
        that shape's generated id, else None."""
        gen = database().generated_objects.get(seg.get("goal"), (None, None, {}))[2]
        touch = (gen.get("touch") or [None])[0]
        return touch.split()[0] if touch else None

    @staticmethod
    def boss(seg: dict) -> dict | None:
        """The generated boss whose death sets the event ``seg["flag"]`` (d1's ``spideyzar``), None for another."""
        doc = database().generated.get(seg["level"], {})
        return next((b for b in doc.get("bosses", ()) if b.get("event") == seg.get("flag")), None)

    def call_field(self, m, boss: dict) -> dict:
        """Walk into the call field the boss's enable names (``touch(CallField<N>Shape)`` beside a call test
        ``{in{N}}``: d1's elevator called to floor 9, Spideyzar's floor), stick toward its middle until the feet stand
        in its footprint for 8 ticks (300 at most)."""
        import re
        from devkit.rando.draft.l3_goal import object_points
        floors = re.findall(r"\{in\{(\d+)\}\}", boss.get("enabled_by") or "")
        name = next((f"CallField{n}Shape" for n in floors if f"CallField{n}Shape" in m.by), None)
        if name is None:
            return {"field": None, "in": False}
        p = object_points(router(m.level).lv, name)
        lo, hi = p.min(axis=0), p.max(axis=0)
        c = (lo + hi) / 2
        st = {"in": 0}

        def fn(sb, row, rows):
            b = m.body()
            st["in"] = st["in"] + 1 if lo[0] <= b[0] <= hi[0] and lo[1] <= b[1] <= hi[1] else 0
            if st["in"] >= 8:
                m.stick = (0.0, 0.0)
                return ["stop"]
            m.toward(c, 0.6)
            return []
        m.run(300, on_tick=fn, hook_at=xo.INPUT_BUILD)
        m.stick = (0.0, 0.0)
        return {"field": name, "in": st["in"] >= 8}

    def fight(self, m, seg: dict, assisted: bool = True) -> dict:
        """A boss killed (Step R1.16c), real pad input in closed loop on his body and HP, the RAM read, never
        written: his generator's critter awaited (``_generated``; when none comes, a touch of the call field his
        enable names, :meth:`call_field`, and the wait again); the game's own no-damage and refill cheats entered
        through the pad (``Sitting.cheat``: the kit stands in for a playthrough's HP and fuel, so the fight is
        [assisted]); EAFW selected (an armor AI blocks no ``elem`` hit: Spideyzar's hit handler 0x2C790 blocks only
        the armor group his mapper 0x2B7F0 gives, -1 for ``elem``); then in FIGHT_CHUNK pieces: close to the reach,
        face him, A every 12 ticks (the three-swing combo), the selection, fuel and reach checked between pieces
        (closer while no swing lands); until his HP reads 0, then a drain into the kill's outcome: his generator's
        ``numDead`` (the flag) and the level loads that follow (d1's EndGame: the victory's movies).
        ``assisted`` False (AZ-499: chased, Spideyzar stalks at about 9 m and flees after each attack, so R1.16e's
        unassisted tries never swung): no cheat, the kit's own HP and fuel; the player holds ground (the stick
        neutral while he is beyond :data:`FIGHT_REACH`), and as he closes to attack (his ``attackRange`` 2 m) steps
        in to :data:`FIGHT_SWING`, turns toward him at 0.12 there and swings; each piece selects the next of
        :data:`FIGHT_STAFFS` whose elements all have fuel (40 a hit at cost 1 from each, EAFW 400 at cost 80), so
        the damage type his armor's group meets turns too.  Each piece records its swings, the swings he was within
        reach and faced, and his nearest distance (rounded), so a fight with no damage says why."""
        from devkit.xemu import route as xr
        sb, boss = m.sb, self.boss(seg)
        rec = _record(m, boss["id"])
        out: dict = {"boss": boss["critter"], "generator": boss["id"], "assisted": assisted, "assists": [],
                     "pieces": []}

        def dead() -> bool:
            try:
                return m.get(rec, "numDead") >= 1
            except OSError:
                return False

        def wait_spawn(n: int) -> int | None:
            st = {"cr": None, "k": 0}

            def fn(sb_, row, rows):
                st["k"] += 1
                st["cr"] = _generated(m, rec)
                return ["stop"] if st["cr"] or dead() else []
            m.run(n, stick=(0.0, 0.0), on_tick=fn, hook_at=xo.INPUT_BUILD)
            out["spawn_ticks"] = out.get("spawn_ticks", 0) + st["k"]
            return st["cr"]
        cr = _generated(m, rec) or wait_spawn(SPAWN_TICKS)
        if cr is None and not dead():                  # the elevator rides to the called floor first (r116c: 330
            out["call"] = self.call_field(m, boss)     # ticks from 320 m off), then his generator enables
            cr = wait_spawn(3 * SPAWN_TICKS) if out["call"]["in"] else None
        out["enable"] = m.get(rec, "enable")
        if cr is None:
            return {**out, "done": dead(), "why": f"no critter on {boss['id']}'s list (enable {out['enable']})"}

        def hp_of(c: int) -> int:
            return struct.unpack("<i", sb.read(c + recipes.CR_HP, 4))[0]
        out["boss_hp"] = [hp_of(cr), struct.unpack("<i", sb.read(cr + recipes.CR_HP + 4, 4))[0]]
        for name in ("no_damage", "refill") if assisted else ():
            try:
                self.s.cheat(name)
                out["assists"].append(name)
            except xs.Teardown:   # a signal ends the chain, never a miss (AZ-701)
                raise
            except SystemExit as e:
                out.setdefault("assist_errors", []).append(f"{name}: {str(e)[:120]}")
        inv = recipes.chain(sb.read_u32)["inv"]
        fuel = [recipes.SLOT0 + 12 * recipes.SLOTS.index(f) + 4 for f in ("ef", "af", "ff", "wf")]
        st = {"k": 0, "reach": FIGHT_REACH if assisted else FIGHT_SWING, "seen": out["boss_hp"][0], "landed_k": 0,
              "a": False, "end": None}

        def fn(sb_, row, rows):
            st["k"] += 1
            k, acts = st["k"], []
            hp = hp_of(cr)
            ent = row["ent"]
            if hp <= 0 or hp_of(sb.read_u32(ent + 0x20)) <= 0 or sb.read_u32(ent + 0x94) == 7:
                st["end"] = "his HP is 0" if hp <= 0 else "the player died"
                m.stick = (0.0, 0.0)
                return (["up a"] if st["a"] else []) + ["stop"]
            if hp < st["seen"]:
                st["seen"], st["landed_k"] = hp, k
            elif assisted and k - st["landed_k"] > 150 and st["reach"] > FIGHT_CLOSE:   # 5 s, no swing landing: closer
                st["reach"], st["landed_k"] = round(st["reach"] - 0.4, 1), k
            b = struct.unpack("<3f", sb.read(cr + recipes.CR_BODY, 12))
            p = m.body()
            gap = math.hypot(b[0] - p[0], b[1] - p[1])
            st["min_gap"] = min(st.get("min_gap", 1e9), gap)
            far = gap > st["reach"]
            yaw = math.degrees(struct.unpack("<f", sb.read(ent + 0x90, 4))[0])
            face = abs(xr.wrap(xr.ang_of(b[0] - p[0], b[1] - p[1]) - yaw))
            if far or face > 25:
                if gap > FIGHT_REACH and not assisted:  # hold ground: he comes to attack
                    m.stick = (0.0, 0.0)
                else:
                    m.toward(b, 1.0 if far else 0.12)
                if st["a"]:
                    st["a"] = False
                    acts.append("up a")
                return acts
            m.stick = (0.0, 0.0)
            st["in_reach"] = st.get("in_reach", 0) + 1
            if k % 12 == 0 and not st["a"]:
                st["a"] = True
                st["swings"] = st.get("swings", 0) + 1
                acts.append("down a")
            elif k % 12 == 4 and st["a"]:
                st["a"] = False
                acts.append("up a")
            return acts
        while st["end"] is None and st["k"] < FIGHT_TICKS:
            piece = {"at": st["k"]}
            vals = [struct.unpack("<ii", sb.read(inv + o, 8)) for o in fuel]     # (value, cap) of each element
            piece["fuel"] = [v for v, _ in vals]
            if assisted and any(v * 4 < cap for v, cap in vals if cap > 0):
                try:                                    # first: the refill code's A and X drop the selection
                    self.s.cheat("refill")
                    piece["refill"] = True
                except xs.Teardown:   # a signal ends the chain, never a miss (AZ-701)
                    raise
                except SystemExit as e:
                    piece["refill"] = str(e)[:120]
            if not assisted:                            # the next staff whose elements have fuel (ef, af, ff, wf)
                have = dict(zip(("earth", "air", "fire", "water"), piece["fuel"]))
                n = len(FIGHT_STAFFS)
                turn = [FIGHT_STAFFS[(len(out["pieces"]) + j) % n] for j in range(n)]
                e = next((x for x in turn if all(have[y] >= 1 for y in x)), None)
                piece["selected"] = {"staff": list(e) if e else None, "ok": m.select(e) if e else None}
            piece["mask"] = m.staff_mask()
            if assisted and piece["mask"] != 15:
                piece["selected"] = m.select("elem")
            for key in ("swings", "in_reach", "min_gap"):
                st.pop(key, None)
            m.run(FIGHT_CHUNK, on_tick=fn, hook_at=xo.INPUT_BUILD)
            piece.update(boss_hp=hp_of(cr), reach=st["reach"], ticks=st["k"] - piece["at"],
                         swings=st.get("swings", 0), in_reach_ticks=st.get("in_reach", 0),
                         nearest_m=round(st["min_gap"], 1) if "min_gap" in st else None)
            out["pieces"].append(piece)
            self.log(f"fight: {piece['ticks']} ticks, his HP {piece['boss_hp']}, reach {st['reach']} m, "
                     f"mask {piece['mask']}{', refilled' if piece.get('refill') is True else ''}")
        out.update(ticks=st["k"], end=st["end"] or f"{FIGHT_TICKS} ticks ran out", boss_hp_end=hp_of(cr))
        if st["end"] != "his HP is 0":
            return {**out, "done": dead(), "why": out["end"]}
        d = self.drain(lambda c: dead(), max_ticks=300)          # the corpse's wait, then numDead
        out["dead_read"] = dead() if d["stop"] == "join" else None
        d2 = self.drain(lambda c: False, max_ticks=600) if d["stop"] == "join" else None   # into the kill's loads
        loads = d["loads"] + (d2["loads"] if d2 else [])
        out["victory_movie"] = any("spideyzardeath" in x.lower() for x in loads)
        out["drain"] = {"stop": (d2 or d)["stop"], "ticks": d["ticks"] + (d2["ticks"] if d2 else 0), "loads": loads}
        out["done"] = bool(out["dead_read"]) or out["victory_movie"]
        if not out["done"]:
            out["why"] = f"his HP is 0 but numDead didn't rise (drain {d['stop']}, loads {loads})"
        return out

    def stop_on_signal(self) -> None:
        """A SIGTERM or SIGHUP the sitting took ends the chain (its teardown runs) at the next segment or search
        even when its ``Teardown`` was raised inside a callback that swallowed it (AZ-701: r116f-s1's, in a weakref
        finaliser, which Python reports as "Exception ignored" and goes on from: the chain played segments 1 and 2
        and a second SIGTERM did nothing)."""
        if self.s.signalled is not None:
            raise xs.Teardown(f"signal {self.s.signalled}: tearing down (its Teardown was swallowed in a callback)")

    def run(self, parent: dict | None = None, missed_first: str | None = None) -> dict:
        """Every segment in order from where the sandbox stands; stops at the first that fails (chain.json says
        which and why); a skipped one (a barrier not in the way, AZ-500) is no miss but no done either: the chain
        goes on and its result names it.  ``parent``: the guest stands at a chain's start already (an ``unpark``ed
        one, halted at the update entry): the first start is taken there, linked to it.  ``missed_first``: the
        first segment is a miss an earlier run recorded (this why): it moves on from it at once
        (``on_miss="place"``).  Returns the record."""
        t0 = time.monotonic()
        i = 0
        try:
            while i < len(self.segs):
                self.stop_on_signal()
                if i == 0 and missed_first:
                    rec = {**self.segs[0], "starts": [], "attempts": [], "ok": False,
                           "why": f"missed in an earlier run: {missed_first}"}
                    self.rec["segments"].append(rec)
                else:
                    n0 = len(self.rec["segments"])
                    try:
                        rec = self.segment(i, self.segs[i], parent)
                    except Exception as e:                      # a driver error is the segment's miss, not the
                        import traceback                        # sitting's end (a relaunch can queue for hours)
                        tb = traceback.format_exc().strip().splitlines()
                        why = f"driver error: {type(e).__name__}: {str(e)[:200]} ({tb[-3].strip()[:160]})"
                        self.log(f"segment {i}: {why}")
                        if len(self.rec["segments"]) > n0:
                            rec = self.rec["segments"][-1]
                        else:
                            rec = {**self.segs[i], "starts": [], "attempts": []}
                            self.rec["segments"].append(rec)
                        rec.update(ok=False, why=why)
                self.save()
                if self.progress is not None:
                    mark(self.progress, self.rec["plan"], self.name, rec)
                if rec.get("skipped"):
                    self.rec.setdefault("skipped", []).append(i)
                if not rec["ok"] and not rec.get("skipped") and self.on_miss == "place" and i + 1 < len(self.segs):
                    try:
                        rec["moved_on"] = self.move_on(i)          # D240: the miss recorded, the chain goes on
                    except xs.Teardown:
                        raise
                    except (Exception, SystemExit) as e:           # recorded, not raised past the record (AZ-819)
                        rec["moved_on"] = {"ok": False, "why": f"driver error: {type(e).__name__}: {str(e)[:200]}"}
                    self.save()
                    if self.progress is not None:
                        mark(self.progress, self.rec["plan"], self.name, rec)
                    if rec["moved_on"]["ok"]:
                        self.rec.setdefault("missed", []).append(i)
                        parent = {"meta_sha12": None, "placed": f"after segment {i}'s miss (D240)"}
                        i += 1
                        continue
                if not rec["ok"] and not rec.get("skipped"):
                    self.rec["result"] = f"stopped at segment {i}: {rec.get('why')}"
                    break
                if (rec["attempts"] or [{}])[-1].get("next_exit_fired") and i + 1 < len(self.segs):
                    i += 1                                         # its exit fired during this segment's replay
                    self.rec["segments"].append({**self.segs[i], "ok": True, "starts": [], "attempts": [],
                                                 "taken_by": f"segment {i - 1}'s replay (its trigger fired on the way)"})
                    if self.progress is not None:
                        mark(self.progress, self.rec["plan"], self.name, self.rec["segments"][-1])
                parent = {"meta_sha12": rec["starts"][-1]["meta_sha12"], "string_sha12": rec["string_sha12"],
                          "drained": rec["drained"]}
                i += 1
            else:
                left = [f"{what}: {self.rec[k]}" for k, what in (("missed", "missed (placed past)"),
                                                                  ("skipped", "skipped (not played)"))
                        if self.rec.get(k)]
                self.rec["result"] = ("every segment replayed and reached its goal" if not left else
                                      "the end reached; " + "; ".join(left))
        finally:
            self.close_pool()
            self.rec.update(ticks=self.k, seconds=round(time.monotonic() - t0, 1), ended=xs.stamp())
            self.save()
        return self.rec


def mark(path: Path, ident: dict, chain: str, rec: dict) -> bool:
    """Step R1.16's progress file (``progress.json`` in the evidence folder: ``plan``, the plan's sha12, and
    ``sample``/``certify`` lists of segments, a sample entry with its ``tour`` (the spheres, ``"1-2-3"``), its
    ``index`` and a ``status``): the ``sample`` entry of the chain's tour (``ident``, its plan identity) with
    ``rec``'s index set from a chain's segment record (``ok`` or ``failed``, why, the chain's name, the ticks, the
    search seconds, the robustness, when), written whole by a rename.  False (nothing written) when the file is
    another plan's or holds no such entry."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not ident.get("sha256") or doc.get("plan") != ident["sha256"][:12]:
        return False
    tour = "-".join(map(str, ident.get("tour") or ()))
    entry = next((e for e in doc.get("sample", ()) if e["index"] == rec.get("index") and e.get("tour") == tour), None)
    if entry is None:
        return False
    entry.update(status="ok" if rec.get("ok") else "skipped" if rec.get("skipped") else "failed",
                 why=rec.get("why") or rec.get("taken_by") or rec.get("skipped"),
                 chain=chain, at=xs.stamp(), **{k: rec[k] for k in ("ticks", "search_s", "robustness", "act_ticks")
                                             if rec.get(k) is not None})
    if rec.get("input"):
        entry["input"] = rec["input"]
    if rec.get("moved_on"):
        mo = rec["moved_on"]
        entry["moved_on"] = (f"[placed] {mo.get('placed') or 'from where it stood'}" if mo.get("ok")
                             else f"not moved on: {mo.get('why')}")
    doc["updated"] = xs.stamp()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)
    return True


def park_check(s, tag: str = "vanilla-beach-shield5", string=BEACH) -> dict:
    """The parked-start measurement (Step X.12, tooling.txt §3.5): at a fresh L3 snapshot's start, ``park``; replay a
    known string held (the control); ``unpark`` in the same xemu, snapshot again in place and replay; quit xemu,
    relaunch on the same W, ``unpark``, snapshot and replay.  Each restored start is compared with the original:
    every user page (the snapshot's sha12 over 21 MB), the registers, the start hash (entity and body) and the
    entity's neighbourhood (its page and the two each side); each replay with L3's rows.  Hashes and counts only."""
    sb = s.sb
    s.loadvm(tag)
    lab = f"x12-park-{time.strftime('%H%M%S')}"

    def snap(suffix: str, here: bool) -> dict:
        info = sb.snapshot(f"{lab}-{suffix}", here=here)
        s.snapshots.append(Path(info["path"]))
        sn = l3.read_snapshot(Path(info["path"]))
        ent, near = sn.meta["entity"], b""
        for va in range((ent & ~0xFFF) - 0x2000, (ent & ~0xFFF) + 0x3000, 0x1000):
            try:
                near += sb.read(va, 0x1000)
            except OSError:
                near += b"-"
        return {"sha12": info["sha12"], "pages": info["pages"], "regs": sn.regs, "meta": sn.meta,
                "near12": hashlib.sha256(near).hexdigest()[:12], "seconds": info["seconds"]}

    a = snap("a", False)
    pads = l3.pads(string)
    snap_a = l3.read_snapshot(l3.snapshot_path(f"{lab}-a"))
    rows = l3.L3(snap_a, sb._xbe("dvd.iso")).run(pads)
    out = {"tag": tag, "pages": a["pages"], "ticks": len(rows)}
    p = sb.park(f"p-{lab}")
    out["park"] = {k: p[k] for k in ("savevm_s", "status")}

    def same(b: dict) -> dict:
        return {"pages_equal": b["sha12"] == a["sha12"], "regs_equal": b["regs"] == a["regs"],
                "start_equal": b["meta"]["start_sha12"] == a["meta"]["start_sha12"]
                and b["meta"]["clock"] == a["meta"]["clock"], "near_equal": b["near12"] == a["near12"],
                "snapshot_s": b["seconds"]}

    def replay() -> dict:
        t0 = time.monotonic()
        got = sb.replay(pads, rows, a["meta"])
        corpus.record(snap_a.meta, False, pads, rows, got, disc=sb.disc_source("dvd.iso"))
        c = xo.l3_compare(rows, got)
        return {**{k: c[k] for k in ("ticks", "l3_ticks", "max_err_m", "states_differ", "hp_differ",
                                     "fields_differ")}, "xemu_s": round(time.monotonic() - t0, 1)}

    out["after_park"] = same(snap("a2", True))
    out["held"] = replay()
    u = sb.unpark(p["tag"], a["meta"])
    out["unpark_same_xemu"] = {**{k: u[k] for k in ("loadvm_s", "at_start", "status")}, **same(snap("b", True)),
                               "replay": replay()}
    sb._quit()
    t0 = time.monotonic()
    sb.relaunch()
    rel = round(time.monotonic() - t0, 1)
    u = sb.unpark(p["tag"], a["meta"])
    out["unpark_relaunched"] = {"relaunch_s": rel, **{k: u[k] for k in ("loadvm_s", "ready_s", "at_start", "status")},
                                **same(snap("c", True)), "replay": replay()}
    ok = all(v.get(k, True) for v in (out["after_park"], out["unpark_same_xemu"], out["unpark_relaunched"])
             for k in ("pages_equal", "regs_equal", "start_equal", "near_equal", "at_start"))
    ok = ok and all(r["max_err_m"] == 0.0 and r["ticks"] == r["l3_ticks"] and not r["states_differ"]
                    and not r["hp_differ"] for r in (out["held"], out["unpark_same_xemu"]["replay"],
                                                    out["unpark_relaunched"]["replay"]))
    out["bit_identical"] = ok
    s.result({"case": "park-check", **out})
    return out


def first_start(seg: dict) -> dict | None:
    """A segment record's first parked start: its own, or for an action (whose starts are its stations' approaches')
    the first station's approach's, so a failed barrier or button resumes at the walk up to it.  A start that isn't
    parked is passed over: an action's own start can be the link after the action before it, with no tag (sitting
    r125-full-h, segment 34: death_keylock2's own start, its parked one its approach's)."""
    if own := [st for st in seg.get("starts") or () if st.get("parked")]:
        return own[0]
    return next((s for st in seg.get("stations", ()) for s in (st.get("approach") or {}).get("starts") or ()
                 if s.get("parked")), None)


def resume(a, segs: list[dict], ident: dict, hints: dict | None, sitting=None) -> int:
    """``run --resume CHAIN_JSON`` (Step R1.16): a chain a ``--keep`` run left goes on from its first segment that
    isn't ok, at that segment's first start, parked in the private store's ``parked/<W name>`` (its drive, its
    discs; ``Sandbox.adopt_parked``) and brought back halted (``unpark``, checked against the kept L3 snapshot's
    start); the segments from that one on, the first start linked to the parked one.  The plan must be the
    record's.  ``sitting``: a running one (an exec server's, ``main(argv, sitting)``) whose sandbox was started on a
    later run's parked drive (``AZURIK_XEMU_HDD``), which holds this start's tag too, as each run's drive is a clone
    of the one it resumed from: no new slot."""
    prev = json.loads(a.resume.read_text(encoding="utf-8"))
    if prev["plan"].get("sha256") != ident["sha256"] or prev["plan"].get("tour") != ident.get("tour"):
        raise SystemExit(f"{a.resume.name}: another plan or tour than this run's")
    if a.resume_at is not None:                          # a segment again (a miss the run moved on from)
        seg = next((sg for sg in prev["segments"] if sg.get("index") == a.resume_at), None)
    else:
        seg = next((sg for sg in prev["segments"] if not sg.get("ok") and not sg.get("skipped")
                    and not (sg.get("moved_on") or {}).get("ok")),
                   None)                                 # a miss the run moved on from (D240) stays behind
    if seg is not None and getattr(a, "start_of", None) is not None:   # a later segment's start in the same node
        at = next((sg for sg in prev["segments"] if sg.get("index") == a.start_of), None)
        if at is None or (at["level"], at["from"]) != (seg["level"], seg["from"]):
            raise SystemExit(f"--start-of {a.start_of}: not a segment of {a.resume.name} from {seg['from']}")
        st0 = first_start(at)
    else:
        st0 = first_start(seg) if seg is not None else None
    if st0 is None or not st0.get("parked"):
        raise SystemExit(f"{a.resume.name}: no segment left with a parked start")
    folder = l3.store() / "parked" / prev["build"]["w"]
    if sitting is not None:                              # the running sandbox's own drive holds the tag
        folder = Path(sitting.sb.hdd).parent
    meta = l3.read_meta(l3.snapshot_path(st0["label"]))
    segs = [sg for sg in segs if sg["index"] >= seg["index"]]
    ident["first"], ident["resumed"] = seg["index"], a.resume.name
    with contextlib.nullcontext(sitting) if sitting is not None else \
            xs.Sitting(a.name, step="R1.16", ev=a.ev, keep=a.keep, hdd=folder / "xbox_hdd.qcow2") as s:
        s.sb.adopt_parked(folder)
        if st0["parked"] not in s.sb.st["parked"]:
            raise SystemExit(f"{st0['parked']}: not a start parked on {folder.name}'s drive")
        s.sb.st["build"] = s.sb.st["parked"][st0["parked"]]["disc"]
        u = s.sb.unpark(st0["parked"], meta)
        if not u.get("at_start"):
            raise SystemExit(f"{st0['parked']}: unpark didn't bring back {st0['label']}'s start")
        s.result({"case": "chain-resume", "from": a.resume.name, "segment": seg["index"], "parked": st0["parked"],
                  **{k: u.get(k) for k in ("how", "loadvm_s", "at_start")}})
        ch = Chain(s, segs, out=s.ev / "results" / f"chain-{xs.slug(a.name)}.json", name=a.name, ident=ident,
                   park=not a.no_park, release={"no": False, "yes": True, "waiting": "waiting"}[a.release],
                   jobs=a.jobs, steps=a.steps, scene={"yes": True, "no": False, "diverged": "diverged"}[a.scene],
                   robust=a.robust, hints=hints, progress=a.progress, repairs=a.repairs, seg_cap=a.seg_cap,
                   pilot=a.pilot, on_miss=a.on_miss, assisted=not a.unassisted, plateau=a.plateau, l3=a.l3)
        rec = ch.run(parent={"meta_sha12": st0["meta_sha12"], "resumed": f"{a.resume.name} {st0['parked']}"},
                     missed_first=seg.get("why") if a.resume_missed else None)
    print(rec["result"])
    return 0 if rec["result"].startswith("every") else 1


def main(argv=None, sitting=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("segments", "run"):
        p = sub.add_parser(name)
        p.add_argument("--plan", type=Path, help="a plan file (default: the golden seed's under the defaults)")
        if name == "run":
            p.add_argument("build", type=Path, help="the built ISO the plan made (azurkit build --seed: its seed)")
            p.add_argument("--tag", default="vanilla-ig-new", help="the save menu state the build boots from (boot_start)")
            p.add_argument("--save", type=int, default=2,
                           help="the save it loads (vanilla-ig-new's 2, the default: the D98 drive's new-game "
                                "character; vanilla-ig-w1's 1: the all-powers one)")
            p.add_argument("--hop", nargs=2, metavar=("LEVEL", "SPOT"), help="an R7 hop after the boot (placed)")
            p.add_argument("--first", type=int, default=0, help="the first segment to play")
            p.add_argument("--no-park", action="store_true", help="hold the sandbox at each start (no savevm)")
            p.add_argument("--release", choices=("no", "yes", "waiting"), default="no",
                           help="quit xemu during each search (yes), only while a sitting waits (waiting), or never "
                                "(the default: a long chain holds its sandbox)")
            p.add_argument("--robust", type=int, default=len(ROBUST),
                           help="re-searches for a winner whose tier is harder than the plan's (0: none)")
            p.add_argument("--jobs", type=int, help="L3 pool workers (default: the cores, at most 16)")
            p.add_argument("--steps", type=int, default=200_000, help="each seed's step budget (the ladder's first rung)")
            p.add_argument("--repairs", type=int, default=2, help="failed replays a segment may re-anchor after")
            p.add_argument("--scene", choices=("yes", "no", "diverged"), default="diverged",
                           help="whole steps for every segment, never, or once a replay diverged (default)")
            p.add_argument("--name", default="x12-chain")
            p.add_argument("--ev", type=Path)
            p.add_argument("--keep", action="store_true", help="keep the snapshots and W")
            p.add_argument("--hints", type=Path, help="a JSON file {segment index: [seed strings]} (segs_of's form)")
            p.add_argument("--progress", type=Path, help="R1.16's progress.json: its sample entries are updated")
            p.add_argument("--resume", type=Path, help="a chain.json a --keep run left: go on from its first segment "
                                                       "not ok, at that segment's parked start (no boot)")
            p.add_argument("--resume-at", type=int, help="with --resume: this segment (its index) instead of the first "
                                                         "not ok")
            p.add_argument("--resume-missed", action="store_true",
                           help="with --resume and --on-miss place: the segment it resumes at is the earlier run's "
                                "miss: move on from it at once (no search again)")
            p.add_argument("--start-of", type=int,
                           help="with --resume-at: start at this later segment's parked start, which stands in the "
                                "same node (d1's seal from the chromatic gate walk's start in d1_core)")
            p.add_argument("--last", type=int, help="the last segment to play (its index)")
            p.add_argument("--seg-cap", type=float, help="each segment's search seconds, all rungs and re-anchors "
                                                         "together (D240: about 600); then the miss")
            p.add_argument("--pilot", action="store_true",
                           help="the route pilot (closed loop, real pad) first on a hop that rides a rig, and after "
                                "a search or replay miss")
            p.add_argument("--on-miss", choices=("stop", "place"), default="stop",
                           help="after a missed segment stop (the default), or record it and place the player at "
                                "the next segment's start (D240: [placed])")
            p.add_argument("--plateau", type=int, metavar="N",
                           help="end a search's seed once its best cost to go hasn't fallen by 0.1 s in N steps "
                                "on every rung (l3_search's Limits.plateau; N over SCENE_COST in whole steps), the 4x "
                                "rung passed over when every seed ended at its plateau; default off: every seed runs "
                                "to its budget or cap)")
            p.add_argument("--l3", choices=("fast", "base"), default=L3_DEFAULT,
                           help="the searches' simulator: FastL3 (fast, on the patched libunicorn when built; its "
                                "records are base L3's) or round 1's L3 on the stock wheel (base)")
            p.add_argument("--unassisted", action="store_true",
                           help="a boss fight enters no cheat: the kit's own HP and fuel, holding ground (AZ-499)")
            p.add_argument("--segments", type=Path,
                           help="the segments as `segments` printed them (the plan's identity line, then one per "
                                "line): a plan this checkout's database refuses, its segments made by the code that "
                                "made it (the frozen plans, Step R1.25)")
        p.add_argument("--sphere", type=int, default=1)
        p.add_argument("--item", type=int, default=0)
        p.add_argument("--back", action="store_true", help="the return path too")
        p.add_argument("--tour", type=int, nargs="+", metavar="SPHERE",
                       help="the tour of these spheres from the start, item to item (back to the start with --back)")
        p.add_argument("--start", help="the tour's first node (default: the world's start)")
        p.add_argument("--victory", action="store_true", help="the tour ends at the victory flag's event")
        p.add_argument("--no-counted", action="store_true", help="the tour's progression items alone (no obsidians)")
        p.add_argument("--no-merge", action="store_true", help="keep each walk its own segment")
    sub.add_parser("park-check").add_argument("--ev", type=Path)
    a = ap.parse_args(argv)
    opts = {"merge": not a.no_merge, "counted": not a.no_counted, "victory": a.victory, "start": a.start} \
        if a.cmd != "park-check" else {}
    if a.cmd == "segments":
        segs, ident = plan_segments(a.plan, a.sphere, a.item, a.back, a.tour, **opts)
        print(json.dumps(ident))
        for sg in segs:
            print(json.dumps(sg))
        return 0
    if a.cmd == "park-check":
        with xs.Sitting("x12-park", step="X.12", ev=a.ev) as s:
            print(json.dumps(park_check(s), default=str))
        return 0
    segs, ident = read_segments(a.segments) if a.segments else plan_segments(a.plan, a.sphere, a.item, a.back,
                                                                             a.tour, **opts)
    if a.last is not None:
        segs = [sg for sg in segs if sg["index"] <= a.last]
    hints = json.loads(a.hints.read_text(encoding="utf-8")) if a.hints else None
    if a.resume:
        return resume(a, segs, ident, hints, sitting)
    with xs.Sitting(a.name, step="R1.16", ev=a.ev, keep=a.keep) as s:
        segs, ident["first"] = segs[a.first:], a.first
        s.result({"case": "chain-start", **boot_start(s, a.build, segs[0]["kit"], a.tag, save=a.save,
                                                       level=None if a.hop else segs[0]["level"],
                                                       discs=ident.get("discs"),
                                                       keys=ident.get("keys"))})
        if a.hop:
            if not (h := s.hop(*a.hop))["ok"]:
                raise SystemExit(f"the hop to {a.hop} didn't settle")
            s.result({"case": "chain-hop", **h})
        ch = Chain(s, segs, out=s.ev / "results" / f"chain-{xs.slug(a.name)}.json", name=a.name, ident=ident,
                   park=not a.no_park, release={"no": False, "yes": True, "waiting": "waiting"}[a.release],
                   jobs=a.jobs, steps=a.steps, scene={"yes": True, "no": False, "diverged": "diverged"}[a.scene],
                   robust=a.robust, hints=hints, progress=a.progress, repairs=a.repairs, seg_cap=a.seg_cap,
                   pilot=a.pilot, on_miss=a.on_miss, assisted=not a.unassisted, plateau=a.plateau, l3=a.l3)
        rec = ch.run()
    print(rec["result"])
    return 0 if rec["result"].startswith("every") else 1


if __name__ == "__main__":
    sys.exit(main())
