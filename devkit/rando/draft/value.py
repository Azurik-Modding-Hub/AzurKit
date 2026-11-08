"""The trick explorer's value ranker (Step TD.4, D253; the trick-discovery plan §3.4): per level and kit, what
reaching a place would add to the logic, from the level's derived file (ids only) and where each mined site lies.

A zone's value (:func:`zone_values`): :data:`W_LOCATION` for each location in it the logic doesn't reach at the
kit's air level (``min_air`` at the hardest tier none or above it), :data:`W_EXIT` for each exit anchored there with
no logic way in at that level (``coverage.exits``' ``least_air``), :data:`W_UNENTERED` when no logic edge enters it
and :data:`W_GATE` when a gate separates it.  A site's value is the sum over the zones whose logic floors lie within
:data:`NEAR_M` of its anchor points (:func:`near_zones`): a site is valued by where it may lead.  :func:`rank`
orders the queue by it and never filters it: the sites past ``cut`` are reported "not attempted" with their rank.
Ids and numbers only; the points stay in memory.
"""

from __future__ import annotations

import numpy as np

from azurkit.tools.randomizer.draft.geometry import RadiusIndex

W_LOCATION, W_EXIT, W_UNENTERED, W_GATE = 3.0, 2.0, 1.0, 1.0   # [proposal]
NEAR_M = 6.0             # [proposal] a site leads to the zones whose floors lie this near its points (m; in height too)
HARDEST = "frame_perfect"


def beyond(least: dict | None, air: int) -> bool:
    """Whether a ``least_air`` record (per tier) has no logic way at the kit's ``air`` level at the hardest tier."""
    v = (least or {}).get(HARDEST)
    return v is None or v > air


def zone_values(derived: dict, air: int) -> dict[str, float]:
    """Each zone's value at the kit's ``air`` level (the module docstring)."""
    val = {z["id"]: 0.0 for z in derived.get("zones", [])}
    for loc in derived.get("locations", []):
        if loc.get("zone") in val and beyond(loc.get("min_air"), air):
            val[loc["zone"]] += W_LOCATION
    exits = derived.get("coverage", {}).get("exits", {})
    for z in derived.get("zones", []):
        val[z["id"]] += W_EXIT * sum(beyond(exits.get(e, {}).get("least_air"), air)
                                     for e in z.get("anchors", {}).get("exit", ()))
    entered = {e["to"] for e in derived.get("edges", []) if e.get("logic") is not False and e["from"] != e["to"]}
    for zid in val:
        val[zid] += W_UNENTERED * (zid not in entered)
    for g in derived.get("gates", []):
        for group in g.get("separates_zones", ()):
            for zid in group:
                if zid in val:
                    val[zid] += W_GATE
    return val


def near_zones(reach, sites) -> dict[str, set[str]]:
    """Per site, the zones (``<level>.Z<n>``) whose logic floor samples lie within :data:`NEAR_M` of one of its
    anchor points, horizontally and in height."""
    lw, zo = reach.W["logic"], getattr(reach, "zone_of", None)
    out: dict[str, set[str]] = {s.id: set() for s in sites}
    js = np.nonzero(lw.reg_soft >= 0)[0]
    if zo is None or not len(js) or not sites:
        return out
    idx = RadiusIndex(np.c_[lw.x[js], lw.y[js]], NEAR_M)
    pts = np.concatenate([s.points for s in sites])
    owner = np.repeat(np.arange(len(sites)), [len(s.points) for s in sites])
    qi, pj, _ = idx.pairs(pts[:, :2])
    ok = np.abs(lw.z[js[pj]] - pts[qi, 2]) <= NEAR_M
    for q, v in zip(qi[ok].tolist(), js[pj[ok]].tolist()):
        out[sites[owner[q]].id].add(f"{reach.name}.Z{int(zo[int(lw.reg_soft[v])]):03d}")
    return out


def rank(sites, near: dict[str, set[str]], values: dict[str, float], cut: int | None = None) -> list[dict]:
    """The sites in queue order: by value (highest first), then id; each with its value and rank, and past ``cut``
    "not attempted"."""
    scored = sorted(((sum(values.get(z, 0.0) for z in near.get(s.id, ())), s.id) for s in sites),
                    key=lambda t: (-t[0], t[1]))
    return [{"id": sid, "value": round(v, 2), "rank": k + 1,
             **({"verdict": "not attempted"} if cut is not None and k >= cut else {})}
            for k, (v, sid) in enumerate(scored)]
