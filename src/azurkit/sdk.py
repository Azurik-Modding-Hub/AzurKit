"""The one surface a UI calls: :func:`catalog`, :func:`verify`,
:func:`vanilla` (and the site's :func:`layout` and :func:`prime`),
:func:`image`, :func:`save`, :func:`build`, :func:`open_build`,
:func:`read_mods`, :func:`preset_encode`, :func:`preset_decode`, the
randomizer's :func:`plan`, :func:`spoiler`, :func:`randomizer_settings`
(its tab's), :func:`randomizer_logic` (its logic, read ahead),
:func:`tracker` (the item tracker's) and :func:`art` and
:func:`art_world` (its maps and icons, drawn from the player's image),
:func:`restore`, the Characters tab's :func:`pickers`, :func:`match`
(its G4 buttons) and :func:`preview`, Azurik-Custom-Content's
:func:`content`, :func:`content_install` and :func:`content_check` (its
community entries), the Data tab's :func:`data` and :func:`data_edit`
(config.xbr's cells, edited before an image is picked), and the Tools
tab's :func:`image_info`, :func:`verify_all`, :func:`files`,
:func:`extract` and :func:`mods_file` (the image, its files, and mods
files saved and read). JSON in and
out: a recipe is a JSON object and each call returns one; :func:`image`
also returns the image, unwritten, which the web page joins into a Blob
(``iso.Image.segments``), or :func:`save` writes. A refusal is a
``ValueError`` or ``OSError`` whose message names what it refuses and why,
never game bytes; a build that fails writes nothing (D35). A long call
reports its named stages to a host's ``progress`` (``core.progress``'s
record: ``{"stage", "label", "done", "total", "percent"}``).
``tests/sdk_api.txt`` is this surface's snapshot (``scripts/sdk_api.py``).

A recipe names its image, every pack it applies, each with its sliders'
values (a slider it doesn't name keeps its default), and the mods file's
``xbr`` operations (``edits.xbr``: a config.xbr cell ``set`` by its names,
or ``replace_bytes`` in an XBR file, applied in order after the packs)::

    {"iso": "<a vanilla image>", "packs": {"fps_unlock": {"target_fps": 120}, "qol_alloc_race": {}},
     "xbr": [{"op": "set", "file": "gamedata/config.xbr", "table": "critters_damage", "entity": "golem",
              "prop": "hitPoints", "value": 321}]}

A build with a layer carries its manifest in two root files the game never
opens, ``/azurkit.json`` and ``/azurkit.bin`` (Q66), and :func:`open_build`
reads an AzurKit build back into its recipe: its mods file (Q268), which
:func:`read_mods` turns into a recipe's ``packs`` and ``xbr`` again.

The packs apply in their canonical order, whatever order the recipe names
them in. A build applies the packs it names and no others: :func:`catalog`
says which are on by default (D528), for a UI to start ticked, each pack's
sliders, and the packs each requires in the same build, without which a
recipe is refused by name. A slider takes any finite number (D23; a whole
one its encoding holds where it takes only those, D45): its track's ends
are hints, never limits, and nothing is clamped (``mods.normalize``).

A randomizer plan needs no image: :func:`plan` takes a seed and its
settings (``tools.randomizer``'s recipe) and returns Modkit's plan file. A
build recipe's ``randomizer`` (that recipe, and an ``obsidian_cost``) plans
it on the logic re-checked under the build's movement sliders and writes it
as the build's first layer, before the packs (Modkit's ``mod_apply``
order); the built image is read back against the plan before anything is
written: a placement a later layer changed is a conflict that leaves the
logic unverified (D28), any other difference fails the build (D35), and the
report's ``randomizer`` gives the verdict (``tools.randomizer.generator``)
and its ``spoiler`` the build's spoiler (Modkit's ``--spoiler`` file)::

    {"iso": "<a vanilla image>", "packs": {...}, "randomizer": {"seed": "2", "share": "AZR-AAEA"}}

A share link carries a recipe's randomizer too (its seed, settings and
obsidian cost), as an AzurKit build's mods file does.

A recipe's ``character`` dresses the player in a species' body (Modkit's
swap, ``tools.characters``: the body and its clips, its attacks, weapon,
sounds and fx, and the shims it hooks): the body's size folds into
player_physics' walk and roll before the packs (Modkit's ``size_params``;
the speed toggle flips those two to the body's own), and the character
layer stacks after the packs::

    {"iso": "<a vanilla image>", "packs": {...}, "character": {"species": "keylord", "mode": "garret4"}}

A character's ``species`` may name a variant (a recipe over a base species:
its sculpted mesh, painted textures, jiggle springs, clips and sounds), a
built-in or one of the recipe file ``variant_file`` names, its shapes sized
by ``shapes``::

    {"character": {"species": "mine", "variant_file": "<recipes.json>", "shapes": {"hips": 1.2}}}

A randomized build may wear a character (Modkit's ``randomize-full --seed``
with ``--player-character``): the plan stands on the walk and roll the
body's size folds, and what the body leaves unmodelled (its grade, its
attacks, its size) leaves the logic unverified, never refused. A build's
mods file (:func:`open_build`) and a share link (:func:`preset_encode`)
carry its character by name and numbers (a variant with its recipe's sha),
never a recipe file's path (Q174).
"""

from __future__ import annotations

import dataclasses
import functools
import hashlib
import json
import math
import os
import sys
import threading
import urllib.parse
from collections.abc import Callable, Mapping
from pathlib import Path

from azurkit import __version__
from azurkit.core import gate, iso, native
from azurkit.core.progress import Steps, noting
from azurkit.core.xbr import Document
from azurkit.edits import manifest as edits
from azurkit.edits import preset, xbr
from azurkit.edits.layer import Layer
from azurkit.tools import characters, mods, randomizer
from azurkit.tools import data as datatool
from azurkit.tools.randomizer import generator, tracking
from azurkit.tools.randomizer import layer as rando_layer

__all__ = ["catalog", "verify", "vanilla", "layout", "prime", "image", "image_staged", "image_checks", "save", "build", "open_build", "read_mods",
           "preset_encode", "preset_decode", "plan", "spoiler", "randomizer_logic", "randomizer_settings", "tracker",
           "art", "art_world", "restore", "content", "content_install", "content_check", "pickers", "match", "preview",
           "data", "data_edit", "image_info", "verify_all", "files", "extract", "mods_file"]
RECIPE = ("iso", "packs", "xbr", "randomizer", "character")
SETUP = ("ticked", "values", "xbr", "randomizer", "character")   # a UI's remembered setup (D915, :func:`restore`)
SOURCE = "https://raw.githubusercontent.com/Azurik-Modding-Hub/Azurik-Custom-Content/main/"
"""Where Azurik-Custom-Content is read from by default (D966: the hub's, public at Step 4.4)."""
SOURCE_ENV = "AZURKIT_CONTENT_SOURCE"   # set, it wins over a host's setting (the tests', a private play's)
#: A UI's tabs, one an area, in the owner's order (D901), each with whether
#: its area works yet: a tab shows only once it does (D902).
TABS = (("patches", "Patches", True), ("randomizer", "Randomizer", True), ("characters", "Characters", True),
        ("data", "Data", True), ("tools", "Tools", True), ("about", "About", True))


def catalog() -> dict:
    """A UI's tabs (each id and title, those whose area works, D902), the
    packs' categories (each id, title and line, in the order a UI groups
    them) and every pack: its name, what it does, its category, whether a
    build starts with it (D528), the releases it supports, the packs it
    requires in the same build and its sliders, in the canonical order. A
    slider: its name, label, default, track (``min``, ``max`` and
    ``step``, display hints only), unit, description, vanilla value
    (``None`` where the image's XBE holds it), ``whole`` (the range of
    whole numbers it takes, its encoding's, or ``None``) and
    ``logic_floor`` (``"min"`` or ``"max"``: the side of its default past
    which a randomized build's logic is unverified, D83(c); ``None``).
    ``randomizer``: what the Randomizer tab offers, with D144's defaults
    (``tools.randomizer.options``); ``characters``: the Characters tab's
    default Content from (:data:`SOURCE`); ``native``: the compiled kernels
    the engine runs (``core.native.report``: the library loaded and its
    sha256[:12], else why their Python twins run), which the perf gate
    reads."""
    return {"tabs": [{"id": tab, "title": title} for tab, title, works in TABS if works],
            "categories": [{"id": category, "title": title, "description": line}
                           for category, (title, line) in mods.CATEGORIES.items()],
            "packs": [{"name": p.name, "description": p.description, "category": p.category,
                       "default_on": p.default_on, "releases": list(p.releases), "requires": list(p.requires),
                       "sliders": [s.catalog() for s in p.sliders()]} for p in mods.PACKS.values()],
            "randomizer": randomizer.options(), "characters": {"source": SOURCE}, "native": native.report()}


def verify(path: str) -> dict:
    """Check that the image at ``path`` is a release's vanilla image, every
    file of it (``gate.NotVanillaError`` names the first that isn't)."""
    stamp = gate.verify(path)
    return {"iso": str(stamp.path), "release": stamp.release.name, "label": stamp.release.label}


def layout(path: str, *, whole: bool = False) -> dict:
    """The site's half of the image's check (``gate.layout``): ``{"files":
    [[path, offset, size]]}``, each file a build reads, whose sha256 a host
    hashes itself (the site's WebCrypto) for :func:`prime`; with ``whole``,
    each file the image's kept check (its build files', :func:`prime`'s)
    hasn't hashed, for :func:`verify_all`'s ``digests`` (none once every
    file was checked)."""
    if not whole:
        return {"files": [list(f) for f in gate.layout(path)]}
    return {"files": [list(f) for f in _rest(path, _stamp(path))]}


def prime(path: str, digests: Mapping[str, str]) -> dict:
    """Check the image at ``path`` with the host's sha256 of each file
    :func:`layout` gave (``{path: sha256}``), as :func:`vanilla` and a build
    check it, for every later call on the image as it is now (what an earlier
    call vouched for at ``path`` is dropped first, whatever the answer):
    ``{"release", "label"}``; ``gate.NotVanillaError`` names the first file
    that isn't the release's."""
    if not isinstance(digests, Mapping) or not all(isinstance(k, str) and isinstance(v, str)
                                                   for k, v in digests.items()):
        raise ValueError("prime: the digests are {path: sha256}")
    _STAMPS.clear()   # these digests decide, not an earlier stamp of the path: the site's look-alike File has the
                      # name, size and time of the image picked before it
    stamp = _stamp(path, digests=dict(digests))
    return {"release": stamp.release.name, "label": stamp.release.label}


def vanilla(path: str) -> dict:
    """The vanilla values the image at ``path`` holds for every slider at a
    site of its XBE (``catalog`` gives those ``None``: the wheel holds no
    game constant, Q174), ``{"release", "label", "packs": {pack: {slider:
    value}}}``, so a UI's track can hold them (D42)."""
    stamp = _stamp(path)
    with iso.Reader(stamp.path) as r:
        xbe = r.read("default.xbe")
    return {"release": stamp.release.name, "label": stamp.release.label, "packs": mods.vanilla(stamp.release, xbe)}


def image_info(path: str) -> dict:
    """What the Tools tab says of the image at ``path``: ``{"release",
    "label", "size", "kind", "whole"}``, its ``kind`` ``vanilla`` (its
    build files checked, D27: :func:`vanilla`'s check, shared; ``whole``
    once every file was, :func:`verify_all`), ``build`` (an AzurKit build:
    AzurKit's ``version`` that made it and its ``layers``, each in a few
    words, :func:`open_build` of the files it changed) or ``modded``
    (``differs``: its first file, in path order, that isn't its release's).
    It hashes nothing the image's kept check vouches for."""
    size = os.stat(path).st_size
    try:
        stamp = _stamp(path)
    except gate.NotVanillaError as exc:
        try:
            found = open_build(path, whole=False)
        except (OSError, ValueError):
            release = exc.release or gate.RELEASES[0]
            return {"release": release.name, "label": release.label, "size": size, "kind": "modded",
                    "whole": False, "differs": exc.why or str(exc)}
        release = next(r for r in gate.RELEASES if r.name == found["base"]["release"])
        return {"release": release.name, "label": release.label, "size": size, "kind": "build", "whole": False,
                "version": found.get("azurkit"), "layers": [_said(layer) for layer in found["layers"]]}
    return {"release": stamp.release.name, "label": stamp.release.label, "size": size, "kind": "vanilla",
            "whole": stamp.whole}


def _said(layer: Mapping) -> str:
    """A build's layer in a few words (the Tools tab's line)."""
    recipe = layer["recipe"]
    if layer["tool"] == "mods":
        return f"{len(recipe)} pack{'' if len(recipe) == 1 else 's'}"
    if layer["tool"] == generator.TOOL:
        return f"seed {recipe.get('seed')}"
    if layer["tool"] == characters.TOOL:
        return f"wears {recipe.get('species')}"
    ops = len(recipe.get("ops", []))
    return f"{ops} data edit{'' if ops == 1 else 's'}"


CHECK_ALL = "Checking every file"   # verify_all's line on a host's bar


def verify_all(path: str, digests: Mapping[str, str] | None = None, *,
               progress: Callable[[dict], object] | None = None) -> dict:
    """Check every file of the image at ``path`` (D27; the Tools tab's
    Verify every file): its build files' check is the one :func:`vanilla`
    and a build share (made here first if none is kept), so only the rest
    are hashed: on threads where the host has them (:data:`THREADS`), else
    as ``digests`` give them (the site's WebCrypto hashes of :func:`layout`'s
    ``whole`` files) or ``gate.verify`` hashes them; then the image's kept
    check is whole, so asked again, or by any later call, it hashes nothing.
    ``{"release", "label", "whole": true}``; ``gate.NotVanillaError`` names
    the first file, in path order, that isn't its release's.
    ``progress(record)`` follows the bytes it hashes (``check``)."""
    steps = Steps(progress)
    stamp = _stamp(path, steps)
    if not stamp.whole:
        if digests is None and THREADS:
            digests = _digests(path, steps, _rest(path, stamp), CHECK_ALL)
        stamp = gate.verify(path, releases=gate.RELEASES, progress=steps.counter("check", CHECK_ALL),
                            digests=digests, kept=stamp)
        _STAMPS.clear()   # the image's kept check is whole now, for the image as verify found it
        _STAMPS[(str(path), stamp.size, stamp.mtime_ns, stamp.ctime_ns)] = stamp
    return {"release": stamp.release.name, "label": stamp.release.label, "whole": True}


def files(path: str) -> dict:
    """The image's files (the Tools tab's list): ``{"files": [[path,
    offset, size]]}`` in path order, each where its bytes start in the image
    (the site's Extract slices them from the player's own File). It reads
    only the image's folders."""
    return {"files": sorted([list(f) for f in gate.layout(path, ("",))])}


def extract(path: str, member: str, out: str, *, progress: Callable[[dict], object] | None = None) -> dict:
    """Write the file ``member`` of the image at ``path`` to ``out`` (the
    app's Extract; the site slices it from the player's File), whole or not
    at all (a part file renamed into place): ``{"out", "size", "sha256"}``.
    Never over the image it reads or a vanilla image (D36): those are
    refused by name, as is a folder or a name the image hasn't.
    ``progress(record)`` follows the write (``write``, in bytes)."""
    target, source = Path(out), Path(path)
    _never_vanilla(target)
    if target.exists() and target.samefile(source):
        raise ValueError(f"{target}: it is the image it extracts from, which AzurKit never writes over")
    report = Steps(progress).counter("write", f"Extracting {member}")
    with iso.Reader(source) as r:
        try:
            entry = r.find(member)
        except FileNotFoundError:
            raise ValueError(f"{member}: the image has no such file") from None
        if entry.is_dir:
            raise ValueError(f"{member}: a folder, not a file: extract its files one by one")
        part = target.with_name(f"{target.name}.part")
        digest, done = hashlib.sha256(), 0
        try:
            with part.open("wb") as f:
                for data in r.chunks(entry):
                    f.write(data)
                    digest.update(data)
                    done += len(data)
                    if report is not None:
                        report(done, entry.size)
            part.replace(target)
        finally:
            part.unlink(missing_ok=True)
    return {"out": str(target), "size": entry.size, "sha256": digest.hexdigest()}


def _packs(recipe: object) -> dict[str, dict]:
    """The recipe's packs, normalized (``mods.normalize``), each with every
    pack it requires (``mods.missing``); every refusal named."""
    if not isinstance(recipe, Mapping):
        raise ValueError(f"a recipe is a JSON object, not {type(recipe).__name__}")
    if unknown := sorted(set(recipe) - set(RECIPE), key=str):
        raise ValueError(f"recipe: no key {', '.join(map(repr, unknown))} (its keys: {', '.join(RECIPE)})")
    packs = mods.normalize(recipe.get("packs", {}))
    if lost := mods.missing(packs):
        raise ValueError("; ".join(lost))
    return packs


AHEAD_WHOLE = 1 << 23   # a file another layer reads whole is read ahead under this: past it, a block's read is its size's


def _plan(recipe: Mapping, steps: Steps = Steps()) -> tuple[gate.Stamp, dict[str, bytes | iso.View], list[Layer],
                                                         Callable | None, generator.Prepared | None]:
    """:func:`_planning`, on a host that reads as it goes."""
    run = _planning(recipe, steps)
    try:
        next(run)
    except StopIteration as done:
        return done.value
    raise AssertionError("a plan with no reads ahead yields nothing")


def _planning(recipe: Mapping, steps: Steps = Steps(), ahead: bool = False):
    """The recipe's vanilla image (its build files checked, D27), the files
    read from it (a seed's levels only as ``generator.sections``' views, but
    any another layer reads), its randomizer's layer (its plan written, the
    first), each pack's layer, then its xbr operations' (the Data tool's,
    after the packs), the randomizer's read-back of the built image and its
    plan (``None`` without one); every refusal named. ``steps`` hears each
    stage. A generator, its ``StopIteration``'s value those: with ``ahead``
    it first yields a seed's ``generator.heads`` and ``generator.pages``, for
    a host whose reads are late to read them all at once, else nothing."""
    packs = own = _packs(recipe)
    ops = xbr.normalize(recipe.get("xbr", []))
    character = characters.normalize(recipe["character"]) if "character" in recipe else None
    if not isinstance(recipe.get("iso"), str):
        raise ValueError("recipe: iso names no image")
    prepared = None
    if "randomizer" in recipe and character is None:
        with noting(steps) as noted:
            noted("plan")
            prepared = generator.prepare(recipe["randomizer"], packs)
    elif "randomizer" in recipe:   # checked now; planned below, on the walk and roll the body's size folds
        generator.check(recipe["randomizer"])
    stamp = _stamp(recipe["iso"], steps)
    folded = vanilla = None
    inputs: dict[str, dict[str, float]] = {}
    if character is not None:   # the worn body's size folds into the walk and roll first (Modkit's size_params)
        packs, inputs, folded, vanilla = _worn(packs, character, stamp, steps)
        if "randomizer" in recipe:   # Modkit's randomize-full: the plan stands on the folded sliders (AZ-383)
            with noting(steps) as noted:
                noted("plan")
                prepared = generator.prepare(recipe["randomizer"], packs)
    chosen = {name: pack for name, pack in mods.PACKS.items() if name in packs}
    steps("read")
    with iso.Reader(stamp.path) as r:
        names = [f for pack in chosen.values() for f in pack.files()] + xbr.files(ops)
        names += list(characters.READS) if character is not None else []
        others = [file for file in dict.fromkeys(names) if file in stamp.release.files]
        base: dict[str, bytes | iso.View] = {}
        if prepared is not None:
            if ahead:
                yield generator.heads(prepared, r)
                yield generator.pages(prepared, r, [f for f in others if r.find(f).size < AHEAD_WHOLE])
            base = dict(generator.sections(prepared, r, others))
            others += [file for file in generator.files(prepared) if file not in base and file not in others]
        base |= {file: r.read(file) for file in others}
    layers, failed, judge = [], [], None
    if prepared is not None:
        layers.append(generator.plan_layer(prepared, base))   # a WriteError or LayerError: nothing planned on
        reasons = generator.movement_reasons(packs, catalog()["packs"])   # the worn body's join them below

        def judge(made: iso.Image, manifest: edits.Manifest) -> dict:
            steps("judge")
            return {generator.TOOL: generator.read_back(prepared, made, manifest.layers, manifest.conflicts,
                                                        reasons, progress=steps.counter("judge"), sparse=True)}
    failed += _pack_layers(stamp, chosen, packs, base, layers, inputs, steps)
    if folded is not None:   # its recipe holds the walk and roll as asked: a rebuild folds the size in again (AZ-829)
        asked = {"pack": rando_layer.SIZE_PACK, "params": own.get(rando_layer.SIZE_PACK, {})}
        layers = [dataclasses.replace(la, recipe=asked) if la.id == f"pack {rando_layer.SIZE_PACK}" else la
                  for la in layers]
    if character is not None and not failed:
        steps("dress", f"Dressing {character['species']}")
        layer, lines, body = characters.plan(character, vanilla, layers,
                                             characters.packs_view(stamp.release, mods.PACKS), folded,
                                             note=lambda label: steps("dress", label))
        if prepared is not None:   # Modkit's check_movement: its packs' reasons, then the body's
            reasons += body
        layers.append(Layer(layer.id, layer.tool, layer.kind, layer.recipe, layer.changes, layer.claims,
                            tuple(line.strip() for line in lines)))
    if ops:
        steps("data")
        try:
            layers.append(xbr.plan(ops, stamp.release, base))
        except ValueError as exc:
            failed.append(str(exc))
    if failed:
        raise ValueError("; ".join(failed))
    return stamp, base, layers, judge, prepared


def _worn(packs: Mapping, character: Mapping, stamp: gate.Stamp, steps: Steps = Steps()) -> tuple[dict, dict, float,
                                                                                                    object]:
    """``packs`` with the worn ``character``'s size s folded into
    player_physics' walk and roll (Modkit's ``size_params``: each x
    sqrt(s), the pack on), as a build and the Randomizer tab plan on them;
    the speed toggle's inputs, s and the image's ``ports.Vanilla`` (the
    size is the body dressed on its files)."""
    from azurkit.tools.characters import ports

    vanilla = ports.Vanilla(stamp.release, stamp.path, stamped=stamp)
    steps("size", f"Sizing {character['species']}")
    folded = characters.size(character, vanilla)
    enabled, params = rando_layer.size_params(list(packs), packs, folded)
    inputs = {}
    if (fold := params.get(rando_layer.SIZE_PACK, {}).pop(rando_layer.SIZE_FOLD, None)) is not None:
        inputs[rando_layer.SIZE_PACK] = {rando_layer.SIZE_FOLD: fold}   # the speed toggle's walk and roll
    return mods.normalize({name: params.get(name, {}) for name in enabled}), inputs, folded, vanilla


def _pack_layers(stamp: gate.Stamp, chosen: Mapping, packs: Mapping, base: Mapping[str, bytes], layers: list[Layer],
                 inputs: Mapping[str, dict] = {}, steps: Steps = Steps()) -> list[str]:
    """Each ``chosen`` pack's layer appended to ``layers`` (past their
    claims), in order; each pack's refusal, named."""
    failed = []
    for i, (name, pack) in enumerate(chosen.items()):
        steps("pack", f"Applying {name}", i, len(chosen))
        try:
            layers.append(mods.plan(pack, stamp.release, base, packs[name], [c for la in layers for c in la.claims],
                                    inputs.get(name)))
        except mods.PackError as exc:
            failed.append(str(exc))
    return failed


_MATCHES: dict[str, dict] = {}   # the G4 matches dressed in this process, by their recipe (a dress takes seconds)
_STAMPS: dict[tuple, gate.Stamp] = {}   # the last image's build files checked, by its path, size, mtime and ctime
_GAME: dict[tuple, tuple] = {}   # its config.xbr and characters.xbr, by the same


THREADS = sys.platform != "emscripten"   # a CPython host's (the app's, the CLI's); the site's worker has none
CORES_ENV = "AZURKIT_CORES"               # at most this many cores, where set (D984's capped profile)
INHERIT: Callable[[], Callable[[], object]] | None = None
"""A host's: asked on the caller's thread as a hash pool starts, what each of
that pool's threads calls first, so they run at the caller's priority (the
engine's ``procpool.inherit``: a job ahead's hash runs as low as the job)."""


def cores(most: int) -> int:
    """How many threads a host's parallel work takes: ``most``, at most the
    machine's cores and ``$AZURKIT_CORES``."""
    try:
        cap = int(os.environ.get(CORES_ENV) or 0)
    except ValueError:
        cap = 0
    return max(1, min(most, os.cpu_count() or 1, *([cap] if cap > 0 else [])))


def _stamp(path: str, steps: Steps = Steps(), digests: Mapping[str, str] | None = None) -> gate.Stamp:
    """The image at ``path``, its build files checked (D27:
    ``gate.verify``), once for the last image as it is now (its path, size,
    modification and change times): every call that reads it shares the
    check, and a touched image is checked again. Its files are hashed on
    threads where the host has them (:data:`THREADS`), else as ``digests``
    (a host's) or ``gate.verify`` hash them. ``steps`` hears the check's
    bytes."""
    at = os.stat(path)
    key = _key(path, at)
    if key not in _STAMPS:
        stamp = gate.vouched(path, whole=False, releases=gate.RELEASES, stat=at)
        if stamp is None:
            if digests is None and THREADS:
                digests = _digests(path, steps)
            stamp = gate.verify(path, whole=False, releases=gate.RELEASES, progress=steps.counter("check"),
                                digests=digests)
        _STAMPS.clear()
        _STAMPS[key] = stamp
    return _STAMPS[key]


def _key(path: str, at: os.stat_result) -> tuple:
    """:data:`_STAMPS`' key for the image at ``path`` as ``at`` (its ``os.stat``) finds it."""
    return str(path), at.st_size, at.st_mtime_ns, at.st_ctime_ns


def _rest(path: str, stamp: gate.Stamp) -> list[tuple[str, int, int]]:
    """Each file of the image at ``path`` (``gate.layout``) that ``stamp``,
    its kept check, doesn't vouch for."""
    return [f for f in gate.layout(path, ("",)) if not stamp.vouches(f[0])]


def _hashers(name: str):
    """A pool of :func:`cores` threads, at the caller's priority (:data:`INHERIT`)."""
    from concurrent.futures import ThreadPoolExecutor

    return ThreadPoolExecutor(cores(8), thread_name_prefix=name, initializer=INHERIT and INHERIT())


def _map(fn: Callable, items) -> list:
    """``map(fn, items)`` as a list, on :func:`cores` threads where the host
    has them (the engine's hashes of a build's changed files: hashlib lets go
    of the GIL), else on the caller's."""
    items = list(items)
    if not THREADS or len(items) < 2:
        return list(map(fn, items))
    with _hashers("azurkit-hash") as pool:
        return list(pool.map(fn, items))


def _digests(path: str, steps: Steps, files: list[tuple[str, int, int]] | None = None,
             label: str | None = None) -> dict[str, str]:
    """``{path: sha256}`` of ``files`` (``(path, offset, size)``), else the
    image's build files (``gate.layout``), each hashed from its own offsets
    (a file object of its own: hashlib lets go of the GIL) on :func:`cores` threads, the
    largest first, ``steps`` hearing them as ``check`` (its ``label``); a
    file the image ends inside is left to ``gate.verify``, which names it."""
    files = sorted(gate.layout(path) if files is None else files, key=lambda f: -f[2])
    total, done, lock = sum(f[2] for f in files), [0], threading.Lock()
    report = steps.counter("check", label)

    def one(file: tuple[str, int, int]) -> tuple[str, str | None]:
        name, at, left = file
        digest = hashlib.sha256()
        with open(path, "rb", buffering=0) as f:
            f.seek(at)
            while left:
                if not (data := f.read(min(iso.CHUNK, left))):
                    return name, None
                digest.update(data)
                left -= len(data)
                if report is not None:
                    with lock:
                        done[0] += len(data)
                        report(done[0], total)
        return name, digest.hexdigest()
    with _hashers("azurkit-check") as pool:
        return {name: sha for name, sha in pool.map(one, files) if sha is not None}


def _game(path: str, reading: Callable[[], object] | None = None) -> tuple[gate.Stamp, bytes, bytes]:
    """The image at ``path`` (its build files checked, D27) and its
    config.xbr and characters.xbr, kept for the last image read
    (``reading()`` is called before a read)."""
    stamp = _stamp(path)
    key = (str(stamp.path), stamp.size, stamp.mtime_ns, stamp.ctime_ns)
    if key not in _GAME:
        if reading is not None:
            reading()
        with iso.Reader(stamp.path) as r:
            _GAME.clear()
            _GAME[key] = (stamp, r.read(characters.CONFIG), r.read(characters.FILES[0]))
    return _GAME[key]


def pickers(given: Mapping, *, progress: Callable[[dict], object] | None = None) -> dict:
    """What the Characters tab shows (Step 4.3d; Modkit's Player page,
    ``tools.characters.picker``) for ``given``: its ``character`` (a
    recipe's; garret4 when none) on the image ``iso`` (none: the graded
    species alone) with Azurik-Custom-Content's ``manifest`` (``content``:
    as :func:`content` or the site's page read it; none: the content
    folder's alone): every usable species in its grade's colour, the
    untested greyed (``species``), the community entries with their state
    and, installed, their variants (``community``), the chosen model's info
    panel, Weapon box, springs, shapes and the options its recipe decides
    (``chosen``), and the character a build takes from the tab
    (``character``). A refusal names the field or the image.
    ``progress(record)`` hears its steps on an image (``read``, 2 of them):
    the image's model files read (once an image), then the models' view,
    so a host's bar moves while the tab waits (Step 4.3 round 3)."""
    if not isinstance(given, Mapping):
        raise ValueError("pickers: a JSON object")
    steps = Steps(progress)
    character = characters.normalize(given.get("character") or {"species": "garret4"})
    config = bodies = None
    if isinstance(given.get("iso"), str) and given["iso"]:
        _, config, bodies = _game(given["iso"], lambda: steps("read", "Reading your image's models", 0, 2))
        steps("read", "Reading the models", 1, 2)
    from azurkit.tools.characters import content as kit
    from azurkit.tools.characters import picker

    manifest = (given.get("content") or {}).get("manifest")
    entries = kit.states(kit.check(manifest) if manifest else None, kit.installed())
    return picker.view(config, bodies, character, {"entries": entries}, kit.ROOT)


def _dress(recipe: Mapping) -> dict:
    """:func:`match`'s answer for ``recipe`` and, for a variant, its
    dress's ``preview`` (``picker.dressed``), kept for this process."""
    from azurkit.tools.characters import _player_variants as variants
    from azurkit.tools.characters import picker, ports

    packs = _packs(recipe)
    if "character" not in recipe:
        raise ValueError("match: the recipe wears no character")
    character = characters.normalize(recipe["character"])
    if not isinstance(recipe.get("iso"), str):
        raise ValueError("recipe: iso names no image")
    stamp = _stamp(recipe["iso"])
    key = json.dumps([str(stamp.path), stamp.release.name, character, packs], sort_keys=True)
    if key not in _MATCHES:
        vanilla = ports.Vanilla(stamp.release, stamp.path, stamped=stamp)
        chosen = {name: pack for name, pack in mods.PACKS.items() if name in packs}
        with iso.Reader(stamp.path) as r:
            names = [f for pack in chosen.values() for f in pack.files()] + list(characters.READS)
            base = {file: r.read(file) for file in dict.fromkeys(names) if file in stamp.release.files}
        layers: list[Layer] = []
        if failed := _pack_layers(stamp, chosen, packs, base, layers):
            raise ValueError("; ".join(failed))
        found, staging = characters.match(character, vanilla, layers, characters.packs_view(stamp.release, mods.PACKS))
        found["text"] = {k: picker.match_text(v) for k, v in found["values"].items() if v is not None}
        if variants.resolve(character["species"], character.get("variant_file")) is not None:
            found["preview"] = picker.dressed(staging, character["species"])
        while len(_MATCHES) >= 16:
            _MATCHES.pop(next(iter(_MATCHES)))
        _MATCHES[key] = found
    return _MATCHES[key]


def match(recipe: Mapping, *, progress: Callable[[dict], object] | None = None) -> dict:
    """The G4 buttons' values (P52, D358: Modkit's match-Garret) for
    ``recipe``'s character dressed from its image over its packs:
    ``{"values": {slider: value or None}, "text": {slider: what its box
    shows: 4 figures rounded up, never short of garret4}, "why": {slider:
    why none matches}}`` for Model size (``scale``), Attack reach, speed
    and damage (at the recipe's Attack speed), each read at the other
    sliders as set; garret4's own body matches at 1 throughout
    (``tools.characters.match``). The answer of a recipe once matched is
    kept for this process. A refusal names what can't dress.
    ``progress(record)`` hears its dress on the ``dress`` stage, its serial
    steps counted ("the dress, k of n", ``core.progress.note``) and the
    swap's items inside each (the host's ``pool.TICK``)."""
    with noting(Steps(progress)) as steps:
        steps("dress")
        found = _dress(recipe)
    return {k: json.loads(json.dumps(found[k])) for k in ("values", "text", "why")}


def preview(recipe: Mapping) -> dict:
    """``recipe``'s character drawn from the front and from behind
    (D772, D919: ``draw.py``, numpy, no Blender): ``{"front": PNG bytes,
    "back": PNG bytes}``, 160 px each. A species' body is drawn from the
    image at once; a variant's from one dress of it over the recipe's packs
    (the dress :func:`match` reads, kept for this process; seconds, a
    detailed one minutes), never its base's picture. A refusal names the
    species or the image."""
    from azurkit.tools.characters import _player_variants as variants
    from azurkit.tools.characters import picker

    if not isinstance(recipe, Mapping) or "character" not in recipe or not isinstance(recipe.get("iso"), str):
        raise ValueError("preview: a recipe naming its image and character")
    character = characters.normalize(recipe["character"])
    if variants.resolve(character["species"], character.get("variant_file")) is not None:
        return dict(_dress(recipe)["preview"])
    _, config, bodies = _game(recipe["iso"])
    return picker.preview(bodies, picker.body_of(config, bodies, character["species"]))


_SPOILERS: dict[str, tuple[generator.Prepared, dict]] = {}   # the last build's spoiler left out, by its plan's sha256


def _report(made: edits.Manifest, prepared: generator.Prepared | None, steps: Steps = Steps(),
            spoiler: bool = True) -> dict:
    out = {"release": made.release.name, "label": made.release.label,
           "layers": [{"id": la.id, "sites": len({c.group for c in la.changes}),
                       "bytes": sum(len(c.after) for c in la.changes)} for la in made.layers],
           "result": dict(made.result), "conflicts": [str(c) for c in made.conflicts],
           "notes": [note for la in made.layers for note in la.notes]}
    if prepared is not None:
        verdict = made.verdicts[generator.TOOL]
        tracking.prime(prepared.plan.doc, prepared.logic)
        out |= {"randomizer": verdict, "plan": prepared.plan.doc}
        if spoiler:
            steps("spoiler")
            out["spoiler"] = generator.spoiler(prepared, verdict)
        else:   # kept for spoiler(plan, built=True)
            _SPOILERS.clear()
            _SPOILERS[prepared.plan.doc["sha256"]] = (prepared, verdict)
    return out


def image(recipe: Mapping, *, progress: Callable[[dict], object] | None = None,
          spoiler: bool = True) -> tuple[iso.Image, dict]:
    """The image ``recipe`` builds, unwritten, and its report: the release,
    each layer's sites and bytes, the sha256 of each file that differs from
    vanilla, every conflict (D28) and each layer's notes (a slider value
    past float32's range, written as the infinity it saturates to, Q110);
    with a randomizer, its verdict (``randomizer``: the seed, share string,
    settings, plan sha256, the movement sliders it stands on,
    ``logic_verified`` with each reason it is false, ``why_not``, and the
    placements a later layer changed, ``conflicts``) and its spoiler
    (``spoiler``: the text of Modkit's ``randomize-full --spoiler`` file; left
    out with ``spoiler`` false, then :func:`spoiler` of its plan with
    ``built`` gives it) and its plan (``plan``: the plan file's object, which
    :func:`tracker` reads). ``progress(record)`` hears each named stage
    (``core.progress``): checking the image (its bytes, the first time),
    planning the seed (and the planner's notes: placing the items), sizing
    and dressing the body, reading its files, applying each pack (done of
    total), the data edits, laying out the image (each file composed and
    hashed, done of total), reading it back against the plan (each level
    file, done of total) and writing the spoiler; an exception it raises stops the
    build."""
    steps = Steps(progress)
    stamp, base, layers, judge, prepared = _plan(recipe, steps)
    steps("layout")
    made, manifest = edits.image(stamp, layers, base, judge=judge, map=_map, progress=steps.counter("layout"))
    return made, _report(manifest, prepared, steps, spoiler)


def image_staged(recipe: Mapping, *, progress: Callable[[dict], object] | None = None, spoiler: bool = True,
                 ahead: bool = False):
    """:func:`image` for a host that hashes the build's changed files itself
    (the site's worker: WebCrypto, off its engine's thread), as a generator
    (``edits.staged``): it yields ``{key: bytes | iso.Patched}`` once they are
    composed and is sent ``{key: sha256}``, each one's (``None`` first, if the
    host hashes them while the image's layout runs, then the shas at the next
    yield; a :class:`iso.Patched`'s md5 too, at once), and returns ``(image,
    report)``, :func:`image`'s, byte for byte, as its ``StopIteration``'s
    value. Its refusals are :func:`image`'s; a key missing from the shas is a
    ``ValueError`` naming it. With ``ahead``, for a host whose reads are late,
    it first yields twice at most a list of ``(image offset, size)``, what it
    reads next, and is resumed once those are at hand (:func:`_planning`)."""
    steps = Steps(progress)
    stamp, base, layers, judge, prepared = yield from _planning(recipe, steps, ahead)
    steps("layout")
    made, manifest = yield from edits.staged(stamp, layers, base, judge=judge, map=_map,
                                             progress=steps.counter("layout"))
    return made, _report(manifest, prepared, steps, spoiler)


def image_checks(made: iso.Image, report: Mapping) -> list[list]:
    """``[path, image offset, size, sha256]`` of each of ``made``'s files the
    build vouches for (``report``'s, :func:`image`'s): what it changed by its
    result, the rest by the release's manifest. The site's Save hashes what it
    hands the browser against them, as a File may read otherwise than it did
    at the build (Firefox's, of a file changed on disk, silently: D35). The
    root files a build adds are its own bytes, so they aren't listed; nor is
    what lies between files, which no file of the game reads."""
    files = next(release for release in gate.RELEASES if release.name == report["release"]).files
    with iso.Reader(made) as r:
        return [[e.path, r.start(e), e.size, report["result"].get(e.path) or files[e.path][1]]
                for e in r.entries() if not e.is_dir and e.size and (e.path in report["result"] or e.path in files)]


def save(made: iso.Image, out: str, *, progress: Callable[[dict], object] | None = None,
         sha256: Callable[[], str] | None = None) -> dict:
    """Write ``made``, an image :func:`image` returned, to ``out`` (never its
    input or a vanilla image, D36) as :func:`build` writes its recipe's,
    without planning it again: ``{"out", "size", "sha256"}``. An input that
    changed since the build read it is refused by name (D27), with nothing
    written. ``progress(record)`` follows the write (``core.progress``'s
    ``write``, in bytes); an exception it raises cancels it, and nothing is
    written. ``sha256``: ``() -> str``, the image's sha256 as a host hashed
    it (``iso.digest``, from Build on), called once the bytes are written;
    else it is hashed as they are."""
    target = Path(out)
    _never_vanilla(target)
    sha = iso.pack(made, target, Steps(progress).counter("write"), sha256=sha256)
    return {"out": str(target), "size": target.stat().st_size, "sha256": sha}


def _never_vanilla(target: Path) -> None:
    for release in gate.RELEASES:
        if (vanilla := gate.find(release)) and target.exists() and target.samefile(vanilla):
            raise ValueError(f"{target}: it is the vanilla {release.label} image, which a build never writes over")


def build(recipe: Mapping, out: str, *, progress: Callable[[int, int], object] | None = None) -> dict:
    """Write the image ``recipe`` builds to ``out`` (never its input or a
    vanilla image, D36); :func:`image`'s report with the output's path,
    size and sha256. ``progress(done, total)`` follows the write; an
    exception it raises cancels it, and nothing is written."""
    stamp, base, layers, judge, prepared = _plan(recipe)
    target = Path(out)
    _never_vanilla(target)
    sha256, manifest = edits.build(stamp, layers, target, base=base, progress=progress, judge=judge, map=_map)
    return _report(manifest, prepared) | {"out": str(target), "size": target.stat().st_size, "sha256": sha256}


def open_build(path: str, *, whole: bool = True) -> dict:
    """The recipe of the AzurKit build at ``path``: its mods file (Q268), a
    preset of its base, AzurKit's version that built it, its layers'
    recipes (the packs; the xbr operations) and the sha256 of each file it
    changed, from its /azurkit.json, once every file of the image is
    checked against it (``edits.manifest.load``): a file no layer wrote
    that differs is drift, refused by name, as is an image that isn't an
    AzurKit build. With ``whole`` false only the files it changed are
    checked (the page's way: it offers the recipe, and builds from a
    vanilla image). Its recipe rebuilds the build from the vanilla image
    (:func:`read_mods`)."""
    return preset.from_manifest(edits.load(path, whole=whole)[1])


def read_mods(given: str | bytes | Mapping) -> dict:
    """A mods file (Q268: a preset or an AzurKit build's manifest, as JSON
    text or the object, or a share link) as a recipe's ``{"packs", "xbr"}``,
    normalized, and ``randomizer`` (the seed and share string a randomized
    build's plan replays from); ``packs`` only when it has a packs layer (a
    build's packs are then its packs, and no others). Every refusal named."""
    found = preset.read(given)
    out: dict = {}
    for layer in found["layers"]:
        if (layer["tool"], layer["kind"]) == ("mods", "packs"):
            out["packs"] = _packs({"packs": layer["recipe"]})
        elif (layer["tool"], layer["kind"]) == (xbr.TOOL, xbr.KIND) and set(layer["recipe"]) == {"ops"}:
            out["xbr"] = xbr.normalize(layer["recipe"]["ops"])
        elif (layer["tool"], layer["kind"]) == (generator.TOOL, generator.KIND):
            out["randomizer"] = generator.normalize(layer["recipe"])
        elif (layer["tool"], layer["kind"]) == (characters.TOOL, characters.KIND):
            out["character"] = _character(layer["recipe"])[0]
        else:
            raise ValueError(f"preset: no tool {layer['tool']!r} with {layer['kind']!r} "
                             "(AzurKit's: mods with packs, data with xbr, randomizer with plan, characters with "
                             "characters)")
    return out


def _character(given: object) -> tuple[dict, dict]:
    """A link's, a mods file's or a setup's character (``characters.normalize``
    less ``variant``, its recipe's sha12) and that as a link carries it:
    names and numbers only, so a recipe file's path (``variant_file``) is
    refused by name (Q174), as is a variant AzurKit holds no recipe of with
    that sha, naming what to Install or Update."""
    if not isinstance(given, Mapping):
        raise ValueError("preset: a character is an object naming its species")
    given = dict(given)
    sha = given.pop("variant", None)
    if "variant_file" in given:
        raise ValueError("preset: a character travels by name and numbers (Q174), never its recipe file's path "
                         "(variant_file): share a built-in or community variant")
    character = characters.normalize(given)
    from azurkit.tools.characters import _player_variants as variants

    worn = variants.resolve(character["species"])
    if sha is not None and not (isinstance(sha, str) and len(sha) == 12 and all(c in "0123456789abcdef" for c in sha)):
        raise ValueError(f"preset: the character's variant {sha!r} is no recipe sha")
    if sha is not None and worn is None:
        raise ValueError(f"preset: {character['species']!r} is a variant (recipe {sha}) this AzurKit has no recipe "
                         "of: install it from the Characters tab's community variants")
    if worn is not None and sha not in (None, worn.sha):
        raise ValueError(f"preset: {character['species']!r} is recipe {sha} there and recipe {worn.sha} here: "
                         "Install or Update it (the Characters tab's community variants), or update AzurKit")
    return character, character | ({"variant": worn.sha} if worn is not None else {})


def _shared(ops: list[dict]) -> list[dict]:
    """``ops``, refused by name unless each is a ``set`` (Q174: a link
    carries names and numbers, never a file's bytes)."""
    if raw := [str(k) for k, op in enumerate(ops, 1) if op["op"] != "set"]:
        raise ValueError(f"preset: a share link carries packs and set only (Q174), not xbr op {', '.join(raw)} "
                         "(replace_bytes)")
    return ops


def preset_encode(recipe: Mapping, report: Mapping | None = None) -> str:
    """The share link's fragment (``#p=…``) for ``recipe``'s randomizer
    (its seed, settings or share string and obsidian cost, checked as a
    build checks them), packs, normalized, and its ``set`` operations, never
    its image's path; given its build's report (:func:`image`), with the
    release it was built from and the sha256 of each file it changed. Names,
    numbers and hashes only (Q174): a recipe with a ``replace_bytes`` is
    refused by name; its ``character`` goes by name and numbers (a variant
    with its recipe's sha), and one naming a recipe file is refused."""
    return preset.encode(_preset(recipe, report))


def _preset(recipe: Mapping, report: Mapping | None = None, *, link: bool = True) -> dict:
    """:func:`preset_encode`'s preset of ``recipe`` (and its build's
    ``report``); a mods file's (``link`` false) keeps a ``replace_bytes``."""
    packs = _packs(recipe)
    character = _character(recipe["character"])[1] if "character" in recipe else None
    made = {"format": preset.FORMAT, "schema_version": preset.SCHEMA_VERSION, "azurkit": __version__,
            "layers": [{"tool": generator.TOOL, "kind": generator.KIND,
                        "recipe": generator.check(recipe["randomizer"])}] if "randomizer" in recipe else []}
    made["layers"].append({"tool": "mods", "kind": "packs", "recipe": packs})
    if character is not None:
        made["layers"].append({"tool": characters.TOOL, "kind": characters.KIND, "recipe": character})
    if ops := (_shared if link else list)(xbr.normalize(recipe.get("xbr", []))):
        made["layers"].append({"tool": xbr.TOOL, "kind": xbr.KIND, "recipe": {"ops": ops}})
    if report is not None:
        name = report.get("release") if isinstance(report, Mapping) else None
        release = next((r for r in gate.RELEASES if r.name == name), None)
        if release is None:
            raise ValueError("preset: the report names no release")
        made["base"] = {"kind": "vanilla", "release": release.name, "iso_sha256": release.iso_sha256}
        made["result"] = dict(report.get("result", {}))
    return made


def preset_decode(text: str) -> dict:
    """The preset in a link or its fragment (``preset.decode``), its packs
    normalized (``mods.normalize``), its ``set`` operations and its
    randomizer checked: a tool or pack AzurKit doesn't have, a value a
    slider refuses, a setting the randomizer refuses, a ``replace_bytes``
    (Q174) or a character naming a recipe file or a variant recipe this
    AzurKit doesn't hold is refused by name."""
    return _loaded(preset.decode(text))


def _loaded(found: dict, *, link: bool = True) -> dict:
    """``found``, a checked preset, as a UI loads it (:func:`preset_decode`'s
    checks); a mods file's (``link`` false) keeps a ``replace_bytes``."""
    for layer in found["layers"]:
        if (layer["tool"], layer["kind"]) == ("mods", "packs"):
            layer["recipe"] = _packs({"packs": layer["recipe"]})
        elif (layer["tool"], layer["kind"]) == (xbr.TOOL, xbr.KIND) and set(layer["recipe"]) == {"ops"}:
            layer["recipe"] = {"ops": (_shared if link else list)(xbr.normalize(layer["recipe"]["ops"]))}
        elif (layer["tool"], layer["kind"]) == (generator.TOOL, generator.KIND):
            layer["recipe"] = generator.check(layer["recipe"])
        elif (layer["tool"], layer["kind"]) == (characters.TOOL, characters.KIND):
            layer["recipe"] = _character(layer["recipe"])[1]
        else:
            raise ValueError(f"preset: no tool {layer['tool']!r} with {layer['kind']!r} "
                             "(AzurKit's: mods with packs, data with xbr, randomizer with plan, characters with "
                             "characters)")
    return found


def mods_file(given: Mapping) -> dict:
    """The Tools tab's mods files (Q268): ``{"text"}``, a mods file's JSON
    text (a preset or an AzurKit build's manifest) or a share link, read as
    a preset and checked as :func:`preset_decode` checks a link's (a
    ``replace_bytes`` kept: a file may carry bytes), for a UI to load:
    ``{"preset"}``; ``{"recipe"}`` (a UI's ``packs``, ``xbr``,
    ``randomizer`` and ``character``, as a build takes them) or
    ``{"preset"}`` (an AzurKit build's, :func:`open_build`'s) written as a
    mods file: ``{"text"}``, which ``azurkit build --mods`` and
    :func:`read_mods` take. Every refusal named."""
    if not isinstance(given, Mapping) or len(set(given) & {"text", "recipe", "preset"}) != 1:
        raise ValueError("mods_file: give one of text (a mods file to read), recipe or preset (one to write)")
    if "text" in given:
        if not isinstance(given["text"], str):
            raise ValueError("mods_file: text is a mods file's text")
        return {"preset": _loaded(preset.read(given["text"]), link=False)}
    made = _preset(given["recipe"], link=False) if "recipe" in given else given["preset"]
    return {"text": json.dumps(preset.check(made), indent=1, sort_keys=True, allow_nan=False) + "\n"}


DATA = ("what", "ops", "packs", "kind", "name", "table")   # what a Data tab's ask holds (:func:`data`)


def data(given: Mapping) -> dict:
    """The Data tab's config.xbr (Step 4.7a; ``tools.data``, from the
    vanilla file AzurKit ships, so before an image): ``{"what": "index"}``
    the tables by category and the pickers' lists, ``{"what": "view",
    "kind", "name"}`` one entity's cells (``kind`` player, critter, item,
    armor or weapon; the player has no ``name``), ``{"what": "table",
    "table"}`` a table as a grid. Each shows the tables as the recipe's
    ``xbr`` operations ``ops`` make them, every changed cell with its
    vanilla value, and marks each cell a slider of ``packs`` (the recipe's
    ticked packs and their values) also writes: the data edit wins, its
    layer last (D28). A pack whose values a build would refuse marks
    nothing here (the build names it). A refusal names the key, the view
    or the table."""
    if not isinstance(given, Mapping):
        raise ValueError("data: a JSON object")
    if unknown := sorted(set(given) - set(DATA), key=str):
        raise ValueError(f"data: no key {', '.join(map(repr, unknown))} (its keys: {', '.join(DATA)})")
    ops, what = given.get("ops") or [], given.get("what")
    if not isinstance(ops, list):
        raise ValueError("data: ops is a list of xbr operations")
    if what == "index":
        return datatool.index(ops)
    if what not in ("view", "table"):
        raise ValueError(f"data: what is index, view or table, not {what!r}")
    written = _written(given.get("packs") or {})
    if what == "view":
        return datatool.view(given.get("kind"), given.get("name"), ops, written)
    return datatool.table(given.get("table"), ops, written)


@functools.cache
def _config_tables() -> Mapping:
    return Document(datatool.vanilla()).tables


def _written(packs: object) -> list[tuple[int, int]]:
    """The spans ``(offset, size)`` of config.xbr each slider of ``packs``
    writes at its value, as a build plans it; what a build would refuse
    (``mods.salvage``'s) writes none here."""
    kept, _ = mods.salvage(packs)
    spans = []
    for name, params in kept.items():
        pack = mods.PACKS[name]
        values = pack.values(params)
        for spec in pack.sites:
            if not (isinstance(spec, mods.XbrParametricEdit) and spec.file == datatool.FILE):
                continue
            try:
                spans += [(at, len(after)) for _, at, after in spec.writes(_config_tables(), values[spec.name])]
            except (LookupError, ValueError):   # a cell it can't write: the build names it
                continue
    return spans


def data_edit(given: Mapping) -> dict:
    """A Data tab's edit, ``{"edit": {"table", "col", "row", "value"},
    "ops"}`` (a cell by position, as :func:`data` gives it, and the
    recipe's ``xbr`` operations): ``{"op", "ops"}``, the cell's ``set``
    operation (``None``: the cell back as vanilla) and ``ops`` with the
    cell's earlier operations dropped and it last (``tools.data.check``).
    A number cell takes any finite number (D23) but what int32 can't hold
    where the game reads one (D45); a refusal says why, with the cell's
    type and an example, never game bytes."""
    if not (isinstance(given, Mapping) and "edit" in given and set(given) <= {"edit", "ops"}):
        raise ValueError("data_edit: {edit: {table, col, row, value}, ops}")
    if not isinstance(ops := given.get("ops") or [], list):
        raise ValueError("data_edit: ops is a list of xbr operations")
    return datatool.check(given["edit"], ops)


def plan(recipe: Mapping, *, progress: Callable[[dict], object] | None = None) -> dict:
    """A randomizer plan: the fill of ``recipe``'s seed (any string) under
    the database's default settings (D144), a settings file's table
    (``settings``) or a share string (``share``), as Modkit's plan file's
    object (its format and generator, the seed, the attempt that passed,
    the settings, their share string and digest, the database's digest,
    every authored pool location's item, and the sha256 of the rest). The
    same recipe gives the same plan on every host. ``progress(record)``
    hears its stages (``core.progress``): the logic read, the fill (its
    items placed, k of n, counted inside its step) and the placements
    written. A refusal names the setting, or the progression items no
    attempt found a safe spot for."""
    return randomizer.plan(recipe, progress)


def spoiler(plan: Mapping, *, built: bool = False, progress: Callable[[dict], object] | None = None) -> dict:
    """``{"lines": [...]}``, the spoiler of a plan file's object: its
    settings, the spheres with each progression item's obtain and return
    paths, the traps and the rest. A plan from another database, format or
    generator, or an edited one, is refused by name. ``progress(record)``
    hears the logic read (``plan``: its checks counted while it is read
    cold, :func:`randomizer_logic`) and the spoiler written. ``built``: the
    spoiler of the randomized build of that plan this engine made last with
    :func:`image`'s ``spoiler`` false (its build's spoiler on the logic the
    build stands on, ``{"lines", "text"}``: the text its report would have
    held), refused by name once this engine keeps it no more (another
    build's since, or another engine)."""
    if not built:
        with noting(Steps(progress)) as steps:
            steps("plan", "Reading the randomizer's logic", 0, 2)
            randomizer.kept_logic()   # its checks counted while it is read cold
            steps("spoiler", None, 1, 2)
            return {"lines": randomizer.spoiler(plan)}
    sha = plan.get("sha256") if isinstance(plan, Mapping) else None
    if (kept := _SPOILERS.get(sha)) is None:
        raise ValueError("spoiler: this engine no longer keeps that build's spoiler: build it again")
    text = generator.spoiler(*kept)
    return {"lines": text.splitlines(), "text": text}


def randomizer_logic(*, progress: Callable[[dict], object] | None = None) -> dict:
    """``{}`` once the randomizer's logic is read, which a process does once
    (``kept_logic``): a host reads it ahead (D1008: the app's engine as the
    Randomizer or Tools tab opens), so a plan, a plan file's spoiler or a
    seed's build doesn't. ``progress(record)`` hears it (``plan``, "Reading
    the randomizer's logic"), its checks counted while it is read cold (a
    checkout's: the wheel and the frozen app ship it checked), on a seed
    plan's scale (its first of 3 steps, the checks under its 33 %), so a
    call that waits on it goes on in its own stages, never back."""
    with noting(Steps(progress)) as steps:
        steps("plan", "Reading the randomizer's logic", 0, 3)
        randomizer.kept_logic()
    return {}


def randomizer_settings(given: Mapping) -> dict:
    """What the Randomizer tab shows for ``given``: its ``settings`` (a
    settings file's table), ``share`` (a share string) or ``file`` (a
    settings file's text, D144's Load settings), its
    ``obsidian_cost`` (vanilla's when not given), the build's ``packs``
    (``{pack: {slider: value}}``, normalized) and ``character`` (the body
    it wears, whose size folds into the walk and roll as a build's does,
    from the vanilla image ``iso``; with none, ``body`` says the
    plan stands on garret4's): the settings as the tab
    holds them (format /2: its categories as they are), their share string
    with the packs' movement sliders (so a seed planned on it is a build's
    plan), a ``note`` when a share string holds
    other sliders (naming the body when a size fold is where they differ),
    each skip a setting can turn on (``skips``: its pick's
    id, name, rating, the ceiling's state and its toggle; D114, D275), the
    picks held and the forfeitable locations, what a build would leave
    unverified so far (``why_not``: the packs' movement past their logic
    floor, D83(c), a roll a skip on was proven at, an obsidian cost above
    vanilla's), the preflight's refusal (``preflight``, AZ-454; ``None``),
    the settings file of the settings (``file``, Save settings') and the
    skip groups (``groups``, D258: each group's picks with their variants'
    ratings, which a page compares with the Movement tier, ``tiers``).
    ``tools.randomizer.tab``; a refusal names the setting, the share string,
    the settings file or the pack."""
    if not isinstance(given, Mapping):
        raise ValueError(f"randomizer: a JSON object, not {type(given).__name__}")
    packs = _packs({"packs": given.get("packs", {})})
    worn = body = None
    if given.get("character") is not None:
        character = characters.normalize(given["character"])
        try:
            stamp = _stamp(given["iso"]) if isinstance(given.get("iso"), str) else None
        except (OSError, gate.NotVanillaError):   # an AzurKit build picked, say: the build's own refusal names it
            stamp = None
        if stamp is not None:
            mine = generator.sliders(packs)
            packs, _, size, _ = _worn(packs, character, stamp)
            worn = {"species": character["species"], "fold": math.sqrt(size), "sliders": mine}
        else:
            body = (f"Pick your vanilla image (1.) to fold {character['species']}'s size into the walk and roll, as "
                    "its build does: until then the share string and Track this seed stand on garret4's")
    view = randomizer.tab({k: v for k, v in given.items() if k not in ("packs", "character", "iso")},
                          generator.sliders(packs), worn, _bodies)
    return view | {"why_not": generator.movement_reasons(packs, catalog()["packs"]) + view["why_not"], "body": body}


def _bodies(fold: float) -> list[str]:
    """The species, each as the Characters tab first wears it, whose size
    folds ``fold`` (sqrt(s)) into the walk and roll on a release, by the
    swap's shipped sizes (D995)."""
    from azurkit.tools.characters import shipped

    return sorted({row["recipe"]["species"] for row in shipped.table().get("size", ())
                   if set(row["recipe"]) == {"species"}
                   and math.isclose(math.sqrt(float.fromhex(row["value"])), fold, rel_tol=1e-12)})


def tracker(given: Mapping, *, progress: Callable[[dict], object] | None = None) -> dict:
    """What the item tracker shows (D189, D249) for ``given``: ``plan`` (a
    plan file's object: :func:`plan`'s, or a randomized build's report's),
    ``marks`` (the spots collected: ``{"collected": [spot], "live": {spot:
    day clock or null}, "veto": [spot], "slot": a save slot or null}``, a
    live mark one the app's Live saw, a veto one a click took off), ``kit``
    (the element levels Live reads the game holding, which the reach holds
    past the marks, R1.41), ``held`` (Live's inventory, the Table's In game
    column), ``spoiler``, and ``toggle`` (a spot to mark or unmark) or
    ``reset``: the marks after it, the head line (the seed, share string,
    settings and skips on), the counter row (``status``: collected,
    reachable now, of how many, the sphere, victory in reach, the levels
    reached now and how many spots only a skip reaches), each spot's level,
    class, state (``got``, ``live``, ``near``, ``skip``: only with a skip,
    or ``far``) and item (once collected, or with ``spoiler``), and the
    Table's two trees (``table``: the items by kind and the spots by level,
    each row's collected, reachable now, left, total, where and the game's
    count). Modkit's tracker, the same verdicts on every host
    (``tools.randomizer.tracking``); ``progress(record)`` hears a plan's
    first view build its tracker and read the world map, the maps' exits
    counted on it; a refusal names what it refuses."""
    with noting(Steps(progress)) as steps:
        return tracking.view(given, progress=steps.report)


def art(path: str, part: str) -> dict:
    """One part of the item tracker's pictures, drawn from the image at
    ``path`` (Step 4.2c3: the wheel, the app and the site hold none; a
    host keeps what this gives and draws each part once),
    each file it reads checked against its release's vanilla file
    (``gate.NotVanillaError`` names one that isn't): ``"icons"`` gives
    ``{"pictures": {"icons/<icon>": PNG bytes}}``, every item's and
    barrier's icon (the game's own model at 20 px, Modkit's), and a level
    of the world map (``tracker()``'s ``world.art.parts``) ``{"pictures":
    {floor: PNG bytes}, "entry": its maps.json entry, "thumb": PNG bytes}``:
    each floor seen from above, where its exits, items, spots, barriers,
    features and gems lie on it (in pixels, with their floor; ``frame``
    maps the world's metres to them), and its main floor's world-map
    thumbnail, which :func:`art_world` takes. Each picture is Modkit's
    pixel for pixel (``tests/test_art.py``). numpy draws them: a host
    without it can't."""
    from azurkit.tools.randomizer import art as drawn

    with drawn.Vanilla(path) as reader:
        out = drawn.part(reader, part)
    return {key: ({name: drawn.png(img) for name, img in value.items()} if key == "pictures"
                  else drawn.png(value) if key == "thumb" else value) for key, value in out.items()}


def art_world(parts: Mapping[str, Mapping]) -> dict:
    """The world map from each level's :func:`art` part (``{level:
    {"entry", "thumb"}}``, every level of the world map), and the maps'
    index, Modkit's ``maps.json``: ``{"pictures": {"world": PNG bytes},
    "index": {"world": {"title", "levels": {level: [x, y, w, h]}},
    "levels": {level: entry}}, "text": maps.json's text}``."""
    from azurkit.tools.randomizer import art as drawn
    from azurkit.tools.randomizer.tracking import GRID

    if not isinstance(parts, Mapping) or set(parts) != set(GRID):
        raise ValueError(f"art_world: a part for each level of the world map ({', '.join(GRID)})")
    picture, world = drawn.world({level: drawn.unpng(p["thumb"]) for level, p in parts.items()})
    entries = {level: p["entry"] for level, p in parts.items()}
    text = drawn.index(entries, world)
    return {"pictures": {"world": drawn.png(picture)}, "index": json.loads(text), "text": text}


def restore(setup: object) -> dict:
    """A UI's remembered setup (D915: the packs it had ticked, each setting
    it had changed, its pack ticked or not, and a loaded recipe's config.xbr
    ``set`` operations, ``{"ticked": [pack], "values": {pack: {slider:
    value}}, "xbr": [operation]}``; never an image, its path or anything
    read from one), as the UI applies it, with ``dropped``: what no longer
    normalizes (a pack renamed or retired, a setting gone, a value its
    slider refuses, a pack without one it requires, an operation a link
    couldn't carry), each left out and named, never applied. A setup's
    ``randomizer`` (the tab's: ``on``, ``seed``, ``settings`` and
    ``obsidian_cost``, ``tools.randomizer.remembered``) comes back
    checked, or is dropped whole, by name, as is its ``character`` (the
    Characters tab's: a species or variant by name and its options, never a
    recipe file's path). It never refuses: a setup it can't read is dropped
    whole, by name."""
    if not isinstance(setup, Mapping) or not set(setup) <= set(SETUP):
        return {"ticked": [], "values": {}, "xbr": [], "dropped": ["your last setup (not one AzurKit reads)"]}
    ticked, dropped = setup.get("ticked", []), []
    if not isinstance(ticked, list):
        ticked, dropped = [], ["the ticked packs (not a list of names)"]
    dropped += [f"{name} (no such pack)" for name in ticked if not (isinstance(name, str) and name in mods.PACKS)]
    on = [name for name in mods.PACKS if name in ticked]
    while lost := [name for name in on if not set(mods.PACKS[name].requires) <= set(on)]:
        dropped += [f"{name} (needs {', '.join(r for r in mods.PACKS[name].requires if r not in on)})" for name in lost]
        on = [name for name in on if name not in lost]
    values, why = mods.salvage(setup.get("values", {}))
    ops, kept = setup.get("xbr", []), []
    if not isinstance(ops, list):
        ops, why = [], [*why, "the config.xbr values (not a list)"]
    for k, op in enumerate(ops, 1):
        try:
            if not (isinstance(op, Mapping) and op.get("op") == "set"):
                raise ValueError("a setup holds set operations only, Q174")
            kept += xbr.normalize([op])
        except ValueError as exc:
            why.append(f"config.xbr value {k} ({str(exc).replace('xbr op 1 (set): ', '')})")
    rando = {}
    if "randomizer" in setup:
        try:
            rando = {"randomizer": randomizer.remembered(setup["randomizer"])}
        except ValueError as exc:
            why.append(f"the randomizer's settings ({exc})")
    if "character" in setup:
        try:
            rando["character"] = _character(setup["character"])[0]
        except ValueError as exc:
            why.append(f"the character ({str(exc).removeprefix('preset: ')})")
    return {"ticked": on, "values": {name: v for name, v in values.items() if v}, "xbr": kept,
            "dropped": list(dict.fromkeys(dropped + why))} | rando


def _secure(url: str) -> bool:
    """Whether content may come over ``url``: https, or http to this computer alone (SEC-8)."""
    parts = urllib.parse.urlsplit(url)
    return parts.scheme == "https" or parts.scheme == "http" and parts.hostname in ("localhost", "127.0.0.1", "::1")


def _source(given: object = None) -> str:
    """The content source: ``$AZURKIT_CONTENT_SOURCE``, else ``given`` (a
    host's setting), else :data:`SOURCE`; an https URL (:func:`_secure`) or
    a folder's absolute path (``~`` expanded), refused by name otherwise."""
    source = os.environ.get(SOURCE_ENV) or given or SOURCE
    if not isinstance(source, str) or not source.strip():
        raise ValueError("content: the source is an https URL or a folder's path")
    source = source.strip()
    if urllib.parse.urlsplit(source).scheme in ("http", "https"):
        if not _secure(source):
            raise ValueError(f"content: {source} is plain http: a URL source is https (http only on this computer)")
        return source if source.endswith("/") else source + "/"
    folder = Path(source).expanduser()
    if not folder.is_absolute():
        raise ValueError(f"content: {source} is neither an https URL nor a folder's full path")
    return str(folder)


def _fetch(source: str) -> Callable[..., bytes]:
    """``fetch(path, size=None)``: the bytes of the file at ``path`` of
    ``source`` (:func:`_source`'s), reading at most one past ``size`` (the
    manifest's, SEC-9; for the manifest itself, what a manifest may hold),
    else the content folder's file limit, and refusing a file past it;
    ``OSError`` names what failed. CPython hosts' (the app's, the CLI's):
    the site fetches in its page."""
    from azurkit.tools.characters import content

    def fetch(path: str, size: int | None = None) -> bytes:
        most = content.MAX_FILE if size is None else size
        if not source.startswith(("http://", "https://")):
            where = str(Path(source) / path)
            with open(where, "rb") as f:
                data = f.read(most + 1)
        else:
            import urllib.request

            where = urllib.parse.urljoin(source, urllib.parse.quote(path))
            try:
                with urllib.request.urlopen(where, timeout=60) as reply:
                    if not _secure(reply.geturl()):   # a redirect's end is held to the source's rule
                        raise OSError(f"redirected to {reply.geturl()}, which isn't https")
                    data = reply.read(most + 1)
            except OSError as exc:   # urllib's HTTPError and URLError are OSErrors
                raise OSError(f"{where}: {getattr(exc, 'reason', exc)}") from None
        if len(data) > most:
            raise OSError(f"{where}: past the {most:,} bytes " + (
                "a manifest may hold" if path == content.MANIFEST else "a content file may hold" if size is None
                else "its manifest lists"))
        return data
    return fetch


def content(given: Mapping | None = None) -> dict:
    """Azurik-Custom-Content as the Characters tab lists it (D913): the
    ``source`` read (:data:`SOURCE`, a host's setting ``given["source"]``, or
    ``$AZURKIT_CONTENT_SOURCE``), its manifest checked
    (``tools.characters.content.check``; the last one fetched, kept in the
    content folder, when the source can't be read, with ``why``), each
    entry's state against what the content folder holds (``entries``:
    install, installed at its version, or update, kept until its Update)
    and ``installed`` (the folder's ``installed.json``). CPython's: the
    site's page fetches, and its worker checks (:func:`content_check`)."""
    from azurkit.tools.characters import content as kit

    given = given or {}
    source, why, manifest = _source(given.get("source")), None, None
    try:
        raw = _fetch(source)(kit.MANIFEST, kit.MAX_MANIFEST)
        manifest = kit.check(raw)
        kit.ROOT.mkdir(parents=True, exist_ok=True)
        (kit.ROOT / kit.MANIFEST).write_bytes(raw)   # the last fetched, listed while the source can't be read
    except (OSError, ValueError) as exc:
        why = f"can't read {source}: {exc}"
        try:
            manifest = kit.check((kit.ROOT / kit.MANIFEST).read_bytes())
        except (OSError, ValueError):
            manifest = None
    record = kit.installed()
    return {"source": source, "manifest": manifest, "why": why, "entries": kit.states(manifest, record),
            "installed": record}


def content_install(given: Mapping) -> dict:
    """Install (or Update) the entry ``given["id"]`` of the content source
    (``given["source"]``, as :func:`content` reads it) into the content
    folder, with the entries it requires: every file's size and sha256
    checked before anything is written (D35), ``installed.json`` written
    last (``tools.characters.content.install``); :func:`content`'s view
    after it. A refusal names the entry and the file."""
    from azurkit.tools.characters import content as kit

    if not isinstance(given, Mapping) or not isinstance(given.get("id"), str):
        raise ValueError("content: name the entry to install")
    source = _source(given.get("source"))
    fetch = _fetch(source)
    manifest = kit.check(fetch(kit.MANIFEST, kit.MAX_MANIFEST))
    sizes = {f["path"]: f["size"] for e in manifest["entries"] for f in e["files"]}
    kit.install(manifest, given["id"], lambda path, size=None: fetch(path, sizes.get(path) if size is None else size),
                source=source)   # each file read to at most its listed size (SEC-9)
    return content({"source": given.get("source")})


def content_check(given: Mapping) -> dict:
    """The site's half of Install (its page fetches, this checks):
    ``given["manifest"]`` checked, and with ``id`` and ``files`` (``{path:
    bytes}``, what the page fetched of the entry and those it requires)
    every file verified as :func:`content_install` verifies it
    (``tools.characters.content.verify``): ``{"manifest", "install": [each
    entry's id it writes, those required first]}``, or the refusal named: none
    goes below its installed version (``tools.characters.content.held_to``;
    the page reads only its own origin, so its source stays one)."""
    from azurkit.tools.characters import content as kit

    if not isinstance(given, Mapping):
        raise ValueError("content: a JSON object")
    manifest = kit.check(given.get("manifest"))
    if "id" not in given:
        return {"manifest": manifest, "install": []}
    chosen = kit.verify(manifest, given["id"], given.get("files") or {})
    kit.held_to(chosen, kit.installed())
    return {"manifest": manifest, "install": [e["id"] for e in chosen]}
