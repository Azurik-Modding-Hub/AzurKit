"""The game's LOD rules as code (D537; USA VAs, the critter draw 0x3EA00).

- **Switch distances** (:func:`thresholds`): ``load_critters_config``
  reads a species' ``critters_engine`` ``lodThreshold1``-``4`` into its
  CritterData +0x110..+0x11C (0x49AD0-0x49B3E): a missing cell reads as
  FLT_MAX, the first is at least 0 and each later one at least the one
  before.
- **The pick** (:func:`pick`): n = min(LODs - 1, 4) (0x3EE73), so LOD 5
  and on are never drawn; the target is how many of the first n
  thresholds the camera distance strictly passes in a row (0x3EEB7),
  stored as a float at critter +0x288 (0 while the cvar "LOD on" is off).
  The draw culls a critter past its ``farClip`` (CritterData +0x30,
  0x3EA1F).
- **The ease**: each frame the drawn value +0x284 goes 2/fps toward the
  target, clamped to [target - 1, target] going out (0x3EF93-0x3EFD5)
  and to [target, target + 1] coming in (0x3EFDD-0x3F023): it snaps to
  within one LOD of the target and fades the last one over 0.5 s.  A
  fractional value draws LODs k and k + 1 together (0x3F3F4, 0x3F719), so
  a target reached from a lower one draws the LOD below it, from a higher
  one the LOD above (:func:`reach`).
- **The realtime shadow**: a species with ``shadowSize`` > 0 (CritterData
  +0x94, 0x499EA; a missing cell 0) and no ``shadowTextureName`` (+0x9C
  -1, 0x49A8E) casts its shadow from its mesh: the critter constructor
  0x40380 (the player's too, 0x12463) makes the shadow (0x406C2-0x40886),
  and while ``render/shadows/realtime`` is on (default 1, 0xFDAF6) each
  frame draws its casters with pass 0x800 (0xC54E0, 0xC55B4), which
  draws the LOD 0xCC330 picks at 1.0 (0x3E8B1): LOD 1, or LOD 0 for a
  one-LOD body (0xCC351 clamps to LODs - 1).  A shadow that names a
  texture draws no mesh (0xC54F2: 0xC54E0 returns).
- **Load**: every LOD of a body is its own load run (``model inspect``'s
  own runs), loaded with the body whether drawn or not, so a LOD adds to
  the load budget and saves none; dropping a LOD the game never draws
  frees its runs.

:func:`pixel_error` is the metres a screen line spans at a distance, so
"p pixels at the switch distance d" is a ``max_error`` for
:func:`~azurik_mod.assets.decimate.decimate`.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import NamedTuple
from azurkit.core import fdlibm

FOV_Y = 55.4
"""The game camera's vertical field of view, degrees [inferred]."""
LINES = 480
"""The screen's lines [inferred: the game draws 640x480]."""
FLT_MAX = 3.4028234663852886e38
"""What a missing ``lodThreshold`` cell reads as (0x49AE5)."""
PICKED = 4
"""The thresholds the pick reads (0x3EE79): LOD 5 and on are never drawn."""
SHADOW_LOD = 1
"""The LOD a realtime shadow draws (0x3E8B1), clamped to the body's last."""


class Wearer(NamedTuple):
    """A species that wears a body: its name, its switch distances as the
    loader keeps them (:func:`thresholds`), its ``farClip`` (0 when the
    cell is missing: the loader's default at 0x49999, so it is never
    drawn) and whether it casts a realtime shadow (module docstring)."""

    species: str
    thresholds: list[float]
    far: float
    shadow: bool


def pixel_error(pixels: float, distance: float) -> float:
    """The metres ``pixels`` screen lines span ``distance`` metres from the
    camera: 2 d tan(FOV/2) / 480 a line, about 0.00219 d."""
    return pixels * 2.0 * distance * fdlibm.tan(math.radians(FOV_Y) / 2.0) / LINES


def thresholds(cells: Sequence[float | None]) -> list[float]:
    """``lodThreshold1``-``4`` (None: no cell) as the loader keeps them."""
    out: list[float] = []
    for v in cells:
        v = FLT_MAX if v is None else v
        out.append(max(v, out[-1] if out else 0.0))
    return out


def pick(distance: float, kept: Sequence[float], count: int) -> int:
    """The LOD a body of ``count`` LODs aims for at ``distance`` metres,
    with the switch distances ``kept`` (:func:`thresholds`)."""
    target = 0
    while target < min(count - 1, PICKED) and distance > kept[target]:
        target += 1
    return target


def spans(kept: Sequence[float], far: float, count: int) -> list[tuple[float, float] | None]:
    """For each of a body's ``count`` LODs, the distances at which the pick
    aims for it, (from, to] (LOD 0's from 0 on), cut at ``far``; None for
    one it never aims for."""
    n = min(count - 1, PICKED)
    edges = [0.0, *kept[:n]]
    out: list[tuple[float, float] | None] = []
    for k in range(count):
        if k > n:
            out.append(None)
            continue
        hi = min(edges[k + 1] if k < n else FLT_MAX, far, FLT_MAX)
        out.append((edges[k], hi) if k == 0 or edges[k] < hi else None)
    return out


def reach(kept: Sequence[float], far: float, count: int) -> tuple[list[int], list[int]]:
    """(steady, drawn): the LODs a wearer draws at rest at some distance,
    and those with the LODs its fades draw (module docstring: the target
    reached from a lower one draws the LOD below it, from a higher one the
    LOD above)."""
    steady = [k for k, s in enumerate(spans(kept, far, count)) if s]
    drawn = set(steady) | {t - 1 for t in steady if t > steady[0]} | {t + 1 for t in steady if t < steady[-1]}
    return steady, sorted(drawn)


def wearers(config_xbr: bytes, body: str) -> list[Wearer]:
    """The ``critters_engine`` species whose ``body`` is ``body``
    (case-blind), with their switch distances, ``farClip`` and shadow."""
    from azurkit.tools.characters.ports import XbrDocument

    engine = XbrDocument.from_bytes(config_xbr).keyed_section("critters_engine")
    rows = engine.row_names()

    def cell(col: int, row: str, kind: int = 1):
        c = engine.read_cell(col, rows.index(row)) if row in rows else None
        return None if c is None or c.type_code != kind else c.double_value if kind == 1 else c.string_value
    out = []
    for col, species in enumerate(engine.col_names()):
        if (cell(col, "body", 2) or "").casefold() == body.casefold():
            far, size = cell(col, "farClip"), cell(col, "shadowSize")
            out.append(Wearer(species, thresholds([cell(col, f"lodThreshold{k}") for k in range(1, PICKED + 1)]),
                              0.0 if far is None else far,
                              (size or 0.0) > 0 and not cell(col, "shadowTextureName", 2)))
    return out


__all__ = ["FLT_MAX", "FOV_Y", "LINES", "PICKED", "SHADOW_LOD", "Wearer", "pick", "pixel_error", "reach", "spans",
           "thresholds", "wearers"]
