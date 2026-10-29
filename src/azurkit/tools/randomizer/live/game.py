"""The live tracker's game reads: which level the player is in, which tracked spots the game holds taken, and
which spot each pickup was (Step R1.26, D249; docs/RE_DATA.md "Live pickups").

A link (:mod:`azurkit.tools.randomizer.live_link`) reads guest memory; :class:`Game` reads the game through it,
every address a USA VA taken to the running release's (:meth:`Region.va`, the release read from the XBE header
in guest RAM), and no code: the scene chain (:mod:`azurik_mod.sim.recipes`), the save device's slot path, the
inventory, the player critter and, for each tracked spot of the level, its critterGenerator node in the level's
main graph, whose numDead (a f32 at ``[node+8]+0x20``) goes 0 -> 1 when the player takes its item.
:class:`Follower` turns readings into events (pure):

- :class:`Took`: a spot's numDead rose and, by the next running poll, the inventory (or HP) changed the way the
  plan's item there should (:func:`pair_key`), at the rise's running poll or the next, each change spent once,
  on the newest rise without one; a popup, pause or cutscene (the event clock frozen) holds a rise, never
  expires it. A rise unpaired after 2 s of event-clock time is :class:`Unpaired`, logged and not marked.
- :class:`Level`: at each settle of a level, its saved spots taken and not, and its unsaved ones taken this
  visit (they reset every visit).
- :class:`Held`: the spots whose planned item is one the inventory holds only from that spot (a fragment, a
  one-copy key, the ammo power), and the fragment spots whose fragment isn't held.
- :class:`Reload`: the inventory's day clock fell (a death, Continue, Load Game, an xemu loadvm), or another
  timeline began: a load onto another saved slot, or a new game (one entered from a saved slot told once it
  leaves its training room: a load back onto that slot is a stored-power trip, the same timeline).

A level whose spots name another seed's or build's items gives none (its :attr:`Reading.mismatch`).

:class:`Session` polls a link with both; :func:`connect` opens one. Nothing here prints guest bytes.
"""

from __future__ import annotations

import collections
import logging
import math
import re
import struct
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType

from azurkit.tools.randomizer.live.regions import REGIONS, Region, UnmappedAddressError
from azurkit.tools.randomizer import writer
from azurkit.tools.randomizer.live.errors import LiveError
from azurkit.tools.randomizer.live import recipes

log = logging.getLogger(__name__)

# USA VAs (each through Region.va): the scene global, the critterGenerator node's vtable, its owner
# sub-object's (node+0x40) and the save device's ([scene+0x28]); the XBE header (the same in every release).
ADDRESSES = {"scene": recipes.SCENE_PTR, "generator": 0x19D6B8, "owner": 0x19D698, "device": 0x19E240}
HEADER, HEADER_SIZE = 0x10000, 0x160
SCENE_DEVICE = 0x28
PD_GRAPH = 0xDC           # the level's main graph (the one its save list holds)
GRAPH_VEC = 0x24          # its node vector [begin, end): one pointer a record
NODE_ATTRS, NODE_OWNER, NODE_SPECIES = 0x08, 0x40, 0x48
NAME_MAX = 32             # a species name's bytes read (each page's part read apart: the next may be unmapped)
ATTR_COUNTS = 0x18        # numGenerated, numAlive, numDead (f32 attributes 6-8)
DEVICE_PATH = 0x20A       # the save device's slot path, "u:\<id>\" ("" a new game not yet saved)
INV_READ, INV_PD = 0x1DC, 0x1D8   # the inventory read, its back-pointer to pd
CR_ENTITY = 0x180
ENT_CLOCK = 0x18          # the entity: its event clock (f64 s), +8 its critter, +0x20 the feet (3 f32)
EPS = 1 / 600             # a second of game time on the day clock (days)
JUMP_S = 5.0              # an event-clock jump past this between polls is a discontinuity (an xemu loadvm)
PAIR_S = 2.0              # event-clock s a rise waits for its item's change
PAUSED_S = 5.0            # wall s of holds before the status says paused
NEW_GAME_LEVEL = "training_room"   # a new game's first level, every element at 1, its clock near 0 [U25, AZ-478]
WAITING_S = 2.0           # the poll period while xemu runs no Azurik
FUELS = ("ef", "af", "ff", "wf")   # the element fuels all_fuel fills


# ---------------------------------------------------------------- the spots

@dataclass(frozen=True)
class Spot:
    """A tracked spot as Live reads it: its pool level, its graph and record (None: in a characters graph,
    with no level node), the plan's item, its kind (``S`` saved, ``U`` unsaved: numDead resets every visit,
    ``C`` characters graph), the inventory field that holds its item from this spot only (None: none) and
    the species its node names for that item ("": the item; a ``_move`` spot's vanilla item keeps its
    template, ``obsidian_move``, as the writer does)."""
    loc: str
    level: str
    graph: int | None
    record: int | None
    item: str
    kind: str
    field: str | None = None
    species: str = ""


@dataclass(frozen=True)
class LevelSpots:
    level: str
    graph: int        # the main graph's index
    records: int      # its node count
    spots: tuple[Spot, ...]


@dataclass(frozen=True)
class SpotTable:
    """The plan's tracked spots by level, built on the Tk thread and handed to the worker."""
    levels: Mapping[str, LevelSpots]
    spots: tuple[Spot, ...]


def spot_table(tracker) -> SpotTable:
    """``tracker``'s spots (:class:`~azurkit.tools.randomizer.tracker.Tracker`) with their kinds, from the
    generated database: a location's ``saved`` and its id's graph and record."""
    db = tracker.logic.db
    names = writer.Names(db)
    items = [tracker.item(loc) for loc in sorted(tracker.spots)]
    fourcc = {k["key_type"]: k["key_fourcc"] for doc in db.generated.values() for k in doc.get("keylocks", ())
              if k.get("key_type")}
    by_level: dict[str, list[Spot]] = {}
    for level, doc in sorted(db.generated.items()):
        for loc in doc["locations"]:
            if loc["id"] not in tracker.spots:
                continue
            item = tracker.item(loc["id"])
            src, g, r = loc["id"].split("/")
            kind = "C" if src == "characters" else "S" if loc["saved"] else "U"
            by_level.setdefault(level, []).append(Spot(
                loc["id"], level, None if kind == "C" else int(g[1:]), None if kind == "C" else int(r[1:]), item,
                kind, unique_field(item, fourcc) if items.count(item) == 1 else None,
                "" if kind == "C" else names.target(loc["id"], item) or loc["template"]))
    levels = {}
    for level, spots in by_level.items():
        main = next(g for g in db.generated[level]["graphs"] if g.get("saved_nodes", 0) > 0)
        levels[level] = LevelSpots(level, main["g"], main["records"], tuple(spots))
    return SpotTable(MappingProxyType(levels), tuple(s for spots in by_level.values() for s in spots))


def unique_field(item: str, fourcc: Mapping[str, str]) -> str | None:
    """The inventory field holding a one-copy ``item`` (``fga2``, ``key:a1k1``, ``mpow``), None if none does."""
    if item in fourcc:
        return f"key:{fourcc[item]}"
    mode, f = pair_key(item)
    return f if mode == "flag" or item == "power_ammo" else None


def pair_key(item: str) -> tuple[str, str]:
    """How a pickup of ``item`` shows in the inventory or HP: (mode, field). ``count``: the field rises by one
    a pickup; ``flag``: a fragment's count 0 -> 1; ``rise``: max HP (power_life adds its amount) or a fuel
    (all_fuel, taken only below a cap) rises; ``alone``: nothing need change (all_health at full HP; an item
    Live doesn't know, logged). The fields are :func:`recipes.item_fields`' (a key: any slot, so their sum)."""
    fields = recipes.item_fields(item) or set()
    if len(fields) > 1:
        return "count", "keys"
    if (f := next(iter(fields), "")).startswith("fg"):
        return "flag", f
    if f.startswith("level.") or f == "obsi":       # (a gem's count isn't known to rise by one: alone)
        return "count", f
    return {"power_staff1": ("count", "spow"), "power_staff2": ("count", "spow"), "power_ammo": ("count", "mpow"),
            "power_life": ("rise", "maxhp"), "all_fuel": ("rise", "fuel"), "all_health": ("alone", "")
            }.get(item, ("alone", ""))


# ---------------------------------------------------------------- readings

@dataclass(frozen=True)
class Reading:
    """One poll of the game. ``state``: "waiting" (xemu runs no Azurik), "menus" (no player), "loading"
    (a level not settled), "hold" (settled, the event clock frozen: a popup, a pause, a cutscene) or
    "running". ``settle`` numbers the settles: a new one is a load or a discontinuity."""
    state: str
    region: Region | None = None
    path: str = ""
    level: str | None = None
    settle: int = 0
    mismatch: bool = False
    clock: float | None = None       # the inventory's day clock (days)
    event: float | None = None       # the player entity's event clock (s)
    slot: str | None = None          # the save device's slot path; None: unknown
    inv: Mapping[str, int] = field(default_factory=dict)
    hp: int | None = None
    maxhp: int | None = None
    at: tuple[float, float, float] | None = None
    yaw: float | None = None
    dead: Mapping[str, float] = field(default_factory=dict)

    @property
    def settled(self) -> bool:
        return self.state in ("hold", "running")

    @property
    def kit(self) -> dict[str, int] | None:
        """The element powers' levels the game holds (air, water, fire, earth), for the tracker's reach
        (:meth:`~azurkit.tools.randomizer.tracker.Tracker.set_kit`); None while not known: not settled, another
        seed's or build's level, or a new game's training room (every element at 1 for its lessons)."""
        if not self.settled or self.mismatch or not self.inv or self.level == NEW_GAME_LEVEL:
            return None
        return {e: self.inv.get(f"level.{e}", 0) for e in ("air", "water", "fire", "earth")}


def _cstr(b: bytes) -> str:
    return b.split(b"\0")[0].decode("latin-1")


def inventory(b: bytes) -> dict[str, int]:
    """:func:`recipes.inventory` of the inventory's bytes, plus ``keys`` (every key slot's count) and
    ``key:<fourcc>`` (its slots' counts)."""
    inv = recipes.inventory(b[:recipes.INV_SAVED])
    inv["keys"] = sum(inv[f"key{i}"] for i in range(5))
    for i in range(5):
        tag, n = struct.unpack_from("<4si", b, recipes.KEY0 + 12 * i)
        if tag.strip(b"\0"):
            inv[f"key:{tag.decode('latin-1')}"] = inv.get(f"key:{tag.decode('latin-1')}", 0) + n
    return inv


def ram_region(header: bytes) -> Region | None:
    """The release of the XBE header the kernel loaded at ``HEADER``, by its kernel-thunk word (+0x158): the
    kernel decodes it in place, so guest RAM holds the release's thunk address itself, not the file's
    XOR-encoded word that :func:`~azurik_mod.assets.vanilla.xbe_region` reads (sitting r1.26); None when
    it is neither release's."""
    if header[:4] != b"XBEH":
        return None
    thunk = struct.unpack_from("<I", header, 0x158)[0]
    return next((r for r in REGIONS if r.thunk_va == thunk), None)


class Game:
    """Reads the game through ``link`` (its ``read``, ``read_many``) for ``spots``: :meth:`read`."""

    def __init__(self, link, spots: SpotTable):
        self.link, self.spots = link, spots
        self.region: Region | None = None
        self._va: dict[str, int] = {}
        self._settles = 0
        self._forget()

    def _forget(self) -> None:
        """Back to no level: nothing resolved or settled (a load, a discontinuity, a reboot)."""
        self._graph = self._polls = 0
        self._settled = False
        self._player = (0, 0)
        self._event: float | None = None
        self._attrs: dict[str, int] = {}
        self._mismatch = False
        self._seen: dict[str, float] = {}    # numDead >= 1 read twice: not read again this settle
        self._twice: set[str] = set()

    def _u32(self, va: int) -> int:
        return struct.unpack("<I", self.link.read(va, 4))[0]

    def _header(self) -> bool:
        """Whether guest RAM's XBE header is Azurik's, its release taken (a new one re-derives every
        address); :class:`LiveError` (F5) when the release lacks one Live reads."""
        try:
            region = ram_region(self.link.read(HEADER, HEADER_SIZE))
        except OSError:
            region = None
        if region is None:
            self.region = None
            return False
        if region is not self.region:
            try:
                self._va = {name: region.va(va) for name, va in ADDRESSES.items()}
            except UnmappedAddressError as exc:
                raise LiveError(f"Live can't read {region.label} yet: {exc}.") from None
            self.region = region
            self._forget()
        return True

    def read(self) -> Reading:
        """One poll: never raises for a game state (an unreadable chain is "menus" while the header says
        Azurik, else "waiting"); :class:`~live_link.LinkLost` passes through."""
        if self.region is None and not self._header():
            return Reading("waiting")
        try:
            r = self._read()
        except OSError:
            r = None
        if r is None or r.state == "menus":   # the player went away (a hop, a death, a reboot): look again
            self._forget()
            if not self._header():
                return Reading("waiting")
            return r or Reading("menus", self.region)
        return r

    def _read(self) -> Reading | None:
        va, u32 = self._va, self._u32
        scene = u32(va["scene"])
        if not scene:
            return None
        device, pd = struct.unpack("<II", self.link.read(scene + SCENE_DEVICE, 8))
        if not pd:
            return None
        blk = self.link.read(pd, PD_GRAPH + 0x0C)
        path = _cstr(blk[recipes.PD_LEVEL:recipes.PD_LEVEL + 0x50])
        critter, graph, inv_at = (struct.unpack_from("<I", blk, o)[0]
                                  for o in (recipes.PD_PLAYER, PD_GRAPH, recipes.PD_INV))
        level = re.split(r"[\\/]", path)[-1].lower() or None
        slot = None
        if device and u32(device) == va["device"]:
            slot = _cstr(self.link.read(device + DEVICE_PATH, 32))
        base = Reading("menus", self.region, path, level, slot=slot)
        if not inv_at:
            return base
        ib = self.link.read(inv_at, INV_READ)
        inv_ok = struct.unpack_from("<I", ib, INV_PD)[0] == pd
        base = replace(base, clock=struct.unpack_from("<f", ib, 0)[0] if inv_ok else None,
                       inv=inventory(ib) if inv_ok else {})
        if not critter:
            return base
        entity = u32(critter + CR_ENTITY)
        e = self.link.read(entity + ENT_CLOCK, 0x2C)
        event, back = struct.unpack_from("<dI", e, 0)
        if back != critter or not math.isfinite(event):
            return base
        quat = struct.unpack("<4f", self.link.read(critter + recipes.CR_QUAT, 16))
        hp, maxhp = struct.unpack("<ii", self.link.read(critter + recipes.CR_HP, 8))
        at, yaw = struct.unpack_from("<3f", e, 0x20), 2 * math.atan2(quat[2], quat[3])
        r = replace(base, state="loading", event=event, hp=hp, maxhp=maxhp,   # a NaN or inf place: none
                    at=at if all(map(math.isfinite, at)) else None, yaw=yaw if math.isfinite(yaw) else None)
        return self._settle(r, pd, graph, (critter, entity), inv_ok)

    def _settle(self, r: Reading, pd: int, graph: int, player: tuple[int, int], inv_ok: bool) -> Reading:
        """The level's state once its load has settled (docs/RE_DATA.md "Live pickups"): the graph pointer
        unchanged for 2 polls, its node vector as long as its records, the player valid, the inventory
        pointing back at pd, a running poll for a first settle, each spot's node a generator of the plan's
        item; an event clock that jumps (back, or more than ``JUMP_S`` on) or a new player under the same graph
        is a discontinuity, settled anew."""
        prev, self._event = self._event, r.event
        if graph != self._graph or not graph:
            self._forget()
            self._graph, self._event = graph, r.event
        elif self._settled and (player != self._player or prev is None or r.event < prev
                                or r.event - prev > JUMP_S):
            self._forget()
            self._graph, self._event = graph, r.event
        self._polls += 1
        self._player = player
        running = prev is not None and r.event > prev
        lv = self.spots.levels.get(r.level)
        if not graph or not inv_ok:
            return r
        if not self._settled:
            b, e = struct.unpack("<II", self.link.read(graph + GRAPH_VEC, 8))
            if self._polls < 2 or not running or (lv and (e - b) // 4 != lv.records):
                return r
            if lv and not self._resolve(lv, b):
                return r
            self._settled = True
            self._settles += 1
        r = replace(r, state="running" if running else "hold", settle=self._settles, mismatch=self._mismatch)
        if self._mismatch or not self._attrs:
            return r
        want = [loc for loc in self._attrs if loc not in self._twice]
        got = self.link.read_many([(self._attrs[loc] + ATTR_COUNTS, 12) for loc in want])
        if self._u32(pd + PD_GRAPH) != graph or None in got:   # an unload began under the reads
            self._forget()
            return replace(r, state="loading", settle=0)
        for loc, b in zip(want, got):
            dead = struct.unpack("<3f", b)[2]
            if dead >= 1 and self._seen.get(loc, 0) >= 1:
                self._twice.add(loc)
            self._seen[loc] = dead
        return replace(r, dead=MappingProxyType(dict(self._seen)))

    def _resolve(self, lv: LevelSpots, vec: int) -> bool:
        """Each spot's attributes, once a load: False while a node isn't a critterGenerator yet; a species
        that isn't the plan's item as the writer names it (:attr:`Spot.species`) is a mismatch (another seed or
        build)."""
        spots = [s for s in lv.spots if s.kind != "C" and s.graph == lv.graph]
        try:
            nodes = self.link.read_many([(vec + 4 * s.record, 4) for s in spots])
            heads = self.link.read_many([(struct.unpack("<I", n)[0], NODE_SPECIES + 4) for n in nodes
                                         if n is not None])
            if None in nodes or None in heads:
                return False
            heads = [tuple(struct.unpack_from("<I", h, o)[0] for o in (0, NODE_ATTRS, NODE_OWNER, NODE_SPECIES))
                     for h in heads]
            if any(vt != self._va["generator"] or owner != self._va["owner"] for vt, _, owner, _ in heads):
                return False
            names = self.link.read_many([(sp, 4) for *_, sp in heads])
            if None in names:
                return False
            ptrs = [struct.unpack("<I", n)[0] for n in names]
            names = self.link.read_many([(p, min(NAME_MAX, 0x1000 - (p & 0xFFF))) for p in ptrs])
            if None in names:
                return False
            cut = [k for k, n in enumerate(names) if b"\0" not in n and len(n) < NAME_MAX]   # at a page's end
            rest = self.link.read_many([(ptrs[k] + len(names[k]), NAME_MAX - len(names[k])) for k in cut])
            if None in rest:
                return False
            for k, more in zip(cut, rest):
                names[k] += more
        except OSError:
            return False
        self._mismatch = any(_cstr(n) != (s.species or s.item) for s, n in zip(spots, names))
        self._attrs = {s.loc: attrs for s, (_, attrs, _, _) in zip(spots, heads)}
        return True


# ---------------------------------------------------------------- events

@dataclass(frozen=True)
class Took:
    """A fresh take of ``loc``, the day clock when it was taken."""
    loc: str
    clock: float


@dataclass(frozen=True)
class Level:
    """A settle of ``level``: its saved spots the game holds taken and not; its unsaved spots taken this visit
    and not (they reset every visit, so their 0 says nothing of an earlier one), and the day clock then, by
    which a reload to before it drops those (no settle shows them untaken)."""
    level: str
    taken: frozenset[str] = frozenset()
    untaken: frozenset[str] = frozenset()
    unsaved_taken: frozenset[str] = frozenset()
    unsaved_untaken: frozenset[str] = frozenset()
    clock: float | None = None


@dataclass(frozen=True)
class Held:
    """The spots whose planned one-copy item the inventory holds, and the fragment spots whose fragment it
    doesn't (``absent``: fragments are never spent)."""
    locs: frozenset[str]
    absent: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Reload:
    """The game went back to day clock ``clock``; ``new_timeline``: another saved slot, or a new game."""
    clock: float
    new_timeline: bool = False


@dataclass(frozen=True)
class Unpaired:
    """A spot's numDead rose with no change of its item: logged, not marked."""
    loc: str


def is_slot(path: str | None) -> bool:
    """A saved slot's path, ``u:\\<id>\\`` (not "" or a ``z:\\`` path)."""
    return bool(path) and path[:3].lower() == "u:\\" and len(path) > 3


@dataclass(eq=False)
class _Rise:
    loc: str
    mode: str
    field: str
    seen: int            # the running poll it rose at
    clock: float         # the day clock at the rise
    event: float         # the event clock at the rise
    settle: int
    dead: float
    confirmed: bool = False
    moved: bool = False  # its level unloaded before it paired: one chance, at the next level's first running poll
    paid: bool = False   # an item change is its own


def _snap(r: Reading) -> dict:
    return {**r.inv, "maxhp": r.maxhp, "hp": r.hp}


class Follower:
    """Readings to events (pure). ``journal``: the tracker's ``{"slot": the last saved slot seen, "newest":
    the newest fresh mark's day clock}``, for a session's first settle."""

    def __init__(self, spots: SpotTable, journal: Mapping | None = None):
        self.spots = spots
        self.by_loc = {s.loc: s for s in spots.spots}
        journal = journal or {}
        self.slot: str | None = journal.get("slot") or None
        self.newest: float | None = journal.get("newest")
        self.start: float | None = None  # the day clock a new game began at, until it is seen on a saved slot
        self.trip: str | None = None     # the saved slot a new game's training room was entered from (R1.41)
        self.first = True              # the next settle is a session's first, or the first since a reboot
        self.clock: float | None = None
        self.settle = 0
        self.loaded = False            # a load since the last settle
        self.dead: dict[str, float] = {}
        self.prev: dict | None = None  # the last running poll's inventory and HP
        self.polls = 0                 # running polls
        self.rises: list[_Rise] = []
        self.unpaired = 0
        self.resync = threading.Event()

    def step(self, r: Reading) -> list:
        if r.state == "waiting":
            self.first, self.rises, self.prev = True, [], None
        if not r.settled:
            self.loaded, self.dead = True, {}
            return []
        if r.mismatch:                 # another seed or build: no marks (the reading tells the tracker)
            self.settle = r.settle
            return []
        events: list = []
        fresh = r.settle != self.settle or self.resync.is_set()
        if fresh or self.first:
            events += self._timeline(r)
        elif r.clock is not None and self.clock is not None and r.clock < self.clock - EPS:
            events += self._timeline(r)     # a reload with no load: an xemu loadvm in the level
        elif self.trip is not None and is_slot(r.slot):
            events += self._trip_ends(r, back=False)   # a save in the training room: the new game's own
        if is_slot(r.slot):
            self.slot, self.start = r.slot, None   # a first save, a save into another slot: the journal moves
        if r.clock is not None:
            self.clock = r.clock
        if fresh:
            self.resync.clear()
            self.settle, self.loaded, self.first = r.settle, False, False
        if self.trip is not None:              # in a new game's training room: none of it is the timeline's yet
            return events
        if r.state == "running":               # a take first: the settle's marks don't take its clock away
            events += self._rises(r, fresh)
            self.prev = _snap(r)
            self.dead = dict(r.dead)
        if fresh:
            events += self._level(r)
            if not any(isinstance(e, Held) for e in events):
                events.append(self.held(r))
        return events

    def _timeline(self, r: Reading) -> list:
        """A Reload when the day clock fell (against the journal's newest mark at a session's first settle),
        new when the game landed on another saved slot or started anew (a fall into the training room, or a
        session's first settle there, on no saved slot: sitting r1.26 read a New Game's first settle there at
        day clock 0.003-0.007 with every element at 1, AZ-478, and a death there before the first save at 0;
        a level request into it runs the clock on and is the same game, AZ-481); after a new game, a load onto
        a saved slot is new unless the clock fell to between the new game's start and now (a death and Continue
        onto its first save). A new game entered from a saved slot is told only once it leaves its training
        room (:meth:`_trip_ends`): until then nothing is given."""
        if r.clock is None:
            return []
        if self.trip is not None:
            if r.level == NEW_GAME_LEVEL and not is_slot(r.slot):
                return []                     # still in the trip's training room (a death there, a stall)
            return self._trip_ends(r, back=is_slot(r.slot) and r.slot.lower() == self.trip.lower())
        fell = self.clock is not None and r.clock < self.clock - EPS
        fell |= self.first and self.newest is not None and r.clock < self.newest - EPS
        moved = fell or self.loaded or self.first
        landed = moved and is_slot(r.slot)
        if self.start is not None:    # a new game seen on no saved slot yet: one is its own only by a fall to it
            other = landed and not (fell and r.clock >= self.start - EPS)
        else:
            other = landed and is_slot(self.slot) and r.slot.lower() != self.slot.lower()
        new_game = (fell or self.first) and r.level == NEW_GAME_LEVEL and not is_slot(r.slot)
        if not (fell or other or new_game):   # a session's first settle on a new game: no fresh mark says fell
            return []
        self.rises, self.prev, self.dead = [], None, {}
        if new_game and is_slot(self.slot):  # a stored-power trip, maybe: told once it leaves the training room
            self.trip, self.start, self.slot = self.slot, r.clock, None
            return []
        self.newest = None if other or new_game or self.newest is None else min(self.newest, r.clock)
        if new_game:                  # its slot path is "" until its first save (or a Continue onto it) [U25]
            self.start, self.slot = r.clock, None
        return [Reload(r.clock, other or new_game), self.held(r)]

    def _trip_ends(self, r: Reading, back: bool) -> list:
        """A new game's training room left (R1.41): ``back`` on the saved slot it was entered from, a
        stored-power skip's trip (New Game, store a power at every element 1, quit, Load Game) is the same
        timeline, the takes since the save dropped by its day clock; else (on to a level not saved, a save, a
        load of another slot) the new game's own timeline."""
        self.trip, self.rises, self.prev, self.dead = None, [], None, {}
        if back:
            self.start = None
        self.newest = None if not back or self.newest is None else min(self.newest, r.clock)
        return [Reload(r.clock, not back), self.held(r)]

    def _level(self, r: Reading) -> list:
        lv = self.spots.levels.get(r.level)
        if not lv or not r.dead:
            return []
        kinds = {s.loc: s.kind for s in lv.spots}
        part = lambda kind, taken: frozenset(   # noqa: E731
            loc for loc, d in r.dead.items() if kinds[loc] == kind and (d >= 1) == taken)
        return [Level(lv.level, part("S", True), part("S", False), part("U", True), part("U", False), r.clock)]

    def held(self, r: Reading) -> Held:
        """The one-copy items the inventory holds now, by their spots (:class:`Held`)."""
        locs, absent = set(), set()
        for s in self.spots.spots:
            if s.field is None:
                continue
            if r.inv.get(s.field, 0) >= 1:
                locs.add(s.loc)
            elif s.field.startswith("fg"):
                absent.add(s.loc)
        return Held(frozenset(locs), frozenset(absent))

    def _rises(self, r: Reading, fresh: bool) -> list:
        """The running poll's rises: seen, confirmed by the next running poll, each paired with a change of
        its item from one running poll to the next (:meth:`_pay`); a characters-graph fragment by its count
        alone."""
        events, now = [], _snap(r)
        self.polls += 1
        if self.prev is not None:
            for s in self.spots.spots:          # a6's and f6's 4th fragments have no level node
                if s.kind == "C" and s.field and self.prev.get(s.field, 0) == 0 and now.get(s.field, 0) >= 1:
                    events.append(Took(s.loc, r.clock))
        keep, refund = [], collections.Counter()
        for rise in self.rises:
            if rise.settle != r.settle:           # its level unloaded: one chance, at this poll
                rise.moved = True
            elif not rise.confirmed:
                if r.dead.get(rise.loc, rise.dead) < rise.dead:
                    refund[rise.mode, rise.field] += rise.paid
                    continue                      # a torn read, gone again: its change goes back
                rise.confirmed = True
            keep.append(rise)
        if not fresh and self.prev is not None:
            pending = {x.loc for x in keep}
            for loc, d in r.dead.items():
                if loc not in pending and d > self.dead.get(loc, d):
                    item = self.by_loc[loc].item
                    mode, f = pair_key(item)
                    if mode == "alone" and item != "all_health":
                        log.info("live: a pickup of %s, an item Live doesn't pair, marks %s", item, loc)
                    keep.append(_Rise(loc, mode, f, self.polls, r.clock, r.event, r.settle, d))
        if self.prev is not None:
            self._pay(keep, self.prev, now, refund)
        paired = [x for x in keep if x.paid and (x.confirmed or x.moved)]
        gone = []
        for rise in keep:
            if rise in paired:
                events.append(Took(rise.loc, rise.clock))
                self.newest = max(self.newest or 0.0, rise.clock)
            elif rise.moved or rise.confirmed and r.event - rise.event > PAIR_S:
                gone.append(rise)               # a rise seen once and gone with its level gives nothing
                if rise.confirmed:
                    log.info("live: %s rose with no change of its %s: not marked", rise.loc, self.by_loc[rise.loc].item)
                    events.append(Unpaired(rise.loc))
        self.rises = [x for x in keep if x not in paired and x not in gone]
        self.unpaired += sum(isinstance(e, Unpaired) for e in events)
        return events

    def _pay(self, rises: list[_Rise], prev: dict, now: dict, refund) -> None:
        """Give this running poll's item changes since the last (``prev`` to ``now``) to the rises still
        without one, newest first: a pickup changes the inventory in its numDead's tick, so the change shows
        at its rise's poll, or the next when the reads straddled it (U4); a change is spent once, never on an
        older rise that had none (a non-pickup numDead rise, U11). By count where the field counts (two
        obsidians, obsi +2), a fragment's 0 -> 1 once; a max HP or fuel rise, whose size doesn't say how many,
        pays this poll's and the last's rises (one older one if none); ``refund``: changes a torn rise
        took back."""
        for key in dict.fromkeys((x.mode, x.field) for x in rises if not x.paid):
            mode, f = key
            group = sorted((x for x in rises if not x.paid and (x.mode, x.field) == key), key=lambda x: -x.seen)
            if mode == "alone":
                n = len(group)
            elif mode == "count":
                n = max(0, (now.get(f) or 0) - (prev.get(f) or 0))
            elif mode == "flag":
                n = int((prev.get(f) or 0) == 0 and (now.get(f) or 0) >= 1)
            else:
                rose = any((now.get(g) or 0) > (prev.get(g) or 0) for g in (FUELS if f == "fuel" else (f,)))
                n = max(1, sum(x.seen >= self.polls - 1 for x in group)) if rose else 0
            for x in group[:n + refund[key]]:
                x.paid = True


# ---------------------------------------------------------------- the session

@dataclass(frozen=True)
class Update:
    """One poll for the tracker: the reading, its events, and whether the game has been held for
    ``PAUSED_S`` (a pause, a popup left up, or xemu stopped)."""
    reading: Reading
    events: tuple = ()
    paused: bool = False
    unpaired: int = 0


class Session:
    """A link to xemu, the game read through it and the events it gives: :meth:`poll` every
    :attr:`period`."""

    def __init__(self, link, spots: SpotTable, journal: Mapping | None = None):
        self.link, self.game, self.follower = link, Game(link, spots), Follower(spots, journal)
        self.last = Reading("waiting")
        self._still: float | None = None       # wall time since the game last ran
        self._refreshed = 0.0

    def describe(self) -> str:
        return self.link.label()

    @property
    def period(self) -> float:
        return WAITING_S if self.last.state == "waiting" else self.link.period

    def poll(self) -> Update:
        """Read the game once; never raises for a game state."""
        r = self.game.read()
        self.last, now = r, time.monotonic()
        events = self.follower.step(r)
        self._still = None if r.state == "running" else self._still or now
        still = self._still is not None and now - self._still >= PAUSED_S
        if still and self.link.kind == "shm" and now - self._refreshed >= WAITING_S:
            self._refreshed = now        # a crashed xemu's name, frozen: open it anew; gone is LinkLost
            self.link.refresh()
        return Update(r, tuple(events), still and r.state == "hold", self.follower.unpaired)

    def resync(self) -> None:
        """The tracker was reset: the next settled poll gives its level's and the inventory's state again."""
        self.follower.resync.set()

    def close(self) -> None:
        self.link.close()
