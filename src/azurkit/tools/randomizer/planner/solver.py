"""The solver: reach, escape, the physical graph and the no-return regions
(RANDOMIZER_PLAN §2.4-§2.9, §2.12, §2.13, §3.1-§3.4; docs/RANDOMIZER_DB.md
§15; Steps R1.5-R1.7).

:class:`Logic` compiles a loaded :class:`~.loader.Database` once, and
:meth:`Logic.reach` returns the least fixpoint of RANDOMIZER_PLAN §2.13's
safe-reach loop for a placement, starting items and flags under one set of
options (D144). Each round (a sphere) reads the state it starts with:

- ``R``: forward reach from the start over the edges in logic;
- ``Safe``: the nodes of ``R`` whose escape holds (below);
- every location at a safe node and every flag or event at a safe node
  whose requirement holds is collected or credited, and every terminal
  event at a node of ``R`` (rule 4: the game ends there);

until a round adds nothing. The state is the items held (a ``Counter``,
AZ-160) and the counters derived from them, plus the credited flags.

**The escape** of a node n (rules 1-3) is a local closure: from n, with the
items held, the flags credited from the start and the flags forced on entry
to n, it walks forward over the edges in logic, collects the locations not
yet collected and credits the flags whose requirement holds wherever it
gets, and holds once it reaches the start (the anchor, never the hub).
Flags credited elsewhere don't count (CE2). A flag is forced on entry to n
when no way into n does without it: with no skip, every player tier's edge
and every item, n can't be reached while the flag is never credited (an
edge's ``assumes`` count as needs), tried for every flag that reach credits.
That is read once per database, so it depends on neither the state nor the
options and Safe stays monotone (D113). A forced flag counts only once
credited: a node that a skip alone gets into isn't safe by the flags its
other ways in set.

**R_phys** is where a player can physically get with the items held: the
edges out of logic too (``logic = false``, every cart, every movement
difficulty including 0, the ``phys`` tier), ``assumes`` ignored, a dark
edge at fire 1 whatever ``dark_fire``, toggles pressed, a respawning barrier
crossed where its destroy requirement holds whatever its mechanism's
handling, one key per lock (no worst-case count), and only the skips the
options turn on. A **trap** is a node of R_phys whose escape on that
physical graph fails at some sphere's state, starting with the flags forced
on entry physically (``assumes`` no need there) that a player can set. A
trap is **trick-free** when, at that state, a player gets into it with no
skip at all (R_phys with every skip off); §2.13's trap gate (D83(b), the
fill's verify, Step R1.12) reads those.

**The disc teleport** (plan §2.9, D81) is one shot: it is no edge of R or
R_phys, and an escape takes it, to its far end, only while its disc's
guardian slot is not yet collected (the disc not yet placed) and its
requirement holds, so reaching the slot with 3 of the disc and whatever
the slot and the boss need gets back. A **no-return region** is the nodes,
reached with every item and no skip, that get back to the start only by a
disc teleport. Its pool locations other than the slot are **forfeitable**:
what they hold never counts (D81: the fill puts no progression there), and
once its slot is collected, its nodes a player can still reach are the
**traps after completion**.

**The cost** (plan §2.13): a backward search from the start, in which an
edge is passable on the items held and the flags its own source node can
set, finds most safe nodes with no closure (the fast path), and a closure
that fails fails, in that round, every node it saw whose starting flags it
held (their closures are inside its own: the cache).

Requirements are compiled once per option set into closures over the
counters and flags, with the skips that are off and the edges above the
movement tier compiled away (§3.4). Nothing here reads a file: the database
is the loader's, and an edge's movement tier is its ``difficulty`` number
(the envelope's tiers, ``draft/tiers.toml``, which the planner never
imports).
"""

from __future__ import annotations

import collections
from collections.abc import Callable, Container, Iterable, Mapping
from dataclasses import dataclass

from azurkit.tools.randomizer.planner.grammar import DISCS, parse
from azurkit.tools.randomizer.planner.settings import (
    MOVEMENT_TIERS,
    SETTINGS_FORMAT,
    Settings,
    pick_of,
    settings_from_table,
    skips_on,
)

Rule = Callable[[Mapping[str, int], Container[str]], bool]
MAX_SETTINGS = Settings(4, "frame_perfect", 1, {})   # every in-logic skip on, every player tier's edge usable
TRICK_FREE = Settings(0, "frame_perfect", 1, {})     # no skip, every player tier's edge usable
STRICTEST = Settings(0, "safe", 1, {})               # no skip, the safe tier (rule 10's options)
_ALL = 1 << 30                                        # a counter "with every item"


def _true(c, f):
    return True


def _false(c, f):
    return False


def _all(rules: Iterable[Rule]) -> Rule:
    rules = [r for r in rules if r is not _true]
    if any(r is _false for r in rules):
        return _false
    if len(rules) < 2:
        return rules[0] if rules else _true
    rules = tuple(rules)
    return lambda c, f: all(r(c, f) for r in rules)


def _any(rules: Iterable[Rule]) -> Rule:
    rules = [r for r in rules if r is not _false]
    if any(r is _true for r in rules):
        return _true
    if len(rules) < 2:
        return rules[0] if rules else _false
    rules = tuple(rules)
    return lambda c, f: any(r(c, f) for r in rules)


def _counter(name: str, n: int) -> Rule:
    return lambda c, f: c.get(name, 0) >= n


def _flag(name: str) -> Rule:
    return lambda c, f: name in f


class _EveryFlag:
    """A flag container holding every flag: the most a state ever credits."""

    def __contains__(self, name: object) -> bool:
        return True


def _band(thresholds: Iterable[int], n: int) -> int:
    """A count's band: the largest threshold the logic compares its counter
    with at or below ``n`` (0 when none is)."""
    return max((t for t in thresholds if t <= n), default=0)


def _matching(cand: Mapping[str, list[str]]) -> dict[str, str]:
    """A largest matching of each lock in ``cand`` to one of its candidate
    key locations, by augmenting paths: {key location: lock}."""
    owner: dict[str, str] = {}

    def augment(lock: str, seen: set[str]) -> bool:
        for loc in cand[lock]:
            if loc not in seen:
                seen.add(loc)
                if loc not in owner or augment(owner[loc], seen):
                    owner[loc] = lock
                    return True
        return False
    for lock in cand:
        augment(lock, set())
    return owner


class SolverError(ValueError):
    """A placement, item, flag or option set the solver can't honour."""


@dataclass(frozen=True)
class Reach:
    """The fixpoint: the nodes reached in logic (R), the safe ones, the nodes
    of R_phys, the traps (nodes of R_phys whose escape failed at some
    sphere's state), the traps after completion (the nodes of R_phys in a
    no-return region whose slot is collected), the locations collected, the
    flags credited, whether the world's victory requirement holds and the
    trick-free traps."""
    nodes: frozenset[str]
    safe: frozenset[str]
    phys: frozenset[str]
    traps: frozenset[str]
    after_completion: frozenset[str]
    locations: frozenset[str]
    flags: frozenset[str]
    victory: bool
    free_traps: frozenset[str] = frozenset()   # the traps a player gets into with no skip (D83(b))


class _Rules:
    """One option set's compiled graph: edges, credits and locations; the
    physical graph (R_phys) when ``physical``."""

    def __init__(self, logic: Logic, settings: Settings, physical: bool = False):
        self.logic, self.db, self.physical = logic, logic.db, physical
        self.on = frozenset(skips_on(settings, logic.skip_tables))
        self.dark_fire = 1 if physical else settings.dark_fire   # dark_fire is logic's leniency, like the tier
        self.tier = MOVEMENT_TIERS.index(settings.movement_tier) + 1
        self.memo: dict[tuple, Rule] = {}
        self.reads: dict[str, set[int]] = collections.defaultdict(set)   # counter -> the thresholds compiled
        lg, db = logic, logic.db
        self.adj: dict[str, list[tuple[str, Rule]]] = collections.defaultdict(list)
        self.radj: dict[str, list[tuple[str, Rule]]] = collections.defaultdict(list)    # the edges, reversed
        self.teleports: list[tuple[str, str, Rule, str]] = []    # the disc teleports: (from, to, rule, disc)
        for lvl in sorted(db.levels):
            for e in db.levels[lvl]["edge"]:
                edge = self.edge(lvl, e)
                if edge and "disc" in e:
                    self.teleports.append((*edge, e["disc"]))
                elif edge:
                    self.adj[edge[0]].append(edge[1:])
                    self.radj[edge[1]].append((edge[0], edge[2]))
        self.credits: list[tuple[str, str, bool, Rule]] = []     # (flag, node, terminal, rule)
        for oid, (lvl, kind, o) in sorted(db.hand.items()):
            if kind == "button" and o["mode"] == "toggle" and not (physical or lg.harmless("toggle")):
                continue
            terminal = kind == "event" and o.get("terminal", False)
            if lvl in db.stubs:     # a stub is one free node (§4.1): its objects' flags come with it
                if kind != "barrier" or lg.persist(o) == "permanent":
                    self.credits.append((oid + {"barrier": ".destroyed", "button": ".open"}.get(kind, ""), lvl,
                                         terminal, _true))
            elif kind == "barrier":
                if lg.persist(o) == "permanent":
                    self.credits += [(oid + ".destroyed", lg.canon(n), False, self.destroy_at(oid, lg.canon(n)))
                                     for n in o.get("destroy_from", [])]
            elif kind == "button":
                self.credits.append((oid + ".open", lg.canon(o["at"]), False,
                                     _all([self.button(oid), self.light_at(o["at"])])))
            else:
                self.credits.append((oid, lg.canon(o["at"]), terminal, _all(
                    [self.expr(o.get("requires", "true")), self.light_at(o["at"]),
                     *(self.opened(b, lg.canon(o["at"])) for b in lg.required_for.get(oid, ()))])))
        self.locations: list[tuple[str, str, Rule]] = []
        for loc, lvl in sorted(lg.pool.items()):
            if lvl in db.stubs:
                self.locations.append((loc, lvl, _true))
                continue
            node = db.node_of[loc]
            over = lg.location_rows.get(loc, {})
            self.locations.append((loc, node, _all(
                [*(self.gate(g) for g in lg.gated_by[loc]), self.expr(over.get("requires", "true")),
                 *(self.opened(b, node) for b in lg.contained_by.get(loc, ())), self.light_at(node)])))
        self.victory = self.expr(db.world["victory"])

    # ---- expressions (docs/RANDOMIZER_DB.md §5) --------------------------------------------------------------------
    def expr(self, text: str, bump: tuple[str, int, tuple[str, ...]] | None = None) -> Rule:
        return self.ast(parse(text), bump)

    def ast(self, a: tuple, bump: tuple[str, int, tuple[str, ...]] | None = None) -> Rule:
        kind = a[0]
        if kind == "and":
            return _all(self.ast(x, bump) for x in a[1])
        if kind == "or":
            return _any(self.ast(x, bump) for x in a[1])
        if kind == "const":
            return _true if a[1] else _false
        if kind == "counter":   # §5.5: a lock that uses its key up needs the worst-case count
            if bump and bump[0] == a[1]:
                return self.key_count(a[1], a[2] + bump[1], bump[2])
            return self.counter(a[1], a[2])
        if kind == "flag":
            return _flag(a[1])
        if kind == "button":
            return _flag(a[1] + ".open")
        if kind == "event":
            return _flag(a[1])
        if kind == "skip":
            return self.skip(a[1])
        return self.destroy(a[1]) if a[2] == "destroy" else self.passes(a[1], *a[2])

    def counter(self, name: str, n: int) -> Rule:
        self.reads[name].add(n)
        return _counter(name, n)

    def key_count(self, name: str, n: int, pending: tuple[str, ...]) -> Rule:
        """§5.5's worst-case count with the key rule (AZ-345): the keys held
        and each refund key still on its spot (its pending counter) make n."""
        if not pending:
            return self.counter(name, n)
        self.reads[name].update(k for k in range(n - len(pending), n + 1) if k > 0)
        return lambda c, f: c.get(name, 0) + sum(c.get(p, 0) for p in pending) >= n

    def memoised(self, key: tuple, build: Callable[[], Rule]) -> Rule:
        if key not in self.memo:
            self.memo[key] = build()
        return self.memo[key]

    def skip(self, sid: str) -> Rule:
        """§5.4: on when the options turn it on (never a held or manual
        skip, D144) and its own requirement holds."""
        if sid not in self.on:
            return _false
        return self.memoised(("skip", sid), lambda: self.expr(self.logic.skip_tables[sid].get("requires", "true")))

    def light(self, dark: bool | str) -> Rule:
        """§2.12, D144: a dark edge (or anything done at a dark node) needs
        fire >= dark_fire, or, when ``dark`` names a nolight skip, that skip
        once the options turn it on: it lifts its own dark area only."""
        if dark is False:
            return _true
        fire = self.counter("fire", self.dark_fire)
        return fire if dark is True else _any([fire, self.skip(dark)])

    def light_at(self, node: str) -> Rule:
        return self.light(self.db.nodes[node][1].get("dark", False))

    # ---- objects (§5.3) --------------------------------------------------------------------------------------------
    def base(self, o: Mapping) -> str:
        """§5.3: the generated requirement a barrier or button binds, or its
        override. A button with no `of` has none of its own; a gate whose
        generated requirement is null (an undecoded barrier, an uncoded
        keylock) is false until override_requires explains it (§4.4)."""
        if "override_requires" in o:
            return o["override_requires"]
        if "of" not in o:
            return "true"
        return self.logic.generated(o).get("requires") or "false"

    def destroy(self, bid: str) -> Rule:
        """A barrier's destroy requirement: the generated one (or its
        override) and the hand one."""
        def build():
            o = self.db.hand[bid][2]
            return _all([self.expr(self.base(o)), self.expr(o.get("requires", "true"))])
        return self.memoised(("destroy", bid), build)

    def destroy_at(self, bid: str, node: str) -> Rule:
        """Destroying a barrier standing at ``node`` (a canonical node): its
        destroy requirement and the light there (§4.2)."""
        return _all([self.destroy(bid), self.light_at(node) if node in self.db.nodes else _true])

    def opened(self, bid: str, node: str) -> Rule:
        """What crossing a barrier from ``node`` (a canonical node, §4.1), or
        its contents or an event it is required for at ``node``, needs: its
        flag when it stays destroyed. When it respawns it is destroyed where
        the player stands (plan §2.4): its destroy requirement and the light
        there, at a node of its destroy_from only; in logic only when every
        respawn mechanism is harmless, physically always."""
        o = self.db.hand[bid][2]
        if self.logic.persist(o) == "permanent":
            return _flag(bid + ".destroyed")
        froms = {self.logic.canon(n) for n in o.get("destroy_from", [])}
        if not (self.physical or self.logic.harmless("respawn")) or node not in froms:
            return _false
        return self.destroy_at(bid, node)

    def passes(self, bid: str, a: str, b: str) -> Rule:
        """Crossing a barrier from a to b: opened from a, or its bypass a->b
        (one way, no flag)."""
        bypass = self.db.hand[bid][2].get("bypass", {}).get(f"{a}->{b}")
        return _any([self.opened(bid, self.logic.canon(a) if a else ""), self.expr(bypass) if bypass else _false])

    def button(self, bid: str) -> Rule:
        """A button's requirement: the generated one (or its override) and the
        hand one; in logic, a lock that uses its key up needs its worst-case
        count, less the refund keys still on their spots (``Logic.keys``;
        physically, one key opens it)."""
        o = self.db.hand[bid][2]
        bump = None if self.physical else self.logic.keys.get(bid)
        return _all([self.expr(self.base(o), bump), self.expr(o.get("requires", "true"))])

    def gate(self, gid: str) -> Rule:
        """§5.6: one atom per generated gate in a location's gated_by: a
        geode's damage, else the hand object bound to the gate (an obsidian
        lock's button, a keylord's or boss's event); none bound is false."""
        lvl, kind, o = self.db.generated_objects[gid]
        if kind == "geodes":
            return self.expr(o["requires"]) if o["requires"] is not None else _false
        bound = self.logic.bound.get(gid)
        if bound is None:
            return _false
        return _flag(bound + ".open" if kind == "obsidian_locks" else bound)

    def edge(self, lvl: str, e: Mapping) -> tuple[str, str, Rule] | None:
        """An edge as (from, to, rule), or None. In logic: not ``logic =
        false``, not a cart whose lock isn't harmless, its difficulty from 1
        up to the movement tier's number, and its ``assumes`` flags
        credited. Physically: every edge, ``assumes`` ignored. Never one
        that is open-ended or inside one stub."""
        lg = self.logic
        if not self.physical and not (
                e.get("logic", True) and (e["kind"] != "cart" or lg.handling.get(e["lock"]) == "harmless")
                and 1 <= e.get("difficulty", 1) <= self.tier):
            return None
        if not e["to"]:
            return None
        a, b = lg.canon(e["from"]) if e["from"] else lvl, lg.canon(e["to"])
        if a == b:
            return None
        return a, b, _all([self.expr(e.get("requires", "true")),
                           *(self.passes(x, e["from"], e["to"]) for x in e.get("through", [])),
                           *(_flag(x) for x in (() if self.physical else e.get("assumes", ()))),
                           self.light(e.get("dark", False))])


@dataclass
class _Round:
    """One sphere's state, as the escape closures read it."""
    counters: dict
    held: collections.Counter
    got: set               # the locations collected
    safe: set              # the canonical nodes known safe


@dataclass(frozen=True)
class Sphere:
    """One round of the reach that collects something (``reach``'s
    ``trace``): the locations it collects, the state it read (counters,
    items held, flags credited and the locations collected before it), and
    the traps (canonical nodes) at that state and at the states of the
    rounds since the last sphere that collected nothing, with the
    trick-free ones."""
    locations: tuple[str, ...]
    counters: dict
    held: collections.Counter
    flags: frozenset[str]
    got: frozenset[str]
    traps: frozenset[str] = frozenset()
    free_traps: frozenset[str] = frozenset()


class Logic:
    """A database compiled for the solver. Build it once per database."""

    def __init__(self, db):
        self.db = db
        self._compiled: dict[tuple, _Rules] = {}
        self.items = {it["name"]: dict(it["counters"]) for it in db.items["item"]}
        self.skip_tables = {sid: s for sid, (_, s) in db.skips.items()}
        self.handling = {m["id"]: m["handling"] for m in db.world["mechanism"]}
        self.kinds = collections.defaultdict(set)
        for m in db.world["mechanism"]:
            self.kinds[m["kind"]].add(m["handling"])
        self.stub_nodes = collections.defaultdict(list)
        for nid, (lvl, _) in sorted(db.nodes.items()):
            if lvl in db.stubs:
                self.stub_nodes[lvl].append(nid)
        self.pool: dict[str, str] = {}
        self.vanilla: dict[str, tuple[str, int]] = {}
        self.gated_by: dict[str, list[str]] = {}
        for lvl, doc in db.generated.items():
            for loc in doc["locations"]:
                if loc["pool"]:
                    self.pool[loc["id"]] = lvl
                    y = loc.get("yield")
                    self.vanilla[loc["id"]] = (loc["item"], y if isinstance(y, int) and y > 0 else 1)
                    self.gated_by[loc["id"]] = loc.get("gated_by", [])
        self.location_rows = {o["id"]: o for doc in db.levels.values() for o in doc["location"]}
        self.contained_by: dict[str, list[str]] = collections.defaultdict(list)
        self.required_for: dict[str, list[str]] = collections.defaultdict(list)
        self.bound: dict[str, str] = {}
        for oid, (_, kind, o) in sorted(db.hand.items()):
            for x in o.get("contains", []) if kind == "barrier" else ():
                self.contained_by[x].append(oid)
            for x in o.get("required_for", []) if kind == "barrier" else ():
                self.required_for[x].append(oid)
            if kind != "barrier" and "of" in o:     # the button or event bound to a generated gate
                self.bound[o["of"]] = oid
        self.start = self.canon(db.world["start"])
        self.everything = dict.fromkeys(set(db.counters) | {c for t in self.items.values() for c in t}, _ALL)
        self.slots = {disc: loc["id"] for doc in db.generated.values() for loc in doc["locations"]
                      if loc["pool"] and loc.get("guardian_slot") for disc, c in DISCS.items()
                      if c in self.items[loc["item"]]}
        self.guardian = frozenset(self.slots.values())    # D81: each keeps its vanilla 4th fragment
        keys = {name for name, cs in self.items.items() if any(c.startswith("key.") for c in cs)}
        # the spots that only ever give their vanilla item: a stub's, and those the fill keeps on it (a guardian
        # slot, a key's spot, an unbounded generator)
        self.prefilled = frozenset(loc["id"] for lvl, doc in db.generated.items() for loc in doc["locations"]
                                   if loc["pool"] and (lvl in db.stubs or loc["id"] in self.guardian
                                                       or loc["item"] in keys or loc.get("unbounded")))
        self.refund: dict[str, tuple[str, str]] = {}    # a refund key's location -> (its key counter, pending counter)
        self.keys: dict[str, tuple[str, int, tuple[str, ...]]] = self._key_counts()   # before the logic graphs
        self.everything.update(dict.fromkeys((p for _, p in self.refund.values()), 1))   # every refund key on its spot
        free = self.rules(TRICK_FREE)
        self.forced = self._forced_on_entry(free)
        self.forced_phys = self._forced_on_entry(self.rules(TRICK_FREE, physical=True))
        self.regions = self._regions(free)
        lost = set().union(*self.regions.values())
        self.forfeitable = frozenset(loc for loc, lvl in self.pool.items() if lvl not in db.stubs
                                     and loc not in self.guardian and self.canon(db.node_of[loc]) in lost)
        self._inside: dict[tuple, dict] = {}      # within's graphs by level and rules
        self._kit_memo: dict[tuple, set[str]] = {}   # kit_short's reaches: (options, counter, count, spot, item)

    def rules(self, settings: Settings, physical: bool = False) -> _Rules:
        """One option set's compiled graph (the physical one when
        ``physical``), compiled once: the fill reaches many placements under
        the same options."""
        key = (settings.skip_ceiling, settings.movement_tier, settings.dark_fire,
               tuple(sorted(settings.skip_override.items())), physical)
        if key not in self._compiled:
            self._compiled[key] = _Rules(self, settings, physical)
        return self._compiled[key]

    def harmless(self, kind: str) -> bool:
        """§3.1: a non-monotone mechanism is modelled in logic only when every
        declaration of its kind says the data proves it harmless."""
        return self.kinds.get(kind) == {"harmless"}

    def canon(self, node: str) -> str:
        """A stub level is one node (§4.1), named by its level."""
        lvl = self.db.nodes[node][0]
        return lvl if lvl in self.db.stubs else node

    def generated(self, o: Mapping) -> Mapping:
        return self.db.generated_objects[o["of"]][2] if "of" in o else {}

    def persist(self, o: Mapping) -> str:
        return o.get("persist", self.generated(o).get("persist", "permanent"))

    def _key_counts(self) -> dict[str, tuple[str, int, tuple[str, ...]]]:
        """§2.6, §5.5: a lock that uses its key up needs one more key for
        each other lock of its type a player could open without passing it,
        counted once from R_phys (plan §2.10, §2.13) with every item, every
        in-logic skip and this lock never pressed. A stub's locks are pressed
        free (§4.1), so they spend no key and count for no other lock.

        The key rule (AZ-345): another lock spends no key of this one's when
        a key spent there is given back on the spot, that is, when a key of
        its type lies on every way to it (:meth:`_given_back`), each such lock
        matched to its own key. Each matched key still on its spot counts as
        held (its pending counter, :attr:`refund`): {lock: (key counter, the
        other locks, the pending counters)}."""
        locks = {}
        for bid, (lvl, kind, o) in self.db.hand.items():
            gen = self.generated(o) if kind == "button" else {}
            if gen.get("coded") and isinstance(gen.get("consumes"), str) and lvl not in self.db.stubs:
                locks[bid] = gen["consumes"]
        rules, out = self.rules(MAX_SETTINGS, physical=True), {}
        found = {key: [loc for loc, lvl in sorted(self.pool.items()) if lvl not in self.db.stubs
                       and self.items[self.vanilla[loc][0]].get(key, 0) > 0] for key in set(locks.values())}
        edges = collections.defaultdict(list)       # the physical edges with their requirement: a -> [(b, rule, ast)]
        for lvl in sorted(self.db.levels):
            for e in self.db.levels[lvl]["edge"]:
                if edge := rules.edge(lvl, e):
                    edges[edge[0]].append((edge[1], edge[2], parse(e.get("requires", "true"))))
        for bid, key in sorted(locks.items()):
            flags = self._closure(rules, self.everything, (), never=bid + ".open")[1]
            others = [o for o, k in sorted(locks.items()) if o != bid and k == key and o + ".open" in flags]
            radj = collections.defaultdict(list)    # the edges passable here, reversed
            for a, outs in edges.items():
                for b, rule, _ in outs:
                    if rule(self.everything, flags):
                        radj[b].append(a)
            owner = _matching({o: [loc for loc in found[key] if self._given_back(edges, radj, flags, loc, o)]
                               for o in others})
            for loc in owner:
                self.refund.setdefault(loc, (key, f"{key}@{loc}"))
            out[bid] = (key, len(others), tuple(sorted(self.refund[loc][1] for loc in owner)))
        return out

    def _given_back(self, edges: Mapping, radj: Mapping, flags: Container[str], loc: str, lock: str) -> bool:
        """The key rule's test (AZ-345): the key at pool location ``loc`` is
        taken on every way to ``lock``'s node in R_phys (``edges``, with every
        item and ``flags``): every path from the start to the lock passes its
        node, and every edge that leaves that node toward the lock without
        coming back asks at least the location's requirement (each of its
        conjuncts, a counter at least as high), so whoever reaches the lock
        stood at the key's node able to take it. The location has no gate,
        container or dark node of its own."""
        node, at = self.canon(self.db.node_of[loc]), self.canon(self.db.hand[lock][2]["at"])
        if self.gated_by[loc] or self.contained_by.get(loc) or self.db.nodes[node][1].get("dark", False):
            return False

        def conj(a: tuple) -> list[tuple]:
            return [x for y in a[1] for x in conj(y)] if a[0] == "and" else [] if a == ("const", True) else [a]
        need = conj(parse(self.location_rows.get(loc, {}).get("requires", "true")))
        if at == node:
            return not need
        back, todo = {at}, [at]                     # the nodes that reach the lock without passing the key's node
        while todo:
            for a in radj.get(todo.pop(), ()):
                if a not in back and a != node:
                    back.add(a)
                    todo.append(a)
        if self.start in back:
            return False
        return all(any(h == q or h[0] == q[0] == "counter" and h[1] == q[1] and h[2] >= q[2] for h in conj(ast))
                   for b, rule, ast in edges[node] if b in back and rule(self.everything, flags) for q in need)

    def _forced_on_entry(self, rules: _Rules) -> dict[str, frozenset[str]]:
        """Plan §2.13: the flags forced on entry to each node, those no way
        into it can do without, on ``rules`` (skip-free: the logic graph at
        every player tier for Safe, the physical one for the traps). A node
        is forced the flag f when, with every item, it can't be reached
        while f is never credited (the whole path read, its requirements,
        crossings and, in logic, ``assumes``, so a room behind a lock is
        forced the lock's flag even when an edge comes back into it from
        further in). Every flag the reach credits is tried, so neither an
        ``|``'s operand order nor a flag read only by another flag's
        requirement hides one. Read once, so it depends on neither the state
        nor the options; a skip into a node isn't a way in here (the escape
        takes these flags only once credited)."""
        reached, credited = self._closure(rules, self.everything, ())
        forced = collections.defaultdict(set)
        for f in sorted(credited):
            for n in reached - self._closure(rules, self.everything, (), never=f)[0]:
                forced[n].add(f)
        return {n: frozenset(fs) for n, fs in forced.items()}

    def _regions(self, rules: _Rules) -> dict[str, frozenset[str]]:
        """Plan §2.9: each disc's no-return region, the nodes that, on
        ``rules`` (skip-free, every player tier's edge), with every item and
        every flag the reach credits, the start reaches and that get back to
        it only by a disc teleport (none is an edge of the graph), and that
        reach that disc's teleport. Read once, like the flags forced on
        entry."""
        reached, flags = self._closure(rules, self.everything, ())
        home = self._bfs(rules, [self.start], self.everything, flags, rules.radj)
        regions = collections.defaultdict(set)
        for a, _, _, disc in rules.teleports:
            regions[disc] |= self._bfs(rules, [a], self.everything, flags, rules.radj) & (reached - home)
        return {disc: frozenset(nodes) for disc, nodes in regions.items() if nodes}

    def reads(self, settings: Settings) -> dict[str, frozenset[int]]:
        """The counters the logic under ``settings`` reads, each with the
        thresholds it compares it with: an item none of whose counters is
        here never changes the reach (the fill, Step R1.9)."""
        return {c: frozenset(ns) for c, ns in sorted(self.rules(settings).reads.items())}

    def within(self, level: str, sources: Iterable[str], counters: Mapping[str, int],
               flags: Iterable[str], settings: Settings | None = None) -> set[str]:
        """The nodes of ``level`` (an authored level) reached from ``sources``
        (its nodes) without leaving it, under ``settings`` (default: the
        database's default options), with ``counters`` held, ``flags`` credited and the flags credited
        wherever it gets (a barrier destroyed, a button pressed): what the
        GUI's maps ask of each exit (AZ-341). It takes no location, so every
        refund key lies on its spot (keys are vanilla in v1; AZ-345) unless
        ``counters`` says otherwise."""
        counters = {**dict.fromkeys((p for _, p in self.refund.values()), 1), **counters}
        rules = self.rules(settings or self.db.defaults)
        if (level, id(rules)) not in self._inside:
            inside = {n for n, (lvl, _) in self.db.nodes.items() if lvl == level}
            self._inside[level, id(rules)] = {u: [(v, r) for v, r in rules.adj.get(u, ()) if v in inside]
                                              for u in inside}
        adj = self._inside[level, id(rules)]
        flags = set(flags)
        while True:
            seen = self._bfs(rules, list(sources), counters, flags, adj)
            new = [f for f, n, _, rule in rules.credits if f not in flags and n in seen and rule(counters, flags)]
            if not new:
                return seen
            flags.update(new)

    def vanilla_placement(self) -> dict[str, str]:
        """Each authored level's pool location with its vanilla item (a stub's
        always hold theirs, §4.1)."""
        return {loc: self.vanilla[loc][0] for loc, lvl in sorted(self.pool.items()) if lvl not in self.db.stubs}

    @staticmethod
    def _bfs(rules: _Rules, sources: Iterable[str], counters: Mapping, flags: Container[str],
             adj: Mapping | None = None) -> set[str]:
        """The nodes reached from ``sources`` over ``adj`` (the rules' edges;
        their reverse, ``radj``, searches backward)."""
        adj = rules.adj if adj is None else adj
        seen, todo = set(sources), collections.deque(sources)
        while todo:
            for v, rule in adj.get(todo.popleft(), ()):
                if v not in seen and rule(counters, flags):
                    seen.add(v)
                    todo.append(v)
        return seen

    def _closure(self, rules: _Rules, counters: Mapping, flags: Iterable[str],
                 never: str | None = None) -> tuple[set[str], set[str]]:
        """With fixed counters, the nodes reached from the start and the flags
        credited wherever they are reached, as a fixpoint, the flag ``never``
        never credited: R_phys on the physical graph, and the key counts'
        and the forced flags' reaches."""
        flags = set(flags)
        while True:
            seen = self._bfs(rules, [self.start], counters, flags)
            new = [f for f, node, _, rule in rules.credits
                   if f not in flags and f != never and node in seen and rule(counters, flags)]
            if not new:
                return seen, flags
            flags.update(new)

    def _item(self, loc: str, placement: Mapping) -> str | None:
        """What a location gives: a stub's or a guardian slot's its vanilla
        item, a forfeitable one nothing (D81), any other what the placement
        put there (None: empty, adds nothing)."""
        if self.pool[loc] in self.db.stubs or loc in self.guardian:
            return self.vanilla[loc][0]
        return None if loc in self.forfeitable else placement.get(loc)

    def _take(self, held: collections.Counter, counters: dict, loc: str, placement: Mapping) -> None:
        """Collect pool location ``loc``: add what it gives (:meth:`_item`).
        A refund key taken off its spot is held now, so its pending counter
        goes (AZ-345)."""
        if (name := self._item(loc, placement)) is None:
            return
        self._add(held, counters, name, self.vanilla[loc][1])
        key, pending = self.refund.get(loc, (None, None))
        if self.items[name].get(key, 0) > 0 and counters.get(pending, 0) > 0:
            counters[pending] -= 1

    def _pending(self, counters: dict, placement: Mapping, got: Container[str]) -> None:
        """Each refund key the placement puts on its spot and not yet
        collected counts as held for the locks it refunds (AZ-345)."""
        for loc, (key, pending) in self.refund.items():
            if loc not in got and (name := self._item(loc, placement)) and self.items[name].get(key, 0) > 0:
                counters[pending] = max(counters.get(pending, 0), 1)

    def _add(self, held: collections.Counter, counters: dict, name: str, n: int) -> None:
        """Add n copies of an item. A disc counter counts distinct fragments
        (§2.1: a second copy of a fragment fills no new slot)."""
        first = held[name] == 0
        held[name] += n
        for c, inc in self.items[name].items():
            counters[c] = counters.get(c, 0) + (inc * first if c.startswith("disc") else inc * n)

    def _escape(self, rules: _Rules, rnd: _Round, node: str, placement: Mapping,
                flags: Iterable[str]) -> tuple[bool, set[str], set[str], dict]:
        """Plan §2.13 rules 1-3 and §2.9's one shot: the local closure from
        ``node`` on ``rules`` (the logic graph for Safe, the physical one for
        a trap). It starts with the items held and ``flags`` (those credited
        from the start and the node's forced flags that are credited in
        logic for Safe, or physically settable for a trap: a node a skip
        alone gets into isn't safe by the flags its other ways in set); it
        collects the locations not yet collected and credits the flags whose
        requirement holds wherever it gets (the empty spots add nothing),
        takes a disc teleport whose slot was not collected before (the disc
        not yet placed) once its requirement holds, and holds once it
        reaches the start. Returns that, the nodes seen, the flags and the
        counters."""
        counters, held, flags, took = dict(rnd.counters), collections.Counter(rnd.held), set(flags), set(rnd.got)
        sources = [node]
        while True:
            seen = self._bfs(rules, sources, counters, flags)
            if self.start in seen:
                return True, seen, flags, counters
            jumps = [b for a, b, rule, disc in rules.teleports if a in seen and b not in seen
                     and self.slots[disc] not in rnd.got and rule(counters, flags)]
            locs = [loc for loc, n, rule in rules.locations if loc not in took and n in seen and rule(counters, flags)]
            new = [f for f, n, _, rule in rules.credits if f not in flags and n in seen and rule(counters, flags)]
            if not (jumps or locs or new):
                return False, seen, flags, counters
            sources += jumps
            for loc in locs:
                took.add(loc)
                self._take(held, counters, loc, placement)
            flags.update(new)

    def _returners(self, rules: _Rules, counters: Mapping, base: frozenset[str]) -> set[str]:
        """Plan §2.13's fast path: the nodes a backward search from the start
        finds when an edge is passable on the items held, ``base`` and the
        flags its own source node can set on them (a barrier destroyed from
        that side, a button pressed there). Each one's escape holds (its
        closure takes the same path), so it needs no closure."""
        local = collections.defaultdict(set)
        for f, n, _, rule in rules.credits:
            if f not in base and rule(counters, base):
                local[n].add(f)
        at = {n: base | fs for n, fs in local.items()}
        seen, todo = {self.start}, collections.deque([self.start])
        while todo:
            for u, rule in rules.radj.get(todo.popleft(), ()):
                if u not in seen and rule(counters, at.get(u, base)):
                    seen.add(u)
                    todo.append(u)
        return seen

    def _escaping(self, rules: _Rules, rnd: _Round, nodes: set[str], placement: Mapping, base: frozenset[str],
                  forced: Mapping[str, frozenset[str]], credited: Container[str]) -> set[str]:
        """Those of ``nodes`` whose escape on ``rules`` holds at this round's
        state, each starting with ``base`` and its ``forced`` flags that are
        ``credited``: the fast path's need no closure, and a closure that
        fails fails every node it saw whose starting flags it held, since
        their closures are inside its own (the cache: the round's counters
        are fixed)."""
        if not nodes:
            return set()
        home = self._returners(rules, rnd.counters, base)
        out, dead = nodes & home, set()
        for n in sorted(nodes - home):
            if n in dead:
                continue
            ok, seen, flags, _ = self._escape(rules, rnd, n, placement, base | (forced.get(n, frozenset()) & credited))
            if ok:
                out.add(n)
            else:
                dead.update(m for m in seen if forced.get(m, frozenset()) & credited <= flags)
        return out

    def _solve(self, settings: Settings, placement: Mapping, counters: dict, held: collections.Counter,
               flags: Iterable[str], trace: list | None = None, traps_too: bool = True,
               got: Iterable[str] | None = None, late: frozenset[str] = frozenset(),
               ) -> tuple[set, set, set, set, set, set, set, bool, set]:
        rules, phys_rules = self.rules(settings), self.rules(settings, physical=True)
        free_rules = self.rules(TRICK_FREE, physical=True) if phys_rules.on else phys_rules
        base, flags = frozenset(flags), set(flags)
        rnd = _Round(counters, held, set(got or ()), {self.start})
        self._pending(counters, placement, rnd.got)
        rnd.got -= late             # collected from the round that reaches it (``reach``'s ``replay``)
        now: set[str] = set()       # with ``got``: the locations reached, never collected
        traps: set[str] = set()
        free: set[str] = set()
        pending: tuple[set, set] = (set(), set())    # the traps of the rounds since the last sphere
        while True:
            reached = self._bfs(rules, [self.start], counters, flags)
            rnd.safe |= self._escaping(rules, rnd, reached - rnd.safe, placement, base, self.forced, flags)
            phys, settable = self._closure(phys_rules, counters, flags) if traps_too else (set(), set())
            maybe = phys - rnd.safe
            found = maybe - self._escaping(phys_rules, rnd, maybe, placement, base, self.forced_phys, settable)
            walked = found if free_rules is phys_rules or not found else \
                found & self._closure(free_rules, counters, flags)[0]
            traps |= found
            free |= walked
            pending[0].update(found)
            pending[1].update(walked)
            locs = [loc for loc, n, rule in rules.locations
                    if loc not in rnd.got and loc not in now and n in rnd.safe and rule(counters, flags)]
            new = [f for f, n, terminal, rule in rules.credits if f not in flags
                   and (n in rnd.safe or terminal and n in reached) and rule(counters, flags)]
            if not (locs or new):
                rnd.got |= late
                after = {n for disc, slot in self.slots.items() if slot in rnd.got
                         for n in self.regions.get(disc, ()) if n in phys}
                return (reached, rnd.safe, phys, traps, after, rnd.got | now, flags, rules.victory(counters, flags),
                        free)
            if got is not None:
                rnd.got.update(late.intersection(locs))
                now.update(locs)
                flags.update(new)
                continue
            if trace is not None and locs:
                trace.append(Sphere(tuple(locs), dict(counters), collections.Counter(held), frozenset(flags),
                                    frozenset(rnd.got), frozenset(pending[0]), frozenset(pending[1])))
                pending = (set(), set())
            for loc in locs:
                rnd.got.add(loc)
                self._take(held, counters, loc, placement)
            flags.update(new)

    def anchored(self) -> bool:
        """Rule 10 (plan §2.13 rule 1): with every item, under the strictest
        options (no skip, the safe tier), the hub is safe: the start reaches
        it and it gets back to the start. The reach being monotone, it then
        holds under any options."""
        safe = self._solve(STRICTEST, {}, dict(self.everything), collections.Counter(), ())[1]
        return self.canon(self.db.world["hub"]) in safe

    def route_walks(self, only: Container[str] | None = None) -> dict[str, tuple[int, dict, dict]]:
        """D169: {location: (the route step that collects it, the counters
        it holds going in, those leaving)} for each route location step that
        replayed ok (``only``: those locations alone). The route's kit at a
        step is what its earlier steps collected (each one's vanilla item; a
        key an action uses up taken off), and the step leaves holding that
        and the spot's vanilla item."""
        db = self.db
        held, kit, steps = collections.Counter(), {}, {}
        for s in (db.route or {}).get("step", ()):
            if s["kind"] == "action":
                if "consumes" in s:
                    kit[s["consumes"]] = kit.get(s["consumes"], 0) - 1
                continue
            if s["item"] not in self.items:      # an open step of a draft route: the kits after it are unknown
                break
            before = dict(kit)
            self._add(held, kit, s["item"], self.vanilla.get(s["id"], (None, 1))[1])
            if s["ok"] and self.pool.get(s["id"]) not in (None, *db.stubs) and (only is None or s["id"] in only):
                steps[s["id"]] = (s["step"], before, dict(kit))
        return steps

    def mark_short(self, loc: str, pv: Mapping, walk: tuple[int, Mapping, Mapping] | None) -> str | None:
        """D169 (toward D157): why the by-route mark ``pv`` on pool location
        ``loc`` is no proof, else None. ``walk`` is its :meth:`route_walks`
        entry, and the spot is proven when :meth:`kit_short` finds no kit the
        logic collects it with that holds less: under the most lenient
        options with the mark's ``unless`` picks off, and with them on for
        each of its ``only`` items (AZ-725, :meth:`route_terms`)."""
        if walk is None:
            return "route.toml collects it at no step that replayed ok"
        unless, only = pv.get("unless", []), pv.get("only", [])
        picks = {pick_of(s, self.skip_tables) for s in skips_on(MAX_SETTINGS, self.skip_tables)}
        if bad := sorted(set(unless) - picks):
            return f"its unless names no in-logic skip's pick: {', '.join(bad)}"
        if bad := sorted(set(only) - {it["name"] for it in self.db.items["item"] if it["class"] == "progression"}):
            return f"its only names no progression item: {', '.join(bad)}"
        step, kin, kout = walk
        bad = self.kit_short(loc, kin, kout, self.without(unless))
        for x in only if not bad else ():
            if bad := self.kit_short(loc, kin, kout, items=(x,)):
                break
        return bad and (f"{bad[1]}; route.toml step {step} holds {bad[0]} {kin.get(bad[0], 0)} going in "
                        f"and {kout.get(bad[0], 0)} leaving")

    def without(self, picks: Iterable[str]) -> Settings:
        """The most lenient options with ``picks`` (D275's: a batch's id or a
        lone skip's) toggled off."""
        return Settings(MAX_SETTINGS.skip_ceiling, MAX_SETTINGS.movement_tier, MAX_SETTINGS.dark_fire,
                        dict.fromkeys(picks, False))

    def route_terms(self, loc: str, kin: Mapping[str, int],
                    kout: Mapping[str, int]) -> tuple[list[str], list[str]] | None:
        """AZ-725 (D169 under the options): for a route walk to ``loc`` that
        :meth:`kit_short` refuses under the most lenient options, the mark's
        ``unless`` and ``only``: the picks whose skips it needs off (the
        fewest a deletion over them in order keeps), and the progression
        items it still holds for with all of them on (an item whose counts
        give the walk's own way out); None when it fails with every skip off
        too. So a skip changes no mark below its own tier."""
        picks = sorted({pick_of(sid, self.skip_tables) for sid in skips_on(MAX_SETTINGS, self.skip_tables)})
        if self.kit_short(loc, kin, kout, self.without(picks)):
            return None
        unless = list(picks)
        for p in picks:
            if not self.kit_short(loc, kin, kout, self.without(rest := [q for q in unless if q != p])):
                unless = rest
        prog = sorted(it["name"] for it in self.db.items["item"] if it["class"] == "progression")
        return unless, [x for x in prog if not self.kit_short(loc, kin, kout, items=(x,))]

    def kit_short(self, loc: str, kin: Mapping[str, int], kout: Mapping[str, int] | None = None,
                  settings: Settings = MAX_SETTINGS, items: Iterable[str] | None = None) -> tuple[str, str] | None:
        """Whether a walk that reached pool location ``loc`` holding the
        counters ``kin`` and left it holding ``kout`` (by default ``kin`` and
        the spot's vanilla item: an L3 string from a new game holding its
        kit, AZ-543) did whatever the logic lets the fill do there with no
        more (D169): None when the logic never collects it holding less than
        ``kin`` on the way in, or less than ``kout`` on the way out (its
        escape picks up whatever progression item is put there), else (the
        counter, why). It is checked under ``settings``, by default the most
        lenient options (every in-logic skip, every movement tier: a mark
        holds whatever the user sets; a route mark may hold only with some
        skips off, AZ-725: :meth:`route_terms`), with ``items`` the only
        progression items the spot may hold (default: any), one counter at
        a time and in the logic's own bands (a count
        matters only at the thresholds the logic compares it with): every
        other counter in full, this one a band below the walk's, the spot
        empty (one reach serves every spot), then holding each progression
        item's count of it. By monotonicity (D113) those are the only kits to
        try. A prefilled spot is checked too (AZ-345's give-back reads the
        same location requirement), holding its own item alone: no other is
        ever put there."""
        if kout is None:
            kout = dict(kin)
            self._add(collections.Counter(), kout, *self.vanilla[loc])
        st, memo = settings, self._kit_memo
        reads, opts = self.reads(st), (st.skip_ceiling, st.movement_tier, st.dark_fire,
                                       tuple(sorted(st.skip_override.items())))
        every = {it["name"]: self.items[it["name"]] for it in self.db.items["item"] if it["class"] == "progression"}
        prog = every if items is None else {name: every[name] for name in items}
        if loc in self.prefilled:
            prog = {(van := self.vanilla[loc][0]): self.items[van]}
            every = prog

        def collects(c: str, h: int, item: str | None = None) -> bool:
            key = (opts, c, h, loc if item else None, item)
            if key not in memo:
                counters = dict(self.everything)
                counters[c] = h
                memo[key] = self._solve(st, {loc: item} if item else {}, counters, collections.Counter(), (),
                                        traps_too=False)[5]
            return loc in memo[key]

        tests = []      # (c, h, p): with c at h, every other counter in full and p of c on the spot, no collect
        for c in sorted(reads):
            fin, fout = _band(reads[c], kin.get(c, 0)), _band(reads[c], kout.get(c, 0))
            worst = {}
            for p in sorted({cs.get(c, 0) for cs in prog.values()}):
                if (h := max(fin - 1, fout - 1 - p)) >= 0:
                    worst[h] = p        # at one h, the largest p is the most lenient
            tests += [(c, h, p) for h, p in sorted(worst.items())]
        top = {c: h for c, h, _ in tests}
        bad = next(((c, h, None) for c, h in top.items() if collects(c, h)), None)
        for c, h, p in tests if bad is None else ():
            item = min(name for name, cs in every.items() if cs.get(c, 0) == p)   # one reach serves every such item
            if collects(c, h, item):
                bad = (c, h, item)
                break
        if bad is None:
            return None
        c, h, item = bad
        return c, f"the logic collects it holding {c} {h} (every other counter in full) with {item or 'nothing'} on it"

    def use_short(self, kit: Mapping[str, int], *, edge: tuple[str, Mapping] | None = None,
                  skip: str | None = None) -> tuple[str, str] | None:
        """Whether a string that crossed an edge (``edge``: its level and its
        row) or made a skip (``skip``: its id) holding the counters ``kit``
        (an L3 record's, AZ-544) did whatever the logic lets the fill do
        with it with no more (D169, as :meth:`kit_short` holds a spot):
        None when its own rule (an edge's requires, barriers, assumes and
        light; a skip's options and requires), which every use of it reads,
        an escape's too, never holds with a counter a band below the kit's,
        every other counter in full and every flag credited, under the most
        lenient options; else (the counter, why)."""
        rules = self.rules(MAX_SETTINGS)
        rule = rules.skip(skip) if skip is not None else got[2] if (got := rules.edge(*edge)) else _false
        reads = self.reads(MAX_SETTINGS)
        for c in sorted(reads):
            if (h := _band(reads[c], kit.get(c, 0)) - 1) >= 0 and rule({**self.everything, c: h}, _EveryFlag()):
                return c, f"the logic uses it holding {c} {h} (every other counter in full, every flag credited)"
        return None

    def reach(self, settings: Settings | None = None, placement: Mapping[str, str | None] | None = None,
              items: Iterable[str] = (), flags: Iterable[str] = (), trace: list | None = None,
              traps: bool = True, collected: Iterable[str] | None = None, replay: bool = False) -> Reach:
        """The fixpoint under ``settings`` (the database's defaults when None),
        with ``placement`` (pool location -> item name, or None for empty;
        an authored level's location it doesn't name is empty; vanilla when
        None), ``items`` held from the start (the world's starting items are
        added) and ``flags`` credited from the start (they count toward
        every escape). A ``trace`` list gets each round that collects
        something, as a :class:`Sphere` (the spoiler's spheres). With
        ``traps`` false, R_phys, the traps and the traps after completion
        aren't computed (they are empty): the fill reads only the
        locations. With ``collected`` (the tracker, D189), the reach now of a
        player who has collected exactly those pool locations: their items
        are held, no other location's item is, and ``locations`` is what is
        reachable now, those among it. With ``replay`` too (the tracker,
        AZ-430, and the fill's trap-gate repair, AZ-431), a collected guardian
        slot counts as collected only from the round that reaches it, as a
        player places the disc after beating its boss: what its one-shot
        teleport got back with stays credited (the boss's flag, and a3, a5
        and the airship behind w3's); without it every one is collected from
        the start."""
        db = self.db
        st = settings if settings is not None else db.defaults
        settings_from_table({"format": SETTINGS_FORMAT, "skip_ceiling": st.skip_ceiling,
                             "movement_tier": st.movement_tier, "dark_fire": st.dark_fire,
                             "skip_override": dict(st.skip_override)}, self.skip_tables, "solver settings")
        placement = self.vanilla_placement() if placement is None else placement
        for loc, item in placement.items():
            if loc not in self.pool or self.pool[loc] in db.stubs:
                raise SolverError(f"placement: {loc} is no pool location of an authored level")
            if item is not None and item not in self.items:
                raise SolverError(f"placement: {loc} holds {item!r}, which items.toml doesn't define")
            if loc in self.guardian and item != self.vanilla[loc][0]:
                raise SolverError(f"placement: {loc} is a guardian slot, which keeps its {self.vanilla[loc][0]} (D81)")
        held, counters = collections.Counter(), {}
        for name in [*db.world["starting_items"], *items]:
            if name not in self.items:
                raise SolverError(f"items: {name!r} is no item of items.toml")
            self._add(held, counters, name, 1)
        flags = set(flags)
        if flags - db.flags:
            raise SolverError(f"flags: {sorted(flags - db.flags)} are no flags of the database")
        if collected is not None:
            collected = set(collected)
            if collected - self.pool.keys():
                raise SolverError(f"collected: {sorted(collected - self.pool.keys())} are no pool locations")
            for loc in sorted(collected):
                self._take(held, counters, loc, placement)
        late = frozenset(collected) & self.guardian if replay and collected is not None else frozenset()
        reached, safe, phys, found, after, got, flags, victory, free = self._solve(st, placement, counters, held,
                                                                                  flags, trace, traps, collected, late)

        def nodes(keys: Iterable[str]) -> frozenset[str]:
            return frozenset(n for key in keys for n in (self.stub_nodes[key] if key in db.stubs else [key]))

        return Reach(nodes(reached), nodes(safe), nodes(phys), nodes(found), nodes(after), frozenset(got),
                     frozenset(flags), victory, nodes(free))
