"""The wiring: a monotone reading of a level's logic nodes.

Reach's gates, events and mechanisms (Step R1.3b; reach v6's
``Wiring``) need to know what starts each thing: which pads, pickups,
arrivals and items make a driven plug non-zero, and which make it zero.
The engine rules (``docs/RE_XBE.md``, the R0 evidence's
``thresholds/REPORT.md`` and ``wiring/REPORT.md``): links propagate every
frame (0x663B0) with every node fully dirty on its first frame; switches
0x6A0F0, combiners 0x69C10, gameState 0x711C0, latches 0x6A350; touch,
whack and magic are pulses (0x7A280).

A signal is read as two conditions in disjunctive normal form (a
frozenset of terms, each a frozenset of atoms): ``on``, under which it
can be made non-zero (and held, unless it is a pulse), and ``off``, under
which it can be zero; ``None`` is undecoded (fail closed), and ``init`` is
its value on the first frame with no event (``None`` when it depends on
something not decoded).  Atoms:

* pads (the player at a place): ``touch:G:R``, ``action:G:R``,
  ``whack:G:R``, ``joystick:G:R``, ``hit:G:R`` (a magic hit on a barrier
  or geode shape: the player within reach of it), ``arrive:G:R`` (a
  playerLocation's ``teleported``), ``loc:<location id>`` (a pickup
  generator's ``numDead``: the item collected);
* items (``docs/RANDOMIZER_DB.md`` §5.1 atoms, prefixed ``F:``):
  counters, ``button:`` (a keylock's key through its hand button),
  ``event:`` (keylords, bosses);
* ``armortype:N`` / ``armorlevel:N`` (gameState's armor slots; armor type
  6 is ``elec``, the air + fire cast [verified static 0x711C0]),
  resolved per term: type 6 with level >= L gives ``air>=L & fire>=L``
  [inferred: a combo cast's level is its elements' common level]; any
  other type, or a level alone, is undecoded (the term is dropped).

A day-night timer slot is a wait (true both ways) [inferred]; any other
non-monotone counter test holds only in ``off``.  AND over two different
pulses is undecoded.  A switch with no turnOff or toggle input is a
one-way latch; a stored non-zero turnOff makes it follow turnOn, which
``lock`` turns into a window [inferred: long enough to pass]; a timer's
currentTime runs from startTime to stopTime once enabled.

Also here: the blocker binding (a toggled solid's gameSolid traced at
most two hops back to a generated gate record, R0's
``route/blockers.py`` rule 2), the hand table of blocker families
(``blocker_families.toml``) and the requirement-string helpers.
Authoring only; nothing here prints or stores a coordinate.
"""

from __future__ import annotations

import collections
import re
import struct
import tomllib
from pathlib import Path

from azurkit.tools.randomizer import levels as L

FAMILIES_TOML = Path(__file__).with_name("blocker_families.toml")

F_TRUE = frozenset([frozenset()])
F_FALSE = frozenset()
F_MAX_TERMS = 64

RANK_REQ = {0: "true", 1: "air>=1", 2: "air>=2", 3: "air>=3"}
TIERS = ("safe", "standard", "hard", "frame_perfect")
TIER_N = {"safe": 1, "standard": 2, "hard": 3, "frame_perfect": 4, "phys": 0}


def _fmin(terms):
    out = []
    for t in sorted(set(terms), key=lambda t: (len(t), sorted(t))):
        if not any(o <= t for o in out):
            out.append(t)
    return frozenset(out) if len(out) <= F_MAX_TERMS else None


def f_or(*fs):
    if any(f == F_TRUE for f in fs if f is not None):
        return F_TRUE
    if any(f is None for f in fs):
        return None
    return _fmin([t for f in fs for t in f])


def f_and(*fs):
    if any(f is not None and not f for f in fs):
        return F_FALSE
    if any(f is None for f in fs):
        return None
    acc = F_TRUE
    for f in fs:
        acc = _fmin([a | b for a in acc for b in f])
        if acc is None:
            return None
    return acc


def f_when(cond, f):
    """f where cond holds, else false (an unused undecoded part stays out)."""
    return f if cond else F_FALSE


class Sig:
    __slots__ = ("on", "off", "pulse", "init")

    def __init__(self, on, off, pulse=False, init=None):
        self.on, self.off, self.pulse, self.init = on, off, pulse, init


def _const(v):
    return Sig(F_TRUE if v else F_FALSE, F_FALSE if v else F_TRUE, False, float(v))


UNK = Sig(None, None, False, None)
_REQ_TOK = re.compile(r"\s*(\(|\)|&|\||[^\s()&|]+)")


def req_dnf(s):
    """A §5.1 requirement string -> DNF over ``F:`` atoms (None for None)."""
    if s is None:
        return None
    toks = _REQ_TOK.findall(s)
    pos = [0]

    def expr():
        t = and_()
        while pos[0] < len(toks) and toks[pos[0]] == "|":
            pos[0] += 1
            t = f_or(t, and_())
        return t

    def and_():
        t = unary()
        while pos[0] < len(toks) and toks[pos[0]] == "&":
            pos[0] += 1
            t = f_and(t, unary())
        return t

    def unary():
        tok = toks[pos[0]]
        pos[0] += 1
        if tok == "(":
            e = expr()
            pos[0] += 1
            return e
        return F_TRUE if tok == "true" else F_FALSE if tok == "false" else frozenset([frozenset(["F:" + tok])])
    return expr()


def and_req(*parts):
    """The §5.1 conjunction of requirement strings: ``true`` drops out,
    ``false`` absorbs, an operand holding ``|`` is parenthesised, repeats
    are dropped."""
    out = []
    for p in parts:
        if p is None:
            continue
        p = p.strip()
        if p == "true":
            continue
        if p == "false":
            return "false"
        if "|" in p:
            p = f"({p})"
        if p not in out:
            out.append(p)
    return " & ".join(out) if out else "true"


def _sample_points(cv, weight, var):
    """Points of a gameState variable's domain at which a link is sampled."""
    if var.lower() in L.REAL_DOMAIN:
        lo, hi, _ = L.REAL_DOMAIN[var.lower()]
        return [lo + (hi - lo) * t / 20.0 for t in range(20)]
    return [float(x) for x in L._int_domain(var, cv, weight)]


def rec_of(gid):
    """(graph, record) of a generated id ``<level>/g<G>/r<R>``."""
    _, gs, rs = gid.split(" ")[0].split("/")
    return int(gs[1:]), int(rs[1:])


POSITIONAL = L.POSITIONAL
GS_COUNTER = {"air level": "air", "water level": "water", "fire level": "fire", "earth level": "earth",
              "air fragments": "disca", "water fragments": "discw", "fire fragments": "discf", "earth fragments": "disce",
              "life fragments": "discl", "obsidians": "obsidian"}
ARMOR_ELEC = 6          # [verified static 0x711C0] armor type (26) `elec` = 6; the electric shield is the air + fire cast


class Wiring:
    """The monotone reading of one level's logic nodes (the module docstring)."""
    OUT = {"switch": ("output", "goal"), "combiner": ("output",), "timer": ("currentTime",), "latch": ("output",),
           "critterGenerator": ("numDead", "numAlive", "numGenerated"), "playerLocation": ("teleported",),
           "damper": ("output",), "platform": ("touch", "actionButton", "whack", "magic", "key", "joystickOn")}
    PAD = {"touch": "touch", "actionButton": "action", "whack": "whack", "joystickOn": "joystick"}

    def __init__(self, lv, gen, toml):
        self.lv, self.gen = lv, gen
        self.memo, self.stack = {}, set()
        hand = {b.get("of"): b["id"] for b in toml.get("button", [])}
        self.key_atom = {}
        for k in gen.get("keylocks", []):
            if k.get("trigger"):
                self.key_atom[rec_of(k["trigger"])] = f"F:button:{hand[k['id']]}" if k["id"] in hand else None
        self.magic_req, self.magic_of = {}, {}
        for kind in ("barriers", "geodes"):
            for b in gen.get(kind, []):
                for sid in b.get("shapes", []):
                    self.magic_req[rec_of(sid)] = req_dnf(b.get("requires"))
                    self.magic_of[rec_of(sid)] = b["id"]
        self.dead_atom = {}
        for k in gen.get("keylords", []):
            if k.get("keylord") and k.get("event"):
                self.dead_atom[rec_of(k["keylord"])] = f"F:event:{k['event']}"
        for b in gen.get("bosses", []):
            if b.get("event"):
                self.dead_atom[rec_of(b["id"])] = f"F:event:{b['event']}"
        for loc in gen.get("locations", []):
            if loc["id"].startswith(lv.name + "/"):
                self.dead_atom.setdefault(rec_of(loc["id"]), f"loc:{loc['id']}")
        self.undecoded_nodes = collections.Counter()
        self.latched = set()             # pad atoms a switch holds (a latch or a locked window): not a teleport's pulse
        self.latch_of = collections.defaultdict(set)    # pad atom -> the switches (G, R) that hold it

    # ---- graph helpers
    def g(self, G):
        return self.lv.graphs[G]

    def incoming(self, G, r):
        """(k, link) of each link into record r, in source record and link order."""
        return [(k, lk) for lk, k in self.g(G).incoming().get(r, ())]

    def attrs(self, G, r):
        g = self.g(G)
        return dict(zip(g.schema.types[g.types[r]].attrs, g.attrs(r)))

    def links_into(self, G, r, plug):
        g = self.g(G)
        return [(k, lk) for k, lk in self.incoming(G, r) if g.plug_name(r, lk.dst_plug) == plug]

    # ---- signals
    def value(self, G, r, plug):
        key = (G, r, plug)
        if key in self.memo:
            return self.memo[key]
        if key in self.stack:
            return UNK                        # a feedback loop: undecoded
        self.stack.add(key)
        try:
            t = self.g(G).types[r]
            s = self.node(G, r, plug) if plug in self.OUT.get(t, ()) else self.attr(G, r, plug)
        except (ValueError, KeyError, IndexError, struct.error):
            s = UNK
        self.stack.discard(key)
        self.memo[key] = s
        return s

    def attr(self, G, r, plug):
        """An input attribute: what its links deliver, or its stored constant.
        An unlinked transform channel (the engine animates cameras and moved
        parts) or a combiner's ``index`` read as a source is undecoded."""
        lks = self.links_into(G, r, plug)
        if not lks:
            g = self.g(G)
            t = g.types[r]
            if (g.schema.is_a(t, "transform") and POSITIONAL.search(plug)) or (t == "combiner" and plug == "index"):
                self.undecoded_nodes[f"{t}.{plug} (engine-set)"] += 1
                return UNK
            return _const(self.attrs(G, r).get(plug, 0.0))
        sigs = [self.link(G, k, lk) for k, lk in lks]
        inits = [s.init for s in sigs]
        init = None if any(v is None for v in inits) else next((v for v in inits if v != 0.0), 0.0)
        return Sig(f_or(*[s.on for s in sigs]), f_and(*[s.off for s in sigs]), any(s.pulse for s in sigs), init)

    def _xs(self, G, src, sp, depth=0):
        """Representative non-zero values of a plug: a magic hit carries the
        attack level (1-4), numDead a count, a value combiner (sum, max,
        min, first non-zero, select) what its inputs carry; anything else 1."""
        g = self.g(G)
        t = g.types[src]
        if t == "platform" and sp == "magic":
            return [1.0, 2.0, 3.0, 4.0]
        if t == "critterGenerator" and sp == "numDead":
            n = int(self.attrs(G, src).get("maxGenerated", 1.0) or 1)
            return [float(k) for k in range(1, max(1, min(n, 8)) + 1)]
        if depth > 6:
            return [1.0]
        if t == "damper" and sp == "output":
            return self._xs(G, src, "goal", depth + 1)
        if t == "combiner" and sp == "output":
            n, fn = L.combiner_header(g, src)
            if fn not in (1, 4, 5, 6, 10):
                return [1.0]
            a = g.attrs(src)
            out = set()
            for q in range(min(n, 16)):
                if not self.links_into(G, src, f"inputs[{q}]"):
                    if a[q] != 0.0:
                        out.add(float(a[q]))
                    continue
                out |= set(self._xs(G, src, f"inputs[{q}]", depth + 1))
            return sorted(out)[:16] or [1.0]
        if sp not in self.OUT.get(t, ()):
            lks = self.links_into(G, src, sp)
            if not lks:
                v = self.attrs(G, src).get(sp, 0.0)
                return [float(v)] if v else [1.0]
            out = set()
            for k, lk in lks:
                s2 = lk.src
                sp2 = g.plug_name(s2, lk.src_plug)
                if g.types[s2] in ("gameState", "timer"):
                    out.add(1.0)
                    continue
                try:
                    cv = L.link_curve(g, s2, k)
                    out |= {L.link_value(cv, x, lk.weight, lk.factor) for x in self._xs(G, s2, sp2, depth + 1)} - {0.0}
                except (ValueError, struct.error):
                    out.add(1.0)
            return sorted(out)[:16] or [1.0]
        return [1.0]

    def link(self, G, k, lk):
        g = self.g(G)
        src, st = lk.src, g.types[lk.src]
        sp = g.plug_name(src, lk.src_plug)
        try:
            cv = L.link_curve(g, src, k)
            gf = lambda x: L.link_value(cv, x, lk.weight, lk.factor)      # noqa: E731
            gf(0.0)
        except (ValueError, struct.error):
            return UNK
        if st == "gameState":
            return self.gs_link(G, src, lk, cv)
        if st == "timer" and sp == "currentTime":
            return self.timer_link(G, src, gf)
        s = self.value(G, src, sp)
        try:
            z = gf(0.0)
            nz = [gf(v) for v in self._xs(G, src, sp)]
            init = None if s.init is None else gf(s.init)
        except ValueError:
            return UNK
        on = f_or(f_when(z != 0.0, s.off), f_when(any(v != 0.0 for v in nz), s.on))
        off = f_or(f_when(z == 0.0, s.off), f_when(any(v == 0.0 for v in nz), s.on))
        return Sig(on, off, s.pulse, init)

    def gs_link(self, G, src, lk, cv):
        var = L.gamestate_vars(self.g(G), src).get(lk.src_plug, "")
        v = var.lower()
        if not v:
            return UNK
        if v in L.REAL_DOMAIN:
            if v != "day night timer":
                return UNK
            vals = [L.link_value(cv, x, lk.weight, lk.factor) for x in _sample_points(cv, lk.weight, var)]
            return Sig(F_TRUE if any(vals) else F_FALSE, F_TRUE if not all(vals) else F_FALSE, False, None)
        xs = list(L._int_domain(var, cv, lk.weight))
        nzs = [x for x in xs if L.link_value(cv, float(x), lk.weight, lk.factor) != 0.0]
        zs = [x for x in xs if x not in nzs]
        init = L.link_value(cv, 0.0, lk.weight, lk.factor)

        def up(S, atom):
            if not S:
                return F_FALSE
            if len(S) == len(xs):
                return F_TRUE
            if S == [x for x in xs if x >= min(S)] and atom:
                return frozenset([frozenset([atom(min(S))])])
            return None
        if v == "armor type":
            on = f_or(*[frozenset([frozenset([f"armortype:{x}"])]) for x in nzs]) if nzs and len(nzs) < len(xs) else \
                (F_TRUE if nzs else F_FALSE)
            return Sig(on, F_TRUE if 0 in zs else None, False, init)
        if v == "armor level":
            return Sig(up(nzs, lambda n: f"armorlevel:{n}"), F_TRUE if 0 in zs else None, False, init)
        c = GS_COUNTER.get(v)
        atom = (lambda n: f"F:{c}>={n}") if c else None
        return Sig(up(nzs, atom), up(zs, atom), False, init)

    def timer_link(self, G, src, gf):
        a = self.attrs(G, src)
        E = self.value(G, src, "enable")
        t0, t1 = a.get("startTime", 0.0), a.get("stopTime", 0.0)
        tc = a.get("currentTime", t0)
        ts = [t0 + (t1 - t0) * q / 48.0 for q in range(49)] if t1 > t0 else [t0]
        try:
            vals = [gf(t) for t in ts]
            v0, vend = gf(tc), gf(t1)
        except ValueError:
            return UNK
        rep = a.get("repeat", 0.0) != 0.0
        on_run = any(v != 0.0 for v in vals) if rep else (vend != 0.0)
        off_run = any(v == 0.0 for v in vals) if rep else (vend == 0.0)
        on = f_or(f_when(v0 != 0.0, F_TRUE), f_when(on_run, E.on))
        off = f_or(f_when(v0 == 0.0, F_TRUE), f_when(off_run, E.on))
        return Sig(on, off, False, v0)

    def node(self, G, r, plug):
        g = self.g(G)
        t = g.types[r]
        a = self.attrs(G, r)
        if t == "platform":
            if plug in self.PAD:
                return Sig(frozenset([frozenset([f"{self.PAD[plug]}:{G}:{r}"])]), F_TRUE, True, 0.0)
            if plug == "key":
                at = self.key_atom.get((G, r))
                return Sig(None if at is None else frozenset([frozenset([at])]), F_TRUE, True, 0.0)
            if plug == "magic":
                req = self.magic_req.get((G, r))
                on = None if req is None else f_and(req, frozenset([frozenset([f"hit:{G}:{r}"])]))
                return Sig(on, F_TRUE, True, 0.0)
        if t == "playerLocation":
            return Sig(frozenset([frozenset([f"arrive:{G}:{r}"])]), F_TRUE, False, 0.0)
        if t == "critterGenerator":
            if plug == "numDead":
                at = self.dead_atom.get((G, r))
                return Sig(None if at is None else frozenset([frozenset([at])]), F_TRUE, False, 0.0)
            self.undecoded_nodes[f"critterGenerator.{plug}"] += 1
            return UNK
        if t == "damper":
            return self.value(G, r, "goal")
        if t == "switch":
            return self.switch(G, r, a)
        if t == "combiner":
            return self.combiner(G, r, a)
        if t == "latch":
            if g.pstr(g.recs[r], 0x18):
                self.undecoded_nodes["latch (a global)"] += 1
                return Sig(None, None, False, a.get("output", 0.0))
            U, I_ = self.value(G, r, "update"), self.value(G, r, "input")
            o0 = a.get("output", 0.0)
            return Sig(f_or(f_when(o0 != 0.0, F_TRUE), f_and(U.on, I_.on)),
                       f_or(f_when(o0 == 0.0, F_TRUE), f_and(U.on, I_.off)), False, o0)
        self.undecoded_nodes[f"{t}.{plug}"] += 1
        return UNK

    def switch(self, G, r, a):
        T, F, TG = self.value(G, r, "turnOn"), self.value(G, r, "turnOff"), self.value(G, r, "toggle")
        off_l, tog_l = bool(self.links_into(G, r, "turnOff")), bool(self.links_into(G, r, "toggle"))
        stored_off = a.get("turnOff", 0.0) != 0.0 and not off_l
        lock = a.get("lock", 0.0) != 0.0
        if T.init is None or F.init is None:
            gi = None
        else:
            gi = 1.0 if T.init != 0.0 else 0.0 if F.init != 0.0 else (1.0 if a.get("goal", 0.0) != 0.0 else 0.0)
        g_on = f_when(gi is not None and gi != 0.0, F_TRUE) if gi is not None else None
        g_off = f_when(gi is not None and gi == 0.0, F_TRUE) if gi is not None else None
        if off_l or tog_l or not stored_off or lock:
            for t_ in T.on or ():
                self.latched.update(t_)
                for x_ in t_:
                    self.latch_of[x_].add((G, r))
        if off_l or tog_l:
            return Sig(f_or(T.on, f_when(tog_l, TG.on), g_on), f_or(f_when(off_l, F.on), f_when(tog_l, TG.on), g_off),
                       False, gi)
        if stored_off:
            return Sig(T.on, T.off, T.pulse and not lock, gi)
        return Sig(f_or(T.on, g_on), g_off, False, gi)

    def combiner(self, G, r, a):
        n, fn = L.combiner_header(self.g(G), r)
        ins = [self.value(G, r, f"inputs[{q}]") for q in range(min(n, 16))]
        npulse = sum(1 for s in ins if s.pulse)
        ons, offs = [s.on for s in ins], [s.off for s in ins]
        if fn in (7, 3, 5):
            on, off = f_and(*ons), f_or(*offs)
            if npulse > 1:
                on = None
        elif fn in (6, 4, 1):
            on, off = f_or(*ons), f_and(*offs)
        elif fn == 12:
            on, off = f_or(*offs), f_and(*ons)
            if npulse > 1:
                off = None
        elif fn == 13:
            on, off = f_and(*offs), f_or(*ons)
        elif fn == 9:
            on, off = (ins[0].off, ins[0].on) if ins else (F_TRUE, F_FALSE)
        else:
            self.undecoded_nodes[f"combiner fn {fn}"] += 1
            return UNK
        inits = [s.init for s in ins]
        try:
            init = None if any(v is None for v in inits) else L.combine(fn, inits, a.get("index", 0.0))
        except ValueError:
            init = None
        return Sig(on, off, npulse > 0, init)

    # ---- readings
    def plug(self, oi, plug):
        o = self.lv.owners[oi]
        return self.value(o["G"], o["R"], plug)

    @staticmethod
    def terms(f):
        """A DNF -> [(pads, items)] with the armour atoms resolved; a term
        with an undecoded atom is dropped (fail closed); None stays None."""
        if f is None:
            return None
        out = []
        for t in f:
            pads, items, atype, alev, bad = set(), set(), set(), 0, False
            for x in t:
                if x.startswith("F:"):
                    items.add(x[2:])
                elif x.startswith("armortype:"):
                    atype.add(int(float(x.split(":")[1])))
                elif x.startswith("armorlevel:"):
                    alev = max(alev, int(float(x.split(":")[1])))
                else:
                    pads.add(x)
            if atype or alev:
                if atype != {ARMOR_ELEC}:
                    bad = True
                else:
                    lv_ = max(alev, 1)
                    items |= {f"air>={lv_}", f"fire>={lv_}"}
            if not bad:
                out.append((frozenset(pads), frozenset(items)))
        out = sorted(set(out), key=lambda pi: (len(pi[0]) + len(pi[1]), sorted(pi[0]), sorted(pi[1])))
        keep = []
        for p_, i_ in out:
            if not any(p2 <= p_ and i2 <= i_ for p2, i2 in keep):
                keep.append((p_, i_))
        return keep


# --------------------------------------------------------------------------- blockers and their families
DRIVER_TYPES = {"switch", "combiner", "latch"}


def _gate_records(gen, level):
    """((graph, record) -> gate, namespace -> gate) for the generated gate objects of one level."""
    out = {}

    def add(gid, owner):
        m = re.match(r"^([a-z0-9_]+)/g(\d+)/r(\d+)$", gid.split(" ")[0]) if isinstance(gid, str) else None
        if m and m.group(1) == level:
            out.setdefault((int(m.group(2)), int(m.group(3))), owner)

    for kind in ("barriers", "geodes"):
        for o in gen.get(kind, []):
            for x in o["shapes"] + o["switches"]:
                add(x, f"{kind[:-1]}:{o['id']}")
    for o in gen.get("keylocks", []):
        for k in ("trigger", "lock_toggle", "id"):
            if o.get(k):
                add(o[k], f"keylock:{o['id']}")
    for o in gen.get("keylords", []):
        for k in ("keylord", "cage", "latch_toggle", "id"):
            if o.get(k):
                add(o[k], f"keylord:{o['id']}")
    for o in gen.get("obsidian_locks", []):
        for k in ("open_combiner", "lock_toggle", "id"):
            if o.get(k):
                add(o[k], f"obsidian_lock:{o['id']}")
    for o in gen.get("seals", []):
        add(o["id"], f"seal:{o['id']}")
        add(o["activate"], f"seal:{o['id']}")
        for t in o["touch"]:
            add(t, f"seal:{o['id']}")
    for o in gen.get("bosses", []):
        add(o["id"], f"boss:{o['id']}")
    ns = {}
    for kind, pre in (("keylocks", "keylock"), ("keylords", "keylord"), ("obsidian_locks", "obsidian_lock")):
        for o in gen.get(kind, []):
            ns[o["namespace"]] = f"{pre}:{o['id']}"
    return out, ns


def blockers(lv, gen):
    """record id -> {bound_to, hint} for every blocker of a level: a platform
    whose gameSolid a switch, combiner or latch drives.  ``bound_to`` is
    the generated gate (``barrier:``, ``keylock:``, ``seal:`` ...) of the
    first record found walking back from those drivers through incoming
    links for at most two hops (R0's ``route/blockers.py`` rule 2), else
    None; ``hint`` is :func:`levels.explain`'s text for its gameSolid (its
    first 600 characters)."""
    gates, ns_gate = _gate_records(gen, lv.name)
    out = {}
    for gi, g in enumerate(lv.graphs):
        inc = g.incoming()
        ctx = None

        def gate_of(j, gi=gi, g=g):
            if (gi, j) in gates:
                return gates[(gi, j)]
            nm = g.names[j] or ""
            return next((gid for nsn, gid in ns_gate.items() if nm.startswith(nsn + ":")), None)

        for i, t in enumerate(g.types):
            if t != "platform" or g.recs[i] is None:
                continue
            solid_in = [lk for lk, _ in inc.get(i, ()) if g.plug_name(i, lk.dst_plug) == "gameSolid"]
            if not any(g.types[lk.src] in DRIVER_TYPES for lk in solid_in):
                continue
            bound = None
            frontier = {lk.src for lk in solid_in}
            seen = set(frontier)
            for hop in range(2):
                for j in sorted(frontier):
                    gt = gate_of(j)
                    if gt and not bound:
                        bound = gt
                if bound or hop == 1:
                    break
                nxt = set()
                for j in frontier:
                    if g.types[j] in L.LOGIC_TYPES:
                        nxt.update(lk.src for lk, _ in inc.get(j, ()))
                    elif g.types[j] == "platform":
                        nxt.add(j)
                frontier = nxt - seen
                seen |= frontier
            if ctx is None:
                ctx = L._Ctx(lv.name, gi, g)
                gsn = {(gi, s): L.gamestate_vars(g, s) for s, ty in enumerate(g.types) if ty == "gameState"}
            out[f"{lv.name}/g{gi}/r{i}"] = {"bound_to": bound, "hint": L.explain(ctx, gsn, i, "gameSolid")[:600]}
    return out


def families():
    """The blocker families (``blocker_families.toml``): member record id -> its family."""
    with FAMILIES_TOML.open("rb") as f:
        doc = tomllib.load(f)
    return {m: fam for fam in doc["family"] for m in fam["members"]}


def saved_names(g):
    """The names of the records a graph's save list restores (``Graph.saved``)."""
    return {g.names[r] for r in g.saved() if 0 <= r < len(g.names) and g.names[r]}
