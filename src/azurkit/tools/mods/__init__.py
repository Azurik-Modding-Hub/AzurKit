"""The pack engine (:mod:`.engine`) and the packs.

:data:`PACKS` holds them in their canonical order, Modkit's registry order,
which every build applies them in (AZ-024); a pack ported later takes its
place there. :func:`normalize` is the one check of the packs a recipe names
and their slider values, for every host (WEB §4.2), and :func:`missing`
names a pack a build applies without one it requires (``Pack.requires``);
:func:`vanilla` reads a site slider's vanilla value from the player's own
XBE (D42, Q174)."""

from collections.abc import Mapping

from azurkit.core import facts
from azurkit.core.gate import Release
from azurkit.tools.mods.engine import CATEGORIES, Pack, PackError, ParametricPatch, XbrParametricEdit, f32, plan
from azurkit.tools.mods.packs import (air_shield_flaps, enemy_damage, enemy_scaling, fps_unlock, player_max_hp,
                                      player_physics, qol_alloc_race, qol_memory, qol_photo_mode, qol_pickup_anims,
                                      qol_popups, qol_save_warp, qol_skip_logo)

PACKS: dict[str, Pack] = {pack.name: pack for pack in (
    fps_unlock.PACK, player_physics.PACK, qol_popups.GEM_POPUPS, qol_popups.OTHER_POPUPS, qol_pickup_anims.PACK,
    qol_skip_logo.PACK, player_max_hp.PACK, air_shield_flaps.PACK, enemy_damage.PACK, enemy_scaling.PACK,
    qol_save_warp.PACK, qol_photo_mode.PACK, qol_memory.BUDGET_PACK, qol_memory.UPPER64_PACK,
    qol_memory.UPPER64_GPU_PACK, qol_memory.UPPER256_PACK, qol_alloc_race.PACK)}


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


def missing(packs: object) -> list[str]:
    """Each pack of ``packs`` (names) that requires one ``packs`` leaves
    out, and what: ``"pack 'x' needs 'y' in the same build"`` (Modkit's
    ``Feature.requires``; ``qol_memory_upper64_gpu`` places its runs in
    ``qol_memory_upper64``'s heap)."""
    return [f"pack {name!r} needs {', '.join(map(repr, lost))} in the same build"
            for name, pack in PACKS.items() if name in packs and (lost := [r for r in pack.requires if r not in packs])]


def vanilla(release: Release, xbe: bytes) -> dict[str, dict[str, float]]:
    """``{pack: {slider: value}}``: each slider at a site of ``release``'s
    XBE (whose catalog's vanilla is ``None``) at the value ``xbe``, the
    player's vanilla one, holds there; a float32's to its 7 significant
    digits. ``LookupError`` or ``ValueError`` names a site it can't read."""
    known, out = facts.of(release), {}
    for pack in PACKS.values():
        for s in pack.sliders():
            if release.name in pack.releases and isinstance(s, ParametricPatch) and not s.virtual and s.on(
                    release.name):
                site = known.site(s.own(known))
                at = known.offset(site.va, site.size)
                value = s.decode(xbe[at:at + site.size])
                out.setdefault(pack.name, {})[s.name] = float(f"{value:.7g}") if s.encode is f32 else value
    return out


__all__ = ["CATEGORIES", "PACKS", "Pack", "PackError", "ParametricPatch", "XbrParametricEdit", "missing", "normalize",
           "plan", "vanilla"]
