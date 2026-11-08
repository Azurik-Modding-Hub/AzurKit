"""``python -m devkit rando soak``: the randomizer's seed soak (Modkit's ``rando_soak.py``: REORG_PLAN §10.2b P4,
its Step R1.15; Step 4.13b).

Fills seeds 0 to ``--seeds`` - 1 on the shipped database under each of
Q293's three fixed settings profiles, plus as many seeds whose settings
are drawn from the seed, in ``--jobs`` spawned processes, and records P4:

- **the independent verify on every plan:** the plan file's placement
  (``plan_doc``, read back by ``load_plan``) solved again by ``verify`` on
  a second load of the database (victory, every location that isn't
  forfeitable, the trap gate with the known traps recomputed): 0 failures;
- **the ``FillError`` rate** after the fill's 20 attempts, per profile: at
  most 1 % for strict and default;
- **the trap gate's retry rate:** the attempts the trap gate refused, of
  all attempts (a plan's ``attempt`` + 1, a ``FillError``'s 20, or none
  when the fill's preflight refuses the settings, AZ-454), and the seeds
  it retried;
- **the cross-process check:** the first ``--hash-sample`` drawn seeds
  again in two pools under ``PYTHONHASHSEED`` 1 and 2 (the main run's
  workers take random hash seeds); every outcome (the plan's sha256, or
  the ``FillError`` message's) equals the main run's: 0 differences;
- **builds:** the first ``--builds`` seeds of each profile that have a
  plan, built by ``azurkit build --seed --share`` from the vanilla image
  (``--iso``, else the USA one AZURKIT_ISO or the user data folder names)
  into a temporary folder, the written image read back
  (``writer.read_back``) and then deleted; each build plans the soak's
  plan (its sha256) and reports ``logic_verified: true``.

Profiles (Q293): strict (ceiling 0, ``safe``), default (0, ``standard``;
D186) and max (4, ``frame_perfect``), each with ``dark_fire`` 1, which every
setting holds since D1061 (Modkit's strict had 2). Drawn settings: a stream
of the seed (sha256 of ``soak-settings``, NUL, the seed) picks the ceiling
and the movement tier uniformly, a toggle (on or off, evenly) on each
turnable skip with chance 1/8, and each item category kept vanilla with
chance 1/8; the seed difficulty stays 0 (Any, the default).

Writes ``--out DIR`` (new or empty): ``soak.json`` (every number, each
seed's outcome, each failure with its reason) and ``soak.txt`` (the table
it prints). Exits 0 when P4 is met and 1 naming each clause that isn't.
It runs locally only, never in CI. It prints no game bytes (hashes only).

    uv run --locked python -m devkit rando soak --out DIR [--seeds 1000] [--jobs 12] [--hash-sample 50] [--builds 10] [--iso ISO]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing
import os
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from azurkit.tools.randomizer.planner.fill import GENERATOR, FillError, Rng, db_digest, fill, settings_table, verify
from azurkit.tools.randomizer.planner.loader import load_database
from azurkit.tools.randomizer.planner.plan import dumps, load_plan, plan_doc
from azurkit.tools.randomizer.planner.settings import (
    CATEGORIES,
    DARK_FIRE,
    MOVEMENT_TIERS,
    SETTINGS_FORMAT,
    SKIP_CEILINGS,
    Settings,
    settings_from_table,
    share_encode,
    turnable,
)
from azurkit.tools.randomizer.planner.solver import Logic
from devkit.xemu.queue import BatchToken

PROFILES = {"strict": Settings(0, "safe", {}), "default": Settings(0, "standard", {}),   # Q293; default: D186
            "max": Settings(4, "frame_perfect", {})}
GROUPS = (*PROFILES, "drawn")
GATED = ("strict", "default")      # P4: FillError at most 1 %
FILL_ERROR_LIMIT = 0.01
TRAP = "the trap gate (D83(b))"    # in the reason of an attempt the trap gate refused
HASH_SEEDS = ("1", "2")
REPO = Path(__file__).resolve().parents[2]

_W: dict = {}


def drawn_settings(seed: int, skips) -> Settings:
    """The settings the soak draws for ``seed`` (the module docstring)."""
    rng = Rng(int.from_bytes(hashlib.sha256(f"soak-settings\0{seed}".encode()).digest()[:8], "big"))
    table = {"format": SETTINGS_FORMAT, "skip_ceiling": rng.choice(SKIP_CEILINGS),
             "movement_tier": rng.choice(MOVEMENT_TIERS), "dark_fire": DARK_FIRE,
             "skip_override": {sid: rng.below(2) == 1 for sid in sorted(skips)
                               if turnable(skips[sid]) and rng.below(8) == 0},
             "exclude_categories": [c for c in CATEGORIES if rng.below(8) == 0]}
    return settings_from_table(table, skips, f"drawn settings of seed {seed}")


def _init() -> None:
    """A worker's databases: one for the fill, one loaded again for the verify."""
    db = load_database()
    vdb = load_database()
    _W.update(db=db, logic=Logic(db), vdb=vdb, vlogic=Logic(vdb),
              skips={sid: s for sid, (_, s) in db.skips.items()})


def _settings(group: str, seed: int) -> Settings:
    return PROFILES[group] if group in PROFILES else drawn_settings(seed, _W["skips"])


def _run(group: str, seed: int, keep_doc: bool) -> dict:
    """One seed's outcome: its plan's sha256, attempts, trap-gate retries
    and verify problems, or its FillError's."""
    t0 = time.perf_counter()
    st = _settings(group, seed)
    rec = {"group": group, "seed": seed, "share": share_encode(st, _W["skips"]),
           "hash_seed": os.environ.get("PYTHONHASHSEED", "random")}
    try:
        f = fill(_W["logic"], str(seed), st)
    except FillError as exc:
        rec.update(outcome="FillError", key=hashlib.sha256(str(exc).encode()).hexdigest(),
                   attempts=len(exc.attempts), trap=sum(TRAP in a for a in exc.attempts),
                   reason=exc.attempts[-1] if exc.attempts else str(exc), items=exc.items)
    else:
        doc = plan_doc(f, _W["db"])
        plan = load_plan(json.loads(dumps(doc)), _W["vdb"])     # the plan file, as a reader gets it
        rec.update(outcome="plan", key=doc["sha256"], attempts=f.attempt + 1,
                   trap=sum(TRAP in a for a in f.failed), verify=verify(_W["vlogic"], plan.settings, plan.placement))
        if keep_doc:
            rec["doc"] = doc
    rec["seconds"] = round(time.perf_counter() - t0, 2)
    return rec


def _pool(jobs: list[tuple[str, int, bool]], n: int, hash_seed: str | None, label: str) -> list[dict]:
    """``jobs`` in ``n`` spawned workers under ``hash_seed`` (None: random),
    with a progress line every 5 %; one at a time while an xemu sitting
    waits for a slot (``BatchToken``, Step X.8)."""
    old = os.environ.get("PYTHONHASHSEED")
    if hash_seed is None:
        os.environ.pop("PYTHONHASHSEED", None)
    else:
        os.environ["PYTHONHASHSEED"] = hash_seed
    out, t0, step = [], time.perf_counter(), max(1, len(jobs) // 20)
    try:
        with ProcessPoolExecutor(min(n, len(jobs)), mp_context=multiprocessing.get_context("spawn"),
                                 initializer=_init) as pool, BatchToken("rando soak", min(n, len(jobs))) as tok:
            for f in tok.completed(pool, _run, jobs):
                out.append(f.result())
                if len(out) % step == 0 or len(out) == len(jobs):
                    spent = time.perf_counter() - t0
                    print(f"  {label}: {len(out)}/{len(jobs)} in {spent:.0f} s "
                          f"(about {spent / len(out) * (len(jobs) - len(out)):.0f} s left)", flush=True)
    finally:
        if old is None:
            os.environ.pop("PYTHONHASHSEED", None)
        else:
            os.environ["PYTHONHASHSEED"] = old
    return sorted(out, key=lambda r: (GROUPS.index(r["group"]), r["seed"]))


def _build(iso: Path, doc: dict, db, scratch: Path) -> dict:
    """``azurkit build --seed --share`` of ``doc``'s seed and share string
    into ``scratch``, the written image read back, then deleted. The build
    plans the seed itself (AzurKit's has no ``--plan``), so its plan must
    be ``doc``'s (the sha256 it prints)."""
    from azurkit.tools.randomizer.writer import read_back

    out = scratch / "soak.iso"
    t0 = time.perf_counter()
    try:
        p = subprocess.run([sys.executable, "-m", "azurkit", "build", "--iso", str(iso), "--out", str(out),
                            "--seed", doc["seed"], "--share", doc["share"]], cwd=REPO, capture_output=True, text=True)
        rec = {"seed": int(doc["seed"]), "plan": doc["sha256"], "exit": p.returncode}
        if p.returncode == 0:
            sha = re.search(r"sha256 ([0-9a-f]{64})", p.stdout)
            made = re.search(r"plan ([0-9a-f]{12});.*logic_verified: (true|false)", p.stdout)
            rec.update(iso_sha256_12=sha.group(1)[:12] if sha else None, built_plan=made and made.group(1),
                       logic_verified=made and made.group(2) == "true", read_back=read_back(out, doc["placement"], db))
        else:
            rec["error"] = [line for line in p.stderr.splitlines() if line.startswith("azurkit:")][:3]
    finally:
        out.unlink(missing_ok=True)
    rec["seconds"] = round(time.perf_counter() - t0, 1)
    rec["ok"] = (rec["exit"] == 0 and rec.get("built_plan") == doc["sha256"][:12] and rec.get("logic_verified") is True
                 and rec.get("read_back") == [])
    return rec


def _pct(n: int, d: int) -> str:
    return f"{100 * n / d:.1f} %" if d else "-"


def summarize(results: list[dict], builds: dict, cross: dict, args) -> dict:
    groups = {}
    for g in GROUPS:
        rs = [r for r in results if r["group"] == g]
        plans = [r for r in rs if r["outcome"] == "plan"]
        errors = [r for r in rs if r["outcome"] == "FillError"]
        attempts, trap = sum(r["attempts"] for r in rs), sum(r["trap"] for r in rs)
        groups[g] = {
            "settings": {**settings_table(PROFILES[g]), "share": rs[0]["share"] if rs else None}
            if g in PROFILES else None,
            "seeds": len(rs), "plans": len(plans), "fill_errors": len(errors),
            "fill_error_rate": len(errors) / len(rs) if rs else None,
            "fill_error_seeds": [r["seed"] for r in errors],
            "fill_error_reasons": _reasons(errors),
            "verify_failures": [{"seed": r["seed"], "problems": r["verify"]} for r in plans if r["verify"]],
            "attempts": attempts, "trap_gate_retries": trap, "trap_gate_retry_rate": trap / attempts if attempts else None,
            "seeds_trap_retried": sum(1 for r in rs if r["trap"]),
            "mean_attempts_per_plan": sum(r["attempts"] for r in plans) / len(plans) if plans else None,
            "seconds_per_seed": sum(r["seconds"] for r in rs) / len(rs) if rs else None,
            "builds": builds.get(g),
        }
    unmet = []
    failures = sum(len(groups[g]["verify_failures"]) for g in GROUPS)
    if failures:
        unmet.append(f"{failures} plans fail the independent verify")
    if cross["differences"]:
        unmet.append(f"{len(cross['differences'])} cross-process differences")
    for g in GATED:
        rate = groups[g]["fill_error_rate"]
        if rate is None or rate > FILL_ERROR_LIMIT:
            unmet.append(f"{g} FillError {_pct(groups[g]['fill_errors'], groups[g]['seeds'])} > 1 %")
    for g in PROFILES:
        done = sum(b["ok"] for b in builds.get(g, []))
        if done < args.builds:
            unmet.append(f"{g} built and read back {done} of {args.builds}")
    return {"groups": groups, "cross_process": cross, "p4_met": not unmet, "p4_unmet": unmet}


def _kind(reason: str) -> str:
    """An attempt's reason without its ids and counts: ``no safe proven
    spot for X``, or which of the verify's checks failed."""
    r = reason.split(": ", 1)[-1]
    if r.startswith("the verify: "):
        return "the verify: " + " + ".join(k for k, s in (("no victory", "does not hold"), ("locations missed",
                                           "never collected"), ("trap gate", TRAP)) if s in r)
    return re.sub(r"\d+", "N", re.sub(r"\S*[_/.]\S*", "X", r))


def _reasons(errors: list[dict]) -> dict[str, int]:
    """The FillErrors' last-attempt reasons (:func:`_kind`), counted."""
    out: dict[str, int] = {}
    for r in errors:
        out[_kind(r["reason"])] = out.get(_kind(r["reason"]), 0) + 1
    return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))


def table(summary: dict, meta: dict) -> list[str]:
    g = summary["groups"]
    lines = [f"rando soak: seeds 0-{meta['seeds'] - 1} per profile, {meta['jobs']} jobs, head {meta['head']}, "
             f"database {meta['db_digest'][:12]}, {meta['generator']}, load {meta['load_start']} -> {meta['load_end']}",
             f"{'profile':8} {'share':10} {'plans':>6} {'FillError':>16} {'verify fails':>12} {'attempts':>9} "
             f"{'trap-gate retries':>26} {'s/seed':>7} {'built+read back':>16}"]
    for name, s in g.items():
        b = s["builds"]
        built = "-" if b is None else f"{sum(x['ok'] for x in b)}/{meta['builds']}"
        share = s["settings"]["share"] if s["settings"] else "drawn"
        lines.append(f"{name:8} {share:10} {s['plans']:>6} "
                     f"{s['fill_errors']:>6} ({_pct(s['fill_errors'], s['seeds']):>7}) {len(s['verify_failures']):>12} "
                     f"{s['attempts']:>9} {s['trap_gate_retries']:>6} ({_pct(s['trap_gate_retries'], s['attempts']):>7}; "
                     f"{s['seeds_trap_retried']:>4} seeds) {s['seconds_per_seed']:>7.1f} {built:>16}")
    c = summary["cross_process"]
    lines.append(f"cross-process: {c['seeds']} drawn seeds under PYTHONHASHSEED {' and '.join(HASH_SEEDS)} "
                 f"(and the main run's random ones): {len(c['differences'])} differences")
    for name, s in g.items():
        if s["fill_error_reasons"]:
            lines.append(f"{name} FillErrors' last reasons: "
                         + "; ".join(f"{k} ({v})" for k, v in s["fill_error_reasons"].items()))
    w = meta["wall_seconds"]
    lines.append("wall time: " + ", ".join(f"{k} {v / 60:.1f} min" for k, v in w.items()))
    lines.append("P4 met" if summary["p4_met"] else "P4 not met: " + "; ".join(summary["p4_unmet"]))
    return lines


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="python -m devkit rando soak", description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True, help="a new or empty folder for soak.json and soak.txt")
    ap.add_argument("--seeds", type=int, default=1000)
    ap.add_argument("--jobs", type=int, default=12)
    ap.add_argument("--hash-sample", type=int, default=50)
    ap.add_argument("--builds", type=int, default=10)
    ap.add_argument("--iso", help="the vanilla image the builds read (default: the USA one AZURKIT_ISO or the user "
                                  "data folder names)")
    a = ap.parse_args(argv)
    out = Path(a.out)
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        ap.error(f"--out {out} is not a new or empty folder")
    if min(a.seeds, a.jobs) < 1 or min(a.hash_sample, a.builds) < 0 or a.hash_sample > a.seeds:
        ap.error("--seeds and --jobs at least 1; --hash-sample and --builds at least 0, the sample at most --seeds")
    iso = None
    if a.builds:
        from devkit.rando.ports import resolve_vanilla_iso
        iso = Path(a.iso) if a.iso else resolve_vanilla_iso()
    out.mkdir(parents=True, exist_ok=True)

    db = load_database()
    head = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=REPO, capture_output=True, text=True)
    meta = {"seeds": a.seeds, "jobs": a.jobs, "builds": a.builds, "head": head.stdout.strip() or None,
            "db_digest": db_digest(db), "generator": GENERATOR, "load_start": "%.1f %.1f %.1f" % os.getloadavg(),
            "wall_seconds": {}}
    t_all = time.perf_counter()

    t0 = time.perf_counter()
    jobs = [(g, s, g in PROFILES and a.builds > 0) for g in GROUPS for s in range(a.seeds)]
    results = _pool(jobs, a.jobs, None, "fills")
    meta["wall_seconds"]["fills"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    builds: dict[str, list[dict]] = {}
    with tempfile.TemporaryDirectory(prefix="rando-soak-") as scratch:
        for g in PROFILES:
            builds[g] = []
            for r in [r for r in results if r["group"] == g and r["outcome"] == "plan"][:a.builds]:
                b = _build(iso, r["doc"], db, Path(scratch))
                builds[g].append(b)
                print(f"  build {g} seed {b['seed']}: {'ok' if b['ok'] else 'FAILED'} ({b['seconds']} s)", flush=True)
    for r in results:
        r.pop("doc", None)
    meta["wall_seconds"]["builds"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    sample = [("drawn", s, False) for s in range(a.hash_sample)]
    main_keys = {(r["group"], r["seed"]): r["key"] for r in results}
    differences, seen = [], {}
    for h in HASH_SEEDS if sample else ():
        rs = _pool(sample, a.jobs, h, f"cross-process PYTHONHASHSEED={h}")
        seen[h] = sorted({r["hash_seed"] for r in rs})
        differences += [{"seed": r["seed"], "hash_seed": h, "main": main_keys[("drawn", r["seed"])], "this": r["key"]}
                        for r in rs if r["key"] != main_keys[("drawn", r["seed"])]]
    cross = {"seeds": len(sample), "hash_seeds_seen": seen, "differences": differences}
    meta["wall_seconds"]["cross-process"] = time.perf_counter() - t0
    meta["wall_seconds"]["total"] = time.perf_counter() - t_all
    meta["load_end"] = "%.1f %.1f %.1f" % os.getloadavg()

    summary = summarize(results, builds, cross, a)
    lines = table(summary, meta)
    (out / "soak.json").write_text(json.dumps({"meta": meta, **summary, "seeds": results}, indent=1) + "\n",
                                   encoding="utf-8")
    (out / "soak.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if summary["p4_met"] else 1
