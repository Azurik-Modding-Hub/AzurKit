"""Realm authoring: a level file written from its derived zone graph and the
realm step's hand decisions (Step R1.8; ``docs/RANDOMIZER_DB.md`` §4, §16).

``azurik-mod rando author LEVEL...`` writes ``data/levels/<level>.toml``
for each level from four inputs: its generated file (the objects and their
decoded requirements), its derived file (the reach model's zones and zone
edges, §16), ``tricks.toml`` (the level's skips, projected as they are)
and ``draft/authoring/<level>.toml``, the realm step's hand decisions: what
the derive could not decode or does not model (below).  ``--check`` writes
nothing and exits 1 unless each level file equals its authoring.

**Nodes.**  Only some zones matter to logic: those holding a pool location,
an exit's switch, an arrival, a button, an event, a barrier's
``destroy_from`` or a respawning barrier's far side (the *kept* zones).
Every other zone is a place a path passes through, so the zone graph is
contracted onto the kept zones: between two kept zones, each movement
tier's requirement is the union, over every path through zones that are
not kept, of the conjunction of its edges' requirements (a monotone formula
over the counters, flags, events and confirmed skips, kept as an antichain
of terms).  Kept zones the safe tier joins both ways with no item over
floors and decoded gates alone are one node, named ``<level>_z<NNN>`` after
its lowest zone unless the authoring names it.  A node anchors its zones
(``zone:<id>``, §4.2), so the derive's location -> zone map gives each
location its node.

**Edges.**  A tier's requirement is written as one edge per difficulty
(§4.3): the terms a tier adds over the tier below it.  A term's confidence
is ``data`` (floors and decoded gates), ``physics`` (a modelled flight of
the measured envelope) or ``assumed`` (a probe-needed derived edge whose
probe class the authoring admits, or a hand edge); a probe-needed edge it
doesn't admit stays out of logic (``logic = false``, R_phys only), and so
does an admitted ``rig`` edge of a rig the authoring holds (``rig_held``:
its ride needs a trigger, a seal or a kill the probe edge doesn't carry), and
any ride (``kind`` "rig", a guess or a barrier bypass) that runs against its
rig's one-way mover (``rig_one_way``: a rig only rising or only sinking,
AZ-589); a rig
whose trigger the derive doesn't decode and the authoring does (``rig_requires``)
carries it on every edge of its ride, R_phys's too.  A term
another path already gives, at a tier no higher, with a kit it meets and a
confidence no weaker, is dropped (a transitive reduction, one term at a
time, so every kit reaches what it reached).  Crossing a permanent barrier
needs its ``.destroyed`` flag; a respawning one is crossed only from its
``destroy_from`` side, by a ``through`` edge (§4.4, §5.3); either way the
barrier's own requirement leaves the crossing.  A generated skip the
derive holds (D114) is false; a confirmed skip stays as its ``skip:``
atom, which places it.

**What the authoring holds** (``draft/authoring/<level>.toml``): node names
(``[names]``: node id -> one of its zones; the world's start and hub are
named there), the probe classes admitted into logic (``probe``), the
requirement of each gate the derive left undecoded (``[gates]``), the zones on
either side of a gate whose edges cross its solids unmarked (``[gate_sides]``: an
edge between a ``near`` and a ``far`` zone needs the gate's ``[gates]``
requirement), the rigs held out of the
admitted ``rig`` class (``[rig_held]``: rig name -> reason), the rigs whose
movers only rise or only sink (``[rig_one_way]``: rig name -> ``way`` "up" or
"down" and ``why``; their admitted ``rig`` edges against it are held), single derived
zone edges held out of logic (``[[held]]``: ``from`` (none: every derived edge into ``to``), ``to``, ``via`` for one
rig's ride, ``why``, and ``difficulty`` to hold only the tiers from it up,
which then read the tier below's requirement; R_phys keeps them; with ``pair =
true``, every path between two kept zones through zones that aren't kept: the
node edge the derive contracts from many guessed paths, held whole), the trigger of a
rig's ride (``[rig_requires]``: rig name -> ``requires`` and ``why``), a
skip's alternative to a decoded one (``[gates_or]``), the zone
of a pool location the derive placed nowhere (``[members]``), the edges it
misses (``[[edge]]``, between zones, ``assumed``), the events it doesn't
set (``[[event]]``: kills, placements), the exits' requirements and
any exit whose switch or arrival it doesn't place (``[exit."<id>"]``; a
gondola's names its lock, ``cart``, Step R1.11c),
barrier overrides, bypasses and ``destroy_from`` additions
(``[barrier."<id>"]``), dark nodes (``[dark]``) and the ``[[location]]``
overrides (proven marks).  Each carries its reason.

**Proven spots** (D122, D143).  A hand mark wins; then the authoring marks
``by = "data"`` (:func:`proven_by_data`) and, over the database the new
files make, ``by = "route"`` (D169): the spots whose vanilla route step
holds no more than the logic requires to get there and back
(:func:`route_marks`; ``rando check`` re-runs
:meth:`~azurkit.tools.randomizer.planner.solver.Logic.mark_short` on every
route mark). A walk the logic outdoes only with some skips on names them
(``unless``) and the items it still holds for with them on (``only``;
AZ-725), so a skip changes no mark below its own tier.

Stdlib only (it reads the committed derived data; no ISO).
"""

from __future__ import annotations

import collections
import functools
import gzip
import json
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from devkit.rando.physics import PICK_STAND
from azurkit.tools.randomizer.planner.grammar import parse
from azurkit.tools.randomizer.planner.loader import DATA_DIR

DRAFT = Path(__file__).resolve().parent
DATA = DATA_DIR
AUTHORING = DRAFT / "authoring"
TIERS = ("safe", "standard", "hard", "frame_perfect")
ASSUMED = ("~", "assumed")            # the marker atom of a term that uses an admitted probe-needed or hand edge
MODELLED = ("~", "physics")           # ... of a term that uses a modelled flight (the envelope), not just floors and data
PROBED = ("~", "probed")              # ... of a term whose node pair a walk proved (D170: an L3 string xemu replayed)
SAFE_P = 0.80                         # D187 (owner): a probed walk counts as a safe-tier (exact) connection for the data
                                      # proofs only when its string's robustness under jitter is at least this (X.7's
                                      # default was 0.95): a fragile string proves the connection, not that anyone walks it
PERMANENT = "permanent"
HEADER = """\
# levels/{level}.toml: written by `azurik-mod rando author {level}` (Step R1.8) from generated/{level}.json,
# derived/{level}.json.gz, tricks.toml and draft/authoring/{level}.toml (the realm step's hand decisions, each
# with its reason). Edit those and re-run it, not this file (docs/RANDOMIZER_DB.md 4, 16).
"""


# --------------------------------------------------------------------------- requirements as antichains of terms
def _dnf(ast) -> list[frozenset]:
    kind = ast[0]
    if kind == "const":
        return [frozenset()] if ast[1] else []
    if kind == "counter":
        return [frozenset({(ast[1], ast[2])})]
    if kind in ("flag", "skip", "event", "button"):
        return [frozenset({(kind, ast[1])})]
    if kind == "or":
        out: list[frozenset] = []
        for c in ast[1]:
            out = union(out, _dnf(c))
        return out
    if kind == "and":
        out = [frozenset()]
        for c in ast[1]:
            out = product(out, _dnf(c))
        return out
    raise ValueError(f"a derived requirement names {ast!r}")


def dnf(text: str) -> list[frozenset]:
    """A requirement string as an antichain of terms (each a frozenset of atoms)."""
    return _dnf(parse(text))


def _norm(t) -> frozenset:
    best, rest = {}, set()
    for a in t:
        if isinstance(a[1], int):
            best[a[0]] = max(best.get(a[0], 0), a[1])
        else:
            rest.add(a)
    return frozenset(rest | set(best.items()))


@functools.lru_cache(maxsize=1 << 20)
def implies(strong: frozenset, weak: frozenset) -> bool:
    """``strong`` meets every atom of ``weak`` (so ``weak`` is no stronger).
    Memoised: the contraction asks the same pairs over and over."""
    have = {a[0]: a[1] for a in strong if isinstance(a[1], int)}
    return all(have.get(a[0], 0) >= a[1] if isinstance(a[1], int) else a in strong for a in weak)


def union(xs, ys) -> list[frozenset]:
    out = list(xs)
    seen = set(out)
    for y in ys:
        if y in seen or any(implies(y, x) for x in out):      # a term already there, or one it implies
            continue
        out = [x for x in out if not implies(x, y)] + [y]
        seen = set(out)
    return out


def product(xs, ys) -> list[frozenset]:
    out: list[frozenset] = []
    for x in xs:
        for y in ys:
            out = union(out, [_norm(x | y)])
    return out


def _key(t: frozenset):
    return sorted((a[0], str(a[1])) for a in t)


def term_text(t: frozenset) -> str:
    parts = []
    for a in sorted((a for a in t if a[0] != "~"), key=lambda a: (not isinstance(a[1], int), a[0], str(a[1]))):
        parts.append(f"{a[0]}>={a[1]}" if isinstance(a[1], int) else f"{a[0]}:{a[1]}")
    return " & ".join(parts) or "true"


def dnf_text(terms) -> str:
    texts = sorted(term_text(t) for t in terms)
    if not texts:
        return "false"
    return " | ".join(f"({x})" if " & " in x and len(texts) > 1 else x for x in texts)


# --------------------------------------------------------------------------- inputs
def _zone_num(zid: str) -> int:
    return int(zid.rsplit(".Z", 1)[1])


def read_derived(level: str, data: Path = DATA) -> dict:
    return json.loads(gzip.decompress((data / "derived" / f"{level}.json.gz").read_bytes()))


def read_spec(level: str, authoring: Path = AUTHORING) -> dict:
    path = authoring / f"{level}.toml"
    spec = tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    known = {"level", "probe", "rig_held", "rig_one_way", "rig_requires", "names", "gates", "gates_or", "gate_sides", "members", "edge",
             "event", "exit",
             "barrier", "dark", "location", "button", "note", "probed", "held"}
    unknown = set(spec) - known
    if unknown:
        raise ValueError(f"draft/authoring/{level}.toml: unknown keys {sorted(unknown)}")
    for rig, v in spec.get("rig_one_way", {}).items():
        if not isinstance(v, dict) or v.get("way") not in ("up", "down") or not v.get("why"):
            raise ValueError(f"draft/authoring/{level}.toml: rig_one_way {rig!r} needs way = \"up\" or \"down\" and "
                             "a why")
    return spec


ONE_WAY_M = 1.0    # a rig edge rising or falling at least this far runs with or against its one-way mover (AZ-589)


def against_mover(e: dict, one_way: dict) -> bool:
    """Is ``e`` a ride on a rig (``kind`` "rig": a guess, ``probe`` "rig", or a barrier bypass up it, "bskip") that
    runs against the rig's one-way mover (``[rig_one_way]``: rig name -> its decoded way, AZ-589, D719): at least
    :data:`ONE_WAY_M` down a rig that only rises, or up one that only sinks?  No ride carries the player that way,
    and a drop beside a rising rig waits for L3 to land it alive (a hand edge then), so it stays out of logic."""
    way = one_way.get(e.get("via")) if e.get("kind") == "rig" else None
    dh = e.get("dh") or 0.0
    return way is not None and abs(dh) >= ONE_WAY_M and (dh > 0) != (way == "up")


@dataclass
class ZoneEdge:
    frm: str
    to: str
    tiers: list            # per tier: the antichain usable in logic (empty: not in logic at that tier)
    phys: list             # the antichain usable physically (R_phys: every edge, frame_perfect)
    through: tuple = ()    # respawning barriers crossed (a direct edge, never contracted)
    certs: tuple = (None,) * 4   # per tier, the certificate of the flight it reads (None: no flight; Step R1.14b)
    hand: bool = False           # the authoring's [[edge]] (hold_pairs keeps it)


@dataclass
class Level:
    """One level's authoring state."""
    name: str
    gen: dict
    doc: dict
    spec: dict
    persist: dict = field(default_factory=dict)       # hand barrier id -> its persistence
    hand_of: dict = field(default_factory=dict)       # generated id -> hand object id
    destroy_from: dict = field(default_factory=dict)  # hand barrier id -> its zones
    edges: list = field(default_factory=list)
    kept: set = field(default_factory=set)
    node_of: dict = field(default_factory=dict)       # kept zone -> node id
    events: dict = field(default_factory=dict)        # derived event id -> its zone (the one it is set at here)
    objects: dict = field(default_factory=dict)       # derived object id -> its row
    arrival_zones: set = field(default_factory=set)
    used_events: set = field(default_factory=set)
    issues: list = field(default_factory=list)
    proofs: dict = field(default_factory=dict)        # a probed term (Atomic) -> its walk's proof (D170)
    robust: dict = field(default_factory=dict)        # a probed term -> its proof's robustness meets SAFE_P
    route_proven: dict = field(default_factory=dict)  # location -> its by-route mark (D169), set by author()


def _gate_mark(gid: str) -> str:
    return f"flag:{re.sub(r'[^A-Za-z0-9_.]', '_', gid.replace('/', '.'))}.open"


def _resolve_held(e: dict, gates: dict) -> dict | None:
    """An edge past undecoded gates whose requirement the authoring gives: its
    ``held`` requirement with each gate's mark replaced by it; None while a
    gate stays open."""
    held = e.get("held")
    if not held or not all(g in gates for g in e.get("gate_undecoded", ())):
        return None
    out = {k: v for k, v in e.items() if k not in ("held", "gate_undecoded")}

    def sub(text):
        for g in e["gate_undecoded"]:
            text = text.replace(_gate_mark(g), f"({gates[g]})")
        return text
    out["requires"] = sub(held["requires"])
    out["difficulty"] = held.get("difficulty", e.get("difficulty", 1))
    if held.get("options"):
        out["options"] = [dict(o, requires=sub(o["requires"])) for o in held["options"]]
    else:
        out.pop("options", None)
    return out


def _divide(terms, gate) -> list[frozenset]:
    """Each term with a gate's own requirement (an antichain ``gate``)
    taken out where the term holds it whole: what crossing needs besides
    the gate."""
    out: list[frozenset] = []
    for t in terms:
        hit = [gt for gt in gate if gt <= t]
        out = union(out, [_norm(t - hit[0]) if hit else t])
    return out


def tier_terms(e: dict) -> list[list[frozenset]]:
    """Per tier, an edge's requirement (``draft/export.py``'s ``tiers_of``)."""
    from devkit.rando.draft.export import tiers_of
    tiers = tiers_of(e)
    return [dnf(tiers[t]) for t in TIERS]


def tier_certs(e: dict) -> list:
    """Per tier, the certificate (``draft/export.py``'s ``cert``: what the flight physically needs, D167) of the
    option :func:`tier_terms` reads there; None where none is or the option has none (a walk, a gate, a ride, a
    hand edge)."""
    if e["requires"] == "false":
        return [None] * 4
    opts = sorted(e.get("options") or [{"difficulty": e.get("difficulty", 1), "cert": e.get("cert")}],
                  key=lambda o: o["difficulty"])
    return [next((o.get("cert") for o in reversed(opts) if o["difficulty"] <= n), None) for n in range(1, 5)]


def build(level: str, db_skips: dict, data: Path = DATA, authoring: Path = AUTHORING) -> Level:
    """The zone graph of a level as logic reads it (the module docstring)."""
    gen = json.loads((data / "generated" / f"{level}.json").read_text(encoding="utf-8"))
    L = Level(level, gen, read_derived(level, data), read_spec(level, authoring))
    spec, doc = L.spec, L.doc
    L.objects = {o["id"]: o for o in doc["objects"]}
    hand = tomllib.loads((data / "levels" / f"{level}.toml").read_text(encoding="utf-8"))
    for kind in ("barrier", "button", "event"):
        for o in hand.get(kind, []):
            if "of" in o:
                L.hand_of[o["of"]] = o["id"]
    for b in gen["barriers"]:
        bid = L.hand_of[b["id"]]
        L.persist[bid] = spec.get("barrier", {}).get(bid, {}).get("persist", b["persist"])
    gates = {g["id"]: g for g in doc["gates"]}
    zones = {z["id"] for z in doc["zones"]}
    for bid in L.persist:      # a destroy_from zone the export dropped (under 25 m², nothing in it, no edge) is unreachable
        g = gates.get(bid, {})
        L.destroy_from[bid] = sorted((set(g.get("destroy_from") or ()) & zones) |
                                     set(spec.get("barrier", {}).get(bid, {}).get("destroy_from", ())))
    # a probe class admitted into logic; "<class>+1" admits it one movement tier harder (a curved path past what the
    # straight flight hits is harder than the straight one [inferred])
    admitted = {p.split("+")[0]: int(p.split("+")[1]) if "+" in p else 0 for p in spec.get("probe", ())}
    held_rigs = set(spec.get("rig_held", {}))    # a rig whose decoded trigger gates its ride: its probe edges stay out
    one_way = {r: v["way"] for r, v in spec.get("rig_one_way", {}).items()}   # AZ-589: its rides against it stay out
    held = [(h.get("from"), h["to"], h.get("via"), h.get("difficulty", 1)) for h in spec.get("held", ())
            if not h.get("pair")]   # derived zone edges held out of logic, from that tier up (no ``from``: every
    # derived edge into ``to``; a pair: hold_pairs)
    matched = set()
    resolved = spec.get("gates", {})
    ev_doc = {e["id"]: e for e in doc["events"]}
    hand_events = {e["id"] for e in spec.get("event", ())}

    def usable(term: frozenset) -> bool:
        """A term the logic can meet: no generated (held) skip, no event the level never sets."""
        for a in term:
            if a[0] == "skip" and a[1] not in db_skips:
                return False
            if a[0] == "event" and a[1] not in hand_events and not (ev_doc.get(a[1]) or {}).get("set_at"):
                return False
        return True

    def clean(terms):
        return [t for t in terms if usable(t)]

    for k, e in enumerate(list(doc["edges"]) + [dict(x, confidence="assumed", difficulty=x.get("difficulty", 1))
                                                for x in spec.get("edge", ())]):
        if e.get("gate_undecoded"):
            e = _resolve_held(e, resolved)
            if e is None:
                continue
        if e["requires"] == "false" and not e.get("options"):
            continue
        through = [t for t in e.get("through") or () if t in L.persist]
        respawn = tuple(t for t in through if L.persist[t] != PERMANENT)
        flags = frozenset(("flag", f"{t}.destroyed") for t in through if L.persist[t] == PERMANENT)
        if respawn and e["from"] not in set().union(*(L.destroy_from[t] for t in respawn)):
            continue        # a respawning barrier is crossed from where it is destroyed (§4.4)
        per = tier_terms(e)
        for gid in through:     # a barrier's own requirement leaves the edge: its flag or its crossing carries it (§5.3)
            if e.get("gate_requires") and gid in e["through"]:
                g = dnf(e["gate_requires"][e["through"].index(gid)])
                per = [_divide(ts, g) for ts in per]
        for gid in e.get("through") or ():          # a decoded gate a skip also passes: its requirement or the skip
            alt = spec.get("gates_or", {}).get(gid)
            if alt and e.get("gate_requires"):
                g = dnf(e["gate_requires"][e["through"].index(gid)])
                per = [union(ts, [x for t in ts for gt in g if gt <= t for x in product([t - gt], dnf(alt))])
                       for ts in per]
        for gid, side in spec.get("gate_sides", {}).items():   # a derived edge through a gate's solids it didn't mark
            ends = {e["from"], e["to"]}
            if gid not in (e.get("through") or ()) and ends & set(side["near"]) and ends & set(side["far"]):
                per = [product(ts, dnf(resolved[gid])) for ts in per]
        if e.get("probe") == "rig" and e.get("via") in spec.get("rig_requires", {}):   # a trigger the derive doesn't decode
            per = [product(ts, dnf(spec["rig_requires"][e["via"]]["requires"])) for ts in per]
        in_logic = (e.get("logic", True) is not False or e.get("probe") in admitted and not (
            e.get("probe") == "rig" and e.get("via") in held_rigs)) and not against_mover(e, one_way)
        hold = {i for i, (a, b, via, _) in enumerate(held) if a in (None, e["from"]) and e["to"] == b and via in (
                None, e.get("via"))} if k < len(doc["edges"]) else set()   # a derived edge (a hand edge is the authoring's)
        matched |= hold
        up = min((held[i][3] for i in hold), default=5) - 1      # the tiers under the hold's (4: none held)
        in_logic = in_logic and up > 0
        shift = admitted.get(e.get("probe"), 0) if e.get("logic", True) is False else 0
        certs = tier_certs(e)
        if shift:
            per = [[] for _ in range(shift)] + per[:4 - shift]
            certs = [None] * shift + certs[:4 - shift]
        conf = e.get("confidence")
        mark = frozenset({ASSUMED}) if conf in ("probe-needed", "assumed") else \
            frozenset() if conf in ("geometry", "data") else frozenset({MODELLED})
        add = flags | mark
        logic_per = per
        if 0 < up < 4:              # a harder tier's option held (AZ-532): those tiers read the tier below's
            logic_per, certs = per[:up] + [per[up - 1]] * (4 - up), certs[:up] + [certs[up - 1]] * (4 - up)
        tiers = [clean(product(t, [add])) if in_logic else [] for t in logic_per]
        phys = clean(product(per[3], [flags]))
        if any(tiers) or phys:
            L.edges.append(ZoneEdge(e["from"], e["to"], tiers, phys, respawn, tuple(certs), k >= len(doc["edges"])))
    L.issues += [f"held {a or '*'} -> {b}{f' via {via}' if via else ''}: no derived edge" for i, (a, b, via, _) in
                 enumerate(held) if i not in matched]
    return L


# --------------------------------------------------------------------------- kept zones, contraction, nodes
def object_zone(L: Level, oid: str) -> str | None:
    """The zone an object (an exit's switch, a button) is used from: one of
    the zones its trigger overlaps that an exit arrives in (a switch beside
    an arrival is used from there), else the one it overlaps most."""
    o = L.objects.get(oid)
    if o is None:
        return None
    near = sorted(set(o.get("at") or ()) & L.arrival_zones, key=_zone_num)
    return near[0] if near else o.get("main_zone")


def kept_zones(L: Level, arrivals: set, extra: set) -> set:
    doc, spec = L.doc, L.spec
    keep = set(arrivals) | set(extra)
    for loc in doc["locations"]:
        if loc.get("zone"):
            keep.add(loc["zone"])
    keep |= set(spec.get("members", {}).values())
    keep |= set(spec.get("names", {}).values())
    for e in spec.get("edge", ()):
        keep |= {e["from"], e["to"]}
    for e in spec.get("event", ()):
        keep.add(e["zone"])
    for x in spec.get("exit", {}).values():
        if x.get("from"):
            keep.add(x["from"])
    for bid, zones in L.destroy_from.items():
        keep |= set(zones)
    for o in doc["objects"]:
        if o["kind"] in ("exit", "keylock", "seal", "obsidian_lock", "keylord") and object_zone(L, o["id"]):
            keep.add(object_zone(L, o["id"]))
    for z in spec.get("button", {}).values():
        keep.add(z)
    for e in L.edges:
        if e.through:
            keep |= {e.frm, e.to}
    for t in L.edges:
        for terms in t.tiers + [t.phys]:
            for term in terms:
                for a in term:
                    if a[0] == "event":
                        L.used_events.add(a[1])
    for loc in doc["locations"]:
        for a in re.findall(r"event:([A-Za-z0-9_.]+)", loc.get("requires", "")):
            L.used_events.add(a)
    for gid in spec.get("gates", {}).values():
        L.used_events |= set(re.findall(r"event:([A-Za-z0-9_.]+)", gid))
    hand_events = {e["id"]: e["zone"] for e in spec.get("event", ())}
    for ev in doc["events"]:
        if ev["id"] in L.used_events and ev["id"] not in hand_events and ev["set_at"]:
            z = sorted(ev["set_at"], key=_zone_num)[0]
            L.events[ev["id"]] = z
            keep.add(z)
    return keep


def contract(L: Level) -> dict:
    """(a, b) -> (per-tier antichains, phys antichain) over paths whose inner
    zones are not kept; a respawning barrier's crossings stay direct."""
    adj = collections.defaultdict(list)
    for e in L.edges:
        if not e.through:
            adj[e.frm].append(e)
    out = {}
    for a in sorted(L.kept):
        lab = {a: ([[frozenset()]] * 4, [frozenset()])}
        todo = collections.deque([a])
        while todo:
            u = todo.popleft()
            per_u, ph_u = lab[u]
            for e in adj.get(u, ()):
                old = lab.get(e.to)
                per = [union(old[0][i] if old else [], product(per_u[i], e.tiers[i])) for i in range(4)]
                ph = union(old[1] if old else [], product(ph_u, e.phys))
                if old is not None and all(set(per[i]) == set(old[0][i]) for i in range(4)) and set(ph) == set(old[1]):
                    continue
                if not (any(per) or ph):
                    continue
                lab[e.to] = (per, ph)
                if e.to not in L.kept:
                    todo.append(e.to)
        for b, (per, ph) in lab.items():
            if b != a and b in L.kept:
                out[(a, b)] = (per, ph)
    for e in L.edges:
        if e.through:
            out.setdefault(("through", e.frm, e.to, e.through), ([[]] * 4, []))
            per, ph = out[("through", e.frm, e.to, e.through)]
            out[("through", e.frm, e.to, e.through)] = ([union(per[i], e.tiers[i]) for i in range(4)],
                                                        union(ph, e.phys))
    return out


def hold_pairs(L: Level) -> None:
    """The authoring's ``[[held]]`` with ``pair = true`` (Step R1.24b, D722): every path from one kept zone to another
    through zones that aren't kept leaves logic at every tier (R_phys keeps it), so a node edge the derive contracts
    from many guessed paths is held whole; a hand edge between them is kept.  A pair with no such path is an issue."""
    for h in L.spec.get("held", ()):
        if not h.get("pair"):
            continue
        key = (h["from"], h["to"])
        if key not in L.pairs:
            L.issues.append(f"held pair {key[0]} -> {key[1]}: no path between two kept zones")
            continue
        hand = [e for e in L.edges if (e.frm, e.to) == key and e.hand and not e.through]
        per = [[] for _ in range(4)]
        for e in hand:
            per = [union(per[i], e.tiers[i]) for i in range(4)]
        L.pairs[key] = (per, L.pairs[key][1])


def merge(L: Level, pairs: dict, dark: dict) -> dict:
    """Kept zone -> node: the strongly connected groups of kept zones joined
    both ways by a ``true`` safe-tier edge (physics, not assumed), never
    across darkness; each named after the authoring's name for one of its
    zones, else its lowest zone."""
    g = collections.defaultdict(set)
    for key, (per, _) in pairs.items():
        if key[0] != "through" and frozenset() in per[0]:
            g[key[0]].add(key[1])
    zone_dark = {z: d for d, zs in dark.items() for z in zs}
    index, low, stack, on, comp = {}, {}, [], set(), {}
    counter = [0]

    def strong(v):          # Tarjan, iterative
        work = [(v, iter(sorted(g[v])))]
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on.add(v)
        while work:
            u, it = work[-1]
            for w in it:
                if zone_dark.get(w) != zone_dark.get(u):
                    continue
                if w not in index:
                    index[w] = low[w] = counter[0]
                    counter[0] += 1
                    stack.append(w)
                    on.add(w)
                    work.append((w, iter(sorted(g[w]))))
                    break
                if w in on:
                    low[u] = min(low[u], index[w])
            else:
                work.pop()
                if work:
                    low[work[-1][0]] = min(low[work[-1][0]], low[u])
                if low[u] == index[u]:
                    group = []
                    while True:
                        w = stack.pop()
                        on.discard(w)
                        group.append(w)
                        if w == u:
                            break
                    for w in group:
                        comp[w] = min(group, key=_zone_num)
    for v in sorted(L.kept, key=_zone_num):
        if v not in index:
            strong(v)
    names = {z: n for n, z in L.spec.get("names", {}).items()}
    groups = collections.defaultdict(list)
    for z, root in comp.items():
        groups[root].append(z)
    node_of = {}
    for root, zs in groups.items():
        named = sorted({names[z] for z in zs if z in names})
        if len(named) > 1:
            L.issues.append(f"zones {sorted(zs, key=_zone_num)} are one node but named {named}")
        nid = named[0] if named else f"{L.name}_z{_zone_num(root):03d}"
        for z in zs:
            node_of[z] = nid
    return node_of


@dataclass(frozen=True)
class Atomic:
    """One term of a node edge: usable in logic from tier ``tier`` (1-4) up,
    or physically only (``tier`` 0)."""
    a: str
    b: str
    tier: int
    term: frozenset
    through: tuple = ()


def atomic_edges(pairs: dict, node_of: dict) -> list[Atomic]:
    node_pairs = collections.defaultdict(lambda: ([[] for _ in range(4)], []))
    for key, (per, ph) in pairs.items():
        through = key[3] if key[0] == "through" else ()
        a, b = (key[1], key[2]) if key[0] == "through" else key
        na, nb = node_of[a], node_of[b]
        if na == nb and not through:
            continue
        cur = node_pairs[(na, nb, through)]
        for i in range(4):
            cur[0][i] = union(cur[0][i], per[i])
        node_pairs[(na, nb, through)] = (cur[0], union(cur[1], ph))
    out = []
    for (na, nb, through), (per, ph) in sorted(node_pairs.items()):
        below: list[frozenset] = []
        for i in range(4):
            for t in per[i]:
                if not any(implies(t, x) for x in below):
                    out.append(Atomic(na, nb, i + 1, t, through))
            below = union(below, per[i])
        for t in ph:
            if not any(implies(t | {ASSUMED, MODELLED}, x) for x in below):
                out.append(Atomic(na, nb, 0, t, through))
    return out


def reduce_edges(edges: list[Atomic]) -> list[Atomic]:
    """Drop each term another path already gives: at a tier no higher, with
    a kit it meets and a confidence no weaker (an assumed term may stand in
    only for an assumed one); physical terms may use any edge but a
    respawning barrier's crossing, whose destroy requirement its term leaves
    out (Step R1.11b: it dropped f1's confirmed skip past flameSpout6).  One at a
    time, against what is left, so each kit still reaches what it reached."""
    alive = list(edges)
    order = sorted(range(len(alive)), key=lambda k: (-len(alive[k].term), -alive[k].tier, alive[k].a, alive[k].b,
                                                    _key(alive[k].term)))
    dead = set()
    for k in order:
        x = alive[k]
        if x.through or x.a == x.b:
            continue
        adj = collections.defaultdict(list)
        for j, y in enumerate(alive):
            if j == k or j in dead or y.through:   # a respawning barrier's crossing needs its destroy requirement,
                continue                          # which its term leaves out: it stands in for no other term
            if x.tier == 0 or (1 <= y.tier <= x.tier):
                if implies(x.term | {ASSUMED, MODELLED} if x.tier == 0 else x.term, y.term):
                    adj[y.a].append(y.b)
        seen, todo = {x.a}, [x.a]
        while todo:
            u = todo.pop()
            for v in adj[u]:
                if v not in seen:
                    seen.add(v)
                    todo.append(v)
        if x.b in seen:
            dead.add(k)
    return [x for j, x in enumerate(alive) if j not in dead]


def robust_enough(rec: dict) -> bool:
    """Whether an L3 walk's ``proofs.jsonl`` record counts as exact for the
    data proofs: each leg's robustness under jitter at least :data:`SAFE_P`
    (D187)."""
    return min((leg.get("robustness", 0.0) for leg in rec["string"].get("legs", ())), default=0.0) >= SAFE_P


def probed(L: Level, edges: list[Atomic], records: dict) -> list[Atomic]:
    """D170: the authoring's ``[[probed]]`` walks (``from`` and ``to`` zones, the ``kit`` held, ``proven``).  Each
    assumed or physics term of the walk's node pair that asks at least the walk's kit (anyone who meets it holds
    the kit, so the walk applies) becomes probed (``L.proofs`` keeps its proof); its tier stays.  An L3 walk's
    proof must resolve to a ``proofs.jsonl`` record (``records``) claiming that walk under the level's current
    zoning (the derived ``zones`` section): a re-derive renumbers the zones, so a stale walk is an issue, never applied
    (``scripts/l3_certify.py recheck`` re-runs the string and re-zones it).  A walk counts as exact for
    :func:`proven_by_data` (``L.robust``) only when its record's robustness is at least :data:`SAFE_P` (an xemu
    walk: always)."""
    from azurkit.tools.randomizer.planner.proofs import zoning
    walks = []
    zones_now = zoning(L.doc)
    for w in L.spec.get("probed", ()):
        a, b = L.node_of.get(w["from"]), L.node_of.get(w["to"])
        pv, where, robust = w.get("proven"), f"probed {w['from']} -> {w['to']}", True
        if a is None or b is None:
            L.issues.append(f"{where}: a zone in no node")
            continue
        if isinstance(pv, dict) and pv.get("by") == "l3":
            rec = records.get(pv.get("ref"))
            if rec is None:
                L.issues.append(f"{where}: no proofs.jsonl record for {pv.get('ref')}")
                continue
            if (rec["claim"].get("from"), rec["claim"].get("to")) != (w["from"], w["to"]):
                L.issues.append(f"{where}: its record claims {rec['claim'].get('from')} -> {rec['claim'].get('to')}")
                continue
            if rec["claim"].get("zoning") != zones_now:
                L.issues.append(f"{where}: its proof's zoning isn't the level's (a re-derive renumbered the "
                                f"zones): run scripts/l3_certify.py recheck --level {L.name} --write")
                continue
            robust = robust_enough(rec)
        walks.append((a, b, dnf(w.get("kit", "true")), pv, robust))
    L.proofs, L.robust = {}, {}
    out = []
    for x in edges:
        if ASSUMED in x.term or MODELLED in x.term:
            atoms = x.term - {ASSUMED, MODELLED}
            for a, b, kit, pv, robust in walks:
                if (a, b) == (x.a, x.b) and any(implies(atoms, k) for k in kit):
                    x = Atomic(x.a, x.b, x.tier, atoms | {PROBED}, x.through)
                    L.proofs[x], L.robust[x] = pv, robust
                    break
        out.append(x)
    return out


# --------------------------------------------------------------------------- movement certificates (Step R1.14b)
def _cheapest(adj: dict, kept: set, sources: set, usable, tier: int) -> dict:
    """From ``sources`` (kept zones) over the zone edges ``usable`` reads, through zones that aren't kept (a
    kept zone ends a path, as in :func:`contract`): per zone reached, (certified hops, hops, zone number, the edge
    into it), the fewest certified hops first (a walk needs no certificate), then the fewest hops."""
    import heapq
    best = {z: (0, 0, _zone_num(z), None) for z in sources}
    heap = [(0, 0, _zone_num(z), z) for z in sources]
    heapq.heapify(heap)
    while heap:
        c, h, _, u = heapq.heappop(heap)
        if best[u][:2] != (c, h) or (u in kept and u not in sources):
            continue
        for e in adj.get(u, ()):
            if not usable(e):
                continue
            cost = (c + (e.certs[tier] is not None), h + 1, _zone_num(e.to))
            if e.to not in best or cost < best[e.to][:3]:
                best[e.to] = (*cost, e)
                heapq.heappush(heap, (*cost, e.to))
    return best


def _path_certs(best: dict, z: str, tier: int) -> list:
    out = []
    while best[z][3] is not None:
        e = best[z][3]
        if e.certs[tier] is not None:
            out.append(e.certs[tier])
        z = e.frm
    return out


def movement_doc(L: Level) -> dict:
    """What a build re-checks under its own movement (D167, D168; ``docs/RANDOMIZER_DB.md`` §17): for each edge row
    with a modelled flight, each term's witness (the zone path, through zones that aren't kept, with the fewest
    certified hops, that gives the term at its tier) as the certificates of the flights on it; and for each
    node of more than one kept zone, the certificates of the safe-tier, no-item paths that join its zones both
    ways (the node's inside).  Terms with no flight on their witness and edges outside logic aren't listed."""
    from azurkit.tools.randomizer.planner.loader import FORMATS

    adj = collections.defaultdict(list)
    for e in L.edges:
        if not e.through:
            adj[e.frm].append(e)
    zones_of = collections.defaultdict(set)
    for z, n in L.node_of.items():
        zones_of[n].add(z)
    searches: dict = {}

    def witness(x: Atomic) -> list:
        i = x.tier - 1
        term = (x.term - {PROBED}) | {ASSUMED, MODELLED} if PROBED in x.term else x.term

        def usable(e):
            return any(implies(term, t) for t in e.tiers[i])
        if x.through:
            es = [e for e in L.edges if e.through == x.through and L.node_of.get(e.frm) == x.a
                  and L.node_of.get(e.to) == x.b and usable(e)]
            e = min(es, key=lambda e: (e.certs[i] is not None, _zone_num(e.frm), _zone_num(e.to)), default=None)
            return None if e is None else [e.certs[i]] if e.certs[i] else []
        key = (x.a, i, term)
        if key not in searches:
            searches[key] = _cheapest(adj, L.kept, zones_of[x.a], usable, i)
        best = searches[key]
        ends = [z for z in zones_of[x.b] if z in best]
        if not ends:
            return None
        return _path_certs(best, min(ends, key=lambda z: best[z][:3]), i)

    rows = collections.defaultdict(list)
    for x in L.atomic:
        if x.tier == 0:
            continue
        certs = witness(x)
        if certs is None:
            L.issues.append(f"movement: no zone path gives {x.a} -> {x.b} {term_text(x.term)} at tier {x.tier}")
            continue
        conf = "assumed" if ASSUMED in x.term else "physics" if MODELLED in x.term else \
            "probed" if PROBED in x.term else "data"
        rows[(x.a, x.b, x.tier, conf, x.through)].append((term_text(x.term), certs))
    inside = {}
    free = collections.defaultdict(set)
    for key, (per, _) in L.pairs.items():
        if key[0] != "through" and frozenset() in per[0] and L.node_of.get(key[0]) == L.node_of.get(key[1]):
            free[key[0]].add(key[1])
    back = collections.defaultdict(set)
    for a, bs in free.items():
        for b in bs:
            back[b].add(a)
    starts: dict = {}
    for n, zs in sorted(zones_of.items()):
        if len(zs) < 2:
            continue
        root, tree = min(zs, key=_zone_num), set()
        for g, fwd in ((free, True), (back, False)):
            seen, todo = {root}, [root]
            while todo:
                u = todo.pop()
                for v in sorted(g[u] & zs, key=_zone_num):
                    if v not in seen:
                        seen.add(v)
                        todo.append(v)
                        tree.add((u, v) if fwd else (v, u))
        certs = []
        for a, b in sorted(tree, key=lambda ab: (_zone_num(ab[0]), _zone_num(ab[1]))):
            if a not in starts:
                starts[a] = _cheapest(adj, L.kept, {a}, lambda e: frozenset() in e.tiers[0], 0)
            certs += _path_certs(starts[a], b, 0)
        if certs:
            inside[n] = certs
    keyed = {json.dumps(c, sort_keys=True): c for _, ts in rows.items() for _, cs in ts for c in cs}
    keyed |= {json.dumps(c, sort_keys=True): c for cs in inside.values() for c in cs}
    order = sorted(keyed)
    index = {k: j for j, k in enumerate(order)}

    def ids(cs):
        return sorted({index[json.dumps(c, sort_keys=True)] for c in cs})
    edges = []
    for (a, b, tier, conf, through), ts in sorted(rows.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2],
                                                                               kv[0][3], kv[0][4])):
        if not any(cs for _, cs in ts):
            continue
        row = {"from": a, "to": b, "difficulty": tier, "confidence": conf}
        if through:
            row["through"] = list(through)
        row["terms"] = [[t, ids(cs)] for t, cs in sorted(ts)]
        edges.append(row)
    pool = {x["id"] for x in L.gen["locations"] if x["pool"]}
    jumps = {loc["id"]: round(loc["dz"] - PICK_STAND, 2) for loc in L.doc["locations"]
             if loc["id"] in pool and loc.get("how") == "jump" and loc.get("dz") is not None}
    return {"format": FORMATS["movement"], "level": L.name, "certs": [keyed[k] for k in order], "edges": edges,
            "nodes": {n: ids(cs) for n, cs in sorted(inside.items())},
            "jumps": dict(sorted(jumps.items(), key=lambda kv: _loc_key(kv[0])))}


def movement_text(L: Level) -> str:
    """A level's ``data/movement/<level>.json``: :func:`movement_doc`, one certificate, row or node per line."""
    doc = movement_doc(L)
    lines = ["{", f' "format": {json.dumps(doc["format"])},', f' "level": {json.dumps(doc["level"])},', ' "certs": [']
    lines += [f"  {json.dumps(c, sort_keys=True)}," for c in doc["certs"]]
    lines += [' ],', ' "edges": [']
    lines += [f"  {json.dumps(r)}," for r in doc["edges"]]
    lines += [' ],', ' "nodes": {']
    lines += [f"  {json.dumps(n)}: {json.dumps(ids)}," for n, ids in doc["nodes"].items()]
    lines += [' },', ' "jumps": {']
    lines += [f"  {json.dumps(loc)}: {h}," for loc, h in doc["jumps"].items()]
    lines += [' }', "}"]
    text = "\n".join(lines) + "\n"
    return re.sub(r",\n( \]| \})", r"\n\1", text)


# --------------------------------------------------------------------------- TOML text
def _s(x) -> str:
    if isinstance(x, bool):
        return "true" if x else "false"
    if isinstance(x, int):
        return str(x)
    if isinstance(x, str):
        return json.dumps(x, ensure_ascii=False)
    if isinstance(x, list):
        return "[" + ", ".join(_s(v) for v in x) + "]"
    if isinstance(x, dict):
        return "{ " + ", ".join(f"{_s(k) if not re.fullmatch(r'[A-Za-z0-9_]+', k) else k} = {_s(v)}"
                                for k, v in x.items()) + " }" if x else "{}"
    raise TypeError(x)


def _table(name: str, rows: dict, comment: str = "") -> str:
    head = f"[[{name}]]" + (f"  # {comment}" if comment else "")
    return "\n".join([head] + [f"{k} = {_s(v)}" for k, v in rows.items() if v is not None]) + "\n"


# --------------------------------------------------------------------------- the realm
@dataclass
class Realm:
    levels: dict           # name -> Level (authored now)
    world: dict
    tricks: dict
    route: dict
    gens: dict             # every level's generated file
    stub_node: dict        # a stub level -> one of its node ids
    data: Path


def _arrivals(level: str, doc: dict, gens: dict) -> dict:
    """Spot id -> its zone, for every live exit's arrival into ``level``."""
    spot_zone = {o["id"]: o["main_zone"] for o in doc["objects"] if o["kind"] == "spot" and o.get("main_zone")}
    out = {}
    for g in gens.values():
        for x in g["exits"]:
            if x.get("dest_level") == level and x["live"] and x["kind"] in ("exit", "teleport") and x.get("arrival"):
                if x["arrival"] in spot_zone:
                    out[x["arrival"]] = spot_zone[x["arrival"]]
    return out


def plan(levels: list[str], data: Path = DATA, authoring: Path = AUTHORING,
         realm: list[str] | None = None) -> Realm:
    """Phase 1 for each level: its zone graph, kept zones, nodes and edges.
    ``realm`` (default ``levels``) names the levels whose authoring may
    place an arrival in one, so one level plans as it does in its realm."""
    tricks = tomllib.loads((data / "tricks.toml").read_text(encoding="utf-8"))
    world = tomllib.loads((data / "world.toml").read_text(encoding="utf-8"))
    route = tomllib.loads((data / "route.toml").read_text(encoding="utf-8"))
    gens = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((data / "generated").glob("*.json"))}
    from azurkit.tools.randomizer.planner.proofs import FILE, read_proofs
    records = read_proofs(data / FILE)[0]          # the L3 proofs the [[probed]] walks resolve to (D170)
    db_skips = {s["id"]: s for s in tricks["skip"]}
    out = {}
    for name in levels:
        L = build(name, db_skips, data, authoring)
        dark = {n: [] for n in L.spec.get("dark", {})}
        for n, z in L.spec.get("names", {}).items():
            if n in dark:
                dark[n].append(z)
        extra = {z for zs in dark.values() for z in zs}
        for other in levels if realm is None else realm:   # an arrival the authoring places (its spot is on no floor)
            for x in read_spec(other, authoring).get("exit", {}).values():
                if x.get("to", "").startswith(f"{name}.Z"):
                    extra.add(x["to"])
        L.arrival_zones = set(_arrivals(name, L.doc, gens).values())
        L.kept = kept_zones(L, L.arrival_zones, extra)
        L.pairs = contract(L)
        hold_pairs(L)
        L.node_of = merge(L, L.pairs, dark)
        L.atomic = probed(L, reduce_edges(atomic_edges(L.pairs, L.node_of)), records)
        out[name] = L
    stub_node = {}
    for p in sorted((data / "levels").glob("*.toml")):
        if p.stem not in out:
            nodes = tomllib.loads(p.read_text(encoding="utf-8")).get("node", [])
            if nodes:
                stub_node[p.stem] = nodes[0]["id"]
    return Realm(out, world, tricks, route, gens, stub_node, data)


def _node_rows(R: Realm, L: Level) -> list[str]:
    groups = collections.defaultdict(list)
    for z, n in L.node_of.items():
        groups[n].append(z)
    members = collections.defaultdict(list)
    for loc, z in L.spec.get("members", {}).items():
        members[L.node_of[z]].append(loc)
    dark = L.spec.get("dark", {})
    out = []
    for n in sorted(groups, key=lambda n: (not (n == R.world["start"] or n == R.world["hub"]), n)):
        zs = sorted(groups[n], key=_zone_num)
        rows = {"id": n, "anchors": [f"zone:{z}" for z in zs]}
        if n == R.world["start"]:
            rows["start"] = True
        if n == R.world["hub"]:
            rows["hub"] = True
        if n in dark:
            rows["dark"] = dark[n]
        if members[n]:
            rows["locations"] = sorted(members[n])
        out.append(_table("node", rows))
    return out


def _edge_rows(L: Level) -> list[str]:
    """One row per node pair, tier, confidence, ``through`` and proof: a probed row's terms are its one walk's
    (D170), so each asks at least the kit its record's string held (AZ-544)."""
    grouped, proofs = collections.defaultdict(list), {}
    for x in L.atomic:
        conf = "assumed" if ASSUMED in x.term else "physics" if MODELLED in x.term else \
            "probed" if PROBED in x.term else "data"
        key = (x.a, x.b, x.tier, conf, x.through, (pv := L.proofs.get(x)) and pv["ref"] or "")
        grouped[key].append(x.term)
        proofs[key] = pv
    out = []
    for key, terms in sorted(grouped.items(), key=lambda kv: (*kv[0][:2], kv[0][2] or 9, *kv[0][3:])):
        a, b, tier, conf, through, _ = key
        rows = {"from": a, "to": b, "kind": "walk", "requires": dnf_text(terms)}
        if through:
            rows["through"] = list(through)
        if tier > 1:
            rows["difficulty"] = tier
        if tier == 0:
            rows["logic"] = False
        rows["confidence"] = conf
        if proofs[key]:
            rows["proven"] = proofs[key]
        out.append(_table("edge", rows))
    return out


def _exit_rows(R: Realm, L: Level) -> list[str]:
    old = {e.get("exit"): e for e in tomllib.loads((R.data / "levels" / f"{L.name}.toml").read_text(
        encoding="utf-8")).get("edge", []) if e.get("exit")}
    out = []
    for x in L.gen["exits"]:
        if not (x["live"] and x["kind"] in ("exit", "teleport")):
            continue
        sx = L.spec.get("exit", {}).get(x["id"], {})
        z = sx.get("from") or object_zone(L, x["id"])
        if not z:
            L.issues.append(f"exit {x['id']} ({x.get('name')}): no zone holds its switch; give its `from` zone")
            continue
        dest = x["dest_level"]
        if sx.get("to") and ".Z" in sx["to"]:       # a zone of an authored level: the node holding it
            to = R.levels[dest].node_of.get(sx["to"])
            if to is None:
                L.issues.append(f"exit {x['id']}: zone {sx['to']} is in no node of {dest}")
                continue
        elif sx.get("to"):
            to = sx["to"]
        elif dest in R.levels:
            D = R.levels[dest]
            dz = {o["id"]: o.get("main_zone") for o in D.doc["objects"]}.get(x.get("arrival"))
            to = D.node_of.get(dz) if dz else None
            if to is None:
                L.issues.append(f"exit {x['id']}: its arrival {x.get('arrival')} is in no node of {dest}")
                continue
        else:
            prev = old.get(x["id"], {}).get("to")
            to = prev if prev and prev.startswith(dest + "_") else R.stub_node.get(dest)
        kind = "cart" if sx.get("cart") else "teleport" if (dest == L.name or sx.get("disc")) else "exit"
        rows = {"from": L.node_of[z], "to": to, "kind": kind, "exit": x["id"], "lock": sx.get("cart"),
                "logic": sx.get("logic"), "disc": sx.get("disc"), "requires": sx.get("requires", "true"),
                "confidence": "data"}
        out.append(_table("edge", rows, f"{x.get('name')} -> {dest} ({x.get('arrival_by')})" +
                          (f"; {sx['why']}" if sx.get("why") else "")))
    return out


def _object_rows(R: Realm, L: Level) -> list[str]:
    spec, out = L.spec, []

    def node(z, what):
        if z is None or z not in L.node_of:
            L.issues.append(f"{what}: zone {z} is in no node")
            return ""
        return L.node_of[z]
    for b in L.gen["barriers"]:
        bid = L.hand_of[b["id"]]
        sb = spec.get("barrier", {}).get(bid, {})
        rows = {"id": bid, "of": b["id"],
                "destroy_from": sorted({node(z, f"barrier {bid}") for z in L.destroy_from[bid]}),
                "bypass": {f"{L.node_of[k.split('->')[0]]}->{L.node_of[k.split('->')[1]]}": v
                           for k, v in sb.get("bypass", {}).items()} or None}
        for key in ("requires", "override_requires", "override_reason", "persist", "persist_reason"):
            rows[key] = sb.get(key)
        out.append(_table("barrier", rows, f"{b['kind']} {b.get('damage')}, generated requires {b['requires']}, "
                                           f"{b['persist']}" + (f"; {sb['why']}" if sb.get("why") else "")))
    for kind in ("keylocks", "seals", "obsidian_locks"):
        for o in L.gen[kind]:
            if kind == "keylocks" and not o["coded"]:
                continue
            bid = L.hand_of[o["id"]]
            z = spec.get("button", {}).get(bid) or object_zone(L, o["id"])
            out.append(_table("button", {"id": bid, "of": o["id"], "at": node(z, f"button {bid}"), "mode": "latch"},
                              f"{kind[:-1]}, generated requires {o.get('requires')}"))
    for e in spec.get("event", ()):
        rows = {"id": e["id"], "of": e.get("of"), "at": node(e["zone"], f"event {e['id']}"),
                "requires": e.get("requires", "true"), "terminal": e.get("terminal")}
        out.append(_table("event", rows, e.get("why", "")))
    ev_doc = {e["id"]: e for e in L.doc["events"]}
    for eid, z in sorted(L.events.items()):
        ev = ev_doc[eid]
        out.append(_table("event", {"id": eid, "at": node(z, f"event {eid}"), "requires": "true"},
                          f"derived: {ev['kind']} of {ev.get('platform') or ev.get('spot') or eid}"))
    rows = {loc["id"]: dict(loc) for loc in spec.get("location", ())}
    pool = {x["id"] for x in L.gen["locations"] if x["pool"]}
    for loc in L.doc["locations"]:      # what the derive needs beyond the location's zone (Step R1.11a)
        lid = loc["id"]
        if lid not in pool or not loc.get("zone") or lid in spec.get("members", {}) or "requires" in rows.get(lid, {}):
            continue
        if loc.get("how") == "jump" and loc.get("requires", "true") != "true":
            rows[lid] = dict(rows.get(lid, {"id": lid}), requires=loc["requires"],
                             note="derived: a jump from its zone's floor (how = jump)")
        elif loc.get("requires") == "false":
            L.issues.append(f"location {lid} ({loc.get('how')}): the derive holds it over its zone; give its "
                            f"requirement ([[location]]) or its zone ([members])")
    for lid in proven_by_data(R, L):
        rows.setdefault(lid, {"id": lid}).setdefault(
            "proven", {"by": "data", "ref": f"rando author: derived/{L.name}.json.gz, safe-tier data and physics edges both ways"})
    for lid, mark in L.route_proven.items():
        rows.setdefault(lid, {"id": lid}).setdefault("proven", mark)
    for lid in sorted(rows, key=_loc_key):
        out.append(_table("location", {k: rows[lid].get(k) for k in ("id", "requires", "exclude", "farmable",
                                                                       "proven", "note")}))
    return out


def _loc_key(lid: str):
    f, g, r = lid.split("/")
    return f, int(g[1:]), int(r[1:])


def proven_by_data(R: Realm, L: Level) -> list[str]:
    """D122's ``by = "data"``: the non-gem pool locations whose requirement
    is exact from decoded data: on a floor the derive placed them on, with
    no hand override, and whose node a path of safe-tier edges (floors,
    decoded gates and the measured envelope's safe flights; no probe-needed
    or hand edge) joins both ways with the level's arrivals and exits
    (whatever their atoms ask: each is a decoded gate, item or event)."""
    adj, radj = collections.defaultdict(set), collections.defaultdict(set)
    for x in L.atomic:
        if x.tier == 1 and ASSUMED not in x.term and (PROBED not in x.term or L.robust.get(x)):
            adj[x.a].add(x.b)
            radj[x.b].add(x.a)
    arrivals = {L.node_of[z] for z in _arrivals(L.name, L.doc, R.gens).values() if z in L.node_of}
    switch = {x["id"]: L.spec.get("exit", {}).get(x["id"], {}).get("from") or object_zone(L, x["id"])
              for x in L.gen["exits"] if x["live"]}
    exits = {L.node_of[z] for z in switch.values() if z in L.node_of}

    def bfs(src, g):
        seen, todo = set(src), list(src)
        while todo:
            for v in g[todo.pop()]:
                if v not in seen:
                    seen.add(v)
                    todo.append(v)
        return seen
    ok = bfs(arrivals, adj) & bfs(exits, radj)
    hand = set(L.spec.get("members", {})) | {x["id"] for x in L.spec.get("location", ()) if "requires" in x}
    gen = {x["id"]: x for x in L.gen["locations"]}
    out = []
    for loc in L.doc["locations"]:
        g = gen[loc["id"]]
        if (g["pool"] and g["class"] != "gem" and loc.get("how") == "floor" and loc["id"] not in hand
                and L.node_of.get(loc.get("zone")) in ok):
            out.append(loc["id"])
    return out


def _skip_rows(R: Realm, L: Level) -> list[str]:
    fams = {t["name"] for t in R.world["trick"]}
    out = []
    for s in R.tricks["skip"]:
        if s["level"] != L.name or not all(f in fams for f in s["tricks"]):
            continue
        rows = {k: s.get(k) for k in ("id", "name", "tricks", "requires", "difficulty", "status", "confirmed", "from",
                                      "to", "gates", "tiers", "batch", "batch_name")}
        out.append(_table("skip", rows))
    return out


def level_text(R: Realm, L: Level) -> str:
    route = [s["id"] for s in R.route["step"] if s["kind"] == "location" and s["level"] == L.name]
    parts = [HEADER.format(level=L.name),
             f'format = "azurik-rando-level/1"\nlevel = "{L.name}"\nstatus = "authored"\nknown_traps = []\n'
             f"route = {_s(route)}\n",
             "# ---- nodes: the kept zones, joined where the safe tier walks both ways with no item --------------\n"]
    parts += _node_rows(R, L)
    parts.append("# ---- edges: the zone graph contracted onto the nodes, one edge per tier and confidence -------------\n")
    parts += _edge_rows(L)
    parts.append("# ---- exits ---------------------------------------------------------------------------------\n")
    parts += _exit_rows(R, L)
    parts.append("# ---- barriers, buttons, events and location overrides ----------------------------------------\n")
    parts += _object_rows(R, L)
    parts.append("# ---- skips: tricks.toml's, projected (FORMAT 4.8) ---------------------------------------------\n")
    parts += _skip_rows(R, L)
    return "\n".join(parts)


def stub_arrivals(R: Realm) -> dict[str, str]:
    """Each stub level file with the ``to`` of its exits into an authored
    level set to the node its arrival is in: {path: new text} for those that
    change."""
    out = {}
    for p in sorted((R.data / "levels").glob("*.toml")):
        if p.stem in R.levels:
            continue
        text = p.read_text(encoding="utf-8")
        exits = {x["id"]: x for x in R.gens[p.stem]["exits"]}
        blocks = re.split(r"(?m)^(?=\[\[)", text)
        for i, blk in enumerate(blocks):
            m = re.search(r'(?m)^exit = "([^"]+)"', blk) if blk.startswith("[[edge]]") else None
            if not m or m.group(1) not in exits:
                continue
            x = exits[m.group(1)]
            D = R.levels.get(x.get("dest_level"))
            if D is None or not x.get("arrival"):
                continue
            dz = {o["id"]: o.get("main_zone") for o in D.doc["objects"]}.get(x["arrival"])
            to = D.node_of.get(dz)
            if to:
                blocks[i] = re.sub(r'(?m)^to = "[^"]*"', f'to = "{to}"', blk, count=1)
        new = "".join(blocks)
        if new != text:
            out[str(p)] = new
    return out


def route_marks(db) -> dict[str, dict]:
    """D169: {location: its by-route mark} for the spots the vanilla route
    proves (``Logic.route_walks``, held to ``Logic.kit_short``) that carry
    no other proven mark in ``db``; a walk the logic outdoes only with some
    skips on names them and the items it holds for then
    (``Logic.route_terms``, AZ-725)."""
    from azurkit.tools.randomizer.planner.solver import Logic
    other = {o["id"] for doc in db.levels.values() for o in doc["location"]
             if o.get("proven", {}).get("by", "route") != "route"}
    logic, out = Logic(db), {}
    for loc, (step, kin, kout) in logic.route_walks().items():
        if loc in other:
            continue
        mark = {"by": "route",
                "ref": f"rando author: route.toml step {step}, its kit within the logic's requirement both ways"}
        if logic.kit_short(loc, kin, kout) is None:
            out[loc] = mark
        elif terms := logic.route_terms(loc, kin, kout):
            out[loc] = {**mark, "unless": terms[0], **({"only": terms[1]} if terms[1] else {})}
    return out


def prove_by_route(R: Realm, files: dict[str, str]) -> list[str]:
    """Set each level's ``route_proven`` to its :func:`route_marks` over the
    database ``files`` make (its level and movement files; the rest of
    ``R.data`` as it is); the database's issues if it doesn't load."""
    from azurkit.tools.randomizer.planner.loader import check_database
    report = check_database(R.data, {Path(p).relative_to(R.data).as_posix(): text for p, text in files.items()})
    if report.database is None:
        return [f"the database the new files make doesn't load, so no route proofs (D169): {i}" for i in report.issues]
    for loc, mark in route_marks(report.database).items():
        if (L := R.levels.get(loc.split("/")[0])) is not None:
            L.route_proven[loc] = mark
    return []


def author(levels: list[str], data: Path = DATA,
           authoring: Path = AUTHORING) -> tuple[dict[str, str], list[str]]:
    """({path: text} for every file the authoring writes, [issues]). Every authored
    level is named together (their exits arrive in each other's nodes):
    ``ValueError`` names those left out."""
    missing = sorted(p.stem for p in (data / "levels").glob("*.toml") if p.stem not in levels
                     and tomllib.loads(p.read_text(encoding="utf-8")).get("status") == "authored")
    if missing:
        raise ValueError(f"name every authored level together (their exits arrive in each other's nodes); "
                         f"missing: {' '.join(missing)}")
    R = plan(levels, data, authoring)
    files, issues = {}, []
    for name, L in R.levels.items():
        files[str(data / "levels" / f"{name}.toml")] = level_text(R, L)
        files[str(data / "movement" / f"{name}.json")] = movement_text(L)
    files.update(stub_arrivals(R))
    for L in R.levels.values():
        issues += [f"{L.name}: {i}" for i in L.issues]
    if not issues:
        issues = prove_by_route(R, files)
        for name, L in R.levels.items():
            if L.route_proven:
                files[str(data / "levels" / f"{name}.toml")] = level_text(R, L)
    return files, issues
