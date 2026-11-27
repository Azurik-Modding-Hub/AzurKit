"""The reach engine's slide launch (Step 4.83b; AZ-374 W): ``slidejump``, a launch family in a file of its own
(``macros.FAMILIES``: ``macros.controller`` is its one hook), keyed apart from the L3 core (``cache.SLIDE_FILES``), so
an edit here re-runs only the jobs that fly it.

A slide jump (:class:`Slide`): from a start on the floor above a slippery slope patch, the stick held along the
heading (down the slope) from the first tick, as R0's run: the body runs onto the slope and slides (entity+0x94 3 or
4, :data:`SLIDING`: ``player_slope_slide_tick`` 0x89A70 keeps 3 under 6 m/s, the stick's term added, and 4 over it);
once it slides and its feet have come ``back`` less the macro's ``lead`` metres along the heading from its start (the
takeoff column the derive's witness end names), Y, held ``macros.JUMP_HOLD`` ticks (the jump fires off any slippery
face along its normal, 0x8917F-0x89207: it rises h nz^2 and is kicked down the fall line); then the air as the
controller it is made of flies it (R0's flaps; an aim's landing control and flaps).  A body that leaves the ground
before its press made no launch of its own (``walked off``: the slide off the patch's end is the derive's modelled
slide); one still on the ground :data:`SLIDE_CAP` ticks in is ``stayed``.

The aims (:func:`slide_jobs`): one per derived flight off a patch (the probe class ``slope``, AZ-374 B: from a zone
holding a patch), from the reach model's best region edge of its zone pair with its witness ends (``w_slope``:
("off", slope column, landing sample)), a slide jump from the floor above the takeoff column (:func:`start`) at the
landing sample moved onto its region and floor face (``aim._inside``, ``Nodes.snap``), in its certificate's kit; the
job's ``from`` is that floor's zone (no body rests on a slope: the floor above it slides into it in logic), its
``stop`` the derived edge's to-zone at its air (``aim.hit``), ``slope`` the patch's zone and ``takeoff_nz`` the
certificate's.  A flight onto a patch (AZ-374 C) is no aim here: its body slides off the patch, so its witness is a
touch-down the hit rule doesn't read yet.  Positions stay in memory and the private cache.
"""

from __future__ import annotations

import functools

import numpy as np

from devkit.reach.engine.macros import JUMP_LEAD, Macro, _feet
from devkit.sim.inputs import heading_to

KIND = "slidejump"
SLIDING = frozenset({3, 4})      # entity+0x94: the slope states (0x89A70)
SLIDE_CAP = 160                  # [proposal] ticks on the ground a slide jump may take before its press (R0's run has
                                 # 40: a slide covers the derive's patch from its top at up to 9 m/s, AZ-374 §3)
UP_M = 2.0                       # [proposal] the floor above a takeoff column: this far up the fall line past the
                                 # patch's top at most
RUN_UP = (1.0, 0.5, 0.0)         # [the run's, ``macros.BACK_RUN``] the start this far further up on that floor first
STEP_M = 0.25                    # the grid those points are on
KICK = ((0.7071, 1.84), (0.8, 1.75), (0.9, 1.41), (0.95, 1.04), (1.0, 0.0))   # [AZ-374 §3's closed form, physics.py's
                                 # constants] the jump's kick down the fall line carries the body this far (m) by the
                                 # time it is back at its takeoff's height, by the face's nz: one aim presses so early
_CLASSES: dict = {}


class Slide:
    """The slide jump's ground half (the module docstring), mixed in before the controller it is made of."""

    def pad(self):
        rows = self.rows
        if self.jump_at is None and self.took is None and rows and rows[-1].state in SLIDING:
            f = _feet(rows[-1])
            if (f[0] - self.start[0]) * self.dx + (f[1] - self.start[1]) * self.dy >= self.back - self.m.lead:
                self.jump_at = len(rows)          # the base's pad holds Y from here (``macros.JUMP_HOLD`` ticks)
        return super().pad()

    def seen(self, pad, row) -> str | None:
        end = super().seen(pad, row)
        t = len(self.rows) - 1
        if end is None and self.took == t and self.jump_at is None:
            return "walked off"                   # off the ground before its press: no launch of its own
        if end == "stayed" and self.took is None and t < SLIDE_CAP:
            return None                           # the base's run cap: a slide takes longer
        return end


def controller(make):
    """The controller a ``slidejump`` launch runs under: :class:`Slide` mixed into ``make`` (``macros._Run``, or an
    aim's controller class, or a ``functools.partial`` of one)."""
    part = isinstance(make, functools.partial)
    base = make.func if part else make
    if (cls := _CLASSES.get(base)) is None:
        cls = _CLASSES[base] = type(f"Slide{base.__name__}", (Slide, base), {"__module__": __name__})
    return functools.partial(cls, *make.args, **make.keywords) if part else cls


def aims(kit: str, flaps: int, nz: float | None = None) -> tuple[Macro, ...]:
    """A slide jump's aims (``aim.aims``' set for a run jump): straight, curved left and right under the landing
    control, pressed at the takeoff column (lead 0), straight :data:`macros.JUMP_LEAD` short of it and, with the
    takeoff face's ``nz``, straight the jump's kick short of it (:data:`KICK`: so the kick carries the body back over
    the derive's takeoff); and the three held at the aim."""
    from devkit.reach.engine.aim import CURVE
    leads = (JUMP_LEAD,) + ((round(float(np.interp(nz, *zip(*KICK))), 2),) if nz is not None else ())
    out = tuple(Macro(KIND, kit, flaps, c, 0.0) for c in (0.0, CURVE, -CURVE))
    out += tuple(Macro(KIND, kit, flaps, 0.0, b) for b in dict.fromkeys(leads) if b > 0.0)
    return out + tuple(Macro(KIND, kit, flaps, c, 0.0, hold=True) for c in (0.0, CURVE, -CURVE))


def offs(derived: dict) -> list[tuple[int, dict]]:
    """The derived file's flights off a slope patch (AZ-374 B), with their index: its edges of the probe class
    ``slope`` (``probe``), kind jump or flap, from a zone holding a patch (a region with ``slope``)."""
    patched = {r["zone"] for r in derived.get("regions", ()) if r.get("slope")}
    return [(n, d) for n, d in enumerate(derived.get("edges", ())) if d.get("probe") == "slope"
            and d["kind"] in ("jump", "flap") and d["from"] in patched]


def _best(nodes) -> dict[tuple, dict]:
    """Per (from zone, to zone, kind), the reach model's best region edge off a patch with its witness ends
    (``w_slope`` "off": least ranks, then gap)."""
    R, best = nodes.R, {}
    for (a, b), es in R.E["logic"].items():
        za, zb = int(R.zone_of[a]), int(R.zone_of[b])
        for e in es:
            w = e.get("w_slope")
            if za == zb or not e.get("slope") or not w or w[0] != "off":
                continue
            k = (za, zb, e["kind"])
            if k not in best or (sum(e["ranks"]), e.get("gap", 0.0)) < (sum(best[k]["ranks"]), best[k].get("gap", 0.0)):
                best[k] = e
    return best


def start(nodes, k: int) -> tuple[tuple, list[list[float]], int] | None:
    """The floor above slope column ``k``: up its fall line (``Slopes.follow``) to the patch's top, then on up to
    :data:`UP_M` (the :data:`STEP_M` grid), the first point over a floor face on a walkable region within the walking
    step of the face; (that point, the starts :data:`RUN_UP` further up on the same region's faces, farthest first,
    and its region), or None for none."""
    S = nodes.slopes
    x, y, z, kt, _ = S.follow(k, down=False)
    ux, uy = -float(S.fx[kt]), -float(S.fy[kt])
    climb = nodes.walk.p["climb"]
    for i in range(int(UP_M / STEP_M) + 1):
        p = (x + i * STEP_M * ux, y + i * STEP_M * uy)
        fz = nodes.faces.floor_z(p[0], p[1], z, climb + STEP_M)
        if fz is None or (r := nodes.region_at((p[0], p[1], fz))) is None:
            continue
        out = []
        for b in RUN_UP:
            q = (p[0] + b * ux, p[1] + b * uy)
            qz = nodes.faces.floor_z(q[0], q[1], fz, climb)
            if qz is not None and nodes.region_at((q[0], q[1], qz)) == r:
                out.append([q[0], q[1], qz])
        return (p[0], p[1], fz), out or [[p[0], p[1], fz]], r
    return None


def slide_jobs(nodes, derived: dict, only=None, prefix: str = "l", more_of=()) -> list[dict]:
    """The slide jumps at the derived flights off a slope patch (the module docstring; :func:`offs`, with ``only``
    those whose ``from>to:kind:confidence`` it holds): ids ``<prefix><derived edge index>``; an edge ``more_of``
    holds asks for every pass (``more``).  None on a model with no slope patches (a derive before AZ-374)."""
    from devkit.rando.draft.author import dnf
    from devkit.reach.engine.aim import FLAPS_OF_RANK, _inside
    from azurkit.tools.randomizer.planner.proofs import zoning
    S, out = getattr(nodes, "slopes", None), []
    if S is None:
        return out
    lw, zoned = nodes.logic, zoning(derived)[:12]
    zone = {f"{nodes.level}.Z{int(z):03d}": int(z) for z in np.unique(nodes.R.zone_of)}
    best = _best(nodes)
    for n, d in offs(derived):
        edge = f"{d['from']}>{d['to']}:{d['kind']}:{d['confidence']}"
        if (only is not None and edge not in only) or d["from"] not in zone or d["to"] not in zone:
            continue
        if (e := best.get((zone[d["from"]], zone[d["to"]], d["kind"]))) is None:
            continue
        _, k, j = e["w_slope"]
        cx, cy = nodes.lv.cxy(S.sc[k])
        col = (float(cx), float(cy), float(S.sz[k]))
        if (up := start(nodes, int(k))) is None:
            continue
        top, starts, region = up
        moved = _inside(nodes, col, int(j))
        dst = nodes.snap(moved, d["to"]) or moved
        cert = next((c for c in e.get("certs") or () if c is not None and c.rank < 4), None)
        nz = getattr(cert, "takeoff_nz", None)
        rank = cert.rank if cert is not None else min(e["ranks"])
        flaps = 0 if rank == 0 else cert.flaps if cert is not None and cert.flaps is not None else FLAPS_OF_RANK[rank]
        kit = "k0" if rank == 0 else "air3"
        airs = [max((a[1] for a in term), default=0) for term in dnf(d.get("requires", "true"))
                if all(a[0] == "air" for a in term)]
        home = nodes.zone_at(top, False, False)
        stop = {"air": min(airs), "to": d["to"], "zoning": zoned} if airs and home is not None else None
        h = heading_to(top, col)
        out.append({"takeoff": -1, "sample": -1, "region": region, "takeoff_feet": list(col), "heading": h,
                    "starts": {"run": starts, "stand": starts}, "cells": list(nodes.cells([top])[0]),
                    "macros": [list(m) for m in aims(kit, flaps, nz)], "id": f"{prefix}{n}", "edge": edge,
                    "target": list(dst), "aim": list(moved), "stop": stop, "target_cells": nodes.cells([dst])[0][:1],
                    "cert": [KIND, kit, flaps], "from": home, "slope": d["from"], "takeoff_nz": nz,
                    **({"more": True} if edge in more_of else {})})
    return out

