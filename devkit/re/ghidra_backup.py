"""``python -m devkit re ghidra-backup list|restore NAME|prune``:
``ghidra-apply``'s backups of a Ghidra project, in ``ghidra-backups/``
beside the folder that holds its ``.gpr`` (Modkit's, ported in Step
4.11d2; :mod:`.ghidra_project` does the work)."""

from __future__ import annotations

import argparse
import json
import sys

from . import ghidra_project as gp


def main(argv: list[str]) -> int:
    """Exit 0 done, 2 refused (nothing done)."""
    p = argparse.ArgumentParser(
        prog="python -m devkit re ghidra-backup",
        description="ghidra-apply's backups live in ghidra-backups/ beside the folder that holds the project's .gpr. "
                    "restore moves the project as it is aside into a backup of its own (it never deletes), then "
                    "puts the named backup back; prune keeps the newest one (--keep N) and the last verified "
                    "apply's backup, its undo.")
    p.add_argument("action", choices=["list", "restore", "prune"])
    p.add_argument("name", nargs="?", default=None, help="restore: the backup (from list)")
    p.add_argument("--project", default=None,
                   help="the project's .gpr; required for restore and prune; list's default: the one "
                        "ghidra-serve's last start used")
    p.add_argument("--keep", type=int, default=None,
                   help="prune: how many to keep (default 1), besides as many verified applies' backups")
    args = p.parse_args(argv)
    try:
        project = gp.project_arg(args.project, writes=args.action != "list")
        found = gp.backups(project)
        if args.action == "list":
            print(f"ghidra-backup: {len(found)} backup(s) of {project} in {gp.backups_dir(project)}")
            for d, info in found:
                r = (json.loads((d / "result.json").read_text(encoding="utf-8"))
                     if (d / "result.json").is_file() else None)
                print(f"  {d.name}  {info['kind']}" + (
                    "" if r is None else f"; plan {r['plan_sha256'][:12]}: "
                    + ("applied and verified" if r["verified"] else "failed, put back" if r["restored"]
                       else "failed, NOT put back" if "restore_failed" in r else "failed, nothing written")))
        elif args.action == "restore":
            saved = next((d for d, _ in found if d.name == args.name), None)
            if saved is None:
                raise gp.ApplyError(f"no backup named {args.name!r} (ghidra-backup list)")
            aside = gp.restore(project, saved)
            print(f"ghidra-backup: restored {saved.name} into {project}"
                  + (f"; the project it replaced is backup {aside.name}" if aside else ""))
        else:
            gone = gp.prune(project, gp.KEEP if args.keep is None else args.keep)
            print(f"ghidra-backup: removed {len(gone)} backup(s)"
                  + (f": {', '.join(d.name for d in gone)}" if gone else ""))
    except (gp.ApplyError, gp.ProjectError) as exc:
        print(f"ghidra-backup: {exc}", file=sys.stderr)
        return 2
    return 0
