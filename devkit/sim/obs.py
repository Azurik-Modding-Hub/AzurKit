"""One observation of the player, read the same way by L3 and the xemu replayer (Step X.10; from Modkit, Step 4.14a1).

:func:`read` decodes one field table through any ``read(va, n) -> bytes``: L3's memory, or the gdbstub of a halted
xemu.  Both backends call it at the same instruction, the player update's RET (0x8C3F1 or 0x8C401), with the camera
direction the input builder read at 0x85276, so an L3 trace and its xemu replay are comparable field by field
(:func:`differ`, :func:`compare`) and tick by tick (:func:`digest`, coordinate-free).

From the entity (its fields: the ``azurik-game-reference`` skill): the velocity +0x24, the state +0x94, the state
time +0x9C, the stored contact normal +0xB8 (the last contact's: the classifier 0x85920 writes it, and it holds
in the air), the flaps used +0xD8, the flap ceiling's latch peak_z +0x164 (z0 + h on the jump tick, in the input
position's frame, the body centre; a walk-off keeps the last jump's) and the fall reference +0x168 (the z a fall
counts from; -FLT_MAX while none counts); from its critter ``[entity+0x20]``: the body centre +0x15C (1 m over
the feet), the animation index +0x200 and HP +0x210/+0x214; from the player data ``pd = [critter+0x154]``
(RAM_RECIPES §1) the armor manager ``[pd+0xCC]``: its air gauge +0x24 and the equipped armor's level struct
``[armor_mgr+0x20]``, its Level +0x08 and Flaps +0x38 (Step TD.0: what the trick explorer keys its cells on and
the detectors read, so in the light read too).  With ``deep``: the element levels (the kit) and a hash of the
inventory's saved 0x1D4 bytes ``[pd+0xE0]`` past its day clock (the first word, which player-tick L3 doesn't
advance: with it the hash differed from xemu's on every tick, AZ-389), and a hash of the global latches (the
flags: the shared map ``[pd+0xE4]``, a tree whose nodes hold the name at +0x10 and a pointer to the 4-byte value
at +0x60, as the shared.sav writer 0x5E8A0 walks it).  ``deep`` costs about 40 reads, so the input search reads
without it.  Positions are private: print :func:`digest`, never an Obs.  The face a contact normal belongs to is
:mod:`devkit.sim.faces`'s lookup (:func:`contact`: the trick explorer's per-row face, Step TD.4; faces comes
with Step 4.13a).
"""

from __future__ import annotations

import hashlib
import math
import struct
from typing import Callable, NamedTuple

from azurkit.tools.randomizer.live import recipes

ENT_VEL, ENT_STATE, ENT_FLAPS_USED, ENT_CRITTER = 0x24, 0x94, 0xD8, 0x20
ENT_STATE_T, ENT_NORMAL, ENT_FALL_REF = 0x9C, 0xB8, 0x168   # f32 += dt a tick; 3 f32; f32 (RE_MOVEMENT.md)
ENT_PEAK_Z = 0x164   # f32: peak_z, written on the jump tick (0x8915A) and by the reset (0x84E16)
CR_PD, CR_ANIM = 0x154, 0x200       # [critter+0x154] = pd, the player data; the animation index (i32)
ARMOR_SLOT, ARMOR_GAUGE = 0x20, 0x24   # [armor_mgr+0x20] = the equipped armor's level struct; the air gauge (f32)
SLOT_LEVEL, SLOT_FLAPS = 0x08, 0x38    # the level struct's Level and Flaps (i32)
PD_SHARED = 0xE4                    # the global latches' map
NODE_LEFT, NODE_RIGHT, NODE_NAME, NODE_VALUE, NODE_SIZE = 0x08, 0x0C, 0x10, 0x60, 0x64
MAX_LATCHES = 4096                  # a longer walk is a corrupt map
CORE = ("pos", "state", "hp")       # what a proof's replay must match tick for tick (D170)


class Obs(NamedTuple):
    """The player at the update's RET.  ``cam`` is the camera direction (two f32) the input builder read, None
    when the tick didn't reach it; the armor's fields are None before the player data exists (or with no armor
    manager or slot), the deep ones also without ``deep``.  The fields after ``flags_sha12`` are Step TD.0's
    (``peak_z`` Step R1.29e's)."""
    pos: tuple[float, float, float]
    vel: tuple[float, float, float]
    state: int
    hp: int
    hp_max: int
    flaps_used: int
    cam: tuple[float, float] | None = None
    flaps: int | None = None
    kit: tuple[int, int, int, int] | None = None   # recipes.ELEMENTS' levels
    inv_sha12: str | None = None
    flags_sha12: str | None = None
    normal: tuple[float, float, float] | None = None   # entity+0xB8: the last contact's normal
    fall_ref: float | None = None   # entity+0x168: the z a fall counts from
    state_t: float | None = None    # entity+0x9C: the time in the state
    anim: int | None = None         # critter+0x200: the animation index
    gauge: float | None = None      # armor_mgr+0x24: the air gauge (1.0 full)
    armor_level: int | None = None  # the equipped slot's Level (its Flaps: ``flaps``)
    peak_z: float | None = None     # entity+0x164: the flap ceiling's latch (the ceiling is peak_z + h)

    @property
    def feet(self) -> tuple[float, float, float]:
        return self.pos[0], self.pos[1], self.pos[2] - recipes.LIFT

    @property
    def cam_yaw(self) -> float | None:
        """The camera's yaw (radians; yaw a looks along (-sin a, cos a))."""
        return None if self.cam is None else math.atan2(-self.cam[0], self.cam[1])


def _u32(b: bytes, off: int = 0) -> int:
    return struct.unpack_from("<I", b, off)[0]


def flags_sha12(read: Callable[[int, int], bytes], shared: int) -> str:
    """sha256[:12] of the global latches (name and value of each, by name) in the map at ``shared``."""
    head = _u32(read(shared, 4))
    todo, out = [_u32(read(head + 4, 4))], []
    while todo:
        n = todo.pop()
        if n in (0, head):
            continue
        if len(out) >= MAX_LATCHES:
            raise ValueError(f"the latch map at {shared:#x} has over {MAX_LATCHES} nodes: corrupt")
        node = read(n, NODE_SIZE)
        vp = _u32(node, NODE_VALUE)
        out.append((bytes(node[NODE_NAME:NODE_VALUE]).split(b"\0")[0], bytes(read(vp, 4)) if vp else b""))
        todo += [_u32(node, NODE_LEFT), _u32(node, NODE_RIGHT)]
    h = hashlib.sha256()
    for name, value in sorted(out):
        h.update(struct.pack("<I", len(name)) + name + value)
    return h.hexdigest()[:12]


def read(read: Callable[[int, int], bytes], entity: int, cam: bytes | None = None, *, deep: bool = True) -> Obs:
    """The :class:`Obs` of the player ``entity`` through ``read(va, n)``; ``cam`` the 8 bytes the input builder
    read at 0x85276."""
    e = read(entity, ENT_FALL_REF + 4)
    crit = _u32(e, ENT_CRITTER)
    c = read(crit + CR_PD, recipes.CR_HP + 8 - CR_PD)
    body = recipes.CR_BODY - CR_PD
    o = Obs(struct.unpack_from("<3f", c, body), struct.unpack_from("<3f", e, ENT_VEL), _u32(e, ENT_STATE),
            *struct.unpack_from("<2i", c, recipes.CR_HP - CR_PD), struct.unpack_from("<i", e, ENT_FLAPS_USED)[0],
            None if cam is None else struct.unpack("<2f", cam), normal=struct.unpack_from("<3f", e, ENT_NORMAL),
            fall_ref=struct.unpack_from("<f", e, ENT_FALL_REF)[0], peak_z=struct.unpack_from("<f", e, ENT_PEAK_Z)[0],
            state_t=struct.unpack_from("<f", e, ENT_STATE_T)[0],
            anim=struct.unpack_from("<i", c, CR_ANIM - CR_PD)[0])
    pd = _u32(c)
    if not pd:
        return o
    p = read(pd + recipes.PD_ARMOR, PD_SHARED + 4 - recipes.PD_ARMOR)
    am, inv, shared = (_u32(p, off - recipes.PD_ARMOR) for off in (recipes.PD_ARMOR, recipes.PD_INV, PD_SHARED))
    if am:
        a = read(am + ARMOR_SLOT, ARMOR_GAUGE + 4 - ARMOR_SLOT)
        o = o._replace(gauge=struct.unpack_from("<f", a, ARMOR_GAUGE - ARMOR_SLOT)[0])
        if slot := _u32(a):
            b = read(slot + SLOT_LEVEL, SLOT_FLAPS + 4 - SLOT_LEVEL)
            o = o._replace(armor_level=struct.unpack_from("<i", b)[0],
                           flaps=struct.unpack_from("<i", b, SLOT_FLAPS - SLOT_LEVEL)[0])
    if not deep:
        return o
    kit = sha = None
    if inv:
        b = bytes(read(inv, recipes.INV_SAVED))
        kit = tuple(struct.unpack_from("<i", b, recipes.INV_LEVEL[el])[0] for el in recipes.ELEMENTS)
        sha = hashlib.sha256(b[recipes.INV_CLOCK:]).hexdigest()[:12]
    return o._replace(kit=kit, inv_sha12=sha, flags_sha12=flags_sha12(read, shared) if shared else None)


NO_CONTACT = (0.0, 0.0, 1.0)        # the classifier's stored normal with no contact (0x85A34)
AIRBORNE = frozenset({2, 0x102})
SETTLED = frozenset({0, 6})          # standing, swimming
SLIDE = 3                            # the slide state: a slippery face, or one of 0.6 < nz <= 0.7071 (no friction)
FLAT_NZ = 0.998                      # a contact this flat is near-flat floor (the derive's floors.SLIP_FLAT_NZ)
REST_MPS = 0.05                      # a sliding body under this horizontal speed is at rest (the reach engine's
                                     # STUCK rest)


def contact(o: Obs, faces):
    """The face the observation's stored contact normal belongs to (``faces``: a level's
    :class:`devkit.sim.faces.Faces`, looked up at the body centre), or None: no normal read, or in the air with
    the classifier's no-contact normal (:data:`NO_CONTACT`; in the climb and the catch it holds the last contact's)."""
    if o.normal is None or (o.state in AIRBORNE and tuple(o.normal) == NO_CONTACT):
        return None
    return faces.face(o.pos, o.normal)


def settled(row) -> bool:
    """Whether a row's body (an L3 row: ``state`` and ``obs``) is settled: standing or swimming (:data:`SETTLED`),
    or at rest on near-flat ice (AZ-737).  On a flat slippery face a still body cycles 0, 3, 3 or stays in the slide
    state (L3 on e6's, w2's, w3's and town's ice: Step R1.39), so state 3 counts where the row's observation has
    the contact normal's z at least :data:`FLAT_NZ` and the horizontal speed under :data:`REST_MPS`; a body sliding
    on (0.6-0.8 m/s on ice of nz 0.998-0.9998) or held still on a slope does not.  A row with no observation is
    read by its state alone.  Every settled read uses this (``l3_search``, ``l3_certify``, ``l3_goal``, the reach
    engine)."""
    if row.state in SETTLED:
        return True
    o = getattr(row, "obs", None)
    return (row.state == SLIDE and o is not None and o.normal is not None and o.normal[2] >= FLAT_NZ
            and math.hypot(o.vel[0], o.vel[1]) < REST_MPS)


def digest(o: Obs, fields: tuple[str, ...] | None = None) -> str:
    """sha256[:12] of every field, or of ``fields`` (e.g. :data:`CORE`), floats by their f32 bits:
    coordinate-free, equal only when those fields are."""
    vals = o if fields is None else tuple(getattr(o, f) for f in fields)
    return hashlib.sha256(repr(tuple(struct.pack("<f", v) if isinstance(v, float) else v for v in _flat(vals)))
                          .encode()).hexdigest()[:12]


def _flat(vals):
    for v in vals:
        yield from (v if isinstance(v, tuple) else (v,))


def differ(a: Obs, b: Obs) -> list[str]:
    """The names of the fields that differ between two observations (floats compared exactly)."""
    return [f for f, x, y in zip(Obs._fields, a, b) if x != y]


JUDGED = Obs._fields[:Obs._fields.index("flags_sha12") + 1]
"""The fields :func:`compare`'s ``first_diff`` is judged on, which a pickup proof reads (``l3_certify.pickup_at``:
the first difference the inventory hash's alone): those before Step TD.0's, so the fields TD.0 added (an
animation the player tick doesn't write, say) change no verdict; ``fields_differ`` counts them too."""


def compare(want: list[Obs], got: list[Obs]) -> dict:
    """Two traces tick by tick (coordinate-free): per field, the ticks it differs on, and the first tick that
    differs in a :data:`JUDGED` field with those fields."""
    count: dict[str, int] = {}
    first = None
    for k, (a, b) in enumerate(zip(want, got)):
        if fs := differ(a, b):
            if first is None and (judged := [f for f in fs if f in JUDGED]):
                first = [k, judged]
            for f in fs:
                count[f] = count.get(f, 0) + 1
    return {"fields_differ": count, "first_diff": first}
