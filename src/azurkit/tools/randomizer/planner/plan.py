"""The plan file and the minimal spoiler (RANDOMIZER_PLAN §3.5, §3.6;
Step R1.9).

A plan file is one JSON object (sorted keys, one-space indentation, a
trailing newline):

- ``format`` (``azurik-rando-plan/1``) and ``generator`` (the fill's
  version, :data:`~.fill.GENERATOR`);
- ``seed`` (the user's string) and ``attempt`` (the first that passed);
- ``settings`` (D144's options, as a settings file holds them), ``share``
  (their share string, with any movement sliders) and ``settings_digest``
  (of the settings it was filled at: under moved movement sliders, their
  tier's, :mod:`~..movement`);
- ``db_digest`` (:func:`~.fill.db_digest`);
- ``placement``: every authored level's pool location id -> the
  ``items.toml`` name it holds (the writer's input, Step R1.10);
- ``sha256``: of the canonical JSON of all the rest.

:func:`load_plan` refuses another format or generator, a wrong sha256 and
a plan made from another database (a different ``db_digest``). The
spoiler (plan §3.6, RANDOMIZER_DB §7.4; Steps R1.9, R1.12) is a pure
function of the plan and the database: the settings with the share string
and the skip registry tag, the skips on by trick family (a batch once,
with its variants' kits on, D275), D82's statement,
the spheres (the solver's rounds on the whole placement) with an obtain
path from the start and a return path back for each progression item,
then the traps, the ``assumes`` edges, the forfeitable locations, the
traps after completion, the region gates, the dangerous saves and the
excluded locations.
"""

from __future__ import annotations

import collections
import hashlib
import heapq
import json
import math
import re
from collections.abc import Container, Iterable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from azurkit.tools.randomizer.movement import PROMISE, played, said, sliders_text
from azurkit.tools.randomizer.planner import difficulty
from azurkit.tools.randomizer.planner.fill import (
    GENERATOR,
    Fill,
    canonical,
    db_digest,
    excluded_locations,
    known_traps,
    settings_digest,
    settings_table,
)
from azurkit.tools.randomizer.planner.grammar import DISCS, atoms, parse
from azurkit.tools.randomizer.planner.settings import (
    CATEGORIES,
    SEED_DIFFICULTY_FILL,
    Settings,
    SettingsError,
    picks,
    picks_on,
    registry_tag,
    settings_from_table,
    share_encode,
    share_sliders,
)
from azurkit.tools.randomizer.planner.solver import Logic, Reach, _Round, _Rules

PLAN_FORMAT = "azurik-rando-plan/1"
_KEYS = {"format", "generator", "seed", "attempt", "settings", "share", "settings_digest", "db_digest", "placement",
         "sha256"}


class PlanError(ValueError):
    """A plan file this database can't use, or an unbeatable plan."""


def plan_doc(result: Fill, db, asked: Settings | None = None) -> dict:
    """The plan file's object for a fill on ``db``: its settings and share
    string ``asked``'s, the settings a fill under moved movement sliders was
    asked for (``movement.played``: it fills at their tier), else the
    fill's; its ``settings_digest`` the fill's own, which seeded it."""
    st = asked or result.settings
    doc = {"format": PLAN_FORMAT, "generator": GENERATOR, "seed": result.seed, "attempt": result.attempt,
           "settings": settings_table(st), "share": share_encode(st, {sid: s for sid, (_, s) in db.skips.items()}),
           "settings_digest": settings_digest(result.settings), "db_digest": db_digest(db),
           "placement": dict(sorted(result.placement.items()))}
    return {**doc, "sha256": hashlib.sha256(canonical(doc)).hexdigest()}


def dumps(doc: Mapping) -> str:
    return json.dumps(doc, indent=1, sort_keys=True) + "\n"


@dataclass(frozen=True)
class Plan:
    """A plan file read back: ``settings``, what its fill and logic read
    (``movement.played`` of ``asked``, the settings its file and share
    string hold, their movement sliders too)."""
    doc: dict
    settings: Settings
    placement: dict[str, str]
    asked: Settings


def load_plan(source: Path | str | Mapping, db) -> Plan:
    """A plan file (a path, or its parsed object) checked against ``db``."""
    doc = dict(source) if isinstance(source, Mapping) else json.loads(Path(source).read_text(encoding="utf-8"))
    if set(doc) != _KEYS:
        raise PlanError(f"not a plan file: keys {sorted(set(doc) ^ _KEYS)} differ from {PLAN_FORMAT}'s")
    if not (isinstance(doc["share"], str) and isinstance(doc["db_digest"], str) and isinstance(doc["settings"], Mapping)
            and isinstance(doc["placement"], Mapping)
            and all(isinstance(k, str) and isinstance(v, str) for k, v in doc["placement"].items())):
        raise PlanError("not a plan file: its share and db_digest are strings, its settings a table "
                        "and its placement maps location ids to items")
    for key, want in (("format", PLAN_FORMAT), ("generator", GENERATOR)):
        if doc[key] != want:
            raise PlanError(f"{key} {doc[key]!r}: this tool reads {want!r}")
    body = {k: v for k, v in doc.items() if k != "sha256"}
    if hashlib.sha256(canonical(body)).hexdigest() != doc["sha256"]:
        raise PlanError("its sha256 doesn't match its content (an edited plan)")
    if doc["db_digest"] != db_digest(db):
        raise PlanError(f"made from another database (db_digest {doc['db_digest'][:12]}, this one's "
                        f"{db_digest(db)[:12]}): replay is refused (plan §3.5)")
    skips = {sid: s for sid, (_, s) in db.skips.items()}
    table = dict(doc["settings"])
    made = table.pop("seed_difficulty_fill", None)
    if table.get("seed_difficulty") and made != SEED_DIFFICULTY_FILL:
        raise PlanError(f"made with Seed difficulty's fill {made}; this AzurKit plans with fill "
                        f"{SEED_DIFFICULTY_FILL}: the same seed would place items differently")
    try:     # the movement sliders it was asked under ride in its share string (AZ-383)
        asked = replace(settings_from_table(table, skips, "plan settings"), sliders=share_sliders(doc["share"], skips))
    except SettingsError as exc:
        raise PlanError(str(exc)) from exc
    return Plan(doc, played(asked), dict(doc["placement"]), asked)


@dataclass(frozen=True)
class Step:
    """A progression item: where it is, its node, and the node paths there
    from the start and back (``" (disc teleport)"`` marks a hop that only
    the one-shot teleport makes). ``picks_up``: the way back needs what
    the solver's escape picks up on it (plan §2.13 rule 2)."""
    location: str
    item: str
    node: str
    obtain: tuple[str, ...]
    back: tuple[str, ...]
    picks_up: bool


@dataclass(frozen=True)
class SpoilerSphere:
    number: int
    steps: tuple[Step, ...]
    counted: dict[str, int]         # e.g. {"obsidian": 5}
    victory: bool                   # victory holds with what the spheres before it collected
    traps: frozenset[str] = frozenset()        # the traps at its state (canonical nodes)
    free_traps: frozenset[str] = frozenset()   # those a player gets into with no skip
    counters: Mapping[str, int] = None         # the counters at its state
    flags: frozenset[str] = frozenset()        # the flags credited at its state
    locations: tuple[str, ...] = ()            # every location it collects


def _path(logic: Logic, rules: _Rules, src: str, dst: str, counters: Mapping, flags, slots_used,
          avoid: Container[tuple[str, str]] = (), extra: Mapping[str, Iterable[str]] | None = None) -> tuple[str, ...]:
    """The fewest-hop node path from ``src`` to ``dst`` over the edges in
    logic passable with ``counters`` and ``flags``, a disc teleport taken
    while its slot isn't collected; empty when there is none.  A tour's
    (Step R1.16d): no hop ``(u, v)`` in ``avoid`` (a one-shot exit it has
    taken), and the hops ``extra`` maps each node to (rides the logic
    leaves out) as well."""
    parent = {src: None}
    todo = collections.deque([src])
    while todo and dst not in parent:
        u = todo.popleft()
        hops = [(v, v) for v, rule in rules.adj.get(u, ()) if (u, v) not in avoid and rule(counters, flags)]
        hops += [(v, v) for v in (extra or {}).get(u, ())]
        hops += [(b, f"{b} (disc teleport)") for a, b, rule, disc in rules.teleports
                 if a == u and logic.slots[disc] not in slots_used and rule(counters, flags)]
        for v, label in hops:
            if v not in parent:
                parent[v] = (u, label)
                todo.append(v)
    if dst not in parent:
        return ()
    out, v = [], dst
    while parent[v] is not None:
        u, label = parent[v]
        out.append(label)
        v = u
    return (src, *reversed(out))


def spheres(plan: Plan, logic: Logic) -> list[SpoilerSphere]:
    """The plan's spheres (plan §3.6): the solver's rounds on the whole
    placement, each with what it collects (a stub's items come free,
    §4.1). An item's obtain path is read with the state its round starts
    from, its return path with that and the item; when that finds none,
    the round's escape from the item's node (which picks up what it passes,
    plan §2.13 rule 2) gives the state. Raises :class:`PlanError` if
    victory never holds."""
    return _playthrough(plan, logic)[1]


ELEMENT_COUNTERS = ("earth", "air", "fire", "water")

# -- the chain driver's segments (D172; Steps X.12, X.19; R1.16's input) ----------------------------------------------
RIDE_FALL = 600      # ticks a ride's search lets a branch stay in the air (w1's spout lifts the body ~150, X.15)
SCENE_KINDS = frozenset({"rig", "teleport"})    # derived edges a mover or the wiring makes: whole steps (scene-side)
# The minigames scripts/xemu_minigames.py's solvers play (Steps R1.8f, R1.8h, R1.8o): a level-file event -> (the solver,
# the object the player walks up to first; None: the event's node)
MINIGAMES = {"w2.hose.won": ("hose", "LightShape"), "w1.torpedo_tower.toppled": ("torpedo", "pCubeShape7"),
             "e6.tree_song.played": ("song", None), "life.filament_cores.won": ("cores", None)}
CASTS = {"W": "water", "F": "fire", "E": "earth", "A": "air"}     # a barrier's generated elements -> the staff's
# The rides a tour takes where the logic has no way (Step R1.16d, AZ-477; play only, never the solver's): (from, to) ->
# the rig.  d1's central elevator from floor 7 back to floor 1 (RE_DATA §8; X34-INTAKE's RP-F: red's program on floor
# 1, the deck's red button), once the bridge-end cutscene into d2, the way back the logic takes, fired its one shot.
RIDES = {("d1_z079", "d1_floor1"): "d1.elevator"}
# The level-file nodes a rig stops at, by floor (Step R1.16d): d1's central elevator (RE_DATA §8; floors 6 and 8 by
# X34-INTAKE §1: green to 6 lands by d1.Z121, red to 8 by d1.Z018).  A hop between two of its floors is a ride
# (``rig``): ``scripts/xemu_chain.py`` presses the floor switches and rides the colours its wiring gives, and
# ``merge_walks`` joins a run of them into one ride, never with a walk.
ELEVATORS = {"d1.elevator": {"d1_floor1": 1, "d1_z002": 2, "d1_z004": 3, "d1_z003": 4, "d1_z081": 5, "d1_z121": 6,
                             "d1_z079": 7, "d1_z018": 8, "d1_floor9": 9, "d1_z000": 10, "d1_floor11": 11}}
_SWITCHED_OFF = re.compile(r"switch\[[^\]]+\]\{off=")     # a gate's switch only turned off: nothing turns it on again


def rig_of(u: str, v: str) -> str | None:
    """The rig (:data:`ELEVATORS`) a hop ``u > v`` rides: one that stops at both, on two floors; None for none."""
    return next((r for r, fl in ELEVATORS.items() if u in fl and v in fl and fl[u] != fl[v]), None)


def one_shot(exit_: Mapping) -> bool:
    """Whether a generated exit fires once: its gate holds a switch that only turns off (``switch[T]{off=...}``,
    no ``on=``; d1's ``D2_movie_levelSwitch``: ``DeathMovie_disable_toggle``, turned off by the exit's own touch and
    kept by the save [verified data])."""
    return bool(_SWITCHED_OFF.search(exit_.get("gate_hint") or ""))


def _kit(counters: Mapping) -> dict:
    return {e: n for e, n in counters.items() if e in ELEMENT_COUNTERS and n}


class _Chain:
    """What a plan's segments are read from: the rules, the generated exits, and per level the derived zone graph
    (cached), for the hints (:meth:`hints`) and the hops (:meth:`hop`)."""

    def __init__(self, plan: Plan, logic: Logic):
        self.plan, self.logic, self.db = plan, logic, logic.db
        self.rules = logic.rules(plan.settings)
        self.exits = {x["id"]: x for doc in self.db.generated.values() for x in doc.get("exits", [])}
        self._graphs: dict[str, tuple] = {}
        self._exprs: dict[str, object] = {}
        self._edges: dict[tuple, list] | None = None     # (from, to) -> [(level, edge, rule)], compiled once

    def zones(self, node: str) -> set[str]:
        return {a[5:] for a in self.db.nodes[node][1].get("anchors", []) if a.startswith("zone:")}

    def graph(self, lvl: str) -> tuple[dict, set, dict, dict]:
        """(zone -> its derived edges, the zones a node anchors, push volume -> switched, push volume -> the zones
        its touch is set at) of ``lvl``."""
        if lvl not in self._graphs:
            d = self.db.derived.get(lvl, {})
            adj = collections.defaultdict(list)
            for e in d.get("edges", ()):
                adj[e["from"]].append(e)
            kept = {z for n, (lv, _) in self.db.nodes.items() if lv == lvl for z in self.zones(n)}
            mech = d.get("mechanisms", {})
            vols = {v["name"]: bool(v.get("switched")) for k in ("updrafts", "currents") for v in mech.get(k, ())}
            touch = {e["platform"]: set(e.get("set_at", ())) for e in d.get("events", ())
                     if e.get("kind") == "touch" and e.get("platform") in vols}
            self._graphs[lvl] = (adj, kept, vols, touch)
        return self._graphs[lvl]

    def holds(self, text: str, counters: Mapping, flags) -> bool:
        if text not in self._exprs:
            try:
                self._exprs[text] = self.rules.expr(text)
            except ValueError:
                self._exprs[text] = lambda c, f: False
        return self._exprs[text](counters, flags)

    def derived_path(self, lvl: str, src: set, dst: set, counters: Mapping, flags,
                     inner: set | None = None) -> list[dict] | None:
        """The derived edges of the cheapest zone path from ``src`` to ``dst`` whose requirements hold (an edge out
        of logic, a probe's, costs 1000 hops), through no zone another node anchors (but ``inner``, by default
        ``src``): what the level-file edge was contracted from (``draft.author.contract``); None when there is none
        (a hand edge)."""
        adj, kept, _, _ = self.graph(lvl)
        inner = src if inner is None else inner
        dist, prev = {z: 0 for z in src}, {}
        heap = [(0, z) for z in sorted(src)]
        while heap:
            d, u = heapq.heappop(heap)
            if d > dist[u]:
                continue
            if u in dst:
                out = []
                while u in prev:
                    out.append(prev[u])
                    u = prev[u]["from"]
                return out[::-1]
            if u in kept and u not in inner:
                continue
            for e in adj.get(u, ()):
                w = d + 1 + 1000 * (e.get("logic") is False)
                if w < dist.get(e["to"], math.inf) and self.holds(e.get("requires", "true"), counters, flags):
                    dist[e["to"]], prev[e["to"]] = w, e
                    heapq.heappush(heap, (w, e["to"]))
        return None

    def hints(self, seg: dict, counters: Mapping, flags) -> dict:
        """The search's hints for a hop (the rules: docs/SIMULATOR.md § "Chains"): ``mech`` (what the hop passes),
        ``scene`` (whole steps: a mover, a teleporter's wiring, a timed volume, a cart), ``fall`` (a ride's ticks in
        the air), ``seeds`` (a ride's foot to walk onto, a proof's string)."""
        lvl, kind = seg["level"], seg["kind"]
        adj, kept, vols, touch = self.graph(lvl)
        src = self.zones(seg["from"])
        if kind in ("exit", "cart", "teleport"):
            dst = {z["id"] for z in self.db.derived.get(lvl, {}).get("zones", ())
                   if seg["goal"] in z.get("anchors", {}).get("exit", ())}
        else:
            dst = self.zones(seg["to"]) if seg["to"] in self.db.nodes else set()
        mech, seeds, scene, fall = set(), [], kind in ("cart", "teleport"), None
        if kind in ("cart", "teleport"):
            mech.add(kind)
        if kind == "cart":
            fall = RIDE_FALL
        path = self.derived_path(lvl, src, dst, counters, flags) if dst else None
        if path is None:
            if kind != "pickup":
                mech.add("hand")
            rides = sorted(v for v, at in touch.items() if at & src)   # a ride from the from-node: a touched volume
            for v in rides:
                mech.add("ride")
                seeds.append({"ride": v, "every": 8})
                scene, fall = scene or vols[v], RIDE_FALL
        else:
            # the hop starts in whichever of the from-node's zones the last segment ended in, so each one's own way
            # counts: a teleporter joining two of them asks whole steps (w1_cove: the field from Z009 up to Z120)
            for z in sorted(src) if len(src) > 1 else ():
                path = path + (self.derived_path(lvl, {z}, dst, counters, flags, inner=src) or [])
            for e in path:
                mech.add(e["kind"])
                if e["kind"] in SCENE_KINDS or vols.get(e.get("via")):
                    scene = True
                if e["kind"] == "push" and e.get("via") in vols:
                    fall = RIDE_FALL
        dz = self.zones(seg["to"]) if seg["to"] in self.db.nodes else dst
        seeds += [{"proof": ref} for ref, p in sorted(self.db.proofs.items())
                  if p["claim"].get("kind") == "edge" and p["claim"].get("level") == lvl
                  and p["claim"].get("from") in src and p["claim"].get("to") in dz]
        return {"mech": sorted(mech), "scene": scene, **({"fall": fall} if fall else {}),
                **({"seeds": seeds} if seeds else {})}

    def _compile(self) -> None:
        self._edges = collections.defaultdict(list)
        for lvl in sorted(self.db.levels):
            for e in self.db.levels[lvl]["edge"]:
                if edge := self.rules.edge(lvl, e):
                    self._edges[edge[:2]].append((lvl, e, edge[2]))

    def edge(self, u: str, v: str, counters: Mapping, flags, escape: bool = False) -> tuple[str, dict]:
        if self._edges is None:
            self._compile()
        found = [(lvl, e) for lvl, e, rule in self._edges.get((u, v), ()) if escape or rule(counters, flags)]
        if not found:
            raise PlanError(f"no edge {u} > {v} holds at that state")
        # a skip last (AZ-789): the solver's way out of a node a skip gets into is by the flags its no-skip ways in set
        # (forced on entry), which a tour plays only on such a way (w3's ice climb to frag_fire_1 and back by the frost)
        return min(found, key=lambda le: ((t := le[1].get("requires", "true")) != "true", "skip:" in t))

    def hop(self, u: str, v: str, counters: Mapping, flags, escape: bool = False) -> tuple[dict, dict]:
        """One hop as (a segment, its level-file edge): the edge the logic takes (the first whose rule holds,
        ``requires = "true"`` first, one with a skip last; ``escape``: by the options alone), its exit's id and
        destination, its ``difficulty`` (the edge's movement tier as a number, 1 safe .. 4 frame_perfect: above 1 the
        hop is in logic only by the plan's tier) and its hints."""
        u, kit, logic = u.split()[0], _kit(counters), self.logic
        if v.endswith(" (disc teleport)"):
            v = v.split()[0]
            e = next((e for lvl in sorted(self.db.levels) for e in self.db.levels[lvl]["edge"]
                      if e.get("disc") and e.get("exit") and logic.canon(e["from"] or lvl) == u
                      and logic.canon(e["to"]) == v), {})
            seg = {"kind": "teleport", "level": self.db.nodes[u][0], "from": u, "to": v, "goal": e.get("exit") or v,
                   "requires": e.get("requires"), "confidence": e.get("confidence"), "kit": kit}
        else:
            lvl, e = self.edge(u, v, counters, flags, escape)
            seg = {"kind": e["kind"], "level": lvl, "from": u, "to": v, "goal": e.get("exit") or v,
                   "requires": e.get("requires", "true"), "confidence": e.get("confidence"), "kit": kit,
                   "difficulty": e.get("difficulty", 1)}
        if e.get("exit") in self.exits:
            seg["dest"] = self.exits[e["exit"]]["dest"]
            if self.exits[e["exit"]].get("movie"):
                seg["movie"] = True
        if seg["kind"] == "walk" and (rig := rig_of(u, v)) is not None:
            seg["rig"] = rig                     # d1's elevator between two of its floors (Step R1.16d)
        return seg | self.hints(seg, counters, flags), e

    def spends(self, u: str, v: str) -> bool:
        """Whether every level-file edge ``u > v`` leaves by a one-shot exit (:func:`one_shot`): taken once, the hop
        is gone for the rest of a tour."""
        if self._edges is None:
            self._compile()
        es = [e for _, e, _ in self._edges.get((u, v), ())]
        return bool(es) and all(e.get("exit") in self.exits and one_shot(self.exits[e["exit"]]) for e in es)

    def ride(self, u: str, v: str, counters: Mapping) -> dict:
        """A ride the logic leaves out (:data:`RIDES`) as a segment: ``kind = "ride"``, its ``rig``."""
        return {"kind": "ride", "level": self.db.nodes[u][0], "from": u, "to": v, "goal": v, "rig": RIDES[(u, v)],
                "requires": None, "confidence": "play", "kit": _kit(counters), "mech": ["rig"], "scene": True}

    def minigame(self, loc: str) -> str | None:
        """The minigame event (:data:`MINIGAMES`) a location's requirement names, or None (the w2 hose's
        ``w2.hose.won`` before power_water's spot, Step R1.8o)."""
        text = self.logic.location_rows.get(loc, {}).get("requires") or "true"
        return next((a[1] for a in atoms(parse(text)) if a[0] == "event" and a[1] in MINIGAMES), None)

    def pickup(self, step: Step, counters: Mapping, done: Container[str] = frozenset()) -> list[dict]:
        """The pickup, after the minigame its requirement names unless ``done`` holds that event (a tour played it
        on the way)."""
        node, lvl = step.node, self.db.nodes[step.node][0]
        out = []
        if (f := self.minigame(step.location)) is not None and f not in done:
            out.append({"kind": "minigame", "level": lvl, "from": node, "to": node, "flag": f,
                        "goal": MINIGAMES[f][1] or node, "solver": MINIGAMES[f][0], "requires": None,
                        "confidence": None, "kit": _kit(counters)})
        return out + [{"kind": "pickup", "level": lvl, "from": node, "to": node, "goal": step.location,
                       "item": step.item, "requires": None, "confidence": None, "kit": _kit(counters)}]


def _numbered(plan: Plan, segs: list[dict]) -> list[dict]:
    tier = plan.settings.movement_tier
    return [{"index": i, **s, "tier": tier} for i, s in enumerate(segs)]


def chain_segments(plan: Plan, logic: Logic, sphere: int, index: int = 0, *, back: bool = False,
                   played: list[SpoilerSphere] | None = None) -> list[dict]:
    """A progression item's spoiler paths as play segments (D172's chain driver, Step X.12; R1.16's input): one per
    hop of its obtain path (the level-file edge the logic takes there: the first whose rule holds at the sphere's
    state, ``requires = "true"`` first, a skip last), then a ``pickup`` at its location (after a ``minigame`` when its
    requirement names one, :data:`MINIGAMES`), and with ``back`` one per hop of its return path (read with the item
    held).  Each is ``{"index", "kind"`` (the edge's: walk, exit, cart, teleport; or pickup, minigame),
    ``"level", "from", "to", "goal"`` (what the play goal targets: the to-node, the exit's id, the location),
    ``"requires", "confidence", "kit"`` (the elements held), ``"tier"`` (the plan's movement tier), for an exit
    ``"dest"`` (the level path it loads), for a pickup ``"item"``, and a hop's hints (:meth:`_Chain.hints`:
    ``mech``, ``scene``, ``fall``, ``seeds``)}.  A disc teleport is ``kind = "teleport"`` on its exit.  A return
    path that needs what the round's escape picks up on the way (``Step.picks_up``) takes its hops' edges by the
    logic's options alone.  Raises :class:`PlanError` for a missing sphere or item.  ``played``: :func:`spheres`'
    result, when the caller has it.  A tour of whole spheres: :func:`tour_segments`."""
    spheres_ = played if played is not None else _playthrough(plan, logic)[1]
    if not 1 <= sphere <= len(spheres_) or not 0 <= index < len(spheres_[sphere - 1].steps):
        raise PlanError(f"no progression item {index} in sphere {sphere}")
    ch, sp = _Chain(plan, logic), spheres_[sphere - 1]
    step = sp.steps[index]
    after = dict(sp.counters)
    logic._add(collections.Counter(), after, step.item, logic.vanilla[step.location][1])   # element counters only
    out = [ch.hop(u, v, sp.counters, sp.flags)[0] for u, v in zip(step.obtain, step.obtain[1:])]
    out += ch.pickup(step, sp.counters)
    if back:
        out += [ch.hop(u, v, after, sp.flags, step.picks_up)[0] for u, v in zip(step.back, step.back[1:])]
    return _numbered(plan, out)


def tour_segments(plan: Plan, logic: Logic, spheres: Iterable[int], *, start: str | None = None, back: bool = True,
                  played: list[SpoilerSphere] | None = None, counted: bool = True,
                  victory: bool = False) -> list[dict]:
    """A playthrough of whole spheres as one chain (Step X.19, R1.16's tour): from ``start`` (the world's start) to
    each item a sphere collects in sphere order (its progression items and, with ``counted``, the counted ones,
    obsidians; within a sphere the nearest next: the fewest hops at the state held so far, the spoiler's order on
    ties), each picked up where it stands, and with ``back`` the way to the start at the end (the last item's
    spoiler return path).
    Where no path leads from where the tour stands to any item left (a one-way drop), it takes the last item's
    return path to the start first.  Before a hop it plays what the logic only credits: each barrier the edge
    crosses (``kind = "barrier"``: its shapes, the staff's elements to cast; a permanent one once) and each button
    or event the rule (or a location's gate) needs that the tour hasn't set (``"button"``, ``"minigame"`` for
    :data:`MINIGAMES`, else ``"event"`` with ``how``: touch, hit, killed, action...), each after the path to its
    node.  With ``victory`` (Step R1.16: the final sphere) it ends at the world's victory flag (the way to its node
    and its event: d1's Spideyzar killed) in place of the way back.  The segments are :func:`chain_segments`'s,
    each with its ``sphere``; ``flag`` names what an action sets.  The tour sets nothing it doesn't play: a tour
    of later spheres alone (a placed start with their kit) plays every action its ways need.  A one-shot exit
    (:func:`one_shot`: d1's bridge-end cutscene into d2) is taken once: after it the tour finds its ways without
    it, and where the logic then has none, by a ride it leaves out (:data:`RIDES`, ``kind = "ride"``: d1's elevator
    from floor 7 back to floor 1; Step R1.16d, AZ-477); taking it sets what its arrival's events set by being reached
    (``d2.lab.reached``, which d1's walk onto the beam walkway reads once the cutscene has fired; Step R1.24b)."""
    spheres_ = played if played is not None else _playthrough(plan, logic)[1]
    want = sorted(set(spheres))
    if not want or not all(1 <= n <= len(spheres_) for n in want):
        raise PlanError(f"no sphere {want} in 1-{len(spheres_)}")
    ch, db, canon = _Chain(plan, logic), logic.db, logic.canon
    cls = {it["name"]: it["class"] for it in db.items["item"]}
    kinds = ("progression", "progression_counted") if counted else ("progression",)
    out: list[dict] = []
    marks: list[tuple[int, int]] = []     # (the first segment of a sphere's part, its number)
    done: set[str] = set()
    got = {loc for sp in spheres_[:want[0] - 1] for loc in sp.locations}
    slots = set(got)
    held: collections.Counter = collections.Counter()
    cur, counters = canon(start or logic.start), dict(spheres_[want[0] - 1].counters)
    spent: set[tuple[str, str]] = set()      # the hops of the one-shot exits the tour has taken (AZ-477)
    rides: dict[str, list[str]] = collections.defaultdict(list)
    for a, b in RIDES:
        rides[a].append(b)

    def way(src: str, dst: str, cn: Mapping, fl, sl) -> tuple[str, ...]:
        """The tour's way: in logic with no spent one-shot exit; else, once one is spent, with the rides the logic
        leaves out (:data:`RIDES`)."""
        return _path(logic, ch.rules, src, dst, cn, fl, sl, spent) or (
            _path(logic, ch.rules, src, dst, cn, fl, sl, spent, rides) if spent else ())

    def needs(text: str | None, flags) -> list[str]:
        """The flags (buttons ``.open``, events, others) of the first term of ``text`` that holds at the counters
        and ``flags`` and not yet set by the tour; [] when it holds on what the tour has set."""
        if not text or ch.holds(text, counters, frozenset(done)):
            return []
        ast = parse(text)
        for t in ast[1] if ast[0] == "or" else (ast,):
            if ch.rules.ast(t)(counters, frozenset(flags)):
                return [a[1] + ".open" * (a[0] == "button") for a in atoms(t)
                        if a[0] in ("flag", "button", "event") and a[1] + ".open" * (a[0] == "button") not in done]
        return []

    def at_of(f: str) -> str | None:
        """The node an object's flag is set at (a button's ``.open``, an event), None for a barrier or a flag no
        object sets."""
        o = db.hand.get(f.removesuffix(".open"), (None, None, {}))[2]
        return canon(o["at"]) if "at" in o else None

    def act(f: str, flags, depth: int) -> None:
        nonlocal cur
        oid = next((x for x in (f, f.removesuffix(".open"), f.removesuffix(".destroyed")) if x in db.hand), None)
        lvl, kind, o = db.hand[oid] if oid else (None, None, {})
        seg = {"flag": f, "requires": o.get("requires"), "confidence": None, "kit": _kit(counters)}
        # where it is set: an object's node, or a barrier's sides (the nearest the tour gets to)
        ats = [canon(o["at"])] if "at" in o else [canon(n) for n in o.get("destroy_from", ())] if kind == "barrier" \
            else []
        # a minigame played at more than one place (w2's hose: the console's on, then the joystick's won) starts at its
        # first station: the node of the event of its level its requirement names (Step R1.16)
        first = [e for a in atoms(parse(o.get("requires") or "true")) if oid in MINIGAMES and a[0] == "event"
                 and a[1] not in done and db.hand.get(a[1], (None,))[0] == lvl and (e := at_of(a[1])) is not None]
        entry = first[:1] or ats
        # the way there by what the tour has set, else by the logic's other flags: never by this one or another the
        # tour hasn't set where this one is (d1's walkway: five touches at its far end open the way onto it)
        flags = flags - {f} - {g for g in flags if g not in done and at_of(g) in ats + entry}
        ways = sorted((len(p), at, p) for at in entry for fl in (frozenset(done), flags)
                      if (p := way(cur, at, counters, fl, slots)))
        if not ats:
            out.append(seg | {"kind": "event", "how": "unknown", "level": lvl, "from": cur, "to": cur, "goal": f})
        elif kind == "barrier":
            go(ways[0][1] if ways else ats[0], flags, depth + 1, path=ways[0][2] if ways else None)
            barrier(oid, cur, cur)
        else:
            at = ats[0]
            go(entry[0], flags, depth + 1, path=ways[0][2] if ways else None)
            seg |= {"level": lvl, "from": entry[0], "to": at}
            if oid in MINIGAMES:
                seg |= {"kind": "minigame", "solver": MINIGAMES[oid][0], "goal": MINIGAMES[oid][1] or at}
                done.update(a[1] for a in atoms(parse(o.get("requires") or "true"))
                            if a[0] == "event" and at_of(a[1]) in first)
                cur = at
            elif kind == "button":
                gen = db.generated_objects.get(o.get("of"), (None, None, {}))[2]
                seg |= {"kind": "button", "goal": o.get("of") or at,
                        **({"lock_toggle": gen["lock_toggle"]} if gen.get("lock_toggle") else {})}
            else:
                ev = next((x for x in db.derived.get(lvl, {}).get("events", ()) if x["id"] == oid), {})
                seg |= {"kind": "event", "how": oid.rsplit(".", 1)[-1], "goal": at,
                        **({"object": ev["platform"]} if ev.get("platform") else {})}
            out.append(seg)
        done.add(f)

    def barrier(b: str, u: str, v: str) -> None:
        lvl, _, o = db.hand[b]
        if b + ".destroyed" in done:
            return
        g = logic.generated(o)
        out.append({"kind": "barrier", "level": lvl, "from": u, "to": v, "goal": b, "shapes": list(g.get("shapes", ())),
                    "cast": [CASTS[c] for c in g.get("elements") or "" if c in CASTS], "requires": g.get("requires"),
                    "confidence": None, "kit": _kit(counters)})
        if logic.persist(o) == "permanent":
            done.add(b + ".destroyed")

    def go(dst: str, flags, depth: int = 0, path=None, escape: bool = False) -> None:
        """The tour from where it stands to ``dst`` (along ``path`` when given; ``escape``: a return path the
        round's escape found, its edges by the options alone), acting for each hop's needs."""
        nonlocal cur
        if depth > 4:
            raise PlanError(f"the tour's actions nest too deep on the way to {dst}")
        path = path or way(cur, dst, counters, flags, slots)
        if not path:          # a way whose flags the round credits on the spot as it walks (§2.13 rule 1's closure)
            lit = frozenset(logic._escape(ch.rules, _Round(dict(counters), collections.Counter(held), set(logic.pool),
                                                           set()), cur, plan.placement, flags)[2])
            if path := way(cur, dst, counters, lit, slots):
                flags = lit       # each hop's needs then sets them (an event's own segment)
        if not path:
            raise PlanError(f"no path from {cur} to {dst} at the tour's state")
        for u, v in zip(path, path[1:]):
            u = u.split()[0]
            if cur != u:
                go(u, flags, depth + 1)
            if (u, v) in RIDES and not any(w == v and rule(counters, flags) for w, rule in ch.rules.adj.get(u, ())):
                out.append(ch.ride(u, v, counters))      # a ride the logic leaves out: the way it took is spent
                cur = v
                continue
            seg, e = ch.hop(u, v, counters, flags, escape)
            if escape:
                seg["escape"] = True
            elif pending := needs(e.get("requires"), flags) + [f for f in e.get("assumes", ()) if f not in done]:
                for f in pending:
                    act(f, flags, depth)
                if cur == seg["to"]:      # the actions ended where the hop leads (d1's walkway: its far end's touch)
                    continue
                if cur != u:
                    go(u, flags, depth + 1)
            for b in e.get("through", ()):
                barrier(b, u, seg["to"])
            out.append(seg)
            if ch.spends(u, v):
                spent.add((u, v))
                # what the one-shot exit's arrival sets by being reached (d2.lab.reached: d1's cutscene has fired,
                # which the walk onto d1's beam walkway reads, Step R1.24b, D722)
                done.update(f for f, (_, kind, o) in db.hand.items() if kind == "event" and "at" in o
                            and canon(o["at"]) == seg["to"] and (o.get("requires") or "true") == "true")
            cur = seg["to"]

    def way_home(sp: SpoilerSphere) -> tuple[tuple, bool] | None:
        """The way from where the tour stands to the start (the spoiler's return path: in logic, else by what the
        round's escape picks up, plan §2.13 rule 2), or None."""
        if p := way(cur, logic.start, counters, sp.flags, slots):
            return p, False
        rnd = _Round(dict(counters), collections.Counter(held), set(slots), set())
        _, _, fl, cn = logic._escape(ch.rules, rnd, cur, plan.placement, logic.forced.get(cur, frozenset()) & sp.flags)
        return ((p, True) if (p := way(cur, logic.start, cn, fl, slots)) else None)

    for n in want:
        marks.append((len(out), n))
        sp, slots = spheres_[n - 1], set(got)     # a disc teleport is one-shot from the sphere's own state
        counters = {k: max(v, counters.get(k, 0)) for k, v in sp.counters.items()} | {
            k: v for k, v in counters.items() if k not in sp.counters}
        steps = {s.location: s for s in sp.steps}
        todo = [steps.get(loc) or Step(loc, plan.placement[loc], canon(db.node_of[loc]), (), (), False)
                for loc in sorted(set(sp.locations) & plan.placement.keys())
                if cls[plan.placement[loc]] in kinds]
        todo.sort(key=lambda s: s.location not in steps)          # the spoiler's items first on ties
        while todo:
            ways = [(len(p), i, p) for i, s in enumerate(todo)
                    if (p := way(cur, s.node, counters, sp.flags, slots))]
            if not ways:
                if cur == canon(logic.start) or (home := way_home(sp)) is None:
                    raise PlanError(f"no path from {cur} to sphere {n}'s items left")
                go(logic.start, sp.flags, path=home[0], escape=home[1])
                continue
            _, i, p = min(ways, key=lambda w: w[:2])
            step = todo[i]
            go(step.node, sp.flags, path=p)
            rule = next(r for lc, _, r in ch.rules.locations if lc == step.location)
            if not rule(counters, frozenset(done)):
                gates = [logic.bound.get(g, "") + ".open" * (db.generated_objects[g][1] == "obsidian_locks")
                         for g in logic.gated_by[step.location] if db.generated_objects[g][1] != "geodes"]
                for f in needs(logic.location_rows.get(step.location, {}).get("requires"), sp.flags) + [
                        f for f in gates if f and f not in done]:
                    act(f, sp.flags, 0)
                for b in logic.contained_by.get(step.location, ()):
                    barrier(b, step.node, step.node)
                if cur != step.node:
                    continue          # pick the nearest again from where the actions left the tour
            todo.pop(i)
            out.extend(ch.pickup(step, counters, done))
            logic._add(held, counters, step.item, logic.vanilla[step.location][1])
            got.add(step.location)
        if n != want[-1] and cur != canon(logic.start) and not way(cur, logic.start, counters, sp.flags, got):
            if (home := way_home(sp)) is not None:   # a one-shot way out (a guardian's teleport) is this sphere's
                go(logic.start, sp.flags, path=home[0], escape=home[1])
    if victory:
        act(db.world["victory"].removeprefix("flag:"), spheres_[want[-1] - 1].flags, 0)
    elif back and cur != canon(logic.start):
        if (home := way_home(spheres_[want[-1] - 1])) is None:
            raise PlanError(f"no way from {cur} back to the start")
        go(logic.start, spheres_[want[-1] - 1].flags, path=home[0], escape=home[1])
    for k, (at, n) in enumerate(marks):
        for seg in out[at:marks[k + 1][0] if k + 1 < len(marks) else len(out)]:
            seg["sphere"] = n
    return _numbered(plan, out)


MERGE_MAX = 4        # hops a merged walk spans at most (the search's tick budget, 3,600, holds about four)


def merge_walks(segs: list[dict], most: int = MERGE_MAX) -> list[dict]:
    """A tour with each run of consecutive walks in one level and sphere merged into one walk of up to ``most`` hops
    (Step R1.16's cut of X.19's estimate: one search and replay where there were several): from the first's
    from-node to the last's to-node, its ``parts`` the hops it spans, the union of their ``mech`` and proof
    ``seeds``, the highest ``difficulty``, the requirements joined.  A walk that asks for whole steps (``scene``),
    a fall or a ride seed, or that an escape takes, stays alone, so a hop the hints single out keeps its own
    search; a run of walks on one rig (``rig``, d1's elevator between its floors) merges into one ride the same
    way, never with a plain walk.  Renumbered."""
    def plain(s: dict) -> bool:
        return (s["kind"] == "walk" and not s.get("scene") and not s.get("fall") and not s.get("escape")
                and not any("ride" in h for h in s.get("seeds", ())) and not s.get("rig"))

    def joins(a: dict, b: dict) -> bool:
        return plain(a) and plain(b) or (a["kind"] == b["kind"] == "walk" and not a.get("escape")
                                         and not b.get("escape") and a.get("rig") is not None
                                         and a.get("rig") == b.get("rig"))
    out: list[dict] = []
    for s in segs:
        last = out[-1] if out else None
        if (last is not None and joins(last, s) and last["level"] == s["level"]
                and last.get("sphere") == s.get("sphere") and last["to"] == s["from"]
                and len(last.get("parts") or [0]) < most):
            parts = last.get("parts") or [[last["from"], last["to"]]]
            reqs = [r for r in dict.fromkeys([last["requires"], s["requires"]]) if r and r != "true"]
            seeds = [h for h in dict.fromkeys(json.dumps(h, sort_keys=True) for h in
                                              last.get("seeds", []) + s.get("seeds", []))]
            out[-1] = {**last, "to": s["to"], "goal": s["goal"], "parts": parts + [[s["from"], s["to"]]],
                       "requires": " & ".join(f"({r})" for r in reqs) if len(reqs) > 1 else reqs[0] if reqs
                       else "true",
                       "confidence": "/".join(sorted({c for x in (last, s) for c in str(x["confidence"]).split("/")}))
                       if last["confidence"] != s["confidence"] else s["confidence"],
                       "difficulty": max(last.get("difficulty", 1), s.get("difficulty", 1)),
                       "mech": sorted(set(last.get("mech", ())) | set(s.get("mech", ()))),
                       **({"seeds": [json.loads(h) for h in seeds]} if seeds else {})}
        else:
            out.append(dict(s))
    return [{**s, "index": i} for i, s in enumerate(out)]


def _playthrough(plan: Plan, logic: Logic) -> tuple[Reach, list[SpoilerSphere]]:
    db, st, placement = logic.db, plan.settings, plan.placement
    cls = {it["name"]: it["class"] for it in db.items["item"]}
    rules, trace = logic.rules(st), []
    reach = logic.reach(st, placement, trace=trace)
    if not reach.victory:
        raise PlanError(f"unbeatable: victory ({db.world['victory']}) never holds")
    out = []
    for number, sp in enumerate(trace, 1):
        steps, counted = [], collections.Counter()
        for loc in sorted(set(sp.locations) & placement.keys()):
            item, n = placement[loc], logic.vanilla[loc][1]
            if cls[item] == "progression_counted":
                counted[item] += n
            if cls[item] != "progression":
                continue
            node = logic.canon(db.node_of[loc])
            after = dict(sp.counters)
            logic._add(collections.Counter(sp.held), after, item, n)
            back, picks = _path(logic, rules, node, logic.start, after, sp.flags, sp.got), False
            if not back:
                rnd = _Round(sp.counters, sp.held, set(sp.got), set())
                _, _, flags, counters = logic._escape(rules, rnd, node, placement,
                                                      logic.forced.get(node, frozenset()) & sp.flags)
                back, picks = _path(logic, rules, node, logic.start, counters, flags, sp.got), True
            obtain = _path(logic, rules, logic.start, node, sp.counters, sp.flags, sp.got)
            steps.append(Step(loc, item, node, obtain, back, picks))
        out.append(SpoilerSphere(number, tuple(steps), dict(sorted(counted.items())),
                                 rules.victory(sp.counters, sp.flags), sp.traps, sp.free_traps, sp.counters,
                                 sp.flags, sp.locations))
    return reach, out


def save_nodes(logic: Logic) -> dict[str, tuple[str, str, str | None]]:
    """Each save point of a level with a level file -> (its level, its name,
    its canonical node: the node anchoring it or its derived zone, a stub's
    one node, or None when no node holds it)."""
    db = logic.db
    anchored = {a: n["id"] for doc in db.levels.values() for n in doc["node"] for a in n.get("anchors", [])}
    out = {}
    for lvl in sorted(db.levels):
        zones = {o["id"]: o.get("main_zone") for o in db.derived.get(lvl, {}).get("objects", ())}
        for sp in db.generated[lvl]["save_points"]:
            node = lvl if lvl in db.stubs else anchored.get(sp["id"]) or anchored.get(f"zone:{zones.get(sp['id'])}")
            out[sp["id"]] = (lvl, sp.get("save_id") or sp["id"], node)
    return out


def _spans(spheres_: list[SpoilerSphere], last: frozenset[str]) -> dict[str, tuple[int, int]]:
    """Each trap -> the first and last sphere at whose state it is one
    (``len + 1``: only with everything collected, ``last``)."""
    out = {}
    for sp in spheres_:
        for n in sp.traps:
            out[n] = (out.get(n, (sp.number,))[0], sp.number)
    end = len(spheres_) + 1
    out.update({n: (end, end) for n in last if n not in out})
    return out


def _span(span: tuple[int, int], end: int) -> str:
    a, b = span
    if a == end:
        return "with everything collected"
    return f"sphere {a}" if a == b else f"spheres {a}-{b}"


def _first(spheres_: list[SpoilerSphere], holds) -> str:
    """The first sphere at whose state ``holds(sphere)``."""
    return next((f"from sphere {sp.number}" for sp in spheres_ if holds(sp)), "never in the spheres")


SOFTLOCK = ("no settings are softlock-free before R2.1 (D82): the logic keeps the seed beatable and every "
            "location but the forfeitable ones collectable for a player who collects in sphere order, but taking "
            "a one-way drop, door, the airship or a guardian arena before holding what its far side needs can "
            "softlock; keep a save from before one-way drops")


def spoiler_lines(plan: Plan, logic: Logic) -> list[str]:
    """The full spoiler, as text (plan §3.6, RANDOMIZER_DB §7.4)."""
    doc, st, db = plan.doc, plan.settings, logic.db
    toggles = ", ".join(f"{sid} {'on' if v else 'off'}" for sid, v in sorted(st.skip_override.items())) or "none"
    kept = ", ".join(c for c in CATEGORIES if c in st.exclude_categories)
    on = picks_on(st, logic.skip_tables)     # D275: a batch once, with the kits of its variants on
    families = collections.defaultdict(list)
    for pid, ids in on.items():
        kits = ", ".join(logic.skip_tables[sid].get("requires", "true") for sid in ids)
        families["+".join(logic.skip_tables[ids[0]].get("tricks", ()))].append(
            pid if ids == [pid] else f"{pid} ({kits})")
    lines = [
        f"plan {doc['sha256'][:12]}: seed {doc['seed']!r}, attempt {doc['attempt']}, {doc['generator']}",
        f"settings: skip_ceiling {st.skip_ceiling}, movement_tier {plan.asked.movement_tier}, dark_fire 1, "
        + (f"seed_difficulty {st.seed_difficulty}, " if st.seed_difficulty else "") +
        f"toggles: {toggles}" + (f", kept vanilla: {kept}" if kept else "") + f"; share {doc['share']} "
        f"(skip registry tag {registry_tag(picks(logic.skip_tables)).hex()})",
        f"database {doc['db_digest'][:12]}: the plan places {len(plan.placement)} locations of "
        f"{', '.join(sorted(set(db.levels) - db.stubs))}; the stubs keep their vanilla items",
        f"skips on ({len(on)}): " + ("; ".join(f"{fam}: {', '.join(ids)}" for fam, ids in sorted(families.items()))
                                     or "none"),
        SOFTLOCK,
    ]
    if any("saveanywhere" in fam.split("+") for fam in families):
        lines.append("warning: a saveanywhere skip is on (plan §2.14): it never counts as an escape")
    reach, spheres_ = _playthrough(plan, logic)
    if st.seed_difficulty:   # right after the skips on
        known = known_traps(logic, st)
        prof = difficulty.profile(logic, st, plan.placement)
        lines[4:4] = difficulty.spoiler_lines(
            prof, difficulty.openers(logic, st, plan.placement) if prof["asks"] else [],
            sorted(reach.traps - reach.after_completion - known))
    if plan.asked.sliders:   # D1064, D1066: right after the settings
        lines.insert(2, f"movement sliders: {sliders_text(plan.asked.sliders)}; {said(plan.asked)}; {PROMISE}")
    won = False
    for sp in spheres_:
        if sp.victory and not won:
            lines.append(f"victory ({db.world['victory']}) holds from sphere {sp.number}")
            won = True
        counted = "".join(f", {n} {item}" for item, n in sp.counted.items())
        lines.append(f"sphere {sp.number}: {len(sp.steps)} progression{counted}")
        for s in sp.steps:
            lines += [f"  {s.item} at {s.location} ({s.node})",
                      f"    obtain: {' > '.join(s.obtain) or 'no path found'}",
                      f"    return: {' > '.join(s.back) or 'no path found'}"
                      + (" (with what it picks up on the way)" if s.picks_up else "")]
    if not won:
        lines.append(f"victory ({db.world['victory']}) holds after the last sphere")
    return lines + _dangers(plan, logic, reach, spheres_)


def _dangers(plan: Plan, logic: Logic, reach: Reach, spheres_: list[SpoilerSphere]) -> list[str]:
    """The spoiler's danger list (plan §2.9, §2.13, §2.14, §3.6): the traps,
    ranked, the ``assumes`` edges, the forfeitable locations, the traps
    after completion, the region gates, the dangerous saves and the
    excluded locations."""
    db, st, canon = logic.db, plan.settings, logic.canon
    end = len(spheres_) + 1
    traps = {canon(n) for n in reach.traps}
    free = {canon(n) for n in reach.free_traps} | {n for sp in spheres_ for n in sp.free_traps}
    known = {canon(n) for n in known_traps(logic, st)}
    spans = _spans(spheres_, frozenset(traps))
    rank = {n: (0 if n in free and n not in known else 1 if n in free else 2, spans[n], n) for n in spans}
    lines = [f"traps ({len(rank)}; a node a player can get into with the kit of those spheres and not get back "
             f"from; new trick-free traps first (the trap gate refuses them, D83(b)), then the known ones "
             f"(vanilla's own, or signed in known_traps), then those only a skip gets into):"]
    lines += [f"  {n}: {_span(spans[n], end)}, "
              + ("trick-free, new" if r == 0 else "trick-free, known" if r == 1 else "only a skip gets in")
              for n, (r, _, _) in sorted(rank.items(), key=lambda kv: kv[1])]
    edges = [(lvl, e) for lvl in sorted(db.levels) for e in db.levels[lvl]["edge"] if e.get("assumes")]
    lines.append(f"assumes edges ({len(edges)}; in logic once their flags are credited: the far side's way back "
                 f"needs them, so set them before taking the edge):")
    lines += [f"  {e['from'] or lvl} > {e['to'] or '(nowhere)'} assumes {', '.join(e['assumes'])}: "
              f"{_first(spheres_, lambda sp, e=e: set(e['assumes']) <= sp.flags)}" for lvl, e in edges]
    region_of = {n: disc for disc, nodes in logic.regions.items() for n in nodes}
    forfeit = sorted(logic.forfeitable)
    lines.append(f"forfeitable locations ({len(forfeit)}; collect them before the region's guardian slot: its "
                 f"one-shot teleport leaves the region for good, D81):")
    lines += [f"  {loc} ({canon(db.node_of[loc])}, the {region_of.get(canon(db.node_of[loc]), '?')} region)"
              for loc in forfeit]
    after = {canon(n) for n in reach.after_completion}
    lines.append(f"no-return regions ({len(logic.regions)}; each region's gate is computed per node: the one-shot "
                 f"teleport with 3 of its disc, the slot's gate and the way there, the boss included, plan §2.9):")
    for disc, nodes in sorted(logic.regions.items()):
        slot = logic.slots[disc]
        got = next((sp for sp in spheres_ if slot in sp.locations), None)
        when = (f"its slot {slot} is collected in sphere {got.number}, holding {got.counters.get(DISCS[disc], 0)} "
                f"of the disc" if got else f"its slot {slot} is never collected")
        lines += [f"  {disc}: {len(nodes)} node{'s' * (len(nodes) != 1)} ({', '.join(sorted(nodes))}); {when}",
                  f"    traps after completion (no way out once the slot is collected): "
                  f"{', '.join(sorted(nodes & after)) or 'none'}"]
    saves = save_nodes(logic)
    risky = sorted((sid, lvl, name, node) for sid, (lvl, name, node) in saves.items() if node in traps | after)
    lines.append(f"dangerous saves ({len(risky)}; a save point at a trap or a trap after completion: a save "
                 f"overwritten there can't be recovered, plan §2.14; {sum(n is None for *_, n in saves.values())} "
                 f"of {len(saves)} save points have no node):")
    lines += [f"  {lvl} {name} ({sid}) at {node}: "
              + ("a trap after completion" if node in after else f"a trap in {_span(spans[node], end)}")
              for sid, lvl, name, node in risky]
    excluded = sorted(excluded_locations(logic) - logic.forfeitable)
    lines.append(f"excluded locations ({len(excluded)}; useful items or filler only: lock 10 and the full clears, "
                 f"RQ-5, the locations marked exclude and the unsaved spots, AZ-467): {', '.join(excluded) or 'none'}")
    return lines
