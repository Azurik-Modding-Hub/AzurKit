"""The movement sliders' tier table, ``src/azurkit/tools/randomizer/data/slider_tiers.json`` (D1066), from the
physics: each modelled movement slider's travel factor k at its :data:`POINTS` (the mean, over air ranks 0-3 at
landings 0, +2 and -2 m, of its travel over vanilla's: ``physics.Envelope.travel``, its flap timing searched in
full, as vanilla's is), and each tier's reach (``draft/tiers.toml``). The planner reads it (``movement.tier_of``),
so a plan under moved sliders runs no physics.

    uv run --locked python scripts/slider_tiers.py [--check] [--workers N]

``--check`` writes nothing and exits 1 naming each row that differs. Run it after a change to the physics or the
tiers (``tests/test_randomizer.py`` holds a point of each row to the physics).
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from azurkit.tools.randomizer import movement, physics  # noqa: E402
from azurkit.tools.randomizer.planner.settings import MOVEMENT_TIERS  # noqa: E402

FORMAT = "azurkit-slider-tiers/1"
GRID = tuple((rank, dh) for rank in range(4) for dh in (0.0, 2.0, -2.0))   # the air ranks and landings k averages
BEAM = 20
SCALE = (0.25, 0.5, 0.75, 0.9, 1.1, 1.25, 1.5, 2.0, 3.0)
POINTS = {   # each modelled slider's points in its own units, its vanilla value added (k 1)
    ("player_physics", "walk_speed_scale"): (*SCALE, 5.0),
    ("player_physics", "gravity"): (2.0, 4.9, 7.0, 8.5, 11.0, 12.5, 15.0, 20.0, 40.0),
    ("player_physics", "jump_speed_scale"): SCALE,
    ("player_physics", "air_control_scale"): (*SCALE, 5.0),
    ("player_physics", "flap_height_scale"): SCALE,
    ("player_physics", "wing_flap_ceiling_scale"): (*SCALE, 5.0),
    ("player_physics", "flap_below_peak_scale"): (0.25, 0.5, 1.5, 2.0, 3.0),
    ("player_physics", "flap_descent_fuel_cost_scale"): (0.0, 0.25, 0.5, 0.75, 1.5, 2.0),
    ("player_physics", "flap_entry_fuel_cost_scale"): (0.0, 0.25, 0.5, 0.75, 1.5, 2.0, 3.0, 5.0),
    ("air_shield_flaps", "air_shield_1_flaps"): (0, 2, 3, 4, 5, 6, 8),
    ("air_shield_flaps", "air_shield_2_flaps"): (0, 1, 3, 4, 5, 6, 8),
    ("air_shield_flaps", "air_shield_3_flaps"): (0, 1, 2, 3, 4, 6, 8, 10),
    ("fps_unlock", "target_fps"): (20.0, 45.0, 60.0, 90.0, 120.0),
}
OUT = movement.TABLE


def rows() -> dict[tuple[str, str], tuple[float, ...]]:
    """:data:`POINTS` with each slider's vanilla value, sorted; every slider on a :data:`movement.MODELLED` field."""
    out = {}
    for (pack, name), (fld, _) in sorted(physics.SLIDERS.items()):
        if fld in movement.MODELLED:
            out[pack, name] = tuple(sorted({*map(float, POINTS[pack, name]), _vanilla(pack, name)}))
    return out


def _vanilla(pack: str, name: str) -> float:
    fld, how = physics.SLIDERS[(pack, name)]
    if fld == "flaps":
        return float(physics.VANILLA.flaps[how])
    return getattr(physics.VANILLA, fld) / (how or 1.0)


def k(pack: str, name: str, value: float) -> float:
    """The travel factor of ``pack``'s ``name`` at ``value``, the rest vanilla, to 4 places (1 at vanilla's)."""
    if value == _vanilla(pack, name):
        return 1.0
    base = physics.envelope(physics.VANILLA, BEAM)
    moved = physics.envelope(physics.Movement.from_params({pack: {name: value}}), BEAM)
    ratios = [(moved.travel(rank, dh) or 0.0) / t for rank, dh in GRID if (t := base.travel(rank, dh))]
    return round(sum(ratios) / len(ratios), 4)


def _one(job: tuple[str, str, float]) -> tuple[str, str, float, float]:
    return (*job, k(*job))


def made(workers: int) -> dict:
    """The table, as :func:`movement.table` reads it."""
    jobs = [(pack, name, v) for (pack, name), vs in rows().items() for v in vs]
    jobs.sort(key=lambda j: -j[2] if physics.SLIDERS[j[:2]][0] == "flaps" else 0)   # the most flaps first: slowest
    with multiprocessing.get_context("spawn").Pool(max(1, workers)) as pool:
        got = {(p, n, v): kv for p, n, v, kv in pool.imap_unordered(_one, jobs)}
    reach = physics.tier_margins()
    sliders = {}
    for (pack, name), vs in rows().items():
        row = {"points": [[v, got[pack, name, v]] for v in vs]}
        if physics.SLIDERS[(pack, name)][0] == "flaps":
            row["whole"] = True
        sliders[f"{pack} {name}"] = row
    return {"format": FORMAT, "reach": {tier: reach[tier].reach for tier in MOVEMENT_TIERS}, "sliders": sliders}


def text(table: dict) -> str:
    """The file: one line a slider."""
    lines = [f' "format": {json.dumps(table["format"])},', f' "reach": {json.dumps(table["reach"])},', ' "sliders": {']
    keys = sorted(table["sliders"])
    lines += [f"  {json.dumps(key)}: {json.dumps(table['sliders'][key])}" + ("," if key != keys[-1] else "")
              for key in keys]
    return "{\n" + "\n".join(lines) + "\n }\n}\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="write nothing; exit 1 naming each row that differs")
    ap.add_argument("--workers", type=int, default=4, help="processes (4)")
    args = ap.parse_args(argv)
    table = made(args.workers)
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.is_file() else {}
    differs = [key for key in sorted(table["sliders"].keys() | old.get("sliders", {}).keys())
               if table["sliders"].get(key) != old.get("sliders", {}).get(key)]
    differs += ["reach"] * (table["reach"] != old.get("reach"))
    for key in differs:
        print(f"{'differs' if args.check else 'changed'}: {key}")
    if args.check:
        return 1 if differs or text(table) != OUT.read_text(encoding="utf-8") else 0
    OUT.write_text(text(table), encoding="utf-8")
    print(f"wrote: {OUT.relative_to(ROOT)} ({len(table['sliders'])} sliders)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
