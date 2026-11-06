"""The item tracker (D189, Step 2.51): the spots of a seed being played
that the player marks collected, and what the solver says is reachable now.

The tracked spots are the pool locations that can hold a progression item
or an obsidian: the major items', the obsidians' and the fuel and health
spots (a gem spot holds only gems, which no requirement reads). Marking
one holds the item the plan put there and nothing else
(:meth:`~.planner.solver.Logic.reach` with ``collected``), and with Live
on the element levels the game holds past those (:meth:`Tracker.set_kit`,
R1.41); the solver
credits the events (a boss, a button, a barrier) the player can do now, and
those a marked guardian slot's region gave before its disc was placed
(``replay``, AZ-430).
:meth:`Tracker.table` sums them for the Table tab (Step R1.26, D249), and
:meth:`Tracker.apply` merges a live tracker's events
(:mod:`azurkit.tools.randomizer.live`): a live mark is one the game showed,
kept apart from a hand mark, which Live never undoes; a click on a live mark
vetoes it, so Live doesn't put it back.
The gem spots (Step R1.43, D928) are counted apart, by Live alone
(:attr:`Tracker.gems`): no requirement reads a gem, so they take no part
in the reach or the counter row's spots.
``gui/tracker.py`` draws it on the maps; ``azurik-mod rando tracker``
opens it.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from azurkit.tools.randomizer.live.game import EPS, Gem, Gems, Held, Level, Reload, Took
from azurkit.tools.randomizer.planner.settings import Settings
from azurkit.tools.randomizer.planner.solver import Logic

TRACKED = ("major", "obsidian", "consumable")
GEM_CLASSES = ("gem", "cluster")     # Step R1.43: a gem's spot, a cluster's (its yield of gems at one generator)
SPOT_CLASSES = {"major": "Item spots", "obsidian": "Obsidian spots", "consumable": "Fuel or health spots"}
GROUPS = {"frag": "Disc fragments", "power": "Powers", "key": "Keys", "obsidian": "Obsidians",
          "consumable": "Fuel and health", "other": "Other"}
ELEMENTS = ("air", "water", "fire", "earth", "life")
KINDS = {"frag": ELEMENTS, "power": (*ELEMENTS, "staff", "ammo"), "consumable": ("fuel", "health")}  # their order
REALMS = {"a": "Air", "e": "Earth", "f": "Fire", "w": "Water", "d": "Death"}   # a1 .. d2; life and town their own


def held_counts(inv: Mapping[str, int]) -> dict[str, int]:
    """The Table's "In game" column (:meth:`Tracker.table`'s ``held``) from a live reading's inventory: what
    the game counts exactly, by item row: obsidians, the fragments held per realm, the element powers' levels,
    the staff and ammo powers. Keys (spent), fuel, health and life (the build's starting HP isn't known) stay
    blank."""
    if not inv:
        return {}
    out = {"obsidian": inv.get("obsi", 0), "power/staff": inv.get("spow", 0), "power/ammo": inv.get("mpow", 0)}
    out |= {f"frag/{e}": sum(inv.get(f"fg{e[0]}{k}", 0) >= 1 for k in range(1, 5)) for e in ELEMENTS}
    out |= {f"power/{e}": inv.get(f"level.{e}", 0) for e in ELEMENTS[:4]}
    return out | {"frag": sum(out[f"frag/{e}"] for e in ELEMENTS)}


def kind_of(item: str) -> tuple[str, str]:
    """The Table's group and kind of an item: ``frag_air_2`` ("frag",
    "air"), ``power_water_a3`` ("power", "water"), ``power_staff1``
    ("power", "staff"), ``key_lens`` ("key", "lens"), ``obsidian``
    ("obsidian", ""), ``all_fuel`` ("consumable", "fuel"); any other
    ("other", the item), so a new item is counted, never dropped."""
    if (m := re.fullmatch(r"frag_([a-z]+)_\d", item)) and m[1] in ELEMENTS:
        return "frag", m[1]
    power = {"staff1": "staff", "staff2": "staff", "water_a3": "water"}.get(item[6:], item[6:])
    if item.startswith("power_") and power in KINDS["power"]:
        return "power", power
    if item.startswith("key_"):
        return "key", item[4:]
    return {"obsidian": ("obsidian", ""), "all_fuel": ("consumable", "fuel"),
            "all_health": ("consumable", "health")}.get(item, ("other", item))


def realm(level: str) -> str:
    """A level's realm: a1 "Air", d2 "Death"; life and town are their own."""
    return REALMS[level[0]] if level[0] in REALMS and level[1:].isdigit() else level.capitalize()


def _ordered(names, first):
    return sorted(names, key=lambda n: (first.index(n) if n in first else len(first), n))


def realms(levels: Iterable[str]) -> list[tuple[str, list[str]]]:
    """``levels`` by realm as the Table groups them: Air, Earth, Fire, Water and Death, then Life and Town (each a
    level of its own), then any other by name (the airship); each realm's levels sorted."""
    out = defaultdict(list)
    for lv in sorted(levels):
        out[realm(lv)].append(lv)
    return [(name, out[name]) for name in _ordered(out, (*REALMS.values(), "Life", "Town"))]


def spot_classes(db) -> dict[str, str]:
    """Each spot the tracker marks and its class (:data:`TRACKED`): the pool's live locations of the major items,
    the obsidians and fuel and health, in the database's order."""
    return {loc["id"]: loc["class"] for doc in db.generated.values() for loc in doc["locations"]
            if loc["pool"] and not loc["dead"] and loc["class"] in TRACKED}


@dataclass(frozen=True)
class Row:
    """A row of the Table tab (Step R1.26): its key (the tree's id) and
    label; how many of its items or spots are collected, reachable now
    and not collected (None: the Spoiler hides it) and tracked; the levels
    holding those left ("": hidden, or a group's); the game's own count
    (None: not known); the rows under it."""
    key: str
    label: str
    got: int
    now: int | None
    total: int
    where: str = ""
    game: int | None = None
    children: tuple["Row", ...] = ()

    @property
    def left(self) -> int:
        return self.total - self.got


@dataclass(frozen=True)
class Status:
    """The counter row: spots collected, reachable now (not collected) and
    tracked; the deepest of the plan's spheres collected from; whether
    victory is in reach; the levels a player reaches now; how many of those
    reachable now only a skip reaches (R1.41)."""
    collected: int
    reachable: int
    total: int
    sphere: int
    victory: bool
    levels: tuple[str, ...]
    skipped: int = 0


def marks(entry) -> dict:
    """A plan's marks as the GUI's state file keeps them: ``{"collected": [...], "live": {loc: day clock or
    null}, "veto": [...], "slot": the last saved slot Live saw, "gems": {loc: [each gem's day clock or
    null]}}``; an older bare list is the collected spots."""
    entry = {"collected": entry} if isinstance(entry, list) else dict(entry or {})
    return {"collected": list(entry.get("collected", [])), "live": dict(entry.get("live", {})),
            "veto": list(entry.get("veto", [])), "slot": entry.get("slot"), "gems": dict(entry.get("gems", {}))}


class Tracker:
    """A plan's tracked spots, those collected (by hand or live), and the reach now. ``live``: the spots a
    live tracker marked, each with the day clock of its take (None: seen taken, not taken while watched);
    ``veto``: live marks a click took off; ``slot``: the last saved slot the game was on (the journal); ``kit``:
    the element levels Live reads the game holding (:meth:`set_kit`); ``gems``: each gem spot's gems Live saw
    taken, a day clock each (None: seen taken), as many as its ``gem_full``, a cluster's yield (Step R1.43)."""

    def __init__(self, logic: Logic, settings: Settings, placement: Mapping[str, str],
                 collected: Iterable[str] = (), live: Mapping[str, float | None] | None = None,
                 veto: Iterable[str] = (), slot: str | None = None,
                 gems: Mapping[str, list[float | None]] | None = None):
        self.logic, self.settings, self.placement = logic, settings, dict(placement)
        self.spot_class = spot_classes(logic.db)
        self.spots = frozenset(self.spot_class)
        self.gem_full = {loc["id"]: loc["yield"] for doc in logic.db.generated.values() for loc in doc["locations"]
                         if loc["pool"] and not loc["dead"] and loc["class"] in GEM_CLASSES}
        self.collected = set(collected) & self.spots
        self.live = {loc: c for loc, c in (live or {}).items() if loc in self.collected}
        self.veto, self.slot = set(veto) & self.spots, slot
        self.gems = {loc: list(c)[:self.gem_full[loc]] for loc, c in (gems or {}).items()
                     if loc in self.gem_full and c}
        self.kit: dict[str, int] = {}
        trace: list = []
        logic.reach(settings, self.placement, trace=trace, traps=False)
        self.sphere_of = {loc: k for k, sp in enumerate(trace, 1) for loc in sp.locations}
        self.update()

    def item(self, loc: str) -> str:
        """The item at a spot: the plan's, a stub's vanilla one."""
        return self.placement.get(loc) or self.logic.vanilla[loc][0]

    def toggle(self, loc: str) -> None:
        """Mark a spot collected, or no longer: a live mark taken off is vetoed (Live won't mark it again),
        and a vetoed spot marked is a hand mark."""
        if loc in self.live:
            del self.live[loc]
            self.veto.add(loc)
        else:
            self.veto.discard(loc)
        self.collected ^= {loc} & self.spots
        self.update()

    def reset(self) -> None:
        """No mark, by hand or live, no veto and no gem taken."""
        self.collected.clear()
        self.live.clear()
        self.veto.clear()
        self.gems.clear()
        self.update()

    def journal(self) -> dict:
        """What a live session's first settle checks the game against: the last saved slot, the newest fresh
        live mark's or gem's day clock."""
        clocks = [*self.live.values(), *(c for cs in self.gems.values() for c in cs)]
        return {"slot": self.slot, "newest": max((c for c in clocks if c is not None), default=None)}

    def gems_taken(self, loc: str) -> int:
        return len(self.gems.get(loc, ()))

    def gem_counts(self) -> dict[str, tuple[int, int]]:
        """Each level's gems Live saw taken and its gems in all (a cluster's each), by pool level."""
        out: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for loc, full in self.gem_full.items():
            n = out[self.logic.pool[loc]]
            n[0] += self.gems_taken(loc)
            n[1] += full
        return {lv: (got, total) for lv, (got, total) in sorted(out.items())}

    def apply(self, events) -> bool:
        """Merge a live tracker's events (:mod:`~azurkit.tools.randomizer.live`); whether any mark changed (then
        the reach is updated once). A hand mark is never dropped, a vetoed spot never marked, and an unsaved
        spot never unmarked by a 0 (it resets every visit)."""
        before = (set(self.collected), dict(self.live), set(self.veto))
        gems = {loc: list(c) for loc, c in self.gems.items()}

        def mark(locs, clock=None) -> None:
            for loc in set(locs) & self.spots - self.collected - self.veto:
                self.collected.add(loc)
                self.live[loc] = clock

        def drop(locs) -> None:
            for loc in set(locs) & set(self.live):
                del self.live[loc]
                self.collected.discard(loc)

        def gem(loc, n, clock=None, down=False) -> None:
            """``loc``'s gems taken: at least ``n`` (more with ``clock``), at most ``n`` with ``down`` (the
            newest dropped)."""
            have = sorted(self.gems.get(loc, ()), key=lambda c: -1.0 if c is None else c)
            n = min(n, self.gem_full.get(loc, 0))
            have = have[:n] if down else have + [clock] * (n - len(have))
            if have:
                self.gems[loc] = have
            else:
                self.gems.pop(loc, None)

        for e in events:
            if isinstance(e, Gem):
                gem(e.loc, e.dead, e.clock)
            elif isinstance(e, Gems):
                for loc, n in e.taken.items():
                    gem(loc, n)
                    gem(loc, n, down=True)
                for loc, n in e.unsaved.items():
                    gem(loc, n, e.clock)
            elif isinstance(e, Took):
                mark([e.loc], e.clock)
            elif isinstance(e, Level):
                mark(e.taken)
                mark(e.unsaved_taken, e.clock)    # no settle unmarks them: the clock rule can
                drop(e.untaken)
                self.veto -= e.untaken | e.unsaved_untaken
            elif isinstance(e, Held):
                mark(e.locs)
                drop(e.absent)
                self.veto -= e.absent
            elif isinstance(e, Reload):
                drop([loc for loc, c in self.live.items() if e.new_timeline or c is not None and c > e.clock + EPS])
                for loc in list(self.gems):
                    gem(loc, 0 if e.new_timeline else sum(c is None or c <= e.clock + EPS for c in self.gems[loc]),
                        down=True)
                if e.new_timeline:
                    self.veto.clear()
                    self.slot = None     # the journal's slot: the new timeline's, once the game shows one
        if changed := before != (self.collected, self.live, self.veto):
            self.update()
        return changed or gems != self.gems

    def is_live(self, loc: str) -> bool:
        return loc in self.live

    def state(self) -> dict:
        """The marks for the GUI's state file (:func:`marks` reads them back)."""
        out = {"collected": sorted(self.collected)}
        out |= {"live": dict(sorted(self.live.items()))} if self.live else {}
        out |= {"gems": dict(sorted(self.gems.items()))} if self.gems else {}
        return out | ({"veto": sorted(self.veto)} if self.veto else {}) | ({"slot": self.slot} if self.slot else {})

    def set_kit(self, kit: Mapping[str, int]) -> bool:
        """The element powers' levels the game holds (Live's :attr:`~.live.Reading.kit`; {}: none read), so the
        reach holds them too, past what the marks give (R1.41: a level the game holds that no mark gives, a
        stored power's or one written into RAM, made spots behind it read not doable); whether they changed
        (then the reach is updated)."""
        kit = {e: n for e, n in kit.items() if n > 0}
        if kit == self.kit:
            return False
        self.kit = kit
        self.update()
        return True

    def update(self) -> None:
        own: dict[str, int] = defaultdict(int)     # the element levels the starting items and the marks give
        for name in (*self.logic.db.world["starting_items"], *map(self.item, self.collected)):
            for counter, n in self.logic.items[name].items():
                own[counter] += n
        kit = [f"power_{e}" for e, n in self.kit.items() for _ in range(n - own[e])]
        def reach(settings):
            return self.logic.reach(settings, self.placement, items=kit, traps=False, collected=self.collected,
                                    replay=True)

        r, none = reach(self.settings), replace(self.settings, skip_ceiling=0, skip_override={})
        self.reachable = frozenset(r.locations & self.spots) - self.collected
        # R1.41: those reachable now with no skip (the rest only a skip on reaches: a stored power's, say)
        self.plain = self.reachable if none == self.settings else self.reachable & reach(none).locations
        self.status = Status(len(self.collected), len(self.reachable), len(self.spots),
                             max((self.sphere_of.get(loc, 0) for loc in self.collected), default=0), r.victory,
                             tuple(sorted({self.logic.db.nodes[n][0] for n in r.safe})),
                             len(self.reachable - self.plain))

    def table(self, spoiler: bool, held: Mapping[str, int] | None = None,
              gems: bool = False) -> tuple[tuple[Row, ...], tuple[Row, ...]]:
        """The Table tab's two trees, each with its All row last: the items
        by group and kind, and the spots by realm and level. Without
        ``spoiler`` nothing says where an item not collected lies: an item
        row's ``now`` is None and its ``where`` "", and a level's rows are
        its spot classes, not the groups of the items there. ``held`` is
        the game's own count by item row key (``obsidian``, ``frag/air``).
        With ``gems`` (Step R1.43) each level's rows end in its Gems (taken,
        left, in all; no Now), and the levels' tree in All gems, after All."""
        pool, held = self.logic.pool, held or {}
        gem_counts = self.gem_counts() if gems else {}

        def row(key, label, locs, children=(), now=spoiler, where=False, game=None) -> Row:
            left = [loc for loc in locs if loc not in self.collected]
            return Row(key, label, len(locs) - len(left), sum(loc in self.reachable for loc in left) if now else None,
                       len(locs), ", ".join(sorted({pool[loc] for loc in left})) if where else "", game,
                       tuple(children))

        kinds = defaultdict(list)       # (group, kind) -> its spots
        for loc in sorted(self.spots):
            kinds[kind_of(self.item(loc))].append(loc)
        items = []
        for group, name in GROUPS.items():
            subs = _ordered({k for g, k in kinds if g == group}, KINDS.get(group, ()))
            children = []
            for k in filter(None, subs):          # obsidians have no kinds
                r = row(f"{group}/{k}", k if group in ("key", "other") else k.capitalize(), kinds[group, k],
                        where=spoiler, game=held.get(f"{group}/{k}"))
                children.append(replace(r, label=f"{r.label} (level {r.got})")
                                if group == "power" and k in ELEMENTS[:4] and r.got else r)
            if subs:
                items.append(row(group, name, [loc for k in subs for loc in kinds[group, k]], children,
                                 where=spoiler and not children, game=held.get(group)))

        by_level = defaultdict(list)
        for loc in sorted(self.spots):
            by_level[pool[loc]].append(loc)

        def level(lv: str, label: str) -> Row:
            names, parts = GROUPS if spoiler else SPOT_CLASSES, defaultdict(list)
            for loc in by_level[lv]:    # its spots by their items' groups (spoiler), else by class
                parts[kind_of(self.item(loc))[0] if spoiler else self.spot_class[loc]].append(loc)
            children = [row(f"{lv}/{p}", names[p], parts[p], now=True) for p in names if p in parts]
            if lv in gem_counts:        # its gems taken and in all (Live's alone: none reachable now)
                children.append(Row(f"{lv}/gems", "Gems", gem_counts[lv][0], None, gem_counts[lv][1]))
            return row(lv, label, by_level[lv], children, now=True)

        levels = []
        for name, lvs in realms(by_level):
            levels.append(level(lvs[0], name) if lvs == [name.lower()] else      # life, town: a level of their own
                          row(name.lower(), name, [loc for lv in lvs for loc in by_level[lv]],
                              [level(lv, lv) for lv in lvs], now=True))
        every = sorted(self.spots)
        total = [Row("gems", "All gems", sum(n for n, _ in gem_counts.values()), None,
                     sum(t for _, t in gem_counts.values()))] if gems else []
        return (*items, row("all", "All", every)), (*levels, row("all", "All", every, now=True), *total)
