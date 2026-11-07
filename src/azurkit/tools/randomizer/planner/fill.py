"""The fill (RANDOMIZER_PLAN §3.3, §3.5; Step R1.9): a seed and D144's
options in, a verified placement of every authored level's pool location
out (a stub keeps its vanilla items, docs/RANDOMIZER_DB.md §4.1, so the
fill covers the realms authored so far and grows with them).

The passes, each drawing from its own named stream:

1. **Pre-fill** (no draw): the guardian slots keep their vanilla 4th
   fragments (D81), the keys stay vanilla (I-9: the key-slot cap), an
   unbounded generator (maxGenerated 0, town's two dispensers) keeps its
   item, since anything placed there would come back endlessly, and so
   does every location whose vanilla item's category the settings'
   ``exclude_categories`` name (Step R1.10b).
2. **Progression** (``progression``), by assumed fill: the progression
   items in a shuffled order, each removed from the assumed set (every
   unplaced item the logic reads, held from the start) and put on an
   empty spot the solver collects with the rest, which is proven (D122,
   D143), neither excluded nor forfeitable (D81) and not a vault. A spot the
   item opens by lying there comes first (Step R1.8m): one at a node the
   reach gets to but can't leave without the item, collected once it lies
   there (its escape picks it up, as vanilla's water in w2's hose pool; the
   reach without the item never collects it). An item with no spot trades
   places with one placed before it (Step R1.8m): it takes that one's spot,
   collected with it there and the other assumed, and the other goes on a
   spot of the reach with it there. Then the counted items (obsidians) as
   blocks: the reach is computed once per threshold band, with the band's
   lowest count assumed, and each copy of the band goes on a safe spot of
   that reach (a subset of each copy's own, so the assumed fill's rule
   holds). **The trap gate's repair** (Step R1.8m): the solve of that
   placement (what the later passes add is read by no logic) is checked as
   the verify checks it; when only the trap gate refuses it, the first
   sphere with new trick-free traps and the first one free of them again
   give a swap (:meth:`_Slots.repairs`: an item collected just before they
   free, the way out, for one collected last before they start, the way in,
   or for a spot at a trap when they are there from the start), the
   obsidians are placed again and it is checked again, up to
   :data:`MAX_REPAIRS` swaps; a swap that breaks the placement goes back.
3. **Useful** (``useful``): the vaults first, the most restricted spots
   (Q290: a vault, a spot an obsidian lock's force field closes, holds
   only ``power_life``, ``power_staff*`` or ``power_ammo``), then the rest,
   weighted toward major spots; each on a safe spot, as above.
4. **Filler** (``filler``): a plain random fill of what is left, by class:
   non-gem items on the non-gem spots, single gems on single-gem spots
   (D77) and each cluster on a cluster of the same yield (D78).
5. **Verify:** an independent solve of the whole placement: victory, every
   location that isn't forfeitable collected (``full``), and the trap gate
   (D83(b), plan §2.13): no trick-free trap that isn't a known one
   (:func:`known_traps`: vanilla's own under the same options, and the
   level files' ``known_traps``), the traps after completion aside.

Every pass keeps each node graph's new strings within its budget, the
writer's own numbers (:class:`~azurkit.tools.randomizer.writer.Names`,
:func:`~azurkit.tools.randomizer.writer.string_cost`), and the result passes
the writer's :func:`~azurkit.tools.randomizer.writer.layout`. An attempt that
gets stuck or fails the verify (its repairs too) is retried with the next
attempt's streams, up to 20 attempts; then :class:`FillError` names the progression items
that found no safe proven spot and the proven spots (D35), and nothing is
filled arbitrarily (AZ-161).

**The preflight** (Step R1.27, AZ-454): each progression item needs a proven
spot of its own, so settings that leave fewer proven spots open to one
(:meth:`_Slots.open_proven`, less those ``exclude_categories`` keeps
vanilla) than the progression items left to place are refused before any
attempt, by a :class:`Starved` naming the categories that hold them, the
counts and what to change in plain words (:meth:`_Slots.starved`); any other
settings fill as before. :func:`roll` finds no seed for them at once, and
the Randomizer tab says so and greys Build (:func:`starved`).

**Seed difficulty** (D1037; :mod:`.difficulty`), at a level over 0 that its
settings can shape; level 0 enters none of it. **The pin:** in the progression
pass, an item the win needs at the ladder's lowest rung (:class:`_Pin`, once a
fill) whose spots are its reach's safe ones takes one of those the most rungs of
the level's ladder miss, with the placement so far and the items still assumed,
preferring a map level that holds no pinned item yet; when no rung misses any,
today's draw. Own spots, trades, the trap gate's repairs, vaults and AZ-725's
marks stay in charge, and every attempt is verified as today. **The acceptance**
(:class:`_Accept`): each attempt that passes is a candidate; the first that
meets the promise is the plan, else, after :data:`~.difficulty.BOUND` of them or
:data:`MAX_ATTEMPTS` attempts, the highest score, the first on a tie. Attempt k
is a pure function of the seed, k, the settings digest and the database, so a
host may run those past the first at once (:data:`WIDTH` on its
:data:`BESIDE`; the planner holds no thread): the same plan at any width. D1038's optional rewards take no code of their own: the
obsidians already lie past a trick by the shaping, and the useful items all
fill the vaults (Q290).

**Streams** (plan §3.5): ``sub_seed(name)`` is the first 8 bytes of the
sha256 of ``seed``, ``name`` and :func:`settings_digest`, NUL-separated;
attempt k > 0 names its streams ``attempt<k>/<pass>``. Only
``random.Random(int).random()`` is drawn (:class:`Rng`), and every choice
iterates sorted ids, so a plan is the same in every process and on every
CPython. The database digest is no input to the streams.
"""

from __future__ import annotations

import collections
import hashlib
import json
import random
import time
import weakref
from array import array
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Protocol

from azurkit.core import native, progress
from azurkit.tools.randomizer.planner.difficulty import BOUND, NOTE, TWIN, Play, Shape, asked
from azurkit.tools.randomizer.planner.grammar import atoms, parse
from azurkit.tools.randomizer.planner.settings import (
    CATEGORIES,
    DARK_FIRE,
    NAMES,
    SEED_DIFFICULTY_FILL,
    Settings,
    category,
    category_table,
    pick_of,
    skips_on,
)
from azurkit.tools.randomizer.planner.solver import Logic, Reach, trick_free
from azurkit.tools.randomizer.writer import Names, graph_of, layout, string_cost

GENERATOR = "azurik-rando-fill/4"     # the fill's version: bumped when the same inputs give another placement
#                                       (/2, Step R1.12: the trap gate; /3, Step R1.8m: own spots, trades, repairs;
#                                       /4, Step R1.37: no progression or obsidian on an unsaved spot, AZ-467)
MAX_ATTEMPTS = 20
WIDTH: int = 1
"""A shaped fill's attempts past its first at once, beside each other on a host's :data:`BESIDE`, so the costliest
seeds' fills end sooner: the same plan at any width."""


class Beside(Protocol):
    """A host's work beside a fill's thread (the app's engine: ``azurkit.app.procpool.Beside``, on threads, which the
    engine holds none of): ``submit(fn, item)`` runs ``fn(item)`` once a worker is free, its notes cancel points once
    the fill has no more use for it; ``answer(handle)`` is that value (or raises its error) on the fill's thread, in its
    turn, ``tick`` its note meanwhile; ``again(fn, items)`` drops what runs and answers each item's; leaving it stops
    what runs at its next note."""

    def __enter__(self) -> Beside: ...

    def __exit__(self, *exc: object) -> None: ...

    def submit(self, fn: Callable[[Any], Any], item: Any) -> Any: ...

    def answer(self, handle: Any) -> Any: ...

    def again(self, fn: Callable[[Any], Any], items: Sequence) -> list: ...


BESIDE: Callable[[int, Callable[[], None]], Beside] | None = None
"""``BESIDE(width, tick)``: the host's :class:`Beside` for a shaped fill's attempts past its first; none (the site's
worker, the command line, the tests' own process): one at a time."""
MAX_REPAIRS = 8                       # the trap gate's repairs in one attempt (Step R1.8m)
VAULT_ITEMS = ("power_life", "power_staff1", "power_staff2", "power_ammo")   # Q290: the items a closed field blocks
USEFUL_MAJOR_WEIGHT = 3               # plan §3.3: useful items lean toward major spots, 3 to 1
_DIGEST_DROP = frozenset({"_meta", "note", "description",   # RANDOMIZER_DB §9: no comments, display names or hints
                          "gate_hint", "do_save", "teleport_gate", "enabled_by", "update", "input"})
_TWO53 = 1 << 53
WAIT = 0.1                            # a fill waited on: how often its waiter tells its count (a cancel point, s)
_POLL = 0.02                          # and looks for its end (s): the engine holds no threads, so no Event


class Rng:
    """One named stream: only ``random.Random(int).random()`` is drawn
    (CPython keeps its sequence across versions; plan §3.5), and the
    integer, shuffle and choice helpers are built on it."""

    def __init__(self, seed: int) -> None:
        self._random = random.Random(seed).random

    def below(self, n: int) -> int:
        """Uniform in [0, n): the draw's 53 bits, by rejection."""
        limit = _TWO53 - _TWO53 % n
        while True:
            x = int(self._random() * _TWO53)
            if x < limit:
                return x % n

    def shuffle(self, xs: list) -> list:
        for i in range(len(xs) - 1, 0, -1):
            j = self.below(i + 1)
            xs[i], xs[j] = xs[j], xs[i]
        return xs

    def choice(self, xs: Sequence):
        return xs[self.below(len(xs))]

    def weighted(self, xs: Sequence, weights: Sequence[int]):
        r = self.below(sum(weights))
        for x, w in zip(xs, weights):
            if r < w:
                return x
            r -= w
        raise AssertionError("unreachable")


def canonical(obj) -> bytes:
    """The canonical JSON every digest hashes: sorted keys, no spaces, ASCII."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def settings_table(settings: Settings) -> dict:
    """The options as a settings file holds them (RANDOMIZER_DB §7.2):
    D144's (``dark_fire`` stays, at 1: every seed's digest holds it), and ``exclude_categories`` only when it names one, so a
    setting without it keeps its digest (and both powers rows kept are
    format /1's ``powers``, so an old setting's too, Step 2.90a); a seed
    difficulty and its fill's version likewise only when over 0, so a level 0
    plan is today's, and ``save_warp`` only when on (D1154)."""
    form, kept = category_table(settings.exclude_categories)
    table = {"format": form, "skip_ceiling": settings.skip_ceiling,
             "movement_tier": settings.movement_tier, "dark_fire": DARK_FIRE,
             "skip_override": dict(sorted(settings.skip_override.items()))}
    if kept:
        table["exclude_categories"] = kept
    if settings.seed_difficulty:
        table["seed_difficulty"], table["seed_difficulty_fill"] = settings.seed_difficulty, SEED_DIFFICULTY_FILL
    if settings.save_warp:
        table["save_warp"] = True
    return table


def settings_digest(settings: Settings) -> str:
    return hashlib.sha256(canonical(settings_table(settings))).hexdigest()


def _strip(x):
    if isinstance(x, dict):
        return {k: _strip(v) for k, v in x.items() if k not in _DIGEST_DROP and not (k == "name" and "id" in x)}
    if isinstance(x, list):
        return [_strip(v) for v in x]
    return x


_DB_DIGEST: list = [None]   # the last database's digest: (a weak ref to it, the digest)


def db_digest(db) -> str:
    """Plan §3.5: the sha256 of the canonical database: what the solver and
    the fill read (the generated and level files, items, world and each
    location's node), without ``_meta``, notes, descriptions, hints or the
    display name of anything that has an id. TOML comments never load.
    Worked out once a database (read-only, as ``kept_logic`` serves it):
    each plan and each plan's first tracker view asks it."""
    from azurkit.tools.randomizer.planner.loader import VERSION
    if (kept := _DB_DIGEST[0]) is not None and kept[0]() is db:
        return kept[1]
    digest = hashlib.sha256(canonical(_strip({
        "format": VERSION, "generated": db.generated, "levels": db.levels, "items": db.items,
        "world": db.world, "node_of": db.node_of}))).hexdigest()
    _DB_DIGEST[0] = (weakref.ref(db), digest)
    return digest


def sub_seed(seed: str, name: str, settings_hex: str) -> int:
    """The named stream's seed: the first 8 bytes of sha256(seed NUL name NUL settings_digest)."""
    return int.from_bytes(hashlib.sha256(f"{seed}\0{name}\0{settings_hex}".encode()).digest()[:8], "big")


def stream(seed: str, name: str, settings_hex: str) -> Rng:
    """The named stream ``name``."""
    return Rng(sub_seed(seed, name, settings_hex))


class FillError(ValueError):
    """No verified placement (D35): ``reason``; ``items``, the progression
    items with no safe proven spot; ``proven``, the proven spots a
    progression item may take; ``attempts``, each failed attempt's reason."""

    ITEMS = "Progression items with no safe proven spot"

    def __init__(self, reason: str, items: list[str], proven: list[str], attempts: Sequence[str] = ()) -> None:
        self.reason, self.items, self.proven, self.attempts = reason, items, proven, list(attempts)
        super().__init__(
            f"no plan (D35): {reason}. {self.ITEMS} (D122, D143): "
            f"{', '.join(items) or 'none'}. The proven spots a progression item may take ({len(proven)}): "
            f"{', '.join(proven) or 'none'}")


class Starved(FillError):
    """The preflight's :class:`FillError` (Step R1.27, AZ-454): the
    settings leave fewer proven spots open than progression items, so no
    attempt is made (``attempts`` is empty). ``reason`` says why and what
    to change in the Randomizer tab's words (Step 4.4u1), ``tick`` its short
    "Tick <row>" (None when no row holds the spots); ``items``, every
    progression item the plan places, competes for ``proven``, the spots
    left."""

    def __init__(self, reason: str, tick: str | None, items: list[str], proven: list[str]) -> None:
        self.reason, self.tick, self.items, self.proven, self.attempts = reason, tick, items, proven, []
        ValueError.__init__(self, f"no plan: {reason}")


def _listed(words: Iterable[str], last: str = "and") -> str:
    """``words`` as a sentence lists them: "a", "a and b", "a, b and c"."""
    *rest, end = words
    return f"{', '.join(rest)} {last} {end}" if rest else end


class _Stuck(Exception):
    """An attempt that gets stuck: ``item``, a progression item with no
    safe proven spot, and ``got``, what its reach collected."""

    def __init__(self, reason: str, item: str | None = None, got: frozenset[str] = frozenset()) -> None:
        super().__init__(reason)
        self.item, self.got = item, got


@dataclass(frozen=True)
class Fill:
    """A verified placement: every authored pool location -> its item;
    ``failed``, the reason each attempt before it failed (the trap gate's
    retry rate, §10.2b P4); ``repaired``, each trap-gate refusal the
    passing attempt repaired (Step R1.8m)."""
    seed: str
    settings: Settings
    attempt: int
    placement: dict[str, str]
    failed: tuple[str, ...] = ()
    repaired: tuple[str, ...] = ()


class _Budget:
    """Each graph's new strings so far, against the writer's budget."""

    def __init__(self, names: Names) -> None:
        self.names, self.new, self.used = names, collections.defaultdict(set), collections.Counter()

    def _cost(self, lid: str, item: str) -> tuple[str, str | None, int]:
        name, g = self.names.target(lid, item), graph_of(lid)
        if name is None or name in self.names.have.get(g, ()) or name in self.new[g]:
            return g, None, 0
        return g, name, string_cost(name)

    def fits(self, lid: str, item: str) -> bool:
        g, name, cost = self._cost(lid, item)
        return name is None or (g in self.names.graphs and self.used[g] + cost <= self.names.budget(g))

    def take(self, lid: str, item: str) -> None:
        g, name, cost = self._cost(lid, item)
        if name is not None:
            self.new[g].add(name)
            self.used[g] += cost


def excluded_locations(logic: Logic) -> frozenset[str]:
    """The authored pool locations that take no progression and no obsidian
    (plan §3.3, §5.4; RQ-5, D81): those a level file marks ``exclude``,
    those an obsidian lock needing a full clear gates (lock 10: the whole
    pool's 100 obsidians, stubs included), the forfeitable ones and the
    unsaved ones (AZ-467): a generator on no save list (``saved``, the
    graph's list a load restores, 0x65E50) comes back from its record on
    every visit, so its item respawns (seen in xemu: f4's r1540 taken
    twice); a prefilled one keeps its own item."""
    db, rows = logic.db, logic.location_rows
    locks = {gid: o for gid, (_, kind, o) in db.generated_objects.items() if kind == "obsidian_locks"}
    supply = collections.Counter()
    for loc in logic.pool:
        item, n = logic.vanilla[loc]
        for c, inc in logic.items[item].items():
            supply[c] += inc * n
    full = {gid for gid, o in locks.items()
            if any(a[0] == "counter" and a[2] >= supply[a[1]] for a in atoms(parse(o["requires"])))}
    unsaved = {loc["id"] for doc in db.generated.values() for loc in doc["locations"]
               if loc["pool"] and not loc.get("saved", True) and loc["id"] not in logic.prefilled}
    return frozenset(loc for loc, lvl in logic.pool.items() if lvl not in db.stubs and (
        rows.get(loc, {}).get("exclude") or set(logic.gated_by[loc]) & full or loc in logic.forfeitable
        or loc in unsaved))


class _Slots:
    """The fill's facts about a database's authored pool under one set of
    options (the database's defaults when None), read once."""

    def __init__(self, logic: Logic, settings: Settings | None = None) -> None:
        db = logic.db
        self.logic, self.names = logic, Names(db)
        self.cls = {name: it["class"] for name, it in self.names.items.items()}
        locs = self.names.locations
        self.pool = sorted(loc for loc, lvl in logic.pool.items() if lvl not in db.stubs)
        self.vanilla = {loc: locs[loc]["item"] for loc in self.pool}
        rows = logic.location_rows
        on = {pick_of(sid, logic.skip_tables) for sid in skips_on(settings or db.defaults, logic.skip_tables)}
        marks = {loc: rows[loc]["proven"] for loc in self.pool if "proven" in rows.get(loc, {})}
        # AZ-725: a route mark that a skip these options turn on outdoes holds then only for its ``only`` items
        self.only = {loc: frozenset(pv.get("only", ())) for loc, pv in marks.items() if on & set(pv.get("unless", ()))}
        self.proven = frozenset(loc for loc in marks if self.only.get(loc, True))
        locks = {gid for gid, (_, kind, _) in db.generated_objects.items() if kind == "obsidian_locks"}
        self.vault = frozenset(loc for loc in self.pool if set(locs[loc].get("gated_by", ())) & locks)
        self.excluded = excluded_locations(logic)
        self.prefilled = {loc: self.vanilla[loc] for loc in self.pool if loc in logic.prefilled}
        self.kind = {loc: ("cluster", locs[loc]["yield"]) if locs[loc]["class"] == "cluster"
                     else locs[loc]["class"] if locs[loc]["class"] == "gem" else "nongem" for loc in self.pool}
        self.major = frozenset(loc for loc in self.pool if locs[loc]["class"] == "major")

    def holds(self, loc: str, item: str) -> bool:
        """Whether ``loc``'s proven mark holds for ``item`` under these options."""
        return loc in self.proven and item in self.only.get(loc, (item,))

    def open_proven(self) -> list[str]:
        """The proven spots a progression item may take."""
        return [loc for loc in self.pool if loc in self.proven and self.kind[loc] == "nongem" and loc not in
                self.excluded and loc not in self.prefilled and loc not in self.vault]

    def kept(self, settings: Settings) -> dict[str, str]:
        """The spots ``settings``' ``exclude_categories`` keep on their vanilla items (Step R1.10b)."""
        return {loc: item for loc, item in self.vanilla.items()
                if category(self.names.base[item]) in settings.exclude_categories}

    def _open(self, excluded: frozenset[str]) -> tuple[list[str], list[str]]:
        """The proven spots open to a progression item and the progression
        items to place when ``excluded``'s categories stay vanilla."""
        kept = {loc for loc, item in self.vanilla.items() if category(self.names.base[item]) in excluded}
        free = [loc for loc in self.open_proven() if loc not in kept]
        items = sorted(item for loc, item in self.vanilla.items() if loc not in self.prefilled and loc not in kept
                       and self.kind[loc] == "nongem" and self.cls[item] == "progression")
        return free, items

    def starved(self, settings: Settings) -> Starved | None:
        """The preflight (Step R1.27, AZ-454): a :class:`Starved` when the
        proven spots open to a progression item under ``settings`` are fewer
        than the progression items the plan places, each needing one of its
        own (D122, D143), so no attempt can fill; None otherwise. Its reason
        (Step 4.4u1) names in the tab's words the rows kept vanilla whose
        items hold the spots, the counts, the row whose tick alone is enough
        (else them all) and the other way: the progression items' own rows
        unticked too, which leaves none to place."""
        excluded = settings.exclude_categories
        free, items = self._open(excluded)
        if len(free) >= len(items):
            return None
        spots = self.open_proven()
        held = collections.Counter(category(self.names.base[self.vanilla[loc]]) for loc in spots if loc not in free)
        mine = {category(self.names.base[item]) for item in items}
        kinds = _listed(NAMES[c] for c in CATEGORIES if c in mine)
        if not held:
            return Starved(f"the levels have {len(spots)} spots whose way there and back is proven for the "
                           f"{len(items)} {kinds}, which go only on such spots: the logic needs more", None, items, free)

        def fits(kept: frozenset[str]) -> bool:
            more, left = self._open(kept)
            return len(more) >= len(left)

        cats = sorted(held, key=lambda c: (-held[c], CATEGORIES.index(c)))
        enough = [c for c in cats if fits(excluded - {c})]
        tick = "Tick " + (_listed((NAMES[c].capitalize() for c in enough), "or") if enough
                          else _listed(NAMES[c].capitalize() for c in cats))
        rows = _listed(NAMES[c].capitalize() for c in CATEGORIES if c in mine)
        return Starved(f"keeping {_listed(NAMES[c] for c in cats)} vanilla leaves {len(free)} spots for the "
                       f"{len(items)} {kinds}, which go only on spots whose way there and back is proven; of the "
                       f"{len(spots)} such spots, {_listed(f'{held[c]} hold {NAMES[c]}' for c in cats)}. {tick}, or "
                       f"untick {rows} too", tick, items, free)

    def ok(self, loc: str, item: str, budget: _Budget) -> bool:
        """The item rules (plan §3.3) for a spot of the right class."""
        cls = self.cls[item]
        if cls in ("progression", "progression_counted") and loc in self.excluded:
            return False
        if cls == "progression" and not self.holds(loc, item):
            return False
        if loc in self.vault and item not in VAULT_ITEMS and item != self.vanilla[loc]:
            return False
        return budget.fits(loc, item)

    def repairs(self, settings: Settings, placement: Mapping[str, str], r: Reach, trace: Sequence,
                prog: Mapping[str, str], known: frozenset[str], nongem: Sequence[str]) -> list[tuple[str, str]]:
        """The trap gate's repair (Step R1.8m): the first sphere ``t`` whose state has new trick-free traps, and
        the first later sphere ``u`` at whose state none of those is one any more. A progression item collected
        in the sphere before ``u`` (the way out) swaps spots with one collected in the sphere before ``t`` (the
        way in), or, when the traps are there from the start, with whatever lies on a spot at a trap node (its
        escape picks the item up there, as vanilla's water in w2's hose pool): each pair (the way out's spot, the
        other), sorted."""
        new = [sp.free_traps - r.after_completion - known for sp in trace]
        t = next((i for i, n in enumerate(new) if n), None)
        u = None if t is None else next((i for i in range(t + 1, len(trace)) if not new[i] & new[t]), None)
        if u is None:
            return []
        outs, got = sorted(trace[u - 1].locations & prog.keys()), trace[t].got
        back = next((i for i in range(t - 1, -1, -1) if trace[i].locations & prog.keys()), None)

        def clears(collected: Iterable[str]) -> bool:   # a collected guardian slot from its round, as the tracker
            return not self.logic.reach(settings, placement, collected=collected, replay=True).free_traps & new[t]
        if back is not None:        # the way in: the last items before t, those without which the traps aren't first
            ins = sorted(trace[back].locations & prog.keys())
            ins = [b for b in ins if clears(got - {b})] or ins
        else:                       # none: the spots at the traps, and first the ways out that free them there
            node = self.logic.db.node_of
            ins = [loc for loc in nongem if node[loc] in new[t] and loc in self.proven and loc not in self.excluded
                   and loc not in self.vault]
            outs = [a for a in outs if clears(got | {a})] or outs
        return [(a, b) for a in outs for b in ins if a != b and self.holds(b, prog[a])
                and (b not in prog or self.holds(a, prog[b]))]

    @staticmethod
    def floor(k: int, counters: Mapping[str, int], reads: Mapping[str, frozenset[int]]) -> int:
        """The lowest count of an item whose copies cross the thresholds k
        copies cross: the bottom of k's band."""
        f = 0
        for c, inc in counters.items():
            t = max((t for t in reads.get(c, ()) if t <= k * inc), default=0)
            f = max(f, -(-t // inc))
        return f

    def attempt(self, settings: Settings, reads: Mapping[str, frozenset[int]], streams: Callable[[str], Rng],
                known: frozenset[str], repaired: list[str] | None = None,
                reaches: _Reaches | None = None, told: _Count | None = None, pin: _Pin | None = None) -> dict[str, str]:
        """One attempt's placement, or :class:`_Stuck`; ``repaired`` gets
        each trap-gate refusal it went on to repair. ``reaches``: the
        fill's kept reaches under ``settings`` (one of its own when None);
        ``told`` hears the items it places and each reach (:class:`_Count`);
        ``pin``: a seed difficulty's (:class:`_Pin`)."""
        lg = self.logic
        reaches = reaches if reaches is not None else _Reaches(lg, settings)
        placed, budget = dict(self.prefilled), _Budget(self.names)
        placed.update(self.kept(settings))
        read = {name for name, cs in lg.items.items() if cs.keys() & reads.keys()}
        todo = [loc for loc in self.pool if loc not in placed]
        told, start = told or _Count.SILENT, len(placed)
        nongem = [loc for loc in todo if self.kind[loc] == "nongem"]
        by_class = collections.defaultdict(list)
        for loc in nongem:
            by_class[self.cls[self.vanilla[loc]]].append(self.vanilla[loc])
        told.begin(sum(len(by_class[cls]) for cls in _Count.REACHED) + 1)
        assumed = collections.Counter(self.vanilla[loc] for loc in todo if self.vanilla[loc] in read)

        def reach(at: Mapping[str, str] | None = None) -> Reach:
            told(len(placed) - start, True)
            return reaches({**placed, **(at or {})}, tuple(sorted(assumed.elements())), traps=False)

        def put(loc: str, item: str) -> None:
            placed[loc] = item
            budget.take(loc, item)
            told(len(placed) - start)

        def safe(item: str, got: frozenset[str]) -> list[str]:
            return [loc for loc in nongem if loc not in placed and loc in got and self.ok(loc, item, budget)]

        def still(item: str, got: frozenset[str], spots: list[str], spot: str) -> list[str]:
            """``safe(item, got)`` once ``spot`` of ``spots`` (its last answer) took ``item``: the put changed that
            spot and its graph's budget alone, so a spot of another graph keeps its verdict and only that graph's are
            asked again (a counted item's copies, hundreds of thousands of asks a plan)."""
            g, was = graph_of(spot), set(spots)
            return [loc for loc in nongem if loc not in placed and loc in got
                    and (self.ok(loc, item, budget) if graph_of(loc) == g else loc in was)]

        def own(item: str, r: Reach) -> list[str]:
            """The spots ``item`` opens by lying there: at a node reached but not safe without it, collected once it
            lies there (its escape picks it up: vanilla's water in w2's hose pool)."""
            return [loc for loc in nongem if loc not in placed and loc not in r.locations and node[loc] in r.nodes
                    and node[loc] not in r.safe and self.ok(loc, item, budget) and loc in reach({loc: item}).locations]

        def spots_for(item: str, r: Reach | None = None) -> list[str]:
            r = r or reach()
            return own(item, r) or safe(item, r.locations)

        def rebudget(prog: Mapping[str, str]) -> bool:
            """``placed`` and the budget again from ``base`` and ``prog``; False when over a budget."""
            nonlocal placed, budget
            placed, budget = dict(base), _Budget(self.names)
            for loc, item in sorted(prog.items()):
                if not budget.fits(loc, item):
                    return False
                put(loc, item)
            return True

        def trade(item: str, r: Reach) -> bool:
            """No spot for ``item`` in its reach ``r``: it takes the spot of a progression item placed before it
            whose node the reach gets to, the spot collected with ``item`` there and the other item assumed, and the
            other item moves to a spot of the reach with ``item`` there (Step R1.8m)."""
            prog = {loc: x for loc, x in placed.items() if loc not in base}
            for loc in rng.shuffle(sorted(loc for loc in prog if node[loc] in r.nodes)):
                if not self.holds(loc, item):      # AZ-725: a spot whose mark holds for its own item alone
                    continue
                other = prog[loc]
                assumed[other] += other in read
                if loc in reach({loc: item}).locations:
                    assumed[other] -= other in read
                    if rebudget({**prog, loc: item}) and (spots := spots_for(other)):
                        put(rng.choice(spots), other)
                        return True
                else:
                    assumed[other] -= other in read
                rebudget(prog)
            return False

        node, base = lg.db.node_of, dict(placed)
        rng = streams("progression")
        pinned: set[str] = set()     # this attempt's pinned spots
        for item in rng.shuffle(sorted(by_class["progression"])):
            assumed[item] -= item in read
            if spots := spots_for(item, r := reach()):
                put(rng.choice(spots) if pin is None else pin.pick(rng, item, spots, r, placed, assumed, pinned), item)
            elif not trade(item, r):
                raise _Stuck(f"no safe proven spot for {item}", item, r.locations)
        prog = {loc: item for loc, item in placed.items() if loc not in base}
        good, pairs = None, []      # the last placement only the trap gate refused, and its untried repairs
        for fix in range(MAX_REPAIRS + 1):
            try:
                if fix:
                    a, b = pairs.pop(rng.below(len(pairs)))
                    prog = {**good, b: good[a]}
                    if b in good:
                        prog[a] = good[b]
                    else:
                        del prog[a]
                    if not rebudget(prog):
                        raise _Stuck(f"the repair puts {prog[b]} on {b} over its graph's string budget")
                for item, k in sorted(collections.Counter(by_class["progression_counted"]).items()):
                    while k:       # one reach per threshold band, the band's lowest count assumed
                        low = self.floor(k - 1, lg.items[item], reads) if item in read else 0
                        assumed[item] = low
                        got = reach().locations
                        spots = safe(item, got)
                        for _ in range(k - low):
                            if not spots:
                                raise _Stuck(f"no safe spot for {item} ({k} left)")
                            put(spot := rng.choice(spots), item)
                            k -= 1
                            spots = still(item, got, spots, spot)
                trace: list = []
                told(len(placed) - start, True)
                r = reaches(placed, trace=trace)
                if not (problems := _problems(lg, r, known)):
                    break
                if len(problems) > 1 or not new_traps(r, known):
                    raise _Stuck("the verify: " + "; ".join(problems))
                good, pairs = prog, self.repairs(settings, placed, r, trace, prog, known, nongem)
                why = _Stuck("the verify: " + "; ".join(problems))
                if pairs and repaired is not None:
                    repaired.append(str(why))
            except _Stuck as exc:       # a repair that breaks the placement goes back to the last one
                if good is None:
                    raise
                why = exc
            if not pairs:
                raise why
        else:
            raise why

        rng = streams("useful")
        items = rng.shuffle(sorted(by_class["useful"]))
        for vault in rng.shuffle([loc for loc in nongem if loc in self.vault and loc not in placed]):
            fits = [item for item in items if self.ok(vault, item, budget)]
            if not fits:
                raise _Stuck(f"no useful item may go into the vault {vault} (Q290)")
            item = rng.choice(fits)
            items.remove(item)
            assumed[item] -= item in read
            if vault not in reach().locations:
                raise _Stuck(f"the vault {vault} is not safe without {item}")
            put(vault, item)
        for item in items:
            assumed[item] -= item in read
            spots = safe(item, reach().locations)
            if not spots:
                raise _Stuck(f"no safe spot for {item}")
            put(rng.weighted(spots, [USEFUL_MAJOR_WEIGHT if loc in self.major else 1 for loc in spots]), item)

        rng = streams("filler")
        groups = [("non-gem", [loc for loc in nongem if loc not in placed], by_class["filler"])]
        for kind in sorted({k for k in self.kind.values() if k != "nongem"}, key=str):
            spots = [loc for loc in todo if self.kind[loc] == kind]
            groups.append((kind if kind == "gem" else f"yield-{kind[1]} cluster", spots,
                           [self.vanilla[loc] for loc in spots]))
        for what, spots, items in groups:
            items = rng.shuffle(sorted(items))
            for loc in rng.shuffle(sorted(spots)):
                j = next((j for j, item in enumerate(items) if self.ok(loc, item, budget)), None)
                if j is None:
                    raise _Stuck(f"no {what} item may go on {loc}")
                put(loc, items.pop(j))

        told(len(placed) - start, True)
        if problems := _problems(lg, reaches(placed), known):     # verify's, on the kept reaches
            raise _Stuck("the verify: " + "; ".join(problems))
        return dict(sorted(placed.items()))


class _Count:
    """The fill's progress as :func:`~azurkit.core.progress.note` calls
    (Step 4.3u): "placing the items, k of n", k the item being placed of
    the n steps an attempt takes, each item a reach places (:data:`REACHED`:
    where its time goes) a step and the rest, placed at once, its last
    (Step 4.3 train B3: counted by spots, the bar sat in its first tenth
    while the reaches ran), one count through the fill's attempts that
    never falls (an attempt after a stuck one tells the count the stuck one
    reached until it passes it; a trade or repair puts items again). A note
    each time the count passes a percent and at each reach, so each is the
    bar's step and a cancel point no more than one reach apart, a retried
    attempt's too; the fill's :class:`_Making` keeps the last for a thread
    waiting on it. A seed difficulty's fill counts up to its :data:`~.difficulty.BOUND`
    candidates, each ``tries``' share of the bar, so it moves through all of
    them; a shaped fill's first candidate that meets its promise ends it there."""

    SILENT: _Count
    REACHED = ("progression", "progression_counted", "useful")
    """The item classes the fill places by a reach, each a step of its count."""

    def __init__(self, making: _Making | None = None, tries: int = 1) -> None:
        self.making, self.n, self.k, self.percent = making, 1, 0, -1
        self.tries, self.tried, self.say, self.beside = tries, 0, "", 0

    def begin(self, n: int) -> None:
        self.n = max(n, 1)
        self(0, True)

    def __call__(self, placed: int, reach: bool = False) -> None:
        whole = self.n * self.tries
        self.k = k = min(max(self.k, self.tried * self.n + placed + 1), whole)
        if self.making is None or not (reach or k * 100 // whole != self.percent):
            return
        self.percent = k * 100 // whole
        self.making.text = text = f"{self.say}placing the items, {k} of {whole}"
        progress.note(text)

    def tick(self) -> None:
        """The fill's thread's note while attempts run beside it, so the bar moves with their steps: about two an item
        (a reach and a placing), inside the next candidate's share (a cancel point)."""
        self(min(self.beside // 2, self.n - 1), True)
        if self.making is None:
            progress.note("placing the items")

    def tried_one(self, tried: int) -> None:
        """``tried`` candidates rejected: the next one's words and its share of the count (a cancel point)."""
        self.tried, self.say, self.beside = tried, f"shaping the seed: try {tried + 1} of up to {BOUND}, ", 0
        if self.making is not None:
            self.making.text = self.say.removesuffix(", ")
        progress.note(self.say.removesuffix(", "))


class _BesideCount(_Count):
    """An attempt's count beside others (:data:`BESIDE`): each step a note its thread hears and one more for the
    fill's count (:meth:`_Count.tick`); a lost increment is a bar's step, no more."""

    def __init__(self, fills: _Count) -> None:
        super().__init__()
        self.fills = fills

    def __call__(self, placed: int, reach: bool = False) -> None:
        self.fills.beside += 1
        progress.note("placing the items")


_Count.SILENT = _Count()


class _Reaches:
    """The fill's reaches under one set of options, kept by what they read
    (Step R2.1): the items placed that a rule of the graphs the reach walks
    reads, and the items held from the start. Any other item (a useful or
    filler item no rule reads, an empty spot) changes no counter a rule
    compares, so its reach is the one kept. ``physical`` false: only
    ``traps=False`` reaches are asked, so the physical graphs aren't compiled."""

    def __init__(self, logic: Logic, settings: Settings, physical: bool = True) -> None:
        self.logic, self.settings, self.kept = logic, settings, {}
        graphs = [logic.rules(settings)]
        self.read = {False: self._read(graphs)}
        if not physical:
            return
        phys = logic.rules(settings, physical=True)
        graphs += [phys, logic.rules(trick_free(settings), physical=True) if phys.on else phys]
        self.read[True] = self._read(graphs)

    def _read(self, graphs) -> frozenset[str]:
        counters = set().union(*(g.reads for g in graphs))
        return frozenset(name for name, cs in self.logic.items.items() if cs.keys() & counters)

    def __call__(self, placement: Mapping[str, str | None], items: Iterable[str] = (), traps: bool = True,
                 trace: list | None = None) -> Reach:
        read = self.read[traps]
        key = (traps, frozenset((loc, item) for loc, item in placement.items() if item in read), tuple(items))
        if trace is None and (r := self.kept.get(key)) is not None:
            return r
        r = self.kept[key] = self.logic.reach(self.settings, placement, items, trace=trace, traps=traps)
        return r


class _Pin:
    """A seed difficulty's pin in one fill (the module docstring): the items the win needs at the ladder's lowest rung
    with every other pool item held, one reach an item, and the ladder's reaches, each on the logical graph alone."""

    def __init__(self, logic: Logic, slots: _Slots, settings: Settings, ladder: Sequence[Settings]) -> None:
        self.rungs, self.level_of = [_Reaches(logic, st, physical=False) for st in ladder], logic.pool
        base = {**slots.prefilled, **slots.kept(settings)}
        rest = collections.Counter(slots.vanilla[loc] for loc in slots.pool if loc not in base)
        needed = set()
        for item in sorted(item for item in rest if slots.cls[item] == "progression"):
            held = rest.copy()
            held[item] -= 1
            progress.note("placing the items")
            if not logic.reach(ladder[-1], base, sorted(held.elements()), traps=False).victory:
                needed.add(item)
        self.needed = frozenset(needed)

    def pick(self, rng: Rng, item: str, spots: list[str], r: Reach, placed: Mapping[str, str],
             assumed: collections.Counter, pinned: set[str]) -> str:
        """``item``'s spot among its ``spots`` (:class:`_Slots`' own or safe ones, sorted; ``r``, its reach)."""
        if item not in self.needed or spots[0] not in r.locations:   # an own spot comes first, as today
            return rng.choice(spots)
        held = tuple(sorted(assumed.elements()))
        missed = [0] * len(spots)
        for rung in self.rungs:
            got = rung(placed, held, traps=False).locations
            missed = [m + (s not in got) for m, s in zip(missed, spots)]
        if not (top := max(missed)):
            return rng.choice(spots)
        best = [s for s, m in zip(spots, missed) if m == top]
        used = {self.level_of[loc] for loc in pinned}
        best = [s for s in best if self.level_of[s] not in used] or best
        pick = rng.choice(best)
        pinned.add(pick)
        return pick


_KNOWN: list = [None]   # the process's last known traps: (its Logic, its database, the options' graphs, the traps)


def known_traps(logic: Logic, settings: Settings) -> frozenset[str]:
    """The traps the trap gate lets a plan have (plan §2.13, D83(b)): the
    level files' ``known_traps`` (owner-signed) and vanilla's own, every
    trap of the vanilla placement under the same options or under the
    database's defaults, however it is entered (default taken under D115:
    D83(b) re-rolls a seed for *new* trick-free traps, vanilla's are
    computed rather than listed by hand, and a node vanilla traps a player
    in, such as f4's lava river or town's pits a skip gets into early, is
    vanilla's whatever the options)."""
    key = (id(logic.rules(settings)), id(logic.rules(logic.db.defaults)))
    if (last := _KNOWN[0]) is not None and last[0] is logic and last[1] is logic.db and last[2] == key:
        return last[3]
    signed = {t["node"] for doc in logic.db.levels.values() for t in doc.get("known_traps", ())}
    vanilla = logic.vanilla_placement()
    traps = []
    for st in (settings, logic.db.defaults)[:1 + (key[0] != key[1])]:
        traps.append(logic.reach(st, vanilla).traps)
        progress.note("placing the items")
    known = frozenset(signed).union(*traps)
    _KNOWN[0] = (logic, logic.db, key, known)
    return known


def new_traps(reach, known: frozenset[str]) -> list[str]:
    """The trick-free traps of ``reach`` the trap gate refuses: not known,
    and not a trap after completion (§2.9: a region left by its teleport)."""
    return sorted(reach.free_traps - reach.after_completion - known)


def verify(logic: Logic, settings: Settings, placement: Mapping[str, str],
           known: frozenset[str] | None = None) -> list[str]:
    """The independent solve (plan §3.3 step 5): victory under ``settings``,
    every authored pool location collected except the forfeitable ones
    (``full``), and the trap gate: no new trick-free trap (``known``:
    :func:`known_traps`, computed when None). Empty when it passes."""
    return _problems(logic, logic.reach(settings, placement), known_traps(logic, settings) if known is None else known)


_FULL: list = [None]   # the last Logic's locations a full reach collects, sorted: (a weak ref to it, to its database, them)


def _full(logic: Logic) -> tuple[str, ...]:
    """The authored pool locations a full reach collects (all but the forfeitable), sorted, once a Logic and database:
    a fill verifies a hundred placements."""
    kept = _FULL[0]
    if kept is None or kept[0]() is not logic or kept[1]() is not logic.db:
        stubs = logic.db.stubs
        kept = _FULL[0] = (weakref.ref(logic), weakref.ref(logic.db), tuple(
            loc for loc, lvl in sorted(logic.pool.items()) if lvl not in stubs and loc not in logic.forfeitable))
    return kept[2]


def _problems(logic: Logic, r: Reach, known: frozenset[str]) -> list[str]:
    """:func:`verify`'s problems with a placement's reach ``r``."""
    out = [] if r.victory else [f"victory ({logic.db.world['victory']}) does not hold"]
    missed = [loc for loc in _full(logic) if loc not in r.locations]
    if missed:
        out.append(f"{len(missed)} locations are never collected ({', '.join(missed[:8])}"
                   f"{', ...' if len(missed) > 8 else ''})")
    if new := new_traps(r, known):
        out.append(f"the trap gate (D83(b)): {len(new)} new trick-free traps ({', '.join(new[:8])}"
                   f"{', ...' if len(new) > 8 else ''})")
    return out


def _streams(seed: str, k: int, digest: str) -> Callable[[str], Rng]:
    """Attempt k's named streams."""
    return lambda name: stream(str(seed), name if k == 0 else f"attempt{k}/{name}", digest)


def fill(logic: Logic, seed: str, settings: Settings | None = None) -> Fill:
    """A verified placement for ``seed`` under ``settings`` (the database's
    defaults when None), from the first of :data:`MAX_ATTEMPTS` attempts
    that passes; :class:`FillError` otherwise, before any attempt when the
    settings starve it (:meth:`_Slots.starved`). The same inputs give the
    same placement in any process. The process's last fill is kept by its
    Logic and the database it holds (the same objects), seed and
    :func:`settings_digest` (what the solver reads of the settings), and a
    call on those again gets a copy of it (Step 2.221: a build after Track
    this seed fills once). A fill of those another thread is making (a
    host's plan ahead) is waited on (Step 4.3u), its waiter telling the
    maker's count every :data:`WAIT` s (:func:`~azurkit.core.progress.note`,
    so a cancel stops the waiter there) and taking a copy when it ends; one
    that ends without a fill (refused or cancelled) is made again by its
    waiter, which names its own refusal. The fill's notes count its spots
    (:class:`_Count`). The engine holds no threads (the site's worker runs it as it is; a host's
    :data:`BESIDE` holds its own): the in-flight fills are one dict whose ``setdefault`` is atomic, and a waiter
    sleeps between looks."""
    st = settings if settings is not None else logic.db.defaults
    key = (str(seed), settings_digest(st))
    ident = (id(logic), id(logic.db), key)   # live while in flight: its _Making holds them
    while True:
        if (made := _kept(logic, key)) is None:
            busy = _MAKING.setdefault(ident, mine := _Making(logic, key))
            if busy is mine and (made := _kept(logic, key)) is None:   # kept since the first look: no fill again
                break
            if busy is mine:   # ended with the kept fill, for a thread whose ask landed on it meanwhile
                mine.made, mine.ended = made, True
                del _MAKING[ident]
            else:
                told = time.monotonic()
                while not busy.ended:
                    time.sleep(_POLL)
                    if time.monotonic() - told >= WAIT:
                        told = time.monotonic()
                        progress.note(busy.text)
                made = busy.made
        if made is not None:
            return _copy(made, st)
    try:
        mine.made = made = _fill(logic, str(seed), st, mine)
        _LAST_FILL[0] = (logic, logic.db, key, made)
    finally:
        del _MAKING[ident]
        mine.ended = True
    return _copy(made, st)


def _kept(logic: Logic, key: tuple[str, str]) -> Fill | None:
    """The process's last fill when it is ``logic``'s (and its database's) for ``key``."""
    last = _LAST_FILL[0]
    return last[3] if last is not None and last[0] is logic and last[1] is logic.db and last[2] == key else None


def _copy(made: Fill, st: Settings) -> Fill:
    return Fill(made.seed, st, made.attempt, dict(made.placement), made.failed, made.repaired)


@dataclass(frozen=True)
class Outcome:
    """Attempt ``k`` of a fill: its ``placement`` and each trap-gate refusal it ``repaired``, or (no placement) why it
    is stuck and the item; ``why_not``, why a passing one misses its seed difficulty's promise (``None``: it meets it,
    or no promise)."""
    k: int
    placement: dict[str, str] | None
    reason: str = ""
    item: str | None = None
    repaired: tuple[str, ...] = ()
    why_not: str | None = None


@dataclass(frozen=True)
class _Verified:
    """What :func:`_problems` reads of a verify's reach, from the kernel's ids."""
    victory: bool
    locations: frozenset[str]
    free_traps: frozenset[str]
    after_completion: frozenset[str]


def _bits(ids: Iterable[int], count: int) -> list[int]:
    """``ids`` as a set's words, each a signed 64-bit word (the kernel's u64 sets in an array of int64)."""
    row = [0] * ((count + 63) // 64)
    for i in ids:
        row[i >> 6] |= 1 << (i & 63)
    return [x - (1 << 64) if x >> 63 else x for x in row]


def _named_bits(words: Sequence[int], names: Sequence[str]) -> frozenset[str]:
    """The names of the bits set in ``words`` (a set's words, each a signed 64-bit word)."""
    return frozenset(names[64 * w + b] for w, x in enumerate(words) if x for b in range(64) if x >> b & 1)


class _Kernel:
    """A run's attempts in the compiled kernel (``native/fill.c``, D1141; :meth:`_Slots.attempt` is its twin, the
    reference): the run's facts packed once as the kernel's blob (:attr:`blob`, the words fill.c's ``F_*``, ``L_*`` and
    ``I_*`` name; every id the reach tables'), each attempt's answer read back into what the twin gives, its notes told
    afterwards in the twin's order. No blob (:meth:`attempt` answers None): the twin runs: no library, tables only the
    reach's twin reads, numbers past the kernel's, or a stub level named as a node, where the kernel's ids can't tell
    apart the names the twin's sets hold."""

    MAGIC, VERSION, HEAD, OUT, CAP = 0x314C4C49464B, 1, 25, 8, 1 << 14    # fill.c's FILL_*, F_HEAD and O_HEAD; a first told log
    CLASSES = {"progression": 0, "progression_counted": 1, "useful": 2, "filler": 3}
    STREAMS = ("progression", "useful", "filler")

    def __init__(self, run: _Run) -> None:
        self.run, self.blob, self.cap, self._last = run, None, self.CAP, (None, None)
        logic, slots, st, db = run.logic, run.slots, run.st, run.logic.db
        if native.library() is None:
            return
        nt = logic._tables(st)
        tabs = [nt, *(logic._tables(rung) for rung in (run.shape.ladder if run.pin is not None else ()))]
        node_of, locs = db.node_of, slots.names.locations
        pool = set(slots.pool)
        copies = len(db.world["starting_items"]) + native._limits(nt.tables)[3] + len(nt.locs)   # an item's most

        def fits(t: native.Tables) -> bool:   # solve's bound on what a reach of the fill can hold
            terms, _, _, all_yields, most = native._limits(t)
            top = most * copies * len(t.items) + copies + all_yields + 1
            return (top + most * all_yields + t.locations) * terms < native.LIMIT
        if (len(tabs) > 4 or any(t.tables.twin_only or (t.locs, t.items, t.nodes) != (nt.locs, nt.items, nt.nodes)
                                 or not fits(t.tables) for t in tabs)
                or db.stubs & db.nodes.keys() or any(logic.canon(node_of[loc]) != node_of[loc] for loc in pool)):
            return
        self.tabs, self.nw, self.lw = tabs, (nt.tables.nodes + 63) // 64, (nt.tables.locations + 63) // 64
        placed = {**slots.prefilled, **slots.kept(st)}
        read = {name for name, cs in logic.items.items() if cs.keys() & run.reads.keys()}
        todo = [loc for loc in slots.pool if loc not in placed]
        nongem = [loc for loc in todo if slots.kind[loc] == "nongem"]
        by_class = collections.defaultdict(list)
        for loc in nongem:
            by_class[slots.cls[slots.vanilla[loc]]].append(slots.vanilla[loc])
        self.steps = sum(len(by_class[cls]) for cls in _Count.REACHED) + 1
        kinds = sorted({k for k in slots.kind.values() if k != "nongem"}, key=str)
        groups = [("non-gem", None, by_class["filler"])]
        for kind in kinds:
            spots = [loc for loc in todo if slots.kind[loc] == kind]
            groups.append((kind if kind == "gem" else f"yield-{kind[1]} cluster", spots,
                           [slots.vanilla[loc] for loc in spots]))
        self.whats = [what for what, _, _ in groups]
        item, loc_id, node_id = nt.item, nt.loc, {n: i for i, n in enumerate(nt.nodes)}
        names = {x: i for i, x in enumerate(nt.items)}

        def name(x: str) -> int:
            return names.setdefault(x, len(names))
        graphs: dict[str, int] = {}
        levels: dict[str, int] = {}
        needed = run.pin.needed if run.pin is not None else ()
        w = [0] * self.HEAD

        def section(slot: int) -> None:
            w[slot] = len(w)
        section(7)                                   # F_LOCS: each location's L_W words
        for loc in nt.locs:
            row = locs[loc]
            w += [1 * (loc in pool) | 2 * (loc in slots.excluded) | 4 * (loc in slots.vault) | 8 * (loc in slots.major)
                  | 16 * (loc in slots.proven) | 32 * (loc in nt.placed) | 64 * (loc in slots.only),
                  item.get(row["item"], -1), 0, graphs.setdefault(graph_of(loc), len(graphs)),
                  node_id[logic.canon(node_of[loc])], levels.setdefault(logic.pool[loc], len(levels)),
                  item[placed[loc]] if loc in placed else -1, name(row["item"]), name(row["template"])]
        section(8)                                   # F_ITEMS: each item's I_W words
        start = collections.Counter(db.world["starting_items"])
        for x in nt.items:
            w += [self.CLASSES.get(slots.cls[x], 4), name(slots.names.base[x]),
                  1 * (x in read) | 2 * (x in VAULT_ITEMS) | 4 * (x in needed), start[x], string_cost(x)]
        section(9)                                   # F_MOVE: a base name's move item
        w += [item[slots.names.move_of[x]] if x in slots.names.move_of else -1 for x in names]
        section(10)                                  # F_GRAPH: in the writer's graphs, and its budget
        for key in graphs:
            mine = key in slots.names.graphs
            w += [int(mine), slots.names.budget(key) if mine else 0]
        section(11)                                  # F_HAVE: each graph's vanilla strings, a bit a name
        for key in graphs:
            w += _bits((i for x in slots.names.have.get(key, ()) if (i := names.get(x)) is not None), len(names))
        section(12)                                  # F_ONLY: AZ-725's items, by location
        at = len(w)
        w += [0] * (len(nt.locs) + 1)
        for i, loc in enumerate(nt.locs):
            w[at + i] = len(w)
            w += sorted(item[x] for x in slots.only.get(loc, ()))
        w[at + len(nt.locs)] = len(w)
        section(13)                                  # F_PROG
        prog = sorted(item[x] for x in by_class["progression"])
        w += [len(prog), *prog]
        section(14)                                  # F_USEFUL
        useful = sorted(item[x] for x in by_class["useful"])
        w += [len(useful), *useful]
        section(15)                                  # F_COUNTED: the item, its copies, each count's band floor
        counted = sorted(collections.Counter(by_class["progression_counted"]).items())
        w.append(len(counted))
        for x, k in counted:
            w += [item[x], k, *(slots.floor(c, logic.items[x], run.reads) if x in read else 0 for c in range(k))]
        section(16)                                  # F_GROUPS: the filler's, in order (the non-gem one's spots: -1)
        w.append(len(groups))
        most_group = max(len(prog), len(useful), len(nongem))
        for i, (_, spots, items) in enumerate(groups):
            w += [i, -1] if spots is None else [i, len(spots), *(loc_id[loc] for loc in spots)]
            w += [len(items), *sorted(item[x] for x in items)]
            most_group = max(most_group, len(spots or ()), len(items))
        section(17)                                  # F_NONGEM
        w += [len(nongem), *(loc_id[loc] for loc in nongem)]

        def bitset(slot: int, ids: Iterable[int], count: int) -> None:
            section(slot)
            w.extend(_bits(ids, count))
        stub_ids = [i for i, n in enumerate(nt.nodes) if n in db.stubs]
        whole = [i for i, n in enumerate(nt.nodes)
                 if all(x in run.known for x in (logic.stub_nodes[n] if n in db.stubs else (n,)))]
        bitset(18, whole, len(nt.nodes))             # F_KNOWN_FULL: every name a canonical node stands for is known
        bitset(19, (i for i, n in enumerate(nt.nodes) if n in run.known), len(nt.nodes))   # F_KNOWN_NAME: its own name
        bitset(20, stub_ids, len(nt.nodes))          # F_STUB
        bitset(21, (loc_id[loc] for loc in logic.guardian), len(nt.locs))     # F_GUARD
        bitset(22, (loc_id[loc] for loc in _full(logic)), len(nt.locs))       # F_FULL
        section(23)                                  # F_GIVES: what each location gives unplaced
        w += nt.gives
        w[:7] = [self.MAGIC, self.VERSION, len(nt.locs), len(nt.items), len(names), len(graphs), len(placed)]
        w[24] = most_group
        self.blob = array("q", w)

    def attempt(self, seed: str, k: int, told: _Count, repaired: list[str]) -> dict[str, str] | None:
        """Attempt ``k``'s placement as :meth:`_Slots.attempt` gives it (or its :class:`_Stuck`), its notes told to
        ``told`` and its refusals in ``repaired``; None: the twin runs."""
        if self.blob is None:
            return None
        run, nt = self.run, self.tabs[0]
        keys = []
        for name in self.STREAMS:
            n = sub_seed(seed, name if k == 0 else f"attempt{k}/{name}", run.digest)
            keys += [1 + (n >> 32 != 0), n & 0xFFFFFFFF, n >> 32]
        vw, nl = 1 + self.lw + 2 * self.nw, len(nt.locs)
        graphs = [g for t in self.tabs for g in t.graphs] + [0] * 3 * (4 - len(self.tabs))
        while True:
            call = array("q", [self.cap, len(self.tabs), int(run.pin is not None), *graphs, *keys])
            at_log = self.OUT + nl + vw * (MAX_REPAIRS + 2)
            out = native.attempt(self.blob, [t.tables for t in self.tabs], call, at_log + self.cap)
            if out != -3:
                break
            self.cap *= 4      # a longer told log than any seen: the attempt again, with room
        if out is None or isinstance(out, int):
            return None
        status, code, a, b, nlog, nrep = out[:6]
        self._told(told, out[at_log:at_log + nlog])
        reach = self.OUT + nl
        repaired.extend(self._verify(out[reach + vw * i:reach + vw * (i + 1)]) for i in range(1, nrep + 1))
        if status:
            raise self._stuck(code, a, b, out[reach:reach + vw])
        items, locs = nt.items, nt.locs
        return {locs[i]: items[x] for i, x in enumerate(out[self.OUT:self.OUT + nl]) if x >= 0}

    def _placement(self, placement: Mapping[str, str]) -> array:
        """A candidate's placement as az_accept reads it, kept for the next ask of the same one (a candidate's need,
        then its play)."""
        if (last := self._last)[0] is placement:
            return last[1]
        item, got = self.tabs[0].item, array("q")
        for loc in self.tabs[0].locs:   # an item's id; -1 none; -2 not in the placement (its vanilla item there)
            x = placement.get(loc, ...)
            got.append(-2 if x is ... else -1 if x is None else item.get(x, -1))
        self._last = (placement, got)
        return got

    def _accept(self, placement: Mapping[str, str], mode: int, rating: int, stop: int | None) -> array | None:
        """az_accept's answer for need (``mode`` 0) or play (1) at ``rating``, or None: the twin runs."""
        ask = self.run.shape.ask.rating if self.run.shape is not None else 0
        if self.blob is None or not 2 <= rating <= ask:
            return None
        graphs = [g for t in self.tabs for g in t.graphs] + [0] * 3 * (4 - len(self.tabs))
        call = array("q", [0, len(self.tabs), 0, *graphs, *[0] * 9, mode, 1 + ask - rating, -1 if stop is None else stop])
        out = native.accept(self.blob, [t.tables for t in self.tabs], call, self._placement(placement),
                            4 + len(self.tabs[0].locs) + 2)
        return None if out is None or isinstance(out, int) else out

    def need(self, placement: Mapping[str, str], rating: int):
        """difficulty.need's answer (no win at the rung), or :data:`~.difficulty.TWIN`."""
        return TWIN if (out := self._accept(placement, 0, rating, None)) is None else not out[1]

    def play(self, placement: Mapping[str, str], rating: int, stop: int | None):
        """difficulty.play's (needed true) for what the acceptance reads (its stages; no rounds), or
        :data:`~.difficulty.TWIN`; its notes told as the twin's."""
        if (out := self._accept(placement, 1, rating, stop)) is None:
            return TWIN
        for _ in range(out[2]):
            progress.note(NOTE)
        return None if out[0] else Play(True, tuple(out[4:4 + out[3]]), ())

    def _told(self, told: _Count, log: Sequence[int]) -> None:
        """The twin's notes, in its order: a beside attempt's steps as one count and one note."""
        if told is _Count.SILENT:
            return
        told.begin(self.steps)
        if isinstance(told, _BesideCount):
            told.fills.beside += len(log)
            progress.note("placing the items")
            return
        for x in log:
            told(x >> 1, bool(x & 1))

    def _verify(self, words: Sequence[int]) -> str:
        """The words of the verify's reach kept at ``words`` (fill.c's ``keep``)."""
        run, nt, lw, nw = self.run, self.tabs[0], self.lw, self.nw
        logic = run.logic
        free, after = (logic._named(logic.stub_nodes, _named_bits(words[at:at + nw], nt.nodes))
                       for at in (1 + lw, 1 + lw + nw))
        r = _Verified(bool(words[0]), _named_bits(words[1:1 + lw], nt.locs), free, after)
        return "the verify: " + "; ".join(_problems(logic, r, run.known))

    def _stuck(self, code: int, a: int, b: int, words: Sequence[int]) -> _Stuck:
        """The twin's :class:`_Stuck` for fill.c's reason ``code`` and its ids (``W_*``: an item ``a``, a location
        ``b``; a count left ``b``; a filler group ``a``) or the verify's reach kept at ``words``."""
        items, locs = self.tabs[0].items, self.tabs[0].locs
        if code == 3:
            return _Stuck(f"no safe spot for {items[a]} ({b} left)")
        if code == 4:
            return _Stuck(self._verify(words))
        if code == 8:
            return _Stuck(f"no {self.whats[a]} item may go on {locs[b]}")
        item, loc = items[a] if a >= 0 else None, locs[b] if b >= 0 else None
        if code == 1:
            return _Stuck(f"no safe proven spot for {item}", item)
        if code == 2:
            return _Stuck(f"the repair puts {item} on {loc} over its graph's string budget")
        if code == 5:
            return _Stuck(f"no useful item may go into the vault {loc} (Q290)")
        if code == 6:
            return _Stuck(f"the vault {loc} is not safe without {item}")
        return _Stuck(f"no safe spot for {item}")


class _Run:
    """What a fill's attempts share: only caches and what a seed's every attempt reads alike."""

    def __init__(self, logic: Logic, st: Settings, making: _Making | None = None) -> None:
        progress.note("placing the items")    # and between the options' first graphs and reaches (cancel points)
        self.logic, self.st, self.slots = logic, st, _Slots(logic, st)
        if (refused := self.slots.starved(st)) is not None:
            raise refused
        self.digest, self.reads = settings_digest(st), logic.reads(st)
        progress.note("placing the items")
        self.known = known_traps(logic, st)
        progress.note("placing the items")
        self.reaches = _Reaches(logic, st)
        ask = asked(st, logic.skip_tables) if st.seed_difficulty else None
        self.shape = None if ask is None else Shape(logic, st, ask)
        self.pin = None if ask is None else _Pin(logic, self.slots, st, self.shape.ladder)
        self.count = _Count(making, 1 if ask is None else BOUND)
        self.kernel = _Kernel(self)
        if self.shape is not None and self.kernel.blob is not None:
            self.shape.kernel = self.kernel

    def attempt(self, seed: str, k: int, count: _Count | None = None) -> Outcome:
        repaired: list[str] = []
        try:
            if (placement := self.kernel.attempt(seed, k, count or self.count, repaired)) is None:
                placement = self.slots.attempt(self.st, self.reads, _streams(seed, k, self.digest), self.known,
                                               repaired, self.reaches, count or self.count, self.pin)
        except _Stuck as exc:
            return Outcome(k, None, str(exc), exc.item)
        layout(placement, self.logic.db)     # the writer's own check (never over a budget): a WriteError is a bug
        return Outcome(k, placement, repaired=tuple(repaired),
                       why_not=None if self.shape is None else self.shape.why_not(placement))


class _Accept:
    """A fill's outcomes in attempt order to its plan (the module docstring)."""

    def __init__(self, run: _Run, seed: str) -> None:
        self.run, self.seed, self.reasons, self.stuck, self.candidates = run, seed, [], set(), []
        self.beside: Beside | None = None

    def add(self, o: Outcome) -> Fill | None:
        """``o``, the next attempt's: the plan, once the outcomes so far decide it."""
        if o.placement is None:
            self.reasons.append(f"attempt {o.k}: {o.reason}")
            if o.item is not None:
                self.stuck.add(o.item)
            return None
        made = Fill(self.seed, self.run.st, o.k, o.placement, tuple(self.reasons),
                    tuple(f"attempt {o.k}: {r}" for r in o.repaired))
        if o.why_not is None:
            return made
        self.reasons.append(f"attempt {o.k}: passed, but {o.why_not}")
        self.candidates.append(made)
        if len(self.candidates) >= BOUND:
            return self.closest()
        self.run.count.tried_one(len(self.candidates))
        return None

    def closest(self) -> Fill | None:
        """The candidate with the highest score, the first on a tie; none: ``None``."""
        if not self.candidates:
            return None
        placements, score = [made.placement for made in self.candidates], self.run.shape.score
        scores = [score(p) for p in placements] if self.beside is None else self.beside.again(score, placements)
        return replace(self.candidates[max(range(len(scores)), key=scores.__getitem__)], failed=tuple(self.reasons))

    def end(self) -> Fill:
        """Every attempt told: the closest, or no plan (D35)."""
        if (kept := self.closest()) is not None:
            return kept
        raise FillError(f"{MAX_ATTEMPTS} attempts failed; the last: {self.reasons[-1]}", sorted(self.stuck),
                        self.run.slots.open_proven(), self.reasons)


class _Making:
    """A fill in flight (:func:`fill`): its Logic and database (held, so
    their ids stay theirs), the note it told last, the fill once made and
    whether it ended."""

    def __init__(self, logic: Logic, key: tuple[str, str]) -> None:
        self.logic, self.db, self.key, self.text = logic, logic.db, key, "placing the items"
        self.made: Fill | None = None
        self.ended = False


_LAST_FILL: list = [None]   # the process's last fill: (its Logic, its database, (seed, settings digest), the Fill)
_MAKING: dict[tuple, _Making] = {}   # the fills in flight, by their Logic's and database's ids and key


def _fill(logic: Logic, seed: str, st: Settings, making: _Making | None = None) -> Fill:
    run = _Run(logic, st, making)
    accept = _Accept(run, seed)
    if (made := accept.add(run.attempt(seed, 0))) is not None:   # most seeds' only one, so never beside others
        return made
    width = WIDTH if run.shape is not None and BESIDE is not None else 1
    if width == 1:
        for k in range(1, MAX_ATTEMPTS):
            if (made := accept.add(run.attempt(seed, k))) is not None:
                return made
        return accept.end()
    told = _BesideCount(run.count)
    with BESIDE(width, run.count.tick) as beside:
        accept.beside = beside
        for future in [beside.submit(lambda k: run.attempt(seed, k, told), k) for k in range(1, MAX_ATTEMPTS)]:
            if (made := accept.add(beside.answer(future))) is not None:
                return made
        return accept.end()


def starved(logic: Logic, settings: Settings | None = None) -> Starved | None:
    """The preflight's refusal of ``settings`` (the database's defaults when
    None) on ``logic`` (:meth:`_Slots.starved`), None when an attempt may
    fill: what the Randomizer tab says before a build, its Build greyed."""
    st = settings if settings is not None else logic.db.defaults
    return _Slots(logic, st).starved(st)


def roll(logic: Logic, seeds: Iterable[str], settings: Settings | None = None) -> str | None:
    """The first of ``seeds`` whose first attempt passes under ``settings``
    (the database's defaults when None), so that its fill is that attempt
    (D185: the GUI starts on such a seed, which fills and plans at once);
    None when none does, at once when the preflight refuses the settings
    (:meth:`_Slots.starved`)."""
    st = settings if settings is not None else logic.db.defaults
    slots = _Slots(logic, st)
    if slots.starved(st) is not None:
        return None
    digest, reads, known = settings_digest(st), logic.reads(st), known_traps(logic, st)
    for seed in seeds:
        try:
            slots.attempt(st, reads, _streams(seed, 0, digest), known)
        except _Stuck:
            continue
        return str(seed)
    return None
