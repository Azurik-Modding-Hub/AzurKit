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
R1.41) or ``far`` (not yet); ``vanilla`` names the item the base game puts
there, which tells the spot without telling what the seed put there.

With ``gems`` (Step R1.43, D928: off by default), each gem spot's gems
(a cluster's yield), how many Live saw taken and the plan's gem there (a
gem spot holds only gems and no requirement reads one, so its colour shows
without Spoiler), each level's taken and in all, and the Table's Gems rows.
Live alone takes a gem (the marks' ``gems``: each spot's takes, a day clock
each); no gem moves the reach or the spots' counts.

The maps (Step 4.2c3) draw from the player's image (:mod:`.art`, the
host's to keep); :func:`world` gives what they draw from the database:
the grid, each level's exits, barriers and features with what they need
(:mod:`.needs`), and :data:`ART_PARTS`, the parts a host draws them in.
"""

from __future__ import annotations

import functools
import json
import re
from collections import OrderedDict
from collections.abc import Mapping, Sequence

from azurkit.tools.randomizer import needs
from azurkit.tools.randomizer.movement import logic_of
from azurkit.tools.randomizer.planner.loader import kept_logic
from azurkit.tools.randomizer.planner.plan import PlanError, load_plan
from azurkit.tools.randomizer.planner.settings import CATEGORIES, picks_on
from azurkit.tools.randomizer.tracker import ELEMENTS, Row, Tracker, held_counts, marks

KEEP = 3                     # the plans whose trackers the process keeps
GIVEN = ("plan", "marks", "kit", "held", "spoiler", "gems", "toggle", "reset")
RATINGS = ("None", "Safe", "Standard", "Hard", "Frame-perfect")   # the skip ceiling's names (Modkit's head line)
#: The world map's grid (Modkit's ``render_level_maps.GRID``): each level's (column, row), neighbours where the
#: game links them; training_room, never part of a seed, has none (D194).
GRID = {"airship": (0, 0), "a3": (1, 0), "a5": (2, 0), "a6": (3, 0), "a1": (4, 0), "e6": (5, 0),
        "w3": (0, 1), "w1": (1, 1), "town": (2, 1), "life": (3, 1), "e2": (4, 1), "e7": (5, 1),
        "w4": (0, 2), "w2": (1, 2), "d1": (2, 2), "f1": (3, 2), "e5": (4, 2), "f2": (5, 2),
        "f3": (1, 3), "d2": (2, 3), "f6": (3, 3), "f4": (4, 3)}
SPOT = {"major": "Item spot", "obsidian": "Obsidian spot", "consumable": "Fuel or health spot"}
#: The pictures a host draws from the player's image (:mod:`.art`), one call each: the item icons, then each level of
#: the world map (whose main floors' thumbnails make the world map); ``ART_VERSION`` names how they are drawn, a
#: host's key for what it keeps (``tests/test_art.py`` holds it to the drawing's source: a sync that changes how
#: they are drawn changes it).
ART_PARTS = ("icons", *GRID)
ART_VERSION = "1-ee4cdff271e9"
_KEPT: OrderedDict[str, Tracker] = OrderedDict()
_LOGIC: dict[str, object] = {}   # a build's plan sha256 -> the logic it was planned on (:func:`prime`)


def prime(doc: Mapping, logic) -> None:
    """Keep the logic a build planned ``doc`` on, so its tracker opens without re-checking it."""
    _LOGIC[doc["sha256"]] = logic
    while len(_LOGIC) > KEEP:
        _LOGIC.pop(next(iter(_LOGIC)))


def item_name(item: str) -> str:
    """An item as the tracker names it (Modkit's): ``frag_air_1`` "Air disc fragment 1", ``power_water`` "Water
    power", ``key_life1`` "Key: life1", ``all_fuel`` "All fuel"."""
    if m := re.fullmatch(r"frag_([a-z]+)_(\d)", item):
        return f"{m[1].capitalize()} disc fragment {m[2]}"
    if item.startswith("key_"):
        return f"Key: {item[4:]}"
    if not item.startswith("power_"):     # an obsidian, a gem, fuel or health
        return item.replace("_", " ").capitalize()
    word = re.sub(r"(\D)(\d)", r"\1 \2", item.removeprefix("power_").split("_a3")[0])
    return f"{word.capitalize()} power"


def icon(item: str) -> str:
    """An item's icon on the page (Modkit's ``item_icon`` names, the page's own drawings, never the game's): a
    fragment or a power by its element (``frag_air``, ``power_water``), the other powers by their own, any key
    ``key``, ``obsidian``, ``fuel``, ``health`` or a gem's (``gem_ruby``)."""
    if m := re.fullmatch(r"frag_([a-z]+)_\d", item):
        return f"frag_{m[1]}"
    if item.startswith("key_"):
        return "key"
    return {"all_fuel": "fuel", "all_health": "health", "power_water_a3": "power_water"}.get(
        item, f"gem_{item}" if item in ("diamond", "emerald", "ruby", "sapphire") else item)


@functools.cache
def world() -> dict:
    """The world map's levels (:data:`GRID`), where each one's exits lead (the vanilla data's live exits, in
    order, each level once) and what the maps draw over their pictures (``maps``: :func:`.needs.overlays`):
    the same for every plan, as exits stay vanilla in v1 (:func:`view` adds ``art``: the pictures' parts and
    version, :data:`ART_PARTS`)."""
    db = kept_logic().db
    exits = {lv: list(dict.fromkeys(e["dest_level"] for e in db.generated[lv]["exits"]
                                    if e["kind"] == "exit" and e["live"] and e["dest_level"] in GRID
                                    and e["dest_level"] != lv)) for lv in GRID if lv in db.generated}
    return {"grid": {lv: list(at) for lv, at in GRID.items()}, "exits": exits, "maps": needs.overlays(tuple(GRID))}


def tracker_of(doc: Mapping) -> Tracker:
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


def marks_of(given: object) -> dict:
    """The page's marks, checked: Modkit's state (``collected``, ``live``,
    ``veto``, ``slot``), or a bare list of spots; ``ValueError`` otherwise."""
    if given is None:
        return marks({})
    if isinstance(given, list):
        given = {"collected": given}
    if not isinstance(given, Mapping) or not set(given) <= {"collected", "live", "veto", "slot", "gems"}:
        raise ValueError("tracker: marks is {collected, live, veto, slot, gems}")
    out = marks(given)
    clocks = [*out["live"].values(), *(c for cs in out["gems"].values() if isinstance(cs, list) for c in cs)]
    if not (all(isinstance(x, str) for x in out["collected"] + out["veto"] + list(out["live"]) + list(out["gems"]))
            and all(isinstance(cs, list) for cs in out["gems"].values())
            and all(x is None or (isinstance(x, (int, float)) and not isinstance(x, bool)) for x in clocks)
            and (out["slot"] is None or isinstance(out["slot"], str))):
        raise ValueError("tracker: marks names spots by their ids, live with a day clock or null, gems with a "
                         "list of them")
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


def view(given: Mapping, events: Sequence = ()) -> dict:
    """What the tracker shows for ``given``: ``plan`` (a plan file's
    object), ``marks`` (as :func:`.tracker.marks` reads them; none: no
    mark), ``kit`` (Live's element levels, ``{element: level}``; none: the
    marks' alone), ``held`` (Live's inventory, for the Table's In game
    column), ``spoiler``, and ``toggle`` (a spot to mark or unmark: a live
    mark taken off is vetoed, so Live doesn't mark it again) or ``reset``
    (no mark and no veto); ``events``, Live's (the app's feed:
    :mod:`.live.game`'s Took, Level, Held and Reload), are merged into the
    marks first (``Tracker.apply``: a hand mark never dropped, a veto never
    marked). ``ValueError`` names what it refuses."""
    if not isinstance(given, Mapping):
        raise ValueError(f"tracker: a JSON object, not {type(given).__name__}")
    if unknown := sorted(set(given) - set(GIVEN), key=str):
        raise ValueError(f"tracker: no key {', '.join(map(repr, unknown))} (its keys: {', '.join(GIVEN)})")
    t = tracker_of(given.get("plan"))
    m, spoiler = marks_of(given.get("marks")), bool(given.get("spoiler"))
    held = given.get("held") or {}
    if not (isinstance(held, Mapping) and all(type(v) is int for v in held.values())):
        raise ValueError("tracker: held is the game's inventory, {field: count}")
    collected, live, veto = set(m["collected"]) & t.spots, m["live"], set(m["veto"]) & t.spots
    gems = {loc: list(c)[:t.gem_full[loc]] for loc, c in m["gems"].items() if loc in t.gem_full and c}
    if (collected, {k: v for k, v in live.items() if k in collected}, veto, m["slot"]) != (
            t.collected, t.live, t.veto, t.slot):
        t.collected, t.veto, t.slot = collected, veto, m["slot"]
        t.live = {loc: c for loc, c in live.items() if loc in collected}
        t.update()
    t.gems = gems
    t.set_kit(_kit(given.get("kit")))
    if events:
        t.apply(events)
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
        item = t.item(loc) if got or spoiler else None
        spots[loc] = {"level": t.logic.pool[loc], "class": t.spot_class[loc], "state": state, "item": item,
                      "name": item_name(item) if item else SPOT[t.spot_class[loc]], "icon": icon(item) if item else None,
                      "vanilla": item_name(t.logic.vanilla[loc][0])}
    shown = bool(given.get("gems"))
    items, levels = t.table(spoiler, held_counts(held) if held else None, gems=shown)
    out = {"head": head(t), "world": world() | {"art": {"version": ART_VERSION, "parts": list(ART_PARTS)}},
           "marks": t.state(),
           "status": {"collected": s.collected, "reachable": s.reachable, "total": s.total, "sphere": s.sphere,
                      "victory": s.victory, "levels": list(s.levels), "skipped": s.skipped},
           "spots": spots, "table": {"items": [_row(r) for r in items], "levels": [_row(r) for r in levels]}}
    if shown:
        out["gems"] = {"spots": {loc: {"level": t.logic.pool[loc], "full": full, "taken": t.gems_taken(loc),
                                       "item": t.item(loc)} for loc, full in sorted(t.gem_full.items())},
                       "counts": {lv: list(n) for lv, n in t.gem_counts().items()}}
    return out


def digest(out: Mapping) -> str:
    """A view's verdicts as one canonical JSON text (the tests' and the evidence's): the marks, the counter row,
    each spot's level, class, state and item, the Table and, with ``gems``, the gems'."""
    spots = {loc: {k: s[k] for k in ("level", "class", "state", "item")} for loc, s in out["spots"].items()}
    return json.dumps({"marks": out["marks"], "status": out["status"], "spots": spots, "table": out["table"]}
                      | ({"gems": out["gems"]} if "gems" in out else {}), sort_keys=True, separators=(",", ":"))
