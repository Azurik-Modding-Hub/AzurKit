"""The item tracker as a page asks for it (Step 4.2c2, D189, D249): Modkit's
:class:`~.tracker.Tracker` (installed by the oracle sync) on a plan, the
spots the player marked collected (by hand, or by Live in the app) and
what the solver says is reachable now, as JSON.

:func:`view` is stateless for its caller: it takes the plan file's object,
the marks as the page keeps them (Modkit's state file's, :func:`.tracker.marks`)
and, with Live on, the element levels the game holds, and gives back the
marks (after a ``toggle`` or a ``reset``), the counter row, each spot's
state on the maps, the levels reached now and the Table tab's two trees. A
spot's item is given only once it is collected or with ``spoiler``: the
page shows nothing the Spoiler hides. The trackers it builds (about 1.5 s
each, the logic under the plan's movement sliders first) are kept for the
process, the last :data:`KEEP` plans, so a click costs one reach.

A spot's ``state``: ``got`` (collected by hand), ``live`` (marked by Live),
``near`` (reachable now), ``skip`` (reachable now only with a skip on,
R1.41) or ``far`` (not yet).
"""

from __future__ import annotations

import json
from collections import OrderedDict
from collections.abc import Mapping

from azurkit.tools.randomizer.movement import logic_of
from azurkit.tools.randomizer.planner.loader import kept_logic
from azurkit.tools.randomizer.planner.plan import PlanError, load_plan
from azurkit.tools.randomizer.planner.settings import CATEGORIES, picks_on
from azurkit.tools.randomizer.tracker import ELEMENTS, Row, Tracker, held_counts, marks

KEEP = 3                     # the plans whose trackers the process keeps
GIVEN = ("plan", "marks", "kit", "held", "spoiler", "toggle", "reset")
RATINGS = ("None", "Safe", "Standard", "Hard", "Frame-perfect")   # the skip ceiling's names (Modkit's head line)
_KEPT: OrderedDict[str, Tracker] = OrderedDict()
_LOGIC: dict[str, object] = {}   # a build's plan sha256 -> the logic it was planned on (:func:`prime`)


def prime(doc: Mapping, logic) -> None:
    """Keep the logic a build planned ``doc`` on, so its tracker opens without re-checking it."""
    _LOGIC[doc["sha256"]] = logic
    while len(_LOGIC) > KEEP:
        _LOGIC.pop(next(iter(_LOGIC)))


def _tracker(doc: Mapping) -> Tracker:
    """The tracker of the plan file's object ``doc`` (``ValueError`` naming
    a plan this database can't read), kept for the process."""
    if not isinstance(doc, Mapping) or not isinstance(doc.get("sha256"), str):
        raise ValueError("tracker: plan is a plan file's object")
    key = doc["sha256"]
    if key in _KEPT and _KEPT[key].doc == doc:   # the plan it was built on, not one edited since
        _KEPT.move_to_end(key)
        return _KEPT[key]
    base = kept_logic()
    try:
        plan = load_plan(doc, base.db)
    except PlanError as exc:
        raise ValueError(f"tracker: {exc}") from None
    logic = _LOGIC.get(key) or logic_of(base, plan.settings)
    _KEPT[key] = made = Tracker(logic, plan.settings, plan.placement)
    made.doc = plan.doc
    while len(_KEPT) > KEEP:
        _KEPT.popitem(last=False)
    return made


def _marks(given: object) -> dict:
    """The page's marks, checked: Modkit's state (``collected``, ``live``,
    ``veto``, ``slot``), or a bare list of spots; ``ValueError`` otherwise."""
    if given is None:
        return marks({})
    if isinstance(given, list):
        given = {"collected": given}
    if not isinstance(given, Mapping) or not set(given) <= {"collected", "live", "veto", "slot"}:
        raise ValueError("tracker: marks is {collected, live, veto, slot}")
    out = marks(given)
    clocks = out["live"].values()
    if not (all(isinstance(x, str) for x in out["collected"] + out["veto"] + list(out["live"]))
            and all(x is None or (isinstance(x, (int, float)) and not isinstance(x, bool)) for x in clocks)
            and (out["slot"] is None or isinstance(out["slot"], str))):
        raise ValueError("tracker: marks names spots by their ids, live with a day clock or null")
    return out


def _kit(given: object) -> dict[str, int]:
    if given is None:
        return {}
    if not (isinstance(given, Mapping) and set(given) <= set(ELEMENTS)
            and all(type(n) is int and n >= 0 for n in given.values())):
        raise ValueError(f"tracker: kit is {{element: level}} of {', '.join(ELEMENTS[:4])}")
    return dict(given)


def _row(row: Row) -> dict:
    return {"key": row.key, "label": row.label, "got": row.got, "now": row.now, "left": row.left,
            "total": row.total, "where": row.where, "game": row.game, "children": [_row(c) for c in row.children]}


def head(t: Tracker) -> dict:
    """The tracker's head line (Modkit's): the seed, its share string, the skip ceiling, the movement tier,
    the fire dark areas need, the categories kept vanilla and each skip on (a batch once, D275)."""
    st, doc = t.settings, t.doc
    on = [pid if ids == [pid] else f"{pid} ({', '.join(ids)})" for pid, ids in picks_on(st, t.logic.skip_tables).items()]
    kept = [c for c in CATEGORIES if c in st.exclude_categories]
    return {"seed": doc["seed"], "share": doc["share"], "sha256": doc["sha256"],
            "text": (f"Seed {doc['seed']} · {doc['share']} · skips {RATINGS[st.skip_ceiling]}, movement "
                     f"{st.movement_tier.replace('_', '-')}, Fire {st.dark_fire}"
                     + (f", vanilla {' '.join(kept)}" if kept else "") + f" · {len(on)} skips on"),
            "skips": on}


def view(given: Mapping) -> dict:
    """What the tracker shows for ``given``: ``plan`` (a plan file's
    object), ``marks`` (as :func:`.tracker.marks` reads them; none: no
    mark), ``kit`` (Live's element levels, ``{element: level}``; none: the
    marks' alone), ``held`` (Live's inventory, for the Table's In game
    column), ``spoiler``, and ``toggle`` (a spot to mark or unmark: a live
    mark taken off is vetoed, so Live doesn't mark it again) or ``reset``
    (no mark and no veto). ``ValueError`` names what it refuses."""
    if not isinstance(given, Mapping):
        raise ValueError(f"tracker: a JSON object, not {type(given).__name__}")
    if unknown := sorted(set(given) - set(GIVEN), key=str):
        raise ValueError(f"tracker: no key {', '.join(map(repr, unknown))} (its keys: {', '.join(GIVEN)})")
    t = _tracker(given.get("plan"))
    m, spoiler = _marks(given.get("marks")), bool(given.get("spoiler"))
    held = given.get("held") or {}
    if not (isinstance(held, Mapping) and all(type(v) is int for v in held.values())):
        raise ValueError("tracker: held is the game's inventory, {field: count}")
    collected, live, veto = set(m["collected"]) & t.spots, m["live"], set(m["veto"]) & t.spots
    if (collected, {k: v for k, v in live.items() if k in collected}, veto, m["slot"]) != (
            t.collected, t.live, t.veto, t.slot):
        t.collected, t.veto, t.slot = collected, veto, m["slot"]
        t.live = {loc: c for loc, c in live.items() if loc in collected}
        t.update()
    t.set_kit(_kit(given.get("kit")))
    if given.get("reset"):
        t.reset()
    elif (loc := given.get("toggle")) is not None:
        if loc not in t.spots:
            raise ValueError(f"tracker: {loc!r} is no spot the tracker marks")
        t.toggle(loc)
    s = t.status
    spots = {}
    for loc in sorted(t.spots):
        got, near = loc in t.collected, loc in t.reachable
        state = ("live" if t.is_live(loc) else "got") if got else ("skip" if loc not in t.plain else "near") \
            if near else "far"
        spots[loc] = {"level": t.logic.pool[loc], "class": t.spot_class[loc], "state": state,
                      "item": t.item(loc) if got or spoiler else None}
    items, levels = t.table(spoiler, held_counts(held) if held else None)
    return {"head": head(t), "marks": t.state(),
            "status": {"collected": s.collected, "reachable": s.reachable, "total": s.total, "sphere": s.sphere,
                       "victory": s.victory, "levels": list(s.levels), "skipped": s.skipped},
            "spots": spots, "table": {"items": [_row(r) for r in items], "levels": [_row(r) for r in levels]}}


def digest(out: Mapping) -> str:
    """A view's verdicts as one canonical JSON text (the tests' and the evidence's), the head aside."""
    return json.dumps({k: v for k, v in out.items() if k != "head"}, sort_keys=True, separators=(",", ":"))
