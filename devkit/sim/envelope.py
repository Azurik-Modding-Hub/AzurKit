"""The movement envelope's flights through the game's own code under :mod:`devkit.sim.l2` (Modkit's
``randomizer/draft/envelope.py`` section 3, Step 4.13a): what the envelope's ``[verified L2]`` numbers came from.

AzurKit's envelope (:mod:`azurkit.tools.randomizer.draft.envelope`) keeps the tiers and the contact laws; these
two producers need Unicorn, so they live here, dev only (the wheel never carries them).
"""

from __future__ import annotations

import math
import struct
from dataclasses import replace

from azurkit.tools.randomizer import physics
from azurkit.tools.randomizer.physics import f32


def l2_xbe(vanilla: bytes, m: physics.Movement) -> bytes:
    """``vanilla`` built with ``m``'s ``player_physics`` sliders (the XBE
    ones: the run speed is a config.xbr cell, which :func:`l2_flight` sets
    in the fake CritterData and the run-up)."""
    from devkit.sim.l2 import build_physics

    params = {name: getattr(m, field) for (pack, name), (field, base) in physics.SLIDERS.items()
              if pack == "player_physics" and base is None and getattr(m, field) != getattr(physics.VANILLA, field)}
    return build_physics(vanilla, **params)


def l2_flight(xbe: bytes, m: physics.Movement, rank: int, flap_ticks=(), run: bool = True,
              spring: float | None = None, stop: float = -20.0):
    """One flight through the game's jump_init, airborne tick, wing_flap
    and consume_fuel under L2 on ``xbe`` (:func:`l2_xbe`), with the move
    code replaced by free flight: from a run at ``m``'s run speed (or
    standing), wearing air shield ``rank`` with ``m``'s Flaps and a full
    gauge (rank 0: no armor), flaps pressed on ``flap_ticks``, a
    springboard launch of ``spring`` m (entity+0x68).  Returns (rows of
    (horizontal travel, feet height) per tick from the takeoff, whether
    each press flapped, the jump) until the feet fall below ``stop`` after
    the last press."""
    from devkit.sim.l2 import AIRBORNE_TICK, FALL_MOVE, STANDING, PlayerSim

    d = STANDING.direction
    v = m.run_speed if run else 0.0
    flaps = 0 if rank == 0 else m.flaps[rank - 1]
    p = replace(STANDING, velocity=(v * d[0], v * d[1], 0.0), walk_speed=m.run_speed, dt=1.0 / m.fps,
                armor_level=max(rank, 1), flaps=flaps, fuel=1.0 if flaps else 0.0,
                charged_jump_height=spring or 0.0)
    sim = PlayerSim(xbe, p)
    x0, y0, z0 = p.position
    jump = sim.jump()
    e, inp = sim.at["entity"], sim.at["input"]
    rows, pos, flapped, presses = [(0.0, 0.0)], list(p.position), [], set(flap_ticks)
    last = max(presses, default=0)
    for k in range(1, 4000):
        if k in presses:
            sim.set(buttons=0x04, y_latch=0)
            flapped.append(sim.flap().flapped)
            rows.append(rows[-1])
            continue
        sim.set(buttons=0x00)
        sim.call(AIRBORNE_TICK, regs={"edi": e}, args=(inp,), until=FALL_MOVE)
        vel = struct.unpack("<3f", sim.uc.mem_read(sim.reg("eax") + 0x1C, 12))
        pos = [f32(pos[i] + f32(vel[i] * p.dt)) for i in range(3)]
        sim.set(velocity=tuple(vel), position=tuple(pos))
        rows.append((math.hypot(pos[0] - x0, pos[1] - y0), pos[2] - z0))
        if k > last and pos[2] - z0 < stop and vel[2] < 0:
            break
    return rows, flapped, jump
