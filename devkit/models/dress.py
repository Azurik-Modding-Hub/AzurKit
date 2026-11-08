"""A player variant dressed in memory as a build dresses it (Modkit's
``model_dress``, Step X.65f; ``models model dress``, and the springs' and
poses' leafs after it): on the verified vanilla image (D27), over the layers
of the packs on by default (both upper packs since D588), so the size lines
are a default build's (a 128 MiB machine's unless ``ram`` is 64; 256 adds
``qol_memory_upper256``, Step 2.162l), the swap's own dress
(``tools.characters.dressed``, the one a build plans) with the recipe's own
options, its prop and mesh left in its body as its readers read it (no P2
copy: that is for the NPCs a level places, Step 2.203). Nothing is written
but what :func:`write` writes, and only after the dress passed (D35)."""

from __future__ import annotations

import dataclasses
import hashlib
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from devkit.models import image

FILES = ("characters.xbr", "index.xbr")
"""The files :func:`write` writes: the dressed bodies and clips and their
index records (game assets)."""


@dataclass
class Dressed:
    """A dressed build: the staging (its files as the dress left them), the
    body the variant wears, the dress's log lines, W24's plan (``None`` for a
    recipe with no ``mesh``), the spring rows' preview data
    (``apply_player_model``'s ``springs_out``; empty with no spring row) and
    the dress's seconds."""

    game: object
    body: str
    log: list
    plan: object
    springs: dict
    seconds: float


def packs(ram: int | None = None) -> dict[str, dict]:
    """The packs a default build for a ``ram`` MiB machine applies (``None``:
    ``model_inspect.DEFAULT_RAM``): every pack on by default, and
    ``qol_memory_upper256`` at 256 (Modkit's ``build_packs(ram_packs(ram))``)."""
    from azurkit.tools import mods
    from azurkit.tools.characters import model_inspect

    extra = {model_inspect.UPPER256_PACK} if (ram or model_inspect.DEFAULT_RAM) == 256 else set()
    return mods.normalize({name: {} for name, pack in mods.PACKS.items() if pack.default_on or name in extra})


def dress(variant, iso: Path, *, ram: int | None = None, strength: float = 1.0, stiffness: float = 1.0) -> Dressed:
    """``variant`` (a ``_player_variants.Variant``) dressed on the vanilla
    ``iso`` for a ``ram`` MiB machine (``None``: the default packs' largest,
    as a build's), the jiggle sliders ``strength`` and ``stiffness`` (any
    finite numbers, D23) passed through; ``ValueError`` names why it can't
    dress, as a build's (D35), or an ``iso`` that isn't vanilla (D27)."""
    from azurkit import sdk
    from azurkit.tools import characters, mods
    from azurkit.tools.characters.gltf import resolve_body

    stamp = image.stamp(iso)
    vanilla, layers = sdk._under_a_dress(stamp, packs(ram))
    body, _ = resolve_body(vanilla.read(characters.FILES[0]), vanilla.read(characters.CONFIG), variant.base)
    recipe = {"species": variant.name, "jiggle_strength": strength, "jiggle_stiffness": stiffness,
              **({"ram": ram} if ram is not None else {})}
    springs, plans, start = {}, [], time.monotonic()
    game, _, _, log = characters.dressed(recipe, vanilla, layers, characters.packs_view(stamp.release, mods.PACKS),
                                         worn=variant, springs_out=springs, plans=plans, player_only=False)
    return Dressed(game, body, log, plans[0] if plans else None, springs, time.monotonic() - start)


def numbers(plan) -> dict | None:
    """W24's ``plan`` as counts and numbers, never a coordinate (a game
    asset's): each field that is a number, a word or none as it is, a
    collection as its length, a nested record (its glTF edit, its mesh)
    the same way, anything else left out."""
    if plan is None:
        return None
    out = {}
    for f in dataclasses.fields(plan):
        value = getattr(plan, f.name)
        if value is None or isinstance(value, (bool, int, float, str)):
            out[f.name] = value
        elif isinstance(value, (dict, list, tuple, set, frozenset)):
            out[f.name] = len(value)
        elif dataclasses.is_dataclass(value):
            out[f.name] = numbers(value)
    return out


def write(out: Path, game, names: tuple[str, ...] = FILES) -> dict[str, tuple[int, str]]:
    """The dressed :data:`FILES` (or ``names``, each one of ``game``'s)
    written into ``out`` (a new or empty folder the caller checked, D36)
    whole: into a scratch folder beside it, then renamed, so a failure writes
    nothing (D35); each one's size and sha256."""
    out = Path(out).absolute()
    out.parent.mkdir(parents=True, exist_ok=True)
    part = Path(tempfile.mkdtemp(prefix=f".{out.name}.part-", dir=out.parent))
    try:
        got = {}
        for name in names:
            data = bytes(game[name])
            (part / name).write_bytes(data)
            got[name] = (len(data), hashlib.sha256(data).hexdigest())
        if out.exists():
            out.rmdir()
        part.rename(out)
    except BaseException:
        shutil.rmtree(part, ignore_errors=True)
        raise
    return got
