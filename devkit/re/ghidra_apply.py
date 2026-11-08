"""``python -m devkit re ghidra-apply --plan P [--apply --plan-sha256 SHA]``
(D90): a reviewed plan dry-run on a copy of a Ghidra project, or written
into the closed project, with a backup, a read-only verify on a copy and an
automatic restore (Modkit's, ported in Step 4.11d2).

The plan is a JSON list of lines that ``ghidra_scripts/ApplyPlan.java``
runs under analyzeHeadless: ``rename`` (a function), ``rename_label``,
``comment``, ``delete_equate``, ``delete_category`` and
``create_function`` (``ghidra-sync --emit-plan`` writes renames and
creates). Success is read from the run's marker lines, never its exit code.
The backups are :mod:`.ghidra_project`'s.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import os
import re
import shlex
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path

from .ghidra_project import (
    KEEP, ApplyError, LockState, ProjectError, _dump, _load, _refuse_open, backup, lock_state, manifest,
    project_arg, prune, restore)

__all__ = ["LOCKS", "apply_plan", "dry_run", "lock_text", "main", "plan_sha256"]

_TIMEOUT = 600  # seconds one headless run may take
# ApplyPlan.java's println lines in analyzeHeadless's output
_MARK = re.compile(r"^INFO\s+ApplyPlan\.java> (AZ(?:PLAN|VERIFY): .*?)(?: \(GhidraScript\))?\s*$", re.M)
Runner = Callable[[Path, str, Path], str]  # (gpr, mode, plan) -> its output


def plan_sha256(plan: Path) -> str:
    """The sha256 the dry run prints and ``--apply --plan-sha256`` names
    (D103; until 2026-10-11 the owner approved it as ``apply plan <sha256>``)."""
    return hashlib.sha256(plan.read_bytes()).hexdigest()


def _marks(out: str) -> list[str]:
    """ApplyPlan.java's marker lines, in order. It prints plan text
    JSON-quoted, so no plan can start a line of its own."""
    return _MARK.findall(out)


def _ok(out: str, final: str) -> bool:
    """Whether a run printed ``final`` and no script error: read from the
    log, never the exit code (analyzeHeadless exits 0 when a script
    throws [verified 2026-10-10, writes lane])."""
    return "SCRIPT ERROR" not in out and any(m.startswith(final) for m in _marks(out))


def _why(out: str) -> str:
    """A failed run's result marker and its first error lines."""
    final = [m for m in _marks(out) if not m.startswith(("AZPLAN: pending", "AZPLAN: in effect"))]
    errors = [line.strip() for line in out.splitlines() if "ERROR" in line][:4]
    return "; ".join(final[-1:] + errors) or "no ApplyPlan result in the log"


def _headless(program: str, work: Path) -> Runner:
    """``ApplyPlan.java <mode> <plan>`` on a project, run by the
    ``.tools`` Ghidra (:func:`.ghidra_serve.tools_dir`) with its settings, cache and temp in
    ``work``; ``-readOnly`` unless the mode is ``apply``. Made before any
    backup, so it refuses there a missing analyzeHeadless and a ``work``
    path Ghidra can't use.

    Each run is a process group of its own, ended whole as the run returns,
    times out or is interrupted: the JVM runs under ``analyzeHeadless`` and
    ``launch.sh``, so killing the first alone would leave it writing."""
    from .ghidra_serve import _CHILDREN, SCRIPTS, _end, headless_exe
    exe = headless_exe()
    if not exe.is_file():
        raise ApplyError(f"no {exe}: run `uv run bootstrap.py --with re` in the main checkout")
    # launch.sh/.bat split the JVM options at spaces; Ghidra refuses a project under a '.' folder
    if any(c.isspace() for c in str(work)) or any(p.startswith(".") for p in work.parts):
        raise ApplyError(f"Ghidra can't use a work folder with whitespace or a '.' folder in its "
                         f"path: {work}")
    detach = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
              if os.name == "nt" else {"start_new_session": True})

    def run(gpr: Path, mode: str, plan: Path) -> str:
        state = work / f"ghidra-{mode}"
        for sub in ("tmp", "home", "settings", "cache"):
            (state / sub).mkdir(parents=True, exist_ok=True)
        options = [f"-Djava.io.tmpdir={state / 'tmp'}", f"-Duser.home={state / 'home'}",
                   f"-Dapplication.settingsdir={state / 'settings'}",
                   f"-Dapplication.cachedir={state / 'cache'}",
                   f"-Dghidra.user.scripts.dir={state / 'home'}"]
        argv = [str(exe), str(gpr.parent), gpr.stem, "-process", program, "-noanalysis",
                *([] if mode == "apply" else ["-readOnly"]),
                "-scriptPath", str(SCRIPTS),
                "-postScript", "ApplyPlan.java", mode, str(plan)]
        with subprocess.Popen(argv, env={**os.environ, "GHIDRA_HEADLESS_JAVA_OPTIONS": " ".join(options)},
                              stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, encoding="utf-8", errors="replace", **detach) as proc:
            _CHILDREN[proc.pid] = proc
            try:
                return proc.communicate(timeout=_TIMEOUT)[0]
            except subprocess.TimeoutExpired:
                pass
            finally:  # the whole group, the JVM included (ghidra-serve's stop), also on Ctrl-C
                _end(proc.pid, 0)
            proc.communicate()  # ends Windows' reader threads, as subprocess.run does
            raise ApplyError(f"analyzeHeadless ({mode}) ran over {_TIMEOUT} s")
    return run


def _work(work_root: Path | None) -> tempfile.TemporaryDirectory:
    """A temporary folder for one verb's copies and Ghidra settings, under
    ``ghidra-apply/`` beside the serves' state in the user cache."""
    if work_root is None:
        from .ghidra_serve import state_root
        work_root = state_root().parent / "ghidra-apply"
    work_root.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(dir=work_root, prefix="run-", ignore_cleanup_errors=True)


def _copy_of(gpr: Path, folder: Path) -> Path:
    """A fresh copy, guarded by the project's fingerprint before and after
    (2.13c's clone path: it may be made while a Ghidra holds the project)."""
    from .ghidra_serve import ServeError, ensure_copy
    try:
        return ensure_copy(gpr, folder)[0]
    except ServeError as exc:
        raise ApplyError(str(exc)) from None


def dry_run(gpr: Path, plan: Path, *, runner: Runner | None = None, program: str = "default.xbe",
            work_root: Path | None = None) -> dict:
    """``ghidra-apply --plan P``: the plan run on a copy of the project.
    Returns each line's state (pending, with what it would overwrite, or in
    effect), the plan's sha256 for ``--apply``, and the lock."""
    data = plan.read_bytes()
    with _work(work_root) as tmp:
        work = Path(tmp)
        run = runner or _headless(program, work)
        (work / "plan.json").write_bytes(data)
        out = run(_copy_of(gpr, work / "dry"), "dry", work / "plan.json")
    if not _ok(out, "AZPLAN: DRY "):
        raise ApplyError(f"the dry run failed: {_why(out)}")
    return {"plan_sha256": hashlib.sha256(data).hexdigest(), "lines": _marks(out),
            "lock": lock_state(gpr)}


@contextlib.contextmanager
def _ctrl_c_once():
    """Ctrl-C stops an apply once, and is ignored after that and from
    ``hold()`` on, so it never stops the run's kill or a restore half way:
    ``uv run`` passes the terminal's Ctrl-C on again ~0.2 s later
    [verified 2026-10-10, Step 2.13c]. Only where Python's own Ctrl-C
    handler is set (the main thread)."""
    mine = (threading.current_thread() is threading.main_thread()
            and signal.getsignal(signal.SIGINT) is signal.default_int_handler)

    def hold(*_):
        if mine:
            signal.signal(signal.SIGINT, signal.SIG_IGN)

    def first(*_):
        hold()
        raise KeyboardInterrupt

    if mine:
        signal.signal(signal.SIGINT, first)
    try:
        yield hold
    finally:
        if mine:
            signal.signal(signal.SIGINT, signal.default_int_handler)


def _undo(gpr: Path, saved: Path, result: dict) -> None:
    """After a failed, timed-out or interrupted apply, whose Ghidra has
    ended: put the backup back unless the project is byte-identical to it.
    Never while a Ghidra holds the project (one that outlived its kill, or
    one opened since, may still write): ``restore_failed`` says why."""
    try:
        _refuse_open(gpr, "not put back")
        try:
            same = manifest(gpr) == _load(saved / "manifest.json")["files"]
        except ProjectError:  # torn: the restore moves what is left aside
            same = False
        if not same:
            aside = restore(gpr, saved)
            result["restored"] = True
            if aside:
                result["replaced"] = str(aside)
    except (ApplyError, ProjectError, OSError) as exc:
        result["restore_failed"] = str(exc)


def apply_plan(gpr: Path, plan: Path, approved_sha256: str, *, runner: Runner | None = None,
               program: str = "default.xbe", work_root: Path | None = None,
               keep: int = KEEP) -> dict:
    """``ghidra-apply --apply`` (D90): write the reviewed plan into
    the closed project.

    Raises, before any backup, on a plan whose sha256 is not the approved
    one, a project a Ghidra holds, and a Ghidra it can't run. Then a
    :func:`backup`, the apply, and a read-only verify on a copy of the
    result. From the backup on, a failure, a timeout or Ctrl-C ends the
    run's Ghidra, puts the backup back byte-identical (Q205) and returns
    (``verified`` false, ``why``; ``restore_failed`` when it could not be
    put back). Success is read from the run's markers. The plan, both logs
    and ``result.json`` stay in the backup folder. A verified apply then
    prunes all but the newest ``keep`` backups, never its own; a failed
    one prunes none, so the last verified apply's backup still undoes it,
    and :func:`prune` keeps that one too (D103: one undo level)."""
    data = plan.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    if approved_sha256.strip().lower() != sha:
        raise ApplyError(f"the plan's sha256 is {sha}, not the approved {approved_sha256}: nothing done")
    _refuse_open(gpr, "nothing done")
    with _work(work_root) as tmp, _ctrl_c_once() as hold:
        work = Path(tmp)
        run = runner or _headless(program, work)
        t0 = time.monotonic()
        saved = backup(gpr)
        (saved / "plan.json").write_bytes(data)
        result = {"project": str(gpr), "plan_sha256": sha, "backup": str(saved), "applied": False,
                  "verified": False, "restored": False}
        ran, stop = False, None
        try:
            _refuse_open(gpr, f"nothing written; backup {saved.name} kept")
            ran = True
            out = run(gpr, "apply", saved / "plan.json")
            (saved / "apply.log").write_text(out, encoding="utf-8")
            result["lines"] = _marks(out)
            result["applied"] = _ok(out, "AZPLAN: APPLIED ") and "Save succeeded" in out
            if result["applied"]:
                out = run(_copy_of(gpr, work / "verify"), "verify", saved / "plan.json")
                (saved / "verify.log").write_text(out, encoding="utf-8")
                result["verified"] = _ok(out, "AZVERIFY: OK ")
            if not result["verified"]:
                result["why"] = _why(out)
        except BaseException as exc:  # an error, the timeout or Ctrl-C; the run's Ghidra has ended
            result["why"] = ("interrupted (Ctrl-C)" if isinstance(exc, KeyboardInterrupt)
                             else str(exc) or type(exc).__name__)
            stop = None if isinstance(exc, (Exception, KeyboardInterrupt)) else exc
        hold()
        if ran and not result["verified"]:
            _undo(gpr, saved, result)
        result["seconds"] = round(time.monotonic() - t0, 1)
        _dump(saved / "result.json", result)
        if stop is not None:
            raise stop
        result["pruned"] = [d.name for d in prune(gpr, keep, protect=(saved,))] if result["verified"] else []
    return result


LOCKS = {"free": "free (no Ghidra has it open)", "held": "held by a Ghidra",
         "stale": "stale (lock files a Ghidra that died left)",
         "unknown": "unknown (no passive lock probe on Windows)"}


def lock_text(lock: LockState) -> str:
    return LOCKS[lock.state] + (f" (pid {lock.pid})" if lock.pid else "")


def main(argv: list[str]) -> int:
    """Exit 0 applied (or the dry run), 1 failed with the project as before
    (put back from its backup, or never written), 2 refused (nothing done),
    3 failed and not put back."""
    from .ghidra_serve import ServeError

    p = argparse.ArgumentParser(
        prog="python -m devkit re ghidra-apply",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Without --apply: runs the plan on a COPY of the project and prints each line (pending, with\n"
            "what it would overwrite, or in effect) and the plan's sha256, which --apply names. With\n"
            "--apply and that sha256: refuses while a Ghidra holds the project, backs it up into\n"
            "ghidra-backups/ beside its folder, writes the plan headlessly, verifies it read-only on a\n"
            "copy, and puts the backup back if anything failed (D90). Plan lines (a JSON list): rename\n"
            "(va, from, to; a function), rename_label (va, from, to; a label), comment (va, kind, text),\n"
            "delete_equate (name), delete_category (path), create_function (va[, name]).\n"
            "Exit 0 applied, 1 failed (the project as before), 2 refused (nothing done), 3 failed and\n"
            "not put back."),
        epilog=(
            "Examples:\n"
            "  python -m devkit re ghidra-apply --plan plan.json\n"
            "  python -m devkit re ghidra-apply --apply --plan plan.json --plan-sha256 <sha256> \\\n"
            "      --project '<folder>/Azurik Ghidra.gpr'"))
    p.add_argument("--plan", required=True, help="the plan (a JSON list of lines)")
    p.add_argument("--project", default=None,
                   help="the project's .gpr; required with --apply; the dry run's default: the one ghidra-serve's "
                        "last start used")
    p.add_argument("--apply", action="store_true", help="write the plan into the project (needs --plan-sha256; "
                                                         "Ghidra closed)")
    p.add_argument("--plan-sha256", default=None, help="the plan's sha256, as its dry run printed it")
    args = p.parse_args(argv)
    try:
        project = project_arg(args.project, writes=args.apply)
        plan = Path(args.plan).expanduser()
        if not args.apply:
            d = dry_run(project, plan)
            print(f"ghidra-apply: dry run of {plan} on a COPY of {project}")
            for line in d["lines"]:
                print(f"  {line}")
            print(f"  the project's lock: {lock_text(d['lock'])}")
            print(f"plan sha256: {d['plan_sha256']}")
            print(f"To write it, once no Ghidra holds the project:\n"
                  f"  python -m devkit re ghidra-apply --apply --plan {shlex.quote(str(plan))} "
                  f"--plan-sha256 {d['plan_sha256']} --project {shlex.quote(str(project))}")
            return 0
        if not args.plan_sha256:
            raise ApplyError("--apply needs --plan-sha256 <the sha256 its dry run printed>")
        r = apply_plan(project, plan, args.plan_sha256)
    except (ApplyError, ProjectError, ServeError) as exc:
        print(f"ghidra-apply: {exc}", file=sys.stderr)
        return 2
    for line in r.get("lines", []):
        print(f"  {line}")
    undo = (f"python -m devkit re ghidra-backup restore {Path(r['backup']).name} "
            f"--project {shlex.quote(str(project))}")
    if r["verified"]:
        print(f"ghidra-apply: applied and verified on a copy in {r['seconds']} s: {project}")
        print(f"  backup: {r['backup']} (to undo: {undo})")
        return 0
    sys.stdout.flush()
    print(f"ghidra-apply: FAILED: {r['why']}", file=sys.stderr)
    if "restore_failed" in r:
        print(f"  the project could NOT be put back: {r['restore_failed']}\n  once no Ghidra holds it: "
              f"{undo}", file=sys.stderr)
        return 3
    print(f"  the project was put back byte-identical from {r['backup']}"
          + (f"; as the run left it, it is in {r['replaced']}" if r.get("replaced") else "")
          if r["restored"] else f"  the project is unchanged; backup {r['backup']}", file=sys.stderr)
    return 1
