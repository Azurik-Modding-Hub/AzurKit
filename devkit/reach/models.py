"""The reach models the L3 store keeps (Step 4.13d1): the store's ``x7/reach`` folder (the certification's private
folder) holds each level's reach model (``draft.reach.Reach``), pickled by this checkout: ``<level>@<sha256 of the
zoning, 12>.pkl`` (or ``<level>.pkl`` while its ``.stamp`` names the level's zoning).  Step 4.13f rebuilt every
current one with this checkout's code; the pickles Modkit made are gone (D1172, D1173):

- :func:`load` unpickles one: the globals a model names are this checkout's modules (:data:`OWN`) and the standard
  library's and numpy's few it holds (:data:`ALLOWED`); any other global, a Modkit module's too, is refused
  (``pickle.UnpicklingError`` naming it);
- :func:`reach_path` is the level's model under the zoning of its derived file (``proofs.zoning``) and its
  builder's code (:func:`builder_sha12`), built from the vanilla image when the store has none (minutes) and kept
  beside the others as a new file.

A re-derive renumbers zones, so a model of another zoning would aim the searches' goals and route seeds at the old
zones; and a model built by older code keeps that code's certificates (AZ-857: 4.13d1's copied plans so stood on
older ones), so the builder's code is in the key too.  Positions stay in memory.
"""

from __future__ import annotations

import functools
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


CODE_ROOT = Path(__file__).resolve().parents[2]   # the checkout whose builder code keys a model
BUILDER = ("devkit/rando/derive.py", "src/azurkit/tools/randomizer/levels.py",
           "src/azurkit/tools/randomizer/art/nodes.py", "src/azurkit/tools/randomizer/art/tern.py")
# the reach model's builder besides a router's code (``l3_goal.ROUTER_CODE``: the draft, physics, collision): the
# derive's router, the level table and the art graph the model reads


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
    """The ``<zoning> <builder sha12>`` key a reach pickle's ``.stamp`` beside it names (None: none)."""
    side = path.with_suffix(".stamp")
    return side.read_text(encoding="utf-8").strip() if side.is_file() else None


@functools.cache
def builder_sha12(root: Path) -> str:
    """sha256[:12] of the reach model builder's code under ``root`` (``l3_goal.ROUTER_CODE`` and :data:`BUILDER`:
    each ``.py`` and ``.toml`` file's path and bytes, as ``l3_goal.router_key`` reads them), once a process."""
    from devkit.rando.draft.l3_goal import ROUTER_CODE
    h = hashlib.sha256()
    for rel in ROUTER_CODE + BUILDER:
        p = root / rel
        for f in sorted(q for q in p.rglob("*") if q.suffix in (".py", ".toml") and q.is_file()) if p.is_dir() else [p]:
            h.update(f"{f.relative_to(root).as_posix()}\n".encode() + f.read_bytes())
    return h.hexdigest()[:12]


def reach_path(level: str) -> Path:
    """The level's reach model under its current zoning and builder code (the module docstring): the first one
    built (``<level>.pkl``) while its ``.stamp`` is the two (``<zoning> <code sha12>``), else the one keyed by them,
    built the first time."""
    from azurkit.tools.randomizer.planner import proofs as pr
    from devkit.rando.draft.author import read_derived
    key = f"{pr.zoning(read_derived(level))} {builder_sha12(CODE_ROOT)}"
    kept = folder() / f"{level}.pkl"
    if _stamp(kept) == key:
        return kept
    path = kept.with_name(f"{level}@{hashlib.sha256(key.encode()).hexdigest()[:12]}.pkl")
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
