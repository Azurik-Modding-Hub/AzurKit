"""The planner loader's database key and load (``planner/loader.py``'s
``load_database`` and ``kept_logic`` call them), in place of Modkit's
``planner/dbcache.py``, which keeps the checked database as a pickle in the
user cache. AzurKit keeps none on disk: the site's worker has no lasting
disk, and a pickle read back from a writable folder runs what it holds. A
database is read and checked at each :func:`load` (about 3 s), and
``kept_logic`` keeps the :class:`~.planner.solver.Logic` it builds for the
process, under :func:`entry`'s key.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

PLANNER = Path(__file__).resolve().parent / "planner"


def entry(root: Path) -> Path:
    """The key of the database at ``root``, as a path whose name is the
    sha256 (32 hex digits) of the name and bytes of each file under it and
    under the planner's code: a changed file gives another key."""
    h = hashlib.sha256()
    for folder in (Path(root), PLANNER):
        for path in sorted(folder.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                h.update(f"{path.relative_to(folder).as_posix()}\0".encode())
                h.update(hashlib.sha256(path.read_bytes()).digest())
    return Path(h.hexdigest()[:32])


def load[T](root: Path, build: Callable[[Path], T]) -> T:
    """The database at ``root``, read and checked now (``build(root)``)."""
    return build(root)
