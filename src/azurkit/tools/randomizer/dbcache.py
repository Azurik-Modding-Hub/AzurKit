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
lists it) or the frozen app, never from a checkout.
"""

from __future__ import annotations

import dataclasses
import gc
import hashlib
import importlib.metadata
import pickle
import sys
from collections.abc import Callable
from pathlib import Path

PLANNER = Path(__file__).resolve().parent / "planner"
SHIPPED = Path(__file__).resolve().parent / "shipped"
# The frozen app's planner is in its archive, not files, sealed with the data it ships: its key is the data's alone.
FROZEN = bool(getattr(sys, "frozen", False))


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


def shipped(root: Path) -> tuple | None:
    """(the checked database at ``root``, its Logic's tables, its memos'
    types) as the wheel's or the frozen app's build made them for ``root``'s
    key, its ``root`` put back, or None (no such file, or this isn't the
    wheel's or the frozen app's own). What it reads (about a million
    objects, kept for the process) is frozen out of the cycle collector's
    walks (``gc.freeze``): read at once, two full walks of it (0.4 s each,
    the GIL held) came with the next call's allocations, which held the app's
    server, a model's pictures asked meanwhile waiting a second (train B2)."""
    if not SHIPPED.is_dir():
        return None
    name = f"{entry(root).name}.pickle"
    path = SHIPPED / name
    if not path.is_file() or not (FROZEN or _installed(path)):
        return None
    db, tables, memos = pickle.loads(path.read_bytes())
    gc.freeze()
    db.root = Path(root)
    return db, tables, memos


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


def shipped_logic(root: Path, logic_type: type) -> object | None:
    """A ``logic_type`` (the planner's Logic) of :func:`shipped`'s database
    with the tables its build made and its memos empty, or None: the loader's
    ``kept_logic`` builds one in about 1.4 s otherwise."""
    if (got := shipped(root)) is None:
        return None
    db, tables, memos = got
    logic = logic_type.__new__(logic_type)
    vars(logic).update(tables, db=db, **{name: kind() for name, kind in memos.items()})
    return logic


def ship(out: Path, planner: Path | None = PLANNER) -> Path:
    """Check the shipped database and write ``out/<key>.pickle`` (the key
    :func:`entry` gives under ``planner``): the database with its ``root``
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
    path.write_bytes(pickle.dumps((dataclasses.replace(report.database, root=None), tables, memos),
                                  pickle.HIGHEST_PROTOCOL))
    return path
