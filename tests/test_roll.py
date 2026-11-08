"""Roll: the game's own code under simulator Level 2 (``devkit.sim.l2``; Modkit's Step 2.12, D29).

The roll is the attack move 'roll forward' that BLACK starts: the entry 0x88990 and the per-tick 0x8C7D0 ->
0x8C630 turn the clip's root motion into the desired velocity gravity_integrate_raw 0x85700 hands the move code.
Blind spots: the root track is a fake curve, the move code 0x47380 (ground ramp, slopes, walls) is a stub, and
the move's end is modelled by the clip clock.  The xemu session xemu-oracle-2026-10-09 saw the roll in game at
30 fps (``devkit/sim/data/sim_blind_spots.toml``): there the move code caps ground acceleration, so the speed is
k times vanilla from the 5th tick and k = 2 rolls 1.838 times as far on flat ground.  60 fps isn't tested:
fps_unlock changes the blind spot 0x47380, and no xemu session has seen the roll at 60 fps.
"""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from azurkit.core import facts, gate, iso
from azurkit.core.xbr import Document
from azurkit.tools.mods import PACKS, PackError
from devkit.sim.l2 import F32_EPS, STANDING, PlayerSim, build_physics
from devkit.sim.ports import apply_pack

# config.xbr's attacks_anims table: TOC entry 1 (labelled armor_properties_unused until AZ-113).
ATTACKS = "attacks_anims"
ROLL_FORWARD = 20          # its entry BLACK picks (xemu: entity+0x134 = 20, +0xE0 = 0x66)
# STANDING after BLACK: the press copies 'roll forward' (Rate 1.5, Move window 0.1/0.9/1.0) to entity+0xDC, and
# the entry tick heads along the yaw of STANDING's facing (130°: later ticks read the quaternion about +z), so
# the roll moves along both x and y.  The entry's anim_change (a stub) leaves the roll clip, 1.1666666 s, on
# layer 2 with flags 0xD, as it did from STANDING's layer 1 in game (xemu sitting s6).
_, _, QZ, QW = STANDING.facing
ROLLER = replace(STANDING, attack=ROLL_FORWARD, attack_anim=0x52 + ROLL_FORWARD, anim_slot=0x52 + ROLL_FORWARD,
                 move_window=(0.1, 0.9, 1.0), attack_rate=1.5, attack_yaw=2 * math.atan2(QZ, QW),
                 anim_layer=2, layer_flags=0xD, clip_length=1.1666666)
BASIC1 = replace(ROLLER, attack=0, attack_anim=0x52, anim_slot=0x52)   # the first ground attack
ATTACK_MOVE = 0x100        # entity+0x94


@pytest.fixture(scope="module")
def usa(usa_iso) -> dict[str, bytes]:
    """The USA image's ``default.xbe`` and ``gamedata/config.xbr``."""
    with iso.Reader(usa_iso) as r:
        return {name: bytes(r.read(name)) for name in ("default.xbe", "gamedata/config.xbr")}


def _roll(vanilla: bytes, player, **physics):
    """``player``'s roll in ``vanilla`` built with player_physics at ``physics``."""
    return PlayerSim(build_physics(vanilla, **physics), player).roll()


def test_roll_slider_scales_roll_distance(usa):
    """roll_speed_scale k hands the move code k times the desired x/y velocity of 'roll forward' (config.xbr
    attacks entry 20, BLACK) in the same ticks, so on the fake track it rolls k times as far: 0 rolls in place,
    -1 rolls back; its vertical motion and every other move (basic1) stay vanilla, and 1.0 builds vanilla
    bytes."""
    attacks = Document(usa["gamedata/config.xbr"]).tables[ATTACKS]
    assert attacks.column("roll forward") == ROLLER.attack
    assert tuple(attacks.number("roll forward", f) for f in ("Rate", "Move start", "Move end1", "Move end2")) == (
        ROLLER.attack_rate, *ROLLER.move_window)
    vanilla = usa["default.xbe"]
    assert build_physics(vanilla, roll_speed_scale=1.0) == vanilla
    base = {p: _roll(vanilla, p) for p in (ROLLER, BASIC1)}
    assert (base[ROLLER].state, base[ROLLER].ticks) == (ATTACK_MOVE, 21)
    assert all(abs(d) > 0.5 for d in base[ROLLER].displacement), base[ROLLER].displacement
    for k in (2.0, 0.0, -1.0):
        for player, scale in ((ROLLER, k), (BASIC1, 1.0)):
            got, want = _roll(vanilla, player, roll_speed_scale=k), base[player]
            assert (got.state, got.ticks, got.vz) == (want.state, want.ticks, want.vz), (k, player.attack)
            assert all(math.isclose(g, scale * w, rel_tol=2 * F32_EPS)
                       for g, w in zip(got.displacement, want.displacement)), (k, player.attack)


def test_roll_time_slider_plays_the_roll_k_times_faster_over_the_same_distance(usa):
    """Modkit's Step 2.185 (D714): roll_time_scale k gives 'roll forward' k times its clip rate at the attack
    entry, so the roll lasts its 21 ticks over k (11, 43 and 7 at 2, 0.5 and 3) and, its velocity being the root
    motion per tick, moves the same distance in x, y and z; with roll_speed_scale 2 it goes twice as far in those
    11 ticks; every other move (basic1) keeps its ticks and motion, and 1.0 builds vanilla bytes."""
    vanilla = usa["default.xbe"]
    assert build_physics(vanilla, roll_time_scale=1.0) == vanilla
    base = {p: _roll(vanilla, p) for p in (ROLLER, BASIC1)}

    def moved(r, dt=1 / 30):
        return (*r.displacement, dt * math.fsum(r.vz))
    for k, ticks, far in ((2.0, 11, 1.0), (0.5, 43, 1.0), (3.0, 7, 1.0), (2.0, 11, 2.0)):
        for player, want_ticks in ((ROLLER, ticks), (BASIC1, 21)):
            got = _roll(vanilla, player, roll_time_scale=k, **({"roll_speed_scale": far} if far != 1.0 else {}))
            scale = far if player is ROLLER else 1.0
            assert (got.state, got.ticks) == (ATTACK_MOVE, want_ticks), (k, far, player.attack)
            assert all(math.isclose(g, s * w, rel_tol=1e-5) for g, w, s in
                       zip(moved(got), moved(base[player]), (scale, scale, 1.0))), (k, far, player.attack)


def test_roll_slider_refuses_a_built_or_modded_xbe_or_a_non_finite_scale(usa):
    """D27/D35: the roll builds only from vanilla: an XBE already built with another roll, or with other bytes at
    its hook 0x8C745, is refused naming the pack and the file; D23: only NaN and ±inf are refused, naming the
    slider.  Either way nothing is written."""
    vanilla = usa["default.xbe"]
    rolled = build_physics(vanilla, roll_speed_scale=2.0)
    modded = bytearray(vanilla)
    hook = facts.of(gate.USA).offset(0x8C745)
    modded[hook:hook + 5] = b"\x90" * 5
    pack = PACKS["player_physics"]
    for xbe, k, match in (
            (rolled, 3.0, r"'player_physics': default.xbe .* is not the vanilla USA one"),
            (bytes(modded), 3.0, r"'player_physics': default.xbe .* is not the vanilla USA one"),
            *((vanilla, k, "roll_speed_scale") for k in (math.nan, math.inf, -math.inf))):
        buf = bytearray(xbe)
        with pytest.raises(PackError, match=match):
            apply_pack(pack, buf, {"roll_speed_scale": k})
        assert bytes(buf) == xbe


def test_roll_lasts_the_games_21_ticks_on_any_active_layer(usa):
    """AZ-270: the game rolls 21 ticks of state 0x100 from every start (xemu s1, s2, s5, s6) on whichever
    animation layer anim_change 0x42910 picked, 1 or 2 by history: the entry and ticks read that layer's flags and
    clip at anim+0x48/+0x44 + 0x40·n (n = anim+0x10), and the roll clip is 1.1666666 s long with flags 0xD (xemu
    s6, 940 rows)."""
    got = {n: PlayerSim(usa["default.xbe"], replace(ROLLER, anim_layer=n, layer_flags=0xD,
                                                    clip_length=1.1666666)).roll()[:2]
           for n in (1, 2)}
    assert got == {1: (ATTACK_MOVE, 21), 2: (ATTACK_MOVE, 21)}
