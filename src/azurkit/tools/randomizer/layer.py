"""``randomize-full``'s randomizer layer (Step R1.10b; RANDOMIZER_PLAN
§5.3): the settings a build asks for, its plan (a fill, or a plan file),
the plan written into the level files as the build's first layer, and the
read-back of the final image.

- :func:`settings_from_args`: the database's defaults, then a settings
  file (``--settings``) or a share string (``--share``), then each option
  flag given on the command line (D144's, ``--skip``/``--no-skip`` and
  ``--exclude-category``), checked as a settings file is (§7.2).
- :func:`plan_for`: ``--plan FILE`` (refused when its ``db_digest``
  differs), else the fill of ``--seed`` under those settings, on the logic
  of the build's own movement sliders (:func:`build_sliders`, Step R1.14b:
  :func:`~.movement.logic_for` re-checks every modelled flight), which the
  settings, so the plan's share string, then hold (AZ-383).
- :func:`write_layer`: the plan through :func:`~.writer.write_plan`, and
  ``--obsidian-cost``'s lock thresholds, as the layer ``randomizer`` of
  the build's :class:`~azurik_mod.patching.mod_apply.LayerLog`.
- :func:`judge`: the read-back of the final image (:func:`~.writer.read_back`):
  a difference a later layer explains (it wrote the location's record,
  name field or the string it names) is a D28 conflict and the build's
  ``logic_verified`` is false; any other fails the build (D35).
- :func:`check_movement`: the movement rule (Step R1.13, D83(c), Q291;
  Step R1.14b): a slider the logic doesn't model (the roll, the swim) past
  its ``logic_floor``, a name no slider has or a swapped body no
  sitting has graded (D260) makes ``logic_verified`` false
  (:func:`movement_reasons`, which the GUI shows live, Step R1.14); so
  does movement that breaks what the logic's
  nodes stand on (:func:`plan_for`'s reasons).

Outputs beside the ISO (D36's rules): the placement file the GUI's maps
and its Spoiler Save… read (:mod:`~.placements`), and on request the
spoiler and the settings file. Nothing here prints a game byte.
"""

from __future__ import annotations

import math
import struct
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path

from azurkit.tools.randomizer.planner.settings import (
    CATEGORIES,
    Settings,
    SettingsError,
    category_table,
    pick_of,
    settings_from_table,
    share_decode,
)

LAYER = "randomizer"
OBSIDIAN_LOCK_TABLES = (0x37DBDC4, 0x37DC0E4)   # town.xbr's two copies of the 10 lock thresholds (float32)
OBSIDIAN_LOCK_ENTRY_SIZE = 48
OBSIDIAN_LOCK_COUNT = 10
OBSIDIAN_COST_VANILLA = 10.0    # lock k opens at 10k (lock 10 just under 100): Q243

# The settings the option flags set, and the flags no --plan or --no-randomize build takes.
_OPTION_FLAGS = ("skip_ceiling", "movement_tier", "dark_fire", "skip", "no_skip", "exclude_category")
_PLAN_FLAGS = ("seed", "settings", "share", *_OPTION_FLAGS)


class LayerError(ValueError):
    """The randomizer layer can't run as asked; the message names why."""


def _given(args, name: str) -> bool:
    value = getattr(args, name, None)
    return value not in (None, [], False)


def settings_from_args(args, db) -> Settings:
    """The build's settings: the database's defaults, a ``--settings`` file
    or a ``--share`` string over them (its movement sliders too, AZ-383),
    then each option flag given. Raises :class:`SettingsError` naming every
    refusal (§7.2)."""
    skips = {sid: s for sid, (_, s) in db.skips.items()}
    if _given(args, "settings"):
        base = read_settings(Path(args.settings), skips)
    elif _given(args, "share"):
        base = share_decode(args.share, skips)
    else:
        base = db.defaults
    table = settings_doc(base)
    for name in ("skip_ceiling", "movement_tier", "dark_fire"):
        if getattr(args, name, None) is not None:
            table[name] = getattr(args, name)
    on, off = ({pick_of(sid, skips) for sid in getattr(args, name, None) or ()} for name in ("skip", "no_skip"))
    if on & off:   # D275: a variant's id stands for its batch
        raise SettingsError("options", [("settings_bad_override", f"skip_override.{pid}", "both --skip and --no-skip")
                                        for pid in sorted(on & off)])
    table["skip_override"] = {**table["skip_override"], **dict.fromkeys(on, True), **dict.fromkeys(off, False)}
    st = settings_from_table(table, skips, "options")
    excluded = st.exclude_categories | set(getattr(args, "exclude_category", None) or ())   # each flag is literal
    form, table["exclude_categories"] = category_table(
        sorted(excluded, key=lambda c: CATEGORIES.index(c) if c in CATEGORIES else 99))
    return replace(settings_from_table({**table, "format": form}, skips, "options"), sliders=base.sliders)


def read_settings(path: Path, skips: Mapping[str, Mapping]) -> Settings:
    """A settings file, checked (§7.2); raises :class:`SettingsError`
    naming the file and each refused key."""
    try:
        table = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise SettingsError(str(path), [("settings_unreadable", "settings", str(exc))]) from None
    return settings_from_table(table, skips, str(path))


def settings_doc(settings: Settings) -> dict:
    """A settings file's table: every option, the toggles and the excluded
    categories (§7.2), in format /1 unless it needs /2 (:func:`category_table`)."""
    form, kept = category_table(settings.exclude_categories)
    return {"format": form, "skip_ceiling": settings.skip_ceiling,
            "movement_tier": settings.movement_tier, "dark_fire": settings.dark_fire,
            "exclude_categories": kept, "skip_override": dict(sorted(settings.skip_override.items()))}


def settings_text(settings: Settings) -> str:
    """The settings file ``--save-settings`` writes (it loads back to the same settings)."""
    t = settings_doc(settings)
    lines = [f'format = "{t["format"]}"', f"skip_ceiling = {t['skip_ceiling']}",
             f'movement_tier = "{t["movement_tier"]}"', f"dark_fire = {t['dark_fire']}",
             "exclude_categories = [" + ", ".join(f'"{c}"' for c in t["exclude_categories"]) + "]",
             "", "[skip_override]"]
    lines += [f'"{sid}" = {"true" if on else "false"}' for sid, on in t["skip_override"].items()]
    return "\n".join(lines) + "\n"


def build_sliders(enabled, params: Mapping) -> dict[str, dict[str, float]]:
    """The build's movement sliders (``physics.SLIDERS``) that aren't
    vanilla's, of its ``enabled`` packs in ``params`` (``{pack: {slider:
    value}}``; :func:`~.physics.slider_values`): what its logic is
    re-checked under and its share string and placement file record
    (AZ-383); a name no slider has is :func:`movement_reasons`' to name."""
    from azurkit.tools.randomizer.physics import slider_values

    return slider_values(params, enabled)


SIZE_PACK = "player_physics"
SIZE_SLIDERS = ("walk_speed_scale", "roll_speed_scale")   # each x sqrt(s): D342's run, D330's roll
SIZE_FOLD = "size_fold"   # player_physics' sqrt(s), the speed toggle's "off" for those two (Step 2.186)


def size_params(enabled, params: Mapping, s: float) -> tuple[list[str], dict[str, dict[str, float]]]:
    """``enabled`` and ``params`` (``{pack: {slider: value}}``) with a
    worn body's size ``s`` folded in (Step 2.133; D330, D342, D353): the
    player_physics walk and roll sliders (:data:`SIZE_SLIDERS`; an unset
    one from 1.0) times sqrt(``s``) and the pack enabled, so the body runs
    garret4's speed and rolls his distance x sqrt(s) and the logic, the
    share string and the placement file read the composed numbers
    (:func:`build_sliders`, AZ-383); ``s`` 1 (garret4's height: the
    vanilla player, a standardized body) leaves both as they are.  With
    the speed toggle on either (``toggle_<slider>``), :data:`SIZE_FOLD`
    is sqrt(``s``) too, so a left stick click flips it to the body's own
    walk and roll, not garret4's (Step 2.186)."""
    if s == 1.0:
        return list(enabled), dict(params)
    folded = {pack: dict(values) for pack, values in params.items()}
    values = folded.setdefault(SIZE_PACK, {})
    for name in SIZE_SLIDERS:
        values[name] = values.get(name, 1.0) * math.sqrt(s)
    if any(values.get(f"toggle_{name}") for name in SIZE_SLIDERS):
        values[SIZE_FOLD] = math.sqrt(s)
    return list(enabled) + ([SIZE_PACK] if SIZE_PACK not in enabled else []), folded


def sliders_text(sliders: Mapping) -> str:
    """Movement sliders (``{pack: {slider: value}}``) in words."""
    return ", ".join(f"{pack} {name} {v:g}" for pack, values in sorted(sliders.items())
                     for name, v in sorted(values.items())) or "none (vanilla movement)"


def plan_for(args, db, sliders=None):
    """The build's plan and the logic it stands on, as (plan, logic,
    recheck, why): ``--plan`` (checked against ``db``), else the fill of
    ``--seed`` (default ``"42"``) under :func:`settings_from_args` with the
    build's movement ``sliders`` (:func:`build_sliders`; none: vanilla's),
    on the logic of ``db`` under them at the settings' tier
    (:func:`~.movement.logic_for`). A ``--share`` made for other sliders is
    refused (:class:`LayerError`): its plan stands on other logic (AZ-383).
    ``why`` names what leaves that logic unverified: free movement the
    nodes stand on that the movement breaks, a ``--plan`` that verifies
    at the movement it was planned for but not at this build's (a plan
    that doesn't verify there is trusted, as before), else a slider weaker
    or taller-jumping over a hop the re-check can't judge (:func:`unjudged_reasons`).
    A run under garret4's 7 m/s (the walk slider, a worn body's size
    folded in: Step 2.133, D353) fills on the logic re-checked at it
    and, when none fills there, on his 7 m/s logic (:func:`~.movement.run_floor`;
    its share string records that run, which a ``--share`` may then hold)
    with :func:`floor_reason` (AZ-606: it raised "no plan" before).
    Raises the planner's errors (D35)."""
    from azurkit.tools.randomizer.movement import logic_for, run_floor, taller, weaker
    from azurkit.tools.randomizer.physics import Movement
    from azurkit.tools.randomizer.planner.fill import FillError, fill, verify
    from azurkit.tools.randomizer.planner.plan import load_plan, plan_doc

    sliders = dict(sliders or {})
    m = Movement.from_params(sliders)
    if _given(args, "plan"):
        plan = load_plan(Path(args.plan), db)
        logic, rc = logic_for(db, m, plan.settings.movement_tier)
        why = list(rc.broken)
        own = Movement.from_params(plan.settings.sliders)
        if own != m and (lost := verify(logic, plan.settings, plan.placement)) \
                and not verify(logic_for(db, own, plan.settings.movement_tier)[0], plan.settings, plan.placement):
            why += [f"the plan verifies at the movement it was planned for but not at this build's: {p}"
                    for p in lost]
        if not why and (weaker(sliders) or taller(sliders)) and not verify(logic, plan.settings, plan.placement):
            why += unjudged_reasons(plan, logic, db, sliders)
        return plan, logic, rc, why + roll_reasons(plan.settings, db, sliders)
    settings = settings_from_args(args, db)
    floor = run_floor(sliders)
    if settings.sliders and settings.sliders != sliders and settings.sliders != floor:
        raise LayerError(f"--share holds the movement sliders {sliders_text(settings.sliders)}, and this build's "
                         f"are {sliders_text(sliders)}: its plan stands on their logic, so set the same sliders "
                         f"(AZ-383); a worn body's size folds into the walk and roll sliders, so build the same "
                         f"body at the same size (Step 2.133)")
    seed = str(args.seed if getattr(args, "seed", None) is not None else "42")
    slower = replace(settings, sliders=sliders)
    slow, rc = logic_for(db, m, settings.movement_tier)
    if (floor is None or not settings.sliders or settings.sliders != floor) and (   # a --share on his run stands on it
            floor is None or not unreachable(slow, slower)):   # a location no plan collects there: none fills
        try:
            plan = load_plan(plan_doc(fill(slow, seed, slower), db), db)
        except FillError:
            if floor is None:
                raise
        else:
            return plan, slow, rc, (list(rc.broken) or unjudged_reasons(plan, slow, db, sliders)) + roll_reasons(
                slower, db, sliders)
    settings = replace(settings, sliders=floor)
    logic, rc = logic_for(db, Movement.from_params(floor), settings.movement_tier)
    plan = load_plan(plan_doc(fill(logic, seed, settings), db), db)
    return plan, logic, rc, [floor_reason(m, verify(slow, slower, plan.placement))] + (
        list(rc.broken) or unjudged_reasons(plan, logic, db, floor)) + roll_reasons(settings, db, sliders)


def unreachable(logic, settings) -> list[str]:
    """The pool locations ``logic`` reaches under ``settings`` with no
    item placed and every item held (``Logic.reach`` grows with what is
    held), but for the forfeitable: none a plan can collect, so a fill
    there can only fail its verify (D122's every location), and
    :func:`plan_for` falls back without its attempts (Step 2.133: 20 of
    them took 3 min at a 6.3 m/s run)."""
    held = [item for item in logic.vanilla_placement().values() if item]
    got = logic.reach(settings, {}, held, traps=False).locations
    return [loc for loc, lvl in sorted(logic.pool.items())
            if lvl not in logic.db.stubs and loc not in got and loc not in logic.forfeitable]


def roll_reasons(settings, db, sliders: Mapping) -> list[str]:
    """Why a roll other than garret4's x1 (the roll distance slider, a worn
    body's size folded in, or the roll speed slider: Step 2.185) leaves a
    plan's logic unverified (Step 2.133, D330, AZ-607): each skip
    ``settings`` turn on that was proven at his roll
    (``movement.rolling_skips``)."""
    from azurkit.tools.randomizer.movement import rolling_skips
    from azurkit.tools.randomizer.physics import Movement
    from azurkit.tools.randomizer.planner.settings import skips_on

    m = Movement.from_params(sliders)
    if m.roll_scale == 1.0 and m.roll_time_scale == 1.0:
        return []
    roll = " and ".join([f"goes x{m.roll_scale:.3g} garret4's distance"] * (m.roll_scale != 1.0)
                        + [f"plays x{m.roll_time_scale:.3g} his speed"] * (m.roll_time_scale != 1.0))
    on = set(skips_on(settings, {sid: s for sid, (_, s) in db.skips.items()})) & rolling_skips(db)
    return [f"skip {sid} is on and the roll {roll}: it was proven at his x1 roll" for sid in sorted(on)]


def floor_reason(m, lost) -> str:
    """Why a plan that fell back to garret4's run (:func:`plan_for`,
    Step 2.133, AZ-606) leaves its logic unverified: movement ``m``'s run,
    and what the logic re-checked at it says of the plan (``lost``:
    :func:`~.planner.fill.verify`'s problems there, its new traps and the
    locations it never collects)."""
    from azurkit.tools.randomizer.physics import RUN_SPEED

    return (f"the run is {m.run_speed:.2f} m/s, under garret4's {RUN_SPEED:g} m/s (the walk slider, a worn body's "
            f"size folded in: D353), and no plan fills on the logic re-checked at it, so the plan stands on his "
            f"{RUN_SPEED:g} m/s logic (its share string records that run, AZ-606)"
            + (f"; on the slower logic it fails ({'; '.join(lost)})" if lost else "")
            + ", so the logic can't count on its routes")


def unjudged_reasons(plan, logic, db, sliders: Mapping) -> list[str]:
    """AZ-384's conservative half: with a modelled slider weaker than
    vanilla (:func:`~.movement.weaker`), or one that raises the jump's arc
    (:func:`~.movement.taller`: no such hop has a known roof, so a taller
    arc may meet one, AZ-407), each hop of the plan's playthrough on
    ``logic`` that the re-check can't judge (:func:`~.movement.unjudged`:
    a hand edge, a ride, a probed walk, an edge past an undecoded gate)
    leaves its logic unverified; a reason per side names the first and
    counts the rest."""
    from azurkit.tools.randomizer.movement import taller, unjudged, weaker

    weak, tall = weaker(sliders), taller(sliders)
    hops = unjudged(plan, logic, db) if weak or tall else []
    if not hops:
        return []
    more = f" and {len(hops) - 1} more" if len(hops) > 1 else ""
    return [f"{', '.join(names)} {what}, and the plan crosses a hop the movement re-check can't judge{roof}: "
            f"{hops[0]}{more} ({az})"
            for names, what, roof, az in ((weak, "is weaker than vanilla", "", "AZ-384"),
                                          (tall, "raises the jump's arc over vanilla's",
                                           ", where a roof may clip the taller arc", "AZ-407")) if names]


def _thresholds(town, cost: float) -> list[tuple[int, float]]:
    """(offset, value) of each lock threshold ``cost`` writes in town.xbr's
    two tables: none when ``cost`` is vanilla's (Q243's writer half)."""
    end = OBSIDIAN_LOCK_TABLES[-1] + (OBSIDIAN_LOCK_COUNT - 1) * OBSIDIAN_LOCK_ENTRY_SIZE + 4
    if end > len(town):
        raise LayerError(f"--obsidian-cost: gamedata/town.xbr ({len(town)} bytes) can't hold its lock "
                         f"tables at {' and '.join(f'0x{t:X}' for t in OBSIDIAN_LOCK_TABLES)} (they end at 0x{end:X})")
    if cost == OBSIDIAN_COST_VANILLA:
        return []
    return [(base + i * OBSIDIAN_LOCK_ENTRY_SIZE, float(cost * (i + 1)))
            for base in OBSIDIAN_LOCK_TABLES for i in range(OBSIDIAN_LOCK_COUNT)]


@dataclass
class LayerReport:
    """What the layer did: the plan (None: ``--no-randomize``), the writer's
    report, the ``--obsidian-cost`` given and the thresholds written, and
    after :func:`judge` the D28 conflicts and whether the logic still holds."""
    plan: object | None
    write: object | None = None
    obsidian_cost: float | None = None
    thresholds: list[float] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    logic_verified: bool = True
    why_not: list[str] = field(default_factory=list)


def obsidian_reason(cost: float | None) -> str | None:
    """Why an obsidian cost leaves a plan's logic unverified (a cost above
    vanilla's), else None."""
    if cost is None or cost <= OBSIDIAN_COST_VANILLA:
        return None
    return f"--obsidian-cost {cost:g} raises the lock thresholds above vanilla's, which the plan's logic assumes"


# The speed sliders at 0 or less of a move that ends only when its clip's
# clock reaches the move's end (Step 2.185), as --player-attack-speed's
# (Step 2.123): the move never ends [inferred from the layer update].
LOCKS = {
    ("player_physics", "roll_time_scale"): "a roll played at a rate of 0 or less never ends, so the first "
                                           "BLACK press holds the player in it",
    ("player_physics", "climb_speed_scale"): "rungs and climb moves played at a rate of 0 or less never end, "
                                             "so the first ladder or hoist holds the player on it",
}

# The enemy sliders at 0 or less that leave an enemy the logic needs
# killed unkillable (Step 2.205): flagged, never refused (D23).
UNKILLABLE = {
    **{("enemy_scaling", f"{who}_health_scale"): f"every {who} spawns with no HP to lose, and a hit kills only "
                                                  "by taking HP from above 0 to 0 or less (apply_damage)"
       for who in ("enemy", "boss")},
    **{("enemy_scaling", f"{who}_size_scale"): f"{a} {who} drawn at a scale of 0 or less has no collision radius "
                                                "(collisionRadius x its scale) or a turned-out one, so no hit can "
                                                "be counted on to reach it" for a, who in (("an", "enemy"), ("a", "boss"))},
}


def _location_ranges(buf, loc: Mapping) -> list[range]:
    """The file bytes a location's read-back reads in ``buf``: its record's
    type field, its name field and the string that field names now."""
    from azurkit.tools.randomizer.writer import NAME_FIELD

    fld = loc["name_ref"]["field"]
    out = [range(fld - NAME_FIELD, fld - NAME_FIELD + 8), range(fld, fld + 8)]
    if fld + 8 <= len(buf):
        n, ref = struct.unpack_from("<Ii", buf, fld)
        at = fld + 4 + ref
        if 0 <= at <= at + n < len(buf):
            out.append(range(at, at + n + 1))
    return out


def spoiler_text(plan, logic, logic_verified: bool, why_not=()) -> str:
    """A build's spoiler: the plan's (:func:`~.planner.plan.spoiler_lines`)
    with the build's ``logic_verified`` and each reason on its second line."""
    from azurkit.tools.randomizer.planner.plan import spoiler_lines

    lines = spoiler_lines(plan, logic)
    lines.insert(1, f"logic_verified: {str(logic_verified).lower()}" + "".join(f"; {why}" for why in why_not))
    return "\n".join(lines) + "\n"


__all__ = ["CATEGORIES", "LAYER", "LayerError", "LayerReport", "SIZE_FOLD", "SIZE_PACK", "SIZE_SLIDERS",
           "build_sliders", "floor_reason", "obsidian_reason", "plan_for", "roll_reasons", "unreachable",
           "read_settings", "size_params", "sliders_text", "settings_from_args", "settings_text", "spoiler_text",
           "unjudged_reasons"]
