"""X12, garret4's timing on a swapped body's stand-ins, and his clips
on a body with none (Step 2.67; D219, D226, D229; Step 2.89, D239).

garret4's own clips reach a swapped body only baked onto its rig
(:mod:`azurik_mod.assets.retarget`, ``characters/<body>/g4/<clip>``),
since a clip binds to a body by raw index, never by name
(``docs/RE_DATA.md`` § "How a clip binds to a body").  X12
(``player_model/borrow.c``) does the rest:

- **garret4's timing** (the hook at 0xCAF6B, the clip change 0xCAD40's
  CALL of the track binder 0xCB080, when anim_change made the change,
  and the one at 0xCAEC0, where the change plays a clip again on the
  layer that already holds it, at rate 1.0 without binding it: a fall
  after a jump on the same stand-in): a slot X11 marked garret4-timed
  (D229: a body the bake doesn't map, a stand-in that isn't very
  similar) plays its own clip at the rate that ends it in garret4's
  clip length.
- **A body with no clips** (gargoylestone, tesla_tree; the hook at
  0x7E3F0, the attacks_anims loader's lookup): the bake gives it
  garret4's clips as timers (none of his bone tracks, his length and
  markers; its root rides his ``m_feet`` / D, Step 2.127),
  which X11 puts in every slot the player asks for, and each column its
  body can't resolve plays ``g4/<name>``: its moves start and end on
  garret4's times and travel his root motion, with X3's hit box.  Since
  Step 2.134a the same lookup plays garret4's attacks baked onto a
  townsperson's rig in Balanced (its columns keep their vanilla names).

X44 (``player_model/borrow_first.c``, Step 2.161b2, AZ-688) takes that
lookup's place for a body that borrows garret4's attacks and owns one of
the vanilla names (``attack_1`` and ``attack_2`` of keylord, golem,
kingkong, overlord and water_elemental, ``attack_1``-``attack_3`` of
balthazar, air_elemental and air_elemental_boss, under a picked Axion
staff or hoe): ``g4/<name>`` first, the
body's own name only where garret4's isn't baked.
"""

from __future__ import annotations

import struct
from pathlib import Path

from azurkit.tools.characters.ports import xbe_site
from azurkit.tools.characters.ports import ShimSource, TrampolinePatch, apply_trampoline_patch
from azurkit.tools.characters.ports import trampoline_symbol_va
from azurkit.tools.characters.ports import release_session
from azurkit.core.xbe import resolve_va_to_file

_REPO_ROOT = Path(__file__).resolve().parents[2]

SHIM = ShimSource(folder=Path(__file__).resolve().parent / "player_model", stem="borrow")
OBJECT = "player_model_borrow"
"""The shim object's name in the shim build dir (``<OBJECT>.o``)."""
TABLE = "_player_model_borrow"
"""The shim's table (``borrow.c``), written into each landing."""
_SLOTS = 0x52


def _call(va: int, target: int) -> bytes:
    """The 5-byte ``CALL target`` at ``va``."""
    return b"\xe8" + struct.pack("<i", target - (va + 5))


def _hook(what: str, why: str, va: int, replaced: bytes, symbol: str) -> TrampolinePatch:
    return TrampolinePatch(
        name=f"{OBJECT}_{what}", label=f"Player model borrow: {why} (X12) at VA 0x{va:X}", va=va,
        replaced_bytes=replaced, shim_object=SHIM.object_path(OBJECT, _REPO_ROOT), shim_symbol=symbol)


BIND = _hook("bind", "garret4's time for a stand-in", 0xCAF6B, _call(0xCAF6B, 0xCB080),
             "_c_player_model_borrow_bind")
"""The clip change 0xCAD40's CALL of the track binder 0xCB080."""
ANIM_CHANGE_CALL = 0x429DA
"""anim_change's (0x42910) CALL of the clip change 0xCAD40: BIND times a
garret4-timed slot only when the change returns there
(:func:`anim_change_return`)."""
ATTACK = _hook("attack", "garret4's attack clips for a clipless body", 0x7E3F0, _call(0x7E3F0, 0x4B600),
               "_c_player_model_borrow_attack")
"""The attacks_anims loader's CALL of species_clip_lookup 0x4B600."""
REUSE = _hook("reuse", "garret4's time for a clip played again", 0xCAEC0, bytes.fromhex("8a442418a804"),
              "_c_player_model_borrow_reuse")
"""The clip change 0xCAD40's ``mov al, [esp+0x18]; test al, 4``, on its
path that plays a clip again on the layer holding it (rate 1.0, no
0xCB080)."""
HOOKS = (BIND, REUSE, ATTACK)
"""X12's hooks, one landing each of ``player_model/borrow.c``."""
FIRST_SHIM = ShimSource(folder=SHIM.folder, stem="borrow_first")
FIRST_OBJECT = "player_model_borrow_first"
"""X44's object's name in the shim build dir (``<FIRST_OBJECT>.o``)."""
FIRST = TrampolinePatch(
    name=FIRST_OBJECT, label="Player model borrow: garret4's attack before the body's own (X44) at VA 0x7E3F0",
    va=0x7E3F0, replaced_bytes=_call(0x7E3F0, 0x4B600), shim_object=FIRST_SHIM.object_path(FIRST_OBJECT, _REPO_ROOT),
    shim_symbol="_c_player_model_borrow_first")
"""X44 (Step 2.161b2, AZ-688): :data:`ATTACK`'s site, ``g4/<name>`` looked up before the name."""


def needed_hooks(timed: dict[int, float], timers: bool) -> tuple[TrampolinePatch, ...]:
    """The X12 hooks a build needs: :data:`BIND` and :data:`REUSE` for
    ``timed`` slots, :data:`ATTACK` for a clipless body's ``timers`` and
    a baked farmer's borrowed attacks (``_player_weapons.Loadout.borrowing``,
    Step 2.134a)."""
    return tuple(hook for hook, need in ((BIND, timed), (REUSE, timed), (ATTACK, timers)) if need)


def install_first_shim(xbe: bytearray) -> None:
    """Install X44 (``player_model/borrow_first.c``) at :data:`FIRST` in
    ``xbe``: the player's attacks_anims columns look up ``g4/<name>``
    before ``<name>``.  :class:`ValueError` names the site when it can't
    land (D35); the shim session the apply opens is released."""
    try:
        ok = apply_trampoline_patch(xbe, FIRST, repo_root=_REPO_ROOT, shim_source=FIRST_SHIM.source_path())
    finally:
        release_session(xbe)
    if not ok:
        raise ValueError(f"the borrow-first shim at VA 0x{FIRST.va:X} didn't install (the line above says why)")


def anim_change_return(xbe: bytes) -> int:
    """Where the clip change returns to in ``xbe``'s anim_change: its
    :data:`ANIM_CHANGE_CALL` in the XBE's release, + 5."""
    return xbe_site(xbe, ANIM_CHANGE_CALL, _call(ANIM_CHANGE_CALL, 0xCAD40))[0] + 5


def borrow_table(timed: dict[int, float], back: int) -> bytes:
    """X12's table: ``back``, anim_change's return from the clip change
    (:func:`anim_change_return`), and each garret4-timed slot's garret4
    clip length (``timed``: slot -> length; 0.0 untimed)."""
    return struct.pack(f"<I{_SLOTS}f", back, *(timed.get(i, 0.0) for i in range(_SLOTS)))


def install_borrow_shim(xbe: bytearray, table: bytes, hooks: tuple[TrampolinePatch, ...]) -> None:
    """Install X12 (``player_model/borrow.c``) at each of ``hooks`` in
    ``xbe`` and write ``table`` (:func:`borrow_table`) into each landing.
    :class:`ValueError` names the site when one can't land (D35); the
    shim session each apply opens is released (it holds ``xbe``)."""
    for hook in hooks:
        try:
            ok = apply_trampoline_patch(xbe, hook, repo_root=_REPO_ROOT, shim_source=SHIM.source_path())
        finally:
            release_session(xbe)
        if not ok:
            raise ValueError(f"the borrow shim at VA 0x{hook.va:X} didn't install "
                             "(the line above says why)")
        at = resolve_va_to_file(xbe, trampoline_symbol_va(xbe, hook, TABLE, _REPO_ROOT,
                                                          shim_source=SHIM.source_path()))
        xbe[at:at + len(table)] = table


__all__ = ["ANIM_CHANGE_CALL", "ATTACK", "BIND", "FIRST", "FIRST_OBJECT", "FIRST_SHIM", "HOOKS", "OBJECT", "REUSE",
           "SHIM", "TABLE", "anim_change_return", "borrow_table", "install_borrow_shim", "install_first_shim",
           "needed_hooks"]
