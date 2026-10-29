"""A build's own movement in the randomizer's logic (Step R1.14b; D167,
D168; ``docs/RANDOMIZER.md`` § Movement).

The level files are the logic at vanilla movement.  What of it rests on a
modelled flight is in ``data/movement/<level>.json`` (``rando author``
writes it; the loader reads it as ``Database.movement``): per edge row, each
term's witness certificates (:class:`~.physics.Certificate`: the flights on
the zone path that gives the term); per node, the certificates of the
paths that join its zones; per jumped-to pool location, its height above
standing reach.  A build with other movement (:meth:`~.physics.Movement.from_params`
of its sliders) re-checks them (:func:`recheck`) before its fill:

- an edge term whose witness flights all stay (:func:`~.physics.keeps`) at
  the row's difficulty keeps it, else takes the first harder tier where they
  do, else leaves logic (``logic = false``, difficulty 0: R_phys keeps the
  physical graph as it is, so the trap check reads what vanilla's does).
  That is the fast (seeded) flap search's verdict; a term it takes out of
  the build's tier's logic is judged again at the tiers up to the build's
  by the ranges' verdict (:func:`_kept`: a failure only once the exact
  search confirms it), so that tier's logic is the one the logic-safe
  ranges count (AZ-369); the rows of the harder tiers, which a fill at the
  build's tier never reads, keep the fast verdict, which errs harder;
- a jumped-to location needs the least air rank whose rise reaches it at
  the build's tier;
- the zones' free movement (:func:`~.physics.free_certs`) and each node's
  inside are what the nodes stand on: one that fails at the build's tier
  (the ranges' verdict) is ``broken`` (no re-check splits a node), and the
  build's ``logic_verified`` is false.

Stronger movement keeps vanilla's edges but where a taller jump under a
stored roof lands short (the roof stops its rise); a flight vanilla can't
make needs a re-derive.  The slider
side: :data:`MODELLED` (the sliders a certificate reads), :func:`required`
(the certificates a plan's playthrough rests on) and :func:`slider_ranges`
(each slider's logic-safe range for them).  Stdlib only, but for
:func:`default_ranges`' user cache (platformdirs).
"""

from __future__ import annotations

import collections
import math
import time
from collections.abc import Mapping
from dataclasses import dataclass, replace

from azurkit.tools.randomizer.physics import (
    PICK_STAND,
    RUN_SPEED,
    SLIDERS,
    VANILLA,
    Certificate,
    Movement,
    bisect_range,
    envelope,
    free_certs,
    keeps,
    read_as,
    slack,
    tier_margins,
)
from azurkit.tools.randomizer.planner.settings import MOVEMENT_TIERS

# The Movement fields some certificate reads: a slider on another field (the roll, the swim) is outside the model
MODELLED = frozenset({"run_speed", "jump_scale", "gravity", "air_control_scale", "flap_scale", "flaps",
                      "flap_ceiling_scale", "descent_scale", "descent_fuel_scale", "flap_fuel_scale", "fps"})
RANK_ATOM = "air>="


def describe(c: Certificate) -> str:
    """A certificate in words."""
    if c.walk_off:
        return f"a {c.gap - 0.25:.1f} m walk-off down {-c.dh:.1f} m"
    if c.lip:
        return f"a lip lift onto a ledge {c.dh:.2f} m up"
    kit = "plain jump" if c.rank == 0 else f"air {c.rank} flight"
    roof = f" under a roof {c.headroom:.1f} m up" if c.headroom is not None else ""
    return f"a {'running' if c.run else 'standing'} {kit} over {c.gap:.1f} m to {c.dh:+.1f} m{roof}"


def _join(texts) -> str:
    texts = sorted(texts)
    return " | ".join(f"({x})" if " & " in x and len(texts) > 1 else x for x in texts)


def _key(row: Mapping) -> tuple:
    return (row["from"], row["to"], row.get("difficulty", 1), row.get("confidence"), tuple(row.get("through", ())))


@dataclass(frozen=True)
class Recheck:
    """What :func:`recheck` found: the level tables as the logic reads them
    under ``movement`` (``db.levels`` itself when nothing changed), the edge
    terms moved to a harder tier or out of logic, the jumped-to locations
    that need more air, and what the logic's nodes stand on that fails at
    ``tier`` (``broken``: the logic can't hold)."""
    movement: Movement
    tier: str
    levels: dict
    retiered: tuple[str, ...] = ()
    dropped: tuple[str, ...] = ()
    relocated: tuple[str, ...] = ()
    broken: tuple[str, ...] = ()
    seconds: float = 0.0
    unproven: tuple[str, ...] = ()
    """The proven pool locations whose proof rolls at garret4's x1 roll,
    no proof at another (:func:`roll_proofs`): unproven in ``levels``."""


# --------------------------------------------------------------------------- contact flights measured in L3
# contact.json (Step X.11): a certificate's slider ranges measured in L3, the game's own code, with a build laid over
# a vanilla snapshot (scripts/l3_contact.py).  Per Movement field (flaps per shield: flaps1-3) and measured tier, the
# range [lo, hi] in which the flight still works (None: that side not measured).  A tier reads the range measured
# at it or, failing that, at the next stricter tier measured; safe has none measured, so the calculator decides, but
# a laxer tier's range refutes: a flight L3 fails at standard fails at safe too (REFUTE_TIERS, Step X.21).
RANGE_TIERS = {"standard": ("standard",), "hard": ("hard", "standard"),
               "frame_perfect": ("frame_perfect", "hard", "standard")}
REFUTE_TIERS = {"safe": ("standard",)}


def changed(m: Movement) -> list[tuple[str, float]]:
    """The Movement fields ``m`` sets otherwise than vanilla (the flaps per shield: ``flaps1`` .. ``flaps3``)."""
    out = [(f"flaps{i}", float(v)) for i, (v, v0) in enumerate(zip(m.flaps, VANILLA.flaps), 1) if v != v0]
    return out + [(f, float(getattr(m, f))) for f in MODELLED - {"flaps"} if getattr(m, f) != getattr(VANILLA, f)]


def measured(db) -> dict[Certificate, dict]:
    """``contact.json``'s ranges by certificate: each measured flight's (when its certificate is in no other
    level's movement file: a measurement is of one flight), and the free walk-off ranges for every walk-off of
    the zones' free movement (:func:`~.physics.free_certs`)."""
    where: dict[Certificate, set] = collections.defaultdict(set)
    for lvl, md in db.movement.items():
        for c in md["certs"]:
            where[Certificate.from_dict(c)].add(lvl)
    out = {}
    for f in db.contact.get("flights", []):
        c = Certificate.from_dict(f["cert"])
        if where.get(c) == {f["level"]}:
            out[c] = f["ranges"]
    walk = db.contact.get("free", {}).get("walk_off")
    if walk:
        out |= {c: walk["ranges"] for c in free_certs() if c.walk_off}
    return out


def verdict(ranges: dict | None, m: Movement, tier: str) -> bool | None:
    """Does the measured flight keep under ``m`` at ``tier``: inside its range, or None where no measurement
    decides (more than one field changed, the field or the side unmeasured, or the tier has none); at a tier
    with none, False past a laxer tier's range (:data:`REFUTE_TIERS`)."""
    diff = changed(m)
    if not ranges or len(diff) != 1 or diff[0][0] not in ranges:
        return None
    (name, v), by = diff[0], ranges[diff[0][0]]
    v0 = float(VANILLA.flaps[int(name[-1]) - 1]) if name.startswith("flaps") else float(getattr(VANILLA, name))
    for tiers, keeps_inside in ((RANGE_TIERS.get(tier, ()), True), (REFUTE_TIERS.get(tier, ()), False)):
        r = next((by[t] for t in tiers if t in by), None)
        if r is not None and (r[0] if v < v0 else r[1]) is not None:
            inside = r[0] - 1e-9 <= v if v < v0 else v <= r[1] + 1e-9
            return inside if keeps_inside else (None if inside else False)
    return None


class _Checker:
    """keeps() of each certificate at each tier, once; a measured flight's own ranges where they decide."""

    def __init__(self, m: Movement, beam: int, contact: dict | None = None):
        self.env, self.margins, self.memo = envelope(m, beam, seeded=True), tier_margins(), {}
        self.contact, self.confirmed = contact or {}, {}

    def ok(self, c: Certificate, tier: str) -> bool:
        """The fast (seeded) search's verdict."""
        key = (c, tier)
        if key not in self.memo:
            v = verdict(self.contact.get(c), self.env.m, tier)
            self.memo[key] = keeps(c, self.env, self.margins[tier]) if v is None else v
        return self.memo[key]

    def kept(self, c: Certificate, tier: str) -> bool:
        """The ranges' verdict (:func:`_kept`): :meth:`ok`, a failure only once the exact search confirms it."""
        key = (c, tier)
        if key not in self.confirmed:
            self.confirmed[key] = self.ok(c, tier) or _kept(c, self.env, self.margins[tier], tier, self.contact)
        return self.confirmed[key]

    def rank(self, h: float, tier: str) -> int:
        """The least air rank whose rise reaches ``h`` m above standing reach at ``tier`` (4: none).  A height
        vanilla's rank reaches only within the derive's 0.1 m rounding counts as that rank's vanilla rise."""
        cl, base = self.margins[tier].clearance, envelope(VANILLA, self.env.beam)
        r_v = next((r for r in range(4) if base.rise(r) - cl >= h - 0.05), 4)
        if r_v < 4:
            h = min(h, base.rise(r_v) - cl)
        return next((r for r in range(4) if self.env.rise(r) - cl >= h - 1e-9), 4)


SWIM_STATES = frozenset({"0x2", "0x6"})
"""The move states a press of BLACK dives in, not rolls (w3/g1/r2006's)."""


def roll_proofs(db) -> frozenset[str]:
    """The proven pool locations whose proof rests on garret4's x1 roll
    (Step 2.133, D330, AZ-607): an L3 string that presses BLACK with a state
    other than the swim's in its outcome (a ground roll: e6/g0/r2747; the
    outcome's states are runs, not ticks, so the coarse rule, the critique's
    3), or an xemu proof, which carries no string."""
    out = set()
    for level in db.levels.values():
        for loc in level.get("location", []):
            pv = loc.get("proven")
            if not isinstance(pv, dict) or pv.get("by") not in ("l3", "xemu"):
                continue
            rec = db.proofs.get(pv.get("ref"), {}) if pv["by"] == "l3" else {}
            black = any("black" in seg.get("buttons", ()) for seg in rec.get("string", {}).get("segments", ()))
            if pv["by"] == "xemu" or (black and set(rec.get("outcome", {}).get("states", ())) - SWIM_STATES):
                out.add(loc["id"])
    return frozenset(out)


def rolling_skips(db) -> frozenset[str]:
    """The skips tricks.toml marks ``rolls = true`` (Step 2.133, AZ-607):
    proven at garret4's x1 roll (the rjump skips, w1.shoreline_rollthrough)."""
    return frozenset(s["id"] for s in db.tricks.get("skip", ()) if s.get("rolls"))


def _unproven(level: dict, ids: frozenset[str]) -> dict:
    """``level`` with ``ids``' locations' proven marks dropped."""
    if not any(x.get("id") in ids and "proven" in x for x in level.get("location", [])):
        return level
    return dict(level, location=[{k: v for k, v in x.items() if k != "proven"} if x.get("id") in ids else x
                                 for x in level.get("location", [])])


def recheck(db, movement: Movement, tier: str, beam: int = 20) -> Recheck:
    """The logic of ``db`` under ``movement`` at the movement tier ``tier``
    (the module docstring).  Vanilla movement changes nothing; a roll
    other than garret4's x1, in distance or in time, makes the proofs
    that roll no proof (:func:`roll_proofs`, Steps 2.133, 2.185)."""
    t0 = time.perf_counter()
    if movement == VANILLA:
        return Recheck(movement, tier, db.levels)
    rolls = (roll_proofs(db) if movement.roll_scale != 1.0 or movement.roll_time_scale != 1.0
             else frozenset())   # a roll at another speed leaves an edge at another (Step 2.185)
    chk, top = _Checker(movement, beam, measured(db)), MOVEMENT_TIERS.index(tier) + 1
    levels, retiered, dropped, relocated, broken = {}, [], [], [], []
    for c in free_certs():
        if not chk.kept(c, tier):
            broken.append(f"the zones' free movement: {describe(c)} (every node assumes it)")
            break
    for lvl, level in db.levels.items():
        md = db.movement.get(lvl)
        if not md:
            levels[lvl] = _unproven(level, rolls)
            continue
        certs = [Certificate.from_dict(c) for c in md["certs"]]
        for node, ids in md["nodes"].items():
            bad = next((certs[i] for i in ids if not chk.kept(certs[i], tier)), None)
            if bad is not None:
                broken.append(f"node {node}'s inside: {describe(bad)}")
        rows = {_key(r): r["terms"] for r in md["edges"]}
        edges = []
        for e in level.get("edge", []):
            terms = rows.get(_key(e))
            if terms is None:
                edges.append(e)
                continue
            d, at = e.get("difficulty", 1), collections.defaultdict(list)
            for text, ids in terms:
                nd = next((t for t in range(d, 5) if all(chk.ok(certs[i], MOVEMENT_TIERS[t - 1]) for i in ids)), 0)
                if d <= top and not 1 <= nd <= top:   # the fast search takes it out of this tier's logic: the
                    # ranges' verdict decides (AZ-369), the cheaper flights confirmed first (a flapless one: no search)
                    cs = sorted((certs[i] for i in ids), key=lambda c: 0 if c.flaps == 0 else c.rank)
                    nd = next((t for t in range(d, top + 1) if all(chk.kept(c, MOVEMENT_TIERS[t - 1]) for c in cs)), nd)
                if nd == 0:
                    dropped.append(f"{e['from']} > {e['to']} ({text})")
                elif nd != d:
                    retiered.append(f"{e['from']} > {e['to']} ({text}): {MOVEMENT_TIERS[d - 1]} -> "
                                    f"{MOVEMENT_TIERS[nd - 1]}")
                at[nd].append(text)
            for nd, texts in sorted(at.items()):     # difficulty 0: out of logic, still physical (R_phys)
                row = {k: v for k, v in e.items() if k != "difficulty"} | {"requires": _join(texts)}
                edges.append(row | ({"difficulty": nd} if nd != 1 else {}) | ({"logic": False} if nd == 0 else {}))
        locs = {x["id"]: x for x in level.get("location", [])}
        for loc, h in md.get("jumps", {}).items():
            r_v, r_m = _vanilla(beam).rank(h, tier), chk.rank(h, tier)
            if r_m <= r_v:
                continue
            relocated.append(f"{loc}: a jump {h + PICK_STAND:.1f} m up needs "
                             + (f"air {r_m}" if r_m < 4 else "more than air 3"))
            old = locs.get(loc, {"id": loc}).get("requires", "true")
            need = f"{RANK_ATOM}{r_m}" if r_m < 4 else "false"
            locs[loc] = dict(locs.get(loc, {"id": loc}), requires=need if old == "true" else f"({old}) & {need}")
        levels[lvl] = _unproven(dict(level, edge=edges, location=list(locs.values())), rolls)
    return Recheck(movement, tier, levels, tuple(retiered), tuple(dropped), tuple(relocated), tuple(broken),
                   time.perf_counter() - t0, tuple(sorted(rolls)))


_VANILLA_CHECKERS: dict = {}


def _vanilla(beam: int) -> _Checker:
    if beam not in _VANILLA_CHECKERS:
        _VANILLA_CHECKERS[beam] = _Checker(VANILLA, beam)
    return _VANILLA_CHECKERS[beam]


def logic_for(db, movement: Movement, tier: str):
    """(:class:`~.planner.solver.Logic` of ``db`` under ``movement``, the
    :class:`Recheck`): the fill and the spoiler read it; ``db`` itself
    (its digest, the writer) is unchanged."""
    from azurkit.tools.randomizer.planner.solver import Logic

    rc = recheck(db, movement, tier)
    return Logic(db if rc.levels is db.levels else replace(db, levels=rc.levels)), rc


def run_floor(sliders: Mapping) -> dict[str, dict[str, float]] | None:
    """``sliders`` (``{pack: {slider: value}}``) with the walk at
    garret4's run when their run is under his 7 m/s (the walk slider
    under 1, or a worn body's size under 1 folded into it: Step 2.133,
    D353): what a plan falls back to when none fills on the logic
    re-checked at the slower run (``layer.plan_for``, AZ-606); ``None``
    when the run isn't under his."""
    if not Movement.from_params(sliders).run_speed < RUN_SPEED:
        return None
    kept = {pack: {name: v for name, v in values.items() if (pack, name) != ("player_physics", "walk_speed_scale")}
            for pack, values in sliders.items()}
    return {pack: values for pack, values in kept.items() if values}


def logic_of(base, settings):
    """The :class:`~.planner.solver.Logic` a plan under ``settings`` stands
    on (AZ-383): ``base`` (the database's vanilla Logic, or the database
    itself) when they hold no movement slider, else :func:`logic_for`'s
    under their sliders at their tier."""
    from azurkit.tools.randomizer.planner.solver import Logic

    db = base.db if isinstance(base, Logic) else base
    if not settings.sliders:
        return base if isinstance(base, Logic) else Logic(db)
    return logic_for(db, Movement.from_params(settings.sliders), settings.movement_tier)[0]


# --------------------------------------------------------------------------- the sliders' logic-safe ranges
def _hops(logic, settings, label=None) -> dict:
    """(canonical from, to) -> [(rule, certificates, label)] of ``logic``'s
    edges in ``settings``' tier, one per term (its movement row's, else the
    whole requirement with none); ``label(level, edge)`` marks an edge."""
    db, rules = logic.db, logic.rules(settings)
    tier = MOVEMENT_TIERS.index(settings.movement_tier) + 1
    hops = collections.defaultdict(list)
    for lvl, level in sorted(db.levels.items()):
        md = db.movement.get(lvl) or {}
        certs = [Certificate.from_dict(c) for c in md.get("certs", ())]
        recs = {_key(r): r["terms"] for r in md.get("edges", ())}
        for e in level.get("edge", []):
            if not (e.get("logic", True) and 1 <= e.get("difficulty", 1) <= tier and e["to"]):
                continue
            mark = label(lvl, e) if label else None
            for text, ids in recs.get(_key(e), [[e.get("requires", "true"), []]]):
                edge = rules.edge(lvl, dict(e, requires=text))
                if edge:
                    hops[edge[:2]].append((edge[2], frozenset(certs[i] for i in ids), mark))
    return hops


def _walk(plan, logic, take) -> None:
    """``take(path, counters, flags)`` for each node path ``plan``'s
    playthrough walks: the spoiler's obtain and return paths (plan §3.6) at
    their sphere's state, and a path from the start to every node the end
    state reaches and back (so every location stays collectable)."""
    from azurkit.tools.randomizer.planner.plan import spheres

    st = plan.settings
    rules = logic.rules(st)
    for sp in spheres(plan, logic):
        for s in sp.steps:
            take(s.obtain, sp.counters, sp.flags)
            after = dict(sp.counters)
            logic._add(collections.Counter(), after, s.item, logic.vanilla[s.location][1])
            take(s.back, after, sp.flags)
    reach = logic.reach(st, plan.placement)
    counters, flags = logic.everything, reach.flags
    for adj in (rules.adj, rules.radj):          # every node reached, from the start and back to it
        parent, todo = {logic.start: None}, collections.deque([logic.start])
        while todo:
            u = todo.popleft()
            for v, rule in adj.get(u, ()):
                if v not in parent and rule(counters, flags):
                    parent[v] = u
                    todo.append(v)
        for v, u in parent.items():
            if u is not None:
                take((u, v) if adj is rules.adj else (v, u), counters, flags)


def required(plan, logic) -> dict[Certificate, str]:
    """The certificates ``plan``'s playthrough stands on at its tier, each
    with what it carries (its first): every hop of :func:`_walk`'s paths,
    each by the passable term with the most room (its certificates' least
    :func:`~.physics.slack` at vanilla, as :func:`~.physics.read_as` reads
    them); the inside of each node on them; and the zones' free movement.
    While they all stay, the plan verifies under the movement too."""
    db, st = logic.db, plan.settings
    hops = _hops(logic, st)
    inside = {n: [Certificate.from_dict(md["certs"][i]) for i in ids]
              for md in db.movement.values() for n, ids in md["nodes"].items()}
    out: dict[Certificate, str] = dict.fromkeys(free_certs(), "the zones' free movement")
    base, margin, room = envelope(VANILLA, 20), tier_margins()[st.movement_tier], {}

    def robust(cs) -> tuple:
        """The least room among a term's certificates at vanilla (one vanilla doesn't reproduce: none), more first."""
        for c in cs:
            if c not in room:
                read = read_as(c, base, margin)
                room[c] = -1.0 if read is None else slack(read, base, margin)
        return (-min((room[c] for c in cs), default=math.inf), len(cs))

    def take(path, counters, flags) -> None:
        for u, v in zip(path, path[1:]):
            v = v.removesuffix(" (disc teleport)")
            ways = [cs for rule, cs, _ in hops.get((u, v), ()) if rule(counters, flags)]
            for c in min(ways, key=robust, default=()):
                out.setdefault(c, f"{u} > {v}")
            for n in (u, v):
                for c in inside.get(n, ()):
                    out.setdefault(c, f"{n}'s inside")

    _walk(plan, logic, take)
    return out


def unjudged(plan, logic, db) -> list[str]:
    """The hops of ``plan``'s playthrough (:func:`_walk`'s, on ``logic``)
    that the re-check can't judge (AZ-384): every passable way of the hop is
    an edge of ``db`` (the database at vanilla movement) with no movement
    row that isn't ``data`` (a floor, a decoded gate, an exit): a hand edge,
    an admitted ride, door or current, a probed walk, an edge past an
    undecoded gate. Each as ``"<level>: <from> > <to> (<requires>)"``, in
    the order first walked."""
    from azurkit.tools.randomizer.planner.fill import canonical

    plain = set()
    for lvl, level in db.levels.items():
        recs = {_key(r) for r in (db.movement.get(lvl) or {}).get("edges", ())}
        plain |= {canonical(e) for e in level.get("edge", []) if e.get("confidence") != "data" and _key(e) not in recs}
    hops = _hops(logic, plan.settings, lambda lvl, e: f"{lvl}: {e['from']} > {e['to']} ({e.get('requires', 'true')})"
                 if canonical(e) in plain else None)
    out: dict[str, None] = {}

    def take(path, counters, flags) -> None:
        for u, v in zip(path, path[1:]):
            ways = [mark for rule, _, mark in hops.get((u, v.removesuffix(" (disc teleport)")), ())
                    if rule(counters, flags)]
            if ways and all(ways):
                out.setdefault(min(ways), None)

    _walk(plan, logic, take)
    return list(out)


# Each movement slider's direction (D168: the feasible set is an orthant in every slider but the jump's own height):
# the side of vanilla where the player moves less (a logic_floor's), and whether the other side can raise the jump's
# own apex (a roof clips a taller arc, which then lands sooner), so both sides are searched; for the rest the other
# side keeps everything.
WEAKER = {("player_physics", "gravity"): +1, ("player_physics", "flap_entry_fuel_cost_scale"): +1,
          ("player_physics", "flap_descent_fuel_cost_scale"): +1, ("fps_unlock", "target_fps"): -1}
TALLER = frozenset({("player_physics", "jump_speed_scale"), ("player_physics", "gravity"),
                    ("fps_unlock", "target_fps")})


def _vanilla_value(pack: str, name: str) -> float:
    fld, scale = SLIDERS[(pack, name)]
    return float(VANILLA.flaps[scale] if fld == "flaps" else getattr(VANILLA, fld) / (scale or 1.0))


def _weaker(pack: str, name: str, value: float) -> bool:
    """A modelled slider (:data:`MODELLED`) at ``value``, on vanilla's weaker side (:data:`WEAKER`)."""
    fld = SLIDERS[(pack, name)][0]
    v = math.trunc(value) if fld == "flaps" else value    # the armor loader truncates
    return fld in MODELLED and (v - _vanilla_value(pack, name)) * WEAKER.get((pack, name), -1) > 1e-9


def weaker(sliders: Mapping) -> list[str]:
    """The modelled movement sliders of ``sliders`` (``{pack: {slider:
    value}}``) weaker than vanilla, each in words: with them a hop the
    re-check can't judge (:func:`unjudged`) leaves a plan unverified (AZ-384)."""
    return [f"{pack} {name} {v:g}" for pack, values in sorted(sliders.items())
            for name, v in sorted(values.items()) if _weaker(pack, name, v)]


def _taller(pack: str, name: str, value: float) -> bool:
    """A slider that can raise the jump's own apex (:data:`TALLER`) at ``value``, on vanilla's stronger side."""
    return (pack, name) in TALLER and (value - _vanilla_value(pack, name)) * WEAKER.get((pack, name), -1) < -1e-9


def taller(sliders: Mapping) -> list[str]:
    """The sliders of ``sliders`` that raise the jump's arc over vanilla's
    (:data:`TALLER` on its stronger side), each in words: a roof over a hop
    the re-check can't judge (:func:`unjudged`) may clip it, so with them
    such a hop leaves a plan unverified too (AZ-407)."""
    return [f"{pack} {name} {v:g}" for pack, values in sorted(sliders.items())
            for name, v in sorted(values.items()) if _taller(pack, name, v)]


@dataclass(frozen=True)
class SafeRange:
    """A slider's logic-safe range in its own units, with the vanilla
    value: ``lo``/``hi`` None where the search found no end, and what the
    first value past each end breaks; ``unjudged``: the playthrough's hops
    the re-check can't judge (:func:`unjudged`), which leave any weaker
    value of a modelled slider (AZ-384), or one that raises the jump's arc
    (AZ-407), unverified (:meth:`unverified`)."""
    pack: str
    slider: str
    vanilla: float
    lo: float | None
    hi: float | None
    below: str | None = None
    above: str | None = None
    unjudged: tuple[str, ...] = ()

    def unverified(self, value: float) -> str | None:
        """Why ``value`` leaves the logic unverified short of breaking a
        certificate: weaker than vanilla, or raising the jump's arc, over a
        hop the re-check can't judge."""
        if not self.unjudged:
            return None
        more = f" and {len(self.unjudged) - 1} more" if len(self.unjudged) > 1 else ""
        if _weaker(self.pack, self.slider, value):
            return f"a hop the re-check can't judge ({self.unjudged[0]}{more}; AZ-384)"
        if _taller(self.pack, self.slider, value):
            return (f"a hop the re-check can't judge, where a roof may clip the taller arc "
                    f"({self.unjudged[0]}{more}; AZ-407)")
        return None

    def breaks(self, value: float) -> str | None:
        """What ``value`` breaks (None inside the range)."""
        if self.lo is not None and value < self.lo - 1e-9:
            return self.below
        if self.hi is not None and value > self.hi + 1e-9:
            return self.above
        return None


def _kept(c: Certificate, env, margin, tier: str, contact) -> bool:
    """keeps() of ``c`` under the seeded ``env``, a measured flight's own range where it decides; a failure only
    once the exact search (:class:`~.physics.Envelope`'s ``exact``) confirms it: the seeded one is a local search
    from vanilla's flap ticks, which a taller jump can trap far below the optimum (AZ-367).  A build's
    :func:`recheck` reads it for its own tier's logic (AZ-369)."""
    v = verdict((contact or {}).get(c), env.m, tier)
    if v is not None:
        return v
    return keeps(c, env, margin) or keeps(c, envelope(env.m, env.beam, exact=True), margin)


DEFAULT_SEED = "2"      # the goldens' seed (D185; scripts/restack.py moves it): the ranges are for it
KEEP = 4                 # the newest cached range sets kept


__all__ = ["DEFAULT_SEED", "MODELLED", "Recheck", "SafeRange", "changed", "describe", "logic_for", "logic_of",
           "measured", "recheck", "required", "roll_proofs", "rolling_skips", "run_floor", "taller", "unjudged",
           "verdict", "weaker"]
