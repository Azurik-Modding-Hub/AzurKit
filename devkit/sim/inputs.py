"""The pad's geometry: what a real left stick gives for a world heading under a camera, and the game's heading
convention (Steps X.4, X.7).  Pure math, radians throughout; nothing here knows the randomizer or Unicorn.

The game's heading ``a`` faces ``(-sin a, cos a)``; the input builder's heading is the camera yaw plus the stick's
angle ``atan2(-x, y)`` (0x85276-0x85291), and the walk speed is 7.0 m/s times the stick's magnitude [verified xemu
x4].  A real pad's raw axes have a dead zone and a round gate, so the largest magnitude along a diagonal is about
0.76 and along an axis 1.0 (:func:`gate_max`); a heading within :data:`SNAP_DEG` of an axis takes the axis.  The
camera turns toward a heading at most :data:`CAM_RATE` a tick under the right stick [xemu X.5; X.4: 3.3 deg].
"""

from __future__ import annotations

import math

DEAD_RAW, RAW_SCALE, GATE_RAW = 12000.0, 4.815332e-5, 32767.0   # [verified xemu x4] the raw axis dead zone, scale, gate
SNAP_DEG = 5.0                           # [proposal] a heading this near a stick axis takes the axis: the other axis's
                                         # sliver would cost that axis's whole dead zone inside the gate
CAM_RATE = math.radians(3.33)            # the camera's turn a tick under the right stick


def wrap(a: float) -> float:
    """``a`` wrapped into (-pi, pi]."""
    return (a + math.pi) % (2 * math.pi) - math.pi


def heading_to(p, q) -> float:
    """The game heading from ``p`` to ``q`` (x, y, ...): it faces (-sin h, cos h)."""
    return math.atan2(-(q[0] - p[0]), q[1] - p[1])


def camera(cam: float, heading: float | None) -> float:
    """The camera yaw a tick later, turned toward ``heading`` by at most :data:`CAM_RATE` (``None``: unmoved)."""
    if heading is None:
        return cam
    d = wrap(heading - cam)
    return cam + max(-CAM_RATE, min(CAM_RATE, d))


def gate_max(cx: float, cy: float) -> float:
    """The largest stick magnitude a real pad gives along the unit stick direction (cx, cy): each axis needs
    |c| m / RAW_SCALE + DEAD_RAW raw units, and the raw pair stays inside the round gate."""
    a = [abs(c) / RAW_SCALE for c in (cx, cy) if abs(c) > 1e-9]
    if not a:
        return 0.0
    s1, s2, k = sum(a), sum(x * x for x in a), len(a)
    disc = (DEAD_RAW * s1) ** 2 - s2 * (k * DEAD_RAW ** 2 - GATE_RAW ** 2)
    return min(1.0, (math.sqrt(max(disc, 0.0)) - DEAD_RAW * s1) / s2)


def stick(heading: float | None, cam: float, mag: float = 1.0) -> tuple[float, float]:
    """The left stick (x right, y up: ControllerState's normalised values) that moves the player along world
    heading ``heading`` (radians) under camera yaw ``cam``, at magnitude ``mag`` or the most the round gate allows
    that way; within :data:`SNAP_DEG` of an axis it lies on the axis.  ``heading`` None: the stick at rest."""
    if heading is None:
        return 0.0, 0.0
    d = math.degrees(wrap(heading - cam))
    q = round(d / 90.0) * 90.0
    a = math.radians(q if abs(d - q) <= SNAP_DEG else d)
    cx, cy = -math.sin(a), math.cos(a)
    cx, cy = (0.0 if abs(cx) < 1e-9 else cx), (0.0 if abs(cy) < 1e-9 else cy)
    m = min(max(mag, 0.0), gate_max(cx, cy))
    return cx * m, cy * m
