"""D358's match-Garret values (Step 2.165b): for the Player page's buttons
beside Model size, Attack reach, Attack damage and Attack speed, the value
each slider takes for the chosen body to stand, reach, chain and deal
damage as garret4 does, read from one in-memory dress of the build's own
:func:`~azurik_mod.patches._player_character.apply_player_model` (its
:class:`~azurik_mod.patches._player_character.AttackLogic`):

- Model size: garret4's height (2.002 m) over the body's drawn at Model
  size 1, the ``--player-character-size garret4`` rule (``size_scale``
  over the scale its size draws it at): 1.0 with "garret4's height" on.
- Attack reach: garret4's basic swing straight ahead
  (``GARRET4_FORWARD``, 2.76 m, D237) over the build's best melee reach
  per unit of the slider (``AttackLogic.reach`` grows with it in step).
- Attack speed: the speed at which the basics' mean W19 chain point is
  garret4's (9.83 ticks), bisected: W19's 0.2 s after the hit and 4
  ticks after the contact don't scale with the speed, and it keeps a
  basic's own ``Move end1`` that falls after the hit and within a tick
  of that point (the bare-hands kit's often do, Step 2.159a).
- Attack damage: garret4's one-target combo rate over the body's at the
  speed slider's value, after the balance's B and its D389/D350 factor,
  linear in the slider (so a ratio, at most what the balance gives).

Each reads the other sliders as they are (speed and damage the reach and
size, damage the speed); a variant's slider multiplies its recipe's
number, so its value is that multiplier.  garret4's own body matches at
1 throughout, measured by no one; it, Skin only and a body with no clips
play garret4's attack timing and multipliers, so speed matches at 1 and
damage at 1 at Attack speed 1 alone (their recipe's inverses for a
variant), his damage per second at another speed unmeasured.  A body
whose basics swing his own moves (``Combo.borrowed``: the six farmers,
Step 2.134a) matches damage at Attack speed 1 alone too, for the same
reason.  A value the body can't match is ``None`` with the reason.
Nothing is clamped (D23)."""

from __future__ import annotations

import contextlib
import io
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from azurkit.tools.characters.characters import height, read_body
from azurkit.tools.characters._player_character import PLAYER, AttackLogic, Combo, apply_player_model
from azurkit.tools.characters._player_damage_marker import GARRET4_FORWARD

if TYPE_CHECKING:
    from azurkit.tools.characters._player_variants import Variant

SPEEDS = (1e-3, 1e3)
"""The attack speeds the speed match is bisected over (log-spaced)."""


@dataclass(frozen=True)
class Match:
    """One body's match-Garret slider values (:func:`garret_match`): each
    ``None`` with its reason in ``why`` (by slider) when none matches;
    the damage's at a speed slider value (:meth:`damage`)."""

    size: float | None
    reach: float | None
    speed: float | None
    combo: Combo | None = None
    units: tuple[float, float] = (1.0, 1.0)
    """A variant's recipe speed and damage, which those sliders multiply."""
    why: dict[str, str] = field(default_factory=dict)

    def damage(self, speed: float) -> tuple[float | None, str]:
        """The damage slider's match at the speed slider's ``speed`` and its
        reason when there is none."""
        speed_unit, damage_unit = self.units
        if not damage_unit:
            return None, "its recipe's damage is 0, which no multiplier lifts"
        at = speed * speed_unit
        if not at > 0:
            return None, "at Attack speed 0 or less no attack ends (D247)"
        if self.combo is None or self.combo.borrowed:   # garret4's attacks: his rate at another speed unmeasured
            if not math.isclose(at, 1.0, rel_tol=1e-3):   # the speed match's 4 figures (Step 2.165b's reviews)
                return None, (f"it plays garret4's own attacks, which deal his damage per second at Attack speed "
                              f"x{1.0 / speed_unit:.4g} only")
            if self.combo is None:
                return 1.0 / damage_unit, ""
        own = self.combo.rate(at)
        if not own or not self.combo.norm_rate:
            return None, "a basic or both finishers hit nothing, so it deals no damage per second to match"
        return self.combo.norm_rate / own / damage_unit, ""


GARRET4 = Match(1.0, 1.0, 1.0)
"""garret4's own body's match: 1 throughout (damage at Attack speed 1),
measured by no one."""


def _speed(combo: Combo) -> float | None:
    """The speed at which ``combo``'s basics chain on average when
    garret4's do, bisected over :data:`SPEEDS` (its pace falls as the
    speed rises); ``None`` outside them."""
    lo, hi = SPEEDS
    slow, fast = combo.pace(lo), combo.pace(hi)
    if None in (combo.norm_pace, slow) or not slow >= combo.norm_pace >= fast:
        return None
    for _ in range(80):
        mid = math.sqrt(lo * hi)
        lo, hi = (mid, hi) if combo.pace(mid) > combo.norm_pace else (lo, mid)
    return math.sqrt(lo * hi)


def garret_match(iso: Path | str, species: str, mode: str = "own", size: str = "own", anims: str | None = None,
                 scale: float = 1.0, reach: float = 1.0, balance: bool | None = None,
                 ground: bool | None = None, variant: Variant | None = None, ram: int | None = None) -> Match:
    """The match-Garret values (module docstring) for ``species`` (a
    ``variant``'s name in its place, built in or saved as the build
    resolves it, Step 2.164a: its base in its recipe's own mode, size,
    balance and ground) dressed in the image ``iso`` as a build at these
    options, Model size ``scale`` and Attack reach ``reach`` dresses it
    (garret4's sounds: they move no value), on the default build's packs
    (both upper packs since D588; at 256 ``qol_memory_upper256`` too, Step
    2.162l) for the machine ``ram`` (Step 2.162i; ``None``, the largest
    its packs make room for), so the build's size lines;
    :class:`ValueError` as the build's, and
    :class:`RuntimeError` for a shim the compiler can't build."""
    from azurkit.tools.characters._player_variants import options

    if species == PLAYER:
        return GARRET4
    worn = variant
    game, logic = iso, AttackLogic()
    with contextlib.redirect_stdout(io.StringIO()):    # the shims' lines
        if worn is not None:
            apply_player_model(game, worn.base, variant=worn, logic=logic, ram=ram,
                               **options(worn, scale=scale, reach=reach))
        else:
            apply_player_model(game, species, mode=mode, size=size, model_scale=scale, attack_reach=reach,
                               attack_balance=balance, attack_ground=ground, missing_anims=anims,
                               sounds="garret4", logic=logic, ram=ram)
    unit = worn.scale if worn is not None else 1.0
    characters = game.stored("characters.xbr")
    tall = height(characters, read_body(characters, PLAYER))   # garret4's 2.002 m
    size_match = tall / logic.height / unit if logic.height and unit else None
    reach_match = GARRET4_FORWARD * reach / logic.reach if logic.reach else None   # the reach grows with the slider
    speed_unit, damage_unit = (worn.speed, worn.damage) if worn is not None else (1.0, 1.0)
    at = 1.0 if logic.combo is None else _speed(logic.combo)   # no combo: garret4's timing
    speed_match = at / speed_unit if at is not None and speed_unit else None
    why = {}
    if size_match is None:
        why["player_character_scale"] = "its recipe's scale is 0" if logic.height else "it has no height to measure"
    if reach_match is None:
        why["player_attack_reach"] = (f"none of its idle swings (basic1, the sweeps) is melee (Step 2.61's 4 m rule), so none stands in for "
                                      f"garret4's basic swing, {GARRET4_FORWARD:.2f} m ahead (D237)"
                                      if logic.reach is None else "at this Attack reach no melee box reaches ahead")
    if speed_match is None:
        why["player_attack_speed"] = ("none of its basics hits, so none chains as garret4's"
                                      if logic.combo is not None and logic.combo.pace() is None
                                      else "no attack speed chains its basics as garret4's")
    return Match(size_match, reach_match, speed_match, logic.combo, (speed_unit, damage_unit), why)
