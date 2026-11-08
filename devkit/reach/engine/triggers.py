"""The rigs' triggers (Step R2.19h2; D826, D847): what starts each moving solid, read from the level's own wiring,
and the RAM poke that starts it in the game's own code.

A rig is a solid platform owner whose ancestor transforms' translate, rotate or scale plugs links move
(``Level.mover_of``); each such link is a **mover**.  A mover's start (:meth:`Triggers.motion`) follows the link's
source back through the node types whose updates the XBE gives ([verified static: ``docs/RE_XBE.md`` § "Rig
triggers"]), and reads the boolean ones with :class:`~azurkit.tools.randomizer.draft.wiring.Wiring`'s rules:

- a timer's ``currentTime`` steps by ``rate``/30 while its ``enable`` is non-zero, wrapping with ``repeat``, else
  held at ``stopTime`` (0x6BAD0): it moves when enabled with a span, each input as its links set it at load (a
  one-shot run from load counts as load);
- a randomNumber's ``output`` draws a new number every ``updateTime`` while its ``enable`` is (0x70260): a wobble;
- a damper's ``output`` steps toward ``goal`` at ``rate`` while its ``enable`` is (0x6BBE0): it moves when its goal
  changes while enabled;
- a blendWeighted's ``output`` is the sum of ``input[i] x weight[i]`` over the record's count (0x70390): it moves
  when an input with a non-zero or linked weight moves;
- a combiner's xor or xnor (codes 8 and 14) flips when any input flips, its sum (1) moves when any input does and
  its product (3) when one does while the others are non-zero at load; its select (10) when its index or the
  selected input does; a max's or min's ``index``, which its update sets to the input that passed the current one
  (0x69C10), when any input does;
- a switch, latch, the other combiners and a pad flip when the wiring says (a 0 output's ``on``, a non-zero one's
  ``off``); a switch whose inputs the wiring can't read when the input that wins in 0x6A0F0 first changes
  (unlocked: turnOn, then turnOff, then a toggle; locked, at its goal: the toggle first);
- a latch bound to a global (``shared.sav``) is set by an earlier level (the atom ``global:<name>``) or by a latch
  of that name here whose ``update`` and ``input`` turn on (0x6A2E0, 0x6A350, 0x5ED70);
- an input fed by a node the wiring doesn't read (a random number, an xor, a select) changes when that node moves; a
  linked input plug (a transform channel, a weight) moves when its links' sources do, but a timer's link whose
  curve is flat over the timer's span at load only when the span changes; an unlinked transform channel is set
  by the engine (undecoded).

A :class:`Start` is ``load`` (it moves with no event), ``wired`` (a DNF over the wiring's atoms: pads, items), ``never``
or ``undecoded`` (its ``leaves`` name the node types and plugs not decoded: parked by name, D847).  A ``wired`` start
with leaves is partial: one way decoded, another not.  A rig's start is its movers' (:meth:`Triggers.rig`).

:meth:`Triggers.tries` are the writes that make each term of a start hold, smallest first: a pad's pulse plug (``touch``,
``actionButton``, ``whack``, ``joystickOn``; a magic hit's ``magic`` at level 1), an arrival's ``teleported``, a key's
``key``, a death's ``numDead``, a global's latches' ``output``; an item counter or armour atom has none, so the
mover's own source input is poked instead (a timer's or random number's ``enable``, a switch's ``turnOn`` or ``turnOff``, a damper's ``enable`` and
``goal``): a witness of the motion, not of the condition (``Poke.of`` says which).

:class:`Runtime` finds the level's node graphs in an L3 snapshot's memory and holds pokes at the per-frame graph
pass, so the game's own update and links run them: world (the scene ``[0x1BF63C]`` +0x2C) +0xDC the level's graph and
+0x108..+0x10C the others (the load's pass 0x54238/0x54258); a graph's node vector +0x24..+0x28 in record order; a
node's attribute floats at ``[+0x08]`` (0x65880 copies the record's there), its dirty mask at +0x10 (bit i for
attribute i < 30, bit 31 for the rest and the whole node), its type at ``[+0x14]`` (+0xC the attribute count); the
pass 0x663B0 (``[esp+4]`` the graph) runs each dirty node's update (vtable +0x14) and then its links.  A platform
node's collision object is at its +0x20 (vtable 0x19C810, its node at +0x294, its world matrix at +0x170: the
loader's call 0x6A953 to 0x79310), so a witness reads the deck where the game collides with it.

Coordinates stay in memory: nothing here prints or stores one.
"""

from __future__ import annotations

import struct
from typing import NamedTuple

from azurkit.tools.randomizer import levels as L
from azurkit.tools.randomizer.draft import envelope
from azurkit.tools.randomizer.draft.geometry import CAT_RIG
from azurkit.tools.randomizer.draft.wiring import F_FALSE, F_TRUE, Wiring, f_and, f_or
from azurkit.tools.randomizer.art import collision

PASS = 0x663B0            # the per-frame graph pass (``[esp+4]`` the graph; RET 4)
PLATFORM_VTABLE, NODE_OBJ, OBJ_NODE, OBJ_WORLD = 0x19C810, 0x20, 0x294, 0x170   # a platform node's collision object
WORLD_OF_SCENE, LEVEL_GRAPH, GRAPHS = 0x2C, 0xDC, (0x108, 0x10C)
NODES, ATTRS, DIRTY, TYPE, TYPE_COUNT = (0x24, 0x28), 0x08, 0x10, 0x14, 0x0C
PADS = {"touch": "touch", "action": "actionButton", "whack": "whack", "joystick": "joystickOn", "hit": "magic"}
SUM, PRODUCT, MAX, MIN, SELECT, XOR, XNOR = 1, 3, 4, 5, 10, 8, 14
CLOCK = "gameState (day night timer)"   # the day's clock, 600 s a day (0x55920): a wait, no event


class Start(NamedTuple):
    kind: str                     # load | wired | never | undecoded
    on: frozenset | None          # the DNF under which it starts: F_TRUE load, F_FALSE never, None undecoded
    leaves: frozenset             # "type.plug" of what it rests on that isn't decoded


class Poke(NamedTuple):
    G: int
    R: int
    plug: str
    value: float
    of: str                       # "condition" (an atom of the start's term) or "source" (the mover's own input)


def _start(on, leaves=frozenset()) -> Start:
    leaves = frozenset(leaves)
    if on is None or (not on and leaves):
        return Start("undecoded", None, leaves or frozenset({"too many terms"}))
    if on == F_TRUE:
        return Start("load", F_TRUE, leaves)
    return Start("never", F_FALSE, leaves) if not on else Start("wired", on, leaves)


def any_of(*ss: Start) -> Start:
    """It moves when any of these does."""
    on = [s.on for s in ss if s.on is not None]
    return _start(f_or(*on) if on else None, frozenset().union(*(s.leaves for s in ss)))


def all_of(*ss: Start) -> Start:
    return _start(f_and(*(s.on for s in ss)), frozenset().union(*(s.leaves for s in ss)))


LOAD, NEVER = Start("load", F_TRUE, frozenset()), Start("never", F_FALSE, frozenset())


class Triggers:
    """One level's rig starts over its :class:`Wiring` (``lv`` a ``geometry.Level``)."""

    def __init__(self, lv, wire: Wiring):
        self.lv, self.w = lv, wire
        self.memo: dict = {}
        self.stack: set = set()
        self.key_rec = {at: rec for rec, at in wire.key_atom.items() if at}
        self.dead_rec = {at: rec for rec, at in wire.dead_atom.items()}
        self.globals: dict[str, list] = {}         # a global's name -> this level's latches bound to it
        for G, g in enumerate(lv.graphs):
            for r, t in enumerate(g.types):
                if t == "latch" and (nm := g.pstr(g.recs[r], 0x18)):
                    self.globals.setdefault(nm, []).append((G, r))
        self.global_of = {rec: nm for nm, recs in self.globals.items() for rec in recs}

    # ---- the boolean reading (the wiring's)
    def flip(self, G, r, plug) -> Start:
        """A boolean signal leaves its load value: a 0's ``on``, a non-zero one's ``off``."""
        s = self.w.value(G, r, plug)
        if s.init is None:
            lv = self.why(G, r, plug)
            if s.on is not None and lv == {CLOCK}:
                return _start(s.on)        # a window of the day's clock: it turns on under ``on`` (a wait inside)
            return _start(None, lv)
        f = s.on if s.init == 0.0 else s.off
        return _start(f, self.why(G, r, plug) if f is None else ())

    def changes(self, G, r, plug) -> Start:
        """An input's first change: the wiring's flip where every link into it comes from a node the wiring reads
        (its outputs, gameState), else its links' sources' motion (a random number's, an xor's, a select's)."""
        g = self.w.g(G)
        lks = self.w.links_into(G, r, plug)
        if lks and not all(g.types[lk.src] in self.w.OUT or g.types[lk.src] == "gameState" for _, lk in lks):
            return self.motion(G, r, plug)
        f = self.flip(G, r, plug)
        return f if f.kind != "undecoded" or not lks else self.motion(G, r, plug)

    def why(self, G, r, plug, depth=0, seen=None) -> frozenset:
        """The undecoded leaves under a signal the wiring can't read (type and plug names)."""
        seen = set() if seen is None else seen
        if (G, r, plug) in seen or depth > 16:
            return frozenset({"a feedback loop"})
        seen.add((G, r, plug))
        s = self.w.value(G, r, plug)
        if s.on is not None and s.off is not None and s.init is not None:
            return frozenset()
        g = self.w.g(G)
        t = g.types[r]
        if plug in self.w.OUT.get(t, ()):
            ins = {"switch": ("turnOn", "turnOff", "toggle"), "damper": ("goal",), "latch": ("update", "input"),
                   "timer": ("enable",)}.get(t, ())
            if t == "combiner":
                n, fn = L.combiner_header(g, r)
                if fn not in (1, 3, 4, 5, 6, 7, 9, 12, 13):
                    return frozenset({f"combiner fn {fn}"})
                ins = tuple(f"inputs[{q}]" for q in range(min(n, 16)))
            out = frozenset().union(*(self.why(G, r, p, depth + 1, seen) for p in ins)) if ins else frozenset()
            return out or frozenset({f"{t}.{plug}"})
        lks = self.w.links_into(G, r, plug)
        if not lks:
            return frozenset({f"{t}.{plug} (engine-set)"})
        out = set()
        for _, lk in lks:
            st, sp = g.types[lk.src], g.plug_name(lk.src, lk.src_plug)
            if st == "timer" and sp == "currentTime":
                out |= self.why(G, lk.src, "enable", depth + 1, seen)
            elif st == "gameState":
                out.add("gameState (" + (L.gamestate_vars(g, lk.src).get(lk.src_plug, "") or "?") + ")")
            elif sp in self.w.OUT.get(st, ()):
                out |= self.why(G, lk.src, sp, depth + 1, seen)
            else:
                out.add(f"{st}.{sp}")
        return frozenset(out) or frozenset({f"{t}.{plug}"})

    def init(self, G, r, plug, depth=0) -> float | None:
        """A plug's value at load: the wiring's, else a combiner's over its inputs' (0x69C10) or a single link's
        from its source's; None when not read."""
        v = self.w.value(G, r, plug).init
        if v is not None or depth > 12:
            return v
        g = self.w.g(G)
        if g.types[r] == "combiner" and plug == "output":
            n, fn = L.combiner_header(g, r)
            ins = [self.init(G, r, f"inputs[{q}]", depth + 1) for q in range(min(n, 16))]
            return None if None in ins else L.combine(fn, ins, self.w.attrs(G, r).get("index", 0.0))
        lks = self.w.links_into(G, r, plug)
        if len(lks) != 1:
            return None if lks else self.w.attrs(G, r).get(plug, 0.0)
        k, lk = lks[0]
        x = self.init(G, lk.src, g.plug_name(lk.src, lk.src_plug), depth + 1)
        try:
            return None if x is None else L.link_value(L.link_curve(g, lk.src, k), x, lk.weight, lk.factor)
        except (ValueError, struct.error):
            return None

    # ---- motion
    def motion(self, G, r, plug) -> Start:
        """When the value at (G, r, plug) starts to change (the module docstring)."""
        key = (G, r, plug)
        if key in self.memo:
            return self.memo[key]
        if key in self.stack:
            return _start(None, {"a feedback loop"})
        self.stack.add(key)
        try:
            s = self._motion(G, r, plug)
        except (ValueError, KeyError, IndexError, struct.error):
            s = _start(None, {f"{self.w.g(G).types[r]}.{plug} (unreadable)"})
        self.stack.discard(key)
        self.memo[key] = s
        return s

    def _gate(self, G, r, plug) -> Start:
        """An enable: on at load, or when it first changes from 0 (:meth:`changes`)."""
        s = self.w.value(G, r, plug)
        if s.init is not None and s.init != 0.0:
            return LOAD
        return self.changes(G, r, plug)

    def _global(self, name) -> Start:
        """A global latch's output (0x6A2E0 binds it to the global ``name`` of ``shared.sav`` and loads its value;
        0x6A350, while ``update``, copies ``input`` to it and to the global, whose other latches 0x5ED70 tells):
        it is set by an earlier level's latch (the atom ``global:<name>``: its value at this load) or here by a
        latch of that name whose ``update`` and ``input`` both turn on."""
        here = [all_of(self._gate(G, r, "update"), self._gate(G, r, "input")) for G, r in self.globals[name]
                if self.w.links_into(G, r, "update") or self.w.links_into(G, r, "input")]
        return any_of(Start("wired", frozenset([frozenset([f"global:{name}"])]), frozenset()), *here)

    def _motion(self, G, r, plug) -> Start:
        w, g = self.w, self.w.g(G)
        t = g.types[r]
        a = w.attrs(G, r)
        if t == "timer" and plug == "currentTime":
            # current += rate/30 while enable, wrapping in [start, stop) with repeat, else held at stop; reset holds
            # it at start (0x6BAD0)
            # (each input as its links set it at load: every node starts dirty)
            gates = [self._gate(G, r, "enable")]
            rate = self.init(G, r, "rate")
            if rate == 0.0:
                if not w.links_into(G, r, "rate"):
                    return NEVER
                gates.append(self.motion(G, r, "rate"))
            t0, t1 = self.init(G, r, "startTime"), self.init(G, r, "stopTime")
            done = self.init(G, r, "repeat") == 0.0 and (rate or 0.0) > 0.0 and t1 is not None and \
                a.get("currentTime", 0.0) >= t1
            span = [self.motion(G, r, p) for p in ("startTime", "stopTime") if w.links_into(G, r, p)]
            if done and w.links_into(G, r, "reset"):
                span.append(self.changes(G, r, "reset"))
            if (t0 is None or t1 is None or t1 != t0) and not done:
                span.append(LOAD)
            return all_of(*gates, any_of(*span) if span else NEVER)
        if t == "randomNumber" and plug == "output":
            return self._gate(G, r, "enable")
        if t == "damper" and plug == "output":
            return all_of(self._gate(G, r, "enable"), self.changes(G, r, "goal"))
        if t == "blendWeighted" and plug == "output":
            n = struct.unpack_from("<I", g.s, g.recs[r] + 0x18)[0]
            ins = []
            for q in range(min(n, 10)):
                wl = w.links_into(G, r, f"weight[{q}]")
                if wl or a.get(f"weight[{q}]", 0.0) != 0.0:
                    ins.append(self.motion(G, r, f"input[{q}]"))
                if wl:
                    ins.append(self.motion(G, r, f"weight[{q}]"))
            return any_of(*ins) if ins else NEVER
        if t == "combiner" and plug == "output":
            n, fn = L.combiner_header(g, r)
            ins = [f"inputs[{q}]" for q in range(min(n, 16))]
            if fn in (XOR, XNOR, SUM):
                return any_of(*(self.motion(G, r, p) for p in ins))
            if fn == PRODUCT and (f := self.flip(G, r, plug)).kind == "undecoded":
                # a product moves with an input while every other input is non-zero
                v0 = [self.init(G, r, p) for p in ins]
                return any_of(*(self.motion(G, r, p) if all(x not in (None, 0.0) for j, x in enumerate(v0) if j != i)
                                else _start(None, f.leaves) for i, p in enumerate(ins)))
            if fn == SELECT:              # in[index]: it moves when the index or the selected input does
                q = self.init(G, r, "index")
                q = min(max(int(q if q is not None else a.get("index", 0.0)), 0), max(n - 1, 0))
                return any_of(self.motion(G, r, f"inputs[{q}]"),
                              *([self.motion(G, r, "index")] if w.links_into(G, r, "index") else []))
            return self.flip(G, r, plug)
        if t == "latch" and plug == "output" and (G, r) in self.global_of:
            return self._global(self.global_of[(G, r)])
        if t == "switch" and plug == "output":
            f = self.flip(G, r, plug)
            if f.kind != "undecoded":
                return f
            # the wiring can't read an input (an xor's, a select's).  0x6A0F0: unlocked, a non-zero turnOn sets the
            # goal 1, else turnOff 0, else a toggle that changed flips it; locked, only at its goal, and the toggle
            # first.  So from 0 turnOn's change moves it, and the toggle's when it is locked or turnOff stays 0; from
            # non-zero turnOff's when turnOn stays 0, and the toggle's when locked or turnOn stays 0
            zero = {p: not w.links_into(G, r, p) and a.get(p, 0.0) == 0.0 for p in ("turnOn", "turnOff")}
            locks = bool(w.links_into(G, r, "lock")) or a.get("lock", 0.0) != 0.0
            if a.get("output", 0.0) == 0.0:
                ins = ["turnOn"] + (["toggle"] if locks or zero["turnOff"] else [])
            else:
                ins = (["turnOff"] if zero["turnOn"] else []) + (["toggle"] if locks or zero["turnOn"] else [])
            return any_of(*(self.motion(G, r, p) for p in ins)) if ins else _start(None, f.leaves)
        if plug in w.OUT.get(t, ()):
            return self.flip(G, r, plug)
        if t == "combiner" and plug == "index" and L.combiner_header(g, r)[1] in (MAX, MIN):
            # a max or min writes the index of the input that passed the current one (0x69CEF-0x69D25, 0x69FFB)
            return any_of(*(self.motion(G, r, f"inputs[{q}]") for q in range(min(L.combiner_header(g, r)[0], 16))))
        lks = w.links_into(G, r, plug)
        if not lks:
            if g.schema.is_a(t, "transform") and plug in collision.TRS_PLUGS:
                return _start(None, {f"{t}.{plug} (engine-set)"})
            return NEVER                     # a stored constant
        out = []
        for k, lk in lks:
            st, sp = g.types[lk.src], g.plug_name(lk.src, lk.src_plug)
            if st == "gameState":
                var = L.gamestate_vars(g, lk.src).get(lk.src_plug, "").lower()
                out.append(LOAD if var == "day night timer" else _start(None, {f"gameState ({var or '?'})"}))
            elif st == "timer" and sp == "currentTime" and self._flat(G, lk.src, k, lk):
                # the link's curve is flat over the timer's span at load: only a new span can carry motion
                out.append(all_of(self._gate(G, lk.src, "enable"),
                                  any_of(*(self.motion(G, lk.src, q) for q in ("startTime", "stopTime")
                                           if w.links_into(G, lk.src, q)))))
            else:
                out.append(self.motion(G, lk.src, sp))
        return any_of(*out)

    def _flat(self, G, src, k, lk) -> bool:
        """Does a timer's link deliver one value over the timer's span as its inputs stand at load?"""
        t0, t1 = self.init(G, src, "startTime"), self.init(G, src, "stopTime")
        if t0 is None or t1 is None:
            return False
        try:
            cv = L.link_curve(self.w.g(G), src, k)
            vals = {L.link_value(cv, t0 + (t1 - t0) * q / 48.0, lk.weight, lk.factor) for q in range(49)}
        except (ValueError, struct.error):
            return False
        return len(vals) == 1

    # ---- rigs
    def movers(self, oi: int) -> list[tuple]:
        """(ancestor record, its moved plug, source record, source plug) of each link that moves owner oi."""
        o = self.lv.owners[oi]
        g = self.lv.graphs[o["G"]]
        inc = g.incoming()
        out = []
        for a in g.ancestors(o["R"]):
            for lk, _ in inc.get(a, ()):
                pn = g.plug_name(a, lk.dst_plug)
                if pn in collision.TRS_PLUGS:
                    out.append((a, pn, lk.src, g.plug_name(lk.src, lk.src_plug)))
        return out

    def rig(self, oi: int) -> Start:
        """Owner oi's start: it moves when any of its movers does."""
        G = self.lv.owners[oi]["G"]
        ms = self.movers(oi)
        return any_of(*(self.motion(G, s, sp) for _, _, s, sp in ms)) if ms else NEVER

    def rigs(self) -> list[int]:
        """Every solid platform owner a link moves (``CAT_RIG`` with a mover)."""
        return [o["oi"] for o in self.lv.owners if o["kind"] == "platform" and o["cat"] == CAT_RIG and self.movers(o["oi"])]

    def exported(self, entries) -> list[int]:
        """The rig owners of the derive's exported ``rigs`` entries (``read_derived(level)["rigs"]``): each entry's
        owner of its name whose movers and axes (``Level.mover_of``, as the derive lists them) are the entry's, the
        one with the entry's deck area where two are, then the first; a ValueError names an entry no owner matches.
        A name alone doesn't do: twin rigs share it (e6's mirrors, d2's rock platforms) and the derive exports only
        those that join zones."""
        lv, rigs, used = self.lv, set(self.rigs()), []
        up = lv.tri_nz >= envelope.STEP_NORMAL_Z

        def moved_as(oi, e):
            movers, axes = lv.mover_of(oi)
            return movers[:6] == list(e["movers"]) and axes == list(e["axes"])

        for e in entries:
            same = [oi for oi in lv.by_name.get(e["name"], []) if oi in rigs and oi not in used and moved_as(oi, e)]
            if not same:
                raise ValueError(f"{e['name']}: no rig owner of that name moved by {e['movers']}")
            deck = [oi for oi in same if round(float(lv.tri_area[(lv.tri_owner == oi) & up].sum()), 1) == e["deck_m2"]]
            used.append((deck or same)[0])
        return sorted(used)

    # ---- pokes
    def atom_pokes(self, atom: str) -> list[Poke] | None:
        """The writes that make one atom hold, or None (an item counter or armour atom)."""
        kind, _, rest = atom.partition(":")
        if kind in PADS:
            G, R = map(int, rest.split(":"))
            return [Poke(G, R, PADS[kind], 1.0, "condition")]
        if kind == "arrive":
            G, R = map(int, rest.split(":"))
            return [Poke(G, R, "teleported", 1.0, "condition")]
        if atom in self.key_rec:
            G, R = self.key_rec[atom]
            return [Poke(G, R, "key", 1.0, "condition")]
        if atom in self.dead_rec:
            G, R = self.dead_rec[atom]
            return [Poke(G, R, "numDead", 1.0, "condition")]
        if kind == "global" and rest in self.globals:
            return [Poke(G, R, "output", 1.0, "condition") for G, R in self.globals[rest]]
        return None

    def source_pokes(self, G, r, plug) -> list[Poke]:
        """The writes on a mover's own source that start it (none for a type with no input to set)."""
        g, a = self.w.g(G), self.w.attrs(G, r)
        t = g.types[r]
        if t in ("timer", "randomNumber"):
            return [Poke(G, r, "enable", 1.0, "source")]
        if t == "damper":
            return [Poke(G, r, "enable", 1.0, "source"),
                    Poke(G, r, "goal", 0.0 if a.get("goal", 0.0) else 1.0, "source")]
        if t == "switch":
            on = a.get("output", 0.0) == 0.0
            return [Poke(G, r, "turnOn" if on else "turnOff", 1.0, "source")]
        return []

    def tries(self, oi: int) -> list[list[Poke]]:
        """The ways to start owner oi, best first: each term of its start (smallest first) with a write for every
        atom, then the wired or undecoded movers' source pokes (none for a load or never start).  A term may not
        move it from where it stands (an elevator called to the floor it is at), so a witness tries them in turn."""
        st = self.rig(oi)
        if st.kind in ("load", "never"):
            return []
        out = []
        for t in sorted(st.on or (), key=lambda t: (len(t), sorted(t))):
            ps = [self.atom_pokes(x) for x in sorted(t)]
            if all(p is not None for p in ps):
                out.append([p for ps_ in ps for p in ps_])
        G = self.lv.owners[oi]["G"]
        src = []
        for _, _, s, sp in self.movers(oi):
            if self.motion(G, s, sp).kind in ("wired", "undecoded"):
                src += [p for p in self.source_pokes(G, s, sp) if p not in src]
        return out + ([src] if src else [])

    def pokes(self, oi: int) -> list[Poke]:
        """The first of :meth:`tries` (empty for a load or never start)."""
        return next(iter(self.tries(oi)), [])


class Runtime:
    """The level's node graphs in an L3 sim's memory (the module docstring): ``node(G, R)`` the runtime node of a
    record, ``attr_va(G, R, plug)``, ``read`` and :meth:`hold` (pokes written at each graph pass's entry)."""

    def __init__(self, sim, lv):
        self.sim, self.lv = sim, lv
        u = sim.u32
        world = u(u(0x1BF63C) + WORLD_OF_SCENE)
        lo, hi = u(world + GRAPHS[0]), u(world + GRAPHS[1])
        graphs = [u(world + LEVEL_GRAPH)] + [u(lo + 4 * i) for i in range((hi - lo) // 4)]
        self.graph = {}
        for G, xg in enumerate(lv.graphs):
            want = [len(xg.schema.types[t].attrs) for t in xg.types]
            for gp in graphs:
                a, b = u(gp + NODES[0]), u(gp + NODES[1])
                if (b - a) // 4 != len(want) or gp in self.graph.values():
                    continue
                vec = struct.unpack(f"<{len(want)}I", sim.read(a, 4 * len(want)))
                if all(nd and u(u(nd + TYPE) + TYPE_COUNT) == c for nd, c in zip(vec, want)):
                    self.graph[G] = gp
                    break
        self._held: dict[int, list] = {}
        self._hook = None

    def node(self, G: int, R: int) -> int:
        gp = self.graph[G]
        return self.sim.u32(self.sim.u32(gp + NODES[0]) + 4 * R)

    def index(self, G: int, R: int, plug: str) -> int:
        g = self.lv.graphs[G]
        return list(g.schema.types[g.types[R]].attrs).index(plug)

    def attr_va(self, G: int, R: int, plug: str) -> int:
        return self.sim.u32(self.node(G, R) + ATTRS) + 4 * self.index(G, R, plug)

    def deck(self, G: int, R: int) -> int | None:
        """A platform record's collision object (node +0x20; its vtable 0x19C810 and its +0x294 back at the node,
        0x6A953 -> 0x79310), or None."""
        nd = self.node(G, R)
        obj = self.sim.u32(nd + NODE_OBJ) if nd else 0
        ok = obj and self.sim.u32(obj) == PLATFORM_VTABLE and self.sim.u32(obj + OBJ_NODE) == nd
        return obj if ok else None

    def pose(self, obj: int):
        """A collision object's world matrix (16 f32, row vectors: world = local @ M[:3, :3] + M[3, :3])."""
        return struct.unpack("<16f", self.sim.read(obj + OBJ_WORLD, 64))

    def read(self, G: int, R: int, plug: str) -> float:
        return struct.unpack("<f", self.sim.read(self.attr_va(G, R, plug), 4))[0]

    def write(self, p: Poke) -> None:
        """Set a node's attribute and its dirty bit, as a link's push does (0x66490-0x664A7)."""
        i = self.index(p.G, p.R, p.plug)
        nd = self.node(p.G, p.R)
        self.sim.write(self.sim.u32(nd + ATTRS) + 4 * i, struct.pack("<f", p.value))
        bit = (1 << i) if i < 30 else 0x80000000
        self.sim.write(nd + DIRTY, struct.pack("<I", self.sim.u32(nd + DIRTY) | bit))

    def hold(self, pokes: list[Poke]) -> None:
        """Write ``pokes`` at the entry of every pass over their graphs until :meth:`hold` ``([])``: a pulse the
        collision object zeroes each frame (0x7A280) is set again before the pass reads it."""
        from unicorn import UC_HOOK_CODE
        from unicorn import x86_const as X
        self._held = {}
        for p in pokes:
            self._held.setdefault(self.graph[p.G], []).append(p)
        if self._hook is None:
            sim = self.sim

            def at_pass(uc, addr, size, _):
                if self._held:
                    gp = sim.u32(uc.reg_read(X.UC_X86_REG_ESP) + 4)
                    for p in self._held.get(gp, ()):
                        self.write(p)
            self._hook = sim.uc.hook_add(UC_HOOK_CODE, at_pass, begin=PASS, end=PASS)
