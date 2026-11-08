"""The local L3 conformance corpus (Step X.10): every xemu replay's verdict, kept, so an engine change can be checked
against xemu offline.

Each replay of an L3 string in xemu (``xemu_oracle.py replay``, the sitting kit's ``l3_replay``,
``l3_certify.py``'s replays) appends a record to ``<store>/conformance.jsonl`` (:func:`record`): the
snapshot it started from (its label and metadata hash), the disc in the tray (its sha12 and the image's path), the
mode, the string (``l3.pads`` segments with the
camera as the f32 pairs L3 read, and the other writes at their ticks, a teleport's place request among them) and,
per tick, digests of both backends' observations (:mod:`devkit.sim.obs`: of the body centre, state and HP,
what a proof's replay must match (D170), and of the whole observation).  Its summary (:func:`summary`: pass or
fail, ticks, the first diverging tick) is coordinate-free; the record itself is private, in the store beside the
snapshots, because a teleport's request holds a position.

:func:`rerun` runs every record's string in L3 again from its kept snapshot and compares the new trace with
xemu's digests: a record that passed and now diverges is a regression, and a change in L3's own trace is
reported even where the record had failed.  A build's record runs on its own disc (the build's XBE, the game's
reads served from the image; AZ-380), never on vanilla's.  Both compare the CORE digests: AZ-389 changed the
whole observation's (the inventory hash starts past the day clock), so an older record's whole digests no longer
compare with a new trace.  ``l3_conformance.py`` is the command.
"""

from __future__ import annotations

import collections
import datetime
import hashlib
import json
import os
from pathlib import Path

from devkit.sim import l3, obs

FILE = "conformance.jsonl"


def corpus_path(store=None) -> Path:
    return l3.store(store) / FILE


def _first(a: list, b: list) -> int | None:
    """The first index where two digest lists differ (a shorter one differs where it ends), else None."""
    k = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), None)
    return k if k is not None or len(a) == len(b) else min(len(a), len(b))


def record(meta: dict, scene: bool, pads: list, rows: list, got: list[dict], *, store=None, disc=None) -> dict:
    """Append one replay (L3's ``rows`` from ``pads`` on the snapshot of ``meta``, xemu's ``got`` with their
    ``obs``) to the corpus, with ``disc``, the path of the image in the tray (outside the sandbox), beside the
    snapshot's ``iso_sha12``; returns its summary."""
    from devkit.sim.l3_search import segments, string_sha12
    rec = {"taken": datetime.datetime.now().isoformat(timespec="seconds"), "label": meta["label"],
           "meta_sha12": l3.meta_sha12(meta), "mode": "scene" if scene else "tick",
           "iso_sha12": meta.get("iso_sha12"), "disc": None if disc is None else str(disc),
           "string_sha12": string_sha12(pads, rows=rows), "taint": sorted(rows[-1].taint) if rows else [],
           "l3": [[obs.digest(r.obs, obs.CORE), obs.digest(r.obs)] for r in rows],
           "xemu": [[obs.digest(g["obs"], obs.CORE), obs.digest(g["obs"])] for g in got],
           "segments": segments(pads, rows),
           "writes": [[k, va, bytes(d).hex()] for k, r in enumerate(rows) for va, d in r.writes[1:]]}
    core = _first([c for c, _ in rec["l3"]], [c for c, _ in rec["xemu"]])
    rec.update(passed=core is None, divergence=core,
               obs_divergence=_first([f for _, f in rec["l3"]], [f for _, f in rec["xemu"]]))
    fd = os.open(corpus_path(store), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    return summary(rec)


def read(store=None) -> list[dict]:
    p = corpus_path(store)
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln] if p.exists() else []


def summary(rec: dict) -> dict:
    """A record's coordinate-free summary."""
    return {k: rec[k] for k in ("taken", "label", "meta_sha12", "mode", "string_sha12", "passed", "divergence",
                                "obs_divergence", "taint")} | {"ticks": len(rec["xemu"]), "l3_ticks": len(rec["l3"])}


def _disc(sha12: str, paths, hashed: dict) -> str | None:
    """The first of ``paths`` that is the image ``sha12`` names, each hashed once (``hashed``)."""
    for p in dict.fromkeys(str(p) for p in paths if p):
        if p not in hashed:
            hashed[p] = None
            if Path(p).is_file():
                with open(p, "rb") as f:
                    hashed[p] = hashlib.file_digest(f, "sha256").hexdigest()[:12]
        if hashed[p] == sha12:
            return p
    return None


def rerun(xbe: bytes, *, store=None, workers: int = 0, only=(), discs=()) -> list[dict]:
    """Every record's string (or those of the snapshots ``only`` names) run again in L3 from its kept snapshot
    (in this process, or on a :class:`~devkit.reach.l3_pool.Pool` of ``workers`` per snapshot): per record its
    summary, whether it passes now and where it diverges from xemu now, and the first tick where L3's own trace
    changed (``l3_changed_at``; None: unchanged).  ``xbe`` is vanilla's; a snapshot taken with another disc in the
    tray (its ``iso_sha12``) runs on that image's XBE with the game's reads served from it: the path its records
    kept, or one of ``discs`` (images moved since) that hashes the same (AZ-380).  A record whose snapshot or disc
    is gone says so (``missing``)."""
    from devkit.sim.ports import VANILLA_ISO_SHA256
    from devkit.sim.ports import read_file
    from devkit.reach.l3_pool import Pool, Worker, trace
    recs = [r for r in read(store) if not only or r["label"] in only]
    hashed: dict[str, str | None] = {}
    by_label: dict[str, list[int]] = collections.defaultdict(list)
    for i, r in enumerate(recs):
        by_label[r["label"]].append(i)
    out: list[dict | None] = [None] * len(recs)
    for label, ix in by_label.items():
        path = l3.snapshot_path(label, store)
        if not path.exists():
            for i in ix:
                out[i] = {**summary(recs[i]), "missing": "its snapshot is no longer in the store"}
            continue
        sha12, disc, run_xbe = l3.read_meta(path).get("iso_sha12"), None, xbe
        if sha12 not in (None, VANILLA_ISO_SHA256[:12]):
            kept = [recs[i].get("disc") for i in ix]
            if (disc := _disc(sha12, [*discs, *kept], hashed)) is None:
                where = ", ".join(dict.fromkeys(p for p in kept if p)) or "no path kept"
                for i in ix:
                    out[i] = {**summary(recs[i]), "missing": f"its disc {sha12} is gone ({where}): pass --disc"}
                continue
            run_xbe = read_file(disc, "default.xbe")
        tasks = [(recs[i]["mode"] == "scene", recs[i]["segments"], recs[i]["writes"]) for i in ix]
        if workers:
            with Pool(label, run_xbe, store=store, workers=workers, name="l3 conformance", disc=disc) as pool:
                traces = pool.map(trace, tasks)
        else:
            w = Worker(label, None if store is None else str(store), run_xbe, None, disc)
            traces = [trace(w, *t) for t in tasks]
        for i, (rows, err) in zip(ix, traces):
            r = recs[i]
            core = _first([x[3] for x in rows], [c for c, _ in r["xemu"]])
            out[i] = {**summary(r), "error": err, "passes_now": core is None and err is None, "divergence_now": core,
                      "l3_changed_at": _first([x[3] for x in rows], [c for c, _ in r["l3"]])}
    return out


def report(results: list[dict]) -> dict:
    """Counts over :func:`rerun`'s results: records, passing then and now, regressions (passed, now not), traces
    L3 changed, records whose snapshot is gone."""
    live = [r for r in results if "missing" not in r]
    return {"records": len(results), "missing": len(results) - len(live),
            "passed": sum(r["passed"] for r in live), "passes_now": sum(r["passes_now"] for r in live),
            "regressions": sum(r["passed"] and not r["passes_now"] for r in live),
            "l3_changed": sum(r["l3_changed_at"] is not None for r in live)}
