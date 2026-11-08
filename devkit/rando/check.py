"""``python -m devkit rando check [--db DIR] [--json]``: load the randomizer database (by default the shipped one,
``src/azurkit/tools/randomizer/data``), print what is open and every error, and exit 1 on an error (Modkit's ``rando
check``, Step 4.13c)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def report_lines(report) -> list[str]:
    """The human summary of a :class:`~azurkit.tools.randomizer.planner.loader.Report`."""
    s = report.summary
    lv, sk = s["levels"], s["skips"]

    def counts(d: dict) -> str:
        return ", ".join(f"{k} {v}" for k, v in d.items()) or "none"

    by_ceiling = s["skips_on_by_ceiling"]
    lines = [
        f"randomizer database, format v{s['format_version']}",
        f"levels: {len(lv['authored']) + len(lv['stubs'])} with a level file: {len(lv['authored'])} authored, "
        f"{len(lv['stubs'])} stubs; without one: {', '.join(lv['without_a_level_file']) or 'none'}",
        f"nodes {s['nodes']}, edges {s['edges']} (confidence: {counts(s['edges_by_confidence'])}), "
        f"live exits {s['live_exits']}; hand objects: {counts(s['hand_objects'])}",
        f"open: {s['todo_fields_total']} TODO fields ({counts(s['todo_fields'])})",
        f"open: {s['pool_locations_without_a_node_total']} pool locations with no node "
        f"({counts(s['pool_locations_without_a_node'])})",
        f"open: {s['undecoded_gates_open']} undecoded gates (generated requires null, no override_requires)",
        f"proven pool locations (D122): {counts(s['locations_proven'])}; "
        f"non-gem ones by realm (Q295): {counts(s['nongem_proven_by_realm'])}, "
        f"{sum(s['nongem_proven_by_realm'].values())} in all",
        f"skips: {sk['total']} ({counts(sk['by_status'])}); confirmed by: {counts(sk['by_confirmed'])}; "
        f"{s['skip_registry']['picks']} picks ({s['skip_registry']['batches']} batches, D275), "
        f"registry tag {s['skip_registry']['tag']}",
        f"skips on at skip_ceiling {', '.join(by_ceiling)} (no toggles): {', '.join(map(str, by_ceiling.values()))}",
        f"time-savers (D145: no logic edge, toggle or ceiling count): {s['time_savers']['total']} "
        f"({counts(s['time_savers']['by_level'])})",
    ]
    for name, st in s["settings"].items():
        lines.append(f"settings/{name}.toml: skip_ceiling {st['skip_ceiling']}, movement_tier {st['movement_tier']}, "
                     f"dark_fire {st['dark_fire']}, {st['overrides']} toggles: {st['skips_on']} skips on; "
                     f"share {st['share']}")
    route = s["route"]
    lines.append(f"route: {route['steps']} steps ({route['status'] or 'no route.toml'}); "
                 f"open: {len(route['open'])} references")
    lines += [f"  {item}" for item in route["open"]]
    lines.append(f"errors: {len(report.issues)}")
    lines += [f"  {issue}" for issue in report.issues]
    return lines


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="python -m devkit rando check", description=__doc__.split("\n\n")[0])
    p.add_argument("--db", metavar="DIR", help="a database folder (default: the shipped one)")
    p.add_argument("--json", action="store_true", help="the whole summary and every error, as JSON")
    args = p.parse_args(argv)
    from azurkit.tools.randomizer.planner.loader import DATA_DIR, check_database
    report = check_database(Path(args.db) if args.db else DATA_DIR)
    if args.json:
        print(json.dumps({**report.summary, "errors": [str(i) for i in report.issues]}, indent=1, sort_keys=True))
    else:
        print("\n".join(report_lines(report)))
    return 1 if report.issues else 0
