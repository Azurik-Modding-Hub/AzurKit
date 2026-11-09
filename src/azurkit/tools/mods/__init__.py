"""The pack engine (:mod:`.engine`) and the packs.

:data:`PACKS` holds them in their canonical order, Modkit's registry order,
which every build applies them in (AZ-024); a pack ported later takes its
place there. :func:`normalize` is the one check of the packs a recipe names
and their slider values, for every host (WEB §4.2), :func:`salvage` keeps
what it takes of a remembered setup's and names the rest (D915), and
:func:`missing` names a pack a build applies without one it requires
(``Pack.requires``), which :func:`settle` turns on or off with a line;
:func:`vanilla` reads a site slider's vanilla value from the player's own
XBE (D42, Q174)."""

from collections.abc import Iterable, Mapping

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


#: Modkit's retired pack names (D43): each refused by name, saying what replaced it (:func:`unknown`).
RETIRED = {"qol_skip_save_signature": "azurkit save edit signs an edited save again with your own BIOS files",
           **{f"rand_{pool}": f"the randomizer's settings choose what is shuffled ({how})" for pool, how in (
               ("major", "a settings file's excluded categories keep fragments and powers vanilla"),
               ("keys", "keys stay vanilla"),
               ("gems", "a settings file's excluded categories keep gems and obsidians vanilla"),
               ("barriers", "barriers stay vanilla"), ("connections", "exits stay vanilla"))}}


def unknown(names: Iterable[str]) -> str:
    """Why no pack has any of ``names``: each named, a retired one with what
    replaced it (:data:`RETIRED`), then the packs."""
    named = [f"{name!r} (retired: {RETIRED[name]})" if name in RETIRED else repr(name) for name in names]
    return f"no pack {', '.join(named)} (the packs: {', '.join(PACKS)})"


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
    if lost := sorted(set(packs) - set(PACKS), key=str):
        failed.append(f"recipe: {unknown(lost)}")
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


def salvage(packs: object) -> tuple[dict[str, dict[str, float | int]], list[str]]:
    """``packs`` (``{pack: {slider: value}}``) as :func:`normalize` gives
    them, less what it would refuse, and each part left out, named: a pack
    no pack has, a parameter its pack doesn't take, a value its slider
    refuses (a remembered setup's, D915: dropped by name, never applied)."""
    if not isinstance(packs, Mapping):
        return {}, ["the settings (not {pack: {setting: value}})"]
    kept, dropped = {}, []
    for name, params in packs.items():
        if name not in PACKS:
            dropped.append(f"{name} (no such pack)")
        elif not isinstance(params, Mapping):
            dropped.append(f"{name}'s settings (not {{setting: value}})")
        else:
            sliders, kept[name] = {s.name: s for s in PACKS[name].sliders()}, {}
            for key, value in params.items():
                try:
                    if key not in sliders:
                        raise ValueError(f"{key} (no such setting)")
                    sliders[key].value(value)
                except ValueError as exc:   # the slider's message starts with its name
                    dropped.append(f"{name}.{exc}")
                else:
                    kept[name][key] = value
    return normalize(kept), dropped


def missing(packs: object) -> list[str]:
    """Each pack of ``packs`` (names) that requires one ``packs`` leaves
    out, and what: ``"pack 'x' needs 'y' in the same build"`` (Modkit's
    ``Feature.requires``; ``qol_memory_upper64_gpu`` places its runs in
    ``qol_memory_upper64``'s heap)."""
    return [f"pack {name!r} needs {', '.join(map(repr, lost))} in the same build"
            for name, pack in PACKS.items() if name in packs and (lost := [r for r in pack.requires if r not in packs])]


def settle(on: Iterable[str], ticked: Iterable[str] = (), unticked: Iterable[str] = ()) -> tuple[list[str], list[str]]:
    """The one rule of what a person's choice moves (a host's ``Pack.requires``;
    the page's ``linked`` walks the same): the packs ``on`` (known names) with
    ``ticked`` and each pack it requires, less ``unticked`` and each pack that
    requires one, in their canonical order, and a line for each pack moved
    that wasn't named. ``ValueError`` (:func:`missing`'s) when a pack ticked
    needs one unticked: only the person can settle that."""
    names, ticked, unticked, lines = {*on, *ticked}, list(ticked), set(unticked), []
    held, todo = set(ticked), list(ticked)
    while todo:
        name = todo.pop()
        for need in PACKS[name].requires:
            if need not in held:
                held.add(need)
                todo.append(need)
            if need not in names:
                names.add(need)
                lines.append(f"Also ticked {need}: {name} {PACKS[name].requires_why}.")
    if lost := missing(held - unticked):
        raise ValueError("; ".join(lost))
    names -= unticked
    todo = list(unticked)
    while todo:
        name = todo.pop()
        for other, pack in PACKS.items():
            if name in pack.requires and other in names:
                names.remove(other)
                todo.append(other)
                lines.append(f"Also unticked {other}: it {pack.requires_why}.")
    return [name for name in PACKS if name in names], lines


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
           "plan", "salvage", "settle", "vanilla"]
