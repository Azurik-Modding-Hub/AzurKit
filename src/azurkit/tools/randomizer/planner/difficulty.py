"""Seed difficulty (D1031, D1037, D1038, D1039): what a level asks of a seed, and how much of it a plan needs.

A *rating* is one scale for movement tiers and skips: 1 Safe, 2 Standard, 3 Hard, 4 Frame-perfect. The *rung* E_r of
settings S is S with everything rated r and above taken away (:func:`rung`). *need_r*: the plan can't be won at E_r, so
a trick rated r or above is needed. *play_r* (:func:`play`): from nothing collected, E_r's reaches to their fixpoint,
then one round of S, again, to the win: its S rounds are the *step-ups*, the fewest any play needs (the skips and the
tier are monotone, D113), and the progression collected between them the *stages*; a stage is a trick-free stretch.

A level's target is one of two promises (:class:`Ask`):

- **throughout**: need_L, at least 2 step-ups at Standard or above, and no stretch over half the progression;
- **once**: need_L alone.

Which one a level asks comes from a shipped rate table, ``data/forcing.json``, written by ``scripts/seed_forcing.py``
from a campaign of this algorithm over seeds "0".."29" at every Movement x Skips cell: :func:`asked`, one rule for every
cell, reads the first of L throughout, L once, then the level below likewise, whose table rate reaches
:data:`RATE_LINE`; none: the level is greyed. Frame-perfect has nothing forceable yet, so its table rate sends it to
Hard, on its own digest. Hence no level is a special case here: a route mark that lets Frame-perfect be forced lifts it
through the table's re-run alone (and bumps ``SEED_DIFFICULTY_FILL``).

:class:`Shape` is what the fill reads: the ladder its pin reads and the acceptance, lazily (:meth:`Shape.why_not`: one
reach, then play_2 stopped at the first stage over half; :meth:`Shape.score` only when the bound ends with no ok).
:func:`profile` is the same measure for the tracker and the spoiler, a pure function of the plan and the database.
Everything is integer counts and rationals from the solver's victory, no clock, so a plan is the same on every host.
"""

from __future__ import annotations

import functools
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from fractions import Fraction
from pathlib import Path

from azurkit.core import progress
from azurkit.tools.randomizer.movement import played
from azurkit.tools.randomizer.planner.settings import (
    MOVEMENT_TIERS,
    RATING_NAMES,
    SEED_DIFFICULTIES,
    Settings,
    picks_on,
    picks,
    registry_tag,
    top_rating,
    turnable,
)
from azurkit.tools.randomizer.planner.solver import Logic, Reach

BOUND = 6                     # the passing candidates a shaped fill tries before it keeps the closest
RATE_LINE = Fraction(1, 2)    # a promise the table meets on under this share of seeds isn't asked
SAY_LINE = Fraction(9, 10)    # one met under this says "about N seeds in 10"
FORCE_LINE = Fraction(1, 3)   # a toggle mix whose picks open under this share of seeds treats the level as under RATE_LINE
FORCING = Path(__file__).resolve().parent.parent / "data" / "forcing.json"
FORCING_FORMAT = "azurkit-seed-forcing/1"
MOVEMENT = "(movement)"       # an opener that is the tier, not a pick
NOTE = "shaping the seed"     # the acceptance's notes: each a cancel point
KEY_CATEGORIES = ("fragments", "powers")   # the categories that hold a needed item the fill moves (keys never move)
ANY_LINE = "Items go wherever the logic allows, as before. A seed may need none of the tricks you allowed."
STANDARD_LINE = ("Tricks all through the first half of the game and past it: you can't win without your tricks, at "
                 "least two separate points need one, and no stretch of more than half the progression comes without "
                 "one. About three quarters of the progression lies past a trick; the last part of the game stays "
                 "open (no trick can gate it yet).")
STANDARD_HARD = "With Hard tricks allowed, they are usually needed too: to keep them out, set Movement and Skips to Standard."
HARD_LINE = ("Standard's promise, and at least one of those points needs a Hard trick (a Hard skip, or Hard movement). "
             "Few Hard tricks can gate key items yet, so the Hard part is often the same one.")
ONCE_NO_SKIP = ("With no skip on, movement can be made needed at one point (around the middle of the game). Turn on "
                "skips for tricks throughout.")
ONCE_POWERS = ("Keeping the powers vanilla leaves too few key items to place for tricks throughout: a trick is needed "
               "at one point.")
ONCE_OTHER = "These settings leave too few tricks to place for tricks throughout: a trick is needed at one point."
GREY_NO_ITEMS = "Randomize the key items to give Seed difficulty something to move."
GREY_NO_SKIP = ("Turn on skips to give Seed difficulty tricks to place: movement alone makes a seed need a Standard "
                "move once at most, in under half the seeds.")
NOTHING = "nothing to shape at these settings"
CLOSEST = "the closest the fill found"
SOME_ON = f" With only some of the skips at that rating on, fewer seeds may meet it; the others get {CLOSEST}."


@dataclass(frozen=True)
class Ask:
    """What a level asks at some settings: ``rating`` throughout, or only ``once``; ``rate``, the table's share of
    seeds that meet it."""
    rating: int
    once: bool
    rate: Fraction


@functools.cache
def forcing() -> dict:
    """The shipped rate table (``scripts/seed_forcing.py``)."""
    return json.loads(FORCING.read_text(encoding="utf-8"))


def skips_tag(skips: Mapping[str, Mapping]) -> str:
    """What the table was measured on, beside the database's digest: the skips' registry."""
    return registry_tag(picks(skips)).hex()


def cell_key(tier: str, ceiling: int) -> str:
    return f"{tier}/{ceiling}"


def _rated(ids: Sequence[str], skips: Mapping[str, Mapping]) -> int:
    return max(skips[sid].get("difficulty", 0) for sid in ids)


def _cell(settings: Settings, skips: Mapping[str, Mapping]) -> tuple[Mapping | None, dict[str, list[str]]]:
    """``settings``' row of the table, by their tier and the highest rating among the skips they turn on (a skip's
    toggle counts, D258), and those picks."""
    on = picks_on(settings, skips)
    return forcing()["cells"].get(cell_key(settings.movement_tier, max((_rated(ids, skips) for ids in on.values()),
                                                                       default=0))), on


def no_key_items(settings: Settings) -> bool:
    """Both categories that hold needed items kept vanilla: nothing to move."""
    return set(KEY_CATEGORIES) <= settings.exclude_categories


def _rate(settings: Settings, row: Mapping, rating: int, kind: str) -> Fraction:
    """The table's rate of a promise: the cell's, or a kept category's when lower."""
    table = forcing()
    counts = row.get(str(rating))
    if counts is None:
        return Fraction(0)
    rate = Fraction(counts[kind], table["seeds"])
    for category in KEY_CATEGORIES:
        if category in settings.exclude_categories and (kept := table["kept"][category].get(str(rating))):
            rate = min(rate, Fraction(kept[kind], table["seeds"]))
    return rate


def _forced(settings: Settings, row: Mapping, on: Mapping[str, list[str]], rating: int,
            skips: Mapping[str, Mapping]) -> bool:
    """Whether a toggle mix leaves enough to force ``rating``: the seeds the table has a pick still on at it, or the
    tier when it is rated that high, open a step-up, a share reaching :data:`FORCE_LINE` (many picks co-open a few
    seeds' rounds, so seeds, not a sum of each pick's share). No toggle: the cell's rates alone."""
    if not settings.skip_override:
        return True
    openers = row.get("openers", {}).get(str(rating), {})
    seeds = {seed for pid, ids in on.items() if _rated(ids, skips) >= rating for seed in openers.get(pid, ())}
    if MOVEMENT_TIERS.index(settings.movement_tier) + 1 >= rating:
        seeds.update(openers.get(MOVEMENT, ()))
    return Fraction(len(seeds), forcing()["seeds"]) >= FORCE_LINE


def asked(settings: Settings, skips: Mapping[str, Mapping]) -> Ask | None:
    """What ``settings``' level asks (the module docstring), from the table alone, no reach; ``None``: no level, or
    nothing to shape (no key item to move, or no promise reaches :data:`RATE_LINE`): then the seed plans with today's
    draws, on its own streams."""
    level = settings.seed_difficulty
    if not level or no_key_items(settings):
        return None
    row, on = _cell(settings, skips)
    if row is None:
        return None
    for rating in range(level, 1, -1):
        if _forced(settings, row, on, rating, skips):
            for once, kind in ((False, "throughout"), (True, "once")):
                if (rate := _rate(settings, row, rating, kind)) >= RATE_LINE:
                    return Ask(rating, once, rate)
    return None


def _say(rate: Fraction) -> str:
    return (f" About {rate.numerator * 10 // rate.denominator} seeds in 10 meet it; the others get {CLOSEST}."
            if rate < SAY_LINE else "")


def _some_on(settings: Settings, skips: Mapping[str, Mapping]) -> bool:
    """A toggle mix that leaves off a skip rated no higher than its highest on (a skip group's tick, D1061, is one): the
    table's rates are its cell's, with all of them on, and 8 seeds at a tick of Roll jumps met 2 to 4 where the cell
    says all (met-rates-after-tick.jsonl, Step 4.3rv-rando), so the line gives no number."""
    on = picks_on(settings, skips)
    if not on or not settings.skip_override:
        return False
    top = max(_rated(ids, skips) for ids in on.values())
    return any(pid not in on and any(turnable(skips[sid]) for sid in ids)
               and _rated([sid for sid in ids if turnable(skips[sid])], skips) <= top for pid, ids in picks(skips).items())


def _line(settings: Settings, skips: Mapping[str, Mapping], ask: Ask) -> str:
    """The line under the select for a level that asks ``ask``."""
    level, top = settings.seed_difficulty, top_rating(settings, skips)
    say = SOME_ON if _some_on(settings, skips) else _say(ask.rate)
    if ask.once:
        on = picks_on(settings, skips)
        once = ONCE_POWERS if "powers" in settings.exclude_categories else ONCE_NO_SKIP if not on else ONCE_OTHER
        text = once + say
    elif ask.rating == 2:
        text = STANDARD_LINE + (f" {STANDARD_HARD}" if top >= 3 else "") + say
    else:
        text = HARD_LINE + say
    if level == ask.rating:
        return text
    if level == 4 and ask.rating == 3:
        some = _cell(settings, skips)[0].get("4", {}).get("once") and not settings.exclude_categories & set(KEY_CATEGORIES)
        return ("Frame-perfect tricks can't be made needed yet: this level plays as Hard"
                + (" (a few seeds need one anyway)." if some else ".") + (f" {text}" if ask.once else ""))
    return (f"{RATING_NAMES[level]} tricks can't often be made needed at these settings: this level plays as "
            f"{RATING_NAMES[ask.rating]}. {text}")


def levels(settings: Settings, skips: Mapping[str, Mapping]) -> dict:
    """The Randomizer tab's ``difficulty``, from the table alone (no reach): ``levels``, each level's ``[value, name,
    enabled, line]``; ``note``, what a loaded level that greys at these settings plans as (a level above the settings'
    top can't be loaded: the file and the string are refused by name). Under moved sliders the seed is shaped at the
    played tier (:func:`.movement.played`, D1066): a level is enabled only where both tiers enable it; a level the asked
    settings grey keeps their line, every other takes the played tier's, and the note is the played tier's."""
    now = played(settings)
    out = _levels(now, skips)
    if now is not settings:
        out = [mine if not mine[2] else level for level, mine in zip(out, _levels(settings, skips))]
    grey = now.seed_difficulty and asked(now, skips) is None
    return {"levels": out, "note": f"Seed difficulty {RATING_NAMES[now.seed_difficulty]}: {NOTHING}" if grey else None}


def _levels(settings: Settings, skips: Mapping[str, Mapping]) -> list[list]:
    top = top_rating(settings, skips)
    out: list[list] = [[0, "Any", True, ANY_LINE]]
    for level in SEED_DIFFICULTIES[1:]:
        name, st = RATING_NAMES[level], replace(settings, seed_difficulty=level)
        if level > top:
            out.append([level, name, False, f"Movement and Skips allow {RATING_NAMES[top]} tricks at most: raise one "
                                            f"of them to pick {name}."])
        elif no_key_items(st):
            out.append([level, name, False, GREY_NO_ITEMS])
        elif (ask := asked(st, skips)) is None:
            out.append([level, name, False, GREY_NO_SKIP if not picks_on(st, skips) else
                        f"These skips can't often make {name} tricks needed: turn more of them on."])
        else:
            out.append([level, name, True, _line(st, skips, ask)])
    return out


def rung(settings: Settings, rating: int, skips: Mapping[str, Mapping]) -> Settings:
    """E_r: ``settings`` with everything rated ``rating`` and above taken away: the movement tier rated at most r - 1,
    the highest of the ceilings below r, and each pick they toggle on whose in-logic variants are all rated r or above
    off. A batch whose variants straddle r stays on, so E_r is never smaller than the exact rung and "not won at E_r"
    still proves a trick rated r or above is needed."""
    tier = MOVEMENT_TIERS[min(MOVEMENT_TIERS.index(settings.movement_tier), rating - 2)]
    ceiling = max(c for c in SEED_DIFFICULTIES if c < rating and c <= settings.skip_ceiling)
    on = picks_on(settings, skips)
    off = {pid: False for pid, value in settings.skip_override.items()
           if value and pid in on and min(skips[sid].get("difficulty", 0) for sid in on[pid]) >= rating}
    return Settings(ceiling, tier, {**settings.skip_override, **off})


def progression(logic: Logic, placement: Mapping[str, str]) -> frozenset[str]:
    """The locations holding a progression item, the placement over vanilla (71 in all, wherever they lie)."""
    cls = {it["name"]: it["class"] for it in logic.db.items["item"]}
    item = {**{loc: v[0] for loc, v in logic.vanilla.items()}, **placement}
    return frozenset(loc for loc, x in item.items() if x is not None and cls.get(x) == "progression")


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

    @property
    def free(self) -> int:
        """The longest trick-free stretch, a count."""
        return max(self.stages)

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


class Shape:
    """A level > 0's parameters for one fill: the plan's ``logic``, its settings, what they ask (:func:`asked`; a fill
    runs the shape only when that isn't ``None``) and the rungs the pin reads, E_L .. E_2, the asked rating's first.
    ``kernel``: the fill's compiled need and play (its ``need`` and ``play`` answer as :func:`need` and :func:`play`,
    or :data:`TWIN`), else these run."""

    def __init__(self, logic: Logic, settings: Settings, ask: Ask) -> None:
        self.logic, self.settings, self.ask = logic, settings, ask
        skips = logic.skip_tables
        self.ladder = tuple(rung(settings, r, skips) for r in range(ask.rating, 1, -1))
        self.limit = len(progression(logic, {})) // 2
        self.kernel = None

    def _need(self, placement: Mapping[str, str], rating: int) -> bool:
        if self.kernel is not None and (got := self.kernel.need(placement, rating)) is not TWIN:
            return got
        return need(self.logic, self.settings, placement, rating)

    def _play(self, placement: Mapping[str, str], rating: int, stop: int | None = None) -> Play | None:
        if self.kernel is not None and (got := self.kernel.play(placement, rating, stop)) is not TWIN:
            return got
        return play(self.logic, self.settings, placement, rating, stop=stop, needed=True)

    def why_not(self, placement: Mapping[str, str]) -> str | None:
        """Whether a passing candidate meets the promise (``None``) or why not, lazily: need_L, one reach, then play_2
        stopped at the first stage over half. It never reads play_r for r >= 3, so the plan kept is the one computing
        every score at once would keep."""
        name = RATING_NAMES[self.ask.rating]
        if not self._need(placement, self.ask.rating):
            return f"no {name} trick is needed; {name} asks for one"
        if self.ask.once:
            return None
        got = self._play(placement, 2, self.limit)
        if got is None:
            return f"a trick-free stretch runs past half the progression; {name} asks for at most half"
        if got.step_ups < 2:
            return f"tricks are needed at {got.step_ups} point; {name} asks for 2"
        return None

    def score(self, placement: Mapping[str, str]) -> tuple:
        """The candidate's score (integers, lexicographic), read only when the bound ends with no ok: the need, then
        the step-ups at the asked rating up to 2, those at Standard up to 2, the longest stretch, shorter first."""
        rating = self.ask.rating
        if not self._need(placement, rating):
            return (0,)
        if self.ask.once:
            return (1, min(self._play(placement, rating).step_ups, 2))
        low = self._play(placement, 2)
        own = () if rating == 2 else (min(self._play(placement, rating).step_ups, 2),)
        return (1, *own, min(low.step_ups, 2), -low.free)


def _third(place: int, total: int) -> str:
    return "early" if place * 3 < total else "late" if place * 3 >= total * 2 else "middle"


def _points(n: int) -> str:
    return f"{n} point{'' if n == 1 else 's'}"


def profile(logic: Logic, settings: Settings, placement: Mapping[str, str]) -> dict | None:
    """How much of a plan its level asks for and it has (level 0: ``None``), a pure function of the plan and the
    database: ``level``; ``asks``, the rating asked (0: nothing to shape); ``once``; ``plays``, for each rating from 2
    to the asked one, its need, step-ups' places and thirds, the longest stretch and the share past a trick, counts of
    ``total``; ``parts``, the promise's parts, each ``{"got", "asked", "met"}``; ``met``, all of them."""
    level = settings.seed_difficulty
    if not level:
        return None
    ask = asked(settings, logic.skip_tables)
    if ask is None:
        return {"level": level, "asks": 0, "once": False, "met": False, "plays": {}, "parts": {}, "total": 0}
    total = len(progression(logic, placement))
    plays = {}
    for rating in range(2, ask.rating + 1):
        p = play(logic, settings, placement, rating)
        plays[rating] = {"need": p.need, "places": p.places(), "stages": list(p.stages), "free": p.free,
                         "past": total - p.stages[0] if p.need else 0,
                         "thirds": [_third(x, total) for x in p.places()]}
    parts = {"need": {"got": plays[ask.rating]["need"], "asked": True, "met": plays[ask.rating]["need"]}}
    if not ask.once:
        low, limit = plays[2], total // 2
        parts["points"] = {"got": len(low["places"]), "asked": 2, "met": len(low["places"]) >= 2}
        parts["stretch"] = {"got": low["free"], "asked": limit, "met": low["free"] <= limit}
    out = {"level": level, "asks": ask.rating, "once": ask.once, "total": total, "plays": plays, "parts": parts,
           "met": all(part["met"] for part in parts.values())}
    if level > ask.rating:
        out["level_need"] = need(logic, settings, placement, level)
    return out


def _percent(n: int, total: int) -> int:
    return n * 100 // total if total else 0


def _heading(prof: Mapping) -> str:
    name = RATING_NAMES[prof["level"]]
    return name if not prof["asks"] or prof["asks"] == prof["level"] else f"{name}, plays as {RATING_NAMES[prof['asks']]}"


def requires(prof: Mapping, *, spoiler: bool = False, openers: Sequence | None = None) -> dict:
    """The tracker's ``head.requires`` of a :func:`profile`: ratings and counts, no location, realm or skip by name;
    with ``spoiler``, each step-up's third and its ``openers``. ``text`` is the line under the head."""
    out = {"level": prof["level"], "asks": prof["asks"], "once": prof["once"], "met": prof["met"],
           "parts": prof["parts"]}
    if not prof["asks"]:
        return out | {"text": f"{_heading(prof)}: {NOTHING}"}
    plays, parts, total = prof["plays"], prof["parts"], prof["total"]
    low, top, name = plays[2], plays[prof["asks"]], RATING_NAMES[prof["asks"]]
    bits = [f"{_heading(prof)}: {'met' if prof['met'] else CLOSEST}"]
    n = len(top["places"])
    if prof["asks"] > 2 or not parts["need"]["met"] or prof["once"]:
        bits.append(f"no {name} trick is needed" if not n else
                    f"a {name} trick is needed " + ("once" if n == 1 else f"at {_points(n)}"))
    if not prof["once"]:
        count = len(low["places"])
        bits.append(f"tricks are needed at {_points(count)}" + ("" if parts["points"]["met"] else " (2 asked)")
                    + (": " + ", ".join(low["thirds"]) if spoiler and count else ""))
        if parts["stretch"]["met"]:
            bits.append(f"about {_percent(low['past'], total)} % of the progression lies past a trick")
        else:
            bits.append(f"the longest trick-free stretch is {_percent(low['free'], total)} % of the progression "
                        "(50 % asked)")
        if "late" not in low["thirds"]:
            bits.append("the late game is open")
    elif spoiler and top["thirds"]:
        bits.append(", ".join(top["thirds"]))
    if spoiler:
        out["thirds"] = low["thirds"]
        if openers:
            out["openers"] = list(openers)
            bits.append("; ".join(_opener_text(o) for o in openers))
    return out | {"text": " · ".join(bits)}


def _opener_text(opener: Mapping) -> str:
    named = ", ".join(opener["picks"])
    return f"one of {named}" if opener["one_of"] else named


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


def spoiler_lines(prof: Mapping, opened: Sequence[Mapping], traps: Sequence[str]) -> list[str]:
    """The spoiler's lines (a plan's :func:`profile`, :func:`openers` and the places a skip can strand you)."""
    head = f"seed difficulty: {_heading(prof)} ({prof['level']})"
    if not prof["asks"]:
        return [f"{head}: {NOTHING}"]
    low, total = prof["plays"][2], prof["total"]
    parts = prof["parts"]
    text = "met" if prof["met"] else f"{CLOSEST}: " + "; ".join(
        ([f"no {RATING_NAMES[prof['asks']]} trick is needed"] if not parts["need"]["met"] else [])
        + ([f"tricks are needed at {_points(parts['points']['got'])} (2 asked)"]
           if "points" in parts and not parts["points"]["met"] else [])
        + ([f"the longest trick-free stretch is {_percent(parts['stretch']['got'], total)} % of the progression "
            "(50 % asked)"] if "stretch" in parts and not parts["stretch"]["met"] else []))
    if prof["level"] > prof["asks"]:
        name = RATING_NAMES[prof["level"]]
        head += f": {name} tricks can't be made needed yet; {name} needed: {'yes' if prof['level_need'] else 'no'}"
    lines = [f"{head}: {text}"]
    for i, (place, opener) in enumerate(zip(low["places"], opened), 1):
        lines.append(f"step-up {i} at {_percent(place, total)} %"
                     f"{' of the progression' if i == 1 else ''}: {_opener_text(opener)}")
    if low["need"]:
        at = low["stages"].index(low["free"])
        start = sum(low["stages"][:at])
        ends = "the end" if at == len(low["stages"]) - 1 else f"{_percent(start + low['free'], total)} %"
        lines.append(f"the longest trick-free stretch: {_percent(low['free'], total)} % (from "
                     f"{_percent(start, total)} % to {ends}); {_percent(low['past'], total)} % of the progression "
                     "past a trick")
    lines.append(f"places a skip can strand you (a dead end you can't leave yet): {len(traps)}"
                 + (f" ({', '.join(traps)})" if traps else ""))
    return lines
