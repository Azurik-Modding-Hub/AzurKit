"""The pack engine (:mod:`.engine`) and the packs.

:data:`PACKS` holds them in their canonical order, Modkit's registry order,
which every build applies them in (AZ-024); a pack ported later takes its
place there. :func:`normalize` is the one check of the packs a recipe names
and their slider values, for every host (WEB §4.2)."""

from collections.abc import Mapping

from azurkit.tools.mods.engine import Pack, PackError, ParametricPatch, plan
from azurkit.tools.mods.packs import fps_unlock, qol_alloc_race, qol_pickup_anims, qol_popups

PACKS: dict[str, Pack] = {pack.name: pack for pack in (
    fps_unlock.PACK, qol_popups.GEM_POPUPS, qol_popups.OTHER_POPUPS, qol_pickup_anims.PACK, qol_alloc_race.PACK)}


def normalize(packs: object) -> dict[str, dict[str, float | int]]:
    """``packs`` (``{pack: {slider: value}}``) as a build takes it: the
    packs in their canonical order, each value as its slider takes it (any
    finite number, D23; a whole one its encoding holds where it takes only
    those, D45), and a value equal to its slider's default dropped, since
    the pack builds the same without it. Nothing is clamped. ``ValueError``
    names every pack no pack has, every parameter a pack doesn't take and
    every value refused, in one message (D35)."""
    if not isinstance(packs, Mapping) or not all(isinstance(v, Mapping) for v in packs.values()):
        raise ValueError("recipe: packs is {pack: {parameter: value}}")
    out, failed = {}, []
    if unknown := sorted(set(packs) - set(PACKS), key=str):
        failed.append(f"recipe: no pack {', '.join(map(repr, unknown))} (the packs: {', '.join(PACKS)})")
    for name, pack in PACKS.items():
        if name in packs:
            try:
                values = pack.values(packs[name])
            except PackError as exc:
                failed.append(str(exc))
                continue
            out[name] = {s.name: values[s.name] for s in pack.sliders()
                         if s.name in packs[name] and values[s.name] != s.default}
    if failed:
        raise ValueError("; ".join(failed))
    return out


__all__ = ["PACKS", "Pack", "PackError", "ParametricPatch", "normalize", "plan"]
