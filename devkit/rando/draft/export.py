"""The derived data: reach's export of one level, its stamp and its checks.

Step R1.3c (reach v6's ``build_doc`` and ``export_check.py``, ported as a
model): :func:`build_doc` turns a finished :class:`~.reach.Reach` into
the document ``azurik-mod rando derive`` commits as
``src/azurkit/tools/randomizer/data/derived/<level>.json.gz``
(``docs/RANDOMIZER_DB.md`` §16, format ``azurik-rando-derived/1``):
the zones (the proposed nodes), the zone edges with their §5.1
requirement and options (:func:`tiers_of` gives each movement tier's), the gates with what they separate and
their bypass analysis, the held generated skips, the events reach sets,
the anchors, every pool location's zone and requirement, and the coverage
ladder.  It holds ids, names, counts, areas, relative heights and
distances, never a coordinate (RANDOMIZER_PLAN §4.4).

:func:`stamp` is the sha256 over :data:`DERIVE_VERSION`, the draft
tables, the level's generated file and :func:`derive_inputs`, the only
other data reach reads: a committed file whose stamp differs is stale.
:func:`check_doc` reads a
document as a consumer would (export_check): it re-derives the coverage,
min_air, flap and exit tables from the zone graph alone, checks the
grammar, every atom and every skip, and the barrier guarantee, and that
no number could be a coordinate.  Stdlib only, but
:func:`build_doc` (numpy arrays of a Reach).
"""

from __future__ import annotations

import collections
import gzip
import hashlib
import io
import json
import re
import tomllib
from pathlib import Path

import azurkit.tools.randomizer.draft as _src_draft
from azurkit.tools.randomizer.planner.loader import DATA_DIR, FORMATS

FORMAT = FORMATS["derived"]
GENERATOR = "azurik-mod rando derive"
DRAFT = Path(__file__).resolve().parent
# the draft tables' folders: this one (blocker_families.toml) and the shipped draft's (tiers.toml)
DRAFTS = (DRAFT, Path(_src_draft.__file__).resolve().parent)
DATA = DATA_DIR
DERIVED = DATA / "derived"
TIERS = ("safe", "standard", "hard", "frame_perfect")
LIST_SECTIONS = ("confirmed_skips", "doors", "edges", "events", "gates", "hand_skips", "locations", "objects", "regions",
                 "rigs", "skips", "zones")   # one entry per line
# The derive's logic version (Step R1.3d): bump it with any change to the derive's code (draft/*.py, levels.py,
# xbr/collision.py, nodes.py, tern.py, toc_scan.py) that changes a derived file.  The stamp holds it instead of
# the code's hash, so an edit that changes no derived file (Step RG.4c's nodes.py) leaves every stamp fresh;
# a forgotten bump is caught by `rando derive airship --check` (tests/test_reach_model.py), which then finds
# the file changed under an unchanged stamp.
DERIVE_VERSION = 7       # 2: Step R1.3d's smaller file (no edge tiers, skip_ids, support or trick; gzip);
                         # 3: Step R1.11c's leaking gate direction is not separated;
                         # 4: Step R1.2b's tiers as margins over the physics envelope, flight certificates;
                         # 5: Step X.16's inherit mode 2, lifting rigs, erosion by the face, the walk-off slack and
                         #    slippery slopes as slides;
                         # 6: Step R1.30's generated bskip skip rates a safe pass standard (D259);
                         # 7: Step R1.24's batch: R1.24a's sloped walk-off lips, standing jumps from ice and the
                         #    roof's ends; R1.24b's water as each volume's own interval (AZ-356) and the falls out of it


def derive_inputs(level: str, tricks: dict, hand: dict, generated: dict) -> dict:
    """What a level's derive reads beyond its generated file and the draft
    tables (Step R1.32): ``tricks.toml``'s ``[[skip]]`` entries of the
    level, its level file's ``node``, ``button`` and ``barrier`` arrays,
    and every generated file's exits into it (they give its arrivals).
    Reach reads these only through this function and :func:`stamp`
    hashes them, so an edit to anything else (another level's skip, a
    ``[[skip_rule]]``, a level file's edges or locations) leaves the stamp
    fresh, and the derive can't read an input the stamp misses."""
    return {"skip": [s for s in tricks.get("skip", []) if s.get("level") == level],
            "level": {k: hand.get(k, []) for k in ("node", "button", "barrier")},
            "exits_into": [[lvl, e] for lvl, doc in sorted(generated.items()) for e in doc.get("exits", [])
                           if e.get("dest_level") == level]}


def stamp(level: str, data: Path = DATA, draft: Path | tuple[Path, ...] = DRAFTS) -> str:
    """The derive stamp of a level: the sha256 of :data:`DERIVE_VERSION`,
    the (path, sha256) lines of the draft tables (``draft/*.toml``: the
    tiers among them) and of its generated file, and the sha256 of its
    :func:`derive_inputs` as canonical JSON.  The ISO's bytes need no line:
    the identity gate admits only vanilla, and the generated file names its
    ``.xbr``'s sha256."""
    def toml(p):
        try:
            return tomllib.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
        except tomllib.TOMLDecodeError as e:
            raise ValueError(f"{p}: {e}") from e

    folders = (draft,) if isinstance(draft, Path) else draft
    files = [(f"draft/{p.name}", p) for p in sorted((p for d in folders for p in d.glob("*.toml")),
                                                  key=lambda p: p.name)]
    files.append((f"data/generated/{level}.json", data / "generated" / f"{level}.json"))
    lines = [f"derive_version {DERIVE_VERSION}"]
    lines += [f"{rel} {hashlib.sha256(p.read_bytes()).hexdigest()}" for rel, p in files if p.is_file()]
    gens = {p.stem: json.loads(p.read_bytes()) for p in sorted(Path(data, "generated").glob("*.json"))}
    inputs = derive_inputs(level, toml(data / "tricks.toml"), toml(data / "levels" / f"{level}.toml"), gens)
    lines.append(f"inputs {hashlib.sha256(json.dumps(inputs, sort_keys=True, default=str).encode()).hexdigest()}")
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def path_of(level: str, derived: Path = DERIVED) -> Path:
    """A level's committed derived file."""
    return derived / f"{level}.json.gz"


def read_text(path: Path) -> str:
    """A derived file's text (the JSON :func:`dumps` wrote)."""
    return gzip.decompress(path.read_bytes()).decode("utf-8")


def write_text(path: Path, text: str) -> None:
    """Write a derived file: the text gzip-compressed with no name or time
    in its header, so the same text gives the same bytes (with the same
    zlib), through a temporary file in the same folder."""
    buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", compresslevel=9, fileobj=buf, mtime=0) as f:
        f.write(text.encode("utf-8"))
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(buf.getvalue())
    tmp.replace(path)


def tiers_of(edge: dict) -> dict:
    """An edge's requirement at each movement tier: its hardest option
    (``options``, or ``requires`` with its ``difficulty``, default 1) whose
    difficulty the tier allows, ``false`` where none is or ``requires`` is
    ``false``.  The options are the Pareto set over the tiers (D113), so
    the hardest allowed one is the cheapest."""
    if edge["requires"] == "false":
        return {t: "false" for t in TIERS}
    opts = sorted(edge.get("options") or [{"requires": edge["requires"], "difficulty": edge.get("difficulty", 1)}],
                  key=lambda o: o["difficulty"])
    return {t: next((o["requires"] for o in reversed(opts) if o["difficulty"] <= n), "false")
            for n, t in enumerate(TIERS, 1)}


def bskip_id(level, gid, za, zb, kit):
    """A generated bskip skip's id, ``tricks.toml`` ``[[skip_rule]]``
    bskip_edge's pattern ``<level>.bskip.<barrier>.<from>.<to>.<kit>``: the
    barrier's name without separators, and reach's zones."""
    stem = re.sub(r"[^a-z0-9]", "", gid.split(".")[-1].lower()) or "gate"
    return f"{level}.bskip.{stem}.z{za:03d}.z{zb:03d}.{'none' if kit == 0 else f'air{kit}'}"


def _r1(x):
    return None if x is None else round(float(x), 1)


def req_ranks(ranks):
    """Per-tier ranks -> the Pareto options as (rank, difficulty): each tier
    whose rank is cheaper than every easier tier's (D113)."""
    from azurkit.tools.randomizer.draft.wiring import TIER_N
    out, cheapest = [], None
    for tname, r in zip(TIERS, ranks):
        r = int(r)
        if r >= 4 or (cheapest is not None and r >= cheapest):
            continue
        cheapest = r
        out.append((r, TIER_N[tname]))
    return out


def req_fields(ranks):
    """``requires`` and ``difficulty`` of the least difficult option, and every
    option when there are several (each its own edge, §4.3)."""
    from azurkit.tools.randomizer.draft.wiring import RANK_REQ
    opts = [{"requires": RANK_REQ[r], "difficulty": d} for r, d in req_ranks(ranks)]
    if not opts:
        return {"requires": "false"}
    out = dict(opts[0])
    if len(opts) > 1:
        out["options"] = opts
    return out


def fold_gates(fields, atoms, undecoded):
    """A requirement entry with the gate atoms ANDed into ``requires`` and
    every option; a gate whose requirement is not decoded makes it
    ``false``, with a ``held`` requirement for the gate-undecoded rung that
    carries a ``flag:<gate>.open`` atom per undecoded gate."""
    from azurkit.tools.randomizer.draft.wiring import and_req
    if undecoded:
        marks = [f"flag:{re.sub(r'[^A-Za-z0-9_.]', '_', u.replace('/', '.'))}.open" for u in sorted(undecoded)]
        out = {"requires": "false", "gate_undecoded": sorted(undecoded),
               "held": dict(fold_gates(fields, list(atoms) + marks, ()), probe=["gate-undecoded"])}
        if "difficulty" in fields:
            out["difficulty"] = fields["difficulty"]
        return out
    out = dict(fields)
    out["requires"] = and_req(fields["requires"], *atoms)
    if "options" in fields:
        out["options"] = [dict(o, requires=and_req(o["requires"], *atoms)) for o in fields["options"]]
    return out


# --------------------------------------------------------------------------- the document
def _bypass_entry(A, d, zid):
    """A gate direction of the barrier cut (zone ids, least air per tier, the skips it generated)."""
    gen = sorted(bskip_id(A.name, d["gate"], d["from"], d["to"], k[3]) for k in A.bskip_gen
                 if k[:3] == (d["gate"], d["from"], d["to"]))
    Z = A.zone_of

    def tie_content(z):
        locs = sorted(lid for lid, x in A.loc.items() if x["logic"]["node"] is not None and int(Z[x["logic"]["node"]]) == z)
        ex = sorted({o["label"] for o in A.obj_at.values() if o["kind"] == "exit" and any(int(Z[n]) == z for n in o["nodes"])})
        return {"zone": zid(z), "locations": locs, "exits": ex} if (locs or ex) else None
    out = {"from": zid(d["from"]), "to": zid(d["to"]),
           "side": {"out": "from the spawn's side", "in": "into the spawn's side"}.get(d["side"], "neither holds the spawn"),
           **({"shut_with": d["shut_with"]} if d.get("shut_with") else {}),
           **({"geometric": "flights over the shut barrier between these two zones: each is a crossing whatever the "
                            "side analysis says; far_zones is only the landing zone"} if d.get("geometric") else {}),
           "least_air_gate_shut_before": {"default": d["bypass_default"], "every_probe_class": d["bypass_any"]}}
    if d.get("not_separated"):
        out["not_separated"] = True
        return out
    out.update({"far_zones": [zid(z) for z in sorted(d["_far_z"])], "far_rounds": d.get("far_rounds"),
                "crossing_edges": len(d.get("_cut", ())), "data_edges_left": d.get("data_edges", 0),
                "generated_skips": gen, "confirmed_skips": [S["id"] for S in d.get("confirmed") or ()],
                "leaks": d.get("leaks", False), "ties": len(d.get("_ties", ())),
                "ties_with_content": [t_ for t_ in (tie_content(z) for z in sorted(d.get("_ties", ()))) if t_],
                "ties_past_the_barrier_plane": [
                    {"zone": zid(z), "least_m_to_barrier": g_[0], "past_plane_m": g_[1], **(tie_content(z) or {})}
                    for z, g_ in sorted(((z_, t_) for z_, t_ in d.get("_tie_geo", {}).items()
                                         if t_[1] is not None and t_[1] > 0), key=lambda kv: (kv[1][0], kv[0]))]})
    return out


def build_doc(A, stamp_: str) -> dict:
    """The derived document of a finished :class:`~.reach.Reach` (the module docstring)."""
    import numpy as np

    from devkit.rando.draft.gates import PROBE_LADDER, probe_class
    from azurkit.tools.randomizer.draft.geometry import CAT_NAME, CELL
    from azurkit.tools.randomizer.draft.wiring import RANK_REQ, and_req

    lv, w, name = A.lv, A.W["logic"], A.name
    nb = w.nreg
    Z = A.zone_of

    def zid(z):
        return f"{name}.Z{int(z):03d}"
    loc_node = {lid: e["logic"]["node"] for lid, e in A.loc.items()}
    zone_locs, zone_anch = collections.defaultdict(list), collections.defaultdict(list)
    for lid, n in loc_node.items():
        if n is not None:
            zone_locs[int(Z[n])].append(lid)
    for n, ids in A.anchor["logic"].items():
        for gid in ids:
            zone_anch[int(Z[n])].append(gid)
    kind_of = {gid: e["kind"] for gid, e in A.obj_at.items()}
    spawn_z = {int(Z[n]) for n in A.spawn["logic"]}
    prop = {}
    for nd in A.toml.get("node", []):
        if nd.get("start") or (name == "town" and nd.get("hub")):
            for z in sorted(spawn_z):
                prop.setdefault(z, nd["id"])
        if nd["id"].endswith("_ocean") and A.wg.n:
            prop.setdefault(int(Z[nb + 0]), nd["id"])
    meaningful = sorted(set(zone_locs) | set(zone_anch))
    for z in meaningful:
        prop.setdefault(z, f"{name}_z{z:03d}")
    cells = {loc["id"]: loc.get("cell") for loc in A.gen.get("locations", [])}
    gate_req = {g["id"]: g["requires"] for g in A.gates}
    conf_sk = A.confirmed_bskip
    agg = {}
    for (a, b), e in ((k, e) for k, es in A.E["logic"].items() for e in es):
        za, zb = int(Z[a]), int(Z[b])
        if za == zb or min(e["ranks"]) >= 4:
            continue
        pc = probe_class(e)
        bs = tuple(tuple(t) for t in e.get("bskip", ()))
        # flap and non-flap edges, and slippery walks, aggregate apart: the kind carries the ranks it stands for
        key = (za, zb, tuple(e.get("through", ())), e["conf"], pc or "", bs, tuple(e.get("needs", ())),
               tuple(e.get("needs_undecoded", ())), e["kind"] == "skip", e["kind"] == "flap", bool(e.get("slip")),
               tuple(e.get("flags", ())), (e.get("current") or {}).get("volume"))
        x = agg.get(key)
        if x is None:
            agg[key] = x = {"from": zid(za), "to": zid(zb), "kind": e["kind"], "ranks": list(e["ranks"]),
                            "confidence": e["conf"], "through": list(e.get("through", ())),
                            "probe": pc, "via": e.get("via"), "_bs": bs,
                            "needs": list(e.get("needs", ())) or None, "_nu": list(e.get("needs_undecoded", ())),
                            "_fl": list(e.get("flags", ())), "_cur": e.get("current"),
                            "conf_movement": e.get("conf_movement"),
                            "dh": _r1(e.get("dh")), "gap": _r1(e.get("gap")), "why": e.get("why"),
                            "fall_hp": e.get("fall", 0), "_rk": sum(e["ranks"]),
                            "_certs": list(e.get("certs") or [None] * len(TIERS)),
                            "hurdle": _r1(e.get("hurdle")), "slip": True if e.get("slip") else None,
                            # §4.3 `logic = false` on a probe-needed edge (any class but bskip, whose held skip atom
                            # already keeps it out of logic): a reader of `requires` alone stays in logic
                            "logic": False if (e["conf"] == "probe-needed" and pc != "bskip") else None}
        if sum(e["ranks"]) < x["_rk"]:
            x.update({"kind": e["kind"], "dh": _r1(e.get("dh")), "gap": _r1(e.get("gap")), "why": e.get("why"),
                      "fall_hp": e.get("fall", 0), "_rk": sum(e["ranks"]),
                      "hurdle": _r1(e.get("hurdle")), "conf_movement": e.get("conf_movement")})
        for ti, (p, q) in enumerate(zip(x["ranks"], e["ranks"])):
            if q < p and e.get("certs"):
                x["_certs"][ti] = e["certs"][ti]
        x["ranks"] = [min(p, q) for p, q in zip(x["ranks"], e["ranks"])]
    # every zone an exported edge touches is kept, so a route through a small zone survives the export
    kept_z = set(meaningful) | {z for z in range(A.nzone) if A.zone_area[z] >= 25.0} | \
        {k[0] for k in agg} | {k[1] for k in agg}
    zones = []
    for z in range(A.nzone):
        if z not in kept_z:
            continue
        members = np.nonzero(Z == z)[0]
        an = collections.defaultdict(list)
        for gid in sorted(set(zone_anch.get(z, []))):
            an[kind_of.get(gid, "other")].append(gid)
        cc = collections.Counter(cells.get(lid) for lid in zone_locs.get(z, []))
        zones.append({"id": zid(z), "node": prop.get(z), "area_m2": round(float(A.zone_area[z]), 2),
                      "land_regions": int((members < nb).sum()), "water_regions": int((members >= nb).sum()),
                      "anchors": dict(sorted(an.items())), "locations": sorted(zone_locs.get(z, [])),
                      "cells": dict(sorted((k, v) for k, v in cc.items() if k))})

    def atoms_at(bs, r):
        """The skip atoms a barrier crossing needs at rank r: a confirmed skip's when it covers the kit, else
        the held generated skip's."""
        out = []
        for gid, fa, fb, sid in bs:
            if sid and r >= conf_sk[sid]["kit"]:
                out += [f"skip:{sid}"] + ([RANK_REQ[r]] if r > conf_sk[sid]["kit"] else [])
            else:
                out.append(f"skip:{bskip_id(name, gid, fa, fb, r)}")
        return out

    edges, used_skips, cur_skips = [], set(), {}
    for key in sorted(agg):
        x = agg[key]
        bs, through = x.pop("_bs"), x["through"]
        atoms = [gate_req[t] for t in through if gate_req.get(t)] + list(x.get("needs") or ())
        undecoded = [t for t in through if gate_req.get(t) is None] + x.pop("_nu")
        fl_ = x.pop("_fl")
        atoms += [A.flag_event(p_) for p_ in fl_]
        if fl_:
            x["flags"] = [A.flag_label(p_) for p_ in fl_]
        cur = x.pop("_cur")
        if cur:
            stem = re.sub(r"[^a-z0-9]", "", cur["volume"].lower()) or "push"
            sid = cur["skip"] or f"{name}.current.{stem}"
            atoms.append(f"skip:{sid}")
            x["current"] = {"volume": cur["volume"], "terminal_mps": cur["speed"], "skip": sid}
            cur_skips.setdefault(sid, {"volume": cur["volume"], "crossings": set(), "hand": bool(cur["skip"])})[
                "crossings"].add(f"{x['from']}->{x['to']}")
        if bs and x["kind"] == "skip":
            sid = bs[0][3]
            fields = {"requires": and_req(*atoms_at(bs, x["ranks"][0])), "difficulty": 1,
                      "skip_difficulty": conf_sk[sid]["difficulty"]}
        elif bs:
            opts = [{"requires": and_req(*atoms_at(bs, r)), "difficulty": d} for r, d in req_ranks(x["ranks"])]
            fields = dict(opts[0], **({"options": opts} if len(opts) > 1 else {}))
        else:
            fields = req_fields(x["ranks"])
        if atoms or undecoded:
            fields = fold_gates(fields, atoms, undecoded)
        certs = x.pop("_certs")
        if any(certs):          # a flight's certificate per option: what it physically needs (D167, D168)
            for o in fields.get("options") or ([fields] if fields["requires"] != "false" else []):
                c = certs[o["difficulty"] - 1] if o.get("difficulty") else None
                if c is not None:
                    o["cert"] = c.as_dict()
        x.update(fields)
        tiers = {}
        for t, r in zip(TIERS, x["ranks"]):
            if r >= 4 or undecoded:
                tiers[t] = "false"
            else:
                tiers[t] = and_req(*(atoms_at(bs, x["ranks"][0] if x["kind"] == "skip" else r) if bs else [RANK_REQ[r]]),
                                   *atoms)
        if tiers != tiers_of(x):         # each tier's requirement, gate and skip atoms included, is its options'
            raise ValueError(f"{name}: edge {x['from']}->{x['to']} {x['kind']}: tiers {tiers} are not its options'")
        if through:
            x["gate_requires"] = [gate_req.get(t) if gate_req.get(t) is not None else "false" for t in through]
        if bs:
            x["bskip"] = [{"gate": gid, "side_from": zid(fa), "side_to": zid(fb), "confirmed_skip": sid}
                          for gid, fa, fb, sid in bs]
            used_skips.update(a_[5:] for t in tiers.values() for a_ in re.findall(r"skip:[a-z0-9_.]+", t))
            # a held requirement (past an undecoded gate) names its generated skips too: they are exported
            used_skips.update(a_[5:] for a_ in re.findall(r"skip:[a-z0-9_.]+", json.dumps(x.get("held") or {})))
        edges.append({k: v for k, v in x.items() if not k.startswith("_") and k != "ranks" and v is not None
                      and not (k == "through" and not v) and not (k == "fall_hp" and not v)})
    gen_skips = {}
    for (gid, fa, fb, K), g_ in sorted(A.bskip_gen.items()):
        sid = bskip_id(name, gid, fa, fb, K)
        if sid not in used_skips:
            continue
        d = g_["dir"]
        gen_skips[sid] = {
            "id": sid, "name": f"{name} {gid.split('.')[-1]} {zid(fa)} -> {zid(fb)} ({'no air' if K == 0 else f'air {K}'})",
            "tricks": ["bskip"], "requires": RANK_REQ[K],
            "difficulty": max(2, g_["difficulty"]),   # D259: a safe pass rates standard (Safe folds into Standard)
            "status": "held", "confirmed": "no",
            "held_reason": "unconfirmed (D114): computed by the reach model from the decoded collision, never seen in "
                           "game; it enters logic once xemu reproduces it with this kit or the owner confirms it",
            "from": zid(fa), "to": zid(fb), "gates": [gid], "rule": "bskip_edge",
            "side": {"out": "from the spawn's side", "in": "into the spawn's side"}.get(d["side"], "neither side holds the spawn"),
            "crossings": [f"{zid(p)}->{zid(q)}" for p, q in sorted(g_["crossings"])],
            "probe": "bskip", "crossing_movement": g_.get("crossing_movement"), "crossing_difficulty": g_.get("crossing_difficulty"),
            "route": [zid(z_) for z_ in g_["route"]] if g_.get("route") else None,
            "route_requires": g_.get("route_requires"), "route_tier": g_.get("route_tier"),
            **({"route_uses_probe_edges": True} if g_.get("route_uses_probe_edges") else {}),
            **({"route_ends_in_far_side": "the crossing lands where the far side's zone is not reached from"}
               if g_.get("route") and not g_.get("route_reaches_side") else {})}
    held_hand = {}
    for sid, c_ in sorted(cur_skips.items()):
        if c_["hand"]:
            h = A.tricks.get(sid, {})
            ok = h.get("status") == "in_logic" and h.get("confirmed") not in (None, "no")
            held_hand[sid] = {"id": sid, "status": h.get("status", "held"),
                              "confirmed": h.get("confirmed", "no") if not isinstance(h.get("confirmed"), dict)
                              else f"{h['confirmed'].get('by')}: {h['confirmed'].get('ref')}",
                              "requires": h.get("requires", "true"), "difficulty": h.get("difficulty"),
                              "probe": "skip" if ok else "current", "source": "tricks.toml", "volume": c_["volume"],
                              "crossings": sorted(c_["crossings"])}
            continue
        gen_skips[sid] = {"id": sid, "name": f"{name} against {c_['volume']} (any crossing)", "tricks": ["current"],
                          "requires": "true", "difficulty": None, "status": "held", "confirmed": "no", "probe": "current",
                          "rule": "current_against",
                          "held_reason": "unconfirmed (D114): computed by the reach model (a push whose terminal speed "
                                         "reaches the swim stroke), never tried in game",
                          "volume": c_["volume"], "crossings": sorted(c_["crossings"])}
    nodes_with = set(A.anchor["logic"]) | {n for n in loc_node.values() if n is not None}
    regions = []
    for r in range(nb):
        if w.area(r) < 2.0 and r not in nodes_with:
            continue
        regions.append({"id": _nid(name, nb, r), "zone": zid(Z[r]), "area_m2": round(w.area(r), 1),
                        "anchors": sorted(A.anchor["logic"].get(r, [])),
                        "locations": sorted(lid for lid, n in loc_node.items() if n == r)})
    for k in range(A.wg.n):
        n = nb + k
        regions.append({"id": _nid(name, nb, n), "zone": zid(Z[n]), "water": True,
                        "area_m2": round(float(A.wg.count[k]) * CELL * CELL, 1),
                        "anchors": sorted(A.anchor["logic"].get(n, [])),
                        "locations": sorted(lid for lid, nn in loc_node.items() if nn == n)})
    gates = []
    for g in A.gates:
        gates.append({"id": g["id"], "members": g["member_names"], "member_kind": g["member_state"],
                      "present_at_load": g["present_at_load"], "driver": g["driver"],
                      "requires": g["requires"] if g["requires"] is not None else "false",
                      **({"requires_from": g["requires_from"]} if g.get("requires_from") else {}),
                      **({"opened_by_pads": True} if g.get("pad_only") else {}),
                      **({"pads_unreached": g["pads_unreached"]} if g.get("pads_unreached") else {}),
                      **({"present_at_load_stored": [bool(lv.owners[oi].get("present_stored", lv.owners[oi]["present"]))
                                                     for oi in g["members"]]}
                         if any(oi in A.init_changed for oi in g["members"]) else {}),
                      "bound_to": g["bound_to"], "family": g["family"], "family_class": g["family_class"],
                      "separates_zones": sorted({tuple(sorted({zid(Z[r]) for r in grp})) for grp in g.get("merges", [])
                                                 if len({int(Z[r]) for r in grp}) > 1}),
                      "separates_regions": len(g.get("merges", [])),
                      "water_separates_zones": sorted({tuple(sorted({zid(Z[nb + r]) for r in grp}))
                                                       for grp in g.get("water_merges", [])
                                                       if len({int(Z[nb + r]) for r in grp}) > 1}),
                      "splits_regions_when_flipped": len(g.get("splits", [])),
                      "encloses_locations": sorted(lid for lid, x in A.loc.items() if g["id"] in x.get("gates", [])),
                      **({"requires_undecoded": True} if g["requires"] is None else {}),
                      **({"requires_family": g["requires_from_family"]} if g.get("requires_from_family") else {}),
                      **({"held_reason": g["family_held"]} if g.get("family_held") else {}),
                      "destroy_from": sorted({zid(Z[r]) for r in g.get("destroy_from", [])}) if g.get("shapes") else None,
                      **({"hazard": g["hazard"]} if g.get("hazard") else {}),
                      **({"door": "moved by its lock (data: the links that move it trace back to the lock); the open "
                                  "pose is not decoded [inferred: it clears the doorway]", "lock": g["lock"]}
                         if g.get("door") == "lock" else {}),
                      **({"bypasses": [_bypass_entry(A, d, zid) for d in A.bskip_dirs if d["gate"] == g["id"]
                                       and (d.get("_cut") or d.get("not_separated") or d.get("data_edges"))],
                          "bypass_directions_checked": sum(1 for d in A.bskip_dirs if d["gate"] == g["id"])}
                         if any(d["gate"] == g["id"] for d in A.bskip_dirs) else {}),
                      "confidence": "data (requirement) / geometry (sides)" if not g.get("hazard")
                      else "geometry (sides); requirement not decoded"})
    rigs = []
    for r in A.rig_info["logic"]:
        zs_ = sorted({zid(Z[n]) for n in r["regions"]})
        if len(zs_) > 1:
            rigs.append({"name": r["name"], "deck_m2": r["deck_m2"], "movers": r["movers"], "axes": r["axes"],
                         "joins_zones": zs_, **({"gated_by": r["gated_by"]} if r.get("gated_by") else {}),
                         "confidence": "probe-needed (motion range not decoded; trigger "
                                       + ("from data" if r.get("gated_by") else "not decoded") + ")"})
    rigs.sort(key=lambda r: r["name"])
    doors = []
    for d in A.doors:
        if not d.get("merges"):
            continue        # a door-shaped rig whose opening joins no regions
        doors.append({"id": d["id"], "members": d["member_names"], "movers": d["movers"], "opened_by": d["opened_by"],
                      "joins_zones": sorted({tuple(sorted({zid(Z[r]) for r in grp})) for grp in d.get("merges", [])
                                             if len({int(Z[r]) for r in grp}) > 1}),
                      "joins_regions": len(d.get("merges", [])),
                      "confidence": "probe-needed (opened by the action button or a touch [data]; the swing is not decoded)"})
    objs = []
    for gid, e in sorted(A.obj_at.items()):
        objs.append({"kind": e["kind"], "id": gid, "label": e["label"], "at": sorted({zid(Z[n]) for n in e["nodes"]}),
                     **({"main_zone": zid(Z[e["main"]])} if "main" in e else {}),
                     "how": e["how"], "rig": e["rig"], **({"dz": e["dz"]} if "dz" in e else {}),
                     **({"support": {k: v for k, v in e["support"].items() if k != "oi"}} if "support" in e else {})})
    locs = []
    for lid in sorted(A.loc):
        e = A.loc[lid]
        m = e["logic"]
        if m["how"] != "air":
            fields = req_fields(m["ranks"])
            if e.get("gate_need"):
                fields = fold_gates(fields, e["gate_atoms"], e["gate_undecoded"])
        else:
            # held: `false` in logic; on its own probe rung (`float`) reach counts it when its zone is reached and
            # `held.requires` holds
            fields = {"requires": "false",
                      "held": {"probe": ["float"] + (["gate-undecoded"] if e["gate_undecoded"] else []),
                               "requires": and_req(*e["gate_atoms"]),
                               "reason": "high above any floor: a spring, an updraft or a ledge above is needed, and none "
                                         "of them is an edge here (probe-needed, class float)"}}
        ent = {"id": lid, "class": e["class"], "item": e["item"], "how": m["how"],
               "zone": zid(Z[m["node"]]) if m["node"] is not None else None,
               "region": _nid(name, nb, m["node"]) if m["node"] is not None else None,
               **fields,
               **({"gates": e["gates"]} if e.get("gates") else {}),
               **({"gated_by": e["gated_by"]} if e.get("gated_by") else {}),
               **({"enclosed_by": e["enclosed_by"]} if e.get("enclosed_by") else {}),
               **({"doors": e["doors"], "door_note": "behind an action door: probe-needed (class door)"}
                  if e.get("doors") else {}),
               "first_reached_safe": A.first_reach["safe"].get(lid),
               "min_air": {t: A.min_air[lid].get(t) for t in TIERS},
               "min_air_gates_open": {t: A.min_air_open[lid].get(t) for t in TIERS},
               "flap_flights_min": {t: A.flaps_min[lid].get(t) for t in TIERS}}
        if e.get("in_hazard"):
            ent["in_hazard"] = e["in_hazard"]
        if m.get("dz") is not None and m["how"] != "floor":
            ent["dz"] = m["dz"]
        if m.get("points_span_nodes"):
            ent["points_span_nodes"] = m["points_span_nodes"]
        if e.get("support"):
            ent["support"] = {k: v for k, v in e["support"].items() if k != "oi"}
        locs.append(ent)
    E = A.E["logic"]
    counts = {"triangles": int(len(lv.P)),
              "owners": dict(sorted(collections.Counter(CAT_NAME[o["cat"]] for o in lv.owners).items())),
              "logic_samples": int(len(w.z)), "logic_regions": int(nb), "water_regions": int(A.wg.n),
              "zones": int(A.nzone), "zones_output": len(zones), "regions_output": len(regions),
              "region_edges": dict(sorted(collections.Counter(e["kind"] for es in E.values() for e in es).items())),
              "region_edges_by_conf": dict(sorted(collections.Counter(e["conf"] for es in E.values() for e in es).items())),
              "zone_edges": len(edges), "phys_samples": int(len(A.W["phys"].z)), "phys_regions": int(A.W["phys"].nreg),
              "hazard_samples_removed": int(w.removed_hazard), "eroded_samples": int(w.eroded.sum()),
              "flights": A.flight_stats.get("logic", {}),
              "probe_edges_by_class": dict(sorted(collections.Counter(
                  probe_class(e) for es in E.values() for e in es if probe_class(e)).items())),
              "door_shaped_rigs_opened_by_action_or_touch": len(A.doors),
              "action_doors_joining_regions": sum(1 for d in A.doors if d.get("merges")),
              "door_gates": sum(1 for g in A.gates if g.get("door") == "lock"),
              "air": {"gaps": int(A.air.N), "joins": int(A.air.joins), "components": int(A.air.n_components)},
              "water": {"columns": int(A.wg.water_columns), "nodes": int(len(A.wg.col)), "joins": int(A.wg.joins),
                        "columns_in_kill_fields": int(A.wg.hazard_cols),
                        "columns_no_swimmable_water_above_the_seabed": int(A.wg.dry_cols),
                        "columns_water_under_the_seabed_dropped": int(A.wg.void_cols),
                        "columns_under_land_above_the_surface": int(A.wg.land_cols),
                        "gaps_inside_closed_solids_dropped": int(A.wg.inside_gaps),
                        "gaps_inside_closed_solids_dropped_m": round(float(A.wg.inside_m), 1)},
              "map_points_walled": int(getattr(A, "walled_points", 0)),
              "locations_gated": sum(1 for x in A.loc.values() if x.get("gate_need")),
              "locations_walled": sum(1 for x in A.loc.values() if x["logic"]["how"] == "walled"),
              "undecoded_gates": sorted(A.undecoded),
              "bskip": {"directions": len(A.bskip_dirs),
                        "directions_with_crossings": sum(1 for d in A.bskip_dirs if d.get("_cut")),
                        "not_separated": sum(1 for d in A.bskip_dirs if d.get("not_separated")),
                        "crossing_edges": sum(len(d.get("_cut", ())) for d in A.bskip_dirs),
                        "far_zones": sum(len(d.get("_far_z", ())) for d in A.bskip_dirs),
                        "ties": sum(len(d.get("_ties", ())) for d in A.bskip_dirs),
                        "ties_past_the_barrier_plane": sum(1 for d in A.bskip_dirs for t_ in d.get("_tie_geo", {}).values()
                                                           if t_[1] is not None and t_[1] > 0),
                        "generated_skips": len(gen_skips),
                        "confirmed_matches": sorted({S["id"] for d in A.bskip_dirs for S in d.get("confirmed") or ()}),
                        "confirmed_not_used": sorted(A.confirmed_ignored),
                        "confirmed_unmatched": dict(sorted(A.confirmed_unmatched.items())),
                        "leaks": sum(1 for d in A.bskip_dirs if d.get("leaks")),
                        "parallel_gate_directions": sum(1 for d in A.bskip_dirs if d.get("shut_with")),
                        "overflight_edges_by_gate": A.overflight_counts["edges_by_gate"],
                        "overflight_marks_dropped": A.overflight_counts["marks_dropped"],
                        "overflight_directions_of_their_own": A.over_dirs,
                        "overflight_edges_same_side": A.over_same_side,
                        "overflight_crossings": sum(1 for d in A.bskip_dirs for _, _, e in d.get("_cut", ()) if e.get("over"))},
              "carry": {**{k: v for k, v in (getattr(A, "_carry", None) or {}).items() if k in ("steps", "exits", "components")},
                        **getattr(A, "blocked_split", {})}}
    from devkit.rando.draft import reach as R
    params = {"cell_m": CELL, "tiers": list(TIERS), "probe_ladder": list(PROBE_LADDER),
              "spawn_spots": R.SPAWN.get(name, ["startspot"]), "envelope_sha256": A.env.sha256}
    return {"_meta": {"format": FORMAT, "generator": GENERATOR, "level": name, "stamp": stamp_,
                      "status": "derived (D108 Q255: geometry-derived edges are drafts the owner reviews)",
                      "no_coordinates": "ids, names, counts, areas and relative dh/gap only (RANDOMIZER_PLAN §4.4)"},
            "level": name, "params": params, "counts": counts, "coverage": A.cov,
            "zones": zones, "edges": edges, "gates": gates, "doors": doors, "skips": [gen_skips[k] for k in sorted(gen_skips)],
            "confirmed_skips": [dict(v, used_by_edges=any(f"skip:{k}" in t for e in edges for t in tiers_of(e).values()))
                                for k, v in sorted(conf_sk.items())],
            "hand_skips": [held_hand[k] for k in sorted(held_hand)],
            "events": _events(A, zid), "mechanisms": _mechanisms(A),
            "rigs": rigs, "objects": objs, "locations": locs, "regions": regions}


def _nid(name, nb, k):
    return f"{name}.R{k:04d}" if k < nb else f"{name}.W{k - nb:02d}"


def _events(A, zid):
    """The flags reach sets (pads, pickups, arrivals): id, kind, what sets it and the zones where it is set."""
    out = []
    Z = A.zone_of
    for _, f in sorted(A.flagdef.items(), key=lambda kv: kv[1]["label"]):
        ent = {"id": f["label"], "kind": f["kind"], "persistent": f.get("persistent", False),
               "set_at": sorted({zid(Z[n]) for n in f["nodes"]["logic"]})}
        if f["kind"] == "loc":
            ent["location"] = f["loc"]
        elif f["kind"] == "arrive":
            ent["holds_at_spawn"] = f["spawn"]
        else:
            ent["platform"] = f["platform"]
        out.append(ent)
    return out


def _mechanisms(A):
    """The data-derived mechanisms and what they gave (names, counts, relative heights and speeds only)."""
    lv = A.lv
    cnt = collections.Counter(e["kind"] for es in A.E["logic"].values() for e in es)
    return {
        "teleports": A.tele,
        "rides": A.rides,
        "updrafts": [{"name": u["name"], "pushZ": u["push"][2], "switched": u["switched"],
                      "requires": "true" if not u["switched"] else A.alts_req(u["alts"])} for u in A.updrafts],
        "downdrafts": len(A.downdrafts),
        "currents": [{"name": c["name"], "terminal_mps": c["speed"], "switched": c["switched"],
                      "blocks_swim": c["blocks_swim"], "moved": c["moved"],
                      "requires": "true" if not c["switched"] else A.alts_req(c["alts"])} for c in A.currents],
        "spring_blockers": sorted({lv.owners[oi]["name"] for oi in A.spring_blockers}),
        "present_at_load_changed": sorted({(lv.owners[oi]["name"], bool(lv.owners[oi]["present"])) for oi in A.init_changed}),
        "edges": {k: cnt[k] for k in ("push", "current", "slide", "teleport", "rig")},
        "swim_nodes_in_blocking_currents": int(A.wg.blocked),
        "wiring_undecoded_nodes": dict(sorted(A.wire.undecoded_nodes.items())),
        "spawn_resolution": A.spawn_how}


def dumps(doc: dict) -> str:
    """The document as compact JSON with sorted keys: the head with one key
    per line, then each list section with one entry per line (a diff of the
    decompressed texts stays readable)."""
    def conv(o):
        if hasattr(o, "item"):
            return o.item()
        if isinstance(o, (set, frozenset, tuple)):
            return sorted(o) if isinstance(o, (set, frozenset)) else list(o)
        raise TypeError(type(o))
    compact = {"sort_keys": True, "default": conv, "separators": (",", ":")}
    head = json.dumps({k: v for k, v in doc.items() if k not in LIST_SECTIONS}, indent=0, **compact)
    parts = [head[:-2]]
    for k in LIST_SECTIONS:
        rows = ",\n".join(json.dumps(x, **compact) for x in doc[k])
        parts.append(f',\n"{k}":[\n{rows}\n]' if rows else f',\n"{k}":[]')
    return "".join(parts) + "\n}\n"


# --------------------------------------------------------------------------- the consumer's checks
TOK = re.compile(r"\s*(\(|\)|&|\||[^\s()&|]+)")
COUNTERS = {"air", "water", "fire", "earth", "disca", "discw", "discf", "disce", "discl", "obsidian", "sapphire", "emerald",
            "ruby", "diamond", "life", "staff", "ammo"}
ATOM = re.compile(r"(?:(?P<c>[a-z]+|key\.[a-z_]+)>=(?P<n>\d+)|flag:[a-z0-9]+(\.[A-Za-z0-9_]+)+|button:[a-z0-9]+(\.[A-Za-z0-9_]+)+|"
                  r"event:[a-z0-9]+(\.[A-Za-z0-9_]+)+|skip:(?P<s>[a-z0-9]+(\.[a-z0-9_]+)+)|true|false)$")
# the numeric keys reviewed as coordinate-free (relative heights, distances, areas, speeds, counts' rates); a number
# under any other key, or a 2-3 float vector outside VEC_KEYS, fails the no-coordinate check
NUM_KEYS = {"area_m2", "cell_m", "damage", "deck_m2", "dh", "dz", "frame_perfect", "gap", "gaps_inside_closed_solids_dropped_m",
            "hard", "headroom", "hurdle", "least_m_to_barrier", "moved_m", "past_plane_m", "pct", "pushZ", "rim", "runup",
            "room_end", "room_start", "safe", "slope", "standard", "terminal_mps"}
VEC_KEYS = {"moved_m", "damage"}


def _parse(s):
    toks = TOK.findall(s)
    pos = [0]

    def peek():
        return toks[pos[0]] if pos[0] < len(toks) else None

    def take():
        pos[0] += 1
        return toks[pos[0] - 1]

    def expr():
        n = [and_()]
        while peek() == "|":
            take()
            n.append(and_())
        return ("or", n) if len(n) > 1 else n[0]

    def and_():
        n = [unary()]
        while peek() == "&":
            take()
            n.append(unary())
        return ("and", n) if len(n) > 1 else n[0]

    def unary():
        t = take()
        if t == "(":
            e = expr()
            if take() != ")":
                raise ValueError(f"unbalanced {s!r}")
            return e
        m = ATOM.match(t)
        if not m or (m.group("c") and m.group("c") not in COUNTERS and not m.group("c").startswith("key.")):
            raise ValueError(f"bad atom {t!r} in {s!r}")
        return ("atom", t)
    e = expr()
    if pos[0] != len(toks):
        raise ValueError(f"trailing tokens in {s!r}")
    return e


def _inv(air, gates):
    c = {"air": air}
    if gates:
        c.update({k: 9 for k in COUNTERS - {"air"}})
    return {"c": c, "gates": gates}


class Doc:
    """A derived document read as a consumer reads it: zones and their edges,
    requirements by the §5.1 grammar, skip atoms, events to a fixpoint."""

    def __init__(self, doc):
        self.doc = doc
        self.gen = {s["id"]: s for s in doc["skips"]}
        self.gen.update({s["id"]: s for s in doc.get("hand_skips", []) if s.get("probe") != "skip"})
        self.hand_on = {s["id"]: s for s in doc.get("hand_skips", []) if s.get("probe") == "skip"}
        self.conf = {s["id"]: s for s in doc["confirmed_skips"]}
        self.events = {f"event:{e['id']}": e for e in doc.get("events", [])}
        self.loc_by_id = {L_["id"]: L_ for L_ in doc["locations"]}
        self.ladder = tuple(doc["params"]["probe_ladder"])
        self.adj = {}
        for e in doc["edges"]:
            self.adj.setdefault(e["from"], []).append(e)
        self.spawn = {z for o in doc["objects"] if o["id"] in doc["coverage"]["spawn"] for z in o["at"]}
        self.cache = {}
        self.last_events = set()

    def ev(self, node, inv, P, held_false=False):
        k = node[0]
        if k == "or":
            return any(self.ev(x, inv, P, held_false) for x in node[1])
        if k == "and":
            return all(self.ev(x, inv, P, held_false) for x in node[1])
        a = node[1]
        if a in ("true", "false"):
            return a == "true"
        m = re.fullmatch(r"([a-z._]+)>=(\d+)", a)
        if m:
            return inv["c"].get(m.group(1), 0) >= int(m.group(2))
        if a.startswith("skip:"):
            sid = a[5:]
            if sid in self.conf:
                return "skip" in P and inv["c"]["air"] >= self.conf[sid]["kit"]
            if sid in self.hand_on:
                return "skip" in P and self.ev(self.p(self.hand_on[sid]["requires"]), inv, P)
            if sid in self.gen:
                return not held_false and self.gen[sid].get("probe", "bskip") in P and \
                    self.ev(self.p(self.gen[sid]["requires"]), inv, P)
            raise KeyError(f"unresolved skip atom {a}")
        if a in self.events:
            return a in inv.get("events", ())
        if a.startswith(("button:", "event:", "flag:")):
            return inv["gates"] and a not in inv.get("deny", ())
        raise ValueError(a)

    def p(self, s):
        if s not in self.cache:
            self.cache[s] = _parse(s)
        return self.cache[s]

    def opts_ok(self, ent, T, inv, P):
        opts = ent.get("options") or [{"requires": ent["requires"], "difficulty": ent.get("difficulty", 1)}]
        return any(o.get("difficulty", 1) <= T and self.ev(self.p(o["requires"]), inv, P) for o in opts)

    def ok(self, ent, T, inv, P):
        if ent.get("confidence") == "probe-needed" and ent.get("probe") not in P:
            return False
        if ent.get("logic") is False and ent.get("probe") not in P:
            return False
        if ent.get("confidence") == "skip" and "skip" not in P:
            return False
        if ent["requires"] == "false" and ent.get("held"):
            h = ent["held"]
            return all(x in P for x in h["probe"]) and self.opts_ok(h, T, inv, P)
        return self.opts_ok(ent, T, inv, P)

    def ok_format(self, ent, T, inv, P):
        """§4.3's own fields only: ``logic = false`` is out, a held location is
        false, a generated skip is held (false)."""
        if ent.get("logic") is False or (ent["requires"] == "false" and ent.get("held")):
            return False
        opts = ent.get("options") or [{"requires": ent["requires"], "difficulty": ent.get("difficulty", 1)}]
        return any(o.get("difficulty", 1) <= T and self.ev(self.p(o["requires"]), inv, P, held_false=True) for o in opts)

    def reach(self, T, inv, P, start=None, skip_edge=None, ok=None, all_events=False):
        """Zones reached, to a fixpoint over the events."""
        ok = ok or self.ok
        inv = dict(inv, events=set(self.events) if all_events else set())
        while True:
            seen = set(start if start is not None else self.spawn)
            st = list(seen)
            while st:
                z = st.pop()
                for e in self.adj.get(z, ()):
                    if e["to"] in seen or (skip_edge and skip_edge(e)) or not ok(e, T, inv, P):
                        continue
                    seen.add(e["to"])
                    st.append(e["to"])
            new = set()
            for a, ev in self.events.items():
                if a in inv["events"]:
                    continue
                if ev["kind"] == "arrive":
                    if ev.get("holds_at_spawn"):
                        new.add(a)
                elif ev["kind"] == "loc":
                    loc = self.loc_by_id.get(ev["location"])
                    if loc and loc["zone"] in seen and ok(loc, T, inv, P):
                        new.add(a)
                elif set(ev["set_at"]) & seen:
                    new.add(a)
            if not new:
                self.last_events = inv["events"]
                return seen
            inv["events"] |= new

    def locs(self, seen, T, inv, P, ok=None):
        fmt = ok is not None and ok == self.ok_format     # §4.3's own fields only: `doors` is not one of them
        ok = ok or self.ok
        inv = dict(inv, events=self.last_events)
        return [loc["id"] for loc in self.doc["locations"]
                if loc["zone"] in seen and (fmt or not loc.get("doors") or "door" in P) and ok(loc, T, inv, P)]

    def flaps(self, T):
        """Zone -> the least flap flights from the spawn (air 3, gates shut, no probe class)."""
        dist = {z: 0 for z in self.spawn}
        dq = collections.deque(self.spawn)
        iv = _inv(3, False)
        self.reach(T, iv, ())
        iv = dict(iv, events=self.last_events)
        while dq:
            z = dq.popleft()
            for e in self.adj.get(z, ()):
                if not self.ok(e, T, iv, ()):
                    continue
                wgt = 1 if e["kind"] == "flap" else 0
                if dist.get(e["to"], 10 ** 9) > dist[z] + wgt:
                    dist[e["to"]] = dist[z] + wgt
                    (dq.append if wgt else dq.appendleft)(e["to"])
        return dist


def hand_ids(db) -> dict:
    """§2.3's sources: the hand buttons, events and barriers of every level file."""
    ids = {"button": set(), "event": set(), "barrier": set()}
    for t in db.levels.values():
        for k in ids:
            ids[k] |= {x["id"] for x in t.get(k, []) if "id" in x}
    return ids


def _strings(x):
    out = [x.get("requires")] + [o["requires"] for o in x.get("options", [])]
    h = x.get("held")
    if h:
        out += [h["requires"]] + [o["requires"] for o in h.get("options", [])]
    return [s for s in out if s is not None]


def coordinate_like(doc) -> dict:
    """{key: count} of numbers under a key not reviewed as coordinate-free, and of 2-3 float vectors."""
    bad = collections.Counter()

    def walk(o, k=None):
        if isinstance(o, dict):
            for kk, v in o.items():
                walk(v, kk)
        elif isinstance(o, list):
            if 2 <= len(o) <= 3 and all(isinstance(v, float) for v in o) and k not in VEC_KEYS:
                bad[f"vector:{k}"] += 1
            for v in o:
                walk(v, k)
        elif isinstance(o, float) and k not in NUM_KEYS:
            bad[f"number:{k}"] += 1
    walk(doc)
    return dict(bad)


def check_doc(doc, ids) -> list[str]:
    """Every problem a consumer finds in a derived document (empty: none).
    ``ids`` are :func:`hand_ids`.  It re-derives the coverage ladder, the
    side rows, min_air (also from §4.3's own fields), the least flap
    flights and the exits from the zone graph alone and compares them with
    the document's; checks every requirement's grammar and skip atom, that
    rides and gate edges carry their atoms (at every tier, :func:`tiers_of`), the barrier guarantee (from a
    direction's near side with its gate shut and no skip atom, every probe
    class: no far zone), that a crossing never stands in logic without a
    skip atom, that every atom resolves (§2.3), and that no number could be
    a coordinate."""
    D = Doc(doc)
    ladder = D.ladder
    bad = []
    for T, tn in enumerate(TIERS, 1):
        rows = [("nothing", _inv(0, False), ()), ("air powers", _inv(3, False), ()),
                ("air powers + confirmed skips", _inv(3, False), ("skip",)), ("gates open", _inv(3, True), ("skip",))]
        acc = ["skip"]
        for pc in ladder:
            acc.append(pc)
            rows.append((f"+probe:{pc}", _inv(3, True), tuple(acc)))
        theirs = {r["state"]: r["items"] for r in doc["coverage"]["tiers"][tn]}
        for lab, iv, P in rows:
            n = len(D.locs(D.reach(T, iv, P), T, iv, P))
            if theirs.get(lab) != n:
                bad.append(f"coverage {tn} {lab}: consumer {n} reach {theirs.get(lab)}")
        for lab, iv, P in rows[:4]:
            n = len(D.locs(D.reach(T, iv, P, ok=D.ok_format), T, iv, P, ok=D.ok_format))
            if theirs.get(lab) != n:
                bad.append(f"§4.3-only {tn} {lab}: {n} reach {theirs.get(lab)}")
        for key, gates in (("min_air", False), ("min_air_gates_open", True)):
            for fmt in (False, True):
                ok = D.ok_format if fmt else None
                mine = {}
                for air in (3, 2, 1, 0):
                    iv = _inv(air, gates)
                    for lid in D.locs(D.reach(T, iv, (), ok=ok), T, iv, (), ok=ok):
                        mine[lid] = air
                for loc in doc["locations"]:
                    if loc["requires"] == "false" and loc.get("held") and (fmt or loc["held"]["probe"][0] == "float"):
                        continue
                    if loc[key][tn] != mine.get(loc["id"]):
                        bad.append(f"{'§4.3-only ' if fmt else ''}{key} {tn} {loc['id']}: consumer {mine.get(loc['id'])} "
                                   f"reach {loc[key][tn]}")
        theirs = {r["state"]: r["items"] for r in doc["coverage"]["side"][tn]}
        for lab, P in [("nothing + confirmed skips + all probe-needed edges", ("skip",) + ladder)] + \
                [(f"nothing + probe:{pc} only", (pc,)) for pc in ("skip",) + ladder]:
            n = len(D.locs(D.reach(T, _inv(0, False), P), T, _inv(0, False), P))
            if theirs.get(lab) != n:
                bad.append(f"side {tn} {lab}: consumer {n} reach {theirs.get(lab)}")
        noslip = lambda e, T_, iv_, P_: not e.get("slip") and D.ok(e, T_, iv_, P_)     # noqa: E731
        n = len(D.locs(D.reach(T, _inv(0, False), (), ok=noslip), T, _inv(0, False), ()))
        lab = "nothing, near-flat slippery floors NOT used"
        if theirs.get(lab) != n:
            bad.append(f"side {tn} {lab}: consumer {n} reach {theirs.get(lab)}")
        dist = D.flaps(T)
        got = {loc["id"]: dist[loc["zone"]] for loc in doc["locations"]
               if loc["zone"] in dist and not (loc["requires"] == "false" and loc.get("held")) and not loc.get("doors")
               and D.ok(loc, T, dict(_inv(3, False), events=D.last_events), ())}
        for loc in doc["locations"]:
            if loc["flap_flights_min"][tn] != got.get(loc["id"]):
                bad.append(f"flap_flights_min {tn} {loc['id']}: consumer {got.get(loc['id'])} reach {loc['flap_flights_min'][tn]}")
        for k in (0, 1):
            lab = f"air powers, at most {k} flap flight{'s' if k != 1 else ''} on the way"
            n = sum(1 for v in got.values() if v <= k)
            if theirs.get(lab) != n:
                bad.append(f"side {tn} {lab}: consumer {n} reach {theirs.get(lab)}")
    ex = {o["id"]: o["at"] for o in doc["objects"] if o["kind"] == "exit"}
    for gid, row in doc["coverage"]["exits"].items():
        for key, gates, P in (("least_air", False, ()), ("least_air_gates_open", True, ()),
                              ("least_air_confirmed_skips", False, ("skip",))):
            for T, tn in enumerate(TIERS, 1):
                mine = next((air for air in (0, 1, 2, 3) if set(ex[gid]) & D.reach(T, _inv(air, gates), P)), None)
                if mine != row[key][tn]:
                    bad.append(f"exit {row['name']} {key} {tn}: consumer {mine} reach {row[key][tn]}")
    for sect in ("edges", "locations", "skips", "confirmed_skips"):
        for x in doc[sect]:
            for s_ in _strings(x):
                try:
                    D.ev(D.p(s_), _inv(3, True), ("skip", "bskip"))
                except (KeyError, ValueError, IndexError) as exc:
                    bad.append(f"grammar {sect} {x.get('id') or (x.get('from'), x.get('to'))}: {exc}")
    for s_ in doc["skips"]:
        if not re.fullmatch(r"[a-z0-9]+(\.[a-z0-9_]+)+", s_["id"]) or s_["status"] != "held" or s_["confirmed"] != "no":
            bad.append(f"skip {s_['id']} not a held dotted id")
    for e in doc["edges"]:
        m = re.findall(r"started by ((?:button|event|flag):[A-Za-z0-9_.]+)", e.get("why") or "")
        if m and not all(a in e["requires"] or a in json.dumps(e.get("held", {})) for a in m):
            bad.append(f"rig {e['from']}->{e['to']} requires {e['requires']!r} lacks {m}")
        if e.get("through") and e.get("gate_requires") and all(e.get("gate_requires")):
            for t, req in tiers_of(e).items():
                if req != "false" and not all(a in req for g in e["gate_requires"]
                                              for a in re.findall(r"[a-z]+:[A-Za-z0-9_.]+|[a-z]+>=\d", g)):
                    bad.append(f"gate edge {e['from']}->{e['to']} tiers {t} {req!r} lacks {e['gate_requires']}")
    for g in doc["gates"]:
        for b in g.get("bypasses", []):
            if b.get("not_separated") or b.get("geometric"):
                continue
            shut = {g["id"]} | set(b.get("shut_with") or ())
            seen = D.reach(4, _inv(3, True), tuple(ladder) + ("skip",), start={b["from"]}, all_events=True,
                           skip_edge=lambda e, shut=shut: bool(shut & set(e.get("through") or ())) or "skip:" in json.dumps(e))
            far = set(b.get("far_zones", [])) | {b["to"]}
            if far & seen:
                bad.append(f"barrier {g['id']} {b['from']}->{b['to']}: far zones {sorted(far & seen)[:6]} reached with the "
                           f"gate shut and no skip atom")
    for e in doc["edges"]:
        for b_ in e.get("bskip") or ():
            if e["requires"] != "false" and "skip:" not in json.dumps([e["requires"], e.get("options")]):
                bad.append(f"bskip edge {e['from']}->{e['to']} over {b_['gate']} has no skip atom")
    held_gates = {g["id"] for g in doc["gates"] if g.get("requires_undecoded")}
    ev_doc = {e["id"] for e in doc.get("events", [])}
    unresolved = collections.Counter()
    for s_ in [s for sect in ("edges", "locations", "skips", "confirmed_skips") for x in doc[sect] for s in
               _strings(x) + list(x.get("gate_requires") or ())] + [g.get("requires") for g in doc["gates"]]:
        for kind, ref in re.findall(r"\b(button|event|flag|barrier):([A-Za-z0-9_.]+)", s_ or ""):
            if kind == "button":
                ok = ref in ids["button"]
            elif kind == "event":
                ok = ref in ids["event"] or ref in ev_doc
            elif kind == "barrier":
                ok = ref in ids["barrier"]
            else:
                ok = ref in ids["event"] or ref in ev_doc or ref.startswith("global.") or \
                    (ref.endswith(".open") and (ref[:-5] in ids["button"] or ref[:-5] in held_gates)) or \
                    (ref.endswith(".destroyed") and ref[:-10] in ids["barrier"])
            if not ok:
                unresolved[f"{kind}:{ref}"] += 1
    bad += [f"unresolved atom {a_} ({n_} strings)" for a_, n_ in sorted(unresolved.items())]
    bad += [f"a number that could be a coordinate: {k} ({n})" for k, n in sorted(coordinate_like(doc).items())]
    return bad
