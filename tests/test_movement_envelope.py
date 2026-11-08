"""The movement envelope: the physics calculator
(``src/azurkit/tools/randomizer/physics.py``, with the derive's walk-off
carry in ``devkit/rando/physics.py``) and the tiers as margins over it
(``src/azurkit/tools/randomizer/draft/``: ``envelope.py``, ``tiers.toml``).

Step R1.2 ported the envelope from the R0 evidence (D108 Q256, D113,
D144) and added the calibration sitting's laws
(``xemu-oracle-2026-10-12-calib``, REPORT §2-§5: springs, updrafts, the
lip-lift ceiling, flap timing); Step R1.2b (D156, D167, D168) made it a
calculator of any movement settings, the tiers margins over it, and each
derived flight a certificate that other settings re-check (AzurKit keeps
the certificates in the derived data and dropped the re-check, Step 4.13c).
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from azurkit.tools.randomizer.draft import envelope as env
from azurkit.tools.randomizer.planner.loader import EDGE_DIFFICULTIES
from azurkit.tools.randomizer.planner.settings import MOVEMENT_TIERS
from devkit.rando import physics
from devkit.sim import envelope as l2
from devkit.sim.l2 import STANDING, PlayerSim
from devkit.sim.ports import read_file

# Calib §5 (S1, air shield 3, a standing jump): flap ticks after the jump
# -> the apex xemu measured, m.
FLAP_APEX = {(3,): 1.4105, (14,): 2.2306, (20,): 2.1225, (23,): 1.9215, (26,): 1.2363,
             (26, 48, 73, 97, 116): 2.3009, (23, 42, 64, 85, 101): 2.3455, (29,): 1.1199,
             (10, 12, 14, 16, 18): 2.3333, (10, 13, 16, 19, 22): 2.3531}
# Calib §2 (placed on the pad): springboard S -> launch vz and the feet's
# highest rise, m.
SPRINGS = {24: (21.68870735, 23.63984), 25: (22.13594437, 24.63206),
           44: (29.36664772, None), 100: (44.27188873, 99.26343)}
# Calib §2, S 24 with air shield 3: flap ticks -> (vz before, vz after)
# of the first flap and the highest rise (a descent flap at 10 and 36).
SPRING_FLAPS = {(10,): (18.749, 2.425, None), (36,): (10.255, 2.425, None),
                (39,): (9.275, 4.850, 20.52), (64, 72, 80, 88, 96): (None, None, 25.18)}
# Calib §3: pushZ -> the fitted vz gain per tick at vz 0 with gravity added
# back (a = c x pushZ / 0.9 + g dt).
PUSH_FITS = {10.0: 0.72004, 30.0: 1.5068, 60.0: 2.68693}
VANILLA = physics.Physics()


def _arc(rank: int, ticks=(), spring=None):
    """A standing arc's rows up to the landing (feet back at the takeoff)."""
    rows = []
    for r in VANILLA.tick_arc(VANILLA.kits[rank], ticks, stick=0.0, spring=spring):
        if r[0] > 0 and r[4] < 0:
            break
        rows.append(r)
    return rows


def test_movement_tiers_are_the_planners_and_monotone_and_their_lip_lift_windows_nest():
    """Phase R1's contract (docs/RANDOMIZER_DB.md §4.3): the planner, which
    never imports this module, reads the same tiers through the data: its
    movement tiers are the player tiers, in order, and an edge's difficulty
    is a tier's number (0, the phys row: R_phys only). A harder tier counts
    everything an easier one counts: every margin is no stricter (its
    reach of the envelope no smaller, frame-perfect's all of it), and every
    lip and takeoff the easier tier's lip lift counts, the harder one
    counts too."""
    tiers = env.TIERS + (env.PHYS,)
    assert [t.name for t in tiers] == list(env.TIER_ORDER)
    assert (tuple(t.name for t in env.TIERS), [t.difficulty for t in tiers]) == (MOVEMENT_TIERS, [1, 2, 3, 4, 0])
    assert {t.difficulty for t in tiers} == EDGE_DIFFICULTIES
    assert env.TIERS[-1].reach == env.PHYS.reach == 1.0
    rows = {r[0] for r in env.LIP_LIFT_ROWS} | {env.PHYS.lift_allowance}
    deficits = sorted({k / 1000 for k in range(-100, 800)} | rows
                      | {d + e for d in rows for e in (-1e-9, 1e-9)})
    for easy, hard in zip(tiers, tiers[1:]):
        for f in ("takeoff_window", "stick_deg", "clearance", "landing_margin"):
            assert getattr(easy, f) >= getattr(hard, f), (f, easy.name, hard.name)
        for f in ("reach", "lift_allowance", "max_drop", "slippery"):
            assert getattr(easy, f) <= getattr(hard, f), (f, easy.name, hard.name)
        for d in deficits:
            we, wh = env.lip_lift_window(easy, d), env.lip_lift_window(hard, d)
            assert we is None or (wh is not None and wh[0] <= we[0] <= we[1] <= wh[1]), \
                (easy.name, hard.name, d, we, wh)


def test_envelope_laws_reproduce_the_calibration_sitting():
    for ticks, want in FLAP_APEX.items():
        assert abs(max(r[4] for r in _arc(3, ticks)) - want) < 1e-4, ticks
    for s, (v0, apex) in SPRINGS.items():
        rows = _arc(0, spring=s)
        assert abs(rows[0][7] - v0) < 1e-6, s
        assert apex is None or abs(max(r[4] for r in rows) - apex) < 1e-4, s
    for ticks, (before, after, apex) in SPRING_FLAPS.items():
        rows = _arc(3, ticks, spring=24)
        k = next(i for i, r in enumerate(rows) if r[1] == "flap")
        assert before is None or (round(rows[k - 1][7], 3), round(rows[k][7], 3)) == (before, after)
        assert apex is None or round(max(r[4] for r in rows), 2) == apex, ticks
    for push, a in PUSH_FITS.items():
        assert abs(env.push_tick(0.0, push) + VANILLA.gdt - a) < 1e-5, push
    # Calib §4: each player tier lifts to the largest deficit measured to
    # mount over at least its takeoff window, from the rows that mounted.
    for t in env.TIERS:
        deficit, first, last = max(r for r in env.LIP_LIFT_ROWS
                                   if r[2] - r[1] + 1 >= max(t.takeoff_window, 1))
        assert t.lift_allowance == deficit, t.name
        assert env.lip_lift_window(t, deficit) == (round(env.lip_row_m(last), 2),
                                                   round(env.lip_row_m(first), 2))
    assert env.lip_lift_window(env.TIERS[0], 0.2343) == (0.65, 3.69)      # s6's window
    assert env.PHYS.lift_allowance >= env.LIP_LIFT_FAILS_M


def test_tiers_toml_refuses_a_value_no_tier_can_hold_naming_the_tier_and_field(tmp_path):
    text = env.TIERS_TOML.read_text(encoding="utf-8")
    path = tmp_path / "tiers.toml"
    path.write_text(text, encoding="utf-8")
    assert env.load_tiers(path) == (env.TIERS, env.PHYS)
    for old, new, field in (("lift_allowance = 0.4987", "lift_allowance = nan", "lift_allowance"),
                            ("max_drop = 16.194", "max_drop = inf", "max_drop"),
                            ("takeoff_window = 2", "takeoff_window = -2", "takeoff_window"),
                            ("stick_deg = 4.0", "stick_deg = -4.0", "stick_deg"),
                            ("reach = 0.86", "reach = 1.2", "reach"),
                            ("reach = 0.86", "reach = 0.0", "reach"),
                            ("difficulty = 2", "difficulty = 1", "difficulty"),
                            ("lift_allowance = 0.4987", "lift_allowance = 0.6", "lift_allowance"),
                            ("slippery = false", 'slippery = "no"', "slippery")):
        assert old in text
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
        with pytest.raises(ValueError, match=rf"\[\w+\]: .*'{field}'"):
            env.load_tiers(path)


def test_a_walk_off_counts_no_farther_than_l3_carries_the_body_off_a_level_lip():
    """AZ-357 (Step X.16): in L3 at vanilla, running off 11 clean ledges
    of 6 levels with a level lip, the body centre is short of the
    calculator's carry past the takeoff floor's end at every drop, by at
    most these (the least reach over the ledges); the derive's walk-off
    limit (carry + WALKOFF_SLACK) lies within L3's reach."""
    least = {1.0: -0.864, 2.0: -0.837, 3.0: -0.83, 4.0: -0.825, 5.0: -0.824, 6.0: -0.823, 8.0: -0.825, 10.0: -0.941}
    base = physics.Envelope()
    for drop, short in least.items():
        assert base.p.walk_off_carry(drop) + physics.WALKOFF_SLACK <= base.p.walk_off_carry(drop) + short, drop


# Step R1.2b (D167): the physics calculator against the simulator. Per setting, (air rank, landing dh, "rise" or
# a springboard's height) -> the simulator's numbers for the calculator's frame-perfect flight (a springboard: the
# flap ticks given): its flap ticks, the travel from a run and from standing to the last descending crossing of dh
# (a springboard: of the takeoff), and the feet's apex, m. The modified setting moves every slider the jump, flap
# and air laws read (walk_speed_scale the run-up).
REACH_SETTINGS = {
    "vanilla": {},
    "modified": {"player_physics": {"gravity": 4.9, "jump_speed_scale": 1.25, "air_control_scale": 1.5,
                                    "flap_height_scale": 1.2, "wing_flap_ceiling_scale": 2.0,
                                    "flap_below_peak_scale": 2.0, "walk_speed_scale": 1.5},
                 "air_shield_flaps": {"air_shield_2_flaps": 3}},
}
REACH = {
    "vanilla": {
        (0, 0.0): ((), 6.778, 1.71, 1.024),
        (0, -3.0): ((), 10.322, 3.507, 1.024),
        (1, 1.0): ((23,), 14.224, 6.501, 1.921),
        (1, "rise"): ((15,), None, None, 2.24),
        (2, 0.0): ((25, 46), 24.392, 14.35, 2.303),
        (3, 0.0): ((24, 49, 74, 97, 116), 49.466, 37.012, 2.301),
        (3, -3.0): ((24, 49, 74, 97, 116), 53.589, 40.947, 2.301),
        (3, "rise"): ((15, 30, 36, 39, 41), None, None, 2.395),
        (3, 24.0): ((39,), 34.155, None, 20.524),
    },
    "modified": {
        (0, 0.0): ((), 18.857, 7.288, 1.651),
        (0, -3.0): ((), 25.753, 12.002, 1.651),
        (1, 1.0): ((40,), 42.805, 26.797, 2.964),
        (1, "rise"): ((27,), None, None, 3.464),
        (2, 0.0): ((40, 85, 117), 92.46, 73.077, 4.055),
        (3, 0.0): ((40, 85, 118, 167, 195), 137.235, 117.131, 4.026),
        (3, -3.0): ((40, 85, 118, 167, 195), 144.607, 124.451, 4.026),
        (3, "rise"): ((25, 31), None, None, 4.06),
        (3, 24.0): ((39,), 72.864, None, 21.908),
    },
}
# A descent flap (feet 4 m below the takeoff, vz -11 m/s, air shield 3): the vz after it; vanilla halves it
DESCENT_VZ = {"vanilla": -7.363, "modified": -4.827}


@pytest.mark.parametrize("setting", sorted(REACH))
def test_physics_reach_is_the_simulators_at_vanilla_and_a_modified_setting(setting, usa_iso):
    """The calculator's frame-perfect reach (flap ticks, travel from a run
    and from standing, apex) and the same flights through the game's own
    jump_init, airborne tick, wing_flap and consume_fuel under L2, on an XBE
    built with the setting's sliders, both give REACH's numbers within 1 mm:
    every press flaps, the launch speed and air control are the game's
    float32 values, a springboard launch follows the jump and air-control
    sliders, and a descent flap's lift and its emptied gauge agree."""
    m = physics.Movement.from_params(REACH_SETTINGS[setting])
    p = physics.Physics(m)
    xbe = l2.l2_xbe(read_file(usa_iso, "default.xbe"), m)
    for (rank, what), (ticks, run, stand, apex) in REACH[setting].items():
        kit, got, sim = p.kits[rank], {}, {}
        if what == "rise":
            v, s, a = p.best(kit, -60.0, objective="apex")
            got = {"ticks": s, "apex": a.apex}
            rows, flapped, jump = l2.l2_flight(xbe, m, rank, s, run=False, stop=-1.0)
            sim = {"apex": max(z for _, z in rows)}
        elif what == 24.0:
            arc = [(r[2], r[4]) for r in p.tick_arc(kit, ticks, v0_xy=(m.run_speed, 0.0), spring=what, z_floor=-1.0)]
            got = {"ticks": ticks, "run": env.last_crossing(arc, 0.0), "apex": max(z for _, z in arc)}
            rows, flapped, jump = l2.l2_flight(xbe, m, rank, ticks, spring=what, stop=-1.0)
            sim = {"run": env.last_crossing(rows, 0.0), "apex": max(z for _, z in rows)}
            assert (jump.vz, jump.air_control) == (p.launch(what), physics.f32(9.0 * m.air_control_scale)), what
        else:
            v, s, a = p.best(kit, what)
            got = {"ticks": s, "run": p.travel(v, m.run_speed, kit.air_control), "stand": p.travel(v, 0.0, kit.air_control),
                   "apex": a.apex}
            rows, flapped, jump = l2.l2_flight(xbe, m, rank, s, stop=what - 1.0)
            standing, _, _ = l2.l2_flight(xbe, m, rank, s, run=False, stop=what - 1.0)
            sim = {"run": env.last_crossing(rows, what), "stand": env.last_crossing(standing, what),
                   "apex": max(z for _, z in rows)}
            assert (jump.vz, jump.air_control) == (kit.v0, kit.air_control), (rank, what)
        want = {"run": run, "stand": stand, "apex": apex}
        assert got.pop("ticks") == ticks and flapped == [True] * len(ticks), (setting, rank, what)
        for name, value in (*got.items(), *sim.items()):
            assert abs(value - want[name]) <= 1e-3, (setting, rank, what, name, value, want[name])
    kit = p.kits[3]
    player = replace(STANDING, armor_level=3, flaps=kit.flaps, fuel=1.0)
    sim3 = PlayerSim(xbe, player)
    sim3.jump()
    x, y, z = player.position
    sim3.set(position=(x, y, z - 4.0), velocity=(0.0, 0.0, -11.0), buttons=0x04)
    flap = sim3.flap()
    vz, gauge, empty = p.flap(kit, -4.0, -11.0)
    assert abs(flap.vz - DESCENT_VZ[setting]) <= 1e-3 and abs(vz - flap.vz) <= 1e-6, setting
    assert (flap.fuel, flap.armor_reset) == (gauge, empty) == (0.0, True), setting
