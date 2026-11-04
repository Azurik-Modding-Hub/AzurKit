"""The planner loader's database key and load (``planner/loader.py``'s
``load_database`` and ``kept_logic`` call them), in place of Modkit's
``planner/dbcache.py``, which keeps the checked database as a pickle in the
user cache. AzurKit keeps none on disk: the site's worker has no lasting
disk, and a pickle read back from a folder the program writes runs what it
holds. ``kept_logic`` keeps the :class:`~.planner.solver.Logic` it builds
for the process, under :func:`entry`'s key.

The wheel and the frozen app ship the checked database instead (Step 4.3g,
P4): ``shipped/<key>.pickle`` beside this module, which their builds write
(:func:`ship`, from ``scripts/web_tools.py`` and ``scripts/freeze.py``;
generated, never in the checkout). :func:`load` serves it for the key it was
made for, so a changed data file or planner module reads and checks the
database as before (about 4 s); it is read only from the wheel (its RECORD
lists it) or the frozen app, never from a checkout. Its file holds the
database's skip table first (:func:`shipped_skips`: a page's remembered
randomizer is checked against it, about 14 KB, never the 87.6 MB logic,
Step 4.4bd), then the database; the logic's read is counted.
"""

from __future__ import annotations

import dataclasses
import gc
import hashlib
import importlib.metadata
import io
import pickle
import sys
from collections.abc import Callable
from pathlib import Path

from azurkit.core import progress

PLANNER = Path(__file__).resolve().parent / "planner"
SHIPPED = Path(__file__).resolve().parent / "shipped"
# The frozen app's planner is in its archive, not files, sealed with the data it ships: its key is the data's alone.
FROZEN = bool(getattr(sys, "frozen", False))
NOTES = 20   # the logic's read is a core.progress note each twentieth of its file ("reading its logic, k of 20")


def entry(root: Path, planner: Path | None = None if FROZEN else PLANNER) -> Path:
    """The key of the database at ``root``, as a path whose name is the
    sha256 (32 hex digits) of the name and bytes of each file under it and
    under the planner's code (``planner``; None: the data's alone, as the
    frozen app's): a changed file gives another key."""
    h = hashlib.sha256()
    for folder in (Path(root), *([planner] if planner is not None else [])):
        for path in sorted(folder.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                h.update(f"{path.relative_to(folder).as_posix()}\0".encode())
                h.update(hashlib.sha256(path.read_bytes()).digest())
    return Path(h.hexdigest()[:32])


def _path(root: Path, key: str | None = None) -> Path | None:
    """The shipped file of ``root``'s key (``key``, :func:`entry`'s when the caller has it, else worked out now), or
    None (no such file, or this isn't the wheel's or the frozen app's own)."""
    if not SHIPPED.is_dir():
        return None
    path = SHIPPED / f"{key or entry(root).name}.pickle"
    return path if path.is_file() and (FROZEN or _installed(path)) else None


def _table(skips: object, path: Path) -> dict:
    """The skip table read from the front of ``path``, or :class:`RuntimeError` naming a file of another layout."""
    if not isinstance(skips, dict):
        raise RuntimeError(f"{path.name}: not a shipped database of this AzurKit's layout (its skip table, then its "
                           "database)")
    return skips


class _Counted(io.RawIOBase):
    """``raw`` read on, each twentieth of its ``size`` read a core.progress
    note ("reading its logic, k of 20"), so the logic's read is counted by
    the bytes it has taken (Step 4.4bd)."""

    def __init__(self, raw: io.RawIOBase, size: int):
        self.raw, self.size, self.done, self.told = raw, max(size, 1), 0, 0

    def readable(self) -> bool:
        return True

    def readinto(self, buffer) -> int:
        got = self.raw.readinto(buffer)
        self.done += got
        if (k := min(self.done * NOTES // self.size + 1, NOTES)) > self.told:
            self.told = k
            progress.note(f"reading its logic, {k} of {NOTES}")
        return got


def shipped(root: Path, key: str | None = None) -> tuple | None:
    """(the checked database at ``root``, its Logic's tables, its memos'
    types) as the wheel's or the frozen app's build made them for ``root``'s
    key (``key``, :func:`entry`'s, when the caller has it), its ``root``
    put back, or None (as :func:`_path`). It is read as a stream, counted
    (:class:`_Counted`). What it reads (about a million
    objects, kept for the process) is frozen out of the cycle collector's
    walks (``gc.freeze``): read at once, two full walks of it (0.4 s each,
    the GIL held) came with the next call's allocations, which held the app's
    server, a model's pictures asked meanwhile waiting a second (train B2)."""
    if (path := _path(root, key)) is None:
        return None
    with open(path, "rb", buffering=0) as raw:
        stream = io.BufferedReader(_Counted(raw, path.stat().st_size), 1 << 20)
        _table(pickle.Unpickler(stream).load(), path)   # the skip table ahead of it (shipped_skips')
        db, tables, memos = pickle.Unpickler(stream).load()
    gc.freeze()
    db.root = Path(root)
    return db, tables, memos


def shipped_skips(root: Path) -> dict | None:
    """The shipped database's skip table (``{id: skip}``, the skips of
    its ``skips``, each beside its level there), read from the front of its
    file (about 14 KB, not the 87.6 MB of the database after it), or None
    (as :func:`_path`): what a page's remembered randomizer is checked
    against without reading the logic (Step 4.4bd)."""
    if (path := _path(root)) is None:
        return None
    with path.open("rb") as f:
        return _table(pickle.load(f), path)


def _installed(path: Path) -> bool:
    """Whether ``path`` is a file the installed wheel put there (its RECORD lists it)."""
    try:
        files = importlib.metadata.files("azurkit") or []
    except importlib.metadata.PackageNotFoundError:
        return False
    rel = path.relative_to(path.parents[4]).as_posix()     # azurkit/tools/randomizer/shipped/<key>.pickle
    return any(f.as_posix() == rel and Path(f.locate()).resolve() == path for f in files)


def load[T](root: Path, build: Callable[[Path], T]) -> T:
    """The database at ``root``: the shipped one for its key (:func:`shipped`), else read and checked now
    (``build(root)``)."""
    got = shipped(root)
    return got[0] if got is not None else build(root)


def shipped_logic(root: Path, logic_type: type, key: str | None = None) -> object | None:
    """A ``logic_type`` (the planner's Logic) of :func:`shipped`'s database
    (for ``key``, the loader's, so it is worked out once) with the tables
    its build made and its memos empty, or None: the loader's
    ``kept_logic`` builds one in about 1.4 s otherwise."""
    if (got := shipped(root, key)) is None:
        return None
    db, tables, memos = got
    logic = logic_type.__new__(logic_type)
    vars(logic).update(tables, db=db, **{name: kind() for name, kind in memos.items()})
    return logic


def ship(out: Path, planner: Path | None = PLANNER) -> Path:
    """Check the shipped database and write ``out/<key>.pickle`` (the key
    :func:`entry` gives under ``planner``): its skip table
    (:func:`shipped_skips`), then the database with its ``root``
    dropped, so no path of the checkout that built it is in it, the tables
    its Logic built and its memos' types. Only under ``PYTHONHASHSEED=0``
    (never ``python -I``, which ignores it), so its sets pickle in one order
    and a build gives the same bytes every time."""
    if sys.flags.hash_randomization:
        raise RuntimeError("the shipped database is written under PYTHONHASHSEED=0 (not python -I, which ignores it)")
    from azurkit.tools.randomizer.planner import loader
    from azurkit.tools.randomizer.planner.solver import Logic

    report = loader.check_database(loader.DATA_DIR)
    if report.issues:
        raise loader.DatabaseError(loader.DATA_DIR, report.issues)
    logic = Logic(report.database)
    tables = {k: v for k, v in vars(logic).items() if k not in loader._MEMOS}
    memos = {k: type(v) for k, v in vars(logic).items() if k in loader._MEMOS and k != "db"}
    path = Path(out) / f"{entry(loader.DATA_DIR, planner).name}.pickle"
    skips = {sid: s for sid, (_, s) in report.database.skips.items()}
    path.write_bytes(pickle.dumps(skips, pickle.HIGHEST_PROTOCOL)
                     + pickle.dumps((dataclasses.replace(report.database, root=None), tables, memos),
                                    pickle.HIGHEST_PROTOCOL))
    return path
