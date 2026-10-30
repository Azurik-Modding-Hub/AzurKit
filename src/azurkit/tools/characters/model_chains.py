"""A body's bone chains that X41's springs could drive (Step 2.169a, D536:
``azurik-mod model chains``): its hair and its cloth (a loincloth's front
and back panels, booblord's sash and tabard, a strap), each a run of
bones a recipe's ``jiggle.springs`` rows can swing link by link (D485:
the body's own bones, their skin and children as they are).

:func:`chains` finds them by name (:data:`KINDS`: a bone whose name
names hair or cloth, its parent's doesn't, or its parent holds more
than one such child) and follows each while the bone has exactly one
such child, so a hub with several locks (balthazar_airship's
``hair_base_joint``) is a chain of its own and each lock another under
it.  A tail or tentacle isn't listed: its critter's clips key it.  Per
link: its length (to its child, else the reach of its vertices along
the chain), its mass (the LOD-0 vertices it weighs at :data:`HEAVY` or
more, and the sum of its weights over every vertex); per chain the clips
(every one under the body, a build's ``g4/`` and ``v/`` ones too) that
key its first link, and the clips that don't (each needs the link's hang
keyed); and
the rows a recipe would need: one per link up to the last that weighs a
vertex (the end node after it is the tip, and a chain that weighs none
has nothing to swing), each with the starting spring of its kind
(:data:`STARTS`, the design's [inferred] values eased from root to tip,
to tune with ``model jiggle --set``) and a travel of the link's length
x tan(angle) across it.  A hub gets no row: the design leaves its mass
to its parent, and its locks start chains of their own.  A link with
one child keeps ``centre`` "auto" (X41 takes the child's bind origin,
the link's tip); any other gets its tip, so its swing has an arm: its
vertices' farthest reach along the chain (along the link above it; a
lone link's toward its mass), or where none reaches past its origin
(female_2's ``hair_3``) 0.8 of the link above it past it, the arm D505
tuned on booblord's hair.  A cloth row carries a wall (Step 2.169b): its
link's bind -up, the panel's face toward her once the clip hangs it, 5 mm
off the clip's pose.  X41's travel is an ellipsoid in the model's
bind axes, and at ``rot_share`` 1 the part of the offset along the link
stays a move, so a link along a model axis (a level panel) can't
stretch but a slanted one can: each row's link gives ``stretch``, the
travel's reach along it.  Lengths are model units (metres at a drawn
scale of 1).  Plain floats, no numpy; nothing here prints a byte.
"""

from __future__ import annotations

import math
import re

from azurkit.tools.characters import body_codec, jiggle_rt
from azurkit.tools.characters.characters import read_body
from azurkit.tools.characters.retarget import read_clip
from azurkit.core.xbr.nodes import named_resources, parse_toc

KINDS = {"hair": re.compile(r"hair|braid|ponytail", re.I),
         "cloth": re.compile(r"loincloth|sash|tabard|cape|skirt|strap", re.I)}
"""A chain's kind by its bones' names."""
HEAVY = 0.25
"""The weight at which a vertex counts as a link's (the design's chainscan)."""
STARTS = {
    "cloth": {"freq": (2.4, 1.6), "damping": (0.30, 0.40), "angle": (8.0, 14.0),
              "spring": {"gain": 1.0, "gravity": 0.0, "accel": 4.0, "give": 0.04, "pace": 2.0, "rot_share": 1.0,
                         "pivot": "origin", "swim": [0.3, 2.0], "wall": {"axis": [0.0, 0.0, -1.0], "stop": 0.005}}},
    "hair": {"freq": (2.2, 1.8), "damping": (0.22, 0.22), "angle": (15.0, 15.0),
             "spring": {"gain": 1.0, "gravity": 0.0, "accel": 3.0, "give": 0.04, "pace": 2.0, "rot_share": 1.0,
                        "pivot": "origin"}},
}
"""Each kind's starting spring (D536's design, its "starting params"
[inferred]): freq (Hz), damping and swing angle (degrees) at the root and
the tip, eased between them link by link; the rest as every link's
(no gravity: the clip's hang is the weight; one probe; a cloth link's
wall, Step 2.169b)."""

Vec = tuple[float, float, float]


def _kind(name: str) -> str | None:
    return next((k for k, rx in KINDS.items() if rx.search(name)), None)


def _role(name: str) -> str:
    role = re.sub(r"[^a-z0-9_]", "_", name.lower())
    return role if role[:1].isalpha() else f"b{role}"


def _unit(v: Vec) -> tuple[Vec, float]:
    n = math.sqrt(sum(c * c for c in v))
    return (tuple(c / n for c in v) if n > 0.0 else (0.0, 0.0, 0.0)), n


def _r(x: float, nd: int = 4) -> float:
    return round(x, nd) + 0.0


def _masses(asset: body_codec.BodyAsset) -> list[dict]:
    """Per bone, over LOD 0: the vertices it weighs at :data:`HEAVY` or
    more (their positions), the sum of its weights and its weighted
    centroid's sum."""
    out = [{"heavy": [], "weight": 0.0, "at": [0.0, 0.0, 0.0]} for _ in asset.bones]
    for g in (asset.lods[0].groups if asset.lods else ()):
        for v in g.vertices:
            for b, w in v.skin(g.palette).items():
                if 0 <= b < len(out):
                    m = out[b]
                    m["weight"] += w
                    for i in range(3):
                        m["at"][i] += w * v.position[i]
                    if w >= HEAVY:
                        m["heavy"].append(v.position)
    return out


def _keyed(characters_xbr: bytes, body: str) -> dict[str, set[int]]:
    """Each clip under ``characters/<body>/``: the bones it keys."""
    toc, prefix = parse_toc(characters_xbr), f"characters/{body}/".casefold()
    out = {}
    for i, name in named_resources(characters_xbr).items():
        rest = name[len(prefix):]
        if name.casefold().startswith(prefix) and toc[i].tag == "banm":
            out[rest] = {tr.target for tr in read_clip(characters_xbr, toc[i].file_offset).bones}
    return dict(sorted(out.items()))


def _ease(pair: tuple[float, float], k: int, n: int) -> float:
    return pair[0] if n < 2 else pair[0] + (pair[1] - pair[0]) * k / (n - 1)


def chains(characters_xbr: bytes, body: str) -> dict:
    """The report (module docstring) on the body ``characters/<body>`` as a
    JSON-able dict: ``body``, ``bones``, ``clips``, ``x41_rows`` (the rows
    X41 holds), ``rows`` (all the chains need) and ``chains``, each
    ``kind``, ``root``, ``parent``, ``links`` (``bone``, ``length``, ``to``:
    its child, "vertices" or "arm", ``vertices``, ``weight``, ``stretch``: how far
    its row's travel lets it stretch, None with no row), ``tip`` (the end
    node, or None), ``hub`` (the locks under its last link when it is a
    hub, else 0), ``length``, ``vertices``, ``weight``, ``keyed`` (the
    clips keying its first link), ``unkeyed`` (the clips that don't) and
    ``rows`` (recipe ``jiggle.springs`` rows).  :class:`ValueError` when
    there is no such body or it doesn't parse."""
    asset = body_codec.read_asset(characters_xbr, body)
    info = read_body(characters_xbr, asset.name)
    names = asset.bone_names
    parents = [b.parent for b in asset.bones]
    origin = [p for _, p in info.bones]
    kind = [_kind(n) for n in names]
    kids = [[c for c, p in enumerate(parents) if p == k and kind[c]] for k in range(len(names))]
    children = [sum(1 for p in parents if p == k) for k in range(len(names))]
    masses = _masses(asset)
    keyed = _keyed(characters_xbr, asset.name)
    out: dict = {"body": asset.name, "bones": len(names), "clips": len(keyed), "x41_rows": jiggle_rt.MAX_ROWS,
                 "chains": []}
    for root in range(len(names)):
        p = parents[root]
        if not kind[root] or (0 <= p < len(names) and kind[p] and len(kids[p]) == 1):
            continue
        run = [root]
        while len(kids[run[-1]]) == 1:
            run.append(kids[run[-1]][0])
        hub = len(kids[run[-1]]) if len(kids[run[-1]]) > 1 else 0
        n_rows = 1 + max((j for j, k in enumerate(run) if masses[k]["heavy"] and len(kids[k]) < 2), default=-1)
        tip = run[n_rows] if 0 < n_rows < len(run) else None
        start = STARTS[kind[root]]
        links, rows, length = [], [], 0.0
        for j, k in enumerate(run[:n_rows] or run):
            m, above = masses[k], length
            if len(kids[k]) == 1:   # to its child: the tip X41's "auto" takes when it is the bone's one child
                u, length = _unit(tuple(a - b for a, b in zip(origin[kids[k][0]], origin[k])))
                to = names[kids[k][0]]
                centre = None if children[k] == 1 else [_r(c) for c in origin[kids[k][0]]]
            else:                   # an end or a hub: its vertices' reach along the chain (a lone link: its mass)
                u, mass_at = (_unit(tuple(a - b for a, b in zip(origin[k], origin[parents[k]]))) if j else
                              _unit(tuple(a / m["weight"] - b for a, b in zip(m["at"], origin[k]))) if m["weight"] else
                              ((0.0, 0.0, 0.0), 0.0))
                length = max((sum((a - b) * c for a, b, c in zip(v, origin[k], u)) for v in m["heavy"]), default=0.0)
                to = "vertices"
                if length <= 0.0:   # none reaches past its origin: D505's arm (0.8 of the link above), else its mass
                    to, length = "arm", 0.8 * above if j else mass_at
                centre = [_r(o + c * length) for o, c in zip(origin[k], u)]
            link = {"bone": names[k], "length": _r(length), "to": to, "vertices": len(m["heavy"]),
                    "weight": _r(m["weight"], 2), "stretch": None}
            links.append(link)
            if j >= n_rows:
                continue
            across = length * math.tan(math.radians(_ease(start["angle"], j, n_rows)))
            spring = {"freq": _r(_ease(start["freq"], j, n_rows), 3),
                      "damping": _r(_ease(start["damping"], j, n_rows), 3),
                      "travel": [_r(across * math.sqrt(max(0.0, 1.0 - c * c))) for c in u]} | start["spring"]
            if centre is not None:
                spring["centre"] = centre
            jiggle_rt.parse_spring(f"{names[k]}'s row", spring)   # a row printed is a row a recipe takes
            # X41's travel is per bind axis and, at rot_share 1, the offset along the link stays a move: its
            # ellipsoid's reach along a slanted link is how far the link can stretch
            link["stretch"] = _r(math.sqrt(sum((t * c) ** 2 for t, c in zip(spring["travel"], u))))
            rows.append({"role": _role(names[k]), "bone": names[k], "parent": names[parents[k]], "spring": spring})
        out["chains"].append({
            "kind": kind[root], "root": names[root], "parent": names[p] if 0 <= p < len(names) else None,
            "links": links, "tip": names[tip] if tip is not None else None, "hub": hub,
            "length": _r(sum(li["length"] for li in links)), "vertices": sum(li["vertices"] for li in links),
            "weight": _r(sum(li["weight"] for li in links), 2),
            "keyed": sum(1 for bones in keyed.values() if root in bones),
            "unkeyed": [c for c, bones in keyed.items() if root not in bones], "rows": rows})
    out["rows"] = sum(len(c["rows"]) for c in out["chains"])
    return out


def _n(n: int, what: str) -> str:
    return f"{n} {what}{'' if n == 1 else 's'}"


def lines(report: dict) -> list[str]:
    """The report as text: each chain and its links, then the rows as
    recipe JSON, one a line."""
    import json

    cs = report["chains"]
    by = ", ".join(f"{sum(1 for c in cs if c['kind'] == k)} {k}" for k in KINDS if any(c["kind"] == k for c in cs))
    out = [f"{report['body']}: {report['bones']} bones, {report['clips']} clips; "
           + (f"{_n(len(cs), 'chain')} ({by}) X41's springs could drive, {_n(report['rows'], 'spring row')} "
              f"(X41 holds {report['x41_rows']})" if cs else "no hair or cloth chain")]
    for c in cs:
        tip = f" to {c['tip']}" if c["tip"] else ""
        unkeyed = (f" (not by {', '.join(c['unkeyed'][:6])}{', ...' if len(c['unkeyed']) > 6 else ''}: "
                   "their hang must be keyed)" if c["keyed"] and c["unkeyed"] else "")
        out.append(f"{c['kind']} {c['root']} under {c['parent']}: {_n(len(c['links']), 'link')}{tip}, "
                   f"{c['length']:.3f} long, "
                   f"{c['vertices']} vertices (weight {c['weight']:.1f}), its first link keyed by {c['keyed']} of "
                   f"{report['clips']} clips{unkeyed}")
        for li in c["links"]:
            to = {"vertices": "its vertices' reach",
                  "arm": "an arm (no vertex reaches past its origin)"}.get(li["to"], li["to"])
            stretch = (f", its travel lets it stretch {li['stretch'] * 1000:.1f} mm (a slanted link)"
                       if li["stretch"] and li["stretch"] >= 0.001 else "")
            out.append(f"  {li['bone']}: {li['length']:.3f} to {to}, {li['vertices']} vertices "
                       f"(weight {li['weight']:.1f}){stretch}")
        if c["hub"]:
            out.append(f"  a hub of {c['hub']} locks, each a chain of its own: no row (its mass rides its parent)")
        elif not c["rows"]:
            out.append(f"  no link weighs a vertex at {HEAVY} or more: nothing for a spring to swing")
    rows = [r for c in cs for r in c["rows"]]
    if rows:
        out.append("jiggle.springs rows (starting values to tune with model jiggle --set):")
        out += [f"  {json.dumps(r)}," for r in rows]
    if report["rows"] > report["x41_rows"]:
        out.append(f"{report['rows']} rows are past the {report['x41_rows']} X41 holds: a recipe takes some of them")
    return out


__all__ = ["HEAVY", "KINDS", "STARTS", "chains", "lines"]
