"""``randomize-full``'s randomizer layer (Step R1.10b; RANDOMIZER_PLAN
§5.3): the settings a build asks for, its plan (a fill, or a plan file),
the plan written into the level files as the build's first layer, and the
read-back of the final image.

- :func:`settings_from_args`: the database's defaults, then a settings
  file (``--settings``) or a share string (``--share``), then each option
  flag given on the command line (D144's, ``--skip``/``--no-skip`` and
  ``--exclude-category``), checked as a settings file is (§7.2).
- :func:`plan_for`: the fill of ``--seed`` under those settings with the
  build's own movement sliders (:func:`build_sliders`), which the
  settings, so the plan's share string, then hold (AZ-383); moved, they
  pick the tier the seed is filled at (:func:`~.movement.played`, D1066);
  or ``--plan``'s plan file, exactly, once :func:`checked_plan` reads it.
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
  (:func:`movement_reasons`, which the GUI shows live, Step R1.14).

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

from azurkit.tools.randomizer.movement import sliders_text
from azurkit.tools.randomizer.planner.settings import (
    CATEGORIES,
    DARK_FIRE,
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
_OPTION_FLAGS = ("skip_ceiling", "movement_tier", "skip", "no_skip", "exclude_category")
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
    for name in ("skip_ceiling", "movement_tier"):
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
    level = {"seed_difficulty": settings.seed_difficulty} if settings.seed_difficulty else {}
    return {"format": form, "skip_ceiling": settings.skip_ceiling,
            "movement_tier": settings.movement_tier, "dark_fire": DARK_FIRE, **level,
            "exclude_categories": kept, "skip_override": dict(sorted(settings.skip_override.items()))}


def settings_text(settings: Settings) -> str:
    """The settings file ``--save-settings`` writes (it loads back to the same settings)."""
    t = settings_doc(settings)
    lines = [f'format = "{t["format"]}"', f"skip_ceiling = {t['skip_ceiling']}",
             f'movement_tier = "{t["movement_tier"]}"', f"dark_fire = {t['dark_fire']}",
             *([f"seed_difficulty = {t['seed_difficulty']}"] if "seed_difficulty" in t else []),
             "exclude_categories = [" + ", ".join(f'"{c}"' for c in t["exclude_categories"]) + "]",
             "", "[skip_override]"]
    lines += [f'"{sid}" = {"true" if on else "false"}' for sid, on in t["skip_override"].items()]
    return "\n".join(lines) + "\n"


def build_sliders(enabled, params: Mapping) -> dict[str, dict[str, float]]:
    """The build's movement sliders (``physics.SLIDERS``) that aren't
    vanilla's, of its ``enabled`` packs in ``params`` (``{pack: {slider:
    value}}``; :func:`~.physics.slider_values`): what picks the tier its
    seed is made at and its share string and placement file record
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


def checked_plan(doc: Mapping, logic):
    """A plan file's object ``doc`` read back on ``logic``'s database
    (:func:`~.planner.plan.load_plan`: its keys' types, format, generator,
    sha256 and ``db_digest``) and beatable under its settings (:func:`~.planner.fill.verify`,
    the fill's own check: victory, every location but the forfeitable, no new
    trick-free trap), as a :class:`~.planner.plan.Plan`;
    :class:`~.planner.plan.PlanError` names each refusal (an edited plan's
    sha256 is anyone's to recompute, so its placement is checked)."""
    from azurkit.tools.randomizer.planner.fill import verify
    from azurkit.tools.randomizer.planner.plan import PlanError, load_plan

    plan = load_plan(doc, logic.db)
    if problems := verify(logic, plan.settings, plan.placement):
        raise PlanError(f"plan {doc['sha256'][:12]} isn't beatable under its settings: {'; '.join(problems)}")
    return plan


def plan_reasons(plan, logic, sliders: Mapping) -> list[str]:
    """Why a plan file's logic is unverified on a build of the movement
    ``sliders`` (Modkit's ``plan_for`` of ``--plan``): planned at other
    sliders, each problem :func:`~.planner.fill.verify` finds at the tier
    this build's pick (:func:`~.movement.played`; flagged, never refused),
    then :func:`roll_reasons`."""
    from azurkit.tools.randomizer.movement import played
    from azurkit.tools.randomizer.planner.fill import verify

    lost = verify(logic, played(replace(plan.asked, sliders=dict(sliders))), plan.placement) \
        if plan.asked.sliders != sliders else []
    return [f"the plan verifies at the movement it was planned for but not at this build's: {p}" for p in lost] + \
        roll_reasons(plan.asked, logic.db, sliders)


def plan_for(args, logic, sliders=None):
    """The build's plan and why its logic is unverified so far, as (plan,
    why): ``--plan``'s plan file (a plan file's object), exactly, once
    :func:`checked_plan` reads it (``why``: :func:`plan_reasons`), else the
    fill of ``--seed`` (default ``"42"``) under
    :func:`settings_from_args` with the build's movement ``sliders``
    (:func:`build_sliders`; none: vanilla's), on ``logic`` (the logic as
    authored); moved, they pick the tier it is filled at, so the seed is that
    tier's (:func:`~.movement.played`, D1066). A ``--share`` made for other
    sliders is refused (:class:`LayerError`): its sliders pick its tier, so
    its world differs (AZ-383). ``why``: :func:`roll_reasons`. Raises the
    planner's errors (D35)."""
    from azurkit.tools.randomizer.movement import played
    from azurkit.tools.randomizer.planner.fill import fill
    from azurkit.tools.randomizer.planner.plan import load_plan, plan_doc

    sliders = dict(sliders or {})
    if _given(args, "plan"):
        plan = checked_plan(args.plan, logic)
        return plan, plan_reasons(plan, logic, sliders)
    settings = settings_from_args(args, logic.db)
    if settings.sliders and settings.sliders != sliders:
        raise LayerError(f"--share holds the movement sliders {sliders_text(settings.sliders)}, and this build's "
                         f"are {sliders_text(sliders)}: its sliders pick the tier its seed is made at, so set the "
                         f"same sliders (AZ-383); a worn body's size folds into the walk and roll sliders, so build "
                         f"the same body at the same size (Step 2.133)")
    seed = str(args.seed if getattr(args, "seed", None) is not None else "42")
    asked = replace(settings, sliders=sliders)
    plan = load_plan(plan_doc(fill(logic, seed, played(asked)), logic.db, asked), logic.db)
    return plan, roll_reasons(asked, logic.db, sliders)


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
                                           "RB press holds the player in it",
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
           "build_sliders", "checked_plan", "obsidian_reason", "plan_for", "plan_reasons", "roll_reasons", "read_settings", "size_params",
           "sliders_text", "settings_from_args", "settings_text", "spoiler_text"]
