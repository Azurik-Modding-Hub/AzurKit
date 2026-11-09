"""A worn body's jiggle (Modkit's tests/test_player_jiggle.py, its rows no
other AzurKit test pinned, ported leanly; Steps 2.154-2.193 there): X41
(``player_model/jiggle.c``) at the pose's per-bone CALL 0xCB5CB and its
Python twin (``jiggle_rt``); a recipe's springs, keyed bones and their
refusals; the hair catalogue; and W28's collider, which keys a baked chain
out of the skin its ``clear`` lists.

The L2 rows run the game's own pose pass (0xCB730) and marker pass
(0xCBC80), as the anim step 0x43A00 runs them, on a hand-built anim object
holding booblord v3's rigged body (W24 and W29 on the vanilla
``characters.xbr``, with garret4's ``m_feet`` grown so an aligned node can
name it), a no-track looping layer and a scene -> world -> player ->
PlayerControl chain, on the USA ``default.xbe`` with X26 and X41 installed
(``devkit.sim.l2``); a second Sim runs the same calls on the vanilla XBE.
No test prints a game byte."""

from __future__ import annotations

import dataclasses
import functools
import math
import struct

import pytest
from unicorn import UC_HOOK_CODE

from azurkit.core import gate, iso
from azurkit.core.xbr.nodes import parse_toc
from azurkit.tools import characters, mods
from azurkit.tools.characters import jiggle, jiggle_rt, mesh_edit, ports
from azurkit.tools.characters._player_character import (CHECKOUT, JIGGLE_HOOK, JIGGLE_SHIM, STANCE_HOOK, STANCE_SHIM,
                                                         install_jiggle_shim, install_stance_term_shim)
from azurkit.tools.characters._player_variants import _jiggle, _variant, builtins
from azurkit.tools.characters.characters import (BoneRecord, body_at, bone_records, inverse_binds, marker_records,
                                                 read_body)
from azurkit.tools.characters.retarget import Clip, Rig, Track, grow_markers, write_clip
from devkit.sim.l2 import Sim
from tests.test_model_verbs import _v3

BODY_NAME = "townspeople/female_2"
BASE = 0x20000000
A, A2, A3 = BASE, BASE + 0x800, BASE + 0x1000          # the player's anim, an NPC's, a new player's
BONES, BONES2, BONES3 = BASE + 0x10000, BASE + 0x18000, BASE + 0x20000
CLOCK, CLIP, TABLE, MARKERS, NODE = BASE + 0x2000, BASE + 0x3000, BASE + 0x3100, BASE + 0xA000, BASE + 0xA800
SCENE, WORLD, CRITTER, CONTROL, SPECIES = BASE + 0x5000, BASE + 0x5100, BASE + 0x6000, BASE + 0x7000, BASE + 0x7800
CRITTER2, CONTROL2, OUT = BASE + 0x8000, BASE + 0x8800, BASE + 0x9000
BODY = BASE + 0x100000
SCENE_VA = 0x1BF63C
IDENT = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)
SCALE = 1.15
V0 = 4.6432748
MINUS_ONE = struct.unpack("<I", struct.pack("<f", -1.0))[0]
CHARACTERS = characters.FILES[0]

HAIR = tuple(jiggle.Bone(f"hair{k}", f"hair_{k}", "head" if k == 1 else f"hair_{k - 1}", (), (), (), 0.0, 0.0, 0.0,
                         0.0, 0.0, spring=jiggle_rt.parse_spring("hair", {
                             "freq": 2.2, "damping": 0.15, "travel": 0.08, "gain": 1.5, "rot_share": 1.0,
                             "pivot": "origin", "give": 0.05, "pace": 3.0,
                             "wall": {"axis": [0, 0, -1], "stop": 0.005}})) for k in (1, 2, 3))
"""A test chain (D485): female_2's own hair_1 -> hair_2 -> hair_3 on
springs, each link swinging about its root, each walled 5 mm off the clip's
pose along its bind -up (Step 2.169b)."""


def _v3_variant(sash: bool = False):
    """booblord v3 (``tests/test_model_verbs._v3``) as the built-in ``booblord``."""
    return _variant("booblord", _v3(sash), "built-in")


@functools.cache
def _read(path: str, name: str) -> bytes:
    with iso.Reader(path) as r:
        return r.read(name)


@functools.cache
def _rigged(path: str):
    """booblord v3's body after W24 and W29 (garret4's ``m_feet`` grown on),
    its spring rows, inverse binds, :data:`HAIR`'s places and its bones'
    parents."""
    variant = _v3_variant()
    vanilla = _read(path, CHARACTERS)
    edited = bytearray(vanilla)
    mesh_edit.write(edited, mesh_edit.plan(vanilla, BODY_NAME, variant.mesh), vanilla)
    rigged = jiggle.rig(edited, vanilla, BODY_NAME, variant.jiggle, variant.mesh)
    index, at = body_at(bytes(edited), BODY_NAME)
    payload = grow_markers(bytes(edited[at:at + parse_toc(bytes(edited))[index].size]),
                           [("m_feet", dict(marker_records(vanilla, "garret4"))["m_feet"])])
    springs = jiggle_rt.spring_bones(variant.jiggle)
    binds = inverse_binds(bytes(edited), BODY_NAME)
    records = bone_records(bytes(edited), BODY_NAME)
    parents = [r.parent for r in records]
    hair = jiggle_rt.spring_places([r.name for r in records], parents, binds, HAIR)
    return payload, rigged.bones, springs, binds, hair, parents


def _rows(path: str, kappa: float = 1.0, change: tuple = (), chain: bool = False) -> list[jiggle_rt.Row]:
    """booblord's spring rows at stiffness ``kappa``, each (role, field, value) of ``change`` changed; with
    ``chain`` :data:`HAIR`'s too."""
    _, placed, springs, binds, hair, parents = _rigged(path)
    if chain:
        placed, springs = (*placed, *hair), springs | {b.role: b.spring for b in HAIR}
    for role, key, value in change:
        springs = springs | {role: dataclasses.replace(springs[role], **{key: value})}
    return jiggle_rt.rows(placed, springs, binds, kappa, parents)


def _building(path: str):
    """The context the swap's shim installs and readers run in: the USA image's vanilla files."""
    stamp = gate.verify(path, whole=False)
    return ports.building(ports.Build(ports.Vanilla(stamp.release, stamp.path, stamped=stamp), taken=[],
                                      packs=characters.packs_view(stamp.release, mods.PACKS)))


@functools.cache
def _x41(path: str, strength: float = 1.0, kappa: float = 1.0, change: tuple = (), chain: bool = False
         ) -> tuple[bytes, dict]:
    """The USA XBE with X26 and X41 (:func:`_rows`), and the addresses of X41's words."""
    xbe = bytearray(_read(path, "default.xbe"))
    with _building(path):
        install_stance_term_shim(xbe)
        x26 = tuple(ports.trampoline_symbol_va(xbe, STANCE_HOOK, f"_player_model_stance_{w}", CHECKOUT,
                                               shim_source=STANCE_SHIM.source_path()) for w in ("held", "edge"))
        rows = _rows(path, kappa, change, chain)
        install_jiggle_shim(xbe, jiggle_rt.table(rows, struct.unpack_from("<i", _rigged(path)[0])[0], kappa, SCALE),
                            strength, x26)
        words = {name: ports.trampoline_symbol_va(xbe, JIGGLE_HOOK, f"_player_model_jiggle_{name}", CHECKOUT,
                                                  shim_source=JIGGLE_SHIM.source_path())
                 for name in ("steps", "resets", "build", "m", "shown", "kick")}
    return bytes(xbe), words


class _Scene:
    """One Sim holding the body, three anim objects, the scene chain and
    two player critters; :meth:`tick` runs 0x43A00's two passes."""

    def __init__(self, path: str, xbe: tuple[bytes, dict] | None = None, node: bool = False, weight: float = 1.0):
        payload = _rigged(path)[0]
        xbe, self.words = xbe if xbe is not None else (_read(path, "default.xbe"), {})
        self.sim = Sim(xbe)
        self.sim.uc.mem_map(BASE, 0x1000000)
        self.bones = struct.unpack_from("<i", payload, 0)[0]
        table = 4 + struct.unpack_from("<i", payload, 4)[0]
        markers = struct.unpack_from("<i", payload, 0x18)[0]
        records = 0x1C + struct.unpack_from("<i", payload, 0x1C)[0]
        self.sim.uc.mem_write(BODY, payload)
        for anim, bones in ((A, BONES), (A2, BONES2), (A3, BONES3)):
            self.put(anim, "IIII", BODY, CLOCK, bones, MARKERS)
            self.put(anim + 0x10, "If", 0, 0.25)
            self.put(anim + 0x28, "dd", -1.0, -1.0)
            for k in range(3):
                self.put(anim + 0x40 + 0x40 * k, "iII", -1, 0, 0)
            self.put(anim + 0x110, "16f", *IDENT)
            for i in range(self.bones):
                b = bones + 0xB0 * i
                self.put(b, "I10f", BODY + table + 160 * i, *([0.0] * 10))
                self.sim.uc.mem_write(b + 0x2C, b"\0")
                self.put(b + 0x30, "16f", *IDENT)
            layer = anim + 0x40   # one playing layer: CLIP (no tracks), weight ``weight``, looping
            self.put(layer, "iII", 0, CLIP, 2)
            self.put(layer + 0x10, "dffffI", 0.0, 0.0, weight, 1.0, 0.0, TABLE)
        for i in range(markers):
            self.put(MARKERS + 0x34 * i, "I", BODY + records + 0x38 * i)
        self.sim.uc.mem_write(NODE, b"m_feet\0")
        self.put(CLIP, "I", 0)
        self.put(CLIP + 0x10, "f", 1.0)
        self.put(0x1BF3F0, "III", BASE + 0x400000, BASE + 0x500000, 0)   # the stack allocator's arena
        self.put(SCENE_VA, "I", SCENE)
        self.put(SCENE + 0x2C, "I", WORLD)
        self.put(WORLD + 0xC0, "I", CRITTER)
        for critter, anim, control in ((CRITTER, A, CONTROL), (CRITTER2, A3, CONTROL2)):
            self.put(critter + 0x178, "III", SPECIES, anim, control)
            self.put(critter + 0xE4, "I", CLOCK)
            self.put(critter + 0x188, "f", SCALE)
            self.put(critter + 0x18C, "4f", 0.0, 0.0, 0.0, 1.0)
            self.put(critter + 0x1F8, "I", NODE if node else 0)
            self.put(critter + 0x204, "I", CLIP if node else 0)
        self.put(SPECIES + 0x64, "I", 0x20)

    def put(self, va: int, fmt: str, *values) -> None:
        self.sim.uc.mem_write(va, struct.pack("<" + fmt, *values))

    def get(self, va: int, fmt: str):
        return struct.unpack("<" + fmt, self.sim.uc.mem_read(va, struct.calcsize("<" + fmt)))

    def move(self, m: dict, critter: int = CRITTER, control: int = CONTROL) -> None:
        self.put(critter + 0x18C, "4f", *m["quat"])
        self.put(critter + 0x19C, "I", m["mode"])
        self.put(critter + 0x1A0, "f", m.get("window", 1.0))
        self.put(critter + 0x1A8, "d", m.get("t0", 0.0))
        self.put(critter + 0x1B0, "3f", *m["origin"])
        self.put(critter + 0x1BC, "3f", *m.get("end", m["origin"]))
        self.put(control + 0x24, "3f", *m["velocity"])
        self.put(control + 0x94, "I", m["state"])
        for anim in (A, A2):   # the pose's own motion (the root's parent matrix) and its clip's rate
            self.put(anim + 0x110, "16f", *m.get("root", IDENT))
            self.put(anim + 0x40 + 0x20, "f", m.get("rate", 1.0))

    def rate(self, anim: int = A) -> float:
        return jiggle_rt.layer_rate([self.get(anim + 0x40 + 0x40 * k, "8xI16xff")[0:3] for k in range(3)])

    def tick(self, now: float, anims=(A, A2)) -> None:
        self.put(CLOCK + 0x10, "d", now)
        for anim in anims:
            self.sim.call(0xCB730, args=(anim, 0x1AA800, MINUS_ONE), budget=4_000_000)
            self.sim.call(0xCBC80, args=(anim, 0x1AA800), budget=4_000_000)

    def world(self, bones: int, k: int) -> tuple:
        return self.get(bones + 0xB0 * k + 0x70, "16f")

    def model(self, critter: int = CRITTER) -> tuple:
        self.sim.call(0x42200, regs={"esi": OUT}, args=(critter,), budget=4_000_000)
        return self.get(OUT, "16f")

    def shown(self, row: int) -> tuple:
        return self.get(self.words["shown"] + jiggle_rt.SHOWN_SIZE * row, "6fd3f")

    def kick(self) -> tuple:
        """X41's run-start clock: s since she moved off, on, running, armed, starts."""
        return self.get(self.words["kick"], "diiiI")


def _yaw(psi: float) -> tuple:
    return (0.0, 0.0, math.sin(psi / 2.0), math.cos(psi / 2.0))


STOP, RUN, JUMP, SPIN, HIT, GAP, SWIM, GLIDE, BOB, END = 2.2, 3.6, 4.6, 6.0, 7.0, 7.6, 7.9, 8.8, 9.2, 10.4
"""The script's events (s): the stop, the run again (a 6.8 m place 0.3 s
in), the jump, the spin, the knockback, the gap, the swim stroke, the
glide, the pose's own bob (a clip at rate 1, then 2) and the end."""


def _motion(hz: int) -> list[dict]:
    """:data:`END` s at ``hz``: idle; a start (98 m/s^2) to a 7 m/s run;
    the 3-tick stop and its ring; a run with a 6.8 m place and a stop; a
    jump at vanilla's v0 and its landing; a 31 rad/s spin; a knockback; a
    0.5 s gap; a swim stroke with a hit in it; an aligned move's glide out
    and back to 0; the pose bobbing 3 cm at 2 Hz in the model, its clip at
    rate 1 for 0.6 s, then 2."""
    dt, out = 1.0 / hz, []
    x = y = z = vy = vz = psi = 0.0
    now, glide = 0.0, None
    for n in range(int(END * hz)):
        t = n * dt
        now += dt
        mode, state, place = 0, 0, False
        if 0.5 <= t < STOP or RUN <= t < RUN + 0.6:
            vy = min(7.0, vy + 98.0 * dt)
            place = abs(t - RUN - 0.3) < dt / 2
        elif HIT <= t < HIT + 0.3:
            vy = -4.0 * (1.0 - (t - HIT) / 0.3)
        elif SWIM <= t < SWIM + 0.6:   # a swim stroke, hit 0.3 s in (0x102 for 0.1 s)
            vy, state = 1.5, jiggle_rt.HIT_STATE if SWIM + 0.3 <= t < SWIM + 0.4 else jiggle_rt.SWIM_STATE
        else:
            vy = max(0.0, vy - 98.0 * dt)
        if abs(t - JUMP) < dt / 2:
            vz = V0
        if vz or z > 0.0:
            vz -= 9.8 * dt
        om = 31.0 if SPIN <= t < SPIN + 0.6 else 0.0
        if abs(t - GAP) < dt / 2:
            now += 0.5
        d = (-math.sin(psi) * vy, math.cos(psi) * vy)
        if n:
            x, y, z, psi = x + d[0] * dt, y + d[1] * dt, z + vz * dt, psi + om * dt
            if place:
                y += 6.8
            if z < 0.0:
                z, vz = 0.0, 0.0
        row = {"now": now, "quat": _yaw(psi), "origin": (x, y, z), "velocity": (d[0], d[1], vz), "mode": mode,
               "state": state}
        if GLIDE <= t < GLIDE + 0.27:   # an aligned move's glide: +0x1B0 to +0x1BC over 0.27 s by the clock
            glide = glide or (now, (x, y, z))
            row |= {"mode": 1, "origin": glide[1], "end": (glide[1][0], glide[1][1] + 0.3, glide[1][2] + 0.2),
                    "t0": glide[0], "window": 0.27}
        elif glide is not None:
            x, y, z = glide[1][0], glide[1][1] + 0.3, glide[1][2] + 0.2
            row["origin"] = (x, y, z)
        if t >= BOB:
            bob = 0.03 * math.sin(2.0 * math.pi * 2.0 * (t - BOB))
            row |= {"root": (*IDENT[:12], 0.0, 0.0, bob, 1.0), "rate": 1.0 if t < BOB + 0.6 else 2.0}
        out.append(row)
    return out


def _run(scene: _Scene, script: list[dict], rows, strength: float = 1.0, check=None) -> list[dict]:
    """``script`` through ``scene`` and the twin, comparing every spring
    bone's world each tick (within 1e-5 model units) and X41's matrix with
    0x42200's after the tick; each tick's shown words (the offset in mm,
    roll, yaw, raw, the clock and the squash's scales), the worlds X41
    left and the posed ones."""
    twin = jiggle_rt.Twin(rows, scene.bones, strength)
    out = []
    for m in script:
        scene.move(m)
        scene.tick(m["now"])
        model, steps = scene.model(), twin.steps
        worlds = {r.bone: scene.world(BONES2, r.bone) for r in rows}
        want = twin.pose(jiggle_rt.Pose("A", "P", "C", m["now"], SCALE, model, worlds, m["velocity"], m["mode"],
                                        m["state"], scene.rate()))
        got = {r.bone: scene.world(BONES, r.bone) for r in rows}
        for r in rows:
            err = max(abs(a - b) for a, b in zip(got[r.bone], want.get(r.bone, worlds[r.bone])))
            assert err < 1e-5, (m["now"], r.role, err)
        drawn = (model[i] * SCALE if i < 12 else model[i] for i in range(16))
        assert twin.steps == steps or all(math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-6)
                                          for a, b in zip(scene.get(scene.words["m"], "16f"), drawn)), m["now"]
        assert scene.get(scene.words["steps"], "I")[0] == twin.steps, m["now"]
        t, on, running, armed, starts = scene.kick()
        assert (on, running, armed, starts) == (twin.kicking, twin.running, twin.armed, twin.kicks), m["now"]
        assert abs(t - twin.kick_t) < 1e-9 or not on, m["now"]
        out.append({"now": m["now"], "shown": [scene.shown(i) for i in range(len(rows))], "got": got,
                    "worlds": worlds, "kick": (on, starts)})
        if check:
            check(m, out[-1])
    return out


SQUASHED = (("bust", "squash", (0.0, -0.08, 0.3)),)
"""The bust's squash in the L2 rows: along up 30% and along forward -8% at its full travel (D481)."""


def _det3(m) -> float:
    return (m[0] * (m[5] * m[10] - m[6] * m[9]) - m[1] * (m[4] * m[10] - m[6] * m[8])
            + m[2] * (m[4] * m[9] - m[5] * m[8]))


def test_x41s_springs_follow_their_twin_ring_at_their_damped_frequency_and_keep_their_walls(usa_iso):
    """X41's springs are its twin's (``jiggle_rt.Twin``): at 30 and 60 Hz,
    through a start, a 7 m/s run, the 3-tick stop, a jump at vanilla's v0
    and its landing, a 31 rad/s spin, a knockback, a 6.8 m place, a 0.5 s
    gap, a swim stroke hit in the water and an aligned move's glide, every
    tick booblord's jiggle bones' worlds and a hair chain's (:data:`HAIR`,
    D485) are the twin's within 1e-5 model units, X41's matrix is the
    game's 0x42200 x the drawn scale, and its step count the twin's. After
    the stop the bust rings at its damped frequency (within 5%), its first
    rebound at least 30% of its first swing; 60 Hz's stop and landing
    peaks are within 10% of 30 Hz's. The bust's squash (D481) keeps its
    volume and squashes it along up as it drops onto the landing,
    stretches it as it floats. A chain's link takes its parent's swing in
    full at any clip rate; its walls (Step 2.169b) hold every link's tip at
    most its stop nearer than the clip poses it, and turn a link its parent
    swung in past it back out. The gain moves only the springs' motion: a
    tilt shows the hang at 1, whatever the gain."""
    path = str(usa_iso)
    rows = _rows(path, change=SQUASHED, chain=True)
    assert [r.chain for r in rows] == [-1, -1, -1, 2, 3]
    peaks = {}
    for hz in (30, 60):
        ran = _run(_Scene(path, _x41(path, change=SQUASHED, chain=True), node=True), _motion(hz), rows)
        stop = [r for r in ran if STOP <= r["now"] - 1.0 / hz < RUN]
        fwd = [r["shown"][0][1] for r in stop]
        first = max(fwd, key=abs)
        after = fwd[fwd.index(first):]
        rebound = max((-v if first > 0 else v) for v in after)
        assert rebound >= 0.3 * abs(first), (hz, first, rebound)
        times = [r["now"] for r in stop]
        cross = [times[i] - fwd[i] * (times[i + 1] - times[i]) / (fwd[i + 1] - fwd[i])
                 for i in range(fwd.index(first), len(fwd) - 1)
                 if fwd[i] * fwd[i + 1] < 0.0 and STOP + 0.3 < times[i] < RUN - 0.1]
        f = (len(cross) - 1) / (2.0 * (cross[-1] - cross[0]))
        bust = rows[0].spring
        assert abs(f / (bust.freq * math.sqrt(1.0 - bust.damping ** 2)) - 1.0) < 0.05, (hz, f, cross)
        land = [r["shown"][0] for r in ran if JUMP < r["now"] < SPIN]
        peaks[hz] = (abs(first), max(abs(v[2]) for v in land))
        for r in ran[1:]:   # the first build only resets (its words not yet written)
            sc = r["shown"][0][7:10]
            assert abs(sc[0] * sc[1] * sc[2] - 1.0) < 1e-5, (hz, r["now"], sc)
            b = rows[0].bone
            assert abs(_det3(r["got"][b]) / _det3(r["worlds"][b]) - 1.0) < 1e-4, (hz, r["now"])
        low, high = min(land, key=lambda v: v[2]), max(land, key=lambda v: v[2])
        assert low[2] < -30.0 and low[9] < 0.96 and high[2] > 30.0 and high[9] > 1.02, (hz, low, high)
        turned = 0
        for r in ran[1:]:   # the walls: each tip off the clip's pose, in the bind axes as built
            for row in rows:
                if row.spring.wall is None:
                    continue
                w = r["worlds"][row.bone]
                if row.chain >= 0:
                    up = rows[row.chain].bone
                    w = jiggle_rt._mul4(jiggle_rt._mul4(w, jiggle_rt._inverse4(r["worlds"][up])), r["got"][up])
                x, axis = jiggle_rt._mul4(row.ib, w), row.spring.wall[:3]
                inv = jiggle_rt._inverse3([[x[4 * i + j] for j in range(3)] for i in range(3)])

                def tip(m, row=row):
                    t = jiggle_rt._mul4(row.ib, m)
                    return [sum(row.centre[i] * t[4 * i + j] for i in range(3)) + t[12 + j] for j in range(3)]

                def along(a, b, inv=inv, axis=axis):   # b - a along the wall's axis, model units
                    d = [q - p for p, q in zip(a, b)]
                    return sum(sum(d[i] * inv[i][j] for i in range(3)) * axis[j] for j in range(3))
                posed, built, got = tip(r["worlds"][row.bone]), tip(w), tip(r["got"][row.bone])
                assert along(posed, got) <= row.spring.wall[3] / SCALE + 1e-5, (hz, r["now"], row.role)
                turned += along(posed, built) > row.spring.wall[3] / SCALE and along(built, got) < -1e-4
        assert turned >= 10, (hz, turned)
    assert all(abs(a / b - 1.0) < 0.1 for a, b in zip(peaks[60], peaks[30])), peaks
    placed = {r.bone: r for r in rows}   # a chain takes its parent's swing in full, at any clip rate

    def chained(rate: float) -> list:
        twin, y, v, out = jiggle_rt.Twin(rows, 93), 0.0, 7.0, []
        for n in range(90):
            v = v if n < 30 else max(0.0, v - 98.0 / 30)
            y += v / 30
            twin.pose(jiggle_rt.Pose("A", "P", "C", (n + 1) / 30, SCALE, (*IDENT[:13], y, 0.0, 1.0),
                                     {k: r.wbind for k, r in placed.items()}, (0.0, v, 0.0), 0, 0, rate))
            out.append([s.offset if s else (0.0, 0.0, 0.0) for s in twin.shown[2:]])
        return out
    slow, fast = chained(1.0), chained(4.0)
    assert max(abs(a - b) for s_, f_ in zip(slow, fast) for x, y in zip(s_, f_) for a, b in zip(x, y)) < 0.01
    assert min(max(math.dist(t[k], (0.0, 0.0, 0.0)) for t in slow[30:]) for k in range(3)) > 10.0
    # the hang at 1: a 60 degree pitch at rest shows the same offset at any gain, at once and settled
    pitch = (1.0, 0.0, 0.0, 0.0, 0.0, 0.5, math.sqrt(0.75), 0.0, 0.0, -math.sqrt(0.75), 0.5, 0.0, 0.0, 0.0, 0.0, 1.0)

    def tilted(gain: float) -> list:
        rows_ = _rows(path, change=(("bust", "gain", gain), ("bust", "gravity", 1.0)))
        twin, out = jiggle_rt.Twin(rows_, 93), []
        for n in range(150):
            twin.pose(jiggle_rt.Pose("A", "P", "C", (n + 1) / 30, SCALE, pitch if n >= 60 else IDENT,
                                     {r.bone: r.wbind for r in rows_}, (0.0, 0.0, 0.0), 0, 0))
            out.append(twin.shown[0].offset if twin.shown[0] else (0.0, 0.0, 0.0))
        return out
    one, three = tilted(1.0), tilted(3.1)
    assert math.dist(one[60], (0.0, 0.0, 0.0)) > 15.0
    assert math.dist(one[60], three[60]) < 0.5 and math.dist(one[-1], three[-1]) < 0.5, (one[60], three[60])


RUNNING = (3.26691, 6.5361, 7.00009)
"""The game's run from standing, m/s a tick; its stop is 7.0 -> 3.73 -> 0.46 -> 0."""
UNKICKED = tuple((role, key, 0.0) for role in ("bust", "glutes") for key in ("kick", "kick_hold"))
"""booblord's rows with no kick (Step 2.156b's off)."""


def _start(speed: float = 7.0, turn: float = 1.75, stops=(), jump: float | None = None,
           end: float = 4.0) -> list[dict]:
    """At 30 Hz: standing 0.5 s, then off at ``speed`` (the game's ramp,
    capped), her facing turning at ``turn`` rad/s over its first 0.8 s, the
    drawn origin bobbing 4 mm at 2.5 Hz while she runs; each (t0, t1) of
    ``stops`` standing again; a jump at vanilla's v0 at ``jump`` s."""
    dt, out = 1.0 / 30, []
    x = y = z = vz = psi = v = 0.0
    run_t, ramp = None, 0
    for n in range(int(end * 30)):
        t = (n + 1) * dt
        moving = t > 0.5 and not any(a <= t < b for a, b in stops)
        if moving:
            v = min(speed, RUNNING[min(ramp, 2)])
            ramp += 1
            run_t = t if run_t is None else run_t
        else:
            v, ramp = (3.73227 if v > 6.0 else 0.46353 if v > 3.0 else 0.0), 0
        if jump is not None and abs(t - jump) < dt / 2:
            vz = V0
        if vz or z > 0.0:
            vz -= 9.8 * dt
        om = turn if run_t is not None and t - run_t < 0.8 else 0.0
        psi += om * dt
        d = (-math.sin(psi) * v, math.cos(psi) * v)
        x, y, z = x + d[0] * dt, y + d[1] * dt, max(0.0, z + vz * dt)
        if z == 0.0 and vz < 0.0:
            vz = 0.0
        bob = 0.004 * math.sin(2.0 * math.pi * 2.5 * (t - 0.5)) if v >= 5.0 and z == 0.0 else 0.0
        out.append({"now": t, "quat": _yaw(psi), "origin": (x, y, z + bob), "velocity": (d[0], d[1], vz),
                    "mode": 0, "state": 0 if z == 0.0 and not vz else 2})
    return out


def test_x41s_run_start_kicks_the_bounce_and_holds_the_swing(usa_iso):
    """AZ-678 (Step 2.156b, D518): X41's run-start clock (on the shim, the
    twin's every tick) starts when she moves off after standing: while she
    runs in the first ``kick_time`` the level drive is held and the up
    drive raised. On an arc into a run her bust's level swing over the
    first 0.75 s is at most a third of the unkicked's and its up bounce
    over the first second at least 1.2 x; 3 s on it moves as unkicked
    within 2 mm. A walk off (4 m/s) never kicks, a stop or a jump in the
    window ends the kick, a standing jump steered forward lands running with
    none, and fifteen stops and starts, each one kicked, swing her no
    further than unkicked."""
    path = str(usa_iso)
    kicked, plain = _rows(path), _rows(path, change=UNKICKED)

    def ran(script, kick: bool = True) -> list:
        return _run(_Scene(path, _x41(path, change=() if kick else UNKICKED)), script, kicked if kick else plain)

    def level(r) -> float:
        return math.hypot(r["shown"][0][0], r["shown"][0][1])

    def up_pp(rs) -> float:
        ups = [r["shown"][0][2] for r in rs]
        return max(ups) - min(ups)

    def first(rs, a, b):
        return [r for r in rs if 0.5 + a < r["now"] <= 0.5 + b]
    arc_k, arc_p = ran(_start(end=5.0)), ran(_start(end=5.0), kick=False)
    assert max(map(level, first(arc_k, 0.0, 0.75))) <= max(map(level, first(arc_p, 0.0, 0.75))) / 3.0
    assert up_pp(first(arc_k, 0.0, 1.0)) >= 1.2 * up_pp(first(arc_p, 0.0, 1.0))
    late = [max(abs(a - b) for a, b in zip(k["shown"][0][:3], q["shown"][0][:3]))
            for k, q in zip(arc_k, arc_p) if k["now"] > 3.5]
    assert late and max(late) <= 2.0, max(late)
    assert [r["kick"] for r in arc_k][-1] == (1, 1)
    walk_k, walk_p = ran(_start(speed=4.0)), ran(_start(speed=4.0), kick=False)   # a walk off never kicks
    assert [r["shown"] for r in walk_k] == [r["shown"] for r in walk_p]
    for script in (_start(stops=((1.0, 9.0),)), _start(jump=1.0)):   # a stop or a jump in the window ends it
        rs = ran(script)
        assert [r["kick"][0] for r in rs if 1.2 < r["now"]] == [0] * sum(1 for r in rs if 1.2 < r["now"])
    hop_k, hop_p = ran(_start(jump=0.5)), ran(_start(jump=0.5), kick=False)   # lands running: no kick
    assert hop_k[-1]["kick"] == (0, 0) and [r["shown"] for r in hop_k] == [r["shown"] for r in hop_p]
    stutter = _start(stops=tuple((0.8 + 0.5 * i, 1.0 + 0.5 * i) for i in range(15)), end=8.0)

    def swing(rs):
        return max(math.dist(r["shown"][0][:3], (0.0, 0.0, 0.0)) for r in rs)
    stutter_k = ran(stutter)
    assert stutter_k[-1]["kick"][1] == 16 and swing(stutter_k) <= 1.05 * swing(ran(stutter, kick=False))


CROUCH = ((-1.2, 1), (-3.0, 3), (-4.4, 11), (-5.6, 20), (-4.0, 28), (-3.4, 36), (-2.4, 42), (0.0, 44), (3.2, 42),
          (3.0, 38), (2.5, 32), (2.2, 24))
"""A 6 m fall's hard landing (state 0x100, glide mode 2 for 13 ticks), a
tick at a time: the bust's drop as drawn (m/s) and its bone's pitch
forward (degrees), before she stands (:data:`STAND`, state 0)."""
STAND = ((1.3, 20), (1.8, 15), (1.8, 10), (1.8, 6), (1.8, 3), (1.8, 1), (1.8, 0), (1.0, 0))


def _drop(height: float, about=None) -> list[dict]:
    """At 30 Hz: 0.3 s standing ``height`` m up, the fall under 9.8 m/s^2
    (state 2) and 2.5 s from its landing (state 0); with ``about`` (a point
    in the model) the landing is a hard one: :data:`CROUCH` then
    :data:`STAND`, the drawn body sinking and pitching about ``about``."""
    out, z, vz, k, sink = [], height, 0.0, None, 0.0
    for n in range(9 + int(math.sqrt(2.0 * height / 9.8) * 30) + 75):
        mode, state, pitch = 0, 0, 0.0
        if k is None and n >= 9:
            vz -= 9.8 / 30
            z, state = z + vz / 30, 2
            if z <= 0.0:
                z, vz, k, state = 0.0, 0.0, 0, 0
        elif k is not None:
            k += 1
        if about is not None and k is not None and k <= len(CROUCH) + len(STAND):
            if k:
                v, pitch = (CROUCH + STAND)[k - 1]
                sink += v / 30
            mode, state = (2, jiggle_rt.HARD_STATE) if k <= len(CROUCH) else (0, 0)
        c, s = math.cos(math.radians(pitch)), math.sin(math.radians(pitch))
        p = [a * SCALE for a in (about or (0.0, 0.0, 0.0))]   # p R = (x, y c + z s, z c - y s): about p
        out.append({"now": (n + 1) / 30, "quat": (-math.sin(math.radians(pitch) / 2.0), 0.0, 0.0,
                                                   math.cos(math.radians(pitch) / 2.0)),
                    "origin": (0.0, p[1] - p[1] * c - p[2] * s, z + sink + p[2] - p[2] * c + p[1] * s),
                    "velocity": (0.0, 0.0, vz), "mode": mode, "state": state})
    return out


def test_a_landing_bounces_the_forms_in_step_with_the_fall(usa_iso):
    """D584, D619 (Step 2.174): with her rows' ``impact`` a landing's push is
    keyed on the speed she met the ground at, along her up as drawn, and
    held through a hard landing's crouch: from 1, 3 and 6 m (6 m's a hard
    landing) every tick X41's spring bones' worlds are its twin's, her
    bust's and glutes' dives grow with the fall (3 m's at least 1.3 x 1
    m's; 6 m's past 3 m's for the bust), as their swings over the 2.5 s
    after it do, and ring down (the last 0.3 s within 15 mm); with no
    impact 6 m's dive is under 3 m's; and the same 3 m drop with no tick in
    the air (a clip's own drop while she stands) shows what it shows with
    no impact, tick for tick."""
    path = str(usa_iso)
    rows, none = _rows(path), (("bust", "impact", 0.0), ("glutes", "impact", 0.0))
    assert min(r.spring.impact for r in rows[:2]) > 0.0 and [r.role for r in rows[:2]] == ["bust", "glutes"]

    def ran(script: list[dict], change: tuple = ()) -> list[dict]:
        return _run(_Scene(path, _x41(path, change=change)), script, _rows(path, change=change))

    def swings(script: list[dict], change: tuple = ()) -> dict:
        out, run = {}, ran(script, change)
        land = next(i for i, m in enumerate(script) if i and script[i - 1]["state"] == 2 and m["state"] != 2)
        for j in (0, 1):
            up = [r["shown"][j][2] for r in run[land:]]
            out[j] = (-min(up), max(up) - min(up), max(abs(v) for v in up[-9:]))
        return out
    got, plain = {}, {}
    for h in (1.0, 3.0, 6.0):
        script = _drop(h, about=rows[0].centre if h == 6.0 else None)
        got[h], plain[h] = swings(script), swings(script, none)
    for j in (0, 1):
        dive = {h: got[h][j][0] for h in got}
        assert dive[3.0] >= 1.3 * dive[1.0] and (j or dive[6.0] > dive[3.0]), (j, got)
        assert got[1.0][j][1] < got[3.0][j][1] < got[6.0][j][1], (j, got)
        assert all(got[h][j][2] < 15.0 for h in got), (j, got)
    assert plain[6.0][0][0] < plain[3.0][0][0], plain
    standing = [m | {"state": 0} for m in _drop(3.0)]
    assert [r["shown"] for r in ran(standing)] == [r["shown"] for r in ran(standing, none)]


def _vanilla_bytes(scene: _Scene) -> dict:
    return {"A": bytes(scene.sim.uc.mem_read(A, 0x150)), "critter": bytes(scene.sim.uc.mem_read(CRITTER, 0x300)),
            "markers": bytes(scene.sim.uc.mem_read(MARKERS, 0x34)),
            "bones": bytes(scene.sim.uc.mem_read(BONES, 0xB0 * scene.bones)),
            "npc": bytes(scene.sim.uc.mem_read(BONES2, 0xB0 * scene.bones))}


def test_x41_leaves_the_pose_vanilla_where_it_must(usa_iso):
    """X41 writes the player's spring bones' worlds and nothing else, and
    draws a build vanilla wherever it must: with an aligned node set (the
    marker pass inside the pose) everything but the two spring bones'
    worlds is vanilla's, every tick; with no layer weighted (the rest path)
    the offset is applied once; a same-clock second pose pass and the
    marker pass's rest rebuild (0xCB5F0) write the same bytes; a build is
    vanilla's, and the resets count it, for the clock set back, NaN in the
    facing, a player without a PlayerControl and the old anim posed as an
    NPC's; a clip change (0xCAD40) keeps the springs within 1 mm; at rest,
    idle and at a steady 7 m/s every offset is within 0.5 mm, a place, a
    gap and a hit in the water change nothing past 1 mm; any strength and
    stiffness and rows with stiffness 0, negative damping, a travel of 0 or
    no turn leave every matrix finite (D23); and the hook's cost: an NPC's
    pose at most 6 instructions a bone and 60 more than vanilla's, the
    player's at most 7 a bone, 9,000 a spring row and 3,000 more."""
    path = str(usa_iso)
    rows = _rows(path)
    script = _motion(30)[:120]
    mine, theirs = _Scene(path, _x41(path), node=True), _Scene(path, node=True)
    spring = {r.bone for r in rows}
    for m in script:   # the aligned node: everything but the spring bones' worlds is vanilla's
        for scene in (mine, theirs):
            scene.move(m)
            scene.tick(m["now"])
        a, b = _vanilla_bytes(mine), _vanilla_bytes(theirs)
        assert [k for k in ("A", "critter", "markers", "npc") if a[k] != b[k]] == [], m["now"]
        assert [k for k in range(mine.bones) if a["bones"][0xB0 * k:0xB0 * k + (0x70 if k in spring else 0xB0)]
                != b["bones"][0xB0 * k:0xB0 * k + (0x70 if k in spring else 0xB0)]] == [], m["now"]
    rest = _Scene(path, _x41(path), node=True, weight=0.0)   # the rest path: the nested build stays vanilla
    _run(rest, script[:60], rows)
    entered = []
    hook = rest.sim.uc.hook_add(UC_HOOK_CODE, lambda uc, a, s, _: entered.append(a), begin=0xCB550, end=0xCB550)
    rest.move(script[60])
    rest.tick(script[60]["now"], (A,))
    rest.sim.uc.hook_del(hook)
    assert len(entered) == 2   # the pose's build and the nested one inside X41's 0x42200
    scene = _Scene(path, _x41(path), node=True)   # a same-clock rebuild writes the same bytes
    _run(scene, script[:40], rows)
    first = bytes(scene.sim.uc.mem_read(BONES, 0xB0 * scene.bones))
    scene.sim.call(0xCB730, args=(A, 0x1AA800, MINUS_ONE), budget=4_000_000)
    assert bytes(scene.sim.uc.mem_read(BONES, 0xB0 * scene.bones)) == first
    scene.sim.call(0xCB5F0, regs={"eax": A}, budget=4_000_000)
    assert bytes(scene.sim.uc.mem_read(BONES, 0xB0 * scene.bones)) == first
    mine, theirs = _Scene(path, _x41(path)), _Scene(path)   # the resets: each build vanilla's
    events = {30: "back", 40: "nan", 50: "no control", 60: "new player"}
    for n, m in enumerate(script[:70]):
        what = events.get(n)
        now = m["now"] - (0.2 if what == "back" else 0.0)
        before = mine.get(mine.words["resets"], "I")[0]
        for scene in (mine, theirs):
            scene.move(m | ({"quat": (math.nan, 0.0, 0.0, 1.0)} if what == "nan" else {}))
            if what == "no control":
                scene.put(CRITTER + 0x180, "I", 0)
            if what == "new player":
                scene.put(WORLD + 0xC0, "I", CRITTER2)
                scene.move(m, CRITTER2, CONTROL2)
            scene.tick(now, (A, A3) if what == "new player" else (A,))
            scene.put(CRITTER + 0x180, "I", CONTROL)
            scene.put(WORLD + 0xC0, "I", CRITTER)
        if what:
            assert _vanilla_bytes(mine)["bones"] == _vanilla_bytes(theirs)["bones"], what
            assert mine.get(mine.words["build"], "I")[0] in (0, A3), what
            assert mine.get(mine.words["resets"], "I")[0] == before + (what not in ("no control",)), what
    stop = round(STOP * 30)   # a clip change keeps the springs
    mine, ref = _Scene(path, _x41(path)), _Scene(path, _x41(path))
    for n, m in enumerate(script[:stop + 30]):
        for scene in (mine, ref):
            scene.move(m)
        if n == stop:
            mine.sim.call(0xCAD40, args=(A, 0, 0), until=0xCADDD, budget=100_000)   # its entry's stores
            assert mine.get(A + 0x30, "d")[0] == -1.0
        for scene in (mine, ref):
            scene.tick(m["now"], (A,))
        assert max(abs(a - b) for k in range(len(rows)) for a, b in zip(mine.shown(k)[:3], ref.shown(k)[:3])) <= 1.0, n
    assert mine.get(mine.words["resets"], "I")[0] == ref.get(ref.words["resets"], "I")[0]
    placed = {r.bone: r for r in rows}   # rest and no kick, on the twin (X41's arithmetic, step for step)

    def offsets(events: dict, ticks: int, speed: float, state: int = 0) -> list[list[float]]:
        twin = jiggle_rt.Twin(rows, 93)
        y, now, out = 0.0, 0.0, []
        for n in range(ticks):
            now += 0.5 if events.get(n) == "gap" else 1.0 / 30
            y += speed / 30 + (events[n] if isinstance(events.get(n), float) else 0.0)
            m = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, y, 0.0, 1.0)
            twin.pose(jiggle_rt.Pose("A", "P", "C", now, SCALE, m, {k: r.wbind for k, r in placed.items()},
                                     (0.0, speed, 0.0), 0, jiggle_rt.HIT_STATE if events.get(n) == "hit" else state))
            out.append([math.dist(s.offset, (0.0, 0.0, 0.0)) if s else 0.0 for s in twin.shown])
        return out
    assert max(max(t) for t in offsets({}, 40, 0.0)) <= 0.5
    assert max(max(t) for t in offsets({}, 60, 7.0)[10:]) <= 0.5
    for event in (6.8, 2.9, "gap"):
        plain, jumped = offsets({}, 70, 7.0), offsets({30: event}, 70, 7.0)
        assert max(abs(a - b) for p, j in zip(plain[30:], jumped[30:]) for a, b in zip(p, j)) <= 1.0, event
    hit = dict.fromkeys(range(30, 33), "hit")
    assert offsets(hit, 60, 1.5, jiggle_rt.SWIM_STATE) == offsets({}, 60, 1.5, jiggle_rt.SWIM_STATE)

    def finite(scene):
        return all(math.isfinite(x) for k in range(scene.bones) for x in scene.world(BONES, k))
    for strength, kappa, change in (   # any finite slider: every matrix finite
            (0.0, 0.0, ()), (-1.0, -1.0, ()), (1e-30, 1e-30, ()), (1e30, 1e30, ()), (-1e30, -1e30, ()),
            (3.4e38, 3.4e38, ()), (1e39, 1.0, ()),
            (1.0, 1.0, (("bust", "freq", 0.0),)), (1.0, 1.0, (("bust", "damping", -0.5),)),
            (1.0, 1.0, (("glutes", "travel", (0.0, 0.0, 0.03)),)), (1.0, 1.0, (("bust", "turn", 0.0),))):
        scene = _Scene(path, _x41(path, strength, kappa, change))
        for m in script[:60]:
            scene.move(m)
            scene.tick(m["now"], (A,))
            assert finite(scene), (strength, kappa, change, m["now"])
    counts = {}   # the cost of the hook
    for key in ("mine", "theirs"):
        scene = _Scene(path, _x41(path) if key == "mine" else None)
        for m in script[:10]:
            scene.move(m)
            scene.tick(m["now"])
        scene.move(script[10])
        scene.put(CLOCK + 0x10, "d", script[10]["now"])
        for anim in (A2, A):
            n = [0]
            hook = scene.sim.uc.hook_add(UC_HOOK_CODE, lambda uc, a, s, _, n=n: n.__setitem__(0, n[0] + 1))
            scene.sim.call(0xCB730, args=(anim, 0x1AA800, MINUS_ONE), budget=4_000_000)
            scene.sim.uc.hook_del(hook)
            counts[key, anim] = n[0]
    assert counts["mine", A2] <= counts["theirs", A2] + 6 * mine.bones + 60, counts
    assert counts["mine", A] <= counts["theirs", A] + 7 * mine.bones + 9000 * len(rows) + 3000, counts


def test_a_springs_refusals_any_finite_slider_and_x41s_table():
    """A recipe's ``spring`` (D23, D45; Step 2.156) takes any finite number
    and refuses by name an unknown or missing key, NaN or inf, both or
    neither of freq and stiffness, a stiffness with no mass, a wall whose
    axis is the zero vector or whose stop isn't finite (any other axis
    normalized, a negative stop taken) and a baked field beside it; a
    spring's coefficients at any finite stiffness slider are finite or the
    row rests: stiffness 0 has no sag, an overflowing kappa rests; X41's
    rows refuse a 33rd row and a body past 256 bones; a recipe's
    ``springs`` (D485) refuse by name a role taken, a bone the body hasn't
    and a parent that isn't the bone's, and chain a row to the nearest row
    above it; the table packs ``TABLE_SIZE`` bytes with the map, every
    row's numbers, its chain and its wall. A character's jiggle strength
    and stiffness take any finite number and refuse NaN or inf by the
    field's name (Modkit's ``--player-jiggle-*`` flags, D445)."""
    assert characters.normalize({"species": "booblord", "jiggle_strength": 0.0, "jiggle_stiffness": -2.5}) == {
        "species": "booblord", "jiggle_strength": 0.0, "jiggle_stiffness": -2.5}
    with pytest.raises(ValueError, match="^character: jiggle_stiffness inf is not a finite number"):
        characters.normalize({"species": "booblord", "jiggle_strength": 1.0, "jiggle_stiffness": math.inf})
    ok = {"freq": 2.6, "damping": 0.13, "travel": [0.05, 0.06, 0.08]}
    for doc, message in (({**ok, "wobble": 1}, "unknown key 'wobble'"),
                         ({"freq": 1, "travel": 0.1}, "missing 'damping'"),
                         ({**ok, "damping": math.nan}, "spring.damping: nan is not a finite number"),
                         ({**ok, "gain": math.inf}, "spring.gain: inf is not a finite number"),
                         ({**ok, "stiffness": 600, "mass": 2}, "exactly one"),
                         ({"damping": 0.1, "travel": 0.1}, "exactly one"),
                         ({"stiffness": 600, "damping": 0.1, "travel": 0.1}, "stiffness needs a mass"),
                         ({**ok, "travel": [0.1, 0.1]}, "spring.travel"),
                         ({**ok, "pivot": "middle"}, "spring.pivot"),
                         ({**ok, "wall": {"axis": [0, 0, 0], "stop": 0.005}},
                          r"spring.wall.axis: \[0, 0, 0\] has no direction"),
                         ({**ok, "wall": {"axis": [0, 0, -1], "stop": math.inf}},
                          "spring.wall.stop: inf is not a finite number"),
                         ({**ok, "wall": {"axis": [0, 0, -1]}}, "spring.wall: ")):
        with pytest.raises(ValueError, match=message):
            jiggle_rt.parse_spring("spring", doc)
    assert jiggle_rt.parse_spring("s", {**ok, "wall": {"axis": [1.7e308, 1.7e308, 0], "stop": 0.005}}).wall == (
        pytest.approx((math.sqrt(0.5), math.sqrt(0.5), 0.0, 0.005)))   # finite, past hypot's range: still normalized
    bone = {"role": "bust", "bone": "joint32", "parent": "spine_2", "shape": ["bust"], "groups": [1],
            "takes": ["spine_2"], "weight": 0.5, "spring": ok}
    with pytest.raises(ValueError, match=r"bones\[0\]: unknown key 'freq'"):
        _jiggle("jiggle", {"frees": [], "bones": [{**bone, "freq": 2}]})
    spec = _jiggle("jiggle", {"frees": [], "bones": [bone]})
    assert spec.bones[0].spring == jiggle_rt.parse_spring("s", ok)
    spring = jiggle_rt.parse_spring("s", {"stiffness": 640.5, "mass": 2.4, "damping": 0.13, "travel": 0.05})
    assert abs(math.sqrt(jiggle_rt.coefficients(spring).w2) / (2 * math.pi) - 2.6) < 0.01
    for kappa in (0.0, -1.0, 1e-30, 1e30, -1e30, 3.4e38):
        c = jiggle_rt.coefficients(jiggle_rt.parse_spring("s", ok), kappa)
        values = (*c.phi_land, *c.gamma_land, *c.phi_swim, *c.gamma_swim, c.alpha, c.sag_land, c.sag_swim)
        assert c.rests or all(math.isfinite(v) for v in values), kappa
    assert jiggle_rt.coefficients(jiggle_rt.parse_spring("s", {**ok, "freq": 0.0})).sag_land == 0.0
    assert jiggle_rt.coefficients(jiggle_rt.parse_spring("s", ok), 1e300).rests
    placed = [jiggle.Placed(dataclasses.replace(spec.bones[0], role=f"r{i}"), i + 1, 0, (0.0, 0.1 * i, 1.0), 0.05,
                            (0.0, 0.0, 0.0), {}, 0.5) for i in range(33)]
    binds = [(1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, -0.1 * i, -1.0, 1.0) for i in range(34)]
    springs = {p.bone.role: spec.bones[0].spring for p in placed}
    with pytest.raises(ValueError, match="33 spring rows, past X41's 32"):
        jiggle_rt.rows(placed, springs, binds)
    with pytest.raises(ValueError, match="257 bones, past X41's 256"):
        jiggle_rt.rows(placed[:1], springs, binds * 7 + binds[:19])
    link = {"role": "hair1", "bone": "b2", "parent": "b1",
            "spring": ok | {"wall": {"axis": [0.0, 3.0, -4.0], "stop": -0.002}}}
    with pytest.raises(ValueError, match="two bones or springs take the role 'bust'"):
        _jiggle("jiggle", {"frees": [], "bones": [bone], "springs": [link | {"role": "bust"}]})
    links = _jiggle("jiggle", {"frees": [], "bones": [bone], "springs": [
        link, link | {"role": "hair2", "bone": "b4", "parent": "b3"}]}).springs
    names, parents = [f"b{i}" for i in range(6)], [-1, 0, 1, 2, 3, 4]
    for named, message in (((dataclasses.replace(links[0], bone="b9"),), "has no bone 'b9'"),
                           ((dataclasses.replace(links[0], parent="b0"),), "b2's parent is b1, not 'b0'")):
        with pytest.raises(ValueError, match=message):
            jiggle_rt.spring_places(names, parents, binds[:6], named)
    chain = jiggle_rt.spring_places(names, parents, binds[:6], links)   # b2 and b4: b4 descends from b2 by b3
    assert [(pl.index, pl.parent, pl.sides) for pl in chain] == [(2, 1, 0.0), (4, 3, 0.0)]
    assert chain[0].origin == pytest.approx((0.0, 0.3, 1.0))   # the link's tip: its one child's bind origin
    rows = jiggle_rt.rows(chain, {b.role: b.spring for b in links}, binds[:6], parents=parents)
    assert [r.chain for r in rows] == [-1, 0] and [r.chain for r in jiggle_rt.rows(chain, {
        b.role: b.spring for b in links}, binds[:6])] == [-1, -1]
    rows = jiggle_rt.rows([placed[0], *chain], springs | {b.role: b.spring for b in links}, binds, parents=parents)
    table = jiggle_rt.table(rows, 10, 1.0, 1.15)   # bone 1 (W29's), its child 2 and 2's grandchild 4
    assert len(table) == jiggle_rt.TABLE_SIZE and table[:4] == jiggle_rt.MAGIC
    assert struct.unpack_from("<III", table, 4) == (3, 10, 0) and list(table[32:39]) == [0, 1, 2, 0, 3, 0, 0]
    at = jiggle_rt.HEADER_SIZE
    assert [struct.unpack_from("<iiIi", table, at + n * jiggle_rt.ROW_SIZE) for n in range(3)] == [
        (1, 0, jiggle_rt.TWO_PROBES, 0), (2, 1, 0, 1), (4, 3, 0, 2)]   # each chained to the row above it, + 1
    assert jiggle_rt.ROW_SIZE == 400 and struct.unpack_from("<4f", table, at + 256) == (0.0,) * 4
    assert struct.unpack_from("<4f", table, at + jiggle_rt.ROW_SIZE + 256) == pytest.approx(
        (0.0, 0.6, -0.8, -0.002), abs=1e-6)   # any axis normalized, a negative stop taken (D23)
    wbind = at + 2 * jiggle_rt.ROW_SIZE - 64   # a row's last 16 floats
    assert struct.unpack_from("<16f", table, wbind)[12:15] == pytest.approx((0.0, 0.2, 1.0))


def test_the_previews_targets_judge_a_bodys_breast_and_glute_rows_by_their_kinds_before_its_hair():
    """Step 2.171: booblord's spring rows run hair1-3, then her breasts and
    glutes, so :func:`jiggle_rt.targets` judges her breast row as the bust
    and her glute row as the glutes by their kinds (not the first and last
    rows), on the bands D583 raised (a run's bust up to 120 mm)."""
    calm = {"hair1": (90.0, 90.0, 90.0), "breast_right": (1.0, 1.0, 1.0), "glute_right": (1.0, 1.0, 1.0)}

    def run(name, peak=None, extrema=()):
        peak = {**calm, **(peak or {})}
        return jiggle_rt.Run(name, 30, 121, peak, {k: max(v) for k, v in peak.items()}, dict.fromkeys(peak, 1.0),
                             dict.fromkeys(peak, 0), dict.fromkeys(peak, 0.2), dict.fromkeys(peak, list(extrema)))
    ring = (60.0, -40.0, 30.0, -20.0)
    runs = [run("idle", {"hair1": (1.0, 1.0, 1.0)}), run("walk40"),
            run("run", {"breast_right": (20.0, 20.0, 70.0), "glute_right": (5.0, 5.0, 80.0)}),
            run("stop", {"breast_right": (10.0, 50.0, 40.0)}, extrema=(50.0, -30.0, 20.0, -10.0)),
            run("jump", extrema=ring), run("drop", extrema=tuple(1.5 * e for e in ring)),
            run("start", {"breast_right": (20.0, 20.0, 90.0)})]
    kinds = {"hair1": "", "breast_right": "bust", "glute_right": "glutes"}
    assert jiggle_rt.targets(runs, kinds_=kinds) == dict.fromkeys(("idle", "run", "stop", "landing", "walk", "start"),
                                                                  True)


SQUISH_OPS = [
    {"op": "push", "name": "squish side right", "bone": "spine_2", "offset": [0.0954, 0.1415, 0.0515],
     "dir": [0.711, 0.701, -0.052], "height": 0.01,
     "radius": {"in": 0.019, "out": 0.048, "up": 0.019, "down": 0.048}, "depth": 0.03, "fold": 0.0,
     "mirror": True, "region": True},
    {"op": "push", "name": "squish under right", "bone": "spine_2", "offset": [0.0662, 0.1031, 0.0085],
     "dir": [0.339, 0.292, -0.894], "height": 0.01,
     "radius": {"in": 0.048, "out": 0.048, "up": 0.048, "down": 0.048}, "depth": 0.03, "fold": 0.0,
     "mirror": True, "region": True}]
SQUISH_BONES = [{"role": f"squish_{k}_{s}", "bone": f"squish_{k}_{s}", "parent": "joint32",
                 "shape": [f"squish {k} {side}"], "groups": [1, 4], "takes": ["joint32"], "weight": 1.0, "keyed": True}
                for k in ("side", "under") for s, side in (("r", "right"), ("l", "left"))]
"""Step 2.168's four squish bones on booblord (D575), with their region pushes."""


def test_a_keyed_bone_takes_from_its_breast_and_moves_only_its_region(usa_iso):
    """W29's keyed bones (Step 2.168, D575): :data:`SQUISH_BONES` on
    booblord v3, new bones under her bust bone that take from it, so every
    vertex they reach gives them exactly what it held on the bust bone (but
    a fourth weight folded between two other bones); their regions are push
    ops that move nothing and steer no subdivision; neither her top's front
    centre over either breast nor anything outside a region carries their
    weight; they get no spring row. Refused by name: a keyed bone with a
    spring or a baked field, ``keyed`` not true, a bone taking a jiggle bone
    other than its parent listed before it, and a ``region`` that isn't
    true or false."""
    from azurkit.tools.characters import body_codec
    from azurkit.tools.characters._player_variants import _mesh_op
    from azurkit.tools.characters.jiggle import _entry

    recipe = _v3()
    ops = recipe["mesh"]["ops"]
    at = next(i for i, op in enumerate(ops) if op.get("name") == "glutes")
    ops[at:at] = SQUISH_OPS
    recipe["jiggle"]["bones"] += SQUISH_BONES
    variant = _variant("booblord", recipe, "built-in")
    vanilla = _read(str(usa_iso), CHARACTERS)
    keyed = [b for b in variant.jiggle.bones if b.keyed]
    assert [(b.role, b.parent, b.takes) for b in keyed] == [
        (f"squish_{k}_{s}", "joint32", ("joint32",)) for k in ("side", "under") for s in "rl"]

    def written(mesh, spec=None):
        edited = bytearray(vanilla)
        mesh_edit.write(edited, mesh_edit.plan(vanilla, BODY_NAME, mesh), vanilla)
        return edited, (jiggle.rig(edited, vanilla, BODY_NAME, spec, mesh) if spec else None)
    regionless = dataclasses.replace(variant.mesh, ops=tuple(op for op in variant.mesh.ops
                                                             if not getattr(op, "region", False)))
    assert len(regionless.ops) == len(variant.mesh.ops) - 2
    assert written(variant.mesh)[0] == written(regionless)[0]
    fine = mesh_edit.SubdivideOp("spine_2", (0.13, 0.17, 0.16), 0.02, (0.0719, 0.09, 0.02), True, groups=(1, 4),
                                 name="bust fine")   # nor do they steer a subdivision's split
    split = [mesh_edit.plan(vanilla, BODY_NAME, dataclasses.replace(m, ops=(fine, *m.ops)))
             for m in (variant.mesh, regionless)]
    assert split[0].added > 0 and (split[0].added, split[0].final) == (split[1].added, split[1].final)
    squished, rigged = written(variant.mesh, variant.jiggle)
    plain, _ = written(variant.mesh, dataclasses.replace(variant.jiggle, bones=tuple(
        b for b in variant.jiggle.bones if not b.keyed)))
    assert [(pl.bone.role, pl.parent) for pl in rigged.bones][2:] == [(b.role, 22) for b in keyed]
    assert jiggle_rt.spring_bones(variant.jiggle).keys() == {"bust", "glutes", "hair1", "hair2", "hair3"}

    def weights(data: bytes) -> dict:
        asset = body_codec.read_asset(data, BODY_NAME)
        out = {}
        for g in asset.lods[0].groups:   # by place: the write splits a group whose palette grew
            for v in g.vertices:
                w = {}
                for k in range(4):
                    if v.weights[k] > 0:
                        name = asset.bone_names[g.palette[_entry(v.slots[k])]]
                        w[name] = w.get(name, 0.0) + v.weights[k]
                out.setdefault((g.material, v.position, v.normal, v.uv), []).append(w)
        return out
    mine, theirs = weights(bytes(squished)), weights(bytes(plain))
    assert mine.keys() == theirs.keys()
    reached = folded = 0
    for key in mine:
        for w, was in zip(mine[key], theirs[key]):
            sq = sum(x for n, x in w.items() if n.startswith("squish_"))
            reached += sq > 0
            assert abs(was.get("joint32", 0.0) - w.get("joint32", 0.0) - sq) < 1e-6, key
            folded += any(abs(w.get(n, 0.0) - was.get(n, 0.0)) > 1e-6 for n in {*w, *was}
                          if n != "joint32" and not n.startswith("squish_"))
    assert reached > 60 and folded <= 10, (reached, folded)
    cloth = body_codec.read_asset(bytes(squished), BODY_NAME).lods[0].groups[4].material
    for side in (1, -1):   # her top's front-most point over each breast: no squish weight
        apex = max(((key[1], w) for key, ws in mine.items() if key[0] == cloth for w in ws
                    if side * key[1][0] > 0.02 and w.get("joint32", 0.0) >= 0.3), key=lambda t: t[0][1])
        assert not any(n.startswith("squish_") for n in apex[1]), apex
    ok = {"freq": 2.6, "damping": 0.13, "travel": [0.05, 0.06, 0.08]}
    bone = {"role": "squish", "bone": "squish_a", "parent": "joint32", "shape": ["bust"], "groups": [1],
            "takes": ["joint32"], "weight": 1.0, "keyed": True}
    for doc, message in (({**bone, "spring": ok}, r"bones\[0\]: unknown key 'spring'"),
                         ({**bone, "freq": 2.0}, r"bones\[0\]: unknown key 'freq'"),
                         ({**bone, "keyed": False}, r"bones\[0\]\.keyed: False is not true")):
        with pytest.raises(ValueError, match=message):
            _jiggle("jiggle", {"frees": [], "bones": [doc]})
    other = dataclasses.replace(keyed[0], parent="spine_2")
    with pytest.raises(ValueError, match=r"jiggle.bones\[2\].takes: 'joint32' is a jiggle bone; a bone takes from "
                                         "one only as its parent"):
        jiggle.rig(bytearray(vanilla), vanilla, BODY_NAME, dataclasses.replace(
            variant.jiggle, bones=(*variant.jiggle.bones[:2], other)), variant.mesh)
    push = {"op": "push", "bone": "spine_2", "dir": [1.0, 0.0, 0.0], "height": 0.01,
            "radius": {"in": 0.05, "out": 0.05, "up": 0.05, "down": 0.05}, "depth": 0.03}
    assert _mesh_op("op", {**push, "region": True}).region and not _mesh_op("op", push).region
    with pytest.raises(ValueError, match=r"op.region 'yes' is not true or false"):
        _mesh_op("op", {**push, "region": "yes"})


@pytest.mark.parametrize("verb", ["jiggle", "dress", "pose"])
def test_the_model_verbs_weigh_a_dressed_body_against_a_default_builds_128_mib_lines(verb, usa_iso, tmp_path,
                                                                                   monkeypatch, capsys):
    """``model jiggle``, ``dress`` and ``pose`` dress the body as a build
    does, on the packs on by default (Step 2.162d, D528) for its default
    128 MiB machine (D588, Step 2.162k): the dress reads a default.xbe
    holding the 42 MiB load budget and both upper packs, and weighs the
    body against the 128 MiB lines, so a body of 20 MiB own runs (past the
    64 MiB lines' 14) is named as one that plays right only at 128 MiB;
    nothing is written when the dress stops."""
    from azurkit.tools.characters import _player_character, model_inspect
    from devkit.models import model

    def weighed(game, *_a, ram=None, **_k):   # the real weighing at the ram the verb asked for, then stop
        said = _player_character._load_budget(game, "b", "who", False, ram)
        raise ValueError(f"budget {model_inspect.budget_of(bytes(game['default.xbe'])) // model_inspect.MiB} MiB: "
                         f"{said}")
    monkeypatch.setattr(model_inspect, "own_runs", lambda *_a, **_k: {
        "bytes": 20 * model_inspect.MiB, "runs": 2, "largest": 10 * model_inspect.MiB, "by_tag": {}})
    monkeypatch.setattr(_player_character, "apply_player_model", weighed)
    out = ["--out", str(tmp_path / ("dressed" if verb == "dress" else "posed.npz"))] if verb != "jiggle" else []
    code = model.main([verb, "booblord", "--iso", str(usa_iso), *out])
    assert code == 1 and "budget 42 MiB: ['  Player model budget: its own load runs, 20.00 MiB, pass the 14 MiB a " \
        "64 MiB machine takes: this build plays right only on a 128 MiB one" in capsys.readouterr().err
    assert not list(tmp_path.iterdir())


HAIR_BODIES = {**dict.fromkeys(("girlchild_1", "girlchild_2", "girlchild_farmer_1", "girlchild_farmer_2"), "braid"),
               **dict.fromkeys(("female_1", "female_2", "female_3", "female_4"), "tail")}


def test_every_body_the_hair_catalogue_lists_springs_its_whole_hair_chain_walled_toward_its_head(usa_iso):
    """Step 2.169f (D536, D737): ``chains.json`` lists the bodies whose hair
    X41 swings when the player wears them with no jiggle of their own: the
    girls' ponytails (2.2/2.0/1.8 Hz), the townswomen's tails (D505's
    hair1-3 drive, booblord's springs) and beamlord's base's five locks
    (balthazar_airship, 3 Hz). On the vanilla ``characters.xbr`` each
    body's rows are every hair row ``model chains`` finds (each link
    weighing vertices), place on its bones, chain root to tip and pack into
    X41's table within its 32 rows, each walled at most 3 mm off the clip's
    pose toward its head; a body it doesn't list (a townsman) gets none."""
    from azurkit.tools.characters import model_chains
    from azurkit.tools.characters._player_variants import chain_springs

    data = _read(str(usa_iso), CHARACTERS)
    bodies = {f"townspeople/{b}": kind for b, kind in HAIR_BODIES.items()} | {"balthazar_airship": "locks"}
    dressed = {b.bone: b.spring for b in builtins()["booblord"].jiggle.springs}
    for body, kind in bodies.items():
        hair = chain_springs(body)
        found = [c for c in model_chains.chains(data, body)["chains"] if c["kind"] == "hair" and c["rows"]]
        assert [b.bone for b in hair] == [r["bone"] for c in found for r in c["rows"]], body
        assert all(li["vertices"] > 0 for c in found for li in c["links"]), body
        records, binds = bone_records(data, body), inverse_binds(data, body)
        names, parents = [r.name for r in records], [r.parent for r in records]
        rows = jiggle_rt.rows(jiggle_rt.spring_places(names, parents, binds, hair), {b.role: b.spring for b in hair},
                              binds, parents=parents)
        assert [r.chain for r in rows] == [-1 if names[r.parent] == "head" or "base" in names[r.parent] else n - 1
                                           for n, r in enumerate(rows)], body
        table = jiggle_rt.table(rows, len(names))
        assert (len(table), struct.unpack_from("<I", table, 4)[0]) == (jiggle_rt.TABLE_SIZE, len(rows)), body
        assert [table[32 + r.bone] for r in rows] == list(range(1, len(rows) + 1)), body
        head = dict(read_body(data, body).bones)["head"]
        for r in rows:
            mid = [(a + b) / 2.0 for a, b in zip(r.wbind[12:15], r.centre)]
            toward = sum(w * (h - m) for w, h, m in zip(r.spring.wall, head, mid))
            assert 0.0 <= r.spring.wall[3] <= 0.003 and toward > 0, (body, r.role)
        assert [r.spring.freq for r in rows] == {"braid": [2.2, 2.0, 1.8], "tail": [2.0] * 3,
                                                 "locks": [3.0] * 15}[kind], body
        if kind == "tail":   # D505's hair1-3 drive, as booblord wears it
            assert [dataclasses.replace(r.spring, wall=None, travel=(0.0,) * 3) for r in rows] == [
                dataclasses.replace(dressed[b.bone], travel=(0.0,) * 3) for b in hair]
    assert chain_springs("townspeople/male_6") == ()


# --------------------------------------------------------------------------- W28's collider


def _box(lo, hi, step=0.01):
    """A box's skin: points ``step`` apart over its six faces, each with its outward normal."""
    out = []
    for a in range(3):
        b, c = (a + 1) % 3, (a + 2) % 3
        nb, nc = round((hi[b] - lo[b]) / step), round((hi[c] - lo[c]) / step)
        for side, at in ((-1.0, lo[a]), (1.0, hi[a])):
            for i in range(nb + 1):
                for j in range(nc + 1):
                    p, n = [0.0] * 3, [0.0] * 3
                    p[a], n[a] = at, side
                    p[b], p[c] = lo[b] + (hi[b] - lo[b]) * i / nb, lo[c] + (hi[c] - lo[c]) * j / nc
                    out.append((tuple(p), tuple(n)))
    return out


def _tail(skins):
    """W28's collider on a three-link tail (``link1``-``link3``, under
    ``head``) hanging from 1.58 m to 1.12 m, 15 cm behind the body's
    middle, and the skin (mesh group 1) of each of ``skins`` (name, origin,
    [(point by it, normal)]), a bone under the root: the rig, the tail's
    placed jiggle bones and vertices, its :class:`~jiggle.Clear` and
    collider, and a function of a clip giving the most any tail point lies
    inside a box (its bone index: (lo, hi) at rest, each bone moved only)
    over 61 times."""
    I = (0.0, 0.0, 0.0, 1.0)   # noqa: E741
    origins = {"root": (0.0, 0.0, 0.0), "torso": (0.0, 0.0, 1.0), "head": (0.0, 0.0, 1.6)}
    ring = [(0.01, 0.0), (-0.01, 0.0), (0.0, 0.01), (0.0, -0.01)]
    tail = [(f, (dx, -0.15 + dy, 1.58 - 0.46 * f)) for f in [i / 46 for i in range(47)] for dx, dy in ring]
    share = [[max(0.0, 1.0 - abs(f - n / 3) * 3) if not (n == 3 and f >= 1.0) else 1.0 for n in (1, 2, 3)]
             for f, _ in tail]
    for n in (1, 2, 3):
        mass = sum(s[n - 1] for s in share)
        origins[f"link{n}"] = tuple(sum(s[n - 1] * p[c] for s, (_, p) in zip(share, tail)) / mass for c in range(3))
    origins.update({name: o for name, o, _ in skins})
    names = ["root", "torso", "head", "link1", "link2", "link3", *(name for name, _, _ in skins)]
    parents = [-1, 0, 1, 2, 3, 4, *(0 for _ in skins)]
    records = tuple(BoneRecord(n, p, False, I, I, tuple(a - b for a, b in zip(
        origins[n], origins[names[p]] if p >= 0 else (0.0, 0.0, 0.0))), I, (1.0, 1.0, 1.0))
        for n, p in zip(names, parents))
    rig = Rig("slab", records, tuple(origins[n] for n in names), (I,) * len(names), ())
    binds = [(1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, *(-c for c in origins[n]), 1.0)
             for n in names]
    verts = []
    for s, (_, p) in zip(share, tail):
        w = [1.0 - sum(s), *s]
        order = sorted(range(4), key=lambda k: -w[k])
        verts.append((p, (0.0, 0.0, 1.0), tuple(w[k] for k in order), tuple(order)))
    skin = [(tuple(a + b for a, b in zip(o, q)), n, (1.0, 0.0, 0.0, 0.0), (e, 0, 0, 0))
            for e, (_, o, points) in enumerate(skins) for q, n in points]
    groups = [([2, 3, 4, 5], verts), ([6 + e for e in range(len(skins))], skin)]
    bone = functools.partial(jiggle.Bone, shape=("tail",), groups=(0,), takes=("head",), weight=1.0, freq=1.3,
                             damping=0.22, travel=0.02, turn=0.12, hang=0.6)
    placed = tuple(jiggle.Placed(bone(role=f"link{n}", bone=f"link{n}", parent=names[1 + n]), 2 + n, 1 + n,
                                 origins[f"link{n}"], 0.005, records[2 + n].t, {}, 1.0) for n in (1, 2, 3))
    clear = jiggle.Clear(("link1", "link2", "link3"), (1,), tuple(name for name, _, _ in skins), 0.004)

    def deepest(clip, boxes) -> float:
        worst = -1.0
        for i in range(61):
            posed = {k: jiggle._posed(rig, clip, jiggle._chain(rig, k))(clip.length * i / 60)
                     for k in range(len(names))}
            for p, _, w, bones in verts:
                q = [sum(x * (posed[b][1][c] + jiggle._turn(posed[b][0], tuple(a - o for a, o in zip(
                    p, origins[names[b]])))[c]) for x, b in zip(w, (2 + e for e in bones))) for c in range(3)]
                for k, (lo, hi) in boxes.items():
                    o = [a - b for a, b in zip(posed[k][1], origins[names[k]])]
                    worst = max(worst, min(min(q[a] - lo[a] - o[a], hi[a] + o[a] - q[a]) for a in range(3)))
        return worst
    return rig, binds, groups, placed, clear, jiggle.collider(rig, binds, groups, placed, clear), deepest


def _moved(k: int, comp: int, rest: float, path) -> Track:
    """Bone ``k``'s translation ``comp`` keyed at ``rest`` plus each (time, offset) of ``path``, flat."""
    return Track(k, comp, tuple((t, rest + v, 0.0, 0.0) for t, v in path))


def _pitched(deg: float) -> Clip:
    """The head (bone 2) pitched ``deg`` degrees about x over the clip's first half, then held."""
    h = math.radians(deg) / 2.0
    return Clip(1.0, (Track(2, 3, ((0.0, 0.0, 0.0, 0.0), (0.5, math.sin(h), 0.0, 0.0), (1.0, math.sin(h), 0.0, 0.0))),
                      Track(2, 6, ((0.0, 1.0, 0.0, 0.0), (0.5, math.cos(h), 0.0, 0.0), (1.0, math.cos(h), 0.0, 0.0)))),
                ())


BACK = [((x / 100, -0.1, z / 100), (0.0, -1.0, 0.0)) for x in range(-15, 16) for z in range(90, 140)]
"""A slab's back, 5 cm in front of the hanging tail."""
TOP = [((x / 100, y / 100, 1.4), (0.0, 0.0, 1.0)) for x in range(-15, 16) for y in range(-10, 11)]
"""The slab's top."""
SLAB = {6: ((-0.15, -0.1, 0.9), (0.15, 0.1, 1.4))}
CLEAR_DOC = {"frees": [], "bones": [{"role": "a", "bone": "a", "parent": "head", "shape": ["s"], "groups": [0],
                                     "takes": ["head"], "weight": 1.0, "freq": 1.0, "damping": 0.2, "travel": 0.02,
                                     "turn": 0.1}]}


def test_a_cleared_chain_bends_out_of_each_skin_group_its_clear_or_clip_lists_where_its_spring_alone_goes_in():
    """W28's collider (Step 2.154b, D617): a three-link tail hanging behind a
    slab's back, its head pitched back 40 degrees so the tail swings into
    the slab. Its springs alone leave tail points centimetres inside; with
    ``clear`` every point stays outside at every key and between them, the
    tail bent out from its root (the first link turned, eased in from
    rest); a clip pitching the head away keys as with no collider, and so
    does one that keys a link of the chain itself (Step 2.168). AZ-739
    (Step 2.169c): a clear lists several skin groups and keeps the tail out
    of each, and a clear's ``clips`` names a clip with its own groups
    (:func:`jiggle.keyed_each` keys each job with the collider its key
    names; a job with none, with none). The recipe's ``clear`` parses; an
    unknown key, a link that isn't a baked jiggle bone of the chain, links
    that weigh no vertex, groups with no vertex of its bones and ``clips``
    that aren't a map of clip names to mesh groups are refused by name."""
    side = [((0.45, y / 100, z / 100), (1.0, 0.0, 0.0)) for y in range(-20, -9) for z in range(135, 146)]
    rig, binds, groups, placed, clear, col, deepest = _tail([("slab", (0.0, 0.0, 0.0), BACK + TOP)])
    back_clip, away = _pitched(40.0), _pitched(-40.0)
    plain = jiggle.keyed(rig, back_clip, placed, 15.0, 1.0, 1.0, False)[0]
    kept = jiggle.keyed(rig, back_clip, placed, 15.0, 1.0, 1.0, False, col)[0]
    assert deepest(plain, SLAB) > 0.03 and deepest(kept, SLAB) < 0.001, (deepest(plain, SLAB), deepest(kept, SLAB))
    x = {tr.target: tr for tr in kept.bones if tr.comp == 3 and tr.target >= 3}
    assert 3 in x and max(abs(k[1]) for k in x[3].keys) > 0.05 and abs(x[3].keys[0][1]) < 0.01   # eased in from rest
    assert [tr for tr in kept.bones[:2]] == list(back_clip.bones)
    assert write_clip(jiggle.keyed(rig, away, placed, 15.0, 1.0, 1.0, False, col)[0]) == write_clip(
        jiggle.keyed(rig, away, placed, 15.0, 1.0, 1.0, False)[0])
    assert write_clip(jiggle.keyed(rig, back_clip, placed[1:], 15.0, 1.0, 1.0, False, col)[0]) == write_clip(
        jiggle.keyed(rig, back_clip, placed[1:], 15.0, 1.0, 1.0, False)[0])   # link1 the clip's own
    assert set(col.tail["target"].tolist()) == {0.004} and set(col.tail["owner"].tolist()) == {0, 1, 2}
    for links, message in ((("link1", "link3"), r"links\[1\]: 'link3''s parent isn't 'link1'"),
                           (("torso",), r"links\[0\]: 'torso' is no baked jiggle bone")):
        with pytest.raises(ValueError, match=message):
            jiggle.collider(rig, binds, groups, placed, dataclasses.replace(clear, links=links))
    with pytest.raises(ValueError, match=r"jiggle.clear.links: they weigh no vertex half or more"):
        jiggle.collider(rig, binds, [(groups[0][0], []), groups[1]], placed, clear)
    rig, binds, groups, placed, clear, _, deepest = _tail([("slab", (0.0, 0.0, 0.0), BACK)])
    moved = [groups[0], ([], []), groups[1]]   # the slab's back in group 2, group 1 empty
    col2 = jiggle.collider(rig, binds, moved, placed, dataclasses.replace(clear, groups=(1, 2)))
    assert deepest(jiggle.keyed(rig, back_clip, placed, 15.0, 1.0, 1.0, False, col2)[0], SLAB) < 0.001
    with pytest.raises(ValueError, match=r"jiggle.clear: groups \[1\] have no vertex of its bones"):
        jiggle.collider(rig, binds, moved, placed, clear)
    rig, binds, groups, placed, clear, _, deepest = _tail([("slab", (0.0, 0.0, 0.0), BACK),
                                                           ("side", (0.0, 0.0, 0.0), side)])
    (pal, skin) = groups[1]
    split = [groups[0], *(([pal[e]], [(q, n, w, (0, 0, 0, 0)) for q, n, w, s_ in skin if s_[0] == e]) for e in (1, 0))]
    cols = {k: jiggle.collider(rig, binds, split, placed, dataclasses.replace(clear, groups=g))
            for k, g in (("", (1, 2)), ("touchdown", (1,)))}
    both, own, bare = jiggle.keyed_each(rig, 15.0, 1.0, cols, [(back_clip, placed, 1.0, False, k)
                                                                for k in ("", "touchdown", None)])
    assert both == jiggle.keyed(rig, back_clip, placed, 15.0, 1.0, 1.0, False, cols[""])
    assert own == jiggle.keyed(rig, back_clip, placed, 15.0, 1.0, 1.0, False, cols["touchdown"])
    assert bare == jiggle.keyed(rig, back_clip, placed, 15.0, 1.0, 1.0, False)
    assert deepest(both[0], SLAB) < 0.001 and deepest(own[0], SLAB) > 0.03 and deepest(bare[0], SLAB) > 0.03
    doc = CLEAR_DOC | {"clear": {"links": ["a"], "group": 1, "bones": ["spine_2", "neck"], "standoff": 0.006}}
    assert _jiggle("jiggle", doc).clear == jiggle.Clear(("a",), (1,), ("spine_2", "neck"), 0.006)
    doc = CLEAR_DOC | {"clear": {"links": ["a"], "group": [1, 2], "bones": ["spine_2"], "clips": {"touchdown": [1]}}}
    assert _jiggle("jiggle", doc).clear == jiggle.Clear(("a",), (1, 2), ("spine_2",), 0.004, (("touchdown", (1,)),))
    for change, message in (({"gap": 1}, r"jiggle.clear: unknown key 'gap'"),
                            ({"clips": ["touchdown"]},
                             r"jiggle.clear.clips: \['touchdown'\] is not a map of clip names"),
                            ({"clips": {"touchdown": []}}, r"jiggle.clear.clips.touchdown: \[\] is not a list of mesh "
                                                           "group")):
        with pytest.raises(ValueError, match=message):
            _jiggle("jiggle", {**doc, "clear": {**doc["clear"], **change}})


def _held_end(kept: Clip) -> Clip:
    """``kept``'s last pose alone: each track held at its last key."""
    return Clip(1.0, tuple(Track(tr.target, tr.comp, ((0.0, tr.keys[-1][1], 0.0, 0.0), (1.0, tr.keys[-1][1], 0.0, 0.0)),
                                 tr.modes) for tr in kept.bones), ())


def _held(rig, clip, placed, col) -> Clip:
    return jiggle.keyed(rig, clip, placed, 15.0, 1.0, 1.0, False, dataclasses.replace(col, held=True))[0]


def test_a_held_clips_last_pose_is_kept_out_draped_back_down_and_eased_from_key_to_key(monkeypatch):
    """Step 2.169d (AZ-739): a clear's ``held`` names a clip whose last pose
    the game holds (a death): its collider solves it from its last key
    back, each link turned for the points of every link under it too. A bar
    sweeping back through the hanging tail to just behind it: the plain
    clear keeps the way its first touch pushed the tail and ends with it in
    the bar; held, the last pose is out. A floor rising under the tail to
    just below its last link's root: held, the links above turn for it.
    Step 2.193 (AZ-762): a held clip's links under a lifted one turn back
    toward their unturned way as far as the tail under them stays out (the
    drape): a bar up through the first link leaves the last link's world
    turn under a quarter of the first's, no point in the bar. Its record
    (F1): a link's drape changes at most ``CLEAR_DRAPE_RATE`` a second and,
    once the clip has come to rest (``CLEAR_REST``), never more than a
    later key's: a shelf rising under the tail for a moment lifts its last
    link over 80 degrees, and while it is up that turn dips less than 20
    degrees from its peak (40 with the rest hold off, the rate cap alone).
    The recipe's ``held`` parses, and one that isn't a list is refused."""
    rig, _, _, placed, _, col, deepest = _tail([("bar", (0.0, -0.05, 1.3), _box((-0.15, -0.02, -0.08),
                                                                               (0.15, 0.02, 0.08)))])
    bar = {6: ((-0.15, -0.07, 1.22), (0.15, -0.03, 1.38))}
    clip = Clip(1.0, (_moved(6, 1, -0.05, ((0.0, 0.0), (0.2, 0.0), (0.7, -0.14), (1.0, -0.14))),), ())
    plain, held = jiggle.keyed(rig, clip, placed, 15.0, 1.0, 1.0, False, col)[0], _held(rig, clip, placed, col)
    assert deepest(_held_end(plain), bar) > 0.01 and deepest(_held_end(held), bar) < -0.005
    rig, _, _, placed, _, col, deepest = _tail([("floor", (0.0, -0.15, 0.95), _box((-0.15, -0.15, -0.05),
                                                                                  (0.15, 0.15, 0.05)))])
    floor = {6: ((-0.15, -0.3, 0.9), (0.15, 0.0, 1.0))}
    clip = Clip(1.0, (_moved(6, 2, 0.95, ((0.0, 0.0), (0.6, 0.0), (0.9, 0.195), (1.0, 0.195))),), ())
    plain, held = jiggle.keyed(rig, clip, placed, 15.0, 1.0, 1.0, False, col)[0], _held(rig, clip, placed, col)
    assert deepest(_held_end(plain), floor) > 0.02 and deepest(_held_end(held), floor) < 0.0
    rig, _, _, placed, _, col, deepest = _tail([("bar", (0.0, -0.10, 1.47), _box((-0.15, -0.02, -0.03),
                                                                                (0.15, 0.02, 0.03)))])
    bar = {6: ((-0.15, -0.12, 1.44), (0.15, -0.08, 1.50))}
    held = _held(rig, Clip(1.0, (_moved(6, 1, -0.10, ((0.0, 0.0), (0.6, 0.0), (0.9, -0.05), (1.0, -0.05))),), ()),
                 placed, col)

    def turn(clip: Clip, k: int, t: float) -> float:   # link k's world turn at t, degrees
        q = jiggle._posed(rig, clip, jiggle._chain(rig, k))(t)[0]
        return math.degrees(2.0 * math.acos(min(1.0, abs(q[3]))))
    first, last = turn(held, 3, 1.0), turn(held, 5, 1.0)
    assert first > 10.0 and last < 0.25 * first and deepest(_held_end(held), bar) < 0.0, (first, last)
    rig, _, _, placed, _, col, _ = _tail([("shelf", (0.0, -0.30, 1.20), _box((-0.15, -0.05, -0.02),
                                                                             (0.15, 0.05, 0.02)))])
    clip = Clip(1.0, (_moved(6, 1, -0.30, ((0.0, 0.0), (0.4, 0.0), (0.47, 0.17), (0.53, 0.17), (0.6, 0.0),
                                           (1.0, 0.0))),), ())

    def turns() -> list[float]:   # the last link's world turn at each key, degrees
        held = _held(rig, clip, placed, col)
        return [turn(held, 5, i / 15) for i in range(16)]
    eased = turns()
    assert max(eased) > 80.0 and min(eased[6:10]) > max(eased) - 20.0, eased
    monkeypatch.setattr(jiggle, "CLEAR_REST", -1.0)
    capped = turns()
    assert max(capped) > 80.0 and min(capped[6:10]) > max(capped) - 40.0, capped
    doc = CLEAR_DOC | {"clear": {"links": ["a"], "group": [1, 2], "bones": ["spine_2"], "held": ["die_2"]}}
    assert _jiggle("jiggle", doc).clear.held == ("die_2",)
    with pytest.raises(ValueError, match=r"jiggle.clear.held: 'die_2' is not a list of clip names"):
        _jiggle("jiggle", {**doc, "clear": {**doc["clear"], "held": "die_2"}})


def test_a_cleared_chain_keeps_its_way_through_a_second_contact_and_swings_aside_where_pitch_cant_clear():
    """W28's collider (Step 2.154b's reviews): a bar in front of the tail
    touches it, draws off and in two frames comes back past the tail's
    middle: the first link keeps the way it took (its x keys never change
    sign from one key to the next) and the tail stays out of the bar, which
    its springs alone don't; in a loop the same holds for a contact across
    its seam. A wall from the side, taller and deeper than any pitch takes
    the tail out of, is cleared by swinging the first link sideways (its y
    keyed, no x); in a loop whose contact is just past its start the swing
    eases in before the seam, so the loop doesn't snap there."""
    bar = {6: ((-0.15, -0.07, 1.43), (0.15, -0.03, 1.47))}
    rig, _, _, placed, _, col, deepest = _tail([("bar", (0.0, -0.05, 1.45), _box((-0.15, -0.02, -0.02),
                                                                                 (0.15, 0.02, 0.02)))])
    for loop, path in ((False, ((0.0, 0.0), (0.15, 0.0), (0.25, -0.075), (0.35, -0.075), (0.45, 0.0),
                                (0.5 + 1 / 120, 0.0), (0.5 + 1 / 60, -0.115), (0.6, -0.115), (0.8, 0.0), (1.0, 0.0))),
                       (True, ((0.0, -0.075), (0.08, -0.075), (0.18, 0.0), (0.78, 0.0), (0.88, -0.115),
                               (1.0, -0.075)))):   # the loop's contact across its seam keeps one way round it
        clip = Clip(1.0, (_moved(6, 1, -0.05, path),), ())
        plain = jiggle.keyed(rig, clip, placed, 15.0, 1.0, 1.0, loop)[0]
        kept = jiggle.keyed(rig, clip, placed, 15.0, 1.0, 1.0, loop, col)[0]
        assert deepest(plain, bar) > 0.01 and deepest(kept, bar) < 0.001, (loop, deepest(plain, bar),
                                                                           deepest(kept, bar))
        x = [k[1] for k in next(tr for tr in kept.bones if (tr.target, tr.comp) == (3, 3)).keys]
        assert max(abs(v) for v in x) > 0.2 and all(a * b >= 0.0 for a, b in zip(x, x[1:])), x
    wall = {6: ((0.25, -0.75, 0.9), (0.35, 0.45, 1.5))}
    rig, _, _, placed, _, col, deepest = _tail([("wall", (0.25, -0.15, 1.2), _box((0.0, -0.6, -0.3), (0.1, 0.6, 0.3),
                                                                                  0.02))])
    for loop, path in ((False, ((0.0, 0.0), (0.2, 0.0), (0.4, -0.265), (0.6, -0.265), (0.8, 0.0), (1.0, 0.0))),
                       (True, ((0.0, 0.0), (0.04, -0.265), (0.12, -0.265), (0.25, 0.0), (1.0, 0.0)))):
        clip = Clip(1.0, (_moved(6, 0, 0.25, path),), ())
        plain = jiggle.keyed(rig, clip, placed, 15.0, 1.0, 1.0, loop)[0]
        kept = jiggle.keyed(rig, clip, placed, 15.0, 1.0, 1.0, loop, col)[0]
        assert deepest(plain, wall) > 0.01 and deepest(kept, wall) < 0.001, (loop, deepest(plain, wall),
                                                                             deepest(kept, wall))
        mine = {tr.comp: [k[1] for k in tr.keys] for tr in kept.bones if tr.target == 3}
        assert max(abs(v) for v in mine[4]) > 0.2 and not any(mine[3]), mine
        if loop:   # eased in over the two keys before the seam: a third and two thirds of the turn at its start
            turn = [2.0 * math.atan(v) for v in mine[4]]
            assert turn[-3:] == pytest.approx([turn[0] / 3.0, 2.0 * turn[0] / 3.0, turn[0]], rel=0.02), turn
