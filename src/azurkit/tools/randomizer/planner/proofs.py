"""L3 proof records (Step X.7, D170): what a ``proven = { by = "l3", ref }`` mark, or a skip's ``confirmed = { by =
"l3", ref }`` (Step R1.8g, D177), resolves to.

``data/proofs.jsonl`` holds one record per line, sorted by ``ref``.  A record is
coordinate-free and RAM-free: the claim (a location, an edge's zones, or a skip with its kit and the most flaps it
made in one jump), the start as a recipe (the loadvm tag,
the R7 hop, the R2 kit, an R6 teleport named by its reach-model sample and the place struct's sha12, the settle
ticks) on a snapshot named by its metadata hash, the input string itself (run-length: the stick, the buttons, the
camera as the exact f32 pair the input builder read), the L3 mode, the outcome (states, zones visited, HP, whether a
spot's way back was walked too), the robustness under jitter and the xemu replay that matched it tick for tick (a
skip's since D277, Step R1.31: the simulator's run confirms it, so its replay may be ``{"rule": "D277"}``, none).
``ref`` is ``<sitting>/<string sha12>@<snapshot meta sha12>``.  The loader resolves every ``l3`` mark to its record
and checks the claim names the same location or edge; ``rando author`` refuses a ``[[probed]]`` walk whose record's
``zoning`` (:func:`zoning`: the sha256 of the level's derived ``zones`` section, which a re-derive renumbers and
``rando author`` never touches) isn't the level's current one (``python -m devkit reach l3-certify recheck`` re-runs
the strings and re-zones them).  A record whose start snapshot is gone is ``retired`` (a string saying why, D1175):
it stays as history and its marks still resolve, but ``recheck`` passes over it.  The records stay out of
``db_digest``: evidence never changes a plan.  Stdlib only: the sim writes none of this (devkit's ``l3-certify``
does) and the planner stays pure.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

FORMAT = "azurik-l3-proof/1"
FILE = "proofs.jsonl"
REF = re.compile(r"[^/\s@]+/[0-9a-f]{12}@[0-9a-f]{12}")
_TRIPLE = re.compile(r"\[\s*-?\d+\.\d+\s*,\s*-?\d+\.\d+\s*,\s*-?\d+\.\d+\s*\]")    # a coordinate: never in a record
INPUT_CLASSES = ("analog-ram", "fifo-cardinal")
MODES = ("tick", "scene")


def ref_of(sitting: str, string_sha12: str, meta_sha12: str) -> str:
    return f"{sitting}/{string_sha12}@{meta_sha12}"


def zoning(derived: dict) -> str:
    """The sha256 of a derived level's ``zones`` section: the zone numbering a record's claim was made under."""
    import hashlib
    return hashlib.sha256(json.dumps(derived.get("zones", []), sort_keys=True).encode()).hexdigest()


def record_problem(rec) -> str | None:
    """Why ``rec`` is no proof record, else None."""
    if not isinstance(rec, dict) or rec.get("format") != FORMAT:
        return f"not a {FORMAT} record"
    ref = rec.get("ref")
    if not isinstance(ref, str) or not REF.fullmatch(ref):
        return "ref is not <sitting>/<string sha12>@<snapshot meta sha12>"
    claim, start, string, outcome, replay = (rec.get(k) for k in ("claim", "start", "string", "outcome", "replay"))
    if not all(isinstance(x, dict) for x in (claim, start, string, outcome, replay)):
        return "claim, start, string, outcome and replay must be tables"
    kind = claim.get("kind")
    if kind == "location":
        if not isinstance(claim.get("id"), str) or claim["id"].count("/") != 2:
            return "a location claim names its generated id"
        if outcome.get("returned") is not True:
            return "a location proof walks back to where it started (D122: reach and come back)"
    elif kind == "edge":
        if not (isinstance(claim.get("from"), str) and isinstance(claim.get("to"), str)):
            return "an edge claim names its from and to zones (or nodes)"
    elif kind == "skip":
        if not (isinstance(claim.get("id"), str) and "." in claim["id"] and isinstance(claim.get("flaps"), int)):
            return "a skip claim names its tricks.toml id and the most flaps it made in one jump (D183)"
    else:
        return "claim.kind is location, edge or skip"
    if not isinstance(claim.get("level"), str) or not isinstance(claim.get("kit"), dict):
        return "a claim names its level and kit"
    if not all(isinstance(k, str) and type(v) is int and v >= 0 for k, v in claim["kit"].items()):
        return "a claim's kit maps counters to non-negative integers"
    if not re.fullmatch(r"[0-9a-f]{64}", str(claim.get("zoning", ""))):
        return "claim.zoning is the sha256 of the level's derived zones section"
    snap = start.get("snapshot")
    if not isinstance(snap, dict) or not re.fullmatch(r"[0-9a-f]{12}", str(snap.get("meta_sha12", ""))):
        return "start.snapshot.meta_sha12 is the snapshot's metadata hash"
    if not isinstance(start.get("setup"), list):
        return "start.setup is the set-up recipe (a list of steps)"
    if not (re.fullmatch(r"[0-9a-f]{12}", str(string.get("sha12", ""))) and isinstance(string.get("ticks"), int)
            and string.get("input") in INPUT_CLASSES and isinstance(string.get("segments"), list)
            and all(isinstance(s, dict) and isinstance(s.get("n"), int) for s in string["segments"])):
        return "string holds sha12, ticks, input class and run-length segments"
    if ref != ref_of(ref.split("/", 1)[0], string["sha12"], snap["meta_sha12"]):
        return "ref doesn't name the string's sha12 and the snapshot's meta sha12"
    if rec.get("l3", {}).get("mode") not in MODES:
        return "l3.mode is tick or scene"
    if outcome.get("reached") is not True or not (replay.get("equal") is True or (
            kind == "skip" and replay.get("rule") == "D277")):
        return ("a proof's outcome reached and its xemu replay equal are both true (a skip's replay is owed no more: "
                "replay.rule D277)")
    if _TRIPLE.search(json.dumps(rec)):
        return "a record holds no coordinate (a float triple)"
    return None


def read_proofs(path: Path) -> tuple[dict[str, dict], list[tuple[int, str]]]:
    """({ref: record}, [(line, problem)]) of a ``proofs.jsonl``; a missing file is empty."""
    out: dict[str, dict] = {}
    problems: list[tuple[int, str]] = []
    if not path.is_file():
        return out, problems
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except ValueError as exc:
            problems.append((n, f"not JSON: {exc}"))
            continue
        why = record_problem(rec)
        if why:
            problems.append((n, why))
        elif rec["ref"] in out:
            problems.append((n, f"a second record for {rec['ref']}"))
        else:
            out[rec["ref"]] = rec
    return out, problems


def write_proofs(path: Path, records: dict[str, dict]) -> None:
    """Write ``records`` as ``proofs.jsonl``, one per line, sorted by ref."""
    lines = [json.dumps(records[r], sort_keys=True, separators=(",", ":")) for r in sorted(records)]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def claim_matches(rec: dict, *, location: str | None = None, level: str | None = None,
                  from_names: set | None = None, to_names: set | None = None, skip: str | None = None) -> str | None:
    """Why the record's claim isn't the mark's: a location id, an edge of ``level`` whose from and to are among
    the nodes' names (the node id and its zone anchors), or a skip id (D177: a skip ``confirmed`` by an L3 string
    xemu replayed); None when it matches."""
    c = rec["claim"]
    if skip is not None:
        if c["kind"] != "skip" or c["id"] != skip:
            return f"the record claims {c['kind']} {c.get('id') or (c.get('from'), c.get('to'))}, not skip {skip}"
        return None
    if location is not None:
        if c["kind"] != "location" or c["id"] != location:
            return f"the record claims {c['kind']} {c.get('id') or (c.get('from'), c.get('to'))}, not {location}"
        return None
    if c["kind"] != "edge" or c["level"] != level:
        return f"the record claims {c['kind']} {c.get('id') or (c.get('from'), c.get('to'))} in {c['level']}"
    if c["from"] not in (from_names or ()) or c["to"] not in (to_names or ()):
        return f"the record's walk {c['from']} -> {c['to']} isn't this edge's node pair"
    return None
