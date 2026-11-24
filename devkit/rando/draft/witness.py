"""The witness gate's evidence (Step 4.76d; ``docs/RANDOMIZER_DB.md`` §4.10): one file a level,
``devkit/rando/draft/witness/<level>.json``, read by :mod:`.author` for a level whose authoring says
``sweep_gate = "witnessed"``.

The file holds, for each zone pair the reach engine flew in the game's own code (``reach-engine witness``'s
``azurik-l3-proof/1`` records, held: ``docs/REACH.md``), the least air rank a witness of it needs (0 without the
air shield; 1, 2 or 3 for at most 1, 2 or more flaps), thinned from those records (:func:`thin`), with what makes
the run the evidence: the level's ``zoning`` (the derived ``zones`` section's sha256, as a proof's claim names it),
the snapshot's label and meta sha12, the engine's three key sha12s (its L3 core, the core with the targeted pass,
the code that names a zone: ``devkit/reach/engine/cache.py``), the plans it read and the passes they flew.  A file of
another zoning is refused (:func:`check`), as an L3 proof is: a re-derive renumbers the zones, so its pairs would
name other places.  Ids, ranks and hashes only, no position or string.

Stdlib only for :func:`read` and :func:`check` (the authoring reads them); :func:`thin`'s defaults import the
engine's cache and the authoring's derived file.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

FORMAT = "azurik-sweep-witness/1"
FOLDER = Path(__file__).resolve().parent / "witness"
RANKS = range(4)          # an air rank: 0 without the shield, 1-3 by the flaps (``reach.engine.macros.min_rank``)
KEYS = ("core", "aim", "zones")


def _num(zid: str) -> int:
    return int(zid.rsplit(".Z", 1)[1])


def check(level: str, doc: dict, derived: dict) -> list[str]:
    """Why ``doc`` is no witness file for ``level`` as its derived file ``derived`` numbers its zones (empty: it
    is one)."""
    from azurkit.tools.randomizer.planner.proofs import zoning
    where = f"witness/{level}.json"
    if not isinstance(doc, dict) or doc.get("format") != FORMAT:
        return [f"{where}: not an {FORMAT} file"]
    if doc.get("level") != level:
        return [f"{where}: its level is {doc.get('level')!r}"]
    if doc.get("zoning") != zoning(derived):
        return [f"{where}: its zoning isn't the level's (a re-derive renumbered the zones): thin it again from an "
                "engine run on this zoning"]
    out = []
    snap = doc.get("snapshot")
    if not isinstance(snap, dict) or not snap.get("label") or not snap.get("meta_sha12"):
        out.append(f"{where}: names no snapshot label and meta sha12")
    keys = doc.get("keys")
    if not isinstance(keys, dict) or sorted(keys) != sorted(KEYS) or not all(isinstance(v, str) and v
                                                                            for v in keys.values()):
        out.append(f"{where}: names not the engine's three keys ({', '.join(KEYS)})")
    for name in ("plans", "passes"):
        if not isinstance(doc.get(name), list) or not doc[name]:
            out.append(f"{where}: names no {name}")
    if not isinstance(doc.get("pairs"), list):
        return out + [f"{where}: its pairs aren't a list"]
    zones = {z["id"] for z in derived.get("zones", ())}
    seen = set()
    for p in doc["pairs"]:
        ok = isinstance(p, list) and len(p) == 3 and p[0] in zones and p[1] in zones and p[0] != p[1] \
            and type(p[2]) is int and p[2] in RANKS and (p[0], p[1]) not in seen
        if not ok:
            out.append(f"{where}: pair {p!r} isn't two of the level's zones and an air rank 0-3, once")
            continue
        seen.add((p[0], p[1]))
    return out


def read(level: str, derived: dict, folder: Path | None = None) -> tuple[dict, list[str]]:
    """``({(from zone, to zone): least witnessed air rank}, [problems])`` from ``level``'s witness file in
    ``folder`` (default :data:`FOLDER`); a missing or refused file gives no pair and names why."""
    path = (FOLDER if folder is None else Path(folder)) / f"{level}.json"
    if not path.is_file():
        return {}, [f"sweep_gate is witnessed but witness/{level}.json is missing"]
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return {}, [f"witness/{level}.json doesn't read: {type(exc).__name__}"]
    problems = check(level, doc, derived)
    if problems:
        return {}, problems
    return {(a, b): r for a, b, r in doc["pairs"]}, []


def engine_keys() -> dict:
    """This checkout's three engine keys (``devkit/reach/engine/cache.py``): the L3 core's, the core with the
    targeted pass's (an aimed job's) and the zone naming code's sha12."""
    from devkit.reach.engine import cache
    return {"core": cache.core(cache.CORE_FILES), "aim": cache.core(cache.CORE_FILES + cache.AIM_FILES),
            "zones": cache.core(cache.ZONE_FILES)}


def thin(level: str, records: list[dict], plans: list[str], passes: list[str], keys: dict | None = None,
         derived: dict | None = None) -> dict:
    """A witness file's doc from one run's ``reach-engine witness`` records of ``level`` (``plans`` the plans it
    read, ``passes`` the passes they flew; ``keys`` the engine's three keys that ran it, by default
    :func:`engine_keys`, this checkout's; ``derived`` the level's derived file, by default this checkout's): each
    zone pair's least ``min_air``.  A record whose claim isn't two of the derived file's zones is left out: a node
    key, or a reach-model zone the export dropped (it keeps only the zones a derived edge touches), names no derived
    edge, so the gate never reads it (:func:`check` would refuse the file for it).  Records of another level, zoning
    or snapshot are refused (``ValueError``)."""
    if derived is None:
        from devkit.rando.draft.author import read_derived
        derived = read_derived(level)
    zones = {z["id"] for z in derived.get("zones", ())}
    zonings, snaps, best = set(), set(), {}
    for rec in records:
        claim = rec.get("claim") or {}
        if claim.get("kind") != "edge" or claim.get("level") != level:
            raise ValueError(f"a record that isn't an edge claim in {level}: {rec.get('ref')}")
        zonings.add(claim.get("zoning"))
        snap = (rec.get("start") or {}).get("snapshot") or {}
        snaps.add((snap.get("label"), snap.get("meta_sha12")))
        a, b = claim.get("from"), claim.get("to")
        if not (isinstance(a, str) and isinstance(b, str)) or a not in zones or b not in zones or a == b:
            continue
        r = claim.get("min_air")
        if type(r) is not int or r not in RANKS:
            raise ValueError(f"a record whose min_air isn't 0-3: {rec.get('ref')}")
        best[(a, b)] = min(best.get((a, b), r), r)
    if len(zonings) != 1 or len(snaps) != 1:
        raise ValueError(f"the records name {len(zonings)} zonings and {len(snaps)} snapshots: thin one run's")
    (zoning,), ((label, meta),) = zonings, snaps
    keys = engine_keys() if keys is None else dict(keys)
    return {"format": FORMAT, "level": level, "zoning": zoning, "snapshot": {"label": label, "meta_sha12": meta},
            "keys": {k: keys[k] for k in KEYS}, "plans": list(plans), "passes": list(passes), "records": len(records),
            "pairs": [[a, b, r] for (a, b), r in sorted(best.items(), key=lambda kv: (_num(kv[0][0]),
                                                                                     _num(kv[0][1])))]}


def text(doc: dict) -> str:
    """A witness file's text: its fields, then one pair a line."""
    lines = ["{"] + [f" {json.dumps(k)}: {json.dumps(v, sort_keys=True)}," for k, v in doc.items() if k != "pairs"]
    lines += [' "pairs": ['] + [f"  {json.dumps(p)}," for p in doc["pairs"]] + [" ]", "}"]
    return re.sub(r",\n( \])", r"\n\1", "\n".join(lines) + "\n")
