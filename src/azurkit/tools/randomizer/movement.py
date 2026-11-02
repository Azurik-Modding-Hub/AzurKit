"""A build's movement sliders in the randomizer (D1064, D1066).

The logic is the level files' as authored, at vanilla movement: no slider
re-checks it. Movement sliders moved (a share string's, a build's, a worn
body's walk and roll folded in) pick the movement tier the seed is filled at
instead (:func:`played`): the tier whose reach (``draft/tiers.toml``: the
share of what perfect flaps add that a tier counts) is nearest the asked
tier's times the sliders' travel factor k (:func:`factor`). k comes from a
shipped table, ``data/slider_tiers.json``, which ``scripts/slider_tiers.py``
makes from :mod:`.physics`: each slider's k at its points (the mean, over air
ranks 0-3 at landings 0, +2 and -2 m, of its travel over vanilla's), read on
the line between them and at the end past either end; sliders multiply. So the
seed is that tier's seed, its digest included, by plain arithmetic on the
table (no search, no libm): the same on every host, never refused.

A seed with a moved slider isn't promised beatable (D1064): the plan's line
(:func:`said`) and the build's first reason (``generator.movement_reasons``)
say so. The roll, climb and swim feed no tier: the table reads only the
fields :data:`MODELLED` names; a roll other than garret4's still flags a skip
proven at his (``layer.roll_reasons``, :func:`rolling_skips`).
"""

from __future__ import annotations

import functools
import json
import math
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

from azurkit.tools.randomizer.planner.settings import MOVEMENT_TIERS, RATING_NAMES

# The Movement fields the tier table reads (scripts/slider_tiers.py): a slider on another field (the roll, the swim,
# the climb) feeds no tier
MODELLED = frozenset({"run_speed", "jump_scale", "gravity", "air_control_scale", "flap_scale", "flaps",
                      "flap_ceiling_scale", "descent_scale", "descent_fuel_scale", "flap_fuel_scale", "fps"})
TABLE = Path(__file__).resolve().parent / "data" / "slider_tiers.json"
PROMISE = "seeds with moved sliders aren't promised beatable"


@functools.cache
def table() -> dict:
    """The shipped tier table (``scripts/slider_tiers.py`` writes it): each tier's ``reach`` and, by ``"pack
    slider"``, each modelled slider's ``points`` ([value, k], sorted; ``whole``: the game truncates it)."""
    return json.loads(TABLE.read_text(encoding="utf-8"))


def _at(row: Mapping, value: float) -> float:
    """``row``'s k at ``value``: on the line between its points, the end's past an end."""
    points, v = row["points"], float(math.trunc(value)) if row.get("whole") else value
    if v <= points[0][0]:
        return points[0][1]
    for (a, ka), (b, kb) in zip(points, points[1:]):
        if v <= b:
            return ka + (kb - ka) * (v - a) / (b - a)
    return points[-1][1]


def factor(sliders: Mapping) -> float:
    """The travel factor k of movement ``sliders`` (``{pack: {slider: value}}``): each modelled one's, multiplied in
    a fixed order; 1 for none (and for the roll, climb and swim)."""
    k, rows = 1.0, table()["sliders"]
    for pack, values in sorted(sliders.items()):
        for name, v in sorted(values.items()):
            if (row := rows.get(f"{pack} {name}")) is not None:
                k *= _at(row, float(v))
    return k


def tier_of(settings) -> str:
    """The movement tier ``settings`` play at: their own with no slider, else the tier whose reach is nearest their
    tier's times :func:`factor` (the lower on a tie)."""
    if not settings.sliders:
        return settings.movement_tier
    reach = table()["reach"]
    want = reach[settings.movement_tier] * factor(settings.sliders)
    return min(MOVEMENT_TIERS, key=lambda tier: abs(reach[tier] - want))


def played(settings):
    """``settings`` as the fill and the logic read them: at :func:`tier_of`'s tier, no slider (so a plan under moved
    sliders is that tier's seed, and reading it again changes nothing)."""
    return replace(settings, movement_tier=tier_of(settings), sliders={}) if settings.sliders else settings


def _named(tier: str) -> str:
    return RATING_NAMES[MOVEMENT_TIERS.index(tier) + 1]


def said(settings) -> str | None:
    """What the movement sliders of ``settings`` make of their tier, in words (None with none the table reads)."""
    rows = table()["sliders"]
    if not any(f"{pack} {name}" in rows for pack, values in settings.sliders.items() for name in values):
        return None
    asked, now = _named(settings.movement_tier), _named(tier_of(settings))
    return (f"your movement sliders make {asked} play like {now}, so the seed is {now}'s" if now != asked
            else f"your movement sliders keep {asked}'s seed")


def sliders_text(sliders: Mapping) -> str:
    """Movement sliders (``{pack: {slider: value}}``) in words, each value
    as typing it gives it back (a size fold's sqrt(s) whole)."""
    return ", ".join(f"{pack} {name} {v:g}" if float(f"{v:g}") == v else f"{pack} {name} {float(v)!r}"
                     for pack, values in sorted(sliders.items())
                     for name, v in sorted(values.items())) or "none (vanilla movement)"


def rolling_skips(db) -> frozenset[str]:
    """The skips tricks.toml marks ``rolls = true`` (Step 2.133, AZ-607):
    proven at garret4's x1 roll (the rjump skips, w1.shoreline_rollthrough)."""
    return frozenset(s["id"] for s in db.tricks.get("skip", ()) if s.get("rolls"))


__all__ = ["MODELLED", "PROMISE", "TABLE", "factor", "played", "rolling_skips", "said", "sliders_text", "table",
           "tier_of"]
