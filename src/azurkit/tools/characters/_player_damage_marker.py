"""X3, the player-model swap's damage marker (Step 2.21c; D112; per
column and at the action point since Step 2.64, D219).

A body's attacks hit only through its ``m_damage`` marker, which the
attack clips switch on (``docs/RE_DATA.md`` § "Character bodies, their
clips and the damage marker").  A clip that switches none on never hits:
xemu sitting swapb (2026-10-12) counted 0 target queries and 0 HP dealt
over 172 flicken attack ticks.  The swap hooks the CALL of the
staff-wall check (0x8C8A0) at 0x8C3B0 in the PlayerControl tick with
``player_model/damage_marker.c``, which gives the attacks_anims columns
whose clip has no damage window (:data:`COLUMNS`, a 24-bit mask) a
marker of garret4's attack box at the body's action point, on from 20%
to 50% of each attack move (not the roll), and keeps the body's own
marker for every other column.

Only a ``--player-character`` build where some attack plays a clip with
no damage window gets it (a body whose clips switch none on, or one W3
gives an ``attack_*`` clip without one), every garret4's-exact body
with clips (D131), and a body with no clips at all in every mode, which
plays garret4's clips as timers (Step 2.67); garret4 and a body whose
every attack has its own damage window build the same bytes as without
X3.  In garret4's exact mode (Step 2.68), and on a body with no clips in
every mode (Step 2.75e, AZ-473), each column takes garret4's own box
and window for the clip it plays in vanilla (:func:`garret4_boxes`,
written into the shim's box table) instead of attack_1's box at 20-50%
of the move, and the body's own ``m_damage2`` (critter+0x21C), which the
damage pass also builds a box from, points at a marker that is never
on, so only garret4's box hits.
"""

from __future__ import annotations

import math
import struct
from collections.abc import Callable
from pathlib import Path

from azurkit.tools.characters.characters import Body, DamageWindow, damage_windows, forward, read_body
from azurkit.tools.characters.ports import ShimSource, TrampolinePatch, apply_trampoline_patch
from azurkit.tools.characters.ports import trampoline_shim_data
from azurkit.tools.characters.ports import release_session
from azurkit.tools.characters.ports import FloatParam
from azurkit.core.xbe import resolve_va_to_file

_REPO_ROOT = Path(__file__).resolve().parents[2]
SHIM = ShimSource(folder=Path(__file__).resolve().parent / "player_model",
                  stem="damage_marker")
OBJECT = "player_model_damage_marker"
"""The shim object's name in the shim build dir (``<OBJECT>.o``)."""

GARRET4_BOX = (0.1625, 1.2341, 0.564)
"""garret4's ``attack_1`` box's centre in his model (``characters.xbr``,
``m_damage`` during its window), the offset of X3's box from the action
point on a standardized body."""
GARRET4_EXTENT = (0.2412, 3.0497, 1.3889)
"""garret4's ``attack_1`` box's extents, X3's marker's outside garret4's
exact (the shim's ``g_marker``; its length 0.5 times them is the half
extents, garret4's size on any model)."""


def _x3_box(point: tuple[float, float, float], offset: tuple[float, float, float],
            scale: float) -> tuple[tuple[float, float], tuple[float, float]]:
    """X3's box outside garret4's exact, horizontally, in metres from the
    feet: unrotated, centred at the fixed ``point`` (model units) at the
    critter's ``scale`` plus ``offset`` (garret4's units), with garret4's
    half extents, as the shim builds it; its low and high (x, y)."""
    x, y = (p * scale + o for p, o in zip(point[:2], offset[:2]))
    hx, hy = (0.5 * e for e in GARRET4_EXTENT[:2])
    return (x - hx, y - hy), (x + hx, y + hy)


def x3_reach(point: tuple[float, float, float], offset: tuple[float, float, float], scale: float) -> float:
    """How far X3's box (:func:`_x3_box`) reaches from the feet outside
    garret4's exact, in metres (Step 2.73): its farthest horizontal
    corner."""
    low, high = _x3_box(point, offset, scale)
    return max(math.hypot(x, y) for x in (low[0], high[0]) for y in (low[1], high[1]))


def x3_forward(point: tuple[float, float, float], offset: tuple[float, float, float], scale: float) -> float:
    """How far X3's box (:func:`_x3_box`) reaches straight ahead of the
    feet (:func:`~azurik_mod.assets.characters.forward`; Step 2.137,
    AZ-604): what the logic compares with :data:`GARRET4_FORWARD`."""
    return forward(*_x3_box(point, offset, scale))


GARRET4_REACH = x3_reach((0.0, 0.0, 0.0), GARRET4_BOX, 1.0)
"""How far garret4's basic1 box (``attack_1``'s, :data:`GARRET4_BOX` and
:data:`GARRET4_EXTENT`) reaches from his feet to its farthest corner,
2.77 m: X3's placement (:data:`~azurik_mod.patches._player_character.HIT_NEAR`)
and X21 read it; the logic reads :data:`GARRET4_FORWARD`."""
GARRET4_FORWARD = x3_forward((0.0, 0.0, 0.0), GARRET4_BOX, 1.0)
"""garret4's basic swing (D237): how far his basic1 box reaches straight
ahead of his feet, 2.76 m (Step 2.137, AZ-604: the corner,
:data:`GARRET4_REACH`, overstated a centred square box by up to sqrt 2):
the logic's no-melee reason names it and D358's match-Garret reach reads
it, and X3's box on a hand, which no build measures, counts as it (it is
this box at the hand); a body's reach short of it never flags (D726)."""


def x3_side(model_scale: float) -> float:
    """What X3's box on a hand multiplies the hand's sideways place by
    at ``model_scale`` (Step 2.103, AZ-521): 1 over it above 1, so the box
    stays where the size puts it beside the facing line (the hand x the
    scale carried garret4's 0.24 m wide box off a small target dead
    ahead: town_male_6 x2's box sat 0.78 m to the side, x1's 0.39); 1 at
    or below 1 (x0.5 keeps its own place, nearer the line)."""
    return 1.0 / model_scale if model_scale > 1.0 else 1.0


def _param(name: str, default: float, what: str) -> FloatParam:
    return FloatParam(name=name, symbol=f"_player_model_x3_{name}", default=default,
                      label=f"Player model X3 {name}", description=what)


COLUMNS = _param("columns", float(0xFFFFFF), "The attacks_anims columns X3's marker serves, a "
                 "24-bit mask (exact in a float): those whose clip has no damage window.")
BONE = _param("bone", -1.0, "The action point's bone index (its runtime matrix), or -1 for "
              "the fixed point.")
POINT = tuple(_param(f"point_{a}", 0.0, f"The fixed action point's {a}, model units.") for a in "xyz")
OFFSET = tuple(_param(f"offset_{a}", v, f"The box centre's {a} from the action point, garret4's units.")
               for a, v in zip("xyz", GARRET4_BOX))
SIDE = _param("side", 1.0, "What the hand's sideways place (x) is multiplied by: 1 over a model scale "
              "above 1, so the box keeps its x1 place beside the facing line (Step 2.103, AZ-521).")

DAMAGE_MARKER = TrampolinePatch(
    name="player_damage_marker",
    label="Player model X3: a damage marker for a clip without one (C shim)",
    va=0x0008C3B0,
    replaced_bytes=bytes([0xE8, 0xEB, 0x04, 0x00, 0x00]),   # CALL 0x8C8A0
    shim_object=SHIM.object_path(OBJECT, _REPO_ROOT),
    shim_symbol="_c_player_damage_marker@4",
    float_params=(COLUMNS, BONE, *POINT, *OFFSET, SIDE),
)


BOX = struct.Struct("<8f")
"""One column of the shim's box table (``ColumnBox``): its window's start
and end as fractions of the clip, the box's centre from the action point
and its extents (the marker's length 0.5 times them is the half
extents), both in garret4's units (Step 2.68)."""
_BOXES_HEAD = struct.Struct("<i")
"""The table's head (``ColumnBoxes.exact``): 1 when its columns serve."""
BOXES_SIZE = _BOXES_HEAD.size + 24 * BOX.size
NO_BOX = (0.0,) * 8
"""A column whose clip has no damage window: X3's marker stays off."""


def garret4_window(characters_xbr: bytes, garret4: Body, clip: str) -> DamageWindow | None:
    """X3's window and box in garret4's exact for a column whose vanilla
    clip is ``clip`` (a :func:`garret4_boxes` row): from the first of the
    clip's damage windows on ``garret4``'s body (Step 2.61's evaluator,
    :func:`~azurik_mod.assets.characters.damage_windows`) to the end of the
    last (clip seconds), and the box bounding every box over them, its
    reach that box's (the attack balance weighs it, Step 2.69); ``None``
    for a clip with none (the roll)."""
    windows = damage_windows(characters_xbr, garret4.name, clip)
    if not windows or clip not in garret4.clips:
        return None
    low = tuple(min(w.low[i] for w in windows) for i in range(3))
    high = tuple(max(w.high[i] for w in windows) for i in range(3))
    return DamageWindow(windows[0].marker, min(w.on for w in windows), max(w.off for w in windows),
                        low, high, max(math.hypot(x, y) for x in (low[0], high[0]) for y in (low[1], high[1])),
                        min(w.near for w in windows))


def garret4_boxes(characters_xbr: bytes, clips: list[str],
                  window: Callable[[str], DamageWindow | None] | None = None) -> list[tuple[float, ...]]:
    """garret4's own box and window for each ``attacks_anims`` column
    playing ``clips`` (its vanilla Anims), as :data:`BOX` rows
    (:func:`garret4_window`, or ``window``'s for the clip: W26's grown
    rows, Step 2.134b): the window over the clip's length, and the
    box (its sweep: basic1's attack_1 is :data:`GARRET4_BOX`, 0.375-0.49
    of the clip); :data:`NO_BOX` for a clip with none (the roll)."""
    garret4 = read_body(characters_xbr, "garret4")
    out = []
    for clip in clips:
        w = window(clip) if window is not None else garret4_window(characters_xbr, garret4, clip)
        if w is None:
            out.append(NO_BOX)
            continue
        length = garret4.length(clip)
        out.append((w.on / length, w.off / length,
                    *((a + b) / 2 for a, b in zip(w.low, w.high)), *(b - a for a, b in zip(w.low, w.high))))
    return out


def install_damage_marker(xbe: bytearray, species: str, *, columns: int = 0xFFFFFF,
                          bone: int = -1, point: tuple[float, float, float] = (0.0, 0.0, 0.0),
                          offset: tuple[float, float, float] = GARRET4_BOX, side: float = 1.0,
                          boxes: list[tuple[float, ...]] | None = None) -> None:
    """Hook X3 into ``xbe`` for ``species``' body: its marker serves the
    attacks_anims ``columns`` (a mask), centred at bone ``bone``'s
    runtime origin (its sideways place x ``side``; or, with -1, at
    ``point``, model units) plus ``offset`` (garret4's units), on from
    20% to 50% of each move; with
    ``boxes`` (garret4's exact, and a body with no clips in every mode:
    :func:`garret4_boxes`) each column's own box and window instead, written into the shim's box table where
    it landed.  :class:`ValueError` names the species and the site when
    it can't (D35: the build writes no ISO).  The shim session the apply
    opens is released here, as ``apply_pack`` releases a pack's: it holds
    ``xbe``."""
    params = {COLUMNS.name: float(columns), BONE.name: float(bone),
              **{p.name: v for p, v in zip(POINT, point)},
              **{p.name: v for p, v in zip(OFFSET, offset)}, SIDE.name: side}
    try:
        ok = apply_trampoline_patch(xbe, DAMAGE_MARKER, repo_root=_REPO_ROOT,
                                    params=params, shim_source=SHIM.source_path())
    finally:
        release_session(xbe)
    if not ok:
        raise ValueError(f"--player-character {species!r}: {DAMAGE_MARKER.label} "
                         f"failed at VA 0x{DAMAGE_MARKER.va:X}")
    if boxes is None:
        return
    spans = [span for span in trampoline_shim_data(xbe, DAMAGE_MARKER, _REPO_ROOT,
                                                   shim_source=SHIM.source_path())
             if span[1] - span[0] == BOXES_SIZE]
    if len(spans) != 1 or len(boxes) > 24:
        raise ValueError(f"--player-character {species!r}: {DAMAGE_MARKER.label} landed no "
                         f"{BOXES_SIZE}-byte box table for {len(boxes)} columns")
    at = resolve_va_to_file(xbe, spans[0][0])
    data = _BOXES_HEAD.pack(1) + b"".join(BOX.pack(*box) for box in boxes)
    xbe[at:at + BOXES_SIZE] = data.ljust(BOXES_SIZE, b"\0")


__all__ = ["BONE", "BOX", "BOXES_SIZE", "COLUMNS", "DAMAGE_MARKER", "GARRET4_BOX", "GARRET4_EXTENT",
           "GARRET4_FORWARD", "GARRET4_REACH", "NO_BOX", "OBJECT", "OFFSET", "POINT", "SHIM", "SIDE", "garret4_boxes",
           "garret4_window", "install_damage_marker", "x3_forward", "x3_reach", "x3_side"]
