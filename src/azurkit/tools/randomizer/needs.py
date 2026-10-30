"""What the tracker's maps say each way needs (Step 4.2c3): Modkit's map
view's needs (``gui/rando_view.py``: ``reaching``, ``exit_edges``,
``need_kind``, ``say`` and the colours), on the randomizer's database under
the default options. Plan-free: exits, barriers and the features a player
steers by stay vanilla in v1, so :func:`overlays` is the same for every
seed and computed once a process (about 4 s, the solver's ``within`` for
each exit's switch).

A level map's exit is a ring in the colour of what using it needs
(:func:`need_kind`, :data:`NEEDS`: one colour a key, disc fragments, an
event, a power, the powers of a barrier type's spell, else several),
dashed when the logic can't come back that way (:func:`one_way`); the
world map draws a line for each pair of levels an exit joins, coloured the
same. Each barrier, key lock, disc seal, save point and teleporter pad is
named with what it needs on hover. Names and requirements only: where each
lies is the drawn map's (``maps.json``, from the player's image).
"""

from __future__ import annotations

import collections
import functools
import re

from azurkit.tools.randomizer.planner.grammar import ParseError, atoms, parse
from azurkit.tools.randomizer.planner.loader import kept_logic
from azurkit.tools.randomizer.planner.settings import skips_on

# What a connection needs, one colour each (Modkit's ``NEEDS``, M9)
NEEDS = {"nothing": "#c9d1d9", "keys": "#ffe8a3", "fragments": "#b98cff", "event": "#ff8fb1",
         "air": "#bdeeff", "water": "#3d8bff", "fire": "#ff6a3d", "earth": "#5cbf4a", "ice block": "#8fa8bf",
         "acid block": "#b5e853", "smash wall": "#c08050", "crystal": "#4fd1c5", "powers": "#e05cff",
         "unreachable": "#6e7681"}
# The barrier type each spell breaks in the vanilla data (AZ-462)
BREAKS = {frozenset(("fire", "water")): "ice block", frozenset(("earth", "water")): "acid block",
          frozenset(("air", "earth", "fire")): "smash wall", frozenset(("air", "fire", "water")): "crystal",
          frozenset(("air", "earth")): "crystal", frozenset(("earth", "fire")): "crystal"}
# A key's colour: the red, green and blue keys' own, the others' one of these by their place among them
KEY_COLOURS = {"red": "#ff5c5c", "green": "#7ee07e", "blue": "#6f9cff"}
KEY_SHADES = ("#f2b134", "#e0c56e", "#f6d58e", "#d98f4e", "#b8915a", "#ffd24d", "#cd7f32", "#a67c2e", "#d4b483",
              "#9e7b4f", "#c9a227", "#8c6d1f", "#e6a157")
ELEMENT = {"a": "air", "w": "water", "f": "fire", "e": "earth", "l": "life"}
# A feature a player steers by (maps.json's "features"): its letter, colour and name
FEATURES = {"save": ("S", "#4fc3f7", "Save point"), "keylock": ("K", "#f2b134", "Key lock"),
            "seal": ("D", "#b98cff", "Disc seal"), "teleport": ("T", "#7ee07e", "Teleporter pad")}
BARRIER_ICONS = {"firewall": "fire_barrier", "iceblock": "ice_block", "acidblock": "acid_block",
                 "smashwall": "smash_wall", "crystal": "crystal"}
BARRIER_NAMES = {"firewall": "Fire barrier", "iceblock": "Ice block", "acidblock": "Acid block",
                 "crystal": "Earth crystal (tree-song switch)", "smashwall": "Smash wall"}


@functools.cache
def thresholds() -> dict[str, frozenset[int]]:
    """Each counter the default options' logic reads, with the thresholds it compares it with."""
    return kept_logic().reads(kept_logic().db.defaults)


def _spare(names: list, ok) -> list:
    """Those of ``names`` ``ok`` still accepts with none of them spare."""
    kept = list(names)

    def drop(group):
        nonlocal kept
        if ok(trial := [x for x in kept if x not in group]):
            kept = trial
        elif len(group) > 1:
            drop(group[:len(group) // 2])
            drop(group[len(group) // 2:])

    drop(list(names))
    return kept


def reaching(level: str, sources: list[str], node: str) -> str | None:
    """What reaching ``node`` from ``sources`` (nodes of ``level``) needs
    without leaving it, under the default options: each way's counters at
    the least threshold the logic reads and the other levels' flags it
    can't spare, the ways or-ed (AZ-432); None when nothing reaches it."""
    lg = kept_logic()
    levels = {c: sorted(ns) for c, ns in thresholds().items()}
    outside = sorted(f for f in lg.db.flags if not f.startswith(f"{level}."))

    def ok(counters, flags):
        return node in lg.within(level, sources, counters, flags)

    def under(caps: dict, c: str, n: int | None = None) -> int:
        cap = caps.get(c, levels[c][-1]) if n is None else min(caps.get(c, n - 1), n - 1)
        return max((t for t in levels[c] if t <= cap), default=0)

    def way(caps: dict) -> dict | None:
        most = {c: n for c in levels if (n := under(caps, c))}
        if not ok(most, outside):
            return None
        held = {c: most[c] for c in _spare(sorted(most), lambda keep: ok({c: most[c] for c in keep}, outside))}
        for c in held:
            held[c] = next(n for n in levels[c] if ok({**held, c: n}, outside))
        return held

    def within_caps(w: dict, caps: dict) -> bool:
        return all(n <= caps.get(c, n) for c, n in w.items())

    first = way({})
    if first is None:
        return None
    ways, dead, seen = [first], [], set()
    todo = [{c: under({}, c, n)} for c, n in first.items()]
    while todo:
        caps = todo.pop(0)
        key = frozenset(caps.items())
        if key in seen or any(within_caps(caps, d) and d.keys() <= caps.keys() for d in dead):
            continue
        seen.add(key)
        held = next((w for w in ways if within_caps(w, caps)), None) or way(caps)
        if held is None:
            dead.append(caps)
            continue
        if held not in ways:
            ways.append(held)
        todo += [{**caps, c: under(caps, c, n)} for c, n in held.items()]
    said = []
    for held in ways:
        flags = _spare(outside, lambda keep, held=held: ok(held, keep))
        said.append(" & ".join([f"{c}>={n}" for c, n in sorted(held.items())] + [f"flag:{f}" for f in flags])
                    or "true")
    if "true" in said:
        return "true"
    return " | ".join(f"({s})" if "&" in s and len(said) > 1 else s for s in said)


@functools.cache
def arrivals() -> dict[str, list[tuple[str, str]]]:
    """Each level's arrivals: (the level an edge from another level comes from, the node it lands on), and
    ("", the world's start) on the start's level."""
    db = kept_logic().db
    level_of = {n: lvl for n, (lvl, _) in db.nodes.items()}
    out = collections.defaultdict(list)
    for lvl, doc in sorted(db.levels.items()):
        for e in doc["edge"]:
            if e.get("from") and e.get("to") and "disc" not in e and level_of[e["to"]] != lvl:
                out[level_of[e["to"]]].append((lvl, e["to"]))
    out[level_of[db.world["start"]]].append(("", db.world["start"]))
    return out


@functools.cache
def exit_edges() -> tuple:
    """(from level, to level, exit id, need) of each exit edge the randomizer's level files name: its own
    requirement and, on an authored level, what reaching its switch needs (AZ-341)."""
    lg = kept_logic()
    db = lg.db
    level_of = {n: lvl for n, (lvl, _) in db.nodes.items()}
    on = set(skips_on(db.defaults, lg.skip_tables))
    out = []
    for lvl, doc in sorted(db.levels.items()):
        for e in doc["edge"]:
            if not e.get("from") or e["kind"] != "exit" and not e.get("exit"):
                continue
            dest, need = level_of.get(e["to"]), _skips_off(e.get("requires", "true"), on)
            if lvl not in db.stubs:
                there = [n for src, n in arrivals()[lvl] if src != dest]
                path = (there and reaching(lvl, there, e["from"])) or reaching(
                    lvl, [n for _, n in arrivals()[lvl]], e["from"]) or "false"
                need = _and(path, need)
            out.append((lvl, dest, e.get("exit", ""), need))
    return tuple(out)


def _skips_off(req: str, on: set[str]) -> str:
    """``req``'s alternatives without those naming a skip ``on`` lacks outside a parenthesis."""
    parts, depth, start = [], 0, 0
    for i, ch in enumerate(req + "|"):
        depth += (ch == "(") - (ch == ")")
        if ch == "|" and depth == 0:
            parts.append(req[start:i].strip())
            start = i + 1
    kept = [p for p in parts if "(" in p or all(s in on for s in re.findall(r"skip:([\w.]+)", p))]
    return req if len(kept) == len(parts) else " | ".join(kept) or "false"


def _or_outside(req: str) -> bool:
    depth = 0
    for ch in req:
        depth += (ch == "(") - (ch == ")")
        if ch == "|" and depth == 0:
            return True
    return False


def _and(*reqs: str) -> str:
    """The requirements and-ed, "true" dropped, a disjunction bracketed and, for plain conjunctions, a counter
    named twice kept at its higher threshold."""
    if any(ch in r for r in reqs for ch in "|()"):
        parts = [r.strip() for r in reqs if r.strip() != "true"]
        return " & ".join(f"({r})" if len(parts) > 1 and _or_outside(r) else r for r in parts) or "true"
    terms: dict[str, tuple[int, str]] = {}
    for t in (t.strip() for r in reqs for t in r.split("&")):
        m = re.fullmatch(r"([\w.]+)>=(\d+)", t)
        key, n = (m[1], int(m[2])) if m else (t, 0)
        if t != "true" and n >= terms.get(key, (-1, ""))[0]:
            terms[key] = n, t
    return " & ".join(t for _, t in terms.values()) or "true"


def _least(reqs: list[str]) -> str:
    return min(reqs, key=lambda r: (r.strip() != "true", len(r))) if reqs else "true"


def needs(level: str, dest: str) -> str:
    """What going from ``level`` to ``dest`` needs: the least need of an exit edge between the two."""
    return _least([r for a, b, _, r in exit_edges() if (a, b) == (level, dest)])


def exit_need(level: str, exit_id: str, dest: str) -> str:
    """What using one of ``level``'s exits (its id in the vanilla data) needs."""
    reqs = [r for a, _, x, r in exit_edges() if a == level and x == exit_id]
    return _least(reqs) if reqs else needs(level, dest)


def need_kind(req: str) -> str:
    """The colour's name (:data:`NEEDS`) of a requirement: what it needs first of a key, disc fragments,
    powers and an event."""
    try:
        found = list(atoms(parse(req)))
    except ParseError:
        return "event"
    if found == [("const", False)]:
        return "unreachable"
    counters = {a[1] for a in found if a[0] == "counter"}
    elements = frozenset(counters & {"air", "water", "fire", "earth"})
    keys = sorted(c[4:] for c in counters if c.startswith("key."))
    if keys:
        return f"key {keys[0]}" if len(keys) == 1 else "keys"
    if any(c.startswith("disc") for c in counters):
        return "fragments"
    if len(elements) == 1:
        return next(iter(elements))
    if elements:
        return BREAKS.get(elements, "powers")
    return "nothing" if all(a == ("const", True) for a in found) else "event"


@functools.cache
def key_names() -> tuple[str, ...]:
    """Every key the vanilla data places, by name (``key_battery``: "battery")."""
    db = kept_logic().db
    return tuple(sorted({loc["item"][4:] for doc in db.generated.values() for loc in doc["locations"]
                         if loc["item"].startswith("key_")}))


def colour(kind: str) -> str:
    """A :func:`need_kind`'s colour: :data:`NEEDS`'s, else its key's own."""
    if kind in NEEDS:
        return NEEDS[kind]
    name = kind.removeprefix("key ")
    others = [n for n in key_names() if n not in KEY_COLOURS]
    return KEY_COLOURS.get(name) or KEY_SHADES[others.index(name) % len(KEY_SHADES) if name in others else 0]


def say(req: str) -> str:
    """A requirement in words: ``water>=1 & key.battery>=1`` is "water 1 + key battery"."""
    if req.strip() in ("", "true"):
        return "nothing"
    s = re.sub(r"\bkey\.(\w+)>=1\b", r"key \1", req)
    s = re.sub(r"\bkey\.(\w+)>=(\d+)", r"\2 \1 keys", s)
    s = re.sub(r"\bdisc([awfel])>=(\d+)", lambda m: f"{m[2]} {ELEMENT[m[1]]} fragments", s)
    s = re.sub(r"\b(obsidian|sapphire|emerald|ruby|diamond)>=(\d+)", r"\2 \1s", s)
    s = re.sub(r"\b([a-z]+)>=(\d+)", r"\1 \2", s)
    s = re.sub(r"\b(?:flag|button|event):\w+\.([\w.]+)", lambda m: m[1].replace("_", " ").replace(".", " "), s)
    return s.replace(" & ", " + ").replace(" | ", " or ")


def need_words(req: str) -> str:
    """What a tip says a way needs: "unreachable", else "needs ..."."""
    return "unreachable" if need_kind(req) == "unreachable" else f"needs {say(req)}"


def one_way(level: str, dest: str) -> bool:
    """No exit edge of ``dest`` the logic can use leads back to ``level`` (M9)."""
    return all(need_kind(r) == "unreachable" for a, b, _, r in exit_edges() if (a, b) == (dest, level))


def barrier_kind(b: dict) -> str:
    """A barrier group's kind as the maps draw it (Modkit's ``render_level_maps.barrier_kind``)."""
    from azurkit.tools.randomizer import DAMAGE_KINDS

    if b["kind"] != "other" or b["requires"] is None:
        return b["kind"]
    return DAMAGE_KINDS.get(b["damage"], "other")


@functools.cache
def overlays(grid: tuple[str, ...]) -> dict:
    """What every map of the ``grid``'s levels draws besides its picture and its spots, as Modkit's map view
    does, by name and in the vanilla data's order (where each lies is ``maps.json``'s): each level's
    ``exits`` (its live exits in maps.json's order: the spot, the level it leads to, its need's ``kind`` and
    ``colour``, ``dashed`` when one way, and its ``tip``), ``barriers`` and ``features`` (by id: their icon or
    letter, colour, tip and the barrier's power level), and the world's ``lines`` (each pair of levels an
    exit joins, coloured by what it needs, dashed when one way, its tip naming each way)."""
    db = kept_logic().db
    levels, ways = {}, {}
    for level in grid:
        gen = db.generated[level]
        needs_of = {r["id"]: r.get("requires") for table in ("keylocks", "seals") for r in gen[table]}
        exits = []
        for e in (g for g in gen["exits"] if g["kind"] == "exit" and g["live"]):
            req = exit_need(level, e["id"], e["dest_level"])
            kind, one = need_kind(req), one_way(level, e["dest_level"])
            exits.append({"spot": e["spot"] or "", "to": e["dest_level"], "kind": kind, "colour": colour(kind),
                          "dashed": one, "disc": e["disc_teleport"],
                          "tip": f"{e['spot'] or ''} → {e['dest_level']}: {need_words(req)}"
                                 + ("; one way" if one else "")})
            if e["dest_level"] in grid and e["dest_level"] != level:
                ways.setdefault((level, e["dest_level"]), needs(level, e["dest_level"]))
        features = {}
        for kind, rows in (("save", gen["save_points"]), ("keylock", gen["keylocks"]), ("seal", gen["seals"]),
                           ("teleport", gen["teleporters"])):
            for r in rows:
                letter, fill, name = FEATURES[kind]
                need = needs_of.get(r["id"])
                features[r["id"]] = {"letter": letter, "colour": fill, "tip": f"{name}: needs {say(need)}" if need
                                     else name}
        barriers = {}
        for g in gen["barriers"]:
            if (kind := barrier_kind(g)) not in BARRIER_ICONS:
                continue
            lvl, name = g.get("level"), "" if g["name"] == "all" else f" {g['name']}"
            barriers[g["id"]] = {"icon": BARRIER_ICONS[kind], "level": lvl,
                                 "tip": f"{BARRIER_NAMES[kind]}{name}" + (f", level {lvl}" if lvl else "")
                                        + f": needs {say(g['requires'] or 'true')}"}
        levels[level] = {"exits": exits, "features": features, "barriers": barriers}
    lines = []
    for pair in sorted({frozenset(w) for w in ways}, key=sorted):
        a, b = sorted(pair)
        there = [(src, dst) for src, dst in ((a, b), (b, a)) if (src, dst) in ways]
        kind = next((k for k in (need_kind(ways[w]) for w in there) if k != "nothing"), "nothing")
        one = one_way(a, b) or one_way(b, a)
        lines.append({"a": a, "b": b, "kind": kind, "colour": colour(kind), "dashed": one,
                      "tip": "\n".join(f"{src} → {dst}: {need_words(ways[src, dst])}" for src, dst in there)
                             + ("; one way" if one else "")})
    return {"levels": levels, "lines": lines}
