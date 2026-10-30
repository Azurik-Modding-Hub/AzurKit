"""X11, the player-model swap's base clip slots (Step 2.66; D219, D226,
D229).

A species' clip slots 0-0x51 are the XBE's base clip table (0x1A9F78:
``idle``, ``walk``, ``jump``, ``superjump``, ``die``, ``swim_idle``,
``victory_1``, ...), resolved by name against its body when the species
loads (0x4B8E0, ``docs/RE_XBE.md`` § "Every clip the player asks for");
no ``config.xbr`` cell reaches them, and only garret4's body has most of
the 57 the player asks for.  An empty slot plays nothing, so a swapped
body kept the clip already playing, or showed its bind pose.  For a body
with clips the swap hooks the species load's CALL of
``species_clip_lookup`` (0x4B600) at 0x4B948 with
``player_model/slots.c``, which looks each of the player's slots up under
the clip name a table it carries gives first (:func:`slot_fills`, written
by :func:`install_slots_shim` after the shim lands), then under its own
name (Step 2.131: a slot the body fills by name is named only by W22,
``_player_character.quiet_fills``, and, on a baked body under garret4's
rule, the jump slot 15, :data:`JUMPS`: Step 2.194a, D760).

The rule (``--player-character-anims``, :data:`ANIMS`):

- **garret4** (the default, D226 and D229): a slot whose semantic chain
  (:data:`CHAINS`, Step 2.60's step 1) names a clip the body has plays
  that very similar clip in its own time; any other slot garret4's body
  has plays the body's closest own clip (:func:`closest_own`, Step 2.60's
  steps 2-3), marked garret4-timed with garret4's clip length, which
  Step 2.67's X12 gives it; a slot garret4 lacks stays empty, as his does.
- **own**: every slot plays the closest own clip in its own time.

On a body whose clips the build bakes (Step 2.87,
:mod:`azurik_mod.assets.retarget`; a body with no clips too, as timers,
Step 2.89) garret4's rule gives every slot without a very similar own
clip, every aligned one (:data:`LEFT_EMPTY`) and the jump family
(:data:`JUMPS`, even where the body has a clip of the slot's name: Step
2.194a, D760) garret4's baked clip, ``g4/<clip>``.  Otherwise the slots
X9 serves (:data:`X9`: the ladder, hoist and step moves and the climb
loops, whose stand-in it plays when a slot is -1) stay empty, and so do
the hard landing and overhead hang (X9 times their stand-in too, Step
2.66b), victories and use (:data:`LEFT_EMPTY`: X9 plays their stand-in
in garret4's time since Step 2.103, AZ-444, where an empty slot dropped
the move; the victories only where :mod:`~azurik_mod.patches._player_victory` gives none since
Step 2.121, D299, D300); a hit reaction's slot
(:data:`HIT`) takes only a very
similar clip (another ``ouch``): X7 plays the rest, its ``ouch_1``, else
``idle``, else the roll's clip, in garret4's 0.4 s.  A slot whose garret4 clip deals no damage
never takes one of the body's damage clips: the damage pass (0x43A80)
reads the body's ``m_damage`` marker in any state.

In Balanced (mode own, Step 2.134a, D331) the base idle slot 1 of a
body without its own ``idle`` plays its calmest looping ``idle_N``
(:func:`calm_idle`) where the chain's pick moves at least twice as
fast: the game's fidget pick (0x309A0) still plays its other idles now
and then.

A variant's ``idles`` (Step 2.168, D553) name the clips of the idle
slots 1-7 (:data:`IDLE_SLOTS`), which X11 plays by name, and X45
(``player_model/idle_pick.c``, :func:`install_idle_pick`) times its
fidgets: the base between them for a wait drawn from the recipe's
range, never one fidget twice in a row.  Its ``slots`` (Step 2.171,
D487, D534, D535) name the clips of its gait and victories, since
Step 2.164c (D768) of its jump family (:data:`RECIPE_SLOTS`), which X11
plays by name too, in place of :data:`JUMPS`' garret4 ones, and since
Step 2.193 of its landing.
"""

from __future__ import annotations

import math
import re
import struct
from pathlib import Path

from azurkit.tools.characters.characters import Body
from azurkit.tools.characters.retarget import BAKED_DIR, Clip, Rig, named_clip, origins
from azurkit.tools.characters.ports import xbe_site
from azurkit.tools.characters.ports import ShimSource, TrampolinePatch, apply_trampoline_patch
from azurkit.tools.characters.ports import trampoline_symbol_va
from azurkit.tools.characters.ports import release_session
from azurkit.tools.characters.ports import BytesParam
from azurkit.core.xbe import resolve_va_to_file

_REPO_ROOT = Path(__file__).resolve().parents[2]

BASE_CLIPS = (
    "initial", "idle", "idle_1", "idle_2", "idle_3", "idle_4", "idle_5", "idle_6", "walk", "run",
    "stalk", "touchdown", "slide", "walk_backwards", "run_backwards", "jump", "jump_standing",
    "superjump", "fall", "fall_attack", "climb_drop", "fall_big", "hover", "die", "die_1", "die_2",
    "die_3", "drowning", "splat", "run_begin", "run_end", "sidestep_left", "sidestep_right",
    "disappear", "shield", "ball", "mutate", "ouch_1", "ouch_2", "ouch_3", "ouch_1r", "ouch_1l",
    "ouch_1b", "attack", "attack_1", "attack_2", "attack_3", "attack_4", "attack_5", "attack_6",
    "fly", "fly_forward", "dive", "step_up", "step_down", "climb_idle", "climb_up", "climb_down",
    "climb_left", "climb_right", "climb_start", "climb_stop", "climb_down_edge", "climb_up_edge",
    "climb_from_jump", "hoist", "hoist_waist", "hang", "hang_start", "hang_stop", "swim_idle",
    "swim_idle_up", "swim_idle_down", "swim_1", "swim_2", "victory_1", "victory_2", "victory_3",
    "victory_4", "victory_5", "victory_6", "use",
)
"""The XBE's base clip table (0x1A9F78), slot by slot: the names the
species load resolves into slots 0-0x51."""

ASKED = frozenset((*range(1, 10), *range(11, 28), *range(37, 43), 53, *range(55, 61),
                   *range(62, 69), *range(70, 73), *range(74, 82)))
"""The 57 base slots the player's code asks for (``docs/RE_XBE.md``
§ "Every clip the player asks for")."""

X9 = frozenset((53, *range(55, 61), *range(62, 67)))
"""X9's slots (``player_model/climb.c``, Step 2.63: the ladder, hoist and
step moves 53, 60, 62-66 through the move-state setter and the climb
loops 55-59, each playing its stand-in when the slot is -1), which X11
never fills on a body with clips."""
LEFT_EMPTY = X9 | {11, 68, *range(75, 82)}
"""Slots X11 fills only with garret4's baked clips (B): X9's,
and the hard landing 11 and overhead hang 68 (X9 plays their stand-in
in garret4's time, Step 2.66b), victories 75-80 and use 81, aligned moves
(0x42430, state 0x100) X9 plays its stand-in for in garret4's time with
his hit immunity (Step 2.103, AZ-444; before, an empty slot dropped the
move at 0x888C2): in the slot, a stand-in would hold the player for its
own length (an idle of seconds after each kill).  The victories have a
second filler since Step 2.121 (D299, D300):
:func:`~azurik_mod.patches._player_victory.victory_fills`, on a body
the bake doesn't serve."""

FLOATS = frozenset((12, 15, 16, 17, 18, 20, 21, 22, 70, 71, 72, 74))
"""The slide, the jumps and falls, the climb drop, the hover and the
swims: the slots a baked flyer plays on its own clips in Balanced
(Step 2.134a, D334, D335; ``_player_character.floats``), garret4's
baked ones putting it on the floor and kicking (the fire elemental's
lowest bone -0.40..+0.05 model units in them, 0.21-0.69 in its own).
None of them is X9's or :data:`LEFT_EMPTY`'s: the aligned moves stay
baked, his markers placing them."""

JUMPS = frozenset(BASE_CLIPS.index(n) for n in ("jump", "jump_standing", "superjump", "climb_drop"))
"""The jump family (15-17, and the climb drop 20, whose chain's first is
``jump``): on a body the bake serves, under garret4's rule, garret4's
baked clips even where the body has its own (Step 2.194a, D760, AZ-756:
the five children's own ``jump``, a run-like hop, played in all four in
place of his)."""

HIT = frozenset(range(37, 43))
"""The hit reactions (``ouch_1``, ``ouch_2``, ``ouch_3``, ``ouch_1r``,
``ouch_1l``, ``ouch_1b``), which X11 fills only from their chain: X7
(``player_model/hit_reaction.c``) plays its fallback for an empty one."""

ANIMS = ("garret4", "own")
"""``--player-character-anims``: garret4's rule (D226, D229; the
default) or the closest own clip everywhere."""

_IDLES = ("idle", "idle_1", "idle_2", "idle_3", "idle_4")
CHAINS: dict[str, tuple[str, ...]] = {
    "initial": _IDLES, "idle": _IDLES[1:], "idle_1": ("idle_2", "idle_3", "idle_4", "idle"),
    "idle_2": ("idle_1", "idle_3", "idle_4", "idle"), "idle_3": ("idle_1", "idle_2", "idle_4", "idle"),
    "idle_4": ("idle_1", "idle_2", "idle_3", "idle"), "idle_5": _IDLES[::-1], "idle_6": _IDLES[::-1],
    "walk": ("stalk", "run", "walk_backwards"), "run": ("walk", "stalk", "run_begin"),
    "walk_backwards": ("walk", "run_backwards", "run"), "run_backwards": ("run", "walk_backwards", "walk"),
    "touchdown": ("step_down", "splat"), "slide": (),
    "jump": ("jump_standing", "superjump"), "jump_standing": ("jump", "superjump"),
    "superjump": ("jump", "jump_standing"), "fall": ("fall_big",), "fall_big": ("fall",),
    "fall_attack": ("attack_1", "attack"), "climb_drop": ("jump", "fall"), "hover": ("fly",),
    "fly": ("hover", "fly_forward"),
    "die": ("die_1", "die_2", "die_3"), "die_1": ("die", "die_2", "die_3"),
    "die_2": ("die", "die_1", "die_3"), "die_3": ("die", "die_1", "die_2"),
    "drowning": ("die", "die_1", "die_2", "die_3"),
    "ouch_1": ("ouch_2", "ouch_3"), "ouch_2": ("ouch_1", "ouch_3"), "ouch_3": ("ouch_2", "ouch_1"),
    "ouch_1r": ("ouch_1",), "ouch_1l": ("ouch_1",), "ouch_1b": ("ouch_1",),
    "step_up": ("walk", "run"), "climb_idle": ("hang",), "climb_up": ("climb_down",),
    "climb_down": ("climb_up",), "climb_left": ("climb_right",), "climb_right": ("climb_left",),
    "climb_start": ("climb_idle", "climb_from_jump"), "climb_down_edge": ("climb_down",),
    "climb_up_edge": ("hoist", "climb_up"), "climb_from_jump": ("climb_start",),
    "hoist": ("hoist_waist", "climb_up_edge"), "hoist_waist": ("hoist",),
    "hang": ("climb_idle", "hover"), "hang_start": ("hang", "climb_from_jump"),
    "swim_idle": ("swim_idle_up", "swim_idle_down", "hover"), "swim_idle_up": ("swim_idle", "hover"),
    "swim_idle_down": ("swim_idle", "hover"), "swim_2": ("swim_1", "fly_forward"),
    "swim_1": ("swim_2", "fly_forward"),
}
"""Each base slot's very similar clips, nearest first (Step 2.60's step
1; D226: the model's own clip only when it is very similar)."""

_CLASS = {
    **dict.fromkeys(("walk", "run", "walk_backwards", "run_backwards", "slide", "step_up", "climb_up",
                     "climb_down", "climb_left", "climb_right", "swim_1", "swim_2"), "move"),
    **dict.fromkeys(("jump", "jump_standing", "superjump", "fall", "fall_big", "climb_drop", "hover", "fly",
                     "climb_start", "climb_down_edge", "climb_up_edge", "climb_from_jump", "hoist",
                     "hoist_waist", "hang_start", "touchdown"), "air"),
    **dict.fromkeys(("die", "die_1", "die_2", "die_3", "drowning"), "die"),
    **dict.fromkeys(("ouch_1", "ouch_2", "ouch_3", "ouch_1r", "ouch_1l", "ouch_1b"), "hurt"),
    "fall_attack": "act",
}
"""A slot's class (every other slot holds: ``hold``)."""
_PATTERN = {
    "hold": ("idle", "stand", "listen", "look", "breath", "wait", "float", "glide", "lean", "talk"),
    "move": ("walk", "run", "move", "glide", "fly", "swim", "crawl", "hop", "slither"),
    "air": ("jump", "leap", "fall", "glide", "fly", "hop", "hover"),
    "die": ("die", "death", "dead", "collapse"),
    "hurt": ("ouch", "hit", "hurt", "pain"),
    "act": ("laugh", "bow", "taunt", "attack", "cast"),
}
"""Each class's name patterns for an extra clip, earlier first."""
_LADDER = {
    "hold": ("idle", "idle_1", "idle_2", "idle_3", "hover", "fly", "swim_idle", "~hold", "walk", "run",
             "fly_forward"),
    "move": ("run", "walk", "fly_forward", "fly", "swim_1", "stalk", "~move", "hover", "idle", "idle_1",
             "idle_2", "~hold"),
    "air": ("jump", "fall", "hover", "fly", "~air", "idle", "idle_1", "idle_2", "~hold", "walk", "run"),
    "die": ("die", "die_1", "ouch_3", "ouch_2", "ouch_1", "~die", "~hurt", "idle", "idle_1", "~hold",
            "walk"),
    "hurt": ("ouch_1", "ouch_2", "ouch_3", "~hurt", "idle", "idle_1", "~hold", "walk"),
    "act": ("~act", "attack_1", "attack", "idle", "idle_1", "~hold", "walk"),
}
"""Each class's ladder after the chain and, but for ``hold``, the class's
own patterns (Step 2.60's steps 2-3): a base name, or ``~class``, the
first extra clip matching that class's patterns."""
_NOT_EXTRA = re.compile(r"attack(_\d)?", re.IGNORECASE)
_NEVER = re.compile(r"^reference$|telltale", re.IGNORECASE)
"""Clips never picked: a rig's bind pose, a boss's warning flash."""


def closest_own(slot: str, body: Body, *, similar: bool = False, harmless: bool = False,
                calm: str | None = None) -> str | None:
    """The body's own clip for the base slot ``slot`` it lacks (Step
    2.60's rule): the first of the slot's :data:`CHAINS` it has; unless
    ``similar``, else an extra clip (a name that is no chain's slot or
    ``attack``/``attack_N``) matching the slot's class, else the class
    ladder, else its first clip (``None`` for a body with none).  With
    ``harmless`` none of the body's damage clips is picked; with ``calm``
    (:func:`calm_idle`) the ladder's ``idle`` step on a body without one
    plays that (Step 2.134a: the fire elemental's jumps on its idle_2,
    not its busy idle_1)."""
    clips = [c for c in body.clips if not _NEVER.search(c) and not (harmless and c in body.damage_clips)]
    have = {c.casefold(): c for c in clips}
    for name in CHAINS.get(slot, ()):
        if name in have:
            return have[name]
    if similar:
        return None
    extras = sorted(c for c in clips if c.casefold() not in CHAINS and not _NOT_EXTRA.fullmatch(c))
    cls = _CLASS.get(slot, "hold")
    for step in _LADDER[cls] if cls == "hold" else ("~" + cls, *_LADDER[cls]):
        if step.startswith("~"):
            hit = next((c for p in _PATTERN[step[1:]] for c in extras if p in c.casefold()), None)
            if hit:
                return hit
        elif step in have:
            return have[step]
        elif step == "idle" and calm is not None:
            return calm
    return clips[0] if clips else None


CALM_SEAM = 0.05
"""How far (model units, the mean over its bones) an idle's last pose may
sit from its first for it to loop (Step 2.134a, D331)."""
CALM_MIN = 0.5
"""The shortest idle (s) that can stand as the base: a shorter one is a
held pose, not a loop."""
CALM_RATIO = 2.0
"""How many times as fast the chain's idle must move as the calmest
looping one before the calm one takes the base slot."""
CALM_HZ = 30.0
"""The rate the bone motion is sampled at (the game's tick)."""
_IDLE_N = re.compile(r"idle_\d")


def _motion(rig: Rig, clip: Clip) -> tuple[float, float]:
    """``clip``'s mean bone-origin speed on ``rig`` (model units/s, sampled
    at :data:`CALM_HZ`) and its seam (the mean distance of each bone's
    origin at its end from its start)."""
    n = max(2, round(clip.length * CALM_HZ) + 1)
    at = [origins(rig, clip, clip.length * i / (n - 1)) for i in range(n)]
    bones = len(rig.bones)
    moved = sum(math.dist(a, b) for p, q in zip(at, at[1:]) for a, b in zip(p, q))
    return (moved / (bones * clip.length) if clip.length > 0 else 0.0,
            sum(math.dist(a, b) for a, b in zip(at[0], at[-1])) / bones)


def calm_idle(characters_xbr: bytes, body: Body) -> str | None:
    """The calmest looping ``idle_N`` of ``body`` for its base idle slot 1
    (Step 2.134a, D331: "the idle animations should not be spammed"), or
    ``None`` to keep the chain's pick: only on a body without its own
    ``idle`` and with two ``idle_N`` or more, and only when the chain's
    pick (:func:`closest_own`) moves at least :data:`CALM_RATIO` times as
    fast as the calmest one that loops (:data:`CALM_SEAM`, at least
    :data:`CALM_MIN` long; :func:`_motion`).  The other idles still play
    as fidgets on garret4's schedule (0x85C60: past 10 s of standing,
    0x309A0's even pick among the filled run of slots from 1, a pick of 1
    made again on the next tick; a fidget 10 s less its seed U(0, 6)
    after the last, 7-10 s after walking, not before the base's first
    wrap: 4-10 s on booblord's 4 s base, 8.0-10.1 s on garret4's, sitting
    2.190).  Of the bodies a player wears only the fire
    elemental's base changes (idle_1 at 0.649/s for idle_2 at 0.067/s);
    a body with its own ``idle`` is outside the rule (magmar's sunk idle_1
    and the shards' 0.067 s pose would "win" it)."""
    have = {c.casefold(): c for c in body.clips}
    idles = [c for c in body.clips if _IDLE_N.fullmatch(c.casefold())]
    pick = closest_own("idle", body, similar=True)
    if "idle" in have or len(idles) < 2 or pick not in idles:
        return None
    rig = Rig.read(characters_xbr, body.name)
    motion = {c: _motion(rig, named_clip(characters_xbr, body.name, c)) for c in idles}
    loops = [c for c in idles if motion[c][1] < CALM_SEAM and body.length(c) >= CALM_MIN]
    calm = min(loops, key=lambda c: motion[c][0], default=None)
    if calm is None or motion[pick][0] < CALM_RATIO * motion[calm][0]:
        return None
    return calm


def slot_fills(body: Body, garret4: Body, anims: str = "garret4", *,
               baked: bool = False, calm: str | None = None, floats: bool = False) -> dict[int, tuple[str, float]]:
    """``{slot: (the clip, garret4's length or 0.0)}`` for each asked slot
    ``body`` leaves empty and X11 fills under ``anims`` (:data:`ANIMS`,
    the rule above); a length above 0 marks a garret4-timed stand-in
    (D229).  A slot whose garret4 clip switches no damage marker on takes
    none of the body's clips that do.  A ``baked`` body (Step 2.87,
    :mod:`azurik_mod.assets.retarget`: garret4's clips baked onto its rig
    under ``g4/``; one with no clips takes them as timers, Step 2.89)
    takes garret4's baked clip (``g4/`` + its name) in every asked slot he
    has where it has no very similar own clip, the hit reactions
    included, in every slot of :data:`LEFT_EMPTY` even where it has
    one (an aligned move lasts its clip), and in every slot of
    :data:`JUMPS` even where it has a clip of the slot's own name (Step
    2.194a, D760: the children jump as garret4 does): it plays in
    garret4's length with his markers, so nothing times it.  ``calm``
    (:func:`calm_idle`, Balanced only) is the base idle slot 1's clip,
    untimed, either way,
    and the ladders' ``idle`` step (:func:`closest_own`).  A ``baked``
    body that ``floats`` (a flyer in Balanced, Step 2.134a) fills each
    slot of :data:`FLOATS` as an unbaked one does: its own clips, in
    garret4's time where not very similar."""
    if anims not in ANIMS:
        raise ValueError(f"--player-character-anims {anims!r}: not one of {', '.join(ANIMS)}")
    have = {c.casefold() for c in body.clips}
    g4 = {c.casefold(): c for c in garret4.clips}
    g4_damage = {c.casefold() for c in garret4.damage_clips}
    out = {1: (calm, 0.0)} if calm is not None and BASE_CLIPS[1] not in have else {}

    def own(name: str, slot: int) -> tuple[str | None, float]:
        """The rule off the bake: a very similar clip untimed, else the closest garret4-timed."""
        harmless = name not in g4_damage
        pick, length = closest_own(name, body, similar=True, harmless=harmless), 0.0
        if pick is None and slot not in HIT and (anims == "own" or name in g4):
            pick = closest_own(name, body, harmless=harmless, calm=calm)
            if anims == "garret4":
                length = garret4.length(g4[name])
        return pick, length
    on_bake = baked and anims == "garret4"
    for slot in sorted((ASKED if on_bake else ASKED - LEFT_EMPTY) - set(out)):
        name = BASE_CLIPS[slot]
        mine = not on_bake or floats and slot in FLOATS   # the rule off the bake
        if name in have and (mine or slot not in JUMPS):
            continue
        if mine:
            pick, length = own(name, slot)
        else:
            pick, length = (None if slot in LEFT_EMPTY | JUMPS
                            else closest_own(name, body, similar=True, harmless=name not in g4_damage)), 0.0
            if pick is None and name in g4:
                pick = BAKED_DIR + g4[name]
        if pick is not None:
            out[slot] = (pick, length)
    return out


SHIM = ShimSource(folder=Path(__file__).resolve().parent / "player_model", stem="slots")
OBJECT = "player_model_slots"
"""The shim object's name in the shim build dir (``<OBJECT>.o``)."""
HOOK_VA = 0x4B948
"""The species load's (0x4B8E0) CALL of species_clip_lookup (0x4B600)."""
HOOK = TrampolinePatch(
    name=OBJECT,
    label=f"Player model slots: own clips for empty base slots (X11) at VA 0x{HOOK_VA:X}",
    va=HOOK_VA,
    replaced_bytes=bytes.fromhex("e8b3fcffff"),    # CALL 0x4B600
    shim_object=SHIM.object_path(OBJECT, _REPO_ROOT),
    shim_symbol="_c_player_model_slots",
)
TABLE = "_player_model_slots"
"""The shim's slot table (``slots.c``): 0x52 ``u16`` name offsets + 1
(0: none), 0x52 ``f32`` garret4 lengths, then the names."""
_SLOTS, _NAMES = 0x52, 2048


def slot_table(fills: dict[int, tuple[str, float]]) -> bytes:
    """``fills`` (:func:`slot_fills`) as the shim's table; each name once,
    NUL-terminated.  :class:`ValueError` when the names don't fit."""
    names, at = bytearray(), {}
    for clip, _ in fills.values():
        if clip not in at:
            at[clip] = len(names)
            names += clip.encode("ascii") + b"\0"
    if len(names) > _NAMES:
        raise ValueError(f"X11's slot table holds {_NAMES} name bytes, not {len(names)}")
    offsets = [at[fills[i][0]] + 1 if i in fills else 0 for i in range(_SLOTS)]
    lengths = [fills[i][1] if i in fills else 0.0 for i in range(_SLOTS)]
    return (struct.pack(f"<{_SLOTS}H{_SLOTS}f", *offsets, *lengths)
            + bytes(names).ljust(_NAMES, b"\0"))


def install_slots_shim(xbe: bytearray, fills: dict[int, tuple[str, float]]) -> None:
    """Install X11 (``player_model/slots.c``) at VA 0x4B948 in ``xbe`` and
    write ``fills``' table into it: when the player's species loads, each
    slot ``fills`` names is looked up under its clip's name, then (none
    found) under its own.
    :class:`ValueError` names the site when it can't (D35: the build
    writes no ISO); the shim session the apply opens is released here
    (it holds ``xbe``)."""
    table = slot_table(fills)
    try:
        ok = apply_trampoline_patch(xbe, HOOK, repo_root=_REPO_ROOT,
                                    shim_source=SHIM.source_path())
    finally:
        release_session(xbe)
    if not ok:
        raise ValueError(f"the slot shim at VA 0x{HOOK_VA:X} didn't install "
                         "(the line above says why)")
    at = resolve_va_to_file(xbe, trampoline_symbol_va(xbe, HOOK, TABLE, _REPO_ROOT,
                                                      shim_source=SHIM.source_path()))
    xbe[at:at + len(table)] = table


# --- X45: a variant's idles, a fidget after a drawn wait, never one twice (Step 2.168, D553) ---
IDLE_SLOTS = BASE_CLIPS[1:8]
"""The idle slots 1-7 a recipe's ``idles`` names (``idle`` the base,
``idle_1``-``idle_6`` the game's fidget slots 2-7): slot 1 loops while the
player stands, slots 2-7 play once; the spawn plays slot 2 (critter_init,
0x40CA9), so a recipe that gives slot 2 its base opens no level on a
fidget."""
IDLE_WAIT = (10.0, 10.0)
"""``idles.wait``'s default (s of standing): the game's own rhythm
(Step 2.190, the owner in X.79: "Like Garret's"): the first fidget after
10 s of standing, then one 10 s less the fidget's seed U(0, 6) after the
last ends, not before the base's first wrap: 4-10 s on booblord's 4 s
base, 8.0-10.1 s on garret4's (sitting 2.190); Step 2.168's 21-30 s
went."""
IDLE_SHIM = ShimSource(folder=SHIM.folder, stem="idle_pick")
IDLE_OBJECT = "player_model_idle_pick"
"""Its object's name: ``player_model_idle_pick.o`` in the shim build dir."""
IDLE_HOOK_VA = 0x85CD7
"""The standing picker's (0x85C60) one CALL of the fidget pick (0x309A0),
which X45 replaces (Europe 0x85C87)."""
IDLE_TIMER_VA = 0x85CAA
IDLE_TIMER_LOAD = bytes.fromhex("d805") + struct.pack("<I", 0x38DC50)
"""``fadd dword ptr [timer]`` (USA's bytes): the build reads the standing
timer's address (USA 0x38DC50, Europe 0x38FBF8) from this load in its own
image."""
IDLE_TABLE = BytesParam(name="idle_pick", symbol="_player_model_idle_pick", size=16,
                        label="Player model idles: the fidgets and the wait (X45)")
IDLE_HOOK = TrampolinePatch(
    name=IDLE_OBJECT,
    label=f"Player model idles: a fidget after a drawn wait, never one twice (X45) at VA 0x{IDLE_HOOK_VA:X}",
    va=IDLE_HOOK_VA,
    replaced_bytes=b"\xe8" + struct.pack("<i", 0x309A0 - (IDLE_HOOK_VA + 5)),    # CALL 0x309A0
    shim_object=IDLE_SHIM.object_path(IDLE_OBJECT, _REPO_ROOT),
    shim_symbol="_c_player_model_idle_pick",
    bytes_params=(IDLE_TABLE,),
)
IDLE_WORDS = ("_player_model_idle_wait", "_player_model_idle_drawn", "_player_model_idle_last",
              "_player_model_idle_seed")
"""The words X45 keeps (its .bss), for L2 and the sitting."""


def idle_fills(idles: dict[str, str]) -> dict[int, tuple[str, float]]:
    """X11's fills for a recipe's ``idles`` ({slot name: the clip's name
    under its body}), each untimed."""
    return {IDLE_SLOTS.index(name) + 1: (clip, 0.0) for name, clip in idles.items()}


def fidget_mask(idles: dict[str, str]) -> int:
    """The fidget slots of ``idles`` (bit k: slot k, 2-7), each naming
    another clip than its base's."""
    base = idles.get(IDLE_SLOTS[0])
    return sum(1 << (k + 1) for k, name in enumerate(IDLE_SLOTS) if k and name in idles and idles[name] != base)


RECIPE_SLOTS = ("walk", "run", "walk_backwards", "run_backwards", *(f"victory_{v}" for v in range(1, 7)),
                *(BASE_CLIPS[k] for k in sorted(JUMPS)), "touchdown")
"""The base slots a recipe's ``slots`` names (Step 2.171): walk 8, run 9,
walk_backwards 13, run_backwards 14 and the victories 75-80; since Step
2.164c (D768: the Variants tab picks "the jump") the jump family
:data:`JUMPS` too: jump 15, jump_standing 16, superjump 17 and
climb_drop 20; and since Step 2.193 the hard landing's touchdown 11,
which 0x8B0D4 plays at rate 1 and holds state 0x100 for (so its clip
lasts garret4's, :data:`TOUCHDOWN_TICKS`)."""
TOUCHDOWN_TICKS = 13
"""garret4's ``touchdown``, 0.433 s: how long a hard landing holds the
player (a recipe's touchdown lasts it, so the landing's timing is his)."""
GAIT_TWINS = {"walk_backwards": "walk", "run_backwards": "run"}
"""Each backward gait slot and the forward one whose cell its rate shares
(0x30D90: 13 plays at the speed over the drawn scale x ``walkAnimSpeed``,
14 x ``runAnimSpeed``)."""


def recipe_fills(slots: dict[str, str]) -> dict[int, tuple[str, float]]:
    """X11's fills for a recipe's ``slots`` ({slot name: the clip's name
    under its body}), each untimed (Step 2.171)."""
    return {BASE_CLIPS.index(name): (clip, 0.0) for name, clip in slots.items()}


def base_seam(characters: bytes, body: str, clip: str) -> float:
    """How far (model units, the mean over its bones) ``clip``'s last pose
    sits from its first (:func:`_motion`): a base that loops sits within
    :data:`CALM_SEAM`."""
    return _motion(Rig.read(characters, body), named_clip(characters, body, clip))[1]


def idle_table(mask: int, wait: tuple[float, float], timer: int) -> bytes:
    """X45's table: the fidget ``mask``, the ``wait`` range and the
    standing timer's address."""
    return struct.pack("<IffI", mask, *wait, timer)


def install_idle_pick(xbe: bytearray, mask: int, wait: tuple[float, float]) -> None:
    """Install X45 (``player_model/idle_pick.c``) at VA 0x85CD7 in ``xbe``
    (either release) with ``mask``'s fidgets and the ``wait`` range: the
    standing player plays its base until the timer reaches a wait drawn
    from ``wait``, then a fidget of ``mask`` other than the last.  The
    timer's address comes from the image's own load at 0x85CAA.
    :class:`ValueError` names a load that isn't ``fadd dword ptr
    [disp32]``, or a site that doesn't install (D35); the shim session
    the apply opens is released here."""
    _, at, load = xbe_site(xbe, IDLE_TIMER_VA, IDLE_TIMER_LOAD)
    if bytes(xbe[at:at + 6]) != load:
        raise ValueError(f"the idle shim: VA 0x{IDLE_TIMER_VA:X} isn't the standing timer's load")
    params = {IDLE_TABLE.name: idle_table(mask, wait, struct.unpack_from("<I", load, 2)[0])}
    try:
        ok = apply_trampoline_patch(xbe, IDLE_HOOK, repo_root=_REPO_ROOT, params=params,
                                    shim_source=IDLE_SHIM.source_path())
    finally:
        release_session(xbe)
    if not ok:
        raise ValueError(f"the idle shim at VA 0x{IDLE_HOOK_VA:X} didn't install (the line above says why)")


__all__ = ["ANIMS", "ASKED", "BASE_CLIPS", "CALM_HZ", "CALM_MIN", "CALM_RATIO", "CALM_SEAM", "CHAINS", "FLOATS",
           "GAIT_TWINS", "HIT", "HOOK", "RECIPE_SLOTS", "recipe_fills", "HOOK_VA", "IDLE_HOOK", "IDLE_HOOK_VA",
           "IDLE_OBJECT", "IDLE_SHIM", "IDLE_SLOTS", "IDLE_TABLE", "IDLE_TIMER_LOAD", "IDLE_TIMER_VA", "IDLE_WAIT",
           "IDLE_WORDS", "JUMPS", "LEFT_EMPTY", "OBJECT", "SHIM", "TABLE", "TOUCHDOWN_TICKS", "X9", "base_seam",
           "calm_idle", "closest_own", "fidget_mask", "idle_fills", "idle_table", "install_idle_pick",
           "install_slots_shim", "slot_fills", "slot_table"]
