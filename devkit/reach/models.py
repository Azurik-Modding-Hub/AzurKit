"""The reach models the L3 store keeps (Step 4.13d1): the store's ``x7/reach`` folder (the certification's private
folder) holds each level's reach model (``draft.reach.Reach``), pickled by this checkout: ``<level>@<sha256 of the
zoning, 12>.pkl`` (or ``<level>.pkl`` while its ``.stamp`` names the level's zoning).  Step 4.13f rebuilt every
current one with this checkout's code; the pickles Modkit made are gone (D1172, D1173):

- :func:`load` unpickles one: the globals a model names are this checkout's modules (:data:`OWN`) and the standard
  library's and numpy's few it holds (:data:`ALLOWED`); any other global, a Modkit module's too, is refused
  (``pickle.UnpicklingError`` naming it);
- :func:`reach_path` is the level's model under the zoning of its derived file (``proofs.zoning``), built from the
  vanilla image when the store has none (minutes) and kept beside the others as a new file.

A re-derive renumbers zones, so a model of another zoning would aim the searches' goals and route seeds at the old
zones.  Positions stay in memory.
"""

from __future__ import annotations

import hashlib
import importlib
import os
import pickle
from pathlib import Path

OWN = frozenset({   # the modules a reach model pickled here names
    *(f"azurkit.tools.randomizer.draft.{m}" for m in ("envelope", "floors", "geometry", "wiring")),
    *(f"devkit.rando.draft.{m}" for m in ("reach", "flights", "gates", "moves", "sites", "route", "l3_goal",
                                          "coverage", "value", "export", "author")),
    "devkit.rando.physics", "azurkit.tools.randomizer.physics",
    *(f"azurkit.tools.randomizer.planner.{m}" for m in ("loader", "proofs", "solver", "fill", "plan", "grammar",
                                                        "settings")),
    *(f"azurkit.tools.randomizer.art.{m}" for m in ("collision", "nodes", "tern")),
    *(f"devkit.reach.engine.{m}" for m in ("nodes", "triggers"))})
ALLOWED = frozenset({   # (module, name): the standard library's and numpy's globals the models hold
    ("builtins", "list"), ("builtins", "set"), ("builtins", "frozenset"), ("builtins", "tuple"),
    ("collections", "Counter"), ("collections", "defaultdict"), ("collections", "OrderedDict"),
    ("pathlib", "PosixPath"), ("pathlib", "WindowsPath"),
    ("numpy", "dtype"), ("numpy", "ndarray"), ("numpy._core.multiarray", "_reconstruct"),
    ("numpy._core.multiarray", "scalar"), ("numpy._core.numeric", "_frombuffer")})


class _Unpickler(pickle.Unpickler):
    def find_class(self, module: str, name: str):
        if module not in OWN and (module, name) not in ALLOWED:
            raise pickle.UnpicklingError(f"a reach model names {module}.{name}, which is no module of this checkout's "
                                         "reach models nor a global they hold")
        return getattr(importlib.import_module(module), name)


def load(file):
    """The reach model pickled in the open binary ``file`` (the module docstring's rules)."""
    return _Unpickler(file).load()


def read(path: str | Path):
    """The reach model pickled at ``path`` (:func:`load`)."""
    with open(path, "rb") as f:
        return load(f)


def folder() -> Path:
    """The L3 store's ``x7/reach``, where the reach models are kept."""
    from devkit.sim import l3
    return l3.store() / "x7" / "reach"


def _stamp(path: Path) -> str | None:
    """The zoning a reach pickle's ``.stamp`` beside it names (None: none)."""
    side = path.with_suffix(".stamp")
    return side.read_text(encoding="utf-8").strip() if side.is_file() else None


def reach_path(level: str) -> Path:
    """The level's reach model under its current zoning (the module docstring): the first one built
    (``<level>.pkl``) while its ``.stamp`` is that zoning, else the one keyed by it, built the first time."""
    from azurkit.tools.randomizer.planner import proofs as pr
    from devkit.rando.draft.author import read_derived
    zoning = pr.zoning(read_derived(level))
    kept = folder() / f"{level}.pkl"
    if _stamp(kept) == zoning:
        return kept
    path = kept.with_name(f"{level}@{hashlib.sha256(zoning.encode()).hexdigest()[:12]}.pkl")
    if not path.exists():
        from devkit.rando.derive import router
        from devkit.sim.ports import vanilla_iso
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.{os.getpid()}.part")
        with open(tmp, "wb") as f:
            pickle.dump(router(vanilla_iso(), level).R, f)
        tmp.chmod(0o600)
        tmp.replace(path)
    return path
