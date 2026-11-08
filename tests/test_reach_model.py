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
    ``load_router`` keeps the router it built in ``routers-azurkit/`` beside its reach model under ``router_key``
    and loads it from there, equal, while the model file stands as it was; the model written again builds it again
    and its older key's file goes, and Modkit's ``routers/`` beside it is never touched (Step 4.13d2: the L3 store
    is shared, and Modkit's keys are other keys).  The key reads ``physics.py``, whose run and swim speeds the
    router's costs divide by (X.95's review: an edit there served the old costs)."""
    import pickle

    from azurkit.tools.randomizer import physics
    from devkit.rando.draft import l3_goal
    assert (route.WALK_MPS, route.SWIM_MPS) == (physics.RUN_SPEED, physics.SWIM_MPS)
    assert Path(physics.__file__).resolve() in {Path(l3_goal.__file__).resolve().parents[3] / rel
                                                for rel in l3_goal.ROUTER_CODE}
    reach = tmp_path / "t.pkl"
    reach.write_bytes(pickle.dumps(Reach(_level(_quad(-8, -8, 8, 8, 0.0)), flights.Env.kept())))
    modkit = tmp_path / "routers" / "t-logic-0123456789ab.pkl"
    modkit.parent.mkdir()
    modkit.write_bytes(b"Modkit's router")
    builds, init = [], Router.__init__
    monkeypatch.setattr(Router, "__init__", lambda self, R, prof="logic": builds.append(prof) or init(self, R, prof))
    a, b = l3_goal.load_router(str(reach)), l3_goal.load_router(str(reach))
    kept = [p.name for p in (tmp_path / "routers-azurkit").glob("*.pkl")]
    assert builds == ["logic"] and kept == [f"t-logic-{l3_goal.router_key(str(reach), 'logic')}.pkl"]
    assert np.array_equal(a.cost, b.cost) and np.array_equal(a.dst, b.dst) and np.array_equal(a.X, b.X)
    reach.write_bytes(reach.read_bytes())
    l3_goal.load_router(str(reach))
    assert builds == ["logic", "logic"] and [p.name for p in (tmp_path / "routers-azurkit").glob("*.pkl")] == [
        f"t-logic-{l3_goal.router_key(str(reach), 'logic')}.pkl"] != kept
    assert modkit.read_bytes() == b"Modkit's router"


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


def test_a_leg_the_logic_has_no_way_for_searches_on_the_trick_graph_and_a_goal_with_no_vertex_on_its_direct_line(
        monkeypatch):
    """Step X.53 (AZ-593): ``l3_certify.leg_guide`` searches a leg on the logic's route graph, else, when the logic
    has no way from the leg's start and the light trick graph at the leg's air does, on the trick graph (the spec's
    profile ``trick``; it was the phys profile's, the envelope alone): with no air the 1.7 m ledge is the trick
    graph's, the floor's own goal stays the logic's.  A goal with no vertex (a point no floor is
    under) costs a row by its direct line, falling as the row nears and finite (it cost 1e6 everywhere), and the
    guide heads there."""
    import typing

    from devkit.rando.draft import l3_goal

    from devkit.reach import l3_certify as cert

    reach = Reach(_level(_quad(0, 0, 14, 4, 0) + _quad(14, 0, 18, 4, 1.7) + _side((14, 0), (14, 4), 0, 1.7)),
                  flights.Env.kept())
    graphs = {"logic": Router(reach), "trick": l3_goal.TrickRouter(reach, 0)}

    class Row(typing.NamedTuple):
        pos: tuple
        state: int
        hp: int = 200
        zone: str | None = None
    start = Row((2.0, 2.0, 1.0), 0)

    def make(target):
        return lambda prof: (l3_goal.RouteGoal(graphs[prof], target), {"kwargs": {"prof": prof}})
    prof, goal, spec = cert.leg_guide(make((17.0, 2.0, 1.7)), start)
    assert (prof, spec["kwargs"]["prof"], goal.R) == ("trick", "trick", graphs["trick"]) and goal.finite_at(start)
    assert cert.leg_guide(make((5.0, 2.0, 0.0)), start)[0] == "logic"
    nowhere = l3_goal.RouteGoal(graphs["logic"], (50.0, 50.0, 5.0))
    near = Row((5.5, 3.5, 1.0), 0)
    assert nowhere.cost(start) == pytest.approx(math.hypot(48.0, 48.0) / route.WALK_MPS + 4.0 / l3_goal.RISE_MPS)
    assert nowhere.cost(near) < nowhere.cost(start) < 1e6
    assert nowhere.toward(start) == (l3_goal.heading_to((2.0, 2.0, 0.0), (50.0, 50.0, 5.0)), False)
    assert nowhere.ahead(start)["stage"] == "no goal vertex"


def test_a_pickup_touch_counts_only_once_the_body_lands_alive_and_a_leg_starting_dead_or_doomed_is_refused(monkeypatch):
    """AZ-571, AZ-627: a pickup's goal (``l3_goal.RouteGoal`` on a point) counts a touch only when the body after it
    lives ``l3_goal.SURVIVE`` ticks and then lands alive (``survive``, ``l3_search.lands_alive`` in ``confirm``), at
    rest or, in the air, holding the string's last stick: on a floor whose far side of the item gives way two ticks
    after a body reaches it, so that the body falls 15 ticks (past the 10-tick window) and dies where it lands, the
    search passes over a seed string that touches it from that side (with no window it wins) and takes the one that
    touches it from the near side; a touch mid-jump over a gap the body clears only on the stick counts.
    ``devkit/reach/l3_certify.py``'s ``leg_start`` refuses a start whose row is dead (R1.29h's a3/g0/r1500 way backs:
    state 7) by an ``L3Error`` at site ``dead start``, and one in the air whose body dies before it lands, at rest
    and on its string's last stick (R1.29j's a3/g0/r1500 seed-4 way back), at site ``doomed start``; one that lands
    alive either way is searched, the simulator left at its start."""
    import typing

    from devkit.rando.draft import l3_goal
    from devkit.sim.l3 import L3Error, Pad
    from devkit.sim.l3_search import Limits, Seg, Segment, confirm, search

    class Row(typing.NamedTuple):
        pos: tuple
        state: int
        hp: int = 200
        zone: str | None = "t.Z000"

    class Fall:          # 0.25 m a tick along the stick; past x 4.3 at y > 2.2 the floor gives way on the third tick
        def __init__(self):
            self.s = (2.0, 2.5, 0)

        def save(self):
            return self.s

        def reset(self, s=(2.0, 2.5, 0)):
            self.s = s

        def step(self, pad):
            x, y, n = self.s
            h, m = pad.yaw + math.atan2(-pad.stick[0], pad.stick[1]), 0.25 * math.hypot(*pad.stick)
            x, y = (x, y) if n > 2 else (x - m * math.sin(h), y + m * math.cos(h))
            n = n + 1 if n or (y > 2.2 and x > 4.3) else 0
            self.s = (x, y, n)
            return Row((x, y, 1.0), 7 if n > 17 else 2 if n > 2 else 0, 0 if n > 17 else 200)

    goal = l3_goal.RouteGoal(Router(Reach(_level(_quad(0, 0, 10, 4, 0)), flights.Env.kept())), (5.0, 2.0, 0.0))
    far, near = [Seg(16, -math.pi / 2)], [Seg(2, math.pi), Seg(16, -math.pi / 2)]   # along y 2.5; to y 2 first
    sim = Fall()

    def won():
        return search(sim, sim.save(), Row((2.0, 2.5, 1.0), 0), goal, Limits(steps=500), seeds=[far, near])
    got = won()
    assert (goal.survive, got.why, [s.heading for s in got.segs]) == (l3_goal.SURVIVE, "a seed string",
                                                                       [math.pi, -math.pi / 2])
    goal.survive = 0
    assert [s.heading for s in won().segs] == [-math.pi / 2]
    from devkit.reach import l3_certify as cert

    class Drop:          # in the air: falls 20 more ticks, then dies there or stands; 12 on the stick clear the gap
        def __init__(self, doomed):
            self.s = (20, doomed, 0)

        def save(self):
            return self.s

        def reset(self, s=None):
            self.s = self.s if s is None else s

        def step(self, pad):
            left, doomed, moved = self.s
            self.s = (left - 1, doomed, moved := moved + any(pad.stick))
            body = (0.25 * moved, 0.0, 1.0)
            return Row(body, 0) if moved >= 12 else Row(body, 2) if left > 0 else Row(body, 7, 0) if doomed else \
                Row(body, 0)

    class Touch:         # a pickup 0.5 m along the stick, touched in the air
        settle, survive = 0, l3_goal.SURVIVE

        def reached(self, row):
            return row.pos[0] >= 0.5
    assert confirm(Drop(True), (20, True, 0), [Seg(2, 0.0)], 0.0, Touch()) == 2
    rows = {"alive": Row((0.0, 0.0, 1.0), 0), "dead": Row((0.0, 0.0, 1.0), 7, 0), "air": Row((0.0, 0.0, 1.0), 2),
            "held": Row((0.0, 0.0, 1.0), 2)}
    held = {"held": [Pad((0.0, 1.0), yaw=0.0), Pad()]}                  # the way there's stick, then a RECAST
    monkeypatch.setattr(cert, "start_of", lambda sim, seg: (sim.save(), rows[seg.snapshot], 0.0,
                                                            held.get(seg.snapshot, []), [rows[seg.snapshot]]))
    assert cert.leg_start(sim, Segment("alive"))[1] == rows["alive"]
    with pytest.raises(L3Error, match="the leg starts dead") as dead:
        cert.leg_start(sim, Segment("dead"))
    assert dead.value.site == "dead start"
    lands = Drop(False)
    assert cert.leg_start(lands, Segment("air"))[1] == rows["air"] and lands.save() == (20, False, 0)
    clears = Drop(True)
    assert cert.leg_start(clears, Segment("held"))[1] == rows["held"] and clears.save() == (20, True, 0)
    with pytest.raises(L3Error, match=r"starts off the floor \(state 0x2\) and dies at rest before it lands") as doom:
        cert.leg_start(Drop(True), Segment("air"))
    assert doom.value.site == "doomed start"


def test_a_stalled_search_names_where_its_best_cell_stalled_whether_it_still_fell_and_ends_at_a_plateau(monkeypatch):
    """Step X.52: a search whose best cost to go stops falling ends its seed after ``Limits.plateau`` steps (a cut
    of the same run: no part of the problem's shape) and names its stall: the least-cost cell's zone and the first
    region edge on the goal's cheapest way from it (``RouteGoal.ahead``: by id, kind and confidence; the walk to
    the goal when the way crosses none), never positions; it keeps its best cost to go as a curve.
    ``devkit/reach/l3_certify.py`` puts each stall at the plan's level edge it lies at and collects the legs not found into
    ``stalls.json``.  Step X.52b: the stall names its stage (a cell standing in no zone, AZ-538's, or on no floor
    of the model, Step X.53's; off the graph, with the zone the fallback steers to and the way on from there; a
    walk, with its first other zone; an edge),
    its row's state and whether the best cost still fell (its last 0.1 s fall's step and its fall over the last
    10,000 steps), and the explorer's result has the same record."""
    import typing

    from devkit.rando.draft import l3_goal
    from devkit.sim import l3_explore
    from devkit.sim.l3_search import Limits, search, stall_name

    reach = Reach(_level(_quad(0, 0, 6, 4, 0) + _quad(6, 0, 10, 4, 1.7) + _side((6, 0), (6, 4), 0, 1.7)),
                  flights.Env.kept())
    reach.zone_of = np.arange(reach.W["logic"].nreg + 64, dtype=np.int64)     # the floor t.Z000, the ledge t.Z001
    ledge = Router(reach)
    goal = l3_goal.RouteGoal(ledge, (9.0, 2.0, 1.7), air=1)
    flap = next(i for i, (_, _, e) in enumerate(ledge.edges) if e["kind"] == "flap")

    class Row(typing.NamedTuple):
        pos: tuple
        state: int
        hp: int = 200
        zone: str | None = "t.Z000"
        obs: object = None

    class Stuck:                   # every pad leaves the body where it stands, below the ledge
        def save(self):
            return 0

        def reset(self, s):
            pass

        def step(self, pad):
            return Row((3.0, 2.0, 1.0), 0)
    edge = {"zone": "t.Z000", "stage": "edge", "edge": flap, "kind": "flap", "conf": "modelled", "from": "t.Z000",
            "to": "t.Z001"}
    assert goal.ahead(Row((3.0, 2.0, 1.0), 0)) == edge
    assert goal.ahead(Row((9.0, 2.0, 2.7), 0))["kind"] == "walk"
    off = goal.ahead(Row((50.0, 50.0, 9.0), 2, zone=None))        # in the air far off the floors
    no_floor = goal.ahead(Row((50.0, 50.0, 1.0), 0, zone=None))   # standing there: on no floor of the model (X.53)
    assert (off["stage"], off["steer"], off["kind"]) == ("off the graph", "t.Z001", "walk")
    assert stall_name(off) == "off the graph, steered to t.Z001: the walk to the goal"
    assert no_floor == {**off, "stage": "on no floor"} and stall_name(no_floor) == f"on no floor: {stall_name(off)}"
    flat = Reach(_level(_quad(0, 0, 12, 4, 0)), flights.Env.kept())
    flat.zone_of = np.arange(flat.W["logic"].nreg + 64, dtype=np.int64)
    walk = l3_goal.RouteGoal(Router(flat), (11.0, 2.0, 0.0))
    lw = flat.W["logic"]
    lw.reg_soft[np.nonzero(walk.R.X[:len(lw.col)] > 6.0)[0]] = 1   # the floor's east half another region, t.Z001
    assert stall_name(walk.ahead(Row((3.0, 2.0, 1.0), 0))) == "the walk to the goal from t.Z000 into t.Z001"
    lim = Limits(steps=5000, plateau=300, exhaust=10**6, seg=4)
    res = search(Stuck(), 0, Row((3.0, 2.0, 1.0), 0), goal, lim, seed=1)
    cost = round(goal.cost(Row((3.0, 2.0, 1.0), 0)), 1)
    still = {"cost_s": cost, "ticks": 0, "state": 0, "last_fall": 0, "fall_10k_s": 0.0}
    assert res.why == f"plateau at #{flap} flap (modelled) t.Z000>t.Z001" and 300 <= res.steps < 5000
    assert res.summary()["stall"] == {**still, **edge} and res.curve[-1] == [res.steps, cost]
    assert lim.shape() == Limits(exhaust=10**6, seg=4).shape()
    ex = l3_explore.explore(Stuck(), 0, Row((3.0, 2.0, 1.0), 0), goal, l3_explore.Limits(steps=2000), seed=1)
    assert not ex.found and ex.summary()["stall"] == {**still, **edge}

    class Creeping(Stuck):         # the body creeps 0.1 s nearer every 125 steps for its first 1000, then stands
        n = 0

        def step(self, pad):
            self.n += 1
            return Row((3.0 + 5.6 * min(self.n, 1000) / 1000, 2.0, 1.0), 0)

    class Ahead:
        settle = 0

        def reached(self, r):
            return False

        def cost(self, r):
            return (10.0 - r.pos[0]) / 7

        def toward(self, r):
            return 0.0, False

        def cell(self, r):
            return (round(r.pos[0], 2),)
    crept = search(Creeping(), 0, Row((3.0, 2.0, 1.0), 0), Ahead(), lim, seed=1)
    assert crept.why == "plateau at the best cell" and 1000 < crept.steps < 5000   # counted from its last progress
    assert crept.stall["fall_10k_s"] == 0.8 and 0 < crept.stall["last_fall"] <= 1000     # still fell in its window
    flat_out = search(Creeping(), 0, Row((3.0, 2.0, 1.0), 0), Ahead(), Limits(steps=15_000, exhaust=10**6, seg=4),
                      seed=1)
    assert flat_out.stall["fall_10k_s"] == 0.0 and flat_out.stall["last_fall"] <= 1000   # flat for its last 10,000

    from devkit.reach import l3_certify as cert
    doc = {"node": [{"id": "t_low", "anchors": ["zone:t.Z000"]}, {"id": "t_top", "anchors": ["zone:t.Z001"]}],
           "edge": [{"from": "t_low", "to": "t_top"}]}
    steps = [(0, "t_low>t_top #0 assumed")]
    assert cert.plan_edge(doc, steps, {"from": "t.Z000", "to": "t.Z001"}) == "t_low>t_top #0 assumed"
    bare = {**edge, "from": None, "to": None}
    assert cert.plan_edge(doc, steps, bare) == "t_low>t_top #0 assumed"           # the stalled cell's zone's way out
    assert cert.plan_edge(doc, steps, {**bare, "zone": "t.Z009"}) is None
    run = {"index": 0, **res.summary(), "stall": {**res.stall, "plan": "t_low>t_top #0 assumed"}}
    results = {"k": {"legs": [{"n": 0, "goal": "the spot", "start_cost_s": cost, "runs": [run]}]},
               "found": {"legs": [{"n": 0, "goal": "the spot", "segs": [[4, 0.0, 0]], "runs": [run]}]}}
    assert cert.stalls(results) == {"k": [{"leg": 0, "goal": "the spot", "seed": 0, "why": res.why,
                                           "best_cost_s": cost, "start_cost_s": cost, **run["stall"]}]}


def test_l3s_reach_model_is_the_one_built_under_the_levels_current_zoning(tmp_path, monkeypatch):
    """AZ-362: the L3 tools' reach model (``devkit/reach/l3_certify.py``'s
    ``_reach_path``, which ``l3_contact`` and ``xemu_chain`` share: the
    route graph their searches, goals and route seeds read) is the one
    built under the level's derived zones: the first one built while its
    stamp is their zoning; after a re-derive renumbers them, one keyed by
    the new zoning, built once, while the old one stays for the records
    made on it."""
    import pickle
    import types

    from devkit.reach import l3_certify as cert
    from devkit.reach import models
    zones, built = [[0]], []
    monkeypatch.setattr(models, "folder", lambda: tmp_path / "reach")
    monkeypatch.setattr("devkit.rando.draft.author.read_derived", lambda level: {"zones": zones})
    monkeypatch.setattr("devkit.sim.ports.vanilla_iso", lambda: "vanilla.iso")
    monkeypatch.setattr("devkit.rando.derive.router", lambda iso, level: built.append(level) or types.SimpleNamespace(
        R=json.dumps(zones)))
    kept = tmp_path / "reach" / "w1.pkl"
    kept.parent.mkdir()
    kept.write_bytes(pickle.dumps("the first model"))
    kept.with_suffix(".stamp").write_text(cert.pr.zoning({"zones": zones}), encoding="utf-8")
    assert cert._reach_path("w1") == kept and built == []
    zones = [[1], [0]]                                   # a re-derive renumbers the zones
    fresh = cert._reach_path("w1")
    assert fresh != kept and built == ["w1"] and pickle.loads(fresh.read_bytes()) == json.dumps(zones)
    assert cert._reach_path("w1") == fresh and built == ["w1"]
    assert pickle.loads(kept.read_bytes()) == "the first model"


def test_r116s_l3_certify_list_sets_up_no_pickup_whose_location_gate_asks_world_state(tmp_path, monkeypatch):
    """Step R1.16: ``devkit/reach/l3_certify.py plan --tour`` lists a pickup or a counted item's reach whose location has
    its own gate a new game plus a hop doesn't give (w2's power behind the hose's blocker, event:w2.hose.won) as not
    set up, as it does a hop whose rule asks one, while a gate of element levels the tour's kit holds is searched."""
    from devkit.reach import l3_certify as cert
    kit = {"water": 1, "air": 3}
    certify = [{"key": k, "index": 0, "sphere": 3, "kind": kind, "level": goal.split("/")[0], "from": node,
                "to": node, "goal": goal, "kit": kit, "requires": None}
               for k, kind, goal, node in (("hose", "pickup", "w2/g0/r1346", "w2_z003"),
                                           ("free", "pickup", "w2/g0/r1351", "w2_z011"),
                                           ("air1", "reach", "w1/g0/r2078", "w1_z996"))]
    (tmp_path / "progress.json").write_text(json.dumps({"sample": [], "certify": certify}), encoding="utf-8")
    got = {t["key"]: t.get("skip") for t in cert.plan_tour(tmp_path / "progress.json", tmp_path / "out")}
    assert got["hose"].startswith("its location asks event:w2.hose.won") and got["free"] is got["air1"] is None, got


def test_a_pickup_proof_needs_xemu_to_take_the_goals_own_item(tmp_path, monkeypatch):
    """AZ-389: ``devkit/reach/l3_certify.py`` proves a skip to a pickup where
    xemu takes it only when the first difference is the inventory hash
    alone, xemu took the goal's own item (its vanilla item's inventory
    field changed, measured past the replay's own writes: not the day
    clock, the kit's element levels or the cast's fuel) and the body was
    equal until then (an error at tick 0 is one); a player-tick pickup
    proof recorded with the clock in the hash, or an older record whose
    raw offsets are only the kit's and the fuel's, no longer holds (a
    sitting replays it again), and ``pickups`` reports which proofs hold,
    reading the folder only."""
    import types

    from devkit.reach import l3_certify as cert
    from azurkit.tools.randomizer.live import recipes
    inv, one = 0x1000, (1).to_bytes(4, "little")
    kit = types.SimpleNamespace(writes=((0, b""), (inv + recipes.INV_LEVEL["air"], one)))   # the pad, then R2's air 1
    inv0, inv1 = bytes(recipes.INV_SAVED), bytearray(recipes.INV_SAVED)
    for o in (0, recipes.INV_LEVEL["air"], recipes.SLOT0 + 12 + 4):     # the clock, the kit's air, the cast's air fuel
        inv1[o:o + 4] = one
    assert cert.inventory_fields(inv0, bytes(inv1), inv, [kit]) == ["af"]
    o = recipes.frag_off("f", 3) + 4                                    # e5/g0/r4263's item, frag_fire_3
    inv1[o:o + 4] = one
    assert cert.inventory_fields(inv0, bytes(inv1), inv, [kit]) == ["af", "fgf3"]
    skip = {"key": "skip-a", "kind": "skip", "goal": "e5/g0/r4263"}
    cmp = {"first_diff": [120, ["inv_sha12"]], "first_err_tick": 121}
    assert cert.pickup_at(skip, cmp, ["af", "fgf3"]) == (120, "")
    assert [cert.pickup_at(t, c, fields)[0] for t, c, fields in (
        (skip, cmp, ["af"]),                                      # the cast's fuel alone
        (skip, cmp, ["fgf1"]),                                    # another item on the way
        (skip, {**cmp, "first_err_tick": 0}, ["fgf3"]),           # the body differs from tick 0
        (skip, {**cmp, "first_err_tick": 119}, ["fgf3"]),         # before the pickup
        ({**skip, "kind": "walk"}, cmp, ["fgf3"]))] == [None] * 5
    d = tmp_path / "certify"
    d.mkdir()
    reps = {"skip-a": {"l3_mode": "tick", "pickup_at": 1, "first_diff": [1, ["inv_sha12"]], "first_err_tick": 40,
                       "inventory_changed_offsets": [0, 1, 292], "proven": True},
            "skip-b": {"l3_mode": "scene", "pickup_at": 120, **cmp,             # the kit's earth and water, the fragment
                       "inventory_changed_offsets": [0, 1, 2, 4, 16, 292], "proven": True},
            "skip-c": {"l3_mode": "tick", "pickup_at": 50, "first_diff": [50, ["inv_sha12"]], "first_err_tick": None,
                       "inventory_fields": ["af", "fgf3"], "inv_sha12_from": 4, "proven": True},
            "skip-d": {"l3_mode": "scene", "pickup_at": 9, "first_diff": [9, ["inv_sha12"]], "first_err_tick": 10,
                       "inventory_changed_offsets": [0, 1, 2, 8, 40], "proven": True},   # the kit's air, its fuel
            "walk": {"l3_mode": "tick", "proven": True}}
    cert._write(d / "targets.json", {"targets": [{**skip, "key": k} for k in reps]})
    cert._write(d / "replays.json", reps)
    cert._write(d / "results.json", {k: {"verified": True} for k in reps})
    before = {p.name: p.read_bytes() for p in d.iterdir()}
    out = tmp_path / "pickups.json"
    cert.main(["pickups", str(d), "--out", str(out)])
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert {k: doc[k] for k in ("results", "replays", "proven", "pickup_proofs", "no_longer_hold")} == {
        "results": 5, "replays": 5, "proven": 5, "pickup_proofs": 4, "no_longer_hold": ["skip-a", "skip-d"]}
    assert doc["pickups"]["skip-d"]["why"] == "xemu's inventory changed ['af'], not the goal's ['fgf3']"
    assert {p.name: p.read_bytes() for p in d.iterdir()} == before
    with pytest.raises(SystemExit, match="outside DIR"):
        cert.main(["pickups", str(d), "--out", str(d / "pickups.json")])


def test_a_tour_replay_is_proven_by_its_outcome_and_a_near_placed_start_proves_no_hop(monkeypatch):
    """AZ-474: ``devkit/reach/l3_certify.py`` judges a tour target's xemu
    replay by its outcome: an exit only when its destination or its movie
    loads within the string or its tail (a load or a stall inside the
    string counts every tick before it), a pickup or a counted item's
    reach only when xemu takes the goal's own item, each with the body,
    state and HP L3's through the goal's tick; a walk by every tick equal
    to the string's end.  A placed start within 1 m of where the string
    first stands in the goal, or of where the load came when sooner, is
    near and proves no hop, unless the target is at a location; a tour
    replay judged before the rule is replayed again.  The tail stops at a load, at its outcome
    or when the player's own ticks stop, so a replay past an exit never
    hangs."""
    from devkit.reach import l3_certify as cert
    from devkit.sim.l3 import Row

    def run(step: float, n: int = 6) -> list:
        return [Row(k, (step * k, 0.0, 1.0), 0, 200, None, (), None) for k in range(n)]

    def xemu(rows, split: int | None = None, n: int | None = None) -> list[dict]:
        return [{"k": r.k, "pos": (r.pos[0] + (k == split), *r.pos[1:]), "state": r.state, "hp": r.hp}
                for k, r in enumerate(rows[:n])]

    exit_, pickup, walk = ({"key": "e", "kind": "exit", "tour": True, "exit": True, "goal": "w1/g0/r3353"},
                           {"key": "p", "kind": "pickup", "tour": True, "goal": "e5/g0/r4263"},
                           {"key": "w", "kind": "walk", "tour": True, "goal": ["w1.Z004"]})
    entry, far, near = {"at": "entry", "k": 6}, run(1.0), run(0.1)

    def verdict(t, rows, got, stop=entry, tail=None, fields=(), placed=True) -> tuple:
        j = cert.judge(t, rows, got, goal_at=len(rows) - 1, start_at=0, stop=stop, tail_=tail, fields=list(fields),
                       placed=placed)
        return j["proven"], j["near"], j["start_goal_band"]
    town = {"at": "load", "k": 3, "level": "levels/town"}
    assert verdict(exit_, far, xemu(far), tail=town) == (True, False, "3-10 m")
    assert verdict(exit_, far, xemu(far), tail={"at": "ticks", "k": 150})[0] is False      # the trigger, no load
    assert verdict(exit_, far, xemu(far), tail={**town, "level": "levels/water/w2"})[0] is False
    assert verdict(exit_, far, xemu(far, n=4), stop={**town, "k": 4})[0] is True          # the game's field is wider
    assert verdict(exit_, far, xemu(far, split=2), tail=town)[0] is False                 # pushed off before it
    assert verdict(exit_, near, xemu(near), tail=town) == (False, True, "<=1 m")            # the placement crossed it
    assert verdict(exit_, near, xemu(near), tail=town, placed=False)[0] is True            # the snapshot's own spot
    assert verdict(exit_, far, xemu(far, n=1), stop={**town, "k": 1}) == (False, True, "<=1 m")   # placed in its field
    movie = {**exit_, "goal": "d1/g0/r2271"}                                                # bink:death.bik, then d2
    assert verdict(movie, far, xemu(far), tail={**town, "level": "bink:death.bik"})[0] is True
    assert verdict(movie, far, xemu(far, n=4), stop={"at": "stall", "k": 4},
                   tail={**town, "level": "levels/death/d2"})[0] is True                  # the movie stalled the replay
    assert verdict(pickup, far, xemu(far), tail={"at": "until", "k": 9}, fields=["af", "fgf3"])[0] is True
    assert verdict(pickup, near, xemu(near), fields=["fgf3"]) == (True, True, "<=1 m")    # standing on it is the claim
    assert verdict(pickup, far, xemu(far), tail={"at": "ticks", "k": 150}, fields=["af"])[0] is False
    assert verdict(pickup, far, xemu(far, split=4), fields=["fgf3"])[0] is False
    reach = {**pickup, "kind": "reach"}                                                     # a counted item's spot
    assert verdict(reach, far, xemu(far), fields=["fgf3"])[0] is True
    assert verdict(reach, far, xemu(far))[0] is False                                     # the body alone: no item
    assert verdict(walk, far, xemu(far))[0] is True
    assert verdict(walk, far, xemu(far, n=4), stop={**town, "k": 4})[0] is False          # an unplanned load
    assert verdict(walk, near, xemu(near)) == (False, True, "<=1 m")
    assert cert.stale(walk, {"proven": True}) and cert.stale(walk, {"proven": True, "rule": cert.RULE}) is None
    assert cert.stale(walk, {"proven": True, "rule": "az474"}) is None                   # AZ-483 left walks alone
    assert cert.stale(pickup, {"proven": True, "rule": "az474"}) and cert.stale(exit_, {"rule": "az474"})
    assert cert.stale({**walk, "tour": None}, {"proven": True}) is None

    import struct
    import types

    from devkit.sim.l3 import PLAYER_UPDATE

    def tail(stops: list[dict], until=lambda: False, wait_s: float = 60.0) -> dict:
        it, clock = iter(stops), itertools.count()
        cur = {"r": next(it)}
        g = types.SimpleNamespace(regs=lambda: cur["r"], read=lambda va, n: struct.pack("<d", next(clock)),
                                  cmd=lambda c: None, cont=lambda: None)
        sb = types.SimpleNamespace(halt=lambda: g, write_pad=lambda pad: None, _halted=True,
                                   _wait=lambda s: cur.update(r=next(it)) or True)
        xo = types.SimpleNamespace(LOAD_LEVEL=0x53750, arm=lambda g_, v: None, resume=lambda g_, v: None,
                                   level_path=lambda g_: "levels/town")
        return cert.tail(sb, xo, 0x100, until, wait_s=wait_s)
    own, other, load = {"eip": PLAYER_UPDATE, "ecx": 0x100}, {"eip": PLAYER_UPDATE, "ecx": 0x200}, {"eip": 0x53750}
    assert tail([own, own, load]) == {"at": "load", "k": 2, "level": "levels/town"}
    calls = itertools.count()
    assert tail([own] * 9, until=lambda: next(calls) == 3) == {"at": "until", "k": 3}
    assert tail([other] * 9, wait_s=0.0) == {"at": "stall", "k": 0}         # another entity's updates alone


def test_an_outcome_inside_the_placements_settle_proves_nothing_and_whole_steps_read_l3s_own_take(monkeypatch):
    """AZ-486: ``devkit/reach/l3_certify.py``'s judge counts an item taken at or before the settle's last row as
    ``settle`` (the placement took it): no proof, not even near.  In player ticks the take is the first tick
    xemu's inventory hash differs from L3's; in whole steps L3 takes the item too, so the hashes agree and the take
    is the row L3's own inventory gained it (``outcome_at``)."""
    import types

    from devkit.reach import l3_certify as cert
    from devkit.sim.l3 import Row

    def obs(h):
        return types.SimpleNamespace(inv_sha12=h)

    def rows(took_l3=None):                    # the settle (rows 0-2), then the string, 1 m a tick
        return [Row(k, (float(k), 0.0, 1.0), 0, 200, None, (), None, obs=obs("b" if took_l3 is not None and k >= took_l3
                    else "a")) for k in range(8)]

    def got(rs, took_x):                       # xemu: the same body, its inventory changed from took_x on
        return [{"pos": r.pos, "state": r.state, "hp": r.hp, "obs": obs("b" if k >= took_x else "a")}
                for k, r in enumerate(rs)]
    pickup = {"key": "p", "kind": "pickup", "tour": True, "goal": "e5/g0/r4263"}

    def verdict(rs, gs, outcome_at=None) -> tuple:
        j = cert.judge(pickup, rs, gs, goal_at=6, start_at=2, stop={"at": "entry"}, tail_=None, fields=["fgf3"],
                       placed=True, outcome_at=outcome_at)
        return j["proven"], j["settle"], j["near"], j["taken_at"]
    tick = rows()                                                       # player ticks: L3 never takes it
    assert verdict(tick, got(tick, 5)) == (True, False, False, 5)
    assert verdict(tick, got(tick, 2)) == (False, True, False, 2)       # taken in the settle
    scene = rows(took_l3=5)                                             # whole steps: L3 took it with xemu
    assert verdict(scene, got(scene, 5), outcome_at=5) == (True, False, False, 5)
    early = rows(took_l3=1)
    assert verdict(early, got(early, 1), outcome_at=1)[:2] == (False, True)
    late = rows(took_l3=6)
    assert verdict(late, got(late, 5), outcome_at=6)[3] == 5            # xemu took it sooner than L3
    exit_ = {"key": "e", "kind": "exit", "tour": True, "exit": True, "goal": "w1/g0/r3353"}
    town = {"at": "load", "k": 3, "level": "levels/town"}
    j = cert.judge(exit_, tick, got(tick, 99), goal_at=None, start_at=2, stop={"at": "entry"}, tail_=town,
                   fields=[], placed=True)                                 # loaded in the tail, never in the trigger
    assert (j["proven"], j["settle"]) == (False, False) and "before the goal's" in j["why"]
    j = cert.judge(exit_, tick, got(tick, 99)[:2], goal_at=None, start_at=2, stop={**town, "k": 2}, tail_=None,
                   fields=[], placed=True)                                 # loaded in the settle
    assert (j["proven"], j["settle"]) == (False, True)


def test_an_item_taken_on_the_way_is_not_the_goals_so_the_body_must_match_through_the_goal(monkeypatch):
    """AZ-699: ``devkit/reach/l3_certify.py``'s judge reads a take past the settle and more than a tick before the
    string stands in the goal's touch as another item on the way (an obsidian elsewhere), not the goal's, so the
    replay must keep L3's body through the goal's tick: one that parts after that take and before the goal is not
    proven.  The goal's own take must come too: xemu's inventory changes again from a tick before the touch on (or
    in a tail that ran with the goal's fields unchanged).  A take a tick before the goal's is still the goal's (the
    touch a tick ahead).  An item's replay judged before this rule (``az483``) is replayed again."""
    import types

    from devkit.reach import l3_certify as cert
    from devkit.sim.l3 import Row

    def obs(h):
        return types.SimpleNamespace(inv_sha12=h)
    rows = [Row(k, (float(k), 0.0, 1.0), 0, 200, None, (), None, obs=obs("a")) for k in range(12)]
    pickup = {"key": "p", "kind": "pickup", "tour": True, "goal": "town/g1/r1611"}

    def verdict(took_x: int, split: int, again: int = 99, tail_=None) -> tuple:
        got = [{"pos": (r.pos[0] + (k >= split), *r.pos[1:]), "state": r.state, "hp": r.hp,
                "obs": obs("c" if k >= again else "b" if k >= took_x else "a")} for k, r in enumerate(rows)]
        j = cert.judge(pickup, rows, got, goal_at=10, start_at=2, stop={"at": "entry"}, tail_=tail_,
                       fields=["obsi"], placed=True)
        return j["proven"], j["taken_at"], j["why"]
    assert verdict(4, 6, again=9) == (False, None, "the body, state or HP differ from tick 6, before the goal's "
                                                   "(tick 10)")
    assert verdict(4, 99, again=9) == (True, None, None)            # the goal's own take, a tick ahead of its touch
    assert verdict(4, 99) == (False, None, "the goal's item not taken: xemu's inventory changed on the way (tick 4) "
                                           "and not from tick 9")    # the same field's take on the way alone
    assert verdict(4, 99, tail_={"at": "until", "k": 0})[0] is False      # the tail stopped on the way's take
    assert verdict(4, 99, tail_={"at": "until", "k": 3})[0] is True       # the goal's own, taken in the tail
    assert verdict(9, 9) == (True, 9, None)                         # taken a tick ahead, parted after it
    assert cert.stale(pickup, {"proven": True, "rule": cert.RULE}) and cert.stale(
        pickup, {"proven": True, "rule": cert.ITEM_RULE}) is None
    assert cert.stale({**pickup, "kind": "exit", "exit": True}, {"rule": cert.RULE}) is None


def test_a_pickup_goal_is_the_items_own_touch_round_where_it_rests_and_whole_steps_see_it_taken(monkeypatch):
    """AZ-483: a pickup's L3 goal is the game's touch (0x8C520 -> 0x60870 -> the critter's 0x418B0): the body
    centre, HP above 0, in any state, inside the ellipsoid of radius R = r * pcr / cr + 1 and half-height
    Z = r * aspect + 1 (r = collisionRadius * scale, config.xbr's critters_engine, its defaults when empty) round
    the item's centre, where it rests: on the surface below its point, hz = r * aspect over it, unless its bottom
    already reaches that surface.  A verify in whole steps reads L3's own inventory: the item counts taken when its
    field grows past the rows' own writes (the kit's levels), not when the cast spends fuel."""
    import types

    from devkit.rando.draft import l3_goal
    from azurkit.tools.randomizer.live import recipes

    cells = {("obsidian", "collisionRadius"): 0.3, ("obsidian", "collisionAspectRatio"): 2.0,
             ("obsidian", "scale"): 1.5, ("bare", "name"): None}
    engine = types.SimpleNamespace(
        col_names=lambda: ["obsidian", "bare"],
        find_cell=lambda sp, prop: None if cells.get((sp, prop)) is None else
        types.SimpleNamespace(type_code=1, double_value=cells[(sp, prop)]))
    assert l3_goal.item_touch(engine, "obsidian") == pytest.approx((1.45, 1.9, 0.9))
    assert l3_goal.item_touch(engine, "bare") == (2.0, 2.0, 1.0) and l3_goal.item_touch(engine, "key") is None
    reach = Reach(_level(_quad(-8, -8, 8, 8, 0.0)), flights.Env.kept())
    router = Router(reach)
    assert l3_goal.item_centre(router.lv, (1.0, 2.0, 3.0), 0.9) == (1.0, 2.0, pytest.approx(0.9))   # it falls
    assert l3_goal.item_centre(router.lv, (1.0, 2.0, 0.5), 0.9) == (1.0, 2.0, 0.5)    # its bottom is on the floor
    goal = l3_goal.RouteGoal(router, (0.0, 0.0, 3.0), touch=(1.45, 1.9, 0.9))
    assert goal.touch_shape == (1.45, 1.9, 0.9) and goal.dist.min() == 0.0
    row = lambda x, z, state=0, hp=200: types.SimpleNamespace(pos=(x, 0.0, z), state=state, hp=hp, zone=None)  # noqa
    assert [goal.reached(row(x, 0.9)) for x in (1.4, 1.5)] == [True, False]       # the centre's height
    assert [goal.reached(row(0.0, 0.9 + dz)) for dz in (1.85, 1.95, -1.85)] == [True, False, True]
    assert goal.reached(row(0.5, 2.0, state=2)) and not goal.reached(row(0.5, 0.9, hp=0))   # airborne; no HP
    old = l3_goal.RouteGoal(router, (0.0, 0.0, 3.0))                                 # no touch: 0.75 m round it
    assert not old.reached(row(1.4, 1.0)) and old.touch_shape is None

    from devkit.reach import l3_certify as cert
    inv, mem = 0x1000, bytearray(recipes.INV_SAVED)
    sim = types.SimpleNamespace(read=lambda va, n: bytes(mem[va - inv:va - inv + n]))

    def put(field_off: int, v: int) -> None:
        mem[field_off:field_off + 4] = v.to_bytes(4, "little", signed=True)
    before = bytes(mem)
    kit = types.SimpleNamespace(writes=((0, b""), (inv + recipes.INV_LEVEL["water"], (1).to_bytes(4, "little"))))
    put(recipes.INV_LEVEL["water"], 1)                                                 # the kit's water level
    assert not cert.gained(sim, inv, {"level.water"}, before, [kit])
    put(recipes.SLOT0 + 12 + 4, -1)                                                    # the cast spends air fuel
    assert not cert.gained(sim, inv, {"ef", "af", "ff", "wf"}, before, [kit])
    put(recipes.SLOT0 + 12 * recipes.SLOTS.index("obsi") + 4, 1)                       # an obsidian taken
    assert cert.gained(sim, inv, {"obsi"}, before, [kit])
    obs = {"key": "p", "kind": "pickup", "goal": "town/g1/r1617"}
    monkeypatch.setattr(cert, "_engine", lambda: engine)
    assert cert.touch_of(obs) == pytest.approx((1.45, 1.9, 0.9)) and cert.touch_of({**obs, "kind": "walk"}) is None
    assert cert.touch_of({**obs, "kind": "spot"}) == pytest.approx((1.45, 1.9, 0.9))     # a plan --spots spot too


def test_an_r6_start_stands_in_the_items_own_cell_outside_its_touch_or_in_the_room_its_zone_settles_in(monkeypatch):
    """AZ-488: ``devkit/reach/l3_certify.py`` places (R6) a pickup's or a counted item's start in the cell its generator
    stands in (the level's cell list, which the place struct names), not the one the snapshot stood in, since the
    item spawns only while the player is in its room; on the start zone's nearest sample whose body stands outside
    1.2 times the item's touch (the placement would take it in the settle).  A ``plan --spots`` spot is at a
    location too (Step R1.29b: placed with the snapshot's room, R1.29's f1/g0/r1403 key and f3/g0/r2390 obsidian
    were touched in whole steps and never taken); placed (``--placed``), it stands 2 m out of the touch, so the
    string walks to it.  Any other target keeps the player's cell and the nearest sample.  AZ-382 (Step R1.29e):
    where neither cell settles in the start zone, every other cell of the level's list is tried, the rooms whose
    locations stand nearest the sample first (a wrong room's placement can settle).  AZ-531 (Step R1.29f): where
    the route graph has no way (every cost infinite) the samples nearest the item come first, not the zone's most
    open ones anywhere in it (w4's off-graph obsidians never started)."""
    import types

    from devkit.reach import l3_certify as cert
    town = json.loads((Path(cert.DATA_DIR) / "generated" / "town.json").read_text(encoding="utf-8"))
    obs = {"key": "p", "kind": "reach", "level": "town", "goal": "town/g1/r1617", "start": "town.Z001"}
    want = town["cells"].index("MainCellShape")
    assert cert.item_cell(obs) == want and cert.item_cell({**obs, "kind": "walk"}) is None
    spot = {**obs, "kind": "spot", "kit_l3": True, "back": ["town.Z001"]}
    assert cert.item_cell(spot) == want

    class Sim:
        entity, placed = 0x100, []

        def reset(self):
            self.at = (-5.0, 0.0, 1.0)                     # the snapshot's spot, outside the start zone

        def run(self, pads):
            return [types.SimpleNamespace(state=0, pos=self.at)]

        def u32(self, va):                                 # the critter, its cell pointer: cell 7
            return {0x120: 0x2000, 0x2000 + 0x158: 0x1000 + 7 * 0xB4}.get(va, 0)

        def teleport(self, p, yaw, cell):
            self.placed.append(cell)
            self.at = (p[0], p[1], p[2] + 1.0)
    monkeypatch.setattr(cert.recipes, "chain", lambda u32: {"cells": 0x1000})
    router = types.SimpleNamespace(
        zone_at=lambda feet, prefer_water=False: "town.Z001" if feet[0] >= 0 else None,
        R=types.SimpleNamespace(zone_of=np.array([1])), ns=3, node=np.zeros(3, dtype=np.int64),
        w=types.SimpleNamespace(nreg=0), wg=types.SimpleNamespace(lab=np.zeros(0, dtype=np.int64), col=[]),
        clear=np.zeros(3), pt=lambda v: (float(v), 0.0, 0.0))
    goal = types.SimpleNamespace(dist=np.array([0.0, 1.0, 2.0, 3.0]), nxt=np.array([-1, -1, -1, -1]),
                                 touch=((0.0, 0.0, 1.0), 1.45, 1.9), gp=None)
    router.ns, router.node, router.clear = 4, np.zeros(4, dtype=np.int64), np.zeros(4)
    got = cert._start(Sim(), router, obs, goal)
    assert (got["sample"], got["cell"], Sim.placed) == (2, want, [want])       # 0 and 1 stand in its touch
    Sim.placed.clear()                                                         # a placed spot: the item's cell,
    small = types.SimpleNamespace(**{**vars(goal), "touch": ((0.0, 0.0, 1.0), 0.5, 1.9)})   # 2 m out of its touch
    router.X, router.Y = np.arange(4.0), np.zeros(4)                           # the samples' places (router.pt)
    got = cert._start(Sim(), router, spot, small, placed=True)                 # (2.5 m on: never near, AZ-474)
    assert (got["sample"], got["cell"], Sim.placed) == (3, want, [want])
    Sim.placed.clear()                                                         # it spawns at its point, 1 m over
    assert cert._start(Sim(), router, obs, types.SimpleNamespace(**{**vars(goal), "gp": (1.0, 0.0, 1.5)}))[
        "sample"] == 3                                                         # 2 stands in the spawn's touch
    Sim.placed.clear()                                                         # no sample settles in its cell:
    teleport = Sim.teleport                                                    # the start zone's room is another
    Sim.teleport = lambda self, p, yaw, cell: teleport(self, (p[0] if cell == 7 else -9.0, *p[1:]), yaw, cell)
    assert (cert._start(Sim(), router, obs, goal)["cell"], Sim.placed[-1]) == (7, 7)
    Sim.placed.clear()                                                         # nor in the snapshot's: a third
    Sim.teleport = lambda self, p, yaw, cell: teleport(self, (p[0] if cell == 4 else -9.0, *p[1:]), yaw, cell)
    assert cert._start(Sim(), router, obs, goal)["cell"] == 4 and Sim.placed[-3:] == [2, 3, 4]   # room of town's 8
    sewer = {x["id"] for x in town["locations"] if x.get("cell") == "SewerCellShape"}       # its locations by it
    router.lv = types.SimpleNamespace(rec_points=lambda i: ([(2.0, 0.0, 0.0) if i in sewer else (90.0, 0.0, 0.0)], 0))
    Sim.teleport = lambda self, p, yaw, cell: teleport(self, (p[0] if cell in (0, 5) else -9.0, *p[1:]), yaw, cell)
    assert cert._start(Sim(), router, obs, goal)["cell"] == town["cells"].index("SewerCellShape") != 0
    del router.lv

    def hangs(self, p, yaw, cell):                                             # whole steps hang on sample 2's
        if p[0] == 2.0:                                                        # settle (Step R1.29b): the next
            raise cert.l3.L3Error("0x54800 did not return")                    # sample starts it
        teleport(self, p, yaw, cell)
    Sim.teleport = hangs
    assert cert._start(Sim(), router, obs, goal)["sample"] == 3
    Sim.teleport = teleport
    Sim.placed.clear()                                                         # AZ-531: off the route graph the
    router.Z, router.clear = np.zeros(4), np.array([0.0, 0.0, 0.0, 1.0])       # nearest the item outside its
    off = types.SimpleNamespace(**{**vars(goal), "dist": np.full(4, np.inf)})  # touch, not the most open
    assert cert._start(Sim(), router, obs, off)["sample"] == 2
    router.clear = np.zeros(4)
    Sim.placed.clear()
    walk = cert._start(Sim(), router, {**obs, "kind": "walk"}, types.SimpleNamespace(dist=goal.dist, nxt=goal.nxt))
    assert (walk["sample"], walk["cell"]) == (0, 7)
    trigger = cert.ExitGoal.__new__(cert.ExitGoal)                         # an exit: outside its trigger too
    trigger.reached = lambda row: row.pos[0] < 0.5
    trigger.dist, trigger.nxt = goal.dist, goal.nxt
    assert cert._start(Sim(), router, {**obs, "kind": "exit", "exit": True}, trigger)["sample"] == 1


def test_an_exit_or_touch_goal_needs_the_body_centre_inside_its_shape_and_whole_steps_see_the_switch_fire(monkeypatch):
    """AZ-483: an exit's L3 goal is the game's touch of its trigger (the player's query 0x60BD0 at the body centre,
    a platform's 0x79D30 -> 0xD2A40): the body centre inside the mesh, the first triangle straight above it facing
    down (the tern's winding), not the feet in the column 2 m under it; a timer gate's ``{>=N}`` s is its ``wait``
    in ticks.  A touch event's approach takes the same test.  In whole steps ``_verify`` ends at the levelSwitch's
    fire (0x6F050) as the outcome, after a tail when the string alone doesn't fire it (a fire of the exit's own
    level there meets the leg; another switch's doesn't), and the chain reads a touch event's done from its shape's
    ``touch`` (no longer "the approach stood on it")."""
    import types

    from devkit.rando.draft import l3_goal
    trigger = [(a, c, b) for a, b, c in _box(4, 0, 1.5, 8, 2.5, 4)]      # a raised field, the tern's winding
    reach = Reach(_level(_quad(0, 0, 12, 6, 0), (trigger, {})), flights.Env.kept())
    reach.gen = {"exits": [{"id": "t/g0/r1", "gate_hint": "touch(p1)", "dest": "levels/x"},
                           {"id": "t/g0/r2", "gate_hint": "timer[T](switch[S]{on=touch(p1)}.goal).currentTime{>=8}"
                                                          "{w=1,f=0.01}", "dest": "levels/y"}]}
    router = Router(reach)
    goal, timed = l3_goal.ExitGoal(router, "t/g0/r1"), l3_goal.ExitGoal(router, "t/g0/r2")
    row = lambda z, x=6.0: types.SimpleNamespace(pos=(x, 1.0, z), state=0, hp=200, zone=None)  # noqa: E731
    assert [goal.reached(row(z)) for z in (1.0, 2.0, 4.5)] == [False, True, False]   # standing under it: no touch
    assert not goal.reached(row(2.0, x=3.0)) and goal.dist.min() == 0.0
    assert (goal.wait, timed.wait) == (0, 240)
    pad = l3_goal.ObjectGoal(router, "p1", radius=0.0, inside=True)
    assert pad.reached(row(2.0)) and not pad.reached(row(1.0))

    from devkit.reach import l3_certify as cert
    from devkit.xemu import chain as xc
    from devkit.sim.l3 import Row

    class Sim:
        scene, k = True, 0

        def __init__(self, fire_at, level="levels/x"):
            self.fires, self.fire_at, self.level = [], fire_at, level

        def reset(self):
            self.k = 0

        def step(self, pad):
            self.k += 1
            if self.k == self.fire_at:
                self.fires.append((self.k, self.level, None))
            return Row(self.k, (6.0, 1.0, 2.0 if self.k >= 4 else 1.0), 0, 200, None, (), None)
    monkeypatch.setattr(cert, "start_of", lambda sim, seg: (None, None, 0.0, ["s"], [Row(0, (0.0, 1.0, 1.0), 0, 200,
                                                                                           None, (), None)]))
    monkeypatch.setattr(cert, "_router", lambda level: router)
    t = {"key": "e", "kind": "exit", "exit": True, "goal": "t/g0/r1", "kit": {}}
    legs = [{"snapshot": "s", "teleport": None, "target": "t/g0/r1", "segs": [(6, 0.0, 0)]}]
    v = cert._verify(Sim(fire_at=4), t, legs, router, tail=10)
    assert (v["outcome_at"], v["outcome"], len(v["rows"]), v["goal_at"], v["ok"]) == (4, ["levels/x", None], 5, [4],
                                                                                         [True])
    v = cert._verify(Sim(fire_at=9), t, legs, router, tail=10)             # the fire came in the tail: the leg met
    assert (v["string_end"], v["outcome_at"], len(v["rows"]), v["ok"], v["goal_at"]) == (7, 9, 10, [True], [4])
    v = cert._verify(Sim(fire_at=9, level="levels/z"), t, legs, router, tail=10)      # another switch's fire
    assert (v["outcome_at"], v["outcome_own"], v["ok"]) == (9, False, [False])
    assert cert._verify(Sim(fire_at=99), t, legs, router, tail=10)["outcome_at"] is None

    seen = iter([0.0, 0.0, 1.0])
    m = types.SimpleNamespace(get=lambda rec, attr: next(seen, 1.0), stick=None, by={"BeamShape": [0]},
                              g=types.SimpleNamespace(names=["BeamShape"], links=lambda i: []))

    def run(n, stick=None, on_tick=None, hook_at=None):
        for _ in range(n):
            if "stop" in on_tick(None, None, []):
                break
    m.run = run
    chain = xc.Chain.__new__(xc.Chain)
    assert chain.touched(m, "BeamShape") == {"done": True, "checked": True, "ticks": 2}
    m.get = lambda rec, attr: 0.0
    assert chain.touched(m, "BeamShape")["done"] is False


def test_a_touch_event_on_a_platform_is_stood_on_by_its_flags_record_and_done_by_its_touch_or_a_rise_its_input_explains(
        monkeypatch):
    """R1.16e's sitting: d1's touch events (the walkway generators' BaseShape, 1.2 m boxes whose top is the walk
    surface; BeamShape, four records of that name) approached with the trigger test took the body centre into the
    shape only falling past its side, three of three to the player's death.  A touch approach takes the inside test
    only for a shape a standing body centre can be inside (``holds_body``: a field on the floor, not a platform
    under the feet), the event's object is the record its flag names (``event_object``).  AZ-501: d1's toggles are
    3 s switches on an OR of three inputs, so ``touched`` counts one only when it rose (off before the approach,
    read by ``action`` before it) at a tick its OR's input from this touch's way reads on; on before, unread
    before, or set by another input, it is a miss that says which.  AZ-497: standing on, jumping on, X at and
    swinging at a walkway generator's base turned on no toggle; its event is played at the same walkway's
    pressure plate, which feeds the same combiner, and a plate the stand leaves untouched is tried again onto its
    middle, with a hop and walked across, until one takes."""
    import types

    from devkit.rando.draft import l3_goal
    rev = lambda tris: [(a, c, b) for a, b, c in tris]                  # noqa: E731  (the tern's winding)
    field, platform = rev(_box(2, 0, 0, 5, 3, 2.5)), rev(_box(7, 0, -1.2, 10, 3, 0))
    router = Router(Reach(_level(_quad(0, 0, 12, 6, 0), (field, {}), (platform, {})), flights.Env.kept()))
    assert l3_goal.holds_body(router, "p1") and not l3_goal.holds_body(router, "p2")

    from devkit.xemu import chain as xc
    beam = {"level": "d1", "kind": "event", "how": "touch", "object": "BeamShape", "flag": "d1.BeamShape_g0r451.touch"}
    pad = {**beam, "object": "walkwayGenerator:BaseShape", "flag": "d1.walkwayGenerator_BaseShape.touch"}
    base2 = {**pad, "object": "walkwayGenerator2:BaseShape", "flag": "d1.walkwayGenerator2_BaseShape.touch"}
    assert (xc.event_object(beam), xc.event_object(pad), xc.event_object(base2)) == (
        "d1/g0/r451", "walkwayGenerator:PressurePlateShape", "walkwayGenerator2:PressurePlateShape")
    monkeypatch.setattr(xc, "router", lambda level, prof="logic": router)
    chain = xc.Chain.__new__(xc.Chain)
    base = {"index": 8, "from": "a", "kit": {}, "tier": "standard"}
    for obj, inside in (("p1", True), ("p2", False)):
        (app, _), = chain.stations({**base, **pad, "level": "t", "object": obj, "flag": None})
        assert (app["object"], app["radius"], app.get("inside", False)) == (obj, 0.0, inside)
    order = []
    chain.toggles_before = lambda seg: order.append("before") or {"W3_toggle": 0.0}
    chain.station = lambda i, seg, k, app, fn, parent, rec: order.append("approach") or {"meta_sha12": "m"}
    chain.acted = lambda seg, parent, rec: rec
    chain.action(8, {**base, **pad, "level": "t", "object": "p2", "flag": None}, None, {"starts": []})
    assert (order, chain._before) == (["before", "approach"], {"W3_toggle": 0.0})

    Link = types.SimpleNamespace                 # the plate's touch and walkwayGenerator7 into W3_toggle's OR
    links = {0: [Link(src_plug=3, dst=3, dst_plug=0), Link(src_plug=xc.TOUCH_PLUG, dst=1, dst_plug=0)],
             1: [Link(src_plug=17, dst=2, dst_plug=0)], 2: [], 3: [], 4: [Link(src_plug=17, dst=1, dst_plug=1)]}
    vals = {}
    m = types.SimpleNamespace(by={"walkwayGenerator:PressurePlateShape": [0]}, stick=None,
                              g=types.SimpleNamespace(names=["walkwayGenerator:PressurePlateShape", "<or>", "W3_toggle",
                                                             "Other_toggle", "walkwayGenerator7"],
                                                      links=lambda i: links[i], plug_name=lambda i, p: f"inputs[{p}]"),
                              get=lambda rec, attr: vals.get((rec, attr), 0.0),
                              ins=lambda j: [(i, lk, 0, "output", f"inputs[{lk.dst_plug}]") for i in links
                                             for lk in links[i] if lk.dst == j])
    m.run = lambda n, stick=None, on_tick=None, hook_at=None: [on_tick(None, None, []) for _ in range(n)]
    assert xc.toggles(m, 0) == {"W3_toggle": (2, 1, "inputs[0]")}       # its touch plug's way only
    for before, toggle, own, other, done, said in (
            ({"W3_toggle": 0.0}, 1.0, 1.0, 0.0, True, "W3_toggle rose, its OR's input from this touch on"),
            ({"W3_toggle": 1.0}, 1.0, 1.0, 0.0, False, "W3_toggle on before the approach"),
            (None, 1.0, 1.0, 0.0, False, "W3_toggle on, not read before the approach"),
            ({"W3_toggle": 0.0}, 1.0, 0.0, 1.0, False, "W3_toggle came on, not by this touch's input "
                                                       "(walkwayGenerator7 on)"),
            ({"W3_toggle": 0.0}, 0.0, 0.0, 0.0, False, "W3_toggle stayed off")):
        vals.update({(2, "goal"): toggle, (1, "inputs[0]"): own, (1, "inputs[1]"): other})
        got = chain.touched(m, xc.event_object(pad), before)
        assert (got["done"], said in (got.get("by") or got["why"])) == (done, True), got
    # AZ-497 (sitting r116f-final-c, segment 23: W3_toggle stayed off on walkwayGenerator's plate): a platform the
    # stand leaves untouched is tried onto its mesh's middle, then with a hop there (here the landing fires it)
    pos = [1.0, 0.0, 1.0]

    def toward(target, mag):
        pos[0] += max(-0.1, min(0.1, target[0] - pos[0]))
        m.stick = ("toward", mag)

    def run(n, stick=None, on_tick=None, hook_at=None):
        for _ in range(n):
            acts = on_tick(None, None, [])
            if "down y" in acts:
                vals.update({(2, "goal"): 1.0, (1, "inputs[0]"): 1.0})
            if "stop" in acts:
                break
    stand_run = m.run
    m.body, m.toward, m.run, m.level = (lambda: tuple(pos)), toward, run, "d1"
    vals.update({(2, "goal"): 0.0, (1, "inputs[0]"): 0.0, (1, "inputs[1]"): 0.0})
    chain._platform_centre = lambda m_, obj: (np.array([0.0, 0.0, 0.0]), 1.5)
    got = chain.touched(m, xc.event_object(pad), {"W3_toggle": 0.0}, platform=True)
    assert (got["done"], got["how"], [t["how"] for t in got["tries"]], abs(pos[0]) < xc.TOUCH_MID) == (
        True, "hop", ["stand", "centre", "hop"], True), got
    pos[:] = [0.6, 0.0, 1.0]                     # here only walking off its side fires it

    def run_across(n, stick=None, on_tick=None, hook_at=None):
        for _ in range(n):
            acts = on_tick(None, None, [])
            if abs(pos[0]) > 2.0:
                vals.update({(2, "goal"): 1.0, (1, "inputs[0]"): 1.0})
            if "stop" in acts:
                break
    m.run = run_across
    vals.update({(2, "goal"): 0.0, (1, "inputs[0]"): 0.0})
    got = chain.touched(m, xc.event_object(pad), {"W3_toggle": 0.0}, platform=True)
    assert (got["done"], got["how"], pos[0] < -2.0) == (True, "across", True), got
    m.run = stand_run
    # EW_toggle's OR feeds it through an AND (the bridge's disable), on for any OR input: the way's input is the OR's
    links.update({1: [Link(src_plug=17, dst=5, dst_plug=0)], 5: [Link(src_plug=17, dst=2, dst_plug=0)]})
    m.g.names[1:3] = ["EW_Touch_orCombiner", "EW_toggle"]
    m.g.names.append("DeathBridge_disable_andCombiner")
    assert xc.toggles(m, 0) == {"EW_toggle": (2, 1, "inputs[0]")}
    vals.update({(2, "goal"): 1.0, (1, "inputs[0]"): 0.0, (1, "inputs[1]"): 1.0, (5, "inputs[0]"): 1.0})
    got = chain.touched(m, xc.event_object(pad), {"EW_toggle": 0.0})
    assert not got["done"] and "(walkwayGenerator7 on)" in got["why"], got


def test_a_skipped_barrier_is_not_done_a_same_node_one_ends_on_its_switch_and_a_carried_store_holds_lt_with_no_y(
        monkeypatch):
    """AZ-500 (R1.16e's sitting, row d): the chain skipped w1's IceBlock_01, whose from-node is its to-node, as "not
    in the way" and marked it ok, so the record read every segment done; and the stored steam, released at W1_3, was
    gone after the walk to the block.  A barrier behind the body is recorded skipped (not ok) and the chain goes on,
    its result naming it, and one its approach left behind the body is recorded skipped too; a same-node one is in
    the way and its walk ends, done, when its own switch moves, not done when none does; a ``carry`` segment holds LT
    on the pipe (again after a relaunch), on the replay's settle tick, every pad and the drains' pads, its search has
    no Y (its seeds' jumps dropped, ``hold`` 0, no flight in its goal), and its barrier presses no element and lets
    LT go at the cast's tick."""
    import struct
    import types

    from devkit.xemu import chain as xc
    from devkit.sim import l3
    wall = [(a, c, b) for a, b, c in _box(2, 4, 0, 5, 5, 2.5)]        # p1: its centre at y 4.5
    router = Router(Reach(_level(_quad(0, 0, 12, 12, 0), (wall, {})), flights.Env.kept()))
    monkeypatch.setattr(xc, "router", lambda level, prof="logic": router)
    monkeypatch.setattr(xc, "zones", lambda node: {f"t.{node}"})
    monkeypatch.setattr(xc, "barrier_switches", lambda seg: ["t/g0/r7"])
    sent = []
    chain = xc.Chain.__new__(xc.Chain)
    chain.s = types.SimpleNamespace(sb=types.SimpleNamespace(hold=lambda b: sent.append(f"down {b}"),
                                                             release_btn=lambda b: sent.append(f"up {b}"),
                                                             alive=lambda: False, relaunch=lambda: sent.append("new"),
                                                             unpark=lambda tag, meta: dict.fromkeys(
                                                                 ("loadvm_s", "ready_s", "at_start"), 1)))
    chain.s.signalled = None   # no signal came: the chain runs on (AZ-701)
    chain.log = lambda msg: None
    chain.goal = lambda seg, prof: types.SimpleNamespace(cost=lambda r: abs(10.0 - r.pos[1]))   # the to-node: y 10
    hop = {"index": 1, "kind": "barrier", "level": "t", "from": "a", "to": "b", "goal": "t.Wall", "shapes": ["p1"]}
    assert chain.in_the_way(hop, (3.5, 4.5, 1.25), (3.5, 2.0, 1.0)) is True
    chain.body = lambda: (3.5, 7.0, 1.0)                                # past the wall
    skipped = chain.action(1, hop, {"meta_sha12": "m"}, {"starts": [], "attempts": [], "ok": False})
    assert (skipped["ok"], bool(skipped["skipped"]), skipped["stations"]) == (False, True, [])
    late = chain.acted(hop, None, {"starts": [], "stations": [{"act": {"done": True, "not_in_the_way": True}}]})
    assert (late["ok"], bool(late["skipped"])) == (False, True)
    assert chain.in_the_way({**hop, "to": "a"}, (3.5, 4.5, 1.25), (3.5, 7.0, 1.0)) is True

    chain.segs = [{"index": 0, "kind": "walk"}, hop, {"index": 2, "kind": "walk"}]
    chain.rec, chain.progress, chain.on_miss, chain.k = {"segments": [], "plan": {}}, None, "stop", 0
    chain.save = chain.close_pool = lambda: None
    walked = {"ok": True, "starts": [{"meta_sha12": "m"}], "attempts": [], "string_sha12": "s", "drained": 0}
    chain.segment = lambda i, seg, parent: chain.rec["segments"].append(r := {**seg, **(skipped if i == 1 else
                                                                                          walked)}) or r
    assert chain.run()["result"] == "the end reached; skipped (not played): [1]"

    goals, ticks = {7: 0.0}, []

    class M:                          # a level's live graph (g0): the block's switch r7 moves at the walk's tick 40
        gi, stick = 0, None
        melts = True

        def body(self):
            return (3.5, 2.0, 1.0)

        def toward(self, target, mag):
            pass

        def get(self, rec, attr):
            return goals[rec]

        def run(self, n, on_tick=None, hook_at=None):
            for k in range(1, n + 1):
                if k == 22 + 40 and self.melts:
                    goals[7] = 1.0
                ticks.append(on_tick(None, None, []))
                if "stop" in ticks[-1]:
                    break
            return {"stop": None}
    block = {**hop, "to": "a"}
    got = chain.staff(M(), block)
    assert (got["done"], got["passed"], got["switches"], len(ticks)) == (True, None, {"t/g0/r7": [0.0, 1.0]}, 62)
    goals[7], M.melts = 0.0, False
    got = chain.staff(M(), block)
    assert (got["done"], got["why"]) == (False, "no switch of the barrier moved")

    chain.carry({"carry": ["fire", "water"]})
    assert (chain._held, sent) == ({"lt"}, ["down ltrigger"])
    assert xc.no_jump([[10, 0.5, 6], [4, None, 0, 2, 3]]) == [[10, 0.5, 0], [4, None, 0, 2, 0]]

    class Sim:
        def __init__(self, *a, **kw):
            self.n = 0

        def step(self, pad):
            self.n += 1
            return l3.Row(self.n, (0.0, 0.0, 1.0), 0, 200, None, (), struct.pack("<2f", 0.0, 1.0))

        def save(self):
            return None
    monkeypatch.setattr(l3, "L3", Sim)
    monkeypatch.setattr(l3, "read_snapshot", lambda path: None)
    monkeypatch.setattr(l3, "snapshot_path", lambda label: label)
    chain.xbe, chain.disc = (lambda: b""), (lambda: "disc")
    pads, rows = chain.l3_run({"label": "s"}, [[3, 0.5, 0]], deep=False)
    assert (len(pads), len(rows), {p.buttons for p in pads}) == (4, 4, {frozenset({"lt"})})
    from devkit.rando.draft import l3_goal
    seen = {}
    monkeypatch.setattr(l3_goal, "route_seed", lambda R, feet, target, air=0: [[10, 0.5, 6]])
    monkeypatch.setattr(xc, "known_strings", lambda seg: [])
    monkeypatch.setattr(xc.lc, "_reach_path", lambda level: Path("t.pkl"))
    monkeypatch.setattr(xc, "solve", lambda seg, spec, xbe, **kw: seen.update(kw, spec=spec) or {
        "winner": None, "reached": False, "seconds": 0.0, "problem": None, "runs": []})
    chain.goal, chain.pool, chain.rate = (lambda seg, prof: types.SimpleNamespace(R=None)), (lambda label: None), \
        (lambda: 30.0)
    chain.steps, chain.ticks, chain.wall_cap, chain.jobs = 1000, 100, 60.0, 1
    chain.search({"kind": "walk", "level": "t", "goal": "b", "kit": {"air": 1}}, {"label": "s"}, 1, "logic",
                 {"hold": 4}, [[[3, 0.5, 2]]])
    assert (seen["limits"].hold, seen["strings"], seen["spec"]["kwargs"]["air"]) == (0, [[[10, 0.5, 0]],
                                                                                         [[3, 0.5, 0]]], 0)
    chain.halted_at_start, chain.park = False, True
    chain.bring_back({"label": "s", "parked": "p", "meta": {}})
    assert sent == ["down ltrigger", "new", "down ltrigger"]            # the new xemu's pipe holds LT again
    clock, written, sb = iter(range(1, 99)), [], chain.s.sb
    g = types.SimpleNamespace(regs=lambda: {"eip": l3.PLAYER_UPDATE, "ecx": 64}, cmd=lambda c: None,
                              read=lambda a, n: struct.pack("<d", next(clock)))
    for mod, name, fn in ((xc.xo, "arm", None), (xc.xo, "resume", None), (xc.recipes, "chain", {"player": 5}),
                          (xc.recipes, "level_path", "t")):
        monkeypatch.setattr(mod, name, lambda *a, _v=fn: _v)
    sb.halt, sb.read_u32, sb.read, sb.write_pad, sb._wait = (lambda: g), (lambda a: 5), None, written.append, \
        (lambda s: True)
    assert chain.drain(lambda c: c["ticks"] >= 2)["stop"] == "join"
    assert [p.buttons for p in written] == [frozenset({"lt"})] * 2
    ticks.clear()
    goals[7], M.melts = 0.0, True
    got = chain.staff(M(), {**block, "cast": ["fire", "water"]})
    acts = [a for t in ticks for a in t]
    assert ("up ltrigger" in ticks[17], got["released_at"], chain._held) == (True, 18, frozenset())
    assert [a for a in acts if a.startswith("down")] == ["down a"] * acts.count("down a")
    chain.carry({})
    assert sent == ["down ltrigger", "new", "down ltrigger"]            # the barrier let it go


def test_a_chains_plateau_stops_seeds_on_every_rung_passes_over_the_4x_rung_it_would_replay_and_keeps_each_curve(
        monkeypatch):
    """Step X.95 (X.93's rank 1: searches that found nothing were 84 % of R1.25b's chain): ``run --plateau N`` sets
    ``Limits.plateau`` to N on every rung (over ``SCENE_COST`` in whole steps), and none without it; the 4x rung, the
    first rung's own problem and seeds, is passed over once every seed ended at its plateau, never for seeds the
    wall cap ended; each run's curve, stall and steps a second stay in the attempt's record (the curves N is picked
    from)."""
    import types

    from devkit.xemu import chain as xc
    from devkit.rando.draft import l3_goal
    from devkit.sim import l3
    seen = []
    run = {"index": 0, "why": "plateau at the best cell", "steps": 9000, "cells": 4, "best_cost_s": 3.2, "faults": 0,
           "taint": [], "steps_per_s": 600, "curve": [[5000, 3.2], [9000, 3.2]], "stall": {"cost_s": 3.2},
           "segs": [], "seconds": 15.0}
    monkeypatch.setattr(xc, "solve", lambda seg, spec, xbe, **kw: seen.append(kw["limits"]) or {
        "winner": None, "reached": False, "seconds": 15.0, "problem": "p", "runs": [run]})
    monkeypatch.setattr(l3_goal, "route_seed", lambda R, feet, target, air=0: [])
    monkeypatch.setattr(xc, "known_strings", lambda seg: [])
    monkeypatch.setattr(xc, "start_of", lambda sim, seg: (None, types.SimpleNamespace(pos=(0.0, 0.0, 0.0)), 0.0,
                                                           [], []))
    monkeypatch.setattr(xc.lc, "_reach_path", lambda level: Path("t.pkl"))
    monkeypatch.setattr(xc.lc, "_feet", lambda row: (0.0, 0.0, 0.0))
    for name, fn in (("L3", lambda *a, **kw: None), ("read_snapshot", lambda path: None),
                     ("snapshot_path", lambda label: label)):
        monkeypatch.setattr(l3, name, fn)
    chain = xc.Chain.__new__(xc.Chain)
    chain.goal, chain.pool, chain.rate = (lambda seg, prof: types.SimpleNamespace(R=None)), (lambda label: None), \
        (lambda: 30.0)
    chain.xbe, chain.disc = (lambda: b""), (lambda: "disc")
    chain.steps, chain.ticks, chain.wall_cap, chain.jobs, chain.plateau = 400_000, 3600, 480.0, 4, None
    walk = {"kind": "walk", "level": "t", "goal": "b", "kit": {}}
    got = chain.search(walk, {"label": "s"}, 1, "logic", {}, [])
    assert seen[-1].plateau is None
    assert got["runs"] == [{k: run[k] for k in ("index", "why", "steps", "cells", "best_cost_s", "faults", "taint",
                                                 "steps_per_s", "curve", "stall")}]
    chain.plateau = 60_000
    for mult, scene, want in ((1, False, 60_000), (4, False, 60_000), (4, True, 6_000)):
        chain.search(walk, {"label": "s"}, mult, "logic", {}, [], scene)
        assert (seen[-1].plateau, seen[-1].steps) == (want, 400_000 * mult // (xc.SCENE_COST if scene else 1))
    assert "plateau" not in seen[-1].shape()                            # a budget: the problem and its seeds stay
    start = {"label": "s", "level": "levels/t", "meta_sha12": "m", "meta": {}}
    chain.segs, chain.hints, chain.scene, chain.pilot, chain.park, chain._held = [walk], {}, None, False, True, ()
    chain.s, chain.seg_cap = types.SimpleNamespace(signalled=None), None
    chain.take_start, chain.off_logic = (lambda i, n, parent: start), (lambda *a: False)
    chain.maybe_release, chain.save, chain.log = (lambda: False), (lambda: None), (lambda msg: None)
    for why, rungs in (("plateau at the best cell", [(1, {}), (4, {"temp": 30.0, "pursue": 0.3}), (4, {})]),
                       ("wall-cap", [(1, {}), (4, {}), (4, {"temp": 30.0, "pursue": 0.3}), (4, {})])):
        ran = []
        chain.search = lambda seg_, st, mult, prof, shape, strings, scene, wall: ran.append((mult, shape)) or {
            "seconds": 1.0, "reached": False, "runs": [{**run, "why": why, "best_cost_s": c} for c in (3.2, 9.0)]}
        rec = chain.searched(0, {**walk, "level": "t", "from": "a"}, None, {"starts": [], "attempts": [], "ok": False})
        assert ran == rungs and rec["why"] == "the search found no string on every rung of the ladder", (ran, rec)


def test_a_chains_l3_fast_pool_spawns_fastl3_workers_on_the_patched_library_and_base_clears_its_switches(monkeypatch):
    """Step X.95: ``run --l3 fast`` makes each start's search pool a FastL3 one (``Pool(fast=True)``) with the patched
    libunicorn's switches in the environment its workers are spawned with (``l3_fast.worker_env``, as the reach
    engine's pool); ``--l3 base`` builds round 1's pool with the switches cleared, also after a fast one."""
    import os

    from devkit.xemu import chain as xc
    from devkit.reach import l3_fast, l3_pool
    made = []

    class Pool:
        def __init__(self, label, xbe, **kw):
            made.append((label, kw.get("fast", False), os.environ.get("LIBUNICORN_PATH"),
                         os.environ.get("UC_TLB_BITS")))

        def close(self):
            pass
    monkeypatch.setattr(l3_pool, "Pool", Pool)
    monkeypatch.setattr(l3_fast, "worker_env", lambda root=None: {"LIBUNICORN_PATH": "/lib", **l3_fast.SWITCHES})
    monkeypatch.setattr(os, "environ", {k: v for k, v in os.environ.items()
                                        if k not in ("LIBUNICORN_PATH", *l3_fast.SWITCHES)})
    chain = xc.Chain.__new__(xc.Chain)
    chain._pool, chain.jobs, chain.xbe, chain.disc = None, 2, (lambda: b""), (lambda: "disc")
    for chain.l3, label in (("fast", "s0"), ("fast", "s0"), ("base", "s1"), ("fast", "s2")):
        chain.pool(label)
    assert made == [("s0", True, "/lib", "12"), ("s1", False, None, None), ("s2", True, "/lib", "12")]
    assert (xc.l3_library("fast"), xc.l3_library("base")) == ("patched", "wheel")


def test_a_chain_plays_the_segments_a_segments_print_holds_for_a_plan_its_database_refuses(tmp_path, monkeypatch):
    """Step R1.25: the frozen plans (13ad9434b881, 066e456b52bd) are refused by a later database (``load_plan``'s
    db_digest), so ``run --segments FILE`` plays the segments the code that made the plan printed (``segments``:
    the plan's identity line, then a segment a line), the identity's tour, discs and keys with them; a file that
    isn't such a print is refused by name."""
    from devkit.xemu import chain as xc
    ident = {"sha256": "13ad9434b881", "tour": [25], "discs": {"earth": 4}, "keys": {"d1k1": 3}}
    segs = [{"index": 0, "kind": "walk", "level": "d1"}, {"index": 1, "kind": "exit", "level": "d1"}]
    f = tmp_path / "final.jsonl"
    f.write_text("".join(json.dumps(x) + "\n" for x in (ident, *segs)), encoding="utf-8")
    assert xc.read_segments(f) == (segs, {**ident, "segments_file": "final.jsonl"})
    f.write_text(json.dumps(segs[0]) + "\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="not a `segments` print"):
        xc.read_segments(f)


def test_a_resume_and_a_move_on_find_the_segments_start_on_the_drive(monkeypatch):
    """Step R1.25b: ``run --resume`` starts at a segment's first parked start, its first station's approach's when
    its own isn't parked (sitting r125-full-h, segment 34: its own start is the link after the button before it, no
    tag).  AZ-819 (sitting r125-full-g, segment 29): the start restored from memory after the route pilot's retreat
    ended in a death, the guest bugchecked and placing the player raised "no player tick to place the player at",
    ending the chain, where a resume loading the same start from the drive moved on: a move-on that finds no player
    tick quits xemu and goes again once from the start loaded from the drive (``bring_back``'s relaunch)."""
    import types
    from devkit.xemu import chain as xc
    seg = {"starts": [{"meta_sha12": "m", "how": "after an action"}],
           "stations": [{"approach": {"starts": [{"label": "s05", "parked": "p-s05"}]}}]}
    assert xc.first_start(seg)["parked"] == "p-s05"
    ch = xc.Chain.__new__(xc.Chain)
    quits, tries = [], []
    ch.s = types.SimpleNamespace(sb=types.SimpleNamespace(_quit=lambda: quits.append(1)))
    ch.park, ch._seg_start, ch.halted_at_start, ch.log = True, {"parked": "p-s03"}, True, (lambda msg: None)

    def move_on(i):
        tries.append(ch.halted_at_start)
        if len(tries) == 1:
            raise SystemExit("no player tick to place the player at")
        return {"placed": "onto d1_z025 (try 1)", "ok": True}
    ch._move_on = move_on
    got = ch.move_on(29)
    assert (got["ok"], quits, tries) == (True, [1], [True, False]) and "relaunched" in got["again"], got


def test_the_chain_rides_d1s_elevator_by_its_wiring_on_the_final_spheres_elevator_legs(monkeypatch):
    """Step R1.16d: the golden final sphere's hops between two floors of d1's elevator are rides (``rig``), each
    run of them one segment (floor 1 to 5, 5 to 8, the ride 7 to 1 the logic leaves out, 1 to 11, 11 to 9), and
    ``devkit/xemu/chain.py`` plans each from the elevator's wiring: a ride on a colour's floor, a floor switch
    pressed on its own floor once its key is in, flipping its toggle and giving the colour the toggle's new floor
    (the owner's ways, X34's RP-E and RP-F: switch4 then green 4, switch3 then green 6; switch6 back to red 1); no
    ride leaves floor 9, and floor 9 needs switch9's key.  AZ-498 (R1.16e's sitting: approaches searched from the
    deck at another floor found no route, the route graph holding the deck only at its rest; a keylock approached
    to 1.2 m stopped 3.04 m off): a ride boards from the call field unless the deck is there and the body by it,
    steps off the deck after each ride onto the call field's walk vertex nearest it off the deck (the next side's
    when one gives no headway: r116f-final-c's floors 5 and 3), and a keylock's approach stands within 0.5 m (a
    floor switch's after its walk-up from 1.2 m stalled out of X's reach, R1.25b: switch9's 1.74 m off), and a walk-up
    that stalls outside X's reach gives up (sitting r125b, 35: 480 ticks of X 1.72 m off while enemies took the HP).
    A ride's switch or call field within 30 m of the body is walked to from there before its
    searched approach (each searched to its cap in sitting r125-d1), and a death mid-ride is the ride's miss, the
    station it came in too (sitting r125s, 35: a press counted done 487 m off, after the reload into w1); a
    keylock's second press backs off out of its sphere first (r669 took from 0.69 m outside it, not from inside);
    a boarding whose straight walk stalls goes by the floor's landing (r125-full-b's 27 never got onto the deck);
    a call ends at a death, recording its tick and the largest floor read before it (r125b, 35's read from w1)."""
    import json as json_
    import types
    from devkit.xemu import chain as xc
    from devkit.xemu import minigames as mg

    from azurkit.tools.randomizer.planner.plan import ELEVATORS, load_plan, merge_walks, spheres, tour_segments
    logic = kept_logic()
    golden = Path(__file__).resolve().parent / "goldens" / "rando_plans.json"
    plan = load_plan(json_.loads(golden.read_text(encoding="utf-8"))["default"]["plan"], logic.db)
    played = spheres(plan, logic)
    final = merge_walks(tour_segments(plan, logic, [len(played)], played=played, victory=True))
    floors = ELEVATORS["d1.elevator"]
    legs = [(floors[x["from"]], floors[x["to"]], x["kind"]) for x in final if x.get("rig")]
    assert legs == [(1, 5, "walk"), (5, 8, "walk"), (7, 1, "ride"), (1, 11, "walk"), (11, 9, "walk")], legs
    new = {"red": 1, "green": 3, "blue": 5}, {t: 0 for _, _, t, _, _ in xc.LIFT_SWITCHES.values()}
    keys = {x: x not in (651, 714) for x in xc.LIFT_SWITCHES}          # death_keylock in: switch4's key on
    assert xc.lift_plan(1, 5, *new, keys) == [("ride", "blue")]
    assert xc.lift_plan(5, 6, *new, keys) == [("press", 664), ("ride", "green"), ("press", 679), ("ride", "green")]
    red8 = {**new[0], "red": 8}, {**new[1], 632: 1}                    # switch6 sent red to 8
    assert xc.lift_plan(7, 1, *red8, keys) == [("press", 629), ("ride", "red")]
    assert xc.lift_plan(11, 9, *new, keys) is None and xc.lift_plan(9, 1, *new, keys) is None
    assert xc.lift_plan(11, 9, *new, {**keys, 714: True}) == [("press", 714), ("ride", "blue")]
    assert xc.lift_plan(3, 3, *new, keys) == []

    chain = xc.Chain.__new__(xc.Chain)
    locks = [x for x in final if x.get("lock_toggle")]
    assert locks and {chain.stations(x)[0][0]["radius"] for x in locks} == {xc.KEYLOCK_R} == {0.5}

    deck, field = (np.array([-2.0, -2.0, 0.0]), np.array([2.0, 2.0, 0.2])), (np.array([-3.0, -3.0, 0.0]),
                                                                              np.array([3.0, 3.0, 5.0]))
    verts = np.array([(0.0, 0.0), (2.2, 0.0), (2.8, 0.0), (-2.8, 0.0), (5.0, 0.0)])   # on it, within 0.5 m, off
    monkeypatch.setattr(xc, "lift_box", lambda level, rec: deck if rec == xc.LIFT_DECK else field)
    monkeypatch.setattr(xc, "router", lambda level, prof="logic": types.SimpleNamespace(
        X=verts[:, 0], Y=verts[:, 1], Z=np.zeros(5), node=np.zeros(5, dtype=int), lv=None))

    class M:                          # d1's live graph: the deck called to floor 1 and there
        level, gi, stick = "d1", 0, (0.0, 0.0)

        def __init__(self, x):
            self.p, self.aims = [x, 0.0, 1.0], []

        def body(self):
            return tuple(self.p)

        def hp(self):
            return 200

        def loaded(self):
            return "levels/death/d1"

        def toward(self, target, mag):
            self.aims.append(target)
            self.p[0] += 0.1 if target[0] > self.p[0] else -0.1

        def get(self, rec, attr):
            return 1.0 if (rec, attr) == (xc.LIFT_CALLED, "inputs[14]") else 0.0

        def run(self, n, stick=None, on_tick=None, hook_at=None):
            for _ in range(n):
                if "stop" in on_tick(None, None, []):
                    break
    m = M(1.5)
    got = chain.step_off(m, 5)
    assert (got["done"], set(m.aims), m.p[0] > 2.0) == (True, {(2.8, 0.0, 0.0)}, True)
    m = M(1.5)                        # sitting r116f-final-c, floors 5 and 3: the nearest side gives no headway
    walk = m.toward
    m.toward = lambda target, mag: None if target[0] > 0 else walk(target, mag)
    got = chain.step_off(m, 5)
    assert (got["done"], [x["side"] for x in got["sides"]], m.p[0] < -2.0) == (True, ["+x", "-x"], True), got

    from devkit.rando.draft import l3_goal
    monkeypatch.setattr(l3_goal, "object_points", lambda lv, obj: np.array([deck[0], deck[1]]))
    m = M(5.0)                                    # sitting r125-full-b, 27: a rail between the body and the deck
    walk = m.toward
    m.toward = lambda target, mag: None if target[0] == 0.0 and (m.p[0] > 3.0 or not jumps) else walk(target, mag)
    m.use = lambda *a, **kw: {"done": False}
    jumps = []                                    # and the deck's edge: walked over only with a jump

    def run_jumps(n, stick=None, on_tick=None, hook_at=None):
        for _ in range(n):
            acts = on_tick(None, None, [])
            jumps.extend(x for x in acts if x == "down y")
            if "stop" in acts:
                break
    m.run = run_jumps
    landed = []

    def pilot(m_, point, st):                     # the route pilot onto the landing at the deck's edge
        landed.append(point)
        m_.p[0] = point[0]
        return {"done": True, "ticks": 30, "left_m": 0.0, "pilot": True}
    chain._pilot_to = pilot
    got = chain.board(m, "blue", 5, 5)            # straight in: no headway; by the +x landing, then onto the deck
    assert (got["why"], abs(m.p[0]) < 2.0, landed, len(jumps)) == (
        "blue's button didn't call floor 5", True, [(2.8, 0.0, 0.0)], 1), got
    m, landed[:] = M(25.0), []                    # r125-full-f, 27: called and there, the body 20-45 m off
    got = chain.call(m, 1)                        # the pilot into the call field first
    assert (got["done"], landed) == (True, [(2.8, 0.0, 0.0)]), got
    m, hps = M(0.0), iter(range(10 ** 6))         # r125b, 35: floor 11's call ends at the death, at its tick
    m.hp = lambda: 0 if next(hps) > 5 else 100
    got = chain.call(m, 11)
    assert (got["done"], got["lost_at"], got["ticks"], got["called_max"]) == (False, 6, 6, 1), got
    u = mg.Minigames.__new__(mg.Minigames)
    import struct as struct_                     # a keylock's second try: backs off out of its sphere, faces it, X
    from devkit.xemu import route as xr
    lock, pos, yaw, pressed = np.array([[-0.25, -0.25, 0.75], [0.25, 0.25, 1.25]]), [0.2, 0.0, 1.0], [0.0], []

    def walk(target, mag):
        dx, dy = target[0] - pos[0], target[1] - pos[1]
        d = math.hypot(dx, dy) or 1.0
        pos[0], pos[1], yaw[0] = pos[0] + 0.1 * mag * dx / d, pos[1] + 0.1 * mag * dy / d, math.radians(
            xr.ang_of(dx, dy))

    def run_x(n, on_tick=None, hook_at=None):
        for _ in range(n):
            acts = on_tick(u, {"ent": 0}, [])
            pressed.extend(round(math.dist(pos, (0.0, 0.0, 1.0)) - math.dist(lock[0], lock[1]) / 2, 2)
                           for a in acts if a == "down x")
            if "stop" in acts:
                break
        return {"stop": None}
    u.mesh = u.mesh_live = lambda n: lock
    u.body, u.toward, u.run = (lambda: tuple(pos)), walk, run_x
    u.g = types.SimpleNamespace(read=lambda a, n: struct_.pack("<f", yaw[0]))
    got = u.use(669, lambda: len(pressed) > 0, n=400, standoff=xc.KEYLOCK_STANDOFF)
    assert got["done"] and pressed[0] >= xc.KEYLOCK_STANDOFF - 0.4, (got, pressed)
    pos[:], pressed[:] = [3.5, 0.0, 1.0], []        # r125b, 35: a walk-up that stalls out of X's reach gives up
    u.toward = lambda target, mag: None
    got = u.use(714, lambda: False, n=480)
    assert (got["done"], pressed, got["ticks"] < 60, "stalled" in got["why"]) == (False, [], True, True), got
    monkeypatch.setattr(xc, "lift_state", lambda m_: (dict(new[0]), dict(new[1]), keys))
    chain.s, chain.disc, chain.log = types.SimpleNamespace(sb=None), (lambda: "disc"), (lambda msg: None)
    chain._in, chain.acted = (lambda R, want: True), (lambda seg, parent, rec: rec)
    for name in ("call", "board", "step_off"):
        setattr(chain, name, lambda m_, *a, _n=name: played.append((_n, *a)) or {"done": True})

    def station(i, seg, k, app, fn, parent, rec):
        played.append(app.get("object"))
        fn(m)
        return {"meta_sha12": "m"}
    chain.station, chain._lost = station, (lambda seg: None)
    monkeypatch.setattr(l3_goal, "object_points", lambda lv, obj: np.array([[0.0, 0.0, 1.0], [1.0, 1.0, 1.0]]))
    leg = {"index": 22, "kind": "walk", "level": "d1", "rig": "d1.elevator", "from": "d1_floor1", "to": "d1_z081"}
    for x, first in ((40.0, ["d1/g0/r735", ("call", 1)]),            # far from the call field: its searched approach
                     (10.0, [None, ("call", 1)]),                     # within 30 m of it: walked to from there
                     (1.0, [])):                                      # by the deck: no call
        played, m = [], M(x)
        monkeypatch.setattr(mg, "Minigames", lambda sb, disc, level: m)
        chain.ride(0, leg, None, {})
        assert played == [*first, None, ("board", "blue", 5, 1), None, ("step_off", 5)], played
    radii = []                                     # r125b, 35: switch9's walk-up from 1.2 m stalled out of reach

    def stalls(i, seg, k, app, fn, parent, rec):
        radii.append(app.get("radius"))
        rec["stations"].append({"act": {"done": len(radii) > 2, "why": "the walk-up stalled 1.74 m outside its sphere"}})
        return {"meta_sha12": "m"} if len(radii) > 2 else None
    chain.station = stalls
    monkeypatch.setattr(xc, "lift_state", lambda m_: (dict(new[0]), dict(new[1]), {**keys, 714: True}))
    chain.ride(0, {**leg, "index": 35, "from": "d1_floor11", "to": "d1_floor9"}, None, {})
    assert radii[:3] == [None, 1.2, xc.KEYLOCK_R], radii   # by X's walk-up, from 1.2 m, then from 0.5 m
    chain.station = station
    chain._lost = lambda seg: "the level changed (levels/water/w1): the player died [inferred]"
    played, rec = [], {}                           # sitting r125-d1, segment 35: a death mid-ride is a miss
    assert "the player died" in chain.ride(0, leg, None, rec)["why"] and played == []
    g = types.SimpleNamespace(regs=lambda: {"ecx": 0}, read=lambda va, n: bytes(n))
    chain.s = types.SimpleNamespace(sb=types.SimpleNamespace(halt=lambda: g))
    chain.drain, chain.rate, chain.save = (lambda until, max_ticks: {"stop": "join", "ticks": 1}), (lambda: 30), \
        (lambda: None)
    rec = {"stations": []}                         # r125s, 35: the press read done after the reload, 487 m off
    assert xc.Chain.station(chain, 0, leg, 1, {}, lambda m_: {"done": True}, None, rec) is None
    assert (rec["stations"][-1]["ok"], "the player died" in rec["why"]) == (False, True), rec


def test_an_unassisted_fight_enters_no_cheat_holds_ground_while_the_boss_is_far_and_swings_a_staff_as_he_closes(
        monkeypatch):
    """AZ-499 (R1.16e's sitting, row c): unassisted, the chain's fight chased Spideyzar at full stick; he stalks at
    about 9 m and flees after each attack, so it never swung in 1,040 ticks.  ``fight(assisted=False)`` enters no
    cheat, holds the stick neutral while he is beyond 2.6 m, steps in once he is within it and swings
    there, and selects the next staff whose elements have fuel each piece (water's gauge empty here: EF, fire's
    staff; R1.16f's single fire, air and earth were armors, cast, not staffs), counting its swings.  It swings from
    2.2 m: in sitting r125-full-h he came no nearer than 1.8 m, so a 1.4 m reach never swung."""
    import struct
    import types

    from devkit.xemu import chain as xc
    from azurkit.tools.randomizer.live import recipes
    cr, ent, pc, inv = 0x1000, 0x2000, 0x3000, 0x4000
    mem = {cr + recipes.CR_HP: struct.pack("<ii", 3000, 3000), pc + recipes.CR_HP: struct.pack("<ii", 200, 200)}
    for f in ("ef", "af", "ff", "wf"):
        mem[inv + recipes.SLOT0 + 12 * recipes.SLOTS.index(f) + 4] = struct.pack("<ii", 0 if f == "wf" else 50, 50)
    tick = {"k": 0, "dead": 0.0}

    def read(a, n):
        if a == cr + recipes.CR_BODY:                   # he stalks 9 m off for 30 ticks, closes to 2.4, attacks from 2
            return struct.pack("<3f", 0.0, 9.0 if tick["k"] <= 30 else 2.4 if tick["k"] <= 40 else 2.0, 0.0)
        if a == ent + 0x90:                             # the player faces +y, toward him
            return struct.pack("<f", 0.0)
        return mem[a][:n] if a in mem else mem[a - 4][4:4 + n]
    sb = types.SimpleNamespace(read=read, read_u32=lambda a: {ent + 0x20: pc, ent + 0x94: 0}[a])

    class M:
        gi, stick, mask = 0, (0.0, 0.0), 0

        def __init__(self):
            self.sb, self.ticks, self.picked = sb, [], []

        def body(self):
            return (0.0, 0.0, 0.0)

        def toward(self, target, mag):
            self.stick = ("toward", mag)

        def get(self, rec, attr):
            return {"numDead": tick["dead"], "enable": 1.0}[attr]

        def staff_mask(self):
            return self.mask

        def select(self, staff):
            self.picked.append(staff)
            return True

        def run(self, n, stick=None, on_tick=None, hook_at=None):
            for _ in range(n):
                tick["k"] += 1
                acts = on_tick(None, {"ent": ent}, [])
                self.ticks.append((tick["k"], self.stick, tuple(acts)))
                if "down a" in acts:                    # the swing kills him
                    mem[cr + recipes.CR_HP], tick["dead"] = struct.pack("<ii", 0, 3000), 1.0
                if "stop" in acts:
                    break
    monkeypatch.setattr(xc, "_generated", lambda m_, rec: cr)
    monkeypatch.setattr(xc.recipes, "chain", lambda u32: {"inv": inv, "player": pc})
    cheats = []
    chain = xc.Chain.__new__(xc.Chain)
    chain.s, chain.log = types.SimpleNamespace(cheat=cheats.append), (lambda msg: None)
    chain.boss = lambda seg: {"id": "d1/g0/r9", "critter": "spideyzar"}
    chain.drain = lambda until, max_ticks: {"stop": "join", "ticks": 1, "loads": []}
    m = M()
    got = chain.fight(m, {"level": "d1", "flag": "d1.spideyzar.killed"}, assisted=False)
    assert (got["done"], got["assists"], cheats, m.picked) == (True, [], [], [("earth", "fire")])
    assert (got["pieces"][0]["selected"], got["pieces"][0]["swings"]) == ({"staff": ["earth", "fire"], "ok": True}, 1)
    far = [(stick, acts) for k, stick, acts in m.ticks if k <= 30]
    assert len(far) == 30 and set(far) == {((0.0, 0.0), ())}            # neutral, no swing, while he is far
    near = {(stick, acts) for k, stick, acts in m.ticks if 30 < k <= 40}
    assert near == {(("toward", 1.0), ())}                              # within 2.6 m: a step in, no swing yet
    assert any("down a" in acts for k, _, acts in m.ticks if k > 40)    # from his 2 m attack range: swings (2.2 m)


def test_a_replay_an_unplanned_level_load_stops_is_searched_again_in_whole_steps_then_placed_past(monkeypatch):
    """AZ-702 (sitting r116f-final-c, segments 9 and 10): each of five replays of one player-tick string stopped at
    the same tick on a trigger's level load the segment doesn't plan (AZ-700's r2271 into d2), the chain playing
    that string again each time.  A load that is neither the segment's exit nor the next one's ends the string's
    tries: the segment is searched again in whole steps, which run the trigger (X.52b), and a replay that stops on
    such a load in whole steps too is a miss (placed past, D240), after two replays."""
    import types
    from devkit.xemu import chain as xc
    chain = xc.Chain.__new__(xc.Chain)
    seg = {"index": 9, "kind": "walk", "level": "d1", "from": "d1_z056", "goal": "d1_z025"}
    chain.segs, chain.hints, chain.scene, chain.pilot, chain.park, chain._held = [seg], {}, None, False, True, ()
    chain.s = types.SimpleNamespace(signalled=None)
    chain.seg_cap, chain.wall_cap, chain.repairs = None, 60.0, 4
    start = {"label": "s9", "level": "levels/death/d1", "meta_sha12": "m", "meta": {}}
    chain.take_start, chain.goal, chain.off_logic = (lambda i, n, parent: start), (lambda *a: None), (lambda *a: False)
    chain.maybe_release, chain.save, chain.log = (lambda: False), (lambda: None), (lambda msg: None)
    searched = []
    chain.search = lambda seg_, st, mult, prof, shape, strings, scene, wall: searched.append((scene, len(strings))) \
        or {"seconds": 1.0, "reached": True, "ticks": 600, "robustness": 1.0, "segs": [(6, 0.0, 0)], "runs": []}
    chain.more_robust = lambda seg_, st, found, *a: found
    chain.play = lambda i, seg_, st, found: {
        "replay": {"stop": {"at": "load", "k": 519, "level": "levels/death/d2"}, "exact": True, "max_err_m": 0.0},
        "ok": False, "why": "an unplanned level load", "string": {"sha12": "x"}, "drain": {"ticks": 0}}
    chain.where = lambda: {"entry": True, "alive": True, "level": "levels/death/d2"}
    rec = chain.searched(0, seg, None, {"starts": [], "attempts": [], "ok": False})
    assert searched == [(False, 0), (True, 0)], searched
    assert rec["why"] == "an unplanned level load (levels/death/d2) at tick 519, in whole steps too", rec["why"]


def test_a_signal_ends_the_chain_though_a_station_or_a_callback_would_take_its_teardown(monkeypatch):
    """AZ-701 (sitting r116f-s1): SIGTERM in segment 0 logged its teardown and the chain played segments 1 and 2;
    a second SIGTERM did nothing.  Its ``Teardown`` was raised inside a weakref finaliser, which Python reports and
    goes on from, and a station's handler takes any ``SystemExit`` as a miss.  A station and a touch event's toggle
    read re-raise it, and once the sitting took a signal the chain stops before its next segment."""
    import types
    from devkit.xemu import chain as xc
    from devkit.xemu import sitting as xs
    chain = xc.Chain.__new__(xc.Chain)
    g = types.SimpleNamespace(regs=lambda: {"ecx": 0}, read=lambda va, n: bytes(n))
    chain.s = types.SimpleNamespace(signalled=None, sb=types.SimpleNamespace(halt=lambda: g))

    def act(_m):
        chain.s.signalled = "SIGTERM"
        raise xs.Teardown("signal SIGTERM: tearing down")
    with pytest.raises(xs.Teardown):
        chain.station(0, {"kind": "warp", "level": "w1"}, 0, {}, act, None, {"stations": []})

    def halt():
        raise xs.Teardown("signal SIGTERM: tearing down")
    chain.s.sb.halt = halt
    with pytest.raises(xs.Teardown):         # the review of Step X.87: None here searched the approach to its end
        chain.toggles_before({"kind": "event", "how": "touch", "level": "w1"})
    played, chain.s.signalled = [], None

    def segment(i, seg, parent):          # its Teardown swallowed inside a callback: the segment ends as if none came
        played.append(i)
        chain.s.signalled = "SIGTERM"
        return {"ok": True, "starts": [{"meta_sha12": "m"}], "attempts": [], "string_sha12": "s", "drained": 0}
    chain.segment, chain.save, chain.close_pool = segment, (lambda: None), (lambda: None)
    chain.segs, chain.rec, chain.k, chain.progress, chain.on_miss = [{}, {}, {}], {"segments": []}, 0, None, "stop"
    with pytest.raises(xs.Teardown):
        chain.run()
    assert played == [0]


def test_a_spot_is_proven_from_its_arrival_at_its_ways_kit_by_xemu_taking_its_item(tmp_path, monkeypatch):
    """Step R1.29 (AZ-455): ``devkit/reach/l3_certify.py plan --spots`` starts a spot from the arrival whose way there
    and back asks the least element levels (w4's earth fragment: none, by its roll-jump skip, Step R2.18), that kit set in L3
    (group ``<level>-k0``); a spot whose way asks a key or a button isn't set up.  Its replay proves it only when
    every tick is L3's, xemu took its own item and the start isn't a teleport within a metre of it (the hop's own
    arrival never is); ``apply`` marks a spot the authoring already holds (a conservative-kit requires) in its own
    ``[[location]]``, once; and each folder keeps its own private start for a key two folders search (an older
    flat one still reads).  Its string starts in the arrival node, at the snapshot's own spot or by R6 into it, and
    its record says it walked back only from there (D122): f1's key from f1_core, not from the f1_town_side spot
    where the level's one snapshot settles.  Its record's kit is the one its string ran with (Step R1.29e: a
    douse's element levels too)."""
    from types import SimpleNamespace as NS

    from azurkit.tools.randomizer.planner import proofs as pr
    from devkit.reach import l3_certify as cert
    none = np.zeros(0, dtype=np.int64)

    class Settled:                                   # a snapshot that settles on a floor in ``zone``, no R6 sample
        def __init__(self, zone):
            self.router = NS(zone_at=lambda feet, prefer_water: zone, R=NS(zone_of=np.zeros(1, dtype=np.int64)),
                             ns=0, node=none, w=NS(nreg=0), wg=NS(lab=none, col=none))

        def reset(self):
            pass

        def run(self, pads):
            return [NS(state=0, pos=(0.0, 0.0, 1.0))]

    key = {"kind": "spot", "kit_l3": True, "level": "f1", "id": "f1/g0/r1403", "kit": {}, "start": "f1.Z000",
           "back": ["f1.Z000", "f1.Z230"]}
    starts = {z: cert._start(sim, sim.router, key, None) for z in ("f1.Z008", "f1.Z230") for sim in [Settled(z)]}
    assert starts["f1.Z008"] is None and starts["f1.Z230"]["zone"] == "f1.Z230"
    rep = {"sha12": "a" * 12, "meta_sha12": "b" * 12, "label": "x", "pages_sha12": "c" * 12, "ticks": 1,
           "l3_mode": "scene", "outcome": {}, "inventory_changed": True, "max_err_m": 0.0}
    snap = {"kit": {}, "level": "levels/fire/f1", "tag": "x", "xemu": "x", "iso_sha12": "d" * 12, "hp": 200}
    res = {"segments": [{"n": 1}], "legs": [], "scene_ok": [True, True]}
    assert [pr.record_problem(cert._record("s", key, snap, res, rep, {"start": {"teleport": None, "zone": z}}))
            for z in ("f1.Z230", "f1.Z008")] == [None, "a location proof walks back to where it started (D122: "
                                                       "reach and come back)"]
    doused = cert._record("s", key, snap, {**res, "kit": {"water": 1}}, rep, {"start": {"teleport": None,
                                                                                          "zone": "f1.Z230"}})
    assert (doused["claim"]["kit"], doused["start"]["setup"][-1]) == ({"water": 1}, ["R2", {"water": 1}])  # R1.29e
    got = {t["id"]: t for t in cert.plan([], tmp_path / "out", 10, ["w4/g0/r645", "d1/g0/r2147"])}
    frag = got["w4/g0/r645"]
    assert (frag["kit"], frag["start"], frag["group"], frag["kit_l3"]) == ({}, "w4.Z001", "w4-k0", True)
    assert got["d1/g0/r2147"]["skip"].startswith("no arrival of the level reaches it and back with element levels")
    spot = {"goal": "w4/g0/r645"}                                   # frag_earth_1: the inventory's fge1
    verdicts = [cert.judge_spot(spot, *case) for case in (
        (True, ["af", "fge1"], 4.2, True), (True, ["af", "fge1"], 0.4, False),     # placed 4 m off; the hop's own
        (True, ["af"], 4.2, True), (False, ["fge1"], 4.2, True), (True, ["fge1"], 0.6, True))]
    assert [v["proven"] for v in verdicts] == [True, True, False, False, False]
    assert (verdicts[0]["start_goal_band"], verdicts[4]["near"], verdicts[2]["why"]) == (
        "3-10 m", True, "the goal's item not taken: xemu changed ['af']")
    text = '[[location]]\nid = "a3/g0/r2591"\nrequires = "air>=2"\nnote = "on a3.Z079"\n\n[[location]]\nid = "x"\n'
    marked = cert._mark_location(text, "a3/g0/r2591", 'proven = { by = "l3", ref = "s/a@b" }', "step R1.29")
    assert marked.split("\n")[:5] == ['[[location]]', 'id = "a3/g0/r2591"', 'proven = { by = "l3", ref = "s/a@b" }',
                                      'requires = "air>=2"', 'note = "on a3.Z079. Step R1.29"']
    assert cert._mark_location(marked, "a3/g0/r2591", "proven = 1", "again") is None
    monkeypatch.setattr(cert, "private", lambda: tmp_path / "x7")    # two folders, one key: two private starts
    (tmp_path / "x7").mkdir()
    cert._write(tmp_path / "x7" / "spot-k.json", {"start": "older, flat"})
    a, b = tmp_path / "a", tmp_path / "b"
    assert cert._read_priv(a, "spot-k") == {"start": "older, flat"}
    cert._write_priv(a, "spot-k", {"start": "a's"})
    cert._write_priv(b, "spot-k", {"start": "b's"})
    assert (cert._read_priv(a, "spot-k"), cert._read_priv(b, "spot-k")) == ({"start": "a's"}, {"start": "b's"})


def test_plan_spots_skips_a_spot_only_its_gate_gives_and_asks_a_ways_barriers_in_its_kit(tmp_path, monkeypatch):
    """AZ-517: ``devkit/reach/l3_certify.py plan --spots`` reads a spot's generated ``gated_by``, so the keylord's public
    key (w1/g0/r1717, gated by the keylord w1/g0/r321) and the guardian slot (w3/g1/r1160, by the boss
    w3/g1/r1157) are not set up as walks to a touch, the skip naming the gate; and a way's ``through`` barriers ask
    their crossing with the edge, so f1's obsidian past the firewall f1.flameSpout15 is set up at water 1."""
    from devkit.reach import l3_certify as cert
    got = {t["id"]: t for t in cert.plan([], tmp_path / "out", 10, ["w1/g0/r1717", "w3/g1/r1160", "f1/g0/r1693"])}
    assert [got[s].get("skip") for s in ("w1/g0/r1717", "w3/g1/r1160")] == [
        "its item only its gate gives, not a touch: gated_by w1/g0/r321 (keylords)",
        "its item only its gate gives, not a touch: gated_by w3/g1/r1157 (bosses)"]
    assert (got["f1/g0/r1693"]["kit"], got["f1/g0/r1693"].get("skip")) == ({"water": 1}, None)


def test_plan_spots_sets_a_spot_at_the_kit_the_logic_collects_it_at_so_rando_check_takes_its_proof(tmp_path,
                                                                                                  monkeypatch):
    """AZ-570: ``devkit/reach/l3_certify.py plan --spots`` lowers a spot's way kit to the most rando check
    (``Logic.kit_short``) takes a proof at, the way's own kept as ``kit_way``: a3/g0/r1500's way asks water 2, but
    its string leaves holding its own water power-up and the logic collects it holding water 2 with nothing there, so
    water 1; f3/g0/r1002's way asks air 3, the logic's kit air 1 (air 2 is refused too); e2/g0/r4402's asks air 1,
    the logic's none.  Three of the six kits R1.29h found refused (its kitlower.txt)."""
    from devkit.reach import l3_certify as cert
    a3 = {"air": 2, "earth": 2, "fire": 3}
    want = {"a3/g0/r1500": ({**a3, "water": 2}, {**a3, "water": 1}), "f3/g0/r1002": ({"air": 3}, {"air": 1}),
            "e2/g0/r4402": ({"air": 1, "water": 1}, {"water": 1})}
    got = {t["id"]: (t["kit_way"], t["kit"]) for t in cert.plan([], tmp_path / "out", 10, list(want))}
    logic = kept_logic()
    assert got == want
    assert [(logic.kit_short(loc, way) is None, logic.kit_short(loc, kit)) for loc, (way, kit) in got.items()] == [
        (False, None)] * 3


def test_a_contact_search_at_a_higher_frame_rate_spans_the_same_game_time(monkeypatch):
    """AZ-372: ``devkit/reach/l3_contact.py`` searches a flight at a frame rate
    in that rate's ticks: at 60 fps its step budget, longest string,
    segment, Y hold, air cap and the landing's ticks at rest are twice
    vanilla's (f3_z042 > f3_z235's 2.3-3.4 s flight fits no 120-tick air
    cap there), at 30 they are vanilla's own, and a shape it is given
    wins."""
    from devkit.reach import l3_contact as lc
    from devkit.sim.l3_search import Limits
    base = Limits()
    assert lc.limits_at(30.0, 60_000) == Limits(steps=60_000, wall_cap_s=3600.0)
    at60 = lc.limits_at(60.0, 60_000, {"temp": 30.0, "seg": 9})
    assert (at60.steps, at60.ticks, at60.hold, at60.fall, at60.seg, at60.temp) == (
        120_000, 2 * base.ticks, 2 * base.hold, 2 * base.fall, 9, 30.0)
    spec = {"module": "m", "factory": "make_goal", "kwargs": {"target": "f3.Z235", "air": 3}}
    assert lc.spec_at(spec, 30.0) == spec and lc.spec_at(spec, 60.0)["kwargs"] == {"target": "f3.Z235", "air": 3,
                                                                                   "settle": 20}


def test_a_contact_case_measured_again_keeps_its_start_and_bisects_its_slider_from_the_packs_default(tmp_path,
                                                                                                      monkeypatch):
    """``devkit/reach/l3_contact.py measure`` on a case an earlier measure
    kept a start for: a start kept with no zoning of its own stands while
    the level's kept reach model is stamped with the current zoning (no
    new start is made), and ``PACK.SLIDER`` is the pack's slider, its
    default the vanilla value the bisection starts from."""
    import contextlib
    import types

    from devkit.reach import l3_certify as cert
    from devkit.reach import l3_contact as lc
    zones = {"zones": [[0]]}
    (tmp_path / "x7" / "reach").mkdir(parents=True)
    (tmp_path / "x7" / "reach" / "w1.stamp").write_text(cert.pr.zoning(zones), encoding="utf-8")
    (tmp_path / "x11").mkdir()
    start = {"teleport": [1.0, 2.0, 3.0, 0.5]}
    (tmp_path / "x11" / "w1.lip.json").write_text(json.dumps({"start": start, "winners": []}), encoding="utf-8")
    monkeypatch.setattr(lc, "private", lambda: tmp_path / "x11")
    monkeypatch.setattr(cert, "private", lambda: tmp_path / "x7")
    monkeypatch.setattr(cert, "_reach_path", lambda level: tmp_path / "x7" / "reach" / f"{level}.pkl")
    monkeypatch.setattr(cert, "read_derived", lambda level: zones)
    monkeypatch.setattr(lc, "load_router", lambda reach, prof: None)
    monkeypatch.setattr(lc, "RouteGoal", lambda router, goal, air: None)
    monkeypatch.setattr(lc, "kit_snapshot", lambda air, base: f"{base}-air{air}")
    monkeypatch.setattr(lc, "vanilla_xbe", lambda: b"")
    # no simulator: a new start (``l3.L3``) would fail here
    monkeypatch.setattr(lc, "l3", types.SimpleNamespace(snapshot_path=str, read_meta=str, meta_sha12=len))
    monkeypatch.setattr("devkit.reach.l3_pool.Pool", lambda *a, **k: contextlib.nullcontext())
    starts = []
    monkeypatch.setattr(lc, "point", lambda pool, case, ov, *a, **k: starts.append((case.priv["start"], ov)) or {
        "reached": True, "robustness": 1.0, "tier": "standard", "seconds": 0})
    monkeypatch.setattr(lc, "regrade", lambda pool, case, *a, **k: {"strings": 0})
    rec = lc.measure("w1.lip", "player_physics.gravity", tmp_path / "out", 1, 1, 1, None, None, None)
    assert starts == [(start, None)] and rec["vanilla"] == 9.8 and list(rec["points"]) == ["9.8"]


def test_a_robustness_trial_moves_a_press_by_the_same_game_time_at_the_builds_frame_rate(monkeypatch):
    """AZ-388: ``l3_search.robustness`` moves each press a 30 fps tick
    earlier or later; at a build's 120 fps that is 4 of its ticks, by the
    same draws (so 30 fps keeps its trials), where it was 1 at any rate,
    and ``devkit/reach/l3_contact.py`` grades a string at the build's rate."""
    import types

    from devkit.sim import l3_search
    from devkit.sim.l3_search import Seg, Segment, jittered
    segs = [Seg(40, 0.0), Seg(40, 0.5, hold=24), Seg(40, 1.0), Seg(40, None, roll=12)]

    def moves(rate):
        return [[a.n - b.n for a, b in zip(jit, segs)] for jit in jittered(segs, trials=16, seed=7, rate=rate)]
    at30 = moves(30.0)
    assert {d for m in at30 for d in m} == {-1, 0, 1} and moves(120.0) == [[4 * d for d in m] for m in at30]
    from devkit.reach import l3_contact as lc
    rates = []
    monkeypatch.setattr(l3_search, "start_of", lambda sim, seg: ("start", None, 0.0, [], []))
    monkeypatch.setattr(l3_search, "confirm", lambda *a: 40)
    monkeypatch.setattr(l3_search, "robustness", lambda *a, **k: rates.append(k["rate"]) or 0.5)
    w = types.SimpleNamespace(sim=lambda *a, **k: None, goal=lambda spec: None)
    assert lc.grade(w, Segment("s"), {}, [list(s) for s in segs], 16, True, 120.0)["robustness"] == 0.5
    assert rates == [120.0]
