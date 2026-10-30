"""A swapped body's victories (Step 2.121; D299, the owner: "for the
victory, let's use garret4's animation if possible"; D300).

No body but garret4's has a ``victory_1``..``6`` clip, so on every other
body X11 left the victory slots 75-80 empty and X9 (``climb.c``, Step
2.103) played its idle stand-in in garret4's time.  The build now fills
them by X11 (:func:`victory_fills`), each with a clip of garret4's
length, which the victory move (0x887D0) plays as it plays his, X9's
hit timer at 0x88958 taking that length (his immunity), and nothing
else times it (unmarked: X12 never touches a victory):

- **garret4's, retargeted** where his rig fits the body's
  (:data:`~azurik_mod.assets.retarget.MAPS`: Balthazar, keylord,
  overlord, the elementals, the townspeople): his six victories baked
  onto its rig, ``g4/victory_N``.  Where the bake serves the body
  already (``--player-character-anims garret4``) X11's rule names them;
  elsewhere (``--player-character-anims own``) the build
  bakes only these six, with no marker grown, so X9 keeps the moves it
  serves, its root lifted to its own idle's height
  (:class:`~azurik_mod.assets.retarget.Retarget`'s ``stand``).
  town_female_4 (:data:`KEEPS_STAND_IN`) carries a vase on her head in
  her own clips, which no baked clip can carry (it hides it): she keeps
  the stand-in.
- **Its own most victory-like clip** where his rig doesn't fit
  (:data:`VICTORY_CLIPS`, D300: the props, the legless, the rigs without
  his limbs): played over garret4's length, each victory's (stretched
  as a whole, ``v/victory_N``, one copy per length), without its tracks
  on the body's damage markers, own damage-field switches and the
  markers that start its scripted fx (W22's: fire_guardian's
  ``m_shards``, Step 2.175, AZ-611;
  :func:`~azurik_mod.assets.retarget.quiet`), so an attack as a
  victory hurts nothing, its wearer not, and spawns nothing.
- **The stand-in** as before on a body with nothing victory-like
  (flicken, skrit, the fish, the items: D300's "with none"); a body
  with no clips plays his as timers (Step 2.89).

The use (slot 81) is unchanged.

**A victory the stick ends** (X46, ``player_model/victory_cancel.c``;
Step 2.181, D702; the owner: "for her victory animation, can we make it
break early if the player wants to move?"): a recipe's
``victory_cancel`` (s; booblord's 0.5) installs it at the state
machine's end check of a 0x1xx move (0x8CF84, Europe 0x8CF34,
:func:`install_victory_cancel`): a victory (slot 75-80) ends, as at its
clip's end, on the first tick its own clock (critter +0x1E4 − +0x1E0,
both the clip's length at its start; not PlayerControl +0x9C, which
keeps an attack's time when the victory starts on the tick the attack
ends) has reached that many seconds with the stick past the game's own dead zone
(input +0x1C over 0.1) and the control the player's (input +0x30
clear), its hit timer (+0x1E0, the immunity and the pickup deferral)
ended with it; with the stick at rest it plays whole.  Sitting 2.181
(main's booblord, a real key pickup, w1's key_life1 [placed: R6 at its
point]): the key counted and the request posted at the touch, the
request cleared on the move's first tick, the stick read during the
move (input +0x1C 1.0) and ignored for its 121 ticks, the camera's yaw
unchanged, so nothing waits on the move's later ticks.
"""

from __future__ import annotations

from pathlib import Path

from azurkit.tools.characters.characters import DAMAGE_MARKERS, Body
from azurkit.tools.characters.retarget import BAKED_DIR, MAPS, Clip, named_clip, quiet, stretched
from azurkit.tools.characters.ports import ShimSource, TrampolinePatch, apply_trampoline_patch
from azurkit.tools.characters.ports import release_session
from azurkit.tools.characters.ports import FloatParam
from azurkit.tools.characters._player_slots import BASE_CLIPS, SHIM as SLOTS_SHIM

VICTORIES = tuple(BASE_CLIPS.index(f"victory_{v}") for v in range(1, 7))
"""The victory slots 75-80 (the request's v 1-6 plays anim 0x4A + v)."""
VICTORY_DIR = "v/"
"""Where a body's own victory clip, played over garret4's length, is
stored: ``characters/<body>/v/victory_N``, N the first of his victories
of that length (1, 3, 5, 6: his victory_2 and victory_4 last as long as
1 and 3)."""
KEEPS_STAND_IN = frozenset({"townspeople/female_4"})
"""Bodies his rig fits that keep the stand-in: town_female_4's own clips
carry her vase on her head (``vase_joint`` at x0.4), which every baked
clip hides (a prop on a root of its own, Step 2.88b), so her victories'
vase would vanish and come back."""
VICTORY_CLIPS: dict[str, str] = {
    "air_octopus": "attack_1",
    "balthazar_spider": "laugh",
    "barnacle": "attack_2",
    "bird": "fly",
    "blaze_sentinel": "attack",
    "bosses/air_guardian": "attack_arc",
    "bosses/earth_guardian": "attack_2",
    "bosses/fire_guardian": "attack_2",
    "bosses/water_guardian": "idle_laugh",
    "bosses/watertentacle_01": "attack_rl",
    "bosses/watertentacle_02": "attack_l2",
    "bosses/watertentacle_03": "attack_l2",
    "bot": "attack_1",
    "bot_evil": "attack_1",
    "catalisk": "attack_1",
    "channeler": "attack",
    "evil_noreht": "mutate",
    "firedrake": "attack_2",
    "gargoyle": "attack",
    "golem": "attack_2",
    "golem_ol": "attack_1",
    "harvester": "attack_2",
    "ice_shard": "attack_1",
    "magmar": "attack_1",
    "nice_noreht": "idle_3",
    "rock_shard": "impact",
    "shadow_demon": "attack",
    "shard": "attack",
    "splinter": "hop",
    "water_lizard": "attack_2",
    "water_lizardx": "attack_1",
}
"""Each body (case-folded) his rig doesn't fit and its most victory-like
own clip (D300; Step 2.121's read, ``$EV/2.121-victory-2026-10-20``
``results/own-candidates.tsv``): of its clips but locomotion, deaths,
hits, the bind pose (``reference``), telltales, ``disappear``, sitting
and leaning, the stand-in, any under 0.2 s, any still one (mean bone
peak under 1 degree) and any that moves ``m_feet``, the first by class
(a taunt: laugh, bow, roar; a flourish: impact, shield, lifedrain,
mutate; a jump: jump, hop, and bird's ``fly``, X11's air class; an
attack: attack*, whirlwind, eat, dive), then by how much it moves.  A
body whose only others are idles (skrit) has none.  guard_air's is its
attack_arc, the rank-2 swoop (Step 2.175, AZ-561: its attack_wind sank
the tail tip 1.59 m under the floor in the cut-in, attack_arc 0.95 m, and
from the 8th tick on stays over it).  nice_noreht's (the
body good_noreht and 24hr wear) is its idle_3, the owner's call to try
over its mutate, a head duck and look back that the 2.121 judge didn't
read as a victory (D320, V01; Step 2.126)."""


def victory_fills(body: Body, garret4: Body, *, baked: bool) -> dict[int, tuple[str, float]]:
    """X11's fills for ``body``'s victory slots (:data:`VICTORIES`), each
    unmarked (module docstring): none on a ``baked`` body, whose rule
    (``slot_fills``) gives his baked victories already; garret4's baked
    ones on a body his rig fits; its :data:`VICTORY_CLIPS` copy of his
    length (``v/``); else none (X9's stand-in)."""
    name = body.name.casefold()
    if baked:
        return {}
    if name in MAPS and name not in KEEPS_STAND_IN:
        return {slot: (BAKED_DIR + BASE_CLIPS[slot], 0.0) for slot in VICTORIES}
    if name in VICTORY_CLIPS:
        return {slot: (VICTORY_DIR + _first_as_long(garret4, BASE_CLIPS[slot]), 0.0) for slot in VICTORIES}
    return {}


def victory_copies(characters: bytes, body: Body, garret4: Body, switches: set[str]) -> dict[str, Clip]:
    """The ``v/`` clips :func:`victory_fills` names on ``body`` (a name
    under the body -> its clip): its :data:`VICTORY_CLIPS` clip without
    its tracks on its damage markers and ``switches`` (its own damage
    field's, W17's, and those that start its scripted fx, W22's: Step
    2.175, AZ-611, fire_guardian's ``m_shards``), played over each of
    garret4's victory lengths."""
    pick = VICTORY_CLIPS.get(body.name.casefold())
    if pick is None:
        return {}
    marks = {i for i, m in enumerate(body.markers) if m in DAMAGE_MARKERS or m in switches}
    clip = quiet(named_clip(characters, body.name, pick), marks)
    names = {_first_as_long(garret4, BASE_CLIPS[slot]) for slot in VICTORIES}
    return {VICTORY_DIR + name: stretched(clip, garret4.length(name)) for name in sorted(names)}


def victories_line(fills: dict[int, tuple[str, float]], body: Body, *, timers: bool,
                   recipe: dict[int, tuple[str, float]] | None = None) -> str:
    """The build log's line on what the victories play; ``recipe``: the
    fills a variant's ``slots`` gives (Step 2.171), in its victory slots
    its own clips."""
    mine = {slot: fills[slot][0] for slot in VICTORIES if slot in (recipe or {})}
    if mine:
        rest = [slot for slot in VICTORIES if slot not in mine]
        by = {}
        for slot, clip in mine.items():
            by.setdefault(clip, []).append(str(slot - VICTORIES[0] + 1))
        played = ", ".join(f"{clip} (victory {', '.join(v)})" for clip, v in by.items())
        return (f"  Player model victories: its recipe's {played} under characters/{body.name}/, X11, in its own "
                f"length, harmless (Step 2.171)" + (f"; the others as without it ({victories_line(
                    {k: v for k, v in fills.items() if k in rest} | {VICTORIES[0]: fills.get(rest[0], ('', 0.0))},
                    body, timers=timers).split(': ', 1)[1]})" if rest else ""))
    first = fills.get(VICTORIES[0], ("", 0.0))[0]
    if timers:
        what = "garret4's as timers (no bone moves), his length and hit immunity"
    elif first.startswith(BAKED_DIR):
        what = f"garret4's baked onto its rig (characters/{body.name}/{BAKED_DIR}victory_N)"
    elif first.startswith(VICTORY_DIR):
        what = (f"its own {VICTORY_CLIPS[body.name.casefold()]} over garret4's length, harmless "
                f"(characters/{body.name}/{VICTORY_DIR}victory_N, X11)")
    else:
        what = "its idle stand-in in garret4's time with his hit immunity (X9)"
    return f"  Player model victories: {what} (D299, D300)"


# --- X46: a recipe's victory the stick ends after its minimum (Step 2.181, D702) ---
_REPO_ROOT = Path(__file__).resolve().parents[2]
CANCEL_SHIM = ShimSource(folder=SLOTS_SHIM.folder, stem="victory_cancel")
CANCEL_OBJECT = "player_model_victory_cancel"
"""Its object's name: ``player_model_victory_cancel.o`` in the shim build dir."""
CANCEL_HOOK_VA = 0x8CF84
"""The state machine's (0x8CCC0) end check of a 0x1xx move, ``test eax,
ecx; jne 0x8CF8C; test al, 1`` (Europe 0x8CF34), which X46 replaces."""
CANCEL_AFTER = FloatParam(
    name="victory_cancel_after", symbol="_player_model_victory_cancel_after", default=0.5,
    label="Player model victory: the seconds before the stick ends it (X46)",
    description="The recipe's victory_cancel: how long a victory plays before a push of the stick ends it.")
CANCEL_HOOK = TrampolinePatch(
    name=CANCEL_OBJECT,
    label=f"Player model victory: the stick ends it after its minimum (X46) at VA 0x{CANCEL_HOOK_VA:X}",
    va=CANCEL_HOOK_VA,
    replaced_bytes=bytes.fromhex("85c87504a801"),   # test eax, ecx; jne +4; test al, 1
    shim_object=CANCEL_SHIM.object_path(CANCEL_OBJECT, _REPO_ROOT),
    shim_symbol="_c_player_model_victory_cancel",
    float_params=(CANCEL_AFTER,),
)


def install_victory_cancel(xbe: bytearray, after: float) -> None:
    """Install X46 (``player_model/victory_cancel.c``) at VA 0x8CF84 in
    ``xbe`` (either release): a victory ends at the first tick ``after``
    seconds in with the stick pushed (module docstring; under 0 acts as 0,
    D23).  :class:`ValueError` names a site that doesn't install (D35);
    the shim session the apply opens is released here."""
    try:
        ok = apply_trampoline_patch(xbe, CANCEL_HOOK, repo_root=_REPO_ROOT, params={CANCEL_AFTER.name: after},
                                    shim_source=CANCEL_SHIM.source_path())
    finally:
        release_session(xbe)
    if not ok:
        raise ValueError(f"the victory shim at VA 0x{CANCEL_HOOK_VA:X} didn't install (the line above says why)")


def _first_as_long(garret4: Body, victory: str) -> str:
    """garret4's first victory as long as ``victory``."""
    return next(f"victory_{v}" for v in range(1, 7) if garret4.length(f"victory_{v}") == garret4.length(victory))


__all__ = ["CANCEL_AFTER", "CANCEL_HOOK", "CANCEL_HOOK_VA", "CANCEL_SHIM", "KEEPS_STAND_IN", "VICTORIES",
           "VICTORY_CLIPS", "VICTORY_DIR", "install_victory_cancel", "victories_line", "victory_copies",
           "victory_fills"]
