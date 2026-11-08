"""A Ghidra project on disk, handled without opening it (stdlib only;
Modkit's, ported in Step 4.11d2).

A project is ``<dir>/<name>.gpr`` plus the ``<name>.rep`` folder beside it.
Ghidra's lock files, ``<name>.lock`` and ``<name>.lock~``, sit beside them;
they belong to no copy and no fingerprint. ``ghidra-serve`` (Step 2.13c)
copies the owner's project with these helpers and only ever reads it.

``ghidra-apply`` (Step 2.13f, D90; :mod:`.ghidra_apply`) is the one
writer: it writes a reviewed plan into the closed project after a
:func:`backup` into ``ghidra-backups/`` beside the project's folder, and
puts the backup back (:func:`restore`) when the run or its read-only
verify on a copy fails, times out or is interrupted. ``ghidra-backup``
lists, restores and prunes those backups.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path
from typing import NamedTuple

__all__ = ["KEEP", "ApplyError", "LockState", "ProjectError", "backup", "backups", "backups_dir",
           "copy_project", "fingerprint", "lock_state", "manifest", "project_arg", "prune", "restore"]


class ProjectError(RuntimeError):
    """Not a Ghidra project."""


class LockState(NamedTuple):
    """``free`` (no lock files), ``held`` (a Ghidra has the project open;
    ``pid`` names it when the platform can tell), ``stale`` (lock files a
    Ghidra that died left behind) or ``unknown`` (Windows: Ghidra's
    ``LockFileEx`` lock has no passive probe)."""

    state: str
    pid: int | None = None


def _files(gpr: Path, every: bool = False) -> list[tuple[str, Path]]:
    """(name-independent key, path) for the ``.gpr`` and each file in the
    ``.rep`` but, unless ``every``, Ghidra's index backups (``~index.bak``,
    ``~journal.bak``): any open, even read-only, may rotate them (a fresh
    import's ``idata/~journal.bak`` goes on the next open) while the live
    ``~index.dat`` stays the same [verified 2026-10-10, Step 2.13c]."""
    rep = gpr.with_suffix(".rep")
    if gpr.suffix != ".gpr" or not gpr.is_file() or not rep.is_dir():
        raise ProjectError(f"not a Ghidra project: {gpr} (a <name>.gpr file with the "
                           f"<name>.rep folder beside it)")
    return [(".gpr", gpr)] + sorted(
        (".rep/" + p.relative_to(rep).as_posix(), p) for p in rep.rglob("*")
        if p.is_file() and (every or not (p.name.startswith("~") and p.suffix == ".bak")))


def fingerprint(gpr: Path) -> str:
    """sha256 over every file's path and content (about 0.2 s for the
    owner's 291 MB project). Content, not mtimes: a clean read-only open
    rewrites the ``~index.dat`` mtimes. The project's name is left out, so
    a faithful copy under another name has the same fingerprint."""
    h = hashlib.sha256()
    for key, path in _files(gpr):
        with open(path, "rb") as f:
            h.update(f"{key}\0{hashlib.file_digest(f, 'sha256').hexdigest()}\n".encode("utf-8"))
    return h.hexdigest()


def _copy(src: Path, dst: Path) -> None:
    """An APFS clone on macOS (``cp -c``), a reflink where Linux's ``cp``
    can make one, otherwise a plain copy."""
    flags = {"darwin": ["-c"], "linux": ["--reflink=auto"]}.get(sys.platform)
    if flags and subprocess.run(["cp", *flags, "-R", str(src), str(dst)],
                                capture_output=True).returncode == 0:
        return
    if dst.is_dir():
        shutil.rmtree(dst)
    dst.unlink(missing_ok=True)
    (shutil.copytree if src.is_dir() else shutil.copy2)(src, dst)


def copy_project(gpr: Path, dest_dir: Path, name: str) -> Path:
    """Copy ``gpr`` and its ``.rep`` into ``dest_dir`` as ``<name>.gpr``
    and return it. Reads the source only; its lock files are not copied."""
    _files(gpr)
    dest_dir.mkdir(parents=True, exist_ok=True)
    new = dest_dir / f"{name}.gpr"
    _copy(gpr, new)
    _copy(gpr.with_suffix(".rep"), new.with_suffix(".rep"))
    return new


def lock_state(gpr: Path) -> LockState:
    """Whether a Ghidra (GUI or headless) holds ``gpr`` open, without
    creating, locking or writing anything.

    Ghidra holds an ``fcntl`` lock on ``<name>.lock~`` while the project is
    open. This opens that file read-only and asks ``F_GETLK`` who holds it.
    A ``<name>.lock`` with no ``.lock~`` is Ghidra's file-lock mode: held."""
    lock = gpr.with_suffix(".lock")
    channel = Path(f"{lock}~")
    if not lock.exists() and not channel.exists():
        return LockState("free")
    if sys.platform not in ("darwin", "linux"):
        return LockState("unknown")
    import fcntl
    try:
        fd = os.open(channel, os.O_RDONLY)
    except FileNotFoundError:
        return LockState("held")
    try:
        if sys.platform == "darwin":  # struct flock: start, len, pid, type, whence
            ask = struct.pack("qqihh", 0, 0, 0, fcntl.F_WRLCK, os.SEEK_SET)
            _, _, pid, kind, _ = struct.unpack("qqihh", fcntl.fcntl(fd, fcntl.F_GETLK, ask))
        else:  # Linux: type, whence, (pad), start, len, pid, (pad): 32 bytes
            ask = struct.pack("hhqqi4x", fcntl.F_WRLCK, os.SEEK_SET, 0, 0, 0)
            kind, _, _, _, pid = struct.unpack("hhqqi4x", fcntl.fcntl(fd, fcntl.F_GETLK, ask))
    finally:
        os.close(fd)
    return LockState("stale") if kind == fcntl.F_UNLCK else LockState("held", pid)


# ----------------------------------------------------------------------
# ghidra-apply's backups (Step 2.13f, D90, D103)
# ----------------------------------------------------------------------

KEEP = 1  # D103: one undo level; a backup is a whole project copy, 291 MB for the owner's


class ApplyError(RuntimeError):
    """An apply, restore or prune that can't go ahead; the verb exits 2."""


def _sha256(path: Path) -> str:
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def _load(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _dump(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, indent=1) + "\n", encoding="utf-8")


def manifest(gpr: Path) -> dict[str, str]:
    """The sha256 of every file of the project, index backups included, by
    its name-independent key: a restore is byte-identical when the
    project's manifest equals the backup's."""
    return {key: _sha256(path) for key, path in _files(gpr, every=True)}


def backups_dir(gpr: Path) -> Path:
    """``ghidra-backups/`` beside the folder that holds the ``.gpr`` (Q205:
    beside the owner's ``ghidra`` folder for the owner's project), so it is
    on the project's volume and a restore moves rather than copies."""
    return gpr.parent.parent / "ghidra-backups"


def backups(gpr: Path) -> list[tuple[Path, dict]]:
    """The project's backups, oldest first: (folder, its ``manifest.json``).
    Only a folder whose manifest names this project's path counts (another
    project of the same name beside it shares ``ghidra-backups/``), so
    nothing else is ever listed, restored or pruned."""
    root = backups_dir(gpr)
    found = [(d, _load(d / "manifest.json")) for d in sorted(root.iterdir())] if root.is_dir() else []
    return [(d, info) for d, info in found if info and info.get("project") == str(gpr)]


def _new_folder(root: Path) -> Path:
    """A new ``<root>/<UTC time>/``; the names sort oldest first, also
    after a prune freed an earlier name of the same second (the next
    suffix follows the last one there)."""
    root.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    last = max((p.name for p in root.iterdir() if p.name.startswith(stamp)), default=None)
    for n in range(0 if last is None else int(last.partition("-")[2] or 0) + 1, 100):
        try:
            (folder := root / (f"{stamp}-{n}" if n else stamp)).mkdir()
            return folder
        except FileExistsError:
            continue
    raise ApplyError(f"no free backup folder name in {root}")


def backup(gpr: Path) -> Path:
    """Copy the project (an APFS clone on macOS) into a new folder under
    :func:`backups_dir`, with ``manifest.json``. Keeps nothing, and
    refuses, when the project changed during the copy (a Ghidra saving)."""
    before = manifest(gpr)
    folder = _new_folder(backups_dir(gpr))
    copy_project(gpr, folder, gpr.stem)
    if manifest(folder / gpr.name) != before or manifest(gpr) != before:
        shutil.rmtree(folder)
        raise ApplyError(f"{gpr} changed while it was backed up (a Ghidra saving?): nothing done")
    _dump(folder / "manifest.json", {"project": str(gpr), "kind": "before ghidra-apply", "files": before})
    return folder


def _refuse_open(gpr: Path, then: str) -> None:
    """Refuse while a Ghidra holds the project; on Windows, which has no
    passive probe, while its lock files exist."""
    lock = lock_state(gpr)
    if lock.state == "held":
        raise ApplyError(f"a Ghidra holds {gpr}" + (f" (pid {lock.pid})" if lock.pid else "")
                         + f": close it, then run again; {then}")
    if lock.state == "unknown":
        raise ApplyError(f"{gpr.with_suffix('.lock')} exists and Windows has no passive lock probe: "
                         f"close Ghidra (if none runs, delete the stale {gpr.stem}.lock and "
                         f"{gpr.stem}.lock~), then run again; {then}")


def restore(gpr: Path, saved: Path) -> Path | None:
    """Put the backup folder ``saved`` back as the project, byte-identical
    to its manifest. The project as it is moves aside first, into a backup
    folder of its own (returned; None when there was no project): a
    restore never deletes anything. Refuses while a Ghidra holds it."""
    info = _load(saved / "manifest.json")
    if info is None:
        raise ApplyError(f"{saved} is not a ghidra-apply backup (no manifest.json)")
    copy = saved / Path(info["project"]).name
    try:
        intact = manifest(copy) == info["files"]
    except ProjectError:
        intact = False
    if not intact:
        raise ApplyError(f"{saved} no longer matches its manifest: nothing restored")
    _refuse_open(gpr, "nothing restored")
    aside = None
    if gpr.exists() or gpr.with_suffix(".rep").exists():
        aside = _new_folder(backups_dir(gpr))
        for part in (gpr, gpr.with_suffix(".rep")):
            if part.exists():
                shutil.move(part, aside / part.name)
        try:
            files = manifest(aside / gpr.name)
        except ProjectError:  # a torn project: kept, not restorable by the verb
            files = None
        _dump(aside / "manifest.json", {"project": str(gpr), "files": files,
                                        "kind": f"replaced by a restore of {saved.name}"})
    copy_project(copy, gpr.parent, gpr.stem)
    if manifest(gpr) != info["files"]:
        raise ApplyError(f"{gpr} does not match {saved.name}'s manifest after the restore; "
                         f"the project it replaced is in {aside}")
    return aside


def prune(gpr: Path, keep: int = KEEP, protect: tuple[Path, ...] = ()) -> list[Path]:
    """Delete all but the newest ``keep`` backups of the project (D103: 1),
    never one in ``protect`` (an apply's own, whatever the clock said) nor
    one of the newest ``keep`` that undo a verified apply: after a failed
    apply the newest are its own backup and the project it set aside,
    and neither undoes anything."""
    if keep < 1:
        raise ApplyError("keep at least 1 backup")
    found = backups(gpr)
    undo = [d for d, info in found if info.get("kind") == "before ghidra-apply"
            and (_load(d / "result.json") or {}).get("verified")][-keep:]
    old = [d for d, _ in found[:-keep] if d not in protect and d not in undo]
    for d in old:
        shutil.rmtree(d)
    return old


def project_arg(project: str | None, *, writes: bool) -> Path:
    """``--project``. Only a read (the dry run, ``ghidra-backup list``) may
    take the project ``ghidra-serve``'s last start used: every start, from
    any lane, rewrites that one record, so a write never does."""
    from .ghidra_serve import remembered_project
    if project:
        return Path(project).expanduser().resolve()
    if writes:
        raise ApplyError("name the project: --project <name>.gpr (a write never takes the one "
                         "ghidra-serve last used); nothing done")
    if (remembered := remembered_project()) is None:
        raise ApplyError("pass --project <name>.gpr (no ghidra-serve start to take it from)")
    return remembered.resolve()
