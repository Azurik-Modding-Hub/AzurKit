"""Seed difficulty (D1157, amending D1031, D1037, D1039): where the fill leans key items, and a plan's measured line.

Four levels, each offered at any settings: Normal (0, today's seeds: the fill enters none of this), Easy (1), Hard (2)
and Expert (3). Three integer measures, each from the solver and the database (no clock, so a plan is the same on every
host):

- **chain**: the round of the progression reach that collects a spot, dense-ranked (1 = the first round that collects
  anything); a plan's *key-item steps* (:func:`chain`), the spheres of its playthrough that collect a progression item.
- **hard spots**: how many rungs E_top .. E_2 of the settings' ladder (:func:`ladder`; top, the highest rating they
  allow, :func:`~.settings.top_rating`) miss a spot at that point of the fill: a spot behind an allowed trick is a hard
  one, so tricks follow from placement, with no forcing of their own. A plan's tricks are play_2's step-ups. With no
  trick allowed (top 1) nothing rates plain platforming, so the levels differ by chain and off the path alone.
- **off the path** (:func:`detours`): a spot's detour on its level's node graph, the fewest hops in and back out over a
  shortest way through (side rooms, dead ends and far ends score, a spot passed anyway doesn't); :data:`OFF_PATH` or
  more is off the path, and a plan's *off* count is the key items the fill put there.

The fill (``fill._Lean``, ``native/fill.c``'s lean) draws each key item's spot among those its rules allow by
w = 4 * missed + round + min(detour, :data:`DETOUR_CAP`): Easy among the lowest (missed, round + detour), Hard weighted
w * w + 1, Expert among the highest w; the obsidians by detour alone (D1038's lean of optional rewards). Easy keeps the
lowest :meth:`Judge.score` of :data:`BOUNDS` passing attempts, Expert the highest, the first on a tie; Hard and Normal
keep the first. Every attempt passes the fill's verify, so every seed stays beatable within its settings.

A *rating* is one scale for movement tiers and skips: 1 Safe, 2 Standard, 3 Hard, 4 Frame-perfect. The *rung* E_r of
settings S is S with everything rated r and above taken away (:func:`rung`). *need_r*: the plan can't be won at E_r.
*play_r* (:func:`play`): from nothing collected, E_r's reaches to their fixpoint, then one round of S, again, to the
win: its S rounds are the *step-ups* (the fewest any play needs: the skips and the tier are monotone, D113), each the
point a trick rated r or above is needed. :func:`profile` measures a plan for the spoiler and the tracker: the numbers
the fill aimed for.
"""

from __future__ import annotations

import collections
import weakref
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from azurkit.core import progress
from azurkit.tools.randomizer.planner.settings import (
    MOVEMENT_TIERS,
    RATING_NAMES,
    SEED_DIFFICULTIES,
    SEED_DIFFICULTY_NAMES,
    Settings,
    picks_on,
    skips_on,
    top_rating,
)
from azurkit.tools.randomizer.planner.solver import Logic, Reach

BOUNDS = (1, 3, 1, 6)         # each level's passing attempts the fill keeps the best of: Normal, Easy, Hard, Expert
STRICT, LEANED = 10, 20       # attempt k leans strictly below STRICT, weighted below LEANED, then draws as today
LOW, WEIGHTED, HIGH, LOW_WEIGHTED = 1, 2, 3, 4   # an attempt's lean (:func:`lean_mode`); 0 none
OFF_PATH = 2                  # a detour this long or longer is off the path (a room in and one back, at least)
DETOUR_CAP = 6                # the lean reads a detour up to this
MOVEMENT = "(movement)"       # an opener that is the tier, not a pick
NOTE = "shaping the seed"     # the acceptance's notes: each a cancel point
#: A trick family's player name (a skip's first ``tricks`` entry), as the line names what a seed needed
TRICK_NAMES = {"rjump": "Roll jumps", "pstorage": "Power storage", "bskip": "Barrier skips", "flutter": "Air flutter",
               "elevjump": "Elevator jumps", "elevbounce": "Elevator bounces", "nolight": "Dark rooms",
               "itrig": "Trigger skips", "tjump": "Turn jumps", "iceclimb": "Ice climbs", "botstep": "Bot steps",
               "flipcancel": "Flip cancels", "ledgepop": "Ledge pops", "saveanywhere": "Save anywhere"}
#: Each level's line under the Randomizer tab's select, easiest first
LINES = {"Easy": "Key items early in the game and close to the way through, with no trick where one can be avoided.",
         "Normal": "Items go wherever the logic allows, as before.",
         "Hard": "Key items lean to later finds, side rooms and dead ends, and spots behind your tricks.",
         "Expert": "Key items as deep in the chain, as far off the way through and as far behind your hardest tricks "
                   "as the fill can put them."}


def lean_mode(level: int, k: int) -> int:
    """Attempt ``k``'s lean at ``level``: Easy's lowest and Expert's highest (:data:`LOW`, :data:`HIGH`) below
    :data:`STRICT`, then weighted toward the low or high end (:data:`LOW_WEIGHTED`, :data:`WEIGHTED`; Hard's from the
    first), and today's draw (0) from :data:`LEANED` on, the fill's last :data:`~.fill.MAX_ATTEMPTS` of a level. A
    strict lean makes much the same placement every attempt, so one the verify refuses would be refused 20 times
    over: the later attempts lean less, then not at all, so a level plans wherever today's fill does. With the
    elemental powers kept vanilla, Easy's attempts pass by the trap gate's repair past a kept way out
    (``fill._Slots.repairs``' ``past``)."""
    if not level or k >= LEANED:
        return 0
    if level == 2:
        return WEIGHTED
    if k < STRICT:
        return LOW if level == 1 else HIGH
    return LOW_WEIGHTED if level == 1 else WEIGHTED


def tricks_allowed(settings: Settings, skips: Mapping[str, Mapping]) -> bool:
    """Whether ``settings`` allow a trick: a rating over Safe (a movement tier over Safe, or a skip on)."""
    return top_rating(settings, skips) >= 2


def levels() -> dict:
    """The Randomizer tab's ``difficulty``: ``levels``, each level's ``[value, name, enabled, line]`` (every one
    offered at any settings, easiest first; a value is the name a settings table holds), and no ``note``."""
    return {"levels": [[name, name, True, LINES[name]] for name in ("Easy", "Normal", "Hard", "Expert")], "note": None}


def _rated(ids: Sequence[str], skips: Mapping[str, Mapping]) -> int:
    return max(skips[sid].get("difficulty", 0) for sid in ids)


def rung(settings: Settings, rating: int, skips: Mapping[str, Mapping]) -> Settings:
    """E_r: ``settings`` with everything rated ``rating`` and above taken away: the movement tier rated at most r - 1,
    the highest of the ceilings below r, and each pick they toggle on whose in-logic variants are all rated r or above
    off. A batch whose variants straddle r stays on, so E_r is never smaller than the exact rung and "not won at E_r"
    still proves a trick rated r or above is needed."""
    tier = MOVEMENT_TIERS[min(MOVEMENT_TIERS.index(settings.movement_tier), rating - 2)]
    ceiling = max(c for c in (0, 2, 3, 4) if c < rating and c <= settings.skip_ceiling)
    on = picks_on(settings, skips)
    off = {pid: False for pid, value in settings.skip_override.items()
           if value and pid in on and min(skips[sid].get("difficulty", 0) for sid in on[pid]) >= rating}
    return Settings(ceiling, tier, {**settings.skip_override, **off}, save_warp=settings.save_warp)


def ladder(settings: Settings, skips: Mapping[str, Mapping]) -> tuple[Settings, ...]:
    """The rungs the lean reads, E_top .. E_2 (none when the settings allow no trick)."""
    return tuple(rung(settings, r, skips) for r in range(top_rating(settings, skips), 1, -1))


_DETOURS: list = [None]   # the last detours: (a weak ref to the Logic, to its database, the options' key, them)


def detours(logic: Logic, settings: Settings) -> dict[str, int]:
    """Each pool location's detour, its node's: on its level's directed node graph (each authored walk, cart and
    teleport edge rated at most the settings' tier, and the edges of the skips they turn on inside one level, every
    requirement held), the fewest of hops(t1 -> node) + hops(node -> t2) - hops(t1 -> t2) over its entries t1 (the
    nodes an exit from another level arrives at, the world's start and hub) and exits t2 (the nodes an exit leaves
    from, the start and hub), t1 = t2 counting 0 hops: 0 on a shortest way through, twice its depth for a side room or
    a dead end; 0 where none is found. Worked out once for the last Logic, database and options."""
    db, skips = logic.db, logic.skip_tables
    key = (settings.movement_tier, tuple(skips_on(settings, skips)))
    if (kept := _DETOURS[0]) is not None and kept[0]() is logic and kept[1]() is db and kept[2] == key:
        return kept[3]
    level_of = {n["id"]: lvl for lvl in sorted(db.levels) for n in db.levels[lvl].get("node", ())}
    tier = MOVEMENT_TIERS.index(settings.movement_tier) + 1
    fwd, back = collections.defaultdict(set), collections.defaultdict(set)
    arrive, depart = collections.defaultdict(set), collections.defaultdict(set)
    for lvl in sorted(db.levels):
        for e in db.levels[lvl].get("edge", ()):
            a, b = e["from"], e["to"]
            if e.get("difficulty", 1) > tier:
                continue
            if e.get("kind") == "exit" or level_of.get(a) != level_of.get(b):
                if a in level_of:
                    depart[level_of[a]].add(a)
                if b in level_of:
                    arrive[level_of[b]].add(b)
                continue
            fwd[a].add(b)
            back[b].add(a)
    for sid in key[1]:
        a, b = skips[sid].get("from"), skips[sid].get("to")
        if a in level_of and level_of[a] == level_of.get(b):
            fwd[a].add(b)
            back[b].add(a)
    for special in (db.world["start"], db.world["hub"]):
        if special in level_of:
            arrive[level_of[special]].add(special)
            depart[level_of[special]].add(special)
    nodes_of = collections.defaultdict(set)
    for n, lvl in level_of.items():
        nodes_of[lvl].add(n)
    found: dict[str, int | None] = {}
    for lvl in sorted(nodes_of):
        nodes = nodes_of[lvl]
        ins, outs = sorted(arrive[lvl] & nodes), sorted(depart[lvl] & nodes)
        into = {t: _hops(t, fwd, nodes) for t in ins}
        out_of = {t: _hops(t, back, nodes) for t in outs}
        for v in nodes:
            best = None
            for t1 in ins:
                if v not in into[t1]:
                    continue
                for t2 in outs:
                    base = 0 if t1 == t2 else into[t1].get(t2)
                    if v in out_of[t2] and base is not None:
                        c = into[t1][v] + out_of[t2][v] - base
                        best = c if best is None else min(best, c)
            found[v] = best
    out = {}
    for loc in logic.pool:
        n = db.node_of[loc]
        out[loc] = (found[n] if n in found else found.get(logic.canon(n))) or 0
    _DETOURS[0] = (weakref.ref(logic), weakref.ref(db), key, out)
    return out


def _hops(src: str, graph: Mapping[str, set], nodes: set) -> dict[str, int]:
    """The fewest hops from ``src`` to each node of ``nodes`` it reaches over ``graph``."""
    d, frontier = {src: 0}, [src]
    while frontier:
        nxt = []
        for v in frontier:
            for w in sorted(graph[v]):
                if w in nodes and w not in d:
                    d[w] = d[v] + 1
                    nxt.append(w)
        frontier = nxt
    return d


def progression(logic: Logic, placement: Mapping[str, str]) -> frozenset[str]:
    """The locations holding a progression item, the placement over vanilla (71 in all, wherever they lie)."""
    cls = {it["name"]: it["class"] for it in logic.db.items["item"]}
    item = {**{loc: v[0] for loc, v in logic.vanilla.items()}, **placement}
    return frozenset(loc for loc, x in item.items() if x is not None and cls.get(x) == "progression")


def chain(logic: Logic, settings: Settings, placement: Mapping[str, str]) -> int:
    """A plan's key-item steps: the spheres of its playthrough (the reach under ``settings`` from nothing) that collect
    a progression item the placement names (the spoiler's "sphere N: k progression" with k at least 1)."""
    cls = {it["name"]: it["class"] for it in logic.db.items["item"]}
    trace: list = []
    logic.reach(settings, placement, trace=trace, traps=False)
    return sum(any(cls.get(placement.get(loc)) == "progression" for loc in sp.locations) for sp in trace)


def off_path(logic: Logic, placement: Mapping[str, str], spots: frozenset[str], detour: Mapping[str, int]) -> int:
    """A plan's key items off the path: the fill's key-item ``spots`` holding a progression item, :data:`OFF_PATH` or
    more off it."""
    cls = {it["name"]: it["class"] for it in logic.db.items["item"]}
    return sum(cls.get(placement.get(loc)) == "progression" and detour[loc] >= OFF_PATH for loc in spots)


@dataclass(frozen=True)
class Play:
    """play_r: ``stages``, the progression collected between step-ups, one more than the step-ups; ``rounds``, each
    step-up's (what it held before it, the progression it gained). No need: one stage, no round."""
    need: bool
    stages: tuple[int, ...]
    rounds: tuple[tuple[frozenset[str], frozenset[str]], ...]

    @property
    def step_ups(self) -> int:
        return len(self.stages) - 1

    def places(self) -> list[int]:
        """Each step-up's place: the progression collected before it."""
        return [sum(self.stages[:i + 1]) for i in range(self.step_ups)]


def need(logic: Logic, settings: Settings, placement: Mapping[str, str], rating: int) -> bool:
    """need_r: one reach."""
    e = rung(settings, rating, logic.skip_tables)
    return not logic.reach(e, placement, traps=False).victory


def play(logic: Logic, settings: Settings, placement: Mapping[str, str], rating: int, *, stop: int | None = None,
         needed: bool = False) -> Play | None:
    """play_r (the module docstring). ``needed``: need_r is known true (a reach saved). ``stop``: ``None`` as soon as a
    stage passes it."""
    if not needed and not need(logic, settings, placement, rating):
        return Play(False, (len(progression(logic, placement)),), ())
    e = rung(settings, rating, logic.skip_tables)
    low, prog = logic, progression(logic, placement)
    got, stages, rounds, cur = frozenset(), [], [], 0
    while True:
        while True:
            progress.note(NOTE)
            r = low.reach(e, placement, collected=got, traps=False, replay=True)
            new = r.locations - got
            if r.victory or not new:
                break
            cur += len(new & prog)
            got |= new
            if stop is not None and cur > stop:
                return None
        if r.victory:
            break
        progress.note(NOTE)
        r = logic.reach(settings, placement, collected=got, traps=False, replay=True)
        new = r.locations - got
        if not new and not r.victory:
            raise ValueError("the plan's play is stuck under its own settings")
        stages.append(cur)
        rounds.append((got, new & prog))
        cur = len(new & prog)
        got |= new
        if stop is not None and cur > stop:
            return None
        if not new:
            break
    stages.append(cur)
    return Play(True, tuple(stages), tuple(rounds))


TWIN = object()   # what a kernel answers when it can't: these reaches run


class Judge:
    """A level's plan score in one fill (:meth:`score`): the plan's ``logic``, its settings, the fill's key-item
    ``spots`` and their ``detour``; ``kernel``: the fill's compiled need and play (each answering as :func:`need` and
    :func:`play`, or :data:`TWIN`), else these run."""

    def __init__(self, logic: Logic, settings: Settings, spots: frozenset[str], detour: Mapping[str, int]) -> None:
        self.logic, self.settings, self.spots, self.detour = logic, settings, spots, detour
        self.top = top_rating(settings, logic.skip_tables)
        self.kernel = None

    def _need(self, placement: Mapping[str, str], rating: int) -> bool:
        if self.kernel is not None and (got := self.kernel.need(placement, rating)) is not TWIN:
            return got
        return need(self.logic, self.settings, placement, rating)

    def _play(self, placement: Mapping[str, str], rating: int) -> Play:
        if self.kernel is not None and (got := self.kernel.play(placement, rating, None)) is not TWIN:
            return got
        return play(self.logic, self.settings, placement, rating, needed=True)

    def step_ups(self, placement: Mapping[str, str], rating: int) -> int:
        """play_r's step-ups (0 when need_r doesn't hold)."""
        return self._play(placement, rating).step_ups if self._need(placement, rating) else 0

    def score(self, placement: Mapping[str, str]) -> int:
        """The candidate's score: its key-item steps, its key items off the path and twice its step-ups at each rating
        from 2 to the settings' top."""
        progress.note(NOTE)
        return (chain(self.logic, self.settings, placement) + off_path(self.logic, placement, self.spots, self.detour)
                + 2 * sum(self.step_ups(placement, r) for r in range(2, self.top + 1)))


def profile(logic: Logic, settings: Settings, placement: Mapping[str, str]) -> dict:
    """A plan's measures (any level), a pure function of the plan and the database: ``level``; ``steps``, its key-item
    steps; ``off``, its key items off the path; ``top``, the highest rating its settings allow; ``points``, play_2's
    step-ups, and ``places``, each one's place in ``total`` progression (none when no trick is allowed)."""
    from azurkit.tools.randomizer.planner.fill import key_spots

    top = top_rating(settings, logic.skip_tables)
    low = play(logic, settings, placement, 2) if top >= 2 else None
    return {"level": settings.seed_difficulty, "steps": chain(logic, settings, placement),
            "off": off_path(logic, placement, key_spots(logic, settings), detours(logic, settings)), "top": top,
            "points": low.step_ups if low else 0, "places": low.places() if low else [],
            "total": len(progression(logic, placement))}


def _times(n: int) -> str:
    return "once" if n == 1 else "twice" if n == 2 else f"{n} times"


def _listed(words: Sequence[str]) -> str:
    return words[0] if len(words) == 1 else f"{', '.join(words[:-1])} and {words[-1]}"


def needs(logic: Logic, settings: Settings, opened: Sequence[Mapping]) -> list[list[str]]:
    """Each step-up's openers (:func:`openers`) in short words, each once: a pick's trick family's player name
    (:data:`TRICK_NAMES`), ``<Tier> movement`` for the tier, "one of A or B" for an irreducible set."""
    skips, tier = logic.skip_tables, RATING_NAMES[MOVEMENT_TIERS.index(settings.movement_tier) + 1]

    def short(pick: str) -> str:
        if pick == MOVEMENT:
            return f"{tier} movement"
        pid = pick.rsplit(" (", 1)[0]
        ids = picks_on(settings, skips).get(pid) or [pid]
        family = (skips.get(ids[0], {}).get("tricks") or [pid])[0]
        return TRICK_NAMES.get(family, family)

    out = []
    for opener in opened:
        names = list(dict.fromkeys(map(short, opener["picks"])))
        out.append([f"one of {' or '.join(names)}"] if opener["one_of"] and len(names) > 1 else names)
    return out


def line(prof: Mapping, needed: Sequence[Sequence[str]] | None = None) -> str:
    """The measured line: ``<Level>: <S> key-item steps, <O> off the path[, <tricks>]``; the tricks part left out when
    no trick is allowed, "no trick needed" with no step-up, "needs " each trick named and how often with ``needed``
    (:func:`needs`, the spoiler shown), else "needs tricks at N points"."""
    text = f"{SEED_DIFFICULTY_NAMES[prof['level']]}: {prof['steps']} key-item steps, {prof['off']} off the path"
    if prof["top"] < 2:
        return text
    if not prof["points"]:
        return f"{text}, no trick needed"
    if needed is None:
        return f"{text}, needs tricks at {prof['points']} point{'' if prof['points'] == 1 else 's'}"
    counts = collections.Counter(n for each in needed for n in each)
    return f"{text}, needs {_listed([f'{n} {_times(k)}' for n, k in counts.items()])}"


def head(prof: Mapping, needed: Sequence[Sequence[str]] | None = None) -> dict:
    """The tracker's ``head.difficulty`` of a :func:`profile`: its level's name, the counts, ``needs`` (each step-up's
    tricks, :func:`needs`) only with the spoiler shown, and ``text``, the line under the head."""
    out = {"level": SEED_DIFFICULTY_NAMES[prof["level"]], "steps": prof["steps"], "off": prof["off"],
           "points": prof["points"]}
    return out | ({"needs": [list(n) for n in needed]} if needed is not None else {}) | {"text": line(prof, needed)}


def openers(logic: Logic, settings: Settings, placement: Mapping[str, str], rating: int = 2) -> list[dict]:
    """Each of play_r's step-ups' openers, as ``{"picks": [...], "one_of": bool}``, a pick with its rating: the picks
    rated >= r whose removal from the settings loses some of that round's new progression, ``(movement)`` when only
    the tier does, and "one of" an irreducible set when neither does: picks, and ``(movement)`` when all of them off
    still open the round, so that the set only loses it with the tier lowered too. Each removal is a reach on the
    settings' switchable option set (``Logic.reach``'s ``off``), one compile a tier for every mix, kept for the next plan
    at these settings; another settings' or another database's openers drop them. The last plan's answer is kept with
    them: the spoiler's View takes an app's job ahead's."""
    mine = (settings.skip_ceiling, settings.movement_tier, tuple(sorted(settings.skip_override.items())))
    held = getattr(logic, "_opener_sets", None)
    if held is not None and (held[0] != mine or held[4] is not logic.db):
        for key in held[1]:
            logic._compiled.pop(key, None)
        for key in held[2]:
            logic._native.pop(key, None)
        held = None
    asked_of = rating, tuple(sorted(placement.items()))
    if held is not None and held[3][0] == asked_of:
        return held[3][1]
    before = set(logic._compiled), set(logic._native)
    answer = held[3] if held else (None, None)
    try:
        answer = asked_of, _worked_out(logic, settings, placement, rating)
        return answer[1]
    finally:
        logic._opener_sets = (mine, (held[1] if held else set()) | (set(logic._compiled) - before[0]),
                              (held[2] if held else set()) | (set(logic._native) - before[1]), answer, logic.db)


def _worked_out(logic: Logic, settings: Settings, placement: Mapping[str, str], rating: int) -> list[dict]:
    skips = logic.skip_tables
    on = picks_on(settings, skips)
    hi = sorted(pid for pid, ids in on.items() if _rated(ids, skips) >= rating)
    made = play(logic, settings, placement, rating)
    lowered = replace(settings, movement_tier=rung(settings, rating, skips).movement_tier)

    told, whole = [0], len(made.rounds) * (len(hi) + 1)    # a round's picks and its one try without them or the tier

    def reached(off: Sequence[str], got: frozenset[str], low: bool = False) -> Reach:
        """The reach with the picks ``off`` turned off, the tier lowered when ``low``."""
        told[0] = min(told[0] + 1, whole)
        progress.note(f"reading what opens each step, {told[0]} of {whole}")
        return logic.reach(lowered if low else settings, placement, collected=got, traps=False, replay=True,
                           off=frozenset(sid for p in off for sid in on[p]))

    def named(pid: str) -> str:
        return f"{pid} ({RATING_NAMES[_rated(on[pid], skips)]})"

    out = []
    for got, gain in made.rounds:
        lost = [p for p in hi if gain - reached((p,), got).locations]
        if lost:
            out.append({"picks": [named(p) for p in lost], "one_of": False})
            continue
        if gain - reached((), got, True).locations:
            out.append({"picks": [MOVEMENT], "one_of": False})
            continue
        some = list(hi)     # no single one: put each back that the rest lose it without
        by_tier = not gain - reached(hi, got).locations    # every pick off still opens it: the tier is a way too
        for p in hi:
            rest = [q for q in some if q != p]
            if gain - reached(rest, got, by_tier).locations:
                some = rest
        out.append({"picks": [named(p) for p in some] + [MOVEMENT] * by_tier, "one_of": True})
    return out


def _percent(n: int, total: int) -> int:
    return n * 100 // total if total else 0


def _opener_text(opener: Mapping) -> str:
    named = ", ".join(opener["picks"])
    return f"one of {named}" if opener["one_of"] else named


def spoiler_lines(prof: Mapping, opened: Sequence[Mapping], needed: Sequence[Sequence[str]]) -> list[str]:
    """The spoiler's lines of a plan's :func:`profile`: "seed difficulty: " its line with each trick named, then a line
    a step-up (its place and its :func:`openers`)."""
    lines = [f"seed difficulty: {line(prof, needed)}"]
    for i, (place, opener) in enumerate(zip(prof["places"], opened), 1):
        lines.append(f"step-up {i} at {_percent(place, prof['total'])} %"
                     f"{' of the progression' if i == 1 else ''}: {_opener_text(opener)}")
    return lines


assert len(BOUNDS) == len(SEED_DIFFICULTIES)
