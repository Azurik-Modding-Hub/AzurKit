"""A barrier crossed in simulator Level 3's whole steps (Step R1.29e): ``xemu_chain.py``'s ``Chain.staff``
recipe (r113's, closed loop) as a deterministic controller on an L3 simulator, so a douse can sit in a searched
string between two searched legs and xemu replays it as it is (D170).

The recipe: face the barrier's shape (the stick toward its centre at :data:`FACE_MAG` for :data:`FACE_TICKS`
ticks), cast the staff's elements (LT held from tick 14, each element's button (:data:`ELEM_BTN`) for a tick from
tick 16, three ticks apart, LT released after the last), then walk toward the shape's mirror point (through the
centre from where the walk starts), A held for 4 ticks every :data:`THROUGH_EVERY` ticks, until the feet stand in
the crossing's to-node for :data:`THROUGH_IN` ticks, at most :data:`THROUGH_MAX` ticks of walking.  The open-loop
recipe (three attacks, then a fixed walk) never got through R1.16's FireWall_03; attacking on the way did, in 3 of
3 variants (``Chain.staff``).  Each tick's pad is decided from the row before it, so the same start gives the same
pads: :func:`douse` returns them (``l3_search.segments`` makes them the replayer's JSON).  The camera turns toward
the heading at most ``inputs.CAM_RATE`` a tick and the stick is a real pad's (:func:`devkit.sim.inputs.stick`),
as in a searched string.  Whether a barrier reacts is the game's own code: only whole steps run its node graph.
Positions stay in memory.  Dev tooling (Unicorn is a dev dependency).
"""

from __future__ import annotations

import types
from dataclasses import dataclass, field
from typing import Callable

from devkit.sim.inputs import camera, heading_to, stick
from devkit.sim.l3 import Pad

ELEM_BTN = {"earth": "a", "air": "y", "fire": "b", "water": "x"}   # LT + this adds the element (xemu_minigames.PICK)
THROUGH_MAX, THROUGH_IN, THROUGH_EVERY = 300, 8, 24   # the walk's most ticks, the ticks in the to-node that end it, an
                                                      # attack every these ticks on the way (``xemu_chain`` reads them)
FACE_TICKS, FACE_MAG = 12, 0.15      # the turn toward the shape: these ticks at this stick (the chain's)
ATTACK_HOLD = 4                      # A held this many ticks for an attack (the chain's down at 0, up at 4)
LT_DOWN, CAST_AT, CAST_GAP = 14, 16, 3   # LT down; the first element's button; the ticks between buttons


@dataclass
class Douse:
    """A douse's pads (one a tick), its rows, whether the feet ended in the to-node (``passed``), and its counts."""
    pads: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    passed: bool = False
    attacks: int = 0
    cam: float = 0.0          # the camera yaw after its last pad

    def summary(self) -> dict:
        return {"passed": self.passed, "ticks": len(self.pads), "attacks": self.attacks}


def schedule(elements) -> tuple[list[str], int, int]:
    """(the elements' buttons, the tick LT is released, the walk's first tick) for casting ``elements``."""
    buttons = [ELEM_BTN[e] for e in elements]
    lt_up = CAST_AT + 2 + CAST_GAP * len(buttons)      # 21 for one element, as the chain's variants
    return buttons, lt_up, lt_up + 4


def in_the_way(cost: Callable[[object], float], centre, pos) -> bool:
    """Whether a barrier (its shape's centre ``centre``) stands between a body centre at ``pos`` and the to-node:
    crossing to its mirror point through the centre lowers ``cost`` (the to-node's cost to go of a standing row,
    ``l3_goal.RouteGoal.cost``).  A level edge's ``through`` names a barrier its derived zone path touches, which
    the walk may not cross (R1.16: w2_z034 > w2_z011 lists FireWall_02 28 m behind the body); ``Chain.staff`` and
    ``l3_certify``'s douse then cross nothing."""
    row = lambda q: types.SimpleNamespace(pos=tuple(q), state=0, hp=200, zone=None, obs=None)   # noqa: E731
    return bool(cost(row((2 * centre[0] - pos[0], 2 * centre[1] - pos[1], pos[2]))) < cost(row(pos)))   # no numpy bool


def douse(sim, row, centre, elements, inside: Callable[[object], bool], cam: float) -> Douse:
    """Cross a barrier from ``row`` (the row now: its ``pos``, the body centre): ``centre`` its shape's centre (x, y,
    z), ``elements`` the staff's ("water", ...), ``inside(row)`` whether the feet stand in the crossing's to-node,
    ``cam`` the camera yaw now; ``sim`` steps one :class:`~devkit.sim.l3.Pad` a tick (whole steps: the
    barrier's graph runs).  Ends after :data:`THROUGH_IN` ticks in the to-node or :data:`THROUGH_MAX` of walking."""
    buttons, lt_up, at = schedule(elements)
    out, far, here, attack = Douse(cam=cam), None, 0, False
    for k in range(1, at + THROUGH_MAX + 1):
        feet = (row.pos[0], row.pos[1], row.pos[2] - 1.0)
        held = {"lt"} if buttons and LT_DOWN <= k < lt_up else set()
        held |= {b for j, b in enumerate(buttons) if k == CAST_AT + CAST_GAP * j}
        if k <= FACE_TICKS:
            heading, mag = heading_to(feet, centre), FACE_MAG
        elif k < at:
            heading, mag = None, 0.0
        else:
            if far is None:
                far = (2 * centre[0] - feet[0], 2 * centre[1] - feet[1], centre[2])
            here = here + 1 if inside(row) else 0
            if here >= THROUGH_IN:
                break
            heading, mag = heading_to(feet, far), 1.0
            j = (k - at) % THROUGH_EVERY
            if j == 0 and not here:
                attack, out.attacks = True, out.attacks + 1
            elif j == ATTACK_HOLD:
                attack = False
            held |= {"a"} if attack else set()
        out.cam = camera(out.cam, heading)
        p = Pad(stick(heading, out.cam, mag), frozenset(held), out.cam)
        row = sim.step(p)
        out.pads.append(p)
        out.rows.append(row)
    out.passed = here >= THROUGH_IN or inside(row)
    return out
