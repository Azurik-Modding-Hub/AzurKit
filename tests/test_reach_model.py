"""The reach model and its derived data (``devkit/rando/draft/`` on the shipped
draft's geometry, floors and wiring), the authoring and the route graph.

Steps R1.3a-c ported it as a model from the randomizer evidence's reach v6
(``randomizer-plan-2026-10-10`` at ``d54313d``); Step 4.13c brought it and
these tests from Modkit (the L3 certification's and the xemu chain's come
with them, 4.13d).  The pure tests build small meshes by hand and read every
committed derived file as a consumer would; the vanilla tests pin one small
level's floors, regions and air against reach v6's own run and re-derive it
with ``python -m devkit rando derive --check``.
"""

from __future__ import annotations

import copy
import dataclasses
import functools
import hashlib
import itertools
import json
import math
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest

from azurkit.tools.randomizer.art import collision, tern
from azurkit.tools.randomizer.draft import geometry
from azurkit.tools.randomizer.planner.loader import kept_logic, load_database
from devkit.rando import author as author_verb
from devkit.rando import derive as derive_verb
from devkit.rando.draft import export, flights, route
from devkit.rando.draft.reach import Reach
from devkit.rando.draft.route import Router


def _quad(x0, y0, x1, y1, z, up=True, z1=None):
    """A horizontal rectangle as two triangles, facing up (or down); with ``z1`` a ramp rising along y to it."""
    z1 = z if z1 is None else z1
    a, b, c, d = (x0, y0, z), (x1, y0, z), (x1, y1, z1), (x0, y1, z1)
    return [(a, b, c), (a, c, d)] if up else [(a, c, b), (a, d, c)]


def _side(p, q, z0, z1):
    """A vertical rectangle from XY point p to q, between heights z0 and z1."""
    a, b, c, d = (*p, z0), (*q, z0), (*q, z1), (*p, z1)
    return [(a, b, c), (a, c, d)]


def _box(x0, y0, z0, x1, y1, z1):
    """A closed box, its faces outward."""
    return (_quad(x0, y0, x1, y1, z1) + _quad(x0, y0, x1, y1, z0, up=False) + _side((x0, y0), (x1, y0), z0, z1)
            + _side((x1, y0), (x1, y1), z0, z1) + _side((x1, y1), (x0, y1), z0, z1) + _side((x0, y1), (x0, y0), z0, z1))


def _mesh(tris, chunks=()) -> tern.Tern:
    """One chunk (solid, 0x8050) of ``tris``, then one per ``(flags, triangles)`` of ``chunks``."""
    return tern.Tern(0, 0, [tern.Chunk(flags, (0, 0, 0), (0, 0, 0), (0, 0, 0), [p for t in ts for p in t],
                                       [(3 * k, 3 * k + 1, 3 * k + 2, 0) for k in range(len(ts))])
                            for flags, ts in ((0x8050, tris), *chunks)], 0)


def _level(tris, *platforms, chunks=()) -> geometry.Level:
    """A level whose static collision (solid, 0x8050) is the given
    triangles (then ``chunks``' (flags, triangles)), with platforms given as
    (triangles, attributes) in place."""
    owners = [collision.Owner("levl", 0, _mesh(tris, chunks), name="levl")]
    for k, (ptris, attrs) in enumerate(platforms, 1):
        owners.append(collision.Owner("platform", k, _mesh(ptris), 0, k, f"p{k}", attrs,
                                      collision.platform_word(attrs)))
    return geometry.Level("t", owners)


def test_components_number_each_component_by_its_lowest_node():
    """The connected components that replace scipy's: every node of one
    component shares a label, and the labels count up in the order of
    each component's lowest node (a breadth-first search decides)."""
    rng = np.random.default_rng(7)
    for n, m in ((1, 0), (9, 4), (300, 220), (2000, 1900)):
        a, b = rng.integers(0, n, m), rng.integers(0, n, m)
        adj = [[] for _ in range(n)]
        for x, y in zip(a.tolist(), b.tolist()):
            adj[x].append(y)
            adj[y].append(x)
        want, nxt = [-1] * n, 0
        for s in range(n):
            if want[s] < 0:
                want[s], todo = nxt, [s]
                while todo:
                    for y in adj[todo.pop()]:
                        if want[y] < 0:
                            want[y] = nxt
                            todo.append(y)
                nxt += 1
        assert geometry.components(n, a, b).tolist() == want


def test_radius_pairs_are_every_pair_within_the_radius_in_query_then_point_order():
    """The radius search that replaces scipy's cKDTree: on a half-metre grid
    (where distances tie, and some equal the radius exactly) it gives
    every pair whose distance is at most r, sorted by query point then
    point, with the distance."""
    rng = np.random.default_rng(3)
    pts = rng.integers(-40, 40, (300, 2)) * 0.5 + 0.25
    qs = rng.integers(-40, 40, (120, 2)) * 0.5 + 0.25
    for r in (2.5, 7.0):
        want = [(i, j, float(np.hypot(*(qs[i] - pts[j]))))
                for i, j in itertools.product(range(len(qs)), range(len(pts)))
                if (qs[i] - pts[j]) @ (qs[i] - pts[j]) <= r * r]
        qi, pj, d = geometry.RadiusIndex(pts, r).pairs(qs)
        assert list(zip(qi.tolist(), pj.tolist(), d.tolist())) == want
        assert any(dd == r for *_, dd in want)


def test_raster_gives_each_column_the_triangle_exact_height_range_over_its_square():
    """A sloped triangle's pieces: in each column the z-range of the part of
    the triangle over that column's closed square (its vertices, its edges'
    crossings of the square's sides and the square's corners inside it),
    here z = x on (0, 0) (4, 0) (0, 4)."""
    lv = _level([((0.0, 0.0, 0.0), (4.0, 0.0, 4.0), (0.0, 4.0, 0.0))])
    col, zlo, zhi = geometry.raster(lv, [0])[:3]
    got = {tuple(float(v) for v in lv.cxy(c)): (float(lo), float(hi)) for c, lo, hi in zip(col, zlo, zhi)}
    assert got[(1.25, 1.25)] == (1.0, 1.5)          # inside: only its corners bound it
    assert got[(3.75, 0.25)] == (3.5, 4.0)          # holds the vertex at x = 4
    assert got[(1.75, 2.25)] == (1.5, 2.0)          # cut by the hypotenuse x + y = 4
    assert got[(2.25, 2.25)] == (2.0, 2.0)          # touched at its corner only
    assert (2.75, 2.25) not in got and len(got) == 45


def test_a_step_within_the_walking_step_joins_two_floors_and_a_higher_one_only_for_r_phys():
    """Two 4 x 4 m floors meet at an open step (no riser face): 0.3 m is
    within the player's walking step (0.35) and joins them; 0.5 m splits
    them for the player tiers but not for R_phys (step-up 0.65 m).  The
    columns along the step stand on the upper floor; regions count down
    by size."""
    for h, logic, phys in ((0.3, [153], [153]), (0.5, [81, 72], [153])):
        lv = _level(_quad(0, 0, 4, 4, 0) + _quad(0, 4, 4, 8, h))
        r = Reach(lv, flights=False)
        assert (r.W["logic"].reg_count.tolist(), r.W["phys"].reg_count.tolist()) == (logic, phys), h


def test_a_wall_takes_its_own_columns_and_erodes_floor_within_the_body_radius():
    """A 3 m wall (the plane x = 2.2, y 1..3) on a floor: its columns are no
    floor (their top is the wall), and a sample whose centre lies within
    0.5 m of it is eroded: 0.45 m beside it at x 1.75, and 0.25 m off its
    end at (2.25, 0.75); 0.55 m at x 2.75 is not."""
    w = Reach(_level(_quad(0, 0, 4, 4, 0) + _side((2.2, 1), (2.2, 3), 0, 3)), flights=False).W["logic"]
    xy = set(zip(w.x.tolist(), w.y.tolist()))
    assert not {(2.25, y) for y in (1.25, 1.75, 2.25, 2.75, 3.25)} & xy and len(xy) == 76
    eroded = set(zip(w.x[w.eroded].tolist(), w.y[w.eroded].tolist()))
    assert eroded == {(1.75, y) for y in (1.25, 1.75, 2.25, 2.75)} | {(2.25, 0.75)}
    assert w.reg_count.tolist() == [71]


def test_a_deck_between_thin_diagonal_rails_is_one_walk_region():
    """AZ-360: a deck 2.1 m wide and 12 m long, at 37 degrees to the grid,
    between two thin rails 0.94 m off its axis (town's rope bridge): the
    erosion measures each rail's face itself, not its column's box, so the
    samples within 0.44 m of the axis stay and walk end to end."""
    ux, uy = math.cos(math.radians(37)), math.sin(math.radians(37))

    def at(s, t, z=0.0):
        return (0.3 + s * ux - t * uy, 0.2 + s * uy + t * ux, z)
    a, b, c, d = at(0, -1.05), at(12, -1.05), at(12, 1.05), at(0, 1.05)
    rails = [tri for t in (-0.94, 0.94) for tri in _side(at(0, t)[:2], at(12, t)[:2], 0.0, 0.9)]
    w = Reach(_level([(a, b, c), (a, c, d)] + rails), flights=False).W["logic"]
    kept = w.reg >= 0
    off = np.abs(-(w.x - 0.3) * uy + (w.y - 0.2) * ux)
    assert len(set(w.reg[kept].tolist())) == 1 and (off[kept] < 0.44).all() and kept.sum() >= 20


def test_a_sealed_room_is_an_air_component_of_its_own():
    """A room closed by walls and a ceiling, with a 1 m slot under its
    far wall (lower than the 1.5 m a body's air needs): the air over its
    floor is one component, and no other floor's air reaches it; a point
    inside the wall is in no air."""
    room = (_quad(6, 0, 10, 4, 0) + _quad(6, 0, 10, 4, 3, up=False) + _side((6, 0), (10, 0), 0, 3)
            + _side((10, 0), (10, 4), 1, 3) + _side((10, 4), (6, 4), 0, 3) + _side((6, 4), (6, 0), 0, 3))
    r = Reach(_level(_quad(0, 0, 4, 4, 0) + room), flights=False)
    w = r.W["logic"]
    inside = w.x > 6
    assert inside.sum() == 49 and (~inside).sum() == 81
    room_air = set(w.acomp[inside].tolist())
    assert len(room_air) == 1 and not room_air & set(w.acomp[~inside].tolist())

    def air_at(x, z):
        return int(r.air.comp_of(r.air.gap_at(r.lv.col(np.array([x]), np.array([2.0])), np.array([z])))[0])
    assert (air_at(8.0, 1.5) in room_air, air_at(2.0, 1.5) in room_air, air_at(6.25, 1.5)) == (True, False, -1)


def test_floors_under_deep_water_or_in_a_damage_volume_are_not_walked():
    """A floor under more than 1 m of water is a seabed, not walked; under
    less it is wading floor; in a damage volume that is there it is gone
    for the player tiers, and R_phys keeps it."""
    lv = _level(_quad(0, 0, 6, 2, 0), (_box(0, 0, -1, 2, 2, 1.5), {"water": 1.0}),
                (_box(2, 0, -1, 4, 2, 0.5), {"water": 1.0}), (_box(4, 0, -1, 6, 2, 1), {"damage": 25.0}))
    r = Reach(lv, flights=False)
    logic, phys = r.W["logic"], r.W["phys"]
    xs = {x: bool(wd) for x, wd in zip(logic.x.tolist(), logic.wading.tolist())}
    assert not {0.75, 1.25, 4.75, 5.25} & set(xs) and xs[2.75] and xs[3.25]
    assert {4.75, 5.25} <= set(phys.x.tolist()) and logic.removed_hazard > 0


def test_water_over_water_is_two_swims_and_the_upper_falls_one_way_into_the_lower():
    """AZ-356 (D722 rows 05 and 12, the owner's X.78 demo: "you cant swim up a
    waterfall"): per column the water is each volume's interval, merged only
    where two overlap or touch, never the hull from the lowest to the
    highest, which made e6's lake and the waterfall's stream over it one
    54 m swim (and town's sewer one swim with the sea 50 m under it). A pool
    6 m over a lake, with air between, is two swim regions; the pool's open
    bottom is a one-way fall into the lake, and nothing climbs the lake up
    into the pool; a pool 18 m up falls into nothing (a lethal fall)."""
    env = flights.Env.kept()

    def swims(top_z):
        r = Reach(_level(_quad(0, 0, 12, 12, -1), (_box(0, 0, -1, 12, 12, 3), {"water": 1.0}),
                         (_box(4, 4, top_z - 3, 8, 8, top_z), {"water": 1.0})), env)
        nb, lake, pool = r.W["logic"].nreg, int(r.wg.lab[r.wg.hi < 5][0]), int(r.wg.lab[r.wg.lo > 5][0])
        kinds = {k: sorted({e["kind"] for e in es}) for k, es in r.E["logic"].items() if nb <= min(k)}
        return r.wg.n, lake != pool, kinds.get((nb + pool, nb + lake)), kinds.get((nb + lake, nb + pool))
    assert [swims(12.0), swims(24.0)] == [(2, True, ["drop"], None), (2, True, None, None)]


def test_a_kept_envelope_equals_a_fresh_build_and_any_edit_to_an_input_of_its_key_builds_it_again(
        tmp_path, monkeypatch):
    """Step R1.33 (flights.Env.kept): one built into an empty folder, that
    one read back and the run's kept envelope (another process may have
    built it) are the same bit for bit, down to each array's layout; an
    edit to any module it is built from (as the process loaded it), the
    movement, a tier, or the Python, numpy or platform it is built under
    misses, so it is built again."""
    import pickle
    import platform
    from dataclasses import replace

    from azurkit.tools.randomizer.draft import envelope
    from devkit.rando import physics

    def same(a, b):     # leaf by leaf: a whole pickle also records which equal strings are one object
        if type(a) is not type(b):
            return False
        if isinstance(a, dict):
            return list(a) == list(b) and all(same(a[k], b[k]) for k in a)
        if isinstance(a, (list, tuple)):
            return len(a) == len(b) and all(map(same, a, b))
        if hasattr(a, "__dict__"):
            return same(vars(a), vars(b))
        return pickle.dumps(a) == pickle.dumps(b)

    with monkeypatch.context() as mp:     # first: another worker may build the run's copy meanwhile
        mp.setenv(flights.KEPT_DIR_VAR, str(tmp_path / "envs"))
        built = flights.Env.kept()
        hit = flights.Env.kept()
    assert hit is not built and same(hit, built) and same(flights.Env.kept(), built)
    monkeypatch.setenv(flights.KEPT_DIR_VAR, str(tmp_path / "envs"))

    class Built(Exception):
        pass

    def build(*_a, **_k):
        raise Built

    tiers = (envelope.TIERS[0], replace(envelope.TIERS[1], clearance=envelope.TIERS[1].clearance + 0.01),
             *envelope.TIERS[2:], envelope.PHYS, envelope.ZONE)
    # a source as a process loaded it (an edit on disk after that is a new process's key, never this one's)
    cases = {m.__name__: (lambda mp, m=m: mp.setattr(m, "SOURCE_SHA256", "edited"), {})
             for m in (physics, envelope, flights)} | {
        "movement": (lambda mp: None, {"movement": replace(physics.VANILLA, run_speed=7.5)}),
        "a tier": (lambda mp: None, {"tiers": tiers}),
        "python": (lambda mp: mp.setattr(sys, "version", sys.version + " edited"), {}),
        "numpy": (lambda mp: mp.setattr(np, "__version__", np.__version__ + ".edited"), {}),
        "platform": (lambda mp: mp.setattr(platform, "platform", lambda: "edited"), {}),
    }
    monkeypatch.setattr(flights.Env, "__init__", build)
    assert flights.Env.kept().sha256 == built.sha256
    missed = []
    for name, (edit, kwargs) in cases.items():
        with monkeypatch.context() as mp:
            edit(mp)
            try:
                flights.Env.kept(**kwargs)
            except Built:
                missed.append(name)
    assert missed == list(cases)


def test_a_flight_through_a_static_hazard_is_its_gate_edge_and_none_leaves_a_spring_pad():
    """A jump whose body passes through a static damage volume is that
    hazard pseudo-gate's edge (modelled, through the gate, whose protection
    is not decoded); a solid autoSpring pad of springboard 0.5 hops the
    body, so no jump takes off from it (the way back still lands)."""
    env = flights.Env.kept()
    burn = Reach(_level(_quad(0, 0, 4, 4, 0) + _quad(5, 0, 9, 4, 0), (_box(4.2, -1, -1, 4.8, 5, 3), {"damage": 25.0})),
                 env)
    assert {k: [(e["conf"], e.get("through")) for e in es] for k, es in burn.E["logic"].items()} == \
        {(0, 1): [("modelled", ["t.hazard.p1"])], (1, 0): [("modelled", ["t.hazard.p1"])]}
    assert [(g["id"], g["requires"]) for g in burn.gates] == [("t.hazard.p1", None)]
    pad = Reach(_level(_quad(5, 0, 9, 4, 0), (_quad(0, 0, 4, 4, 0), {"gameSolid": 1.0, "autoSpring": 1.0,
                                                                     "springboard": 0.5})), env)
    assert sorted(pad.E["logic"]) == [(1, 0)] and pad.spring_blockers == {1}


def test_a_flight_needs_an_open_path_and_a_drop_is_a_walk_off():
    """Between two floors 1 m apart a jump flies at every tier with no
    shield; a ceiling 2.5 m over the gap and the floors stops the body's
    head on every modelled flight, so the edge is probe-needed; a floor 3 m
    lower is a walk-off drop, and no kit climbs back up."""
    env = flights.Env.kept()

    def edges(*extra, dz=0.0):
        r = Reach(_level(_quad(0, 0, 4, 4, 0) + _quad(5, 0, 9, 4, dz) + list(extra)), env)
        return {k: [(e["kind"], e["conf"], e["ranks"]) for e in es] for k, es in r.E["logic"].items()}

    assert edges() == {(0, 1): [("jump", "modelled", [0, 0, 0, 0])], (1, 0): [("jump", "modelled", [0, 0, 0, 0])]}
    roofed = edges(*_quad(3, -1, 6, 5, 2.5, up=False))
    assert {k: [x[1] for x in v] for k, v in roofed.items()} == {(0, 1): ["probe-needed"], (1, 0): ["probe-needed"]}
    assert edges(dz=-3.0) == {(0, 1): [("drop", "geometry", [0, 0, 0, 0])]}


def test_a_walk_off_from_a_lip_sloping_down_leaves_falling_and_carries_less():
    """AZ-365 (D719): the body runs off a lip that slopes down with the
    slope's part of its run speed falling (L3, Step X.16: 17 of 28 ledges,
    0.7-2.9 m/s), so it carries less: 3 m down, 3.90 m off a 20 degree lip
    against 5.64 m off a level one.  The derive reads the lip's slope from
    the top triangle under the takeoff floor's end and keeps it on the
    walk-off's certificate; a 3 m gap 3 m down is a walk-off off a level
    lip, not off a 20 degree one (its witness the plain running jump)."""
    from devkit.rando import physics
    env, t = flights.Env.kept(), math.tan(math.radians(20.0))
    p = physics.Physics()
    assert (p.walk_off_carry(3.0), p.walk_off_carry(3.0, t)) == pytest.approx((5.637, 3.898), abs=1e-3)
    a, b, c, d = (4, 0, 0), (5, 0, -t), (5, 4, -t), (4, 4, 0)      # the lip's last metre, falling along +x

    def walk_off(gap: float, sloped: bool):
        take = _quad(0, 0, 4, 4, 0) + [(a, b, c), (a, c, d)] if sloped else _quad(0, 0, 5, 4, 0)
        (e,) = Reach(_level(take + _quad(5 + gap, 0, 9 + gap, 4, -3)), env).E["logic"][(0, 1)]
        cert = e["certs"][0]
        return cert.walk_off, cert.slope
    assert walk_off(2.5, True) == (True, pytest.approx(0.36, abs=0.005))
    assert [walk_off(3.0, s) for s in (False, True)] == [(True, 0.0), (False, 0.0)]


def test_a_roof_that_dips_toward_the_landing_clips_a_taller_jump_its_one_headroom_kept():
    """AZ-387 (D719): a certificate's one headroom is the least room over
    the whole flight, so under a roof falling from 6 m over the takeoff to
    2.6 m past the landing a taller jump's arc, which comes down later and
    higher, kept a 4.5 m gap at every jump; the derive keeps the room over
    the arc's last quarter apart (``room_end``, 1.08 m, under the first
    quarter's 1.72 m), so a movement's re-check can clip a taller arc by
    that roof (Modkit's; AzurKit keeps the certificate and dropped the
    re-check)."""
    a, b, c, d = (-1, 0, 6.0), (13, 0, 2.6), (13, 4, 2.6), (-1, 4, 6.0)     # the roof, facing down
    reach = Reach(_level(_quad(0, 0, 4, 4, 0) + _quad(9, 0, 13, 4, 0) + [(a, c, b), (a, d, c)]), flights.Env.kept())
    (e,) = reach.E["logic"][(0, 1)]
    cert = e["certs"][1]
    assert (cert.gap, cert.room_start, cert.room_end) == pytest.approx((4.5, 1.72, 1.08), abs=0.01)


def test_a_sloped_slippery_ramp_is_slid_down_and_never_walked_up():
    """AZ-359 (Step X.16): the body slides back down slippery floors
    (0x8051) steeper than nz 0.998 (L3: no reliable headway walking up the
    fall line), so a 12 m ramp 4 m high (nz 0.95) between two plain floors
    is no logic floor: the top reaches the bottom by a slide, the bottom
    the top by nothing it can walk, and a point on it is touched sliding
    down from the top; a ramp of nz 0.999 is walked both ways."""
    for rise, down_only in ((4.0, True), (0.54, False)):
        mesh = _mesh(_quad(0, 0, 4, 4, rise) + _quad(16, 0, 20, 4, 0))
        a, b, c, d = (4, 0, rise), (16, 0, 0), (16, 4, 0), (4, 4, rise)
        mesh.chunks.append(tern.Chunk(0x8051, (0, 0, 0), (0, 0, 0), (0, 0, 0), [a, b, c, a, c, d],
                                      [(0, 1, 2, 0), (3, 4, 5, 0)]))
        r = Reach(geometry.Level("t", [collision.Owner("levl", 0, mesh, name="levl")]), flights.Env.kept())
        w = r.W["logic"]
        top, low = int(w.reg[np.argmax(w.z)]), int(w.reg[np.argmin(w.z)])
        on_ramp = (w.x > 4.5) & (w.x < 15.5) & (w.reg >= 0)
        kinds = {k: {e["kind"] for e in r.E["logic"].get(k, ()) if e["ranks"][0] == 0} for k in ((top, low), (low, top))}
        if down_only:
            assert not on_ramp.any() and "slide" in kinds[(top, low)] and kinds[(low, top)] == set()
            assert r.map_point("logic", (10.0, 2.0, 2.5)) == (top, "slide", pytest.approx(0.5, abs=0.3))   # on it
        else:
            assert on_ramp.any() and (top == low or {"walk"} <= kinds[(top, low)] & kinds[(low, top)])


def test_a_jump_from_flat_ice_is_a_standing_jump():
    """AZ-366 (D719): on flat slippery floor (0x8051, nz 0.998 and up) a
    run from a stand slides and covers 6-8 m in 3 s against 20 m (L3, Step
    X.16), so until L3 measures the ice run a takeoff from it is a standing
    jump: a 2.5 m flat gap a plain running jump clears at every tier off
    plain floor needs air 1 off a 16 m2 floor of ice, its certificate a
    standing one; the jump back onto the ice is still a running one.
    R_phys, the trap check's bound, keeps the run-up (its walk has no
    slippery regions): a 4 m gap off the ice, past its standing jump, is
    still rank 0 there."""
    env = flights.Env.kept()

    def across(ice: bool, gap: float = 2.5, prof: str = "logic"):
        take, land = _quad(0, 0, 4, 4, 0), _quad(4 + gap, 0, 8 + gap, 4, 0)
        r = Reach(_level(land, chunks=[(0x8051, take)]) if ice else _level(take + land), env)
        return {k: [(e["ranks"], e["certs"][0].run) for e in es] for k, es in r.E[prof].items()}
    assert across(False) == {(0, 1): [([0, 0, 0, 0], True)], (1, 0): [([0, 0, 0, 0], True)]}
    assert across(True) == {(0, 1): [([1, 1, 1, 1], False)], (1, 0): [([0, 0, 0, 0], True)]}
    assert across(True, 4.0, "phys") == {(0, 1): [([0, 0, 0, 0], True)], (1, 0): [([0, 0, 0, 0], True)]}


def test_a_jump_past_the_far_floors_top_lands_on_its_sloped_rim_by_the_step_up_but_not_against_a_face():
    """AZ-352 (Step R1.2b): a 7.0 m flat gap, past the plain running jump's
    6.78 m at the landing height.  When the far floor's rim slopes (nz
    0.57, rising 0.8 m over the last 0.55 m to the top) the body meets it
    under the top and the step-up lifts it on [verified xemu r18d: w1's
    stepping stones 8 of 8 and 5 of 5, town's hill 4 of 4], so the jump is
    a plain one at every tier, its certificate landing 0.8 m under the top
    by the rim; against a vertical face of the same height no plain jump
    lands, so the edge takes the air power's longer jump.  A 0.97 m riser
    the two floors meet at (town's hill, 4 of 4 with no air) is a plain
    step at every tier by the step-up too, lifted up to the largest lift
    measured over a face (0.4987 m), as safe's clearance puts its top above
    the plain apex."""
    env = flights.Env.kept()
    floors = _quad(0, 0, 3.95, 4, 0) + _quad(11.05, 0, 15, 4, 0)
    a, b, c, d = (10.5, 0, -0.8), (11.05, 0, 0), (11.05, 4, 0), (10.5, 4, -0.8)
    slope = Reach(_level(floors + [(a, b, c), (a, c, d)]), env)
    face = Reach(_level(floors + _side((11.05, 0), (11.05, 4), -0.8, 0)), env)

    def across(r):
        w = r.W["logic"]
        (e,) = r.E["logic"][(int(w.reg[np.argmin(w.x)]), int(w.reg[np.argmax(w.x)]))]
        return e

    e = across(slope)
    cert = e["certs"][0]
    assert (e["kind"], e["conf"], e["ranks"], e["kit"]) == ("jump", "modelled", [0, 0, 0, 0], "none")
    assert (cert.rank, cert.rim, cert.dh, cert.run) == (0, 0.8, pytest.approx(-0.8), True) and 6.8 < cert.gap <= 7.3
    f = across(face)
    assert (f["ranks"], f["certs"][0].rank, f["certs"][0].rim) == ([1, 1, 1, 1], 1, 0.0)
    riser = Reach(_level(_quad(0, 0, 6, 4, 0) + _quad(6, 0, 10, 4, 0.97) + _side((6, 0), (6, 4), 0, 0.97)), env)
    s = across(riser)        # a 0.97 m riser the floors meet at (town's hill): under the plain apex at hard, under
    assert (s["kind"], s["ranks"]) == ("step", [0, 0, 0, 0])     # safe's clearance only by the step-up
    assert (s["certs"][0].rim, s["certs"][0].dh) == (pytest.approx(0.4987, abs=0.001), pytest.approx(0.97 - 0.4987, abs=0.02))


def test_a_lip_lift_counts_from_the_tiers_window_with_its_rows_of_takeoff_room():
    """A plain ledge 0.2 m above the plain jump's apex, its face 2.6-2.7 m
    ahead of the takeoff samples, across a pit whose rim (the takeoff
    floor's end) lies 0.13-0.35 m ahead of them: the face is in every
    tier's window, and a tier presses over max(takeoff_window, 1) rows of
    floor, at most 2 (0.23 m, safe and standard), which fit before the
    farther rim, so every tier mounts it with no air. The window narrows as the lip stands higher above the apex (calib §4,
    Q299), less the tier's rows of takeoff room: safe counts 0.2 m from
    0.65 + 7/30 to 3.69 m, 0.3 m over rows 22-28 (1.35-2.75 m), 0.45 m over
    rows 23-27 (1.58-2.52 m), and nothing above its 0.4987 m allowance;
    hard (1 row) counts 0.45 m from 1.58 m."""
    row = 7 / 30
    near, far = flights.lip_windows("safe", np.array([0.2, 0.3, 0.45, 0.55]))
    assert near[:3].tolist() == pytest.approx([0.65 + row, 1.35 + row, 1.58 + row])
    assert far[:3].tolist() == [3.69, 2.75, 2.52] and np.isnan([near[3], far[3]]).all()
    assert flights.lip_windows("hard", np.array([0.45]))[0][0] == pytest.approx(1.58)
    env = flights.Env.kept()
    h = env.apex[("safe", "none")] + 0.2
    r = Reach(_level(_quad(2, 1.5, 4.5, 2.5, 0) + _quad(8, 1.5, 10, 2.5, h) + _side((8, 1.5), (8, 2.5), 0, h)), env)
    (e,) = r.E["logic"][(0, 1)]
    assert (e["lip"], e["kit"], e["ranks"]) == (True, "none", [0, 0, 0, 0])


def test_a_route_walks_round_a_corner_jumps_a_ledge_flaps_a_higher_one_and_swims_a_pool():
    """The xemu pilot's routes (``draft/route.py``) over the reach model's
    own graph at the hard tier: round an L of floor every straight
    way-point line stays on the floor; a 0.5 m riser is a step, its jump
    pressed before the riser and landing beyond it; a 1.7 m riser (above
    the plain jump's apex and its lip lift) needs the air-1 flap, so with
    no air the route only gets as close as the floor allows; across an 8 m
    wide, 3 m deep pool (wider than a plain jump) it walks, swims and
    walks.  A ledge 0.2 m above the plain apex across a pit (hard mounts
    it by the lip lift, X.2's miss) is a lip-lift jump whose takeoff
    stands in hard's window before the face."""
    env = flights.Env.kept()
    ell = Router(Reach(_level(_quad(0, 0, 4, 10, 0) + _quad(4, 6, 12, 10, 0)), env))
    step, ledge = (Router(Reach(_level(_quad(0, 0, 6, 4, 0) + _quad(6, 0, 10, 4, h) + _side((6, 0), (6, 4), 0, h)), env))
                   for h in (0.5, 1.7))
    h = env.apex[("hard", "none")] + 0.2
    pit = Router(Reach(_level(_quad(2, 1.5, 4.5, 2.5, 0) + _quad(8, 1.5, 10, 2.5, h) + _side((8, 1.5), (8, 2.5), 0, h)),
                       env))
    rt = pit.plan((2.75, 2, 0), (9.5, 2, h), tier="hard", air=0)
    jump = rt.legs[-1] if rt.legs[-1].action == "jump" else rt.legs[-2]
    win = jump.lip["window_m"]
    assert rt.reached and jump.lip["deficit_m"] == pytest.approx(0.2) and win[0] <= jump.lip["before_m"] <= win[1]
    assert 7.5 - jump.at[0] == pytest.approx(jump.lip["before_m"], abs=0.3) and jump.lip["floor_m"] <= 0.25
    pool = Router(Reach(_level(_quad(0, 0, 4, 4, 0) + _quad(4, 0, 12, 4, -3) + _quad(12, 0, 16, 4, 0)
                               + _side((4, 0), (4, 4), -3, 0) + _side((12, 4), (12, 0), -3, 0),
                               (_box(4, 0, -3, 12, 4, -0.2), {"water": 1.0})), env))
    for router, goal, air, want in ((ell, (11, 8, 0), 0, (True, ["walk"])),
                                    (step, (9, 2, 0.5), 0, (True, ["walk", "jump", "walk"])),
                                    (ledge, (9, 2, 1.7), 0, (False, ["walk"])),
                                    (ledge, (9, 2, 1.7), 1, (True, ["walk", "flap", "walk"])),
                                    (pool, (15, 2, 0), 0, (True, ["walk", "swim", "walk"]))):
        rt = router.plan((2, 1, 0) if router is ell else (1, 2, 0), goal, tier="hard", air=air)
        assert (rt.reached, [leg.action for leg in rt.legs]) == want, (goal, air)
        for leg in rt.legs:
            if leg.action == "walk" and rt.reached:
                assert all(router.line_ok(a, b, swim=False) for a, b in zip(leg.pts, leg.pts[1:]))
            if leg.action in ("jump", "flap"):
                assert leg.at[0] < 6.0 < leg.pts[-1][0]
    assert len(ell.plan((2, 1, 0), (11, 8, 0)).legs[0].pts) >= 3          # it turns at the corner


def test_the_l3_goal_flaps_a_flight_by_the_descent_flap_rule_and_recasts_a_spent_gauge_before_its_takeoff():
    """Step R1.29e: the L3 search's guide (``l3_goal.RouteGoal``) over a 1.7 m ledge that needs air 1's flap: on
    the ground near the flap's takeoff with the gauge under 1 it asks for a cast (the fourth item; standing at the
    takeoff, at rest), with it full it runs up and jumps; in the air on the flight's track it heads for the landing
    and flaps only falling, with a flap left and gauge, under the landing, inside the flap ceiling and the descent
    bound the game's peak_z sets (z0 + 1.2 at the jump: 2.4 m over the takeoff floor and 3.6 m under it; after a
    springboard higher, after a walk-off the last jump's); its cells keep the flaps left in a jump and whether the
    gauge is full apart; the trick explorer's guides ask no cast (their moves have none: a takeoff keeps its
    heading and jump); and the search runs a cast it asks for as a short LT+Y segment."""
    import typing

    from devkit.rando.draft import l3_goal
    from devkit.sim.l3_search import Limits, search
    from devkit.sim.obs import Obs

    ledge = Router(Reach(_level(_quad(0, 0, 6, 4, 0) + _quad(6, 0, 10, 4, 1.7) + _side((6, 0), (6, 4), 0, 1.7)),
                         flights.Env.kept()))
    goal = l3_goal.RouteGoal(ledge, (9.0, 2.0, 1.7), air=1)

    class Row(typing.NamedTuple):
        pos: tuple
        state: int
        hp: int = 200
        zone: str | None = "t.Z000"
        obs: Obs | None = None

    def row(x, z, state=0, vz=0.0, used=0, gauge=1.0, peak=2.2):       # a jump from the floor: centre 1.0 + h
        return Row((x, 2.0, z + 1.0), state, obs=Obs((x, 2.0, z + 1.0), (0.0, 0.0, vz), state, 200, 200, used,
                                                      flaps=1, gauge=gauge, fall_ref=0.0, peak_z=peak))
    assert goal.toward(row(4.5, 0.0, gauge=0.5))[3] and len(goal.toward(row(4.5, 0.0))) == 3      # the run-up
    assert goal.toward(row(5.5, 0.0, gauge=0.5)) == (None, False, None, True)                     # the takeoff
    assert goal.toward(row(5.5, 0.0))[1] and not goal.toward(row(5.5, 0.0, gauge=0.5))[1]
    explorer = l3_goal.RouteGoal(ledge, (9.0, 2.0, 1.7), air=1)
    explorer.casts = l3_goal.TrickGoal.casts                   # the trick explorer's (its moves cast nothing)
    assert not explorer.casts and explorer.toward(row(5.5, 0.0, gauge=0.5)) == goal.toward(row(5.5, 0.0))
    heading, flap = goal.toward(row(6.0, 1.0, 2, vz=-1.0))
    assert flap and -math.sin(heading) > 0                       # toward the landing beyond the face
    assert not any(goal.toward(r)[1] for r in (row(6.0, 1.0, 2, vz=1.0), row(6.0, 1.0, 2, vz=-1.0, used=1),
                                               row(6.0, 1.0, 2, vz=-1.0, gauge=0.0), row(6.0, 2.5, 2, vz=-1.0),
                                               row(6.0, -3.5, 2, vz=-1.0), row(6.0, 1.0, 2, vz=-1.0, peak=8.0),
                                               row(6.0, 1.0, 2, vz=-1.0, peak=0.5)))   # a launch's, a stale one
    assert goal.cell(row(4.5, 0.0)) != goal.cell(row(4.5, 0.0, gauge=0.5))
    assert goal.cell(row(6.0, 1.0, 2)) != goal.cell(row(6.0, 1.0, 2, used=1))

    class Rec:                           # a sim that records the buttons it was given; the guide asks for a cast
        def __init__(self):
            self.s, self.seen = 0, []

        def save(self):
            return self.s

        def reset(self, s):
            self.s = s

        def step(self, pad):
            self.seen.append(pad.buttons)
            self.s += 1
            return Row((0.0, 0.1 * self.s, 1.0), 0)

    class Cast:
        settle = 0

        def reached(self, r):
            return False

        def cost(self, r):
            return 1.0

        def toward(self, r):
            return 0.0, False, None, True

        def cell(self, r):
            return (round(r.pos[1], 1),)
    sim = Rec()
    search(sim, 0, Row((0.0, 0.0, 1.0), 0), Cast(), Limits(steps=60, pursue=1.0), seed=1)
    assert sim.seen[:6] == [{"lt", "y"}, set(), set()] * 2


def test_an_anchored_goal_prices_no_unsupported_row_under_its_start_and_a_flying_row_by_its_flight_while_it_can_land():
    """Step X.53 (AZ-578, AZ-581, AZ-582): the L3 search's guide over a 1.7 m ledge that needs air 1's flap,
    anchored at a start standing on the floor.  (i) A row in the air 6.2 m under the goal's ledge, far from every
    floor, costs the start's cost plus ``FAR_S``, not the far fallback's straight line through the floor (which is
    under it); (ii) a row standing 3 m over the floor on nothing costs the same, not the floor under it, and its
    stall stage is ``on no floor``.  AZ-621 (Step X.54): (iii) a row in the air on the flap's track whose arc can
    still land (``l3_goal.air_time``: its rise, the flap left under the flap ceiling, a descent flap's a quarter of
    a flap's, the game halving its launch speed) costs the landing's cost plus
    the time still to land (the flap and the fall onto the ledge; 1 m over the landing, the fall), more than a row
    standing there, its stall names the flap (``flying #k``), and over the landing the guide heads on along the
    track; (iv) one with its flap spent 1.2 m under the ledge's top can't land there, so it costs, and its stall
    is named, by the floor it falls to."""
    import typing

    from devkit.rando.draft import l3_goal
    from devkit.sim.l3_search import stall_name
    from devkit.sim.obs import Obs

    reach = Reach(_level(_quad(0, 0, 6, 4, 0) + _quad(6, 0, 10, 4, 1.7) + _side((6, 0), (6, 4), 0, 1.7)),
                  flights.Env.kept())
    reach.zone_of = np.arange(reach.W["logic"].nreg + 64, dtype=np.int64)     # the floor t.Z000, the ledge t.Z001
    R = Router(reach)
    goal = l3_goal.RouteGoal(R, (9.0, 2.0, 1.7), air=1)
    flap = next(i for i, (_, _, e) in enumerate(R.edges) if e["kind"] == "flap")

    class Row(typing.NamedTuple):
        pos: tuple
        state: int
        hp: int = 200
        zone: str | None = None
        obs: Obs | None = None

    def fly(x, y, feet, vz, used=0):                      # in the air off the floor's jump (peak_z 2.2), flaps 1
        c = (x, y, feet + 1.0)
        return Row(c, 2, obs=Obs(c, (0.0, 0.0, vz), 2, 200, 200, used, flaps=1, gauge=1.0, fall_ref=0.0, peak_z=2.2))
    start, deep, perched = Row((3.0, 2.0, 1.0), 0), Row((9.0, 2.0, -3.5), 2), Row((5.0, 2.0, 4.0), 0)
    straight = goal._far((9.0, 2.0, -4.5))[1] + l3_goal.FAR_S         # the fallback's line to the ledge, 6.2 m
    under = R.locate((5.0, 2.0, 3.0))                                   # the floor 3 m under the perched row
    credited = goal.dist[under] + 3.0 / route.WALK_MPS
    assert goal.cost(deep) == straight                                  # unanchored: the straight line
    goal.anchor(start)
    s = goal.cost(start)
    assert straight < s + l3_goal.FAR_S and credited < s + l3_goal.FAR_S
    assert goal.cost(deep) == goal.cost(perched) == s + l3_goal.FAR_S
    assert goal.ahead(perched)["stage"] == "on no floor"
    g = 9.8
    assert l3_goal.air_time(0.0, 4.0, 0.0) == pytest.approx((8.0 / g, 8.0 / g))
    assert l3_goal.air_time(0.0, 0.0, 1.0) is None and l3_goal.air_time(0.0, 0.0, 1.0, 1, 2.0)[0] > 0
    assert l3_goal.air_time(0.0, 0.0, 0.29, 1, 8.2) and l3_goal.air_time(0.0, 0.0, 0.31, 1, 8.2) is None
    w = int(R.dst[int(np.nonzero((R.kind == route.K_EDGE) & (R.eid == flap))[0][0])])
    flapping, over, spent = fly(6.0, 2.0, 1.0, -1.0), fly(R.X[w], R.Y[w], R.Z[w] + 1.0, -2.0, 1), fly(5.5, 2.0, 0.5,
                                                                                                    -1.0, 1)
    standing = Row((R.X[w], R.Y[w], R.Z[w] + 1.0), 0)
    rise = math.sqrt(2 * g * l3_goal.FLAP_H)                             # the flap from rest, then down onto 1.7 m
    assert goal.cost(flapping) == pytest.approx(goal.dist[w] + (rise + math.sqrt(rise ** 2 - 2 * g * 0.7)) / g)
    assert goal.cost(over) == pytest.approx(goal.dist[w] + (-2.0 + math.sqrt(4.0 + 2 * g)) / g)
    assert goal.cost(standing) < goal.cost(over) < goal.cost(flapping)
    assert stall_name(goal.ahead(flapping)) == f"flying #{flap} flap (modelled) t.Z000>t.Z001"
    assert goal.toward(over) == (-math.pi / 2, False)                     # on along the track (+x); no flap left
    floor = R.locate((5.5, 2.0, 0.5))
    assert goal.cost(spent) == pytest.approx(goal.dist[floor] + math.dist((5.5, 2.0, 0.5), R.pt(floor))
                                             / route.WALK_MPS)
    assert stall_name(goal.ahead(spent)) == f"#{flap} flap (modelled) t.Z000>t.Z001"


def test_the_trick_graph_doubts_what_the_games_jump_cant_make_drops_nothing_and_joins_near_water():
    """Step X.53 (AZ-591, AZ-577): the light trick graph (``l3_goal.TrickRouter``, guidance only) drops no flight
    it doubts.  A drop straight down off a slab onto the floor 3.2 m under its edge (no distance across: every test
    path crosses the slab's own top) is kept at its plain cost; a jump through a 6 m wall costs ``DOUBT_S`` more,
    doubted ``blocked`` (both were dropped); two pools 1 m apart are joined by a swim link (a swimmer in one is on
    the field of a goal in the other).  The game's jump (``jump_doubt``, 0x89060's two branches): from a slope of nz
    0.65 a lift of 1.0 m passes h nz^2 plus the lip lift (0.96 m) and from a flat floor it doesn't (the apex
    1.02 m); a lift 0.7 m over the apex makes it only by a sloped rim's step-up; a slope hop landing behind its
    face's normal is doubted.  ``route.Router._widen`` keeps a witness whose sideways move would land 0.3 m higher
    on a ramp, and still moves one onto a flat floor."""
    import typing

    from devkit.rando.draft import l3_goal

    env = flights.Env.kept()
    apex = env.apex[("phys", "none")]
    lift = [flights.RIM_STEP_LIFT, flights.RIM_STEP_LIFT, flights.RIM_LIFT, flights.RIM_STEP_LIFT, 0.0]
    assert l3_goal.jump_doubt(np.array([1.0, 1.0, apex + 0.7, apex + 0.7, 0.2]), np.array([0.65, 1.0, 1.0, 1.0, 0.65]),
                              np.zeros(5, bool), np.array([False] * 4 + [True]), h=1.1, flaps=0.0, apex=apex,
                              lift=np.array(lift)).tolist() == [1, 0, 0, 1, 2]
    tris = (_quad(0, 0, 6, 4, 0) + _box(0, 0, 3.0, 3, 4, 3.2)                                 # a slab over a floor
            + _quad(20, 0, 24, 4, 0) + _quad(26, 0, 30, 4, 0) + _box(24.8, -1, -1, 25.2, 5, 6)   # a wall between
            + _quad(40, 0, 44, 4, -3) + _quad(45, 0, 49, 4, -3))                                 # two pools' floors
    reach = Reach(_level(tris, (_box(40, 0, -3, 44, 4, -0.2), {"water": 1.0}),
                         (_box(45, 0, -3, 49, 4, -0.2), {"water": 1.0})), env)
    w = reach.W["phys"]

    def samples(x, y):                                  # the phys samples in a column, highest first
        return sorted(np.nonzero(w.col == int(reach.lv.col(x, y)))[0].tolist(), key=lambda j: -w.z[j])
    top, under = samples(1.75, 2.25)
    drop = {"kind": "drop", "conf": "geometry", "ranks": [0, 0, 0, 0], "w": (top, under)}
    reach.E["phys"][(int(w.reg[top]), int(w.reg[under]))].append(drop)
    near, far = (int(w.reg[samples(x, 2.25)[0]]) for x in (23.75, 26.25))
    walled = next(e for e in reach.E["phys"][(near, far)] if e["kind"] == "jump")    # the derive's, over the wall
    plain, trick = Router(reach, "phys"), l3_goal.TrickRouter(reach, 0)

    def link(R, e):
        k = next(i for i, (_, _, x) in enumerate(R.edges) if x is e)
        return k, np.nonzero((R.kind == route.K_EDGE) & (R.eid == k))[0]
    (kd, qd), (kw, qw), (_, pw) = link(trick, drop), link(trick, walled), link(plain, walled)
    assert len(qd) == 1 and kd not in trick.doubt and trick.cost[qd[0]] < l3_goal.DOUBT_S
    assert trick.doubt[kw] == "blocked" and trick.cost[qw].tolist() == pytest.approx(
        (plain.cost[pw] + l3_goal.DOUBT_S).tolist())

    class Row(typing.NamedTuple):
        pos: tuple
        state: int
        hp: int = 200
        zone: str | None = None
    assert l3_goal.RouteGoal(trick, (47.0, 2.0, -0.2)).finite_at(Row((41.0, 2.0, 0.0), 6))
    for rise, moved in ((2.4, False), (0.0, True)):        # a ramp rising 0.6 m a metre sideways, or flat
        ramp = Reach(_level(_quad(60, 0, 64, 4, 0) + _quad(66, 0, 70, 4, 0.5, z1=0.5 + rise)), env)
        rw = ramp.W["phys"]
        i, j = (int(np.nonzero(rw.col == int(ramp.lv.col(x, 0.25)))[0][0]) for x in (63.75, 66.25))
        jump = {"kind": "jump", "conf": "modelled", "ranks": [0, 0, 0, 0], "w": (i, j)}
        ramp.E["phys"][(int(rw.reg[i]), int(rw.reg[j]))].append(jump)
        R = Router(ramp, "phys")
        q = link(R, jump)[1][0]
        assert ((int(R.src[q]), int(R.dst[q])) != (i, j)) == moved, rise


def test_a_climbing_bodys_cost_to_go_falls_along_its_climb_from_the_foot_to_the_top():
    """Step R1.29e: a body climbing (state 1) stands on no vertex, so the L3 search's guide (``l3_goal.RouteGoal``)
    gave it the floor under it plus the way up to it at walk speed (or the nearest vertex and 2 s, or the far
    fallback and 4 s): its cost rose as it climbed, and the cell picker shunned the climb (a5/g0/r1773's way back).
    Now it is the climb edge's own cost interpolated by height, falling from the foot's to the top's, and its
    heading is into the face."""
    import typing

    from devkit.rando.draft import l3_goal

    reach = Reach(_level(_quad(0, 0, 6, 4, 0) + _quad(6, 0, 10, 4, 10) + _side((6, 0), (6, 4), 0, 10)),
                  flights.Env.kept())
    w = reach.W["logic"]
    lo, hi = int(w.reg[np.argmin(w.z)]), int(w.reg[np.argmax(w.z)])
    reach.E["logic"][(lo, hi)] = [{"kind": "climb", "conf": "modelled", "ranks": [0, 0, 0, 0], "dh": 10.0}]
    goal = l3_goal.RouteGoal(Router(reach), (9.0, 2.0, 10.0))

    class Row(typing.NamedTuple):
        pos: tuple
        state: int
        hp: int = 200
        zone: str | None = "t.Z000"
    rows = [Row((5.5, 2.0, 1.0), 0)] + [Row((5.8, 2.0, z + 1.0), 1) for z in (1.0, 4.0, 8.0, 9.6)] + [
        Row((6.5, 2.0, 11.0), 0)]
    cost = [goal.cost(r) for r in rows]
    assert all(a > b for a, b in zip(cost, cost[1:])), cost
    assert all(-math.sin(goal.toward(r)[0]) > 0.9 for r in rows[1:-1])     # into the face (+x)


def test_a_route_rides_a_lift_from_its_trigger_pad(monkeypatch):
    """The pilot's rides (Step X.4): a decoded ride edge's wait leg
    carries the pad that starts it and the reach nodes that touch the
    pad."""
    reach = Reach(_level(_quad(0, 0, 4, 4, 0) + _quad(8, 0, 12, 4, 10)), flights.Env.kept())
    w = reach.W["logic"]
    lo, hi = int(w.reg[np.argmin(w.z)]), int(w.reg[np.argmax(w.z)])
    reach.E["logic"][(lo, hi)] = [{"kind": "rig", "conf": "modelled", "ranks": [0, 0, 0, 0], "dh": 10.0, "via": "lift",
                                   "flags": ["touch:0:7"]}]
    monkeypatch.setattr(reach, "pad_nodes", lambda atom, prof: {lo}, raising=False)
    monkeypatch.setattr(reach, "flagdef_label", lambda atom: "liftPad (touch)", raising=False)
    ride = next(leg for leg in Router(reach).plan((2, 2, 0), (10, 2, 10), tier="hard", allow_probe=("rig",)).legs
                if leg.action == "wait")
    assert (ride.action, ride.edge["conf"], ride.trigger) == ("wait", "modelled", [
        {"atom": "touch:0:7", "kind": "touch", "pad": "liftPad (touch)", "nodes": frozenset({lo})}])


def test_the_guide_stands_on_a_ride_walks_into_a_teleport_and_keeps_off_a_held_rigs_guesses(tmp_path, monkeypatch):
    """Step X.53 (AZ-592): the L3 guide (``l3_goal.RouteGoal``) over a lift from a floor up onto a ledge 10 m
    higher stands at the ride's source rather than running at the deck, and a body standing in the ride's column
    with no floor under its feet is on the ride: it costs the ledge's cost plus the ride's rest by height and
    stands until level with the ledge, then steps off toward it.  A teleport from the floor's pad joins it to a
    floor nothing else reaches: finite across, its cost the walk into the pad plus ``TELEPORT_S``, the guide
    heading into the pad.  A probe-needed ride of a rig the level's authoring holds (``[rig_held]``) is not in the
    route graph, and the light trick graph doubts it (``held rig``), and a teleport that needs other pads touched
    first (``pads first``)."""
    import typing

    from devkit.rando.draft import author, l3_goal

    pad = _box(1, 1, 0, 2, 2, 2)
    reach = Reach(_level(_quad(0, 0, 4, 4, 0) + _quad(8, 0, 12, 4, 10) + _quad(30, 0, 34, 4, 0), (pad, {})),
                  flights.Env.kept())
    w = reach.W["logic"]
    lo, hi, far = (int(w.reg[np.nonzero(w.col == int(reach.lv.col(x, 2.25)))[0][0]]) for x in (1.25, 9.25, 31.25))
    reach.E["logic"][(lo, hi)] = [{"kind": "rig", "conf": "modelled", "ranks": [0, 0, 0, 0], "dh": 10.0,
                                   "via": "lift"}]
    reach.E["logic"][(lo, far)] = [{"kind": "teleport", "conf": "data", "ranks": [0, 0, 0, 0], "teleporter": "t/g0/r9",
                                    "why": "touch p1 (touch) -> playerLocation Loc.teleport (wiring)"}]
    monkeypatch.setattr(reach.lv, "rec_points", lambda gid: [[(32.0, 2.0, 0.0)]], raising=False)

    class Row(typing.NamedTuple):
        pos: tuple
        state: int
        hp: int = 200
        zone: str | None = None
    R = Router(reach)
    lift, tele = (next(i for i, (_, _, e) in enumerate(R.edges) if e["kind"] == kind) for kind in ("rig", "teleport"))
    up = l3_goal.RouteGoal(R, (10.0, 2.0, 10.0))
    q = int(np.nonzero((R.kind == route.K_EDGE) & (R.eid == lift))[0][0])
    src, dst = R.pt(int(R.src[q])), R.pt(int(R.dst[q]))
    assert up.toward(Row((src[0], src[1], 1.0), 0)) == (None, False)            # at the ride's source: stand
    mid, top = Row((5.0, 2.0, 6.0), 0), Row((5.0, 2.0, dst[2] + 1.0), 0)       # on the deck, 5 m up and level
    assert up.cost(mid) == pytest.approx(up.dist[int(R.dst[q])] + 0.5 * R.cost[q] + abs(
        (5.0 - src[0]) * (dst[1] - src[1]) - (2.0 - src[1]) * (dst[0] - src[0])) / math.dist(src[:2], dst[:2])
        / route.WALK_MPS)
    assert up.toward(mid) == (None, False)                                         # stand, then step off
    assert up.toward(top) == (l3_goal.heading_to((5.0, 2.0, dst[2]), dst), False)
    assert up.ahead(mid)["stage"] == "riding"
    across = l3_goal.RouteGoal(R, (32.0, 2.0, 0.0))
    t = int(np.nonzero((R.kind == route.K_EDGE) & (R.eid == tele))[0][0])
    assert R.pads[tele] == (1.5, 1.5, 0.0) and R.cost[t] == pytest.approx(
        math.dist(R.pt(int(R.src[t])), (1.5, 1.5, 0.0)) / route.WALK_MPS + route.TELEPORT_S)
    assert across.finite_at(Row((3.0, 3.0, 1.0), 0))
    assert across.toward(Row((3.0, 3.0, 1.0), 0)) == (l3_goal.heading_to((3.0, 3.0, 0.0), (1.5, 1.5, 0.0)), False)
    reach.E["logic"][(lo, hi)][0].update(conf="probe-needed")                     # a guessed ride, the rig held
    (tmp_path / "t.toml").write_text('[rig_held]\nlift = "a test hold"\n', encoding="utf-8")
    monkeypatch.setattr(author, "AUTHORING", tmp_path)
    assert not l3_goal.RouteGoal(Router(reach), (10.0, 2.0, 10.0)).finite_at(Row((2.0, 3.0, 1.0), 0))
    reach.E["phys"][(lo, hi)] = [reach.E["logic"][(lo, hi)][0]]
    reach.E["phys"][(lo, far)] = [dict(reach.E["logic"][(lo, far)][0], flags=["touch:0:9"])]   # another pad first
    T = l3_goal.TrickRouter(reach, 0)
    assert {e["kind"]: T.doubt.get(i) for i, (_, _, e) in enumerate(T.edges) if e["kind"] in ("rig", "teleport")} == {
        "rig": "held rig", "teleport": "pads first"}


def test_a_guessed_ride_needs_movers_that_carry_its_deck_up_and_keep_it_level(usa_iso):
    """AZ-353: ``moves.rig_edges`` guesses a ride only on a deck whose
    movers lift it level (``Level.lifts``): not e2's gears and axles,
    which a rotateX turns over, nor its grinder, turned about the vertical
    (sitting x2's rides that never moved); a translateZ bucket floor and
    e5's upright carriers under RotateX_Pivot (inherit mode 2) are."""
    lv = {name: geometry.Level.read(usa_iso, name) for name in ("e2", "e5")}

    def lifts(level, name):
        return {lv[level].lifts(o["oi"]) for o in lv[level].owners if o["kind"] == "platform" and o["name"] == name}
    assert [lifts("e2", n) for n in ("Gear_Large5:pTorusShape27", "Axle2Shape", "Grinder3:pTorusShape5",
                                     "mineplat4:BucketFloorShape")] == [{False}, {False}, {False}, {True}]
    assert lifts("e5", "pCylinderShape14") == {True}


def test_a_route_skirts_a_level_exits_trigger_unless_the_target_is_in_it():
    """Sitting x4: f6's exit camera field, on the straight walk, took over
    the player for 95 ticks; a route goes round a trigger named as an
    exit's field, and still into it when the target lies inside."""
    reach = Reach(_level(_quad(0, 0, 12, 6, 0), (_box(4, 0, -0.5, 8, 2.5, 3), {})), flights.Env.kept())
    reach.lv.owners[1]["name"] = "ExitCamFieldShape"
    router = Router(reach)
    inside = lambda p: 4 <= p[0] <= 8 and p[1] <= 2.5          # noqa: E731
    pts = [q for leg in router.plan((1, 1, 0), (11, 1, 0)).legs for q in leg.pts]
    on = [(a[0] + (b[0] - a[0]) * t / 20, a[1] + (b[1] - a[1]) * t / 20) for a, b in zip(pts, pts[1:]) for t in range(21)]
    assert router.exit_v.any() and not any(inside(q) for q in on)
    assert router.plan((1, 1, 0), (6, 1, 0)).reached


def test_the_pilots_stick_is_camera_relative_within_a_real_pads_round_gate_and_its_air_target_lands_on_the_aim():
    """The xemu pilot's pad (Step X.4): the stick points up along the
    camera and left 90 degrees to its left; along an axis (or within 5
    degrees of one, the other axis left in its dead zone) it reaches 1.0,
    on a diagonal only the round gate's 0.761 (each axis's dead zone takes
    12000 of 32767 raw units).  The air target, held, carries the body
    exactly over the distance in n ticks of the air blend; a jump lands
    on its own height after the 28 ticks xemu measured."""
    from devkit.sim import inputs
    r = math.radians
    assert inputs.stick(r(30.0), r(30.0)) == inputs.stick(r(33.0), r(30.0)) == pytest.approx((0.0, 1.0), abs=1e-4)
    assert inputs.stick(r(120.0), r(30.0), 0.5) == pytest.approx((-0.5, 0.0), abs=1e-9)
    x, y = inputs.stick(r(75.0), r(30.0))
    assert math.hypot(x, y) == pytest.approx(0.761, abs=1e-3) and x == pytest.approx(-y)
    tx, ty = route.air_target(3.0, -1.0, 7.0, 0.0, 20)
    vx, vy, px, py = 7.0, 0.0, 0.0, 0.0
    for _ in range(20):
        vx, vy = tx + (vx - tx) * route.AIR_F, ty + (vy - ty) * route.AIR_F
        px, py = px + vx / 30, py + vy / 30
    assert (px, py) == pytest.approx((3.0, -1.0))
    assert (route.fall_ticks(4.6432748, 0.0), route.fall_ticks(0.0, -0.5)) == (28, 0)     # the measured jump


def _sha(*arrs) -> str:
    h = hashlib.sha256()
    for a in arrs:
        a = np.ascontiguousarray(a)
        h.update(str(a.dtype).encode() + str(a.shape).encode() + a.tobytes())
    return h.hexdigest()[:16]


def test_airship_floors_regions_and_air_hold_their_pinned_digests(usa_iso):
    """airship's owners, walkable floors, regions and air components (counts
    and digests of the in-memory arrays; no coordinate is stored), first
    pinned to reach v6's own run (the evidence repository at d54313d,
    Step R1.3a) and re-pinned at Step X.16: slippery slopes under nz
    0.998 are no floor (AZ-359: 1,344 fewer logic samples) and the
    erosion measures an obstacle's face (AZ-360: 860 and 1,402 fewer
    eroded samples).  airship's wiring changes no owner at load."""
    lv = geometry.Level.read(usa_iso, "airship")
    r = Reach(lv, flights=False)
    cats = {}
    for o in lv.owners:
        cats[geometry.CAT_NAME[o["cat"]]] = cats.get(geometry.CAT_NAME[o["cat"]], 0) + 1
    assert cats == {"static": 1, "platform": 3, "rig": 67, "toggled": 2, "trigger": 10}
    assert (r.air.N, r.air.joins, r.air.n_components, _sha(r.air.comp)) == (96662, 151293, 20735, "bc3d34cb11af7e3d")
    got = {p: (len(w.z), w.nreg, int(w.eroded.sum()), _sha(w.col, w.z, w.ceil, w.sidx), _sha(w.reg), _sha(w.reg_soft))
           for p, w in r.W.items()}
    assert got == {
        "logic": (18229, 98, 541, "063e3d23d4751872", "c04dbe747ea0e45c", "135b6d921dd678b5"),
        "phys": (31530, 226, 882, "5b4e3d29bcb31e12", "941e8928cad0cb3c", "9b78939baf6a9ee6"),
    }


def test_every_derived_file_passes_the_consumers_checks_and_carries_the_current_derive_stamp():
    """The committed derived data (``data/derived/<level>.json.gz``, Step
    R1.3c; gzip-compressed compact JSON with sorted keys since R1.3d, the
    text :func:`export.dumps` writes) read as a consumer reads it
    (``export.check_doc``, reach v6's export_check): the coverage ladder,
    the side rows, min_air, the least flap flights and the exits re-derive
    from the zone graph alone; every requirement parses and its atoms
    resolve (§2.3), every generated skip is held and unconfirmed (D114), a
    crossing past a shut barrier needs a skip atom and none is reached
    without one, and no number could be a coordinate.  Each file's stamp is
    the current one (:func:`export.stamp`: the derive version, the draft
    tables and the level's own inputs), so a change to them owes a
    re-derive (``python -m devkit rando derive --all``)."""
    db = load_database()
    ids = export.hand_ids(db)
    assert sorted(db.derived) == ["a1", "a3", "a5", "a6", "airship", "d1", "d2", "e2", "e5", "e6", "e7", "f1", "f2", "f3",
                                  "f4", "f6", "life", "town", "w1", "w2", "w3", "w4"]
    assert [lvl for lvl, doc in db.derived.items() if export.read_text(export.path_of(lvl)) != export.dumps(doc)] == []
    assert {lvl: export.check_doc(doc, ids)[:5] for lvl, doc in db.derived.items()} == {lvl: [] for lvl in db.derived}
    assert {lvl: doc["_meta"]["stamp"] for lvl, doc in db.derived.items()} == {lvl: export.stamp(lvl) for lvl in db.derived}


REALM = ["a1", "a3", "a5", "a6", "airship", "d1", "d2", "e2", "e5", "e6", "e7", "f1", "f2", "f3", "f4", "f6", "life",
         "town", "w1", "w2", "w3", "w4"]


@functools.cache
def _planned(level: str):
    """``author.plan``'s phase 1 for one level of the realm, once a process:
    its own case and each case whose exits lead into it read the same plan."""
    from devkit.rando.draft import author
    return author.plan([level], realm=REALM).levels[level]


@functools.cache
def _route_marks() -> dict:
    """The vanilla route's proof marks (D169), as ``author()`` adds them, once a process."""
    from devkit.rando.draft import author
    return author.route_marks(load_database())


def _jumps(level: str, doc: dict, spec: dict) -> dict:
    """{(level, location): requires} for each location the derive reaches
    only by a jump from its zone and the authoring doesn't place by hand."""
    return {(level, loc["id"]): loc["requires"] for loc in doc["locations"]
            if loc.get("how") == "jump" and loc.get("zone") and loc.get("requires", "true") != "true"
            and loc["id"] not in spec.get("members", {}) | {x["id"]: 0 for x in spec.get("location", ())}}


def test_a_probed_walk_counts_as_exact_for_the_data_proofs_from_robustness_0_80():
    """D187 (owner, 2026-10-13): an L3 walk counts as a safe-tier (exact)
    connection for the data proofs once its string's robustness under
    jitter is at least 0.80 (X.7's default was 0.95), every leg of it:
    e2's Z028 -> Z000 record (0.812) would count, town's Z370 -> Z004 (0.0)
    doesn't."""
    from devkit.rando.draft import author

    def rec(*legs):
        return {"string": {"legs": [{"robustness": r} for r in legs]}}
    assert [author.robust_enough(rec(*legs)) for legs in ((0.812,), (0.80,), (0.79,), (0.95, 0.79), (0.0,), ())] == [
        True, True, False, False, False, False]


def test_a_held_pair_takes_every_guessed_path_between_two_kept_zones_out_of_logic_and_keeps_its_hand_edge():
    """AZ-476 (D722 row 11, the owner's X.78 demo: "my bad i meant row 11
    isnt possible"): d1's floor 7 to floor 6 on foot is a node edge the
    derive contracts from many guessed paths through zones that aren't
    kept. A ``[[held]]`` with ``pair = true`` takes every such path out of
    logic at every tier (R_phys keeps it), and the authoring's own edge
    between the two zones (there, death_keylock's) stays; a pair that no
    path joins is an issue."""
    from types import SimpleNamespace
    from devkit.rando.draft import author
    walk = [author.product(author.dnf("true"), [frozenset({author.ASSUMED})])] * 4
    lock = [author.product(author.dnf("button:x.lock"), [frozenset({author.ASSUMED})])] * 4
    L = SimpleNamespace(edges=[author.ZoneEdge("x.Z1", "x.Z9", walk, [frozenset()]),
                               author.ZoneEdge("x.Z9", "x.Z2", walk, [frozenset()]),
                               author.ZoneEdge("x.Z1", "x.Z2", lock, [frozenset()], hand=True)],
                        kept={"x.Z1", "x.Z2", "x.Z3"}, issues=[],
                        spec={"held": [{"from": "x.Z1", "to": "x.Z2", "pair": True},
                                       {"from": "x.Z1", "to": "x.Z3", "pair": True}]})
    L.pairs = author.contract(L)
    before = author.dnf_text(L.pairs[("x.Z1", "x.Z2")][0][0])
    author.hold_pairs(L)
    per, phys = L.pairs[("x.Z1", "x.Z2")]
    assert (before, [author.dnf_text(ts) for ts in per], phys, L.issues) == (
        "true", ["button:x.lock"] * 4, [frozenset()], ["held pair x.Z1 -> x.Z3: no path between two kept zones"])


def test_two_probed_walks_of_one_node_pair_at_different_kits_author_a_row_each_that_its_own_record_backs():
    """AZ-544 (D170): a probed row's one record must back every term of it
    (the loader refuses a record holding more than the row asks), so a
    walk at water 1 and one at no kit between the same nodes are two rows,
    each with its own walk's record, when the water walk is listed first;
    listed second, the kit-0 walk backs both terms and it adds no row."""
    import tomllib
    from types import SimpleNamespace

    from devkit.rando.draft import author
    from azurkit.tools.randomizer.planner.proofs import zoning

    walks = [{"from": "x.Z001", "to": "x.Z000", "kit": kit, "proven": {"by": "l3", "ref": f"{n}/{n * 12}@{'b' * 12}"}}
             for n, kit in (("a", "water>=1"), ("c", "true"))]
    got = []
    for spec in (walks, walks[::-1]):
        L = SimpleNamespace(name="x", doc={"zones": []}, spec={"probed": spec}, issues=[],
                            node_of={"x.Z001": "x_a", "x.Z000": "x_b"})
        records = {w["proven"]["ref"]: {"claim": {"from": w["from"], "to": w["to"], "zoning": zoning(L.doc)},
                                        "string": {"legs": [{"robustness": 1.0}]}} for w in spec}
        L.atomic = author.probed(L, [author.Atomic("x_a", "x_b", 1, frozenset({author.ASSUMED, ("water", 1)})),
                                     author.Atomic("x_a", "x_b", 1, frozenset({author.ASSUMED}))], records)
        got.append([(e["requires"], e["proven"]["ref"][0]) for row in author._edge_rows(L)
                    for e in tomllib.loads(row)["edge"]])
    assert got == [[("water>=1", "a"), ("true", "c")], [("true | water>=1", "c")]]


@pytest.mark.parametrize("level", REALM)
def test_authored_levels_are_their_authoring_and_their_nodes_lose_none_of_the_zone_graphs_reach(level):
    """Steps R1.8, R1.11b and R1.14b (docs/RANDOMIZER_DB.md §4.10, §17): each authored level's file,
    its movement file and each stub's exit into one, is what ``rando author`` writes from its
    derived data, ``tricks.toml`` and ``devkit/rando/draft/authoring/<level>.toml``, so
    an edit to any of them shows here.  And the authoring loses no reach:
    from a level's arrivals, at each movement tier and physically, with no
    item, air 1 and every counter (every flag and event credited, no skip),
    its nodes reach exactly the pool locations its zone graph reaches, so
    contracting the zones, joining them into nodes and dropping the terms
    another path gives keep every kit's reach.  A pool location the derive
    reaches only by a jump from its zone keeps that jump's requirement
    (Step R1.11a: the zone alone would make it free).  One case per level
    (Step 2.47), so the realm's plans spread over the workers: a level's
    text and its issues as ``author.author`` assembles them, its exits
    reading the nodes of the levels they lead into from the run's shared
    plans, and the stubs' exits into it."""
    import tomllib

    from devkit.rando.draft import author

    realm = sorted(p.stem for p in (author.DATA / "levels").glob("*.toml")
                   if tomllib.loads(p.read_text(encoding="utf-8"))["status"] == "authored")
    assert realm == REALM
    L = copy.copy(_planned(level))      # its own copy: the case sets its route marks
    shell = author.plan([], realm=REALM)
    into = sorted({x["dest_level"] for x in L.gen["exits"]} & set(REALM) - {level})
    R = dataclasses.replace(shell, levels={level: L} | {d: _planned(d) for d in into},
                            stub_node={n: node for n, node in shell.stub_node.items() if n not in REALM})
    L.route_proven = {loc: ref for loc, ref in _route_marks().items() if loc.split("/")[0] == level}
    files = {str(author.DATA / "levels" / f"{level}.toml"): author.level_text(R, L),
             str(author.DATA / "movement" / f"{level}.json"): author.movement_text(L)}
    files |= {p: text for p, text in author.stub_arrivals(R).items() if Path(p).stem not in REALM}
    issues = [f"{level}: {i}" for i in L.issues]
    assert (issues, sorted(p for p, text in files.items() if open(p, encoding="utf-8").read() != text)) == ([], [])
    jumps = _jumps(level, L.doc, L.spec)
    written = {(level, x["id"]): x.get("requires") for x in tomllib.loads(
        (author.DATA / "levels" / f"{level}.toml").read_text(encoding="utf-8")).get("location", [])}
    assert any(_jumps(n, author.read_derived(n), author.read_spec(n)) for n in REALM)
    assert {k: written.get(k) for k in jumps} == jumps

    def meets(term, kit):
        return all((kit.get(a[0], 0) >= a[1]) if isinstance(a[1], int) else a[0] != "skip" for a in term)

    def reached(src, adj):
        seen, todo = set(src), list(src)
        while todo:
            for v in adj.get(todo.pop(), ()):
                if v not in seen:
                    seen.add(v)
                    todo.append(v)
        return seen
    everything = {c: 9 for c in ("air", "water", "fire", "earth", "obsidian", "disca", "discw", "discf", "disce",
                                 "discl", "life", "staff", "ammo")}
    lost = {}
    zone_of = {loc["id"]: L.spec.get("members", {}).get(loc["id"], loc.get("zone")) for loc in L.doc["locations"]}
    for tier in (1, 2, 3, 4, 0):
        for kit in ({}, {"air": 1}, everything):
            zadj, nadj = {}, {}
            for e in L.edges:
                if any(meets(t, kit) for t in (e.phys + e.tiers[3] if tier == 0 else e.tiers[tier - 1])):
                    zadj.setdefault(e.frm, set()).add(e.to)
            for x in L.atomic:
                if (tier == 0 or 1 <= x.tier <= tier) and meets(x.term, kit):
                    nadj.setdefault(x.a, set()).add(x.b)
            zones = reached(L.arrival_zones, zadj)
            nodes = reached({L.node_of[z] for z in L.arrival_zones}, nadj)
            by_zone = {lid for lid, z in zone_of.items() if z in zones}
            by_node = {lid for lid, z in zone_of.items() if L.node_of.get(z) in nodes}
            if by_zone != by_node:
                lost[(level, tier, tuple(kit))] = sorted(by_zone ^ by_node)[:5]
    assert lost == {}
def test_a_respawning_barriers_crossing_stands_in_for_no_skip_term():
    """Step R1.11b: the authoring's transitive reduction keeps a term that
    gets past a respawning barrier another way (a confirmed skip), since
    the barrier's crossing leaves its destroy requirement out of its own
    term; before, f1's confirmed skip past flameSpout6 was dropped."""
    from devkit.rando.draft import author

    crossing = author.Atomic("a", "b", 1, frozenset(), ("f1.flameSpout6",))
    by_skip = author.Atomic("a", "b", 1, frozenset({("skip", "f1.flamespout6_air1")}))
    assert author.reduce_edges([crossing, by_skip]) == [crossing, by_skip]

def test_the_derive_stamp_moves_with_the_derive_version_the_tables_and_the_levels_own_inputs_only(tmp_path, monkeypatch):
    """Step R1.3d: airship's stamp changes with ``DERIVE_VERSION``, a draft
    table, its generated file, an exit into it (w1's) and, since Step R1.32,
    only the parts of its level file and ``tricks.toml`` the derive reads
    (``export.derive_inputs``: its nodes, its skips); not with another
    level's generated data or skip, a comment, an edge, or the derive's
    code, which a change bumps ``DERIVE_VERSION`` for."""
    data, draft = tmp_path / "data", tmp_path / "draft"
    shutil.copytree(export.DATA, data, ignore=shutil.ignore_patterns("derived"))
    shutil.copytree(export.DRAFT, draft, ignore=shutil.ignore_patterns("__pycache__"))
    for table in export.DRAFTS[1].glob("*.toml"):     # tiers.toml, the shipped draft's, beside blocker_families.toml
        shutil.copy(table, draft / table.name)

    def edit(path, f):
        path.write_text(f(path.read_text(encoding="utf-8")), encoding="utf-8")

    def edit_json(path, f):
        doc = json.loads(path.read_text(encoding="utf-8"))
        f(doc)
        path.write_text(json.dumps(doc), encoding="utf-8")

    def w1_exit_into_airship(doc):
        next(e for e in doc["exits"] if e["dest_level"] == "airship")["arrival"] = "elsewhere"
    edge, node = '\n[[edge]]\nfrom = "airship_a"\nto = "airship_b"\n', '\n[[node]]\nid = "airship_new"\n'

    def skip(level):
        return f'\n[[skip]]\nid = "{level}.new"\nlevel = "{level}"\n'
    edits = [
        ("a3's generated data", lambda: edit_json(data / "generated/a3.json", lambda d: d["_meta"].update(date="x")), False),
        ("w1's other exits", lambda: edit_json(data / "generated/w1.json", lambda d: d["_meta"].update(date="x")), False),
        ("the derive's code", lambda: edit(draft / "reach.py", lambda t: t + "\n# a comment\n"), False),
        ("DERIVE_VERSION", lambda: monkeypatch.setattr(export, "DERIVE_VERSION", export.DERIVE_VERSION + 1), True),
        ("tiers.toml", lambda: edit(draft / "tiers.toml", lambda t: t + "\n# a comment\n"), True),
        ("airship's generated data", lambda: edit(data / "generated/airship.json", lambda t: t + " "), True),
        ("airship.toml's comment", lambda: edit(data / "levels/airship.toml", lambda t: t + "\n# a comment\n"), False),
        ("airship.toml's edge", lambda: edit(data / "levels/airship.toml", lambda t: t + edge), False),
        ("airship.toml's node", lambda: edit(data / "levels/airship.toml", lambda t: t + node), True),
        ("tricks.toml's comment", lambda: edit(data / "tricks.toml", lambda t: t + "\n# a comment\n"), False),
        ("w1's skip", lambda: edit(data / "tricks.toml", lambda t: t + skip("w1")), False),
        ("airship's skip", lambda: edit(data / "tricks.toml", lambda t: t + skip("airship")), True),
        ("w1's exit into airship", lambda: edit_json(data / "generated/w1.json", w1_exit_into_airship), True),
    ]
    moved = {}
    for what, apply, _ in edits:
        before = export.stamp("airship", data, draft)
        apply()
        moved[what] = export.stamp("airship", data, draft) != before
    assert moved == {what: expect for what, _, expect in edits}


def test_a_trick_exit_goal_takes_its_trigger_in_any_state_and_costs_a_body_out_of_bounds_by_the_way_straight_in():
    """Step TD.4b (the trick-discovery plan §4's P1): a level exit's trigger as a goal on the light trick graph:
    reached when the body centre is inside its mesh, in the air too; a body in a zone costs by the graph as an
    ``ExitGoal`` would, and one outside every zone (out of bounds: over the void past the floor's edge) by the
    lesser of that and the straight way to the mesh (its horizontal gap at walk speed plus any rise to its bottom),
    which shrinks as it nears and is free from right above, and its guidance heads that way."""
    import types

    from devkit.rando.draft import l3_goal
    trigger = [(a, c, b) for a, b, c in _box(10, 0, 1.5, 16, 2.5, 4)]      # sticks out past the floor's edge (x 12)
    reach = Reach(_level(_quad(0, 0, 12, 6, 0), (trigger, {})), flights.Env.kept())
    reach.gen = {"exits": [{"id": "t/g0/r1", "gate_hint": "touch(p1)", "dest": "levels/x"}]}
    reach.zone_of = np.zeros(reach.W["logic"].nreg + 64, dtype=np.int64)      # every floor in zone t.Z000
    goal = l3_goal.TrickExitGoal(l3_goal.TrickRouter(reach, 0), "t/g0/r1")
    row = lambda x, z, state=2: types.SimpleNamespace(pos=(x, 1.0, z), state=state, hp=200, zone=None)  # noqa: E731
    floor, far, near, above = row(2.0, 1.0, 0), row(17.4, 9.0), row(16.8, 9.0), row(14.0, 9.0)
    assert goal.zone(floor) == "t.Z000" and goal.cost(floor) == l3_goal.RouteGoal.cost(goal, floor) < 1e6
    assert [goal.zone(r) for r in (far, near, above)] == [None] * 3
    assert goal.cost(far) < l3_goal.RouteGoal.cost(goal, far) and goal.cost(above) == 0.0 < goal.cost(near) \
        < goal.cost(far)
    assert goal.toward(far) == (l3_goal.heading_to((17.4, 1.0, 8.0), (16.0, 1.0, 4.0)), False)
    assert goal.reached(row(14.0, 3.0)) and goal.reached(row(11.0, 2.0, 0)) and not goal.reached(row(5.0, 1.0, 0))


def test_the_value_ranker_orders_sites_by_what_the_zones_near_them_add_and_the_probe_list_names_unreproduced_edges():
    """Step TD.4 (the trick-discovery plan §3.4, §3.6): a zone is worth 3 per location the logic doesn't reach at
    the kit, 2 per exit anchored there with no logic way in, 1 if no logic edge enters it and 1 per gate side; a
    site is worth the zones whose floors lie within 6 m of its anchor points; the queue goes by value, then id, and
    never drops a site (past the cut: "not attempted", with its rank); a saturated zone's logic edges that no
    transition reproduced are the probe list."""
    from devkit.rando.draft import sites, value
    reach = Reach(_level(_quad(0, 0, 10, 10, 0) + _quad(30, 0, 40, 10, 0)), flights.Env.kept())
    reach.zone_of = np.arange(reach.W["logic"].nreg + 64, dtype=np.int64)    # the two floors: t.Z000, t.Z001
    derived = {"zones": [{"id": "t.Z000", "anchors": {"exit": ["t/g0/r1"]}}, {"id": "t.Z001"}],
               "locations": [{"zone": "t.Z001", "min_air": {"frame_perfect": 3}}],
               "coverage": {"exits": {"t/g0/r1": {"least_air": {"frame_perfect": 1}}}},
               "edges": [{"from": "t.Z000", "to": "t.Z001", "kind": "walk"},
                         {"from": "t.Z000", "to": "t.Z001", "kind": "jump", "logic": False}],
               "gates": [{"separates_zones": [["t.Z001"]]}]}
    assert value.zone_values(derived, 0) == {"t.Z000": 3.0, "t.Z001": 4.0}
    assert value.zone_values(derived, 3) == {"t.Z000": 1.0, "t.Z001": 1.0}
    site = lambda k, x: sites.Site(f"t.slope.{k:03d}", "slope", np.zeros(0, np.int64), 1.0, 0.0,   # noqa: E731
                                   np.array([[x, 5.0, 0.5]]))
    found = [site(0, 5.0), site(1, 35.0), site(2, 80.0)]
    near = value.near_zones(reach, found)
    assert near == {"t.slope.000": {"t.Z000"}, "t.slope.001": {"t.Z001"}, "t.slope.002": set()}
    assert value.rank(found, near, value.zone_values(derived, 0), cut=2) == [
        {"id": "t.slope.001", "value": 4.0, "rank": 1}, {"id": "t.slope.000", "value": 3.0, "rank": 2},
        {"id": "t.slope.002", "value": 0.0, "rank": 3, "verdict": "not attempted"}]
    assert sites.probes(derived, ["t.Z000"], {}) == [{"from": "t.Z000", "to": "t.Z001", "kinds": ["walk"]}]
    assert sites.probes(derived, ["t.Z000"], {"t.Z000>t.Z001": [1, 40, 900]}) == sites.probes(derived, [], {}) == []


def test_the_goal_factories_share_one_router_per_reach_model_in_a_process(monkeypatch):
    """A search worker keeps a goal per target (``l3_pool.Worker.goal``); the factories (``make_goal``,
    ``make_exit_goal``, ``make_object_goal``) build each on one router per reach model and profile in the process
    (``shared_router``), not a router of its own: town's is 2.7 GB of phys_footprint, and a worker with six goals
    reached 17 GB in Step R1.16e's re-search."""
    from devkit.rando.draft import l3_goal
    loads = []
    reach = Reach(_level(_quad(-8, -8, 8, 8, 0.0)), flights.Env.kept())
    monkeypatch.setattr(l3_goal, "load_router", lambda path, prof="logic": loads.append((path, prof)) or Router(reach))
    a = l3_goal.make_goal("t-shared.pkl", (0.0, 0.0, 3.0), touch=[1.45, 1.9, 0.9])
    b = l3_goal.make_goal("t-shared.pkl", (1.0, 0.0, 3.0))
    assert a.R is b.R and loads == [("t-shared.pkl", "logic")]
    assert l3_goal.make_goal("t-shared.pkl", (1.0, 0.0, 3.0), prof="phys").R is not a.R and len(loads) == 2


def test_a_built_router_is_kept_by_its_content_key_beside_its_reach_model_and_built_again_once_the_model_changes(
        tmp_path, monkeypatch):
    """Step X.95 (X.93: router loads were 3-5 s of each sandbox; w1's router takes 16.5 s to build and 0.8 s to load):
    ``load_router`` keeps the router it built in ``routers/`` beside its reach model under ``router_key`` and loads
    it from there, equal, while the model file stands as it was; the model written again builds it again and its
    older key's file goes.  The key reads ``physics.py``, whose run and swim speeds the router's costs divide by
    (X.95's review: an edit there served the old costs)."""
    import pickle

    from azurkit.tools.randomizer import physics
    from devkit.rando.draft import l3_goal
    assert (route.WALK_MPS, route.SWIM_MPS) == (physics.RUN_SPEED, physics.SWIM_MPS)
    assert Path(physics.__file__).resolve() in {Path(l3_goal.__file__).resolve().parents[3] / rel
                                                for rel in l3_goal.ROUTER_CODE}
    reach = tmp_path / "t.pkl"
    reach.write_bytes(pickle.dumps(Reach(_level(_quad(-8, -8, 8, 8, 0.0)), flights.Env.kept())))
    builds, init = [], Router.__init__
    monkeypatch.setattr(Router, "__init__", lambda self, R, prof="logic": builds.append(prof) or init(self, R, prof))
    a, b = l3_goal.load_router(str(reach)), l3_goal.load_router(str(reach))
    kept = [p.name for p in (tmp_path / "routers").glob("*.pkl")]
    assert builds == ["logic"] and kept == [f"t-logic-{l3_goal.router_key(str(reach), 'logic')}.pkl"]
    assert np.array_equal(a.cost, b.cost) and np.array_equal(a.dst, b.dst) and np.array_equal(a.X, b.X)
    reach.write_bytes(reach.read_bytes())
    l3_goal.load_router(str(reach))
    assert builds == ["logic", "logic"] and [p.name for p in (tmp_path / "routers").glob("*.pkl")] == [
        f"t-logic-{l3_goal.router_key(str(reach), 'logic')}.pkl"] != kept


def test_rando_author_of_some_authored_levels_names_the_ones_left_out(capsys):
    """P6 (Step R1.19): ``rando author town w1 w2 w3 w4`` (TOOLS.md's old
    realm) exited with a bare ``ERROR: 'd1'``; it names every authored
    level left out, before any work."""
    assert (author_verb.main(["town", "w1", "w2", "w3", "w4"]), capsys.readouterr().err) == (1, (
        "ERROR: name every authored level together (their exits arrive in each other's nodes); missing: "
        + " ".join(sorted(set(REALM) - {"town", "w1", "w2", "w3", "w4"})) + "\n"))


def test_a_robustness_trial_rests_two_seconds_after_its_string_at_the_builds_frame_rate():
    """AZ-406: each of ``l3_search.robustness``'s jittered copies ends at
    rest for 60 ticks, 2 s at 30 fps but 0.5 s at 120, so a slow landing at
    a high build rate failed its trial; the rest is 2 s at any rate."""
    from devkit.sim.l3_search import Seg, jittered
    segs = [Seg(40, 0.0), Seg(40, 0.5, hold=24)]
    assert {rate: {tuple(jit[-1]) for jit in jittered(segs, trials=4, rate=rate)} for rate in (30.0, 60.0, 120.0)} \
        == {rate: {tuple(Seg(n, None))} for rate, n in ((30.0, 60), (60.0, 120), (120.0, 240))}


def test_rando_derive_check_in_its_process_pool_finds_the_committed_derived_data_fresh(usa_iso, capsys):
    """``python -m devkit rando derive airship --check`` re-derives airship (the
    one committed level that derives in seconds) from the vanilla ISO in a
    spawned worker (the default ``-j``, Step R1.3d) and finds its committed
    file equal byte for byte, writing nothing.  The stamp holds the derive
    version, not the code's hash, so this is the test that fails when a
    change to the derive's output forgets to bump ``DERIVE_VERSION``."""
    assert derive_verb.main(["airship", "--check", "--iso", str(usa_iso)]) == 0
    assert capsys.readouterr().out.endswith("1 derived files equal a fresh derivation\n")

