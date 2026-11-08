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
community entries) with :func:`community` (the packs the content folder
holds) and :func:`content_refusal`, the Data tab's :func:`data` and :func:`data_edit`
(config.xbr's cells, edited before an image is picked; the command line's
:func:`mods_diff`, what a mods file changes before a build,
:func:`mod_template`, vanilla values to edit, and :func:`entity_diff`, two
entities side by side), and the Tools
tab's :func:`image_info`, :func:`verify_all`, :func:`files`,
:func:`extract` and :func:`mods_file` (the image, its files, and mods
files saved and read), :func:`file_entry` (a replaced file's) and
:func:`saves`, and the Variants editor's :func:`variant_check` (Check
with game data), :func:`variant_colours`, :func:`variant_preview`,
:func:`variant_rows` and :func:`export_pngs` (its colour views, the quick
shape preview and its rows' PNGs, on the dress a Check keeps),
:func:`add_png` and :func:`add_wav` (a file copied into a variant's
folder) and :func:`base_bones`, :func:`own_sounds`, :func:`kit_throw`
and :func:`move_sources` (what its tabs read of a base species), with
the Variants view's :func:`variants` (its list), :func:`variant_open`,
:func:`variant_read` (a recipe as the library would hold it),
:func:`variant_save` (Save, Save as, New from this), :func:`variant_delete`,
:func:`variant_import` and :func:`variant_export` (a zip). JSON in and
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
it at the movement tier the build's movement sliders pick (D1066), or takes a
plan file's object as its ``plan`` (Modkit's ``randomize-full --plan``), exactly,
once it reads back on this database and is beatable under its settings,
and writes it as the build's first layer, before the packs (Modkit's ``mod_apply``
order); the built image is read back against the plan before anything is
written: a placement a later layer changed is a conflict that leaves the
logic unverified (D28), as does any moved slider, under which a seed isn't
promised beatable (D1064); any other difference fails the build (D35), and the
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
built-in, one of the recipe file ``variant_file`` names or, with none, one of
yours (``tools.characters.library``), its shapes sized by ``shapes``::

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

import contextlib
import dataclasses
import functools
import hashlib
import json
import math
import os
import re
import sys
import threading
import urllib.parse
from collections.abc import Callable, Mapping
from pathlib import Path

from azurkit import __version__
from azurkit.core import gate, iso, native
from azurkit.core.progress import Steps, noting
from azurkit.core.xbr import Document
from azurkit.core.xbr import document as xbrdoc
from azurkit.edits import manifest as edits
from azurkit.edits import files as replaced
from azurkit.edits import modkit, preset, xbr
from azurkit.edits.layer import Layer
from azurkit.tools import characters, mods, randomizer
from azurkit.tools import data as datatool
from azurkit.tools.mods import community as communal
from azurkit.tools.randomizer import generator, tracking
from azurkit.tools.randomizer import layer as rando_layer

__all__ = ["catalog", "verify", "vanilla", "layout", "prime", "image", "image_staged", "image_checks", "save", "build", "open_build", "read_mods",
           "preset_encode", "preset_decode", "plan", "spoiler", "randomizer_logic", "randomizer_settings", "tracker",
           "art", "art_world", "restore", "content", "content_install", "content_check", "pickers", "match", "preview",
           "data", "data_edit", "mods_diff", "mod_template", "entity_diff", "image_info", "verify_all", "files", "extract", "mods_file", "community",
           "content_refusal", "file_entry", "saves", "variant_check", "variant_pictures", "variant_colours",
           "variant_preview", "variant_rows", "export_pngs", "add_png", "add_wav", "base_bones", "own_sounds", "kit_throw", "move_sources",
           "variants", "variant_open", "variant_read", "variant_save", "variant_delete", "variant_import", "variant_export"]
RECIPE = ("iso", "packs", "xbr", "randomizer", "character", "community", "files")
SETUP = ("ticked", "values", "xbr", "randomizer", "character", "community")   # a UI's remembered setup (D915, :func:`restore`)
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
    requires in the same build (``requires_why``: why, finishing a sentence
    that starts with its name) and its sliders, in the canonical order. A
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
                       "requires_why": p.requires_why,
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
    """The recipe's packs, normalized (``mods.normalize``), with those its
    community packs set (``community.merge``), each with every pack it
    requires (``mods.missing``); every refusal named."""
    if not isinstance(recipe, Mapping):
        raise ValueError(f"a recipe is a JSON object, not {type(recipe).__name__}")
    if unknown := sorted(set(recipe) - set(RECIPE), key=str):
        raise ValueError(f"recipe: no key {', '.join(map(repr, unknown))} (its keys: {', '.join(RECIPE)})")
    packs = mods.normalize(recipe.get("packs", {}))
    if "community" in recipe:
        packs = communal.merge(packs, _picks(recipe))
    if lost := mods.missing(packs):
        raise ValueError("; ".join(lost))
    return packs


AHEAD_WHOLE = 1 << 23   # a file another layer reads whole is read ahead under this: past it, a block's read is its size's


def _picks(recipe: Mapping) -> list[dict]:
    """The community packs ``recipe`` names as a build takes them
    (``community.resolve``, from the content folder), each refusal named."""
    if "community" not in recipe:
        return []
    from azurkit.tools.characters import content as kit

    return communal.resolve(recipe["community"], kit.installed(), lambda path: (kit.ROOT / path).read_bytes())


def _plan(recipe: Mapping, steps: Steps = Steps(), picked: Mapping[str, bytes] | None = None,
          hashed: Mapping[str, str] | None = None) -> tuple[gate.Stamp, dict[str, bytes | iso.View], list[Layer],
                                                            Callable | None, generator.Prepared | None]:
    """:func:`_planning`, on a host that reads as it goes."""
    run = _planning(recipe, steps, picked, hashed)
    try:
        next(run)
    except StopIteration as done:
        return done.value
    raise AssertionError("a plan with no reads ahead yields nothing")


def _planning(recipe: Mapping, steps: Steps = Steps(), picked: Mapping[str, bytes] | None = None,
              hashed: Mapping[str, str] | None = None, ahead: bool = False):
    """The recipe's vanilla image (its build files checked, D27), the files
    read from it (a seed's levels only as ``generator.sections``' views, but
    any another layer reads), its randomizer's layer (its plan written, the
    first), each pack's layer, the character's, each community pack's edits,
    then its xbr operations' (the Data tool's), the files it replaces
    (``picked``, the bytes the player picked this session by path, ``hashed``
    their sha256 if the host hashed them; last, ``edits.files``), the
    randomizer's read-back of the built image and its plan (``None`` without
    one); every refusal named. ``steps`` hears each stage. A generator, its
    ``StopIteration``'s value those: with ``ahead`` it first yields a seed's
    ``generator.heads`` and ``generator.pages``, or a worn body's files, and
    before a dress that reads its voices (``characters.reads_voices``)
    their file (``characters.SOUNDS``), for a host whose reads are late to read
    them all at once, else nothing."""
    packs = own = _packs(recipe)
    picks = _picks(recipe)
    ops = xbr.normalize(recipe.get("xbr", []))
    entries = replaced.normalize(recipe.get("files", []))
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
        names += [f for pick in picks for f in xbr.files(pick["xbr"])]
        names += list(characters.READS) if character is not None else []
        others = [file for file in dict.fromkeys(names) if file in stamp.release.files]
        base: dict[str, bytes | iso.View] = {}
        if prepared is not None:
            if ahead:
                yield generator.heads(prepared, r)
                yield generator.pages(prepared, r, [f for f in others if r.find(f).size < AHEAD_WHOLE])
            base = dict(generator.sections(prepared, r, others))
            others += [file for file in generator.files(prepared) if file not in base and file not in others]
        elif ahead and character is not None:
            yield [(r.start(entry), entry.size) for entry in map(r.find, others)]   # a body's files, at once
        base |= {file: vanilla.read(file) if vanilla is not None and file in characters.READS else r.read(file)
                 for file in others}   # a worn body's files the bytes its dress reads (its Vanilla's): one copy
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
        sounds = [f for f in characters.SOUNDS if f in stamp.release.files]
        if (ahead and sounds and not (character.get("shapes") and prepared is None)
                and characters.reads_voices(character, stamp.release, layers, folded)):
            with iso.Reader(stamp.path) as r:   # the file its dress reads its voices from, at once
                yield [(r.start(entry), entry.size) for entry in map(r.find, sounds)]

        def dress():
            return characters.plan(character, vanilla, layers, characters.packs_view(stamp.release, mods.PACKS), folded,
                                   note=lambda label: steps("dress", label))
        # a reshape's layers before its dress are its image's, its own packs' and its size's (no seed's): one key
        layer, lines, body = (_reshape_kept("plan", stamp, character, own, dress)
                              if character.get("shapes") and prepared is None else dress())
        if prepared is not None:   # Modkit's check_movement: its packs' reasons, then the body's
            reasons += body
        layers.append(Layer(layer.id, layer.tool, layer.kind, layer.recipe, layer.changes, layer.claims,
                            tuple(line.strip() for line in lines)))
    for pick in picks:   # after the character, before the player's own edits, which win, reported (D28)
        try:
            layers.append(communal.layer(pick, stamp.release, base))
        except ValueError as exc:
            failed.append(str(exc))
    if ops:
        steps("data")
        try:
            layers.append(xbr.plan(ops, stamp.release, base))
        except ValueError as exc:
            failed.append(str(exc))
    if entries or picked:
        try:
            layers.append(replaced.plan(entries, picked or {}, stamp.release, hashed))
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
    folded = (_reshape_kept("size", stamp, character, None, lambda: characters.size(character, vanilla))
              if character.get("shapes") else characters.size(character, vanilla))
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
    and, installed, their variants (``community``), your own variants, each
    its title, base and grade or its refusal (``custom``), the chosen model's info
    panel, Weapon box, springs, shapes and the options its recipe decides
    (``chosen``), and the character a build takes from the tab
    (``character``). A refusal names the field or the image.
    ``progress(record)`` hears its steps on an image (``read``, 2 of them):
    the image's model files read (once an image), then the models' view,
    its body's weapons counted inside it ("the weapons, k of n": where the
    view's time goes), so a host's bar moves while the tab waits (Step 4.3
    round 3, Step 4.4be)."""
    if not isinstance(given, Mapping):
        raise ValueError("pickers: a JSON object")
    with noting(Steps(progress)) as steps:
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


def _under_a_dress(stamp: gate.Stamp, packs: Mapping) -> tuple[object, list[Layer]]:
    """The image a dress reads (a ``ports.Vanilla``) and the layers of the packs it stands on."""
    from azurkit.tools.characters import ports

    vanilla = ports.Vanilla(stamp.release, stamp.path, stamped=stamp)
    chosen = {name: pack for name, pack in mods.PACKS.items() if name in packs}
    with iso.Reader(stamp.path) as r:
        names = [f for pack in chosen.values() for f in pack.files()] + list(characters.READS)
        base = {file: r.read(file) for file in dict.fromkeys(names) if file in stamp.release.files}
    layers: list[Layer] = []
    if failed := _pack_layers(stamp, chosen, packs, base, layers):
        raise ValueError("; ".join(failed))
    return vanilla, layers


_DRESSED: dict[str, tuple[str, object]] = {}   # each kind's last reshape: its key and answer (:func:`_reshape_kept`)


def _reshape_kept(kind: str, stamp: gate.Stamp, character: Mapping, packs: Mapping | None,
                  work: Callable[[], object]) -> object:
    """``work()``'s answer, ``kind`` (``size`` or ``plan``) of the reshaped
    ``character`` on ``stamp``'s image over ``packs`` (a reshape's fold and
    dress: minutes), kept for this process's last reshape of that kind, so
    its pictures and its build make one dress between them, whichever comes
    first (one heap on the site, D1054). Its key holds what the dress reads
    besides the image (D35): the content folder's installed entries (a
    Content Update) and a recipe file's bytes and its WAVs' (``variant_file``,
    an edit to either), each by its sha256, not a stat an edit in place can
    leave as it was; its glTF, PNG and clip files are pinned by their sha256
    in it; a variant of yours by what its build reads (``library.stamp``).
    Each call keeps and returns its own key's answer, so the app's threads
    (a shape's pictures beside another's build) never cross theirs."""
    from azurkit.tools.characters import _player_variants as variants
    from azurkit.tools.characters import content as kit
    from azurkit.tools.characters import library

    recipes = character.get("variant_file")
    worn = recipes and variants.resolve(character["species"], recipes)
    read = [Path(recipes), *(variants.recipe_wav_files(worn) if worn else ())] if recipes else []
    key = json.dumps([str(stamp.path), stamp.release.name, character, packs, kit.installed(),
                      [p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest() for p in read],
                      None if recipes else library.stamp(character["species"])], sort_keys=True)
    if (kept := _DRESSED.get(kind)) is not None and kept[0] == key:
        return kept[1]
    _DRESSED.pop(kind, None)   # the last one's dress goes before this one is worked out (one heap)
    found = work()
    _DRESSED[kind] = (key, found)
    return found


def _reshaped(recipe: Mapping, character: Mapping) -> dict:
    """A reshaped variant's two pictures: from the dress a build of it makes
    (its layers to ``characters.plan``'s, which the app keeps for that
    build, and :func:`_reshape_kept` for this process), kept for this
    process."""
    from azurkit.tools.characters import library, picker, ports

    packs, stamp = _packs(recipe), _stamp(recipe["iso"])
    key = json.dumps(["reshaped", str(stamp.path), stamp.release.name, character, packs,
                      library.stamp(character["species"])], sort_keys=True)
    if key not in _MATCHES:
        stamp, _, layers, _, _ = _plan({"iso": recipe["iso"], "packs": packs, "character": dict(character)})
        files = characters.worn_by(ports.Vanilla(stamp.release, stamp.path, stamped=stamp), layers)
        while len(_MATCHES) >= 16:
            _MATCHES.pop(next(iter(_MATCHES)))
        _MATCHES[key] = picker.dressed(files, character["species"], character.get("variant_file"))
    return dict(_MATCHES[key])


def _dress(recipe: Mapping) -> dict:
    """:func:`match`'s answer for ``recipe`` and, for a variant, its
    dress's ``preview`` (``picker.dressed``), kept for this process."""
    from azurkit.tools.characters import _player_variants as variants
    from azurkit.tools.characters import library, picker, ports

    packs = _packs(recipe)
    if "character" not in recipe:
        raise ValueError("match: the recipe wears no character")
    character = characters.normalize(recipe["character"])
    if not isinstance(recipe.get("iso"), str):
        raise ValueError("recipe: iso names no image")
    stamp = _stamp(recipe["iso"])
    key = json.dumps([str(stamp.path), stamp.release.name, character, packs, library.stamp(character["species"])],
                     sort_keys=True)
    if key not in _MATCHES:
        vanilla, layers = _under_a_dress(stamp, packs)
        found, staging = characters.match(character, vanilla, layers, characters.packs_view(stamp.release, mods.PACKS))
        found["text"] = {k: picker.match_text(v) for k, v in found["values"].items() if v is not None}
        if variants.resolve(character["species"], character.get("variant_file")) is not None:
            found["preview"] = picker.dressed(staging, character["species"], character.get("variant_file"))
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
    detailed one minutes), never its base's picture; a reshaped variant's
    (``shapes``) from the dress of those shapes a build makes. A refusal
    names the species or the image."""
    from azurkit.tools.characters import _player_variants as variants
    from azurkit.tools.characters import picker

    if not isinstance(recipe, Mapping) or "character" not in recipe or not isinstance(recipe.get("iso"), str):
        raise ValueError("preview: a recipe naming its image and character")
    character = characters.normalize(recipe["character"])
    if variants.resolve(character["species"], character.get("variant_file")) is not None:
        return _reshaped(recipe, character) if character.get("shapes") else dict(_dress(recipe)["preview"])
    _, config, bodies = _game(recipe["iso"])
    return picker.preview(bodies, picker.body_of(config, bodies, character["species"]))


# ---------------------------------------------------------------- the Variants editor's calls (Step 4.6b)
VARIANT_RECIPE = "recipe.json"   # a variant folder's recipe file, {name: recipe} (Modkit's variant_library.RECIPE)
_WORN = {characters.XBE: "default.xbe", characters.CONFIG: "config.xbr", characters.FILES[0]: "characters.xbr",
         characters.FILES[1]: "fx.xbr"}   # what a Check reads of its dress
_CHECKED: dict[str, dict] = {}   # the last Check's dress before its colours (one heap, as _DRESSED)
_BODIES: dict[tuple, object] = {}   # the last base body the Colours views recoloured (a colour_preview.Base)


def _editing(given: object, what: str, *, image: bool = True) -> tuple[str, object, dict | None]:
    """The variant the editor has open in ``given``: ``name`` a built-in's
    (no ``recipe``), else its ``recipe`` read as ``folder``'s
    ``recipe.json`` would hold it (its files beside it), checked as the
    loader checks a recipe file: an unknown field or value, a number not
    finite, a built-in's name, each refused by name (D23, D35). Its name,
    the ``Variant`` and the recipe (``None``: a built-in's)."""
    from azurkit.tools.characters import _player_variants as variants

    if not isinstance(given, Mapping) or not isinstance(given.get("name"), str) or not given["name"]:
        raise ValueError(f"{what}: an object naming the variant (name), with its recipe and folder (a built-in: none)")
    if image and not isinstance(given.get("iso"), str):
        raise ValueError(f"{what}: iso names no image")
    name = given["name"]
    if "recipe" not in given:
        if name not in variants.builtins():
            raise ValueError(f"variant {name!r}: no built-in has that name (give its recipe and folder)")
        return name, variants.builtins()[name], None
    recipe = given["recipe"]
    if not isinstance(recipe, Mapping):
        raise ValueError(f"variant {name!r}: its recipe is not an object of recipe fields")
    if not isinstance(given.get("folder"), str) or not given["folder"]:
        raise ValueError(f"variant {name!r}: folder names no folder for its files (its library folder)")
    try:
        found = variants.load_variants(json.dumps({name: recipe}), str(Path(given["folder"]) / VARIANT_RECIPE),
                                       tuple(variants.builtins()))
    except (TypeError, RecursionError) as exc:   # the loader's lookup in a list; JSON nested too deep
        raise ValueError(f"variant {name!r}: not a recipe ({type(exc).__name__}: {exc})") from None
    return name, found[name], dict(recipe)


def _edit_key(given: Mapping, recipe: Mapping | None, leave: tuple[str, ...] = ()) -> str:
    """An edit's identity: the image, the variant's name, folder and packs and its recipe but the fields ``leave``."""
    stamp = _stamp(given["iso"])
    shown = None if recipe is None else {k: v for k, v in recipe.items() if k not in leave}
    return json.dumps([str(stamp.path), stamp.release.name, given["name"], given.get("folder"), shown,
                       _packs({"packs": given.get("packs", {})})], sort_keys=True)


def _place(given: Mapping) -> str:
    """The image and packs an edit dresses over: a quick preview moves a
    kept Check's dress made over the same, whatever the edit's name or
    folder (a built-in checked by its name, then dragged: an edit of it)."""
    stamp = _stamp(given["iso"])
    return json.dumps([str(stamp.path), stamp.release.name, _packs({"packs": given.get("packs", {})})])


def _dressing(given: Mapping, recipe: Mapping | None, steps: Steps = Steps()) -> tuple[dict[str, bytes], list[str]]:
    """``default.xbe``, config.xbr, characters.xbr and fx.xbr as a build of
    the edit (over ``given``'s ``packs``) writes them, and its dress's
    lines: a built-in's by name, and yours as saved (its ``recipe.json`` in
    the library holds the edit) by name too, as its Build dresses it, so the
    two share one dress key (``characters.cache_key``: one dress in the
    app's store); any other edit from its
    recipe written for the dress beside its files (a hidden file in its
    folder, removed after; a folder not made yet: a temporary one), as
    ``variant_file`` names it, its dress kept by what it holds."""
    import tempfile

    from azurkit.tools.characters import ports

    name = given["name"]
    with contextlib.ExitStack() as stack:
        file = None
        if recipe is not None and not _saved_as(given, name, recipe):
            folder = Path(given["folder"])
            if not folder.is_dir():
                folder = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="azurkit-variant-")))
            file = folder / f".{name}.edit-{os.getpid()}-{threading.get_ident()}.json"
            stack.callback(file.unlink, missing_ok=True)
            file.write_text(json.dumps({name: recipe}, indent=1) + "\n", encoding="utf-8")
        character = {"species": name} | ({"variant_file": str(file)} if file else {})
        try:
            stamp, _, layers, _, _ = _plan({"iso": given["iso"], "packs": given.get("packs", {}),
                                            "character": character}, steps)
        except (ValueError, OSError) as exc:   # named as the editor holds it: its folder, its recipe.json
            if file is None:
                raise
            said = str(exc).replace(file.name, VARIANT_RECIPE)
            raise ValueError(said.replace(str(file.parent), given["folder"])) from None
        files = characters.worn_by(ports.Vanilla(stamp.release, stamp.path, stamped=stamp), layers, _WORN)
    edit = re.compile(rf"\.{re.escape(name)}\.edit-\d+-\d+\.json")   # a kept dress's lines name the call's that kept it
    lines = [edit.sub(VARIANT_RECIPE, line) if file else line
             for la in layers if la.tool == characters.TOOL for line in la.notes]
    return files, lines


def _saved_as(given: Mapping, name: str, recipe: Mapping) -> bool:
    """Whether the edit dresses as your variant ``name`` as its library folder holds it (``given``'s folder, its
    ``recipe.json`` the edit but for their labels, which no dress reads: a title or notes typed since)."""
    from azurkit.tools.characters import _player_variants as variants
    from azurkit.tools.characters import library

    folder = Path(given["folder"])
    if folder != library.root() / name:
        return False
    try:
        saved = json.loads((folder / VARIANT_RECIPE).read_text(encoding="utf-8"))[name]
        if library.find(name) is None:   # yours as the library reads it (a label it refuses: the edit's own)
            return False
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        return False
    return isinstance(saved, dict) and ({k: v for k, v in saved.items() if k not in variants.LABELS}
                                        == {k: v for k, v in recipe.items() if k not in variants.LABELS})


def _check_key(given: Mapping, name: str, recipe: Mapping | None) -> str:
    """What a Check stands on, by content: the image and the edit
    (:func:`_edit_key`), each file its recipe names in its folder by its
    bytes, a glTF's with its buffers (``library.file_stamp``), and the
    content installed."""
    from azurkit.tools.characters import content as kit
    from azurkit.tools.characters import library

    files = None if recipe is None else library.file_stamp(Path(given["folder"]) / VARIANT_RECIPE,
                                                            library.text_of(name, dict(recipe)).encode())
    return json.dumps([_edit_key(given, recipe), files, kit.installed()], sort_keys=True)


def _colours_of(variant) -> tuple:
    """``variant``'s colours, each ``png`` op's file found in its folder and checked."""
    from azurkit.tools.characters import _player_variants as variants
    from azurkit.tools.characters import paint

    return paint.located(variant.colours, variants.colour_folder(variant)) if variant.colours else ()


def _uncoloured(variant, recipe: Mapping | None) -> Mapping | None:
    """The recipe a dress of ``variant`` before its colours is made of: its own, but garret4's own body's without
    them (his build recolours his rows in place, ``colour_preview.uncoloured``)."""
    from azurkit.tools.characters import colour_preview

    if recipe is None or colour_preview.uncoloured(variant) is variant:
        return recipe
    return {k: v for k, v in recipe.items() if k != "colours"}


def variant_check(given: Mapping, *, progress: Callable[[dict], object] | None = None) -> dict:
    """The Variants editor's Check with game data (Modkit's
    ``variant_library.check``; a bar op, D980, D999): the variant ``given``
    holds (``{"iso", "name", "recipe", "folder", "packs"}``: a built-in's
    by ``name`` alone, an edit by its recipe and the folder its files are
    in) dressed on the image as a build of it dresses it (``preview``'s
    path; seconds, a detailed one minutes). ``{"refusal": why, "sha",
    "bones"}`` when it can't dress (its base's own bones, where its Jiggle
    tab's springs rows go), else its dress's ``log`` lines, its ``sha``
    (sha256[:12] of what builds), the dressed ``body`` and its ``bones``
    (each ``[name, its parent's]``), its own load runs against the build's
    lines (``load``: ``own``, ``error`` and ``warning`` bytes, the lines of
    the machine its ``default.xbe`` is for, ``model_inspect.lines_ram``,
    and ``words``) and each ``effects`` row's bytes; its picture comes after
    the answer, from :func:`variant_pictures` (Step 4.6q: the answer
    first). This process keeps the dress before its colours for
    :func:`variant_pictures`, :func:`variant_colours`,
    :func:`variant_preview` and :func:`variant_rows`, and its answer: a
    Check of what it checked last, unchanged (:func:`_check_key`), answers
    at once (D1015), and a dress worked out before is taken as kept
    (``characters.cache_key``, by content), so only the first Check of new
    content dresses. A field or value the loader refuses is a
    ``ValueError`` naming it."""
    from azurkit.tools.characters import colour_preview, editor, picker, ports
    from azurkit.tools.characters import model_inspect as mi

    with noting(Steps(progress)) as steps:
        name, variant, recipe = _editing(given, "variant_check")
        place = _place(given)   # the image checked and the packs read first: their refusals are raised
        asked = _check_key(given, name, recipe)
        if (last := _CHECKED.get("last")) is not None and last["asked"] == asked:   # checked last, unchanged
            return dict(last["answer"])
        steps("dress", f"Dressing {name}")
        _CHECKED.clear()   # the last one's dress goes before this one is worked out (one heap)
        dresses = colour_preview.dresses(variant)
        try:
            files, log = _dressing(given, recipe, steps)
            bare = _uncoloured(variant, recipe)
            plain = files if bare is recipe or not dresses else _dressing(given, bare, steps)[0]
        except (ValueError, OSError) as exc:
            _, config, bodies = _game(given["iso"])
            try:
                bones = editor.bones(bodies, colour_preview.body_of(config, bodies, variant.base))
            except (ValueError, KeyError):
                bones = None
            return {"refusal": str(exc), "sha": variant.sha, "bones": bones}
        body, worn = picker.worn_body(files["config.xbr"]), files["characters.xbr"]
        xbe, own, stamp = files["default.xbe"], mi.own_runs(worn, body, files["fx.xbr"]), _stamp(given["iso"])
        with ports.building(ports.Build(ports.Vanilla(stamp.release, stamp.path, stamped=stamp),
                                        packs=characters.packs_view(stamp.release, mods.PACKS))):   # the packs' sites
            error, warning = mi.lines_for(mi.budget_of(xbe), mi.lines_ram(xbe, mi.DEFAULT_RAM))
        answer = {"refusal": None, "sha": variant.sha, "log": log, "body": body, "bones": editor.bones(worn, body),
                  "load": {"own": own["bytes"], "error": error, "warning": warning, "words": mi.own_words(own)},
                  "effects": editor.effect_bytes(log, variant.effects)}
        characters_xbr = plain["characters.xbr"]
        _CHECKED["last"] = {"place": place, "uncoloured": _edit_key(given, recipe, ("colours",)),
                            "edit": _edit_key(given, recipe), "variant": variant, "body": body,
                            "base": None, "pictures": None, "characters": characters_xbr, "kept": None,
                            "drawn": (lambda: colour_preview.base(characters_xbr, body, True)) if dresses else
                            (lambda: _base_of(given, name, variant, recipe)), "asked": asked, "answer": answer}
        return dict(answer)


def _kept_base(kept: dict):
    """The kept Check's body as the Colours views recolour it (a
    ``colour_preview.Base``), drawn the first time it is asked (Step 4.6q:
    after the Check's answer)."""
    if kept["base"] is None:
        kept["base"] = kept["drawn"]()
    return kept["base"]


def variant_pictures(given: Mapping) -> dict:
    """Check with game data's picture, after its answer (Step 4.6q, the
    Check design's L4: the answer first, then the picture): the variant
    ``given`` holds (as :func:`variant_check` takes it), as its last Check
    dressed it, drawn in its colours from the front and from behind
    (``front``, ``back``: PNG bytes, 160 px), once a Check. A ``ValueError``
    asks for the Check where none of this edit is kept (none yet, or it
    changed since)."""
    from azurkit.tools.characters import colour_preview

    name, variant, recipe = _editing(given, "variant_pictures")
    kept = _CHECKED.get("last")
    if kept is None or kept["edit"] != _edit_key(given, recipe):
        raise ValueError(f"variant {name!r}: no Check of it is kept (none yet, or it changed since): Check with game "
                         "data dresses it")
    if kept["pictures"] is None:
        kept["pictures"] = colour_preview.pictures(colour_preview.recoloured(_kept_base(kept), _colours_of(variant)))
    return dict(kept["pictures"])


def _checked(given: Mapping, recipe: Mapping | None) -> dict | None:
    """The kept Check of the same edit but its colours, else ``None``."""
    kept = _CHECKED.get("last")
    return kept if kept is not None and kept["uncoloured"] == _edit_key(given, recipe, ("colours",)) else None


def _base_of(given: Mapping, name: str, variant, recipe: Mapping | None):
    """The body the Colours views recolour: the image's own body of the
    variant's base, or for a recipe whose build changes it the kept Check's
    dress of the same edit (but its colours); a ``ValueError`` asks for the
    Check."""
    from azurkit.tools.characters import colour_preview

    if colour_preview.dresses(variant):
        if (kept := _checked(given, recipe)) is None:
            raise ValueError(f"variant {name!r}: its build changes its body (a mesh, textures or texture_scale): "
                             "Check with game data dresses it first")
        return _kept_base(kept)
    stamp, config, bodies = _game(given["iso"])
    body = colour_preview.body_of(config, bodies, variant.base)
    key = (str(stamp.path), stamp.release.name, body)
    if key not in _BODIES:
        _BODIES.clear()
        _BODIES[key] = colour_preview.base(bodies, body)
    return _BODIES[key]


def variant_colours(given: Mapping) -> dict:
    """The Colours tab's live recolour (Modkit's colour views, D539, D768):
    the variant ``given`` holds (as :func:`variant_check` takes it) drawn
    in its ``colours`` from the front and from behind (``front``,
    ``back``: PNG bytes, 160 px; its body the image's own of its base, or
    for a recipe whose build changes it the last Check's dress, which it
    asks for), each material row's ``tile`` (PNG, 64 px), ``palette`` (its
    six main colours, RGB) and texture ``size`` as recoloured (``rows``, by
    row), and ``across``, how wide the body draws against how tall (the
    views' portrait crop). A fraction of a second; a colour op the loader
    refuses is a ``ValueError`` naming it."""
    from azurkit.tools.characters import colour_preview, draw, paint

    name, variant, recipe = _editing(given, "variant_colours")
    colours = _colours_of(variant)
    base = _base_of(given, name, variant, recipe)
    parts, by_row, rows = colour_preview.recoloured(base, colours), colour_preview.ops_by_row(base, colours), {}
    for row, raw in base.rows().items():
        tex = paint.recoloured(raw, by_row[row]) if by_row.get(row) else raw
        rows[str(row)] = {"tile": draw.png_rgba(colour_preview.tile(tex), 6),
                          "palette": colour_preview.palette(tex).tolist(), "size": list(base.sizes.get(row, ()))}
    return {**colour_preview.pictures(parts), "rows": rows, "across": colour_preview.across(parts)}


def variant_preview(given: Mapping) -> dict:
    """The Shape tab's quick preview (Modkit's ``variant_library.preview``):
    the last Check's dress of the variant ``given`` holds (as
    :func:`variant_check` takes it), each drawn vertex moved to where the
    build's position steps put it at the edit's shape values on the
    Check's topology (``editor.moved``; no dress, so approximate: the finer
    triangles a build makes at the new values aren't made), drawn in its
    colours: ``{"front", "back": PNG bytes, "seconds"}``. A ``ValueError``
    asks for the Check where none of this variant is kept or its mesh
    changed beyond its shapes since."""
    import time

    from azurkit.tools.characters import colour_preview, editor

    started = time.perf_counter()
    name, variant, recipe = _editing(given, "variant_preview")
    kept = _CHECKED.get("last")
    ref, plain = kept and kept["variant"], variant.plain or variant.mesh
    if (kept is None or kept["place"] != _place(given) or plain is None or variant.base != ref.base
            or repr(plain) != repr(ref.plain or ref.mesh)):
        raise ValueError(f"variant {name!r}: no Check of its mesh is kept (none yet, another variant's, or its mesh "
                         "changed beyond its shapes since): Check with game data dresses it")
    base = _kept_base(kept)
    drawn = [(q.P, q.T) for q in base.parts]
    if kept["kept"] is None:   # its mesh prepared on the base's own body once a Check
        _, config, bodies = _game(given["iso"])
        kept["kept"] = editor.prepared(bodies, colour_preview.body_of(config, bodies, variant.base), ref, drawn)
    moved = base.moved(editor.moved(kept["kept"], variant, drawn))
    return {**colour_preview.pictures(colour_preview.recoloured(moved, _colours_of(variant))),
            "seconds": time.perf_counter() - started}


def variant_rows(given: Mapping, *, progress: Callable[[dict], object] | None = None) -> dict:
    """The Colours tab's Export, its pictures (Modkit's
    ``colour_preview.variant_rows``, Step 2.203): each material row's
    texture whole, recoloured as a build of the variant ``given`` holds
    (as :func:`variant_check` takes it) recolours it: ``{"body", "files":
    {"<name>_row<R>.png": PNG bytes}, "sizes": {row: [width, height]}}``,
    of the image's own body of its base, or for a recipe whose build
    changes it of the last Check's dress of the same edit (else dressed
    now: a bar op). An edited one comes back through :func:`add_png`."""
    from azurkit.tools.characters import colour_preview, picker

    with noting(Steps(progress)) as steps:
        name, variant, recipe = _editing(given, "variant_rows")
        _, config, worn = _game(given["iso"])
        if not colour_preview.dresses(variant):
            body = colour_preview.body_of(config, worn, variant.base)
        elif (kept := _checked(given, recipe)) is not None:
            worn, body = kept["characters"], kept["body"]
        else:
            steps("dress", f"Dressing {name}")
            files = _dressing(given, _uncoloured(variant, recipe), steps)[0]
            worn, body = files["characters.xbr"], picker.worn_body(files["config.xbr"])
        rows = colour_preview.rows(worn, body, _colours_of(variant))
    return {"body": body, "files": colour_preview.pngs(name, rows),
            "sizes": {str(r): [img.shape[1], img.shape[0]] for r, img in sorted(rows.items())}}


def export_pngs(given: Mapping, *, progress: Callable[[dict], object] | None = None) -> dict:
    """The Colours tab's Export (Step 2.203): :func:`variant_rows`' files
    written into the folder ``out`` (made if missing), each whole (a part
    file renamed), none when ``out`` holds one of their names already (an
    edited PNG is never overwritten, D35, D36): ``{"files": [names]}``."""
    if not isinstance(given, Mapping) or not isinstance(given.get("out"), str) or not given["out"]:
        raise ValueError("export_pngs: out names no folder to write the rows' PNGs into")
    found = variant_rows({k: v for k, v in given.items() if k != "out"}, progress=progress)
    out = Path(given["out"])
    if there := [n for n in found["files"] if (out / n).exists()]:
        raise ValueError(f"{out} holds {', '.join(there)} already: export into another folder (an edited PNG is "
                         "never overwritten)")
    out.mkdir(parents=True, exist_ok=True)
    for n, data in found["files"].items():
        part = out / f".{n}.{os.getpid()}.part"
        part.write_bytes(data)
        os.replace(part, out / n)
    return {"files": list(found["files"])}


def _folder_file(given: object, what: str) -> tuple[Path, Path]:
    if not isinstance(given, Mapping) or not all(isinstance(given.get(k), str) and given[k] for k in ("folder", "file")):
        raise ValueError(f"{what}: an object naming the variant's folder and the file to copy into it (file)")
    return Path(given["folder"]), Path(given["file"])


def add_png(given: Mapping) -> dict:
    """The Colours tab's Import (Step 2.203): ``file``, an edited PNG of a
    row's texture (8-bit RGB or RGBA, the texture's ``size``, [width,
    height], as :func:`variant_rows` gives it), copied whole into the
    variant's ``folder`` under a name of its own (``_2``, ``_3`` .. while
    another file has it; one there with the same bytes taken as it is):
    ``{"name", "sha256"}``, the row's ``png`` op's. A refusal names the file."""
    from azurkit.tools.characters import editor

    folder, file = _folder_file(given, "add_png")
    size = given.get("size")
    if not (isinstance(size, list) and len(size) == 2 and all(type(n) is int and n > 0 for n in size)):
        raise ValueError(f"add_png: size {size!r} is not the row's texture's [width, height]")
    name, sha = editor.add_png(folder, file, tuple(size))
    return {"name": name, "sha256": sha}


def add_wav(given: Mapping) -> dict:
    """The Sounds tab's Add (Step 2.164b): ``file``, a WAV the build reads
    (uncompressed integer PCM, mono or stereo, any rate), copied whole into
    the variant's ``folder`` under a name a recipe's ``wavs`` take (as
    :func:`add_png` names it): ``{"name"}``. A refusal names the file."""
    from azurkit.tools.characters import editor

    folder, file = _folder_file(given, "add_wav")
    return {"name": editor.add_wav(folder, file)}


def _species(given: object, what: str) -> tuple[gate.Stamp, bytes, bytes, str, str]:
    """``given``'s image (its config.xbr and characters.xbr) and ``species``, a species the player can wear or a
    body of one, with its body; a refusal names the field or the species."""
    from azurkit.tools.characters import colour_preview

    if not isinstance(given, Mapping) or not isinstance(given.get("iso"), str):
        raise ValueError(f"{what}: an object naming the image (iso) and a base species (species)")
    if not isinstance(given.get("species"), str) or not given["species"]:
        raise ValueError(f"{what}: species names no base species")
    stamp, config, bodies = _game(given["iso"])
    try:
        body = colour_preview.body_of(config, bodies, given["species"])
    except ValueError:
        raise ValueError(f"{what}: {given['species']!r} is no species or body of this image") from None
    return stamp, config, bodies, given["species"], body


def base_bones(given: Mapping) -> dict:
    """A base species' own body's bones in the image (``{"iso",
    "species"}``): ``{"body", "bones": [[name, its parent's], ...]}``,
    where a recipe's springs rows go before its Check dresses it."""
    from azurkit.tools.characters import editor

    _, _, bodies, _, body = _species(given, "base_bones")
    return {"body": body, "bones": editor.bones(bodies, body)}


def own_sounds(given: Mapping) -> dict:
    """The roles a base species' own sounds take as the player's, as its
    build binds them (``{"iso", "species"}``): ``{"roles": [...]}``; a base
    with any takes no ``voice`` or ``wavs`` of a recipe's (the build's
    refusal), garret4's none."""
    from azurkit.tools.characters import editor

    stamp, config, bodies, species, _ = _species(given, "own_sounds")
    with iso.Reader(stamp.path) as r:
        files = {"config.xbr": config, "characters.xbr": bodies, "fx.xbr": r.read(characters.FILES[1]),
                 "english.xbr": r.read(characters.SOUNDS[0])}
    try:
        return {"roles": list(editor.own_sounds(files, species))}
    except KeyError:
        raise ValueError(f"own_sounds: {species!r} is no species of critters_engine (a body has no sounds of its own)"
                         ) from None


def kit_throw(given: Mapping) -> dict:
    """What a base species' default weapon throws as the player's
    (``{"iso", "species"}``): ``{"throw": "rock" | "vase" | "", "columns":
    [the attack columns that throw it]}``; a recipe on it naming no
    weapon, whose own columns leave one of those, takes no projectile row
    (the build's refusal)."""
    from azurkit.tools.characters import editor

    _, config, bodies, species, _ = _species(given, "kit_throw")
    kind, columns = editor.kit_throw(config, bodies, species)
    return {"throw": kind, "columns": list(columns)}


def move_sources(given: Mapping) -> dict:
    """The clips the Moves tab offers a base species' body (``{"iso",
    "species"}``; D768, D785): ``{"columns"}`` (the attack columns a recipe
    may name, the roll's left out), ``"own"`` (its body's clips),
    ``"lenders"`` ({body: its clips}: garret4 and each humanoid body whose
    clips the bake can put on it) and ``"variants"`` ({built-in: [the body
    they're read on, its Blender clips]})."""
    from azurkit.tools.characters import editor, picker

    _, config, bodies, _, body = _species(given, "move_sources")
    worn = {species: b for species, b, _ in picker.species_list()}
    return editor.move_sources(config, bodies, body, worn).to_json()


# ------------------------------------------------- the Variants view's library calls (Step 4.6c, on Step 4.6a's)
UNSAVED = "unsaved"   # the working name of a recipe the library doesn't hold yet (a new one, an edited built-in)


def _grade(variant) -> str:
    """``variant``'s grade at its recipe's scale (``_player_variants.status``, the picker's): unseen till a sitting."""
    from azurkit.tools.characters import _player_variants as kinds

    return kinds.status(variant, variant.scale)[0]


def variants(given: Mapping | None = None) -> dict:
    """The Variants view's list (Modkit's Variant box): ``root``, the
    library's folder (yours each ``root/<name>``, the files its recipe
    names beside its ``recipe.json``); ``builtins``, each built-in
    variant's name, title, base, grade and ``community`` (the
    Azurik-Custom-Content entry whose files it needs, with ``content``'s
    ``manifest`` as :func:`pickers` takes it, else the content folder's
    alone: ``None``); ``yours``, each library folder's name with its title,
    base and grade, or its ``refusal``; ``species``, the species New may
    start on, none of which a variant of yours may be named as; ``unsaved``,
    the name a recipe not saved yet works under; ``grades``, each grade's
    words; and ``colours``, each grade's colour (the Models view's)."""
    from azurkit.tools.characters import _player_variants as kinds
    from azurkit.tools.characters import content as kit
    from azurkit.tools.characters import library, picker

    manifest = ((given or {}).get("content") or {}).get("manifest") if isinstance(given, Mapping) else None
    record = kit.installed()
    entries, held = kit.states(kit.check(manifest) if manifest else None, record), picker._variants_of(kit.ROOT, record)
    community = {}
    for name in kinds.builtins():
        entry = picker._entry_of(name, entries, held)
        community[name] = entry["id"] if entry else None
    return {"root": str(library.root()), "unsaved": UNSAVED, "grades": picker.GRADE_WORDS,
            "colours": picker.STATUS_COLOURS,
            "builtins": [{"name": name, "title": v.title, "base": v.base, "grade": _grade(v),
                          "community": community[name]} for name, v in kinds.builtins().items()],
            "yours": [{"name": e.name, "title": e.variant.title, "base": e.variant.base, "grade": _grade(e.variant)}
                      if e.variant is not None else {"name": e.name, "refusal": e.refusal} for e in library.listing()],
            "species": [name for name, _, _ in picker.species_list()]}


def _named(given: object, what: str) -> str:
    if not isinstance(given, Mapping) or not isinstance(given.get("name"), str) or not given["name"]:
        raise ValueError(f"{what}: an object naming the variant (name)")
    return given["name"]


def variant_open(given: Mapping) -> dict:
    """The recipe the Variants view opens variant ``name`` as (Modkit's
    ``_open``): a built-in's (``kind`` ``"built-in"``: its own recipe where
    it is ``from`` others, else one ``from`` it with its labels), yours as
    its ``recipe.json`` holds it (``"yours"``; a refused folder's recipe as
    far as it reads, else ``{}``), with its ``folder`` and its ``read``
    (:func:`variant_read`'s answer)."""
    from azurkit.tools.characters import _player_variants as kinds
    from azurkit.tools.characters import library

    name = _named(given, "variant_open")
    if name in kinds.builtins():
        recipe, kind = library.opened(name), "built-in"
    else:
        folder = library.root() / name
        if not kinds._NAME.match(name) or not folder.is_dir():
            raise ValueError(f"variant {name!r}: no built-in and none of yours")
        try:
            doc = json.loads((folder / library.RECIPE).read_text(encoding="utf-8"))
            recipe = doc[name] if isinstance(doc, dict) and isinstance(doc.get(name), dict) else {}
        except (OSError, ValueError, RecursionError):
            recipe = {}
        kind = "yours"
    folder = str(library.root() / (name if kind == "yours" else UNSAVED))
    shown = {"name": name if kind == "yours" else UNSAVED, "recipe": recipe, "folder": folder}
    return {"name": name, "kind": kind, "recipe": recipe, "folder": folder,
            "read": variant_read({**shown, "built_in": name} if kind == "built-in" else shown)}


def variant_read(given: Mapping) -> dict:
    """The recipe the Variants view has open (``{"name", "recipe"}``: its
    working name, yours or :data:`UNSAVED`) as the library would hold it
    (``library.checked``, a species' name refused too), never raised:
    ``{"sha", "base", "mode", "mesh", "grade"}`` (``mesh``: it brings a mesh
    of its own; ``grade``: ``built_in``'s, the built-in it was opened from,
    while the recipe is that one's as opened, else unseen) and its body as
    it builds (``size``, ``scale``, ``arms``, ``rotate``, ``weapon``: a
    recipe ``from`` another's from that one), or ``{"refusal"}``, the
    loader's or the library's words."""
    from azurkit.tools.characters import _player_variants as kinds
    from azurkit.tools.characters import library

    name = _named(given, "variant_read")
    recipe = given.get("recipe")
    if not isinstance(recipe, Mapping):
        return {"refusal": f"variant {name!r}: its recipe is not an object of recipe fields"}
    try:
        v = library.checked(library.text_of(name, dict(recipe)), name, library.root() / name / library.RECIPE)
        if name in library.species():
            raise ValueError(f"variant {name!r}: a species has that name, so a character can't name the variant")
    except ValueError as exc:
        return {"refusal": str(exc)}
    built = given.get("built_in")
    grade = (_grade(kinds.builtins()[built]) if isinstance(built, str) and built in kinds.builtins()
             and dict(recipe) == library.opened(built) else "unseen")
    return {"refusal": None, "sha": v.sha, "base": v.base, "mode": v.mode, "mesh": v.mesh is not None, "grade": grade,
            "size": v.size, "scale": v.scale, "arms": v.arms, "rotate": v.rotate, "weapon": v.weapon}


def _saved(name: str, given: Mapping) -> dict:
    """A written folder's answer: its name and folder, and with ``files`` its files (the site keeps them)."""
    from azurkit.tools.characters import library

    return {"name": name, "folder": str(library.root() / name)} | (
        {"files": library.files_of(name)} if given.get("files") else {})


def variant_save(given: Mapping) -> dict:
    """Save, Save as and New from this (Modkit's): ``{"name", "recipe"}``
    written again as your variant ``name`` (Save); with ``as``, a new
    folder of that name holding the recipe and copies of the files it names
    from ``from``'s folder (yours, the one open), one ``from`` a built-in an
    own copy (``library.copy_as``: every field its own). Each whole or
    nothing, a refusal naming why (D35). ``{"name", "folder"}``, and the
    folder's ``files`` when ``files`` is true."""
    from azurkit.tools.characters import library

    name = _named(given, "variant_save")
    recipe = given.get("recipe")
    if not isinstance(recipe, Mapping):
        raise ValueError(f"variant {name!r}: its recipe is not an object of recipe fields")
    if "as" not in given:
        library.save(name, dict(recipe))
        return _saved(name, given)
    new, source = given["as"], given.get("from")
    if not isinstance(new, str):
        raise ValueError(f"{new!r}: a variant's name is a lower-case letter, then lower-case letters, digits and _")
    files = library.root() / source if isinstance(source, str) and (library.root() / source).is_dir() else None
    library.copy_as(new, dict(recipe), files)
    return _saved(new, given)


def variant_delete(given: Mapping) -> dict:
    """Delete: your folder ``name`` and everything in it (``library.delete``): ``{"name"}``."""
    from azurkit.tools.characters import library

    name = _named(given, "variant_delete")
    library.delete(name)
    return {"name": name}


def variant_import(given: Mapping) -> dict:
    """Import: ``data``, an Export's zip or a ``recipe.json`` alone, as a
    new folder of yours (``library.import_``: its name free, the loader
    taking it, each file it names in the zip): ``{"name", "folder"}``, and
    its ``files`` when ``files`` is true. A refusal names what and why."""
    from azurkit.tools.characters import library

    if not isinstance(given, Mapping) or not isinstance(given.get("data"), (bytes, bytearray)):
        raise ValueError("variant_import: an object holding the zip's or recipe.json's bytes (data)")
    return _saved(library.import_(bytes(given["data"])), given)


def variant_export(given: Mapping) -> dict:
    """Export: your variant ``name`` as a zip (``library.pack``):
    ``{"name": "<name>.zip", "zip": bytes, "unshareable": [...]}``, the
    files it holds that aren't yours to share (a mesh, a texture: D393)."""
    from azurkit.tools.characters import library

    name = _named(given, "variant_export")
    data, held = library.pack(name)
    return {"name": f"{name}.zip", "zip": data, "unshareable": held}


_SPOILERS: dict[str, tuple[generator.Prepared, dict]] = {}   # the last build's spoiler left out, by its plan's sha256


def _ingame(layers: list[Layer]) -> list[str]:
    """The in-game controls a build of ``layers`` adds (D1153), in the modern
    pad's names, each only where the build has it: the save warp, LB's
    attack sets (X36's, two or more, as the character layer's log says
    them), the speed toggle where its L3 landed, the roll (the game's own
    RB) where the player moved its distance or speed, and photo mode."""
    from azurkit.tools.mods.packs import player_physics

    by = {la.id: la for la in layers}
    out = ["LT + A, B, X, Y on a save platform: town and back"] if "pack qol_save_warp" in by else []
    if worn := [la for la in layers if la.tool == characters.TOOL]:
        from azurkit.tools.characters._player_character import said_sets
        if (sets := max(said_sets(la.notes) for la in worn)) > 1:
            out.append(f"LB: next attack set ({sets})")
    if physics := by.get("pack player_physics"):
        tick = f"({player_physics.TOGGLE_HOOKS[0][0].label})"
        if any(c.group.endswith(tick) for c in physics.changes):
            out.append("L3: speed toggle")
        params = physics.recipe.get("params", {})
        rolled = [f"{what} x{k:g}" for what, name in (("distance", "roll_speed_scale"), ("speed", "roll_time_scale"))
                  if (k := params.get(name, 1.0)) != 1.0]
        if rolled:
            out.append(f"RB: roll ({', '.join(rolled)})")
    if "pack qol_photo_mode" in by:
        out.append("click both sticks: photo mode")
    return out


def _report(made: edits.Manifest, prepared: generator.Prepared | None, steps: Steps = Steps(),
            spoiler: bool = True) -> dict:
    out = {"release": made.release.name, "label": made.release.label,
           "layers": [{"id": la.id, "sites": len({c.group for c in la.changes}),
                       "bytes": sum(len(c.after) for c in la.changes)} for la in made.layers],
           "result": dict(made.result), "conflicts": [str(c) for c in made.conflicts],
           "notes": [note for la in made.layers for note in la.notes], "ingame": _ingame(made.layers)}
    if prepared is not None:
        verdict = made.verdicts[generator.TOOL]
        out |={"randomizer": verdict, "plan": prepared.plan.doc}
        if spoiler:
            steps("spoiler")
            out["spoiler"] = generator.spoiler(prepared, verdict)
        else:   # kept for spoiler(plan, built=True)
            _SPOILERS.clear()
            _SPOILERS[prepared.plan.doc["sha256"]] = (prepared, verdict)
    return out


def image(recipe: Mapping, *, progress: Callable[[dict], object] | None = None, spoiler: bool = True,
          picked: Mapping[str, bytes] | None = None) -> tuple[iso.Image, dict]:
    """The image ``recipe`` builds, unwritten, and its report: the release,
    each layer's sites and bytes, the sha256 of each file that differs from
    vanilla, every conflict (D28), each layer's notes (a slider value
    past float32's range, written as the infinity it saturates to, Q110)
    and the in-game controls it adds (``ingame``, :func:`_ingame`);
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
    build. ``picked`` holds the bytes of the files a recipe's ``files``
    replaces, by the image's path (``edits.files``: a recipe names them, never
    holds them)."""
    steps = Steps(progress)
    stamp, base, layers, judge, prepared = _plan(recipe, steps, picked)
    steps("layout")
    made, manifest = edits.image(stamp, layers, base, judge=judge, map=_map, progress=steps.counter("layout"))
    return made, _report(manifest, prepared, steps, spoiler)


def image_staged(recipe: Mapping, *, progress: Callable[[dict], object] | None = None, spoiler: bool = True,
                 picked: Mapping[str, bytes] | None = None, hashed: Mapping[str, str] | None = None,
                 ahead: bool = False):
    """:func:`image` for a host that hashes the build's changed files itself
    (the site's worker: WebCrypto, off its engine's thread), as a generator
    (``edits.staged``): it yields ``{key: bytes | iso.Patched}`` once they are
    composed and is sent ``{key: sha256}``, each one's (``None`` first, if the
    host hashes them while the image's layout runs, then the shas at the next
    yield; a :class:`iso.Patched`'s md5 too, at once), and returns ``(image,
    report)``, :func:`image`'s, byte for byte, as its ``StopIteration``'s
    value. Its refusals are :func:`image`'s; a key missing from the shas is a
    ``ValueError`` naming it. ``picked`` as :func:`image`'s, with ``hashed``
    the sha256 of each that the host hashed. With ``ahead``, for a host whose
    reads are late, it first yields three times at most a list of ``(image
    offset, size)``, what it reads next, and is resumed once those are at
    hand (:func:`_planning`)."""
    steps = Steps(progress)
    stamp, base, layers, judge, prepared = yield from _planning(recipe, steps, picked, hashed, ahead)
    steps("layout")
    made, manifest = yield from edits.staged(stamp, layers, base, judge=judge, map=_map,
                                             progress=steps.counter("layout"))
    return made, _report(manifest, prepared, steps, spoiler)


def image_checks(made: iso.Image, report: Mapping) -> dict[str, list[list]]:
    """What the site's Save hashes, as a File may read otherwise than it did at
    the pick (Firefox's, of a file changed on disk, silently: D35). ``image``:
    ``[path, image offset, size, sha256]`` of each of ``made``'s files the
    build vouches for (``report``'s, :func:`image`'s): what it changed by its
    result, the rest by the release's manifest. ``input``: the same of each
    file it changed as the input holds it, by the manifest, as the result's
    sha was hashed from that input whatever it held at the build (a browser
    that refuses a changed File's reads needn't hash these). Each ``image``
    row ends with the file's offset in the input where the input holds it at
    that size, else ``None``: a host that hashed the input's file knows the
    image's where the image's bytes there are a copy of the input's at that
    offset. The root files a build adds are its own bytes, so they aren't
    listed; nor is what lies between files, which no file of the game reads."""
    files = next(release for release in gate.RELEASES if release.name == report["release"]).files
    with iso.Reader(made.source) as r:
        held = [(e, r.start(e)) for e in r.entries() if not e.is_dir and e.size]
    placed = {e.path: (at, e.size) for e, at in held}
    with iso.Reader(made) as r:
        image = [[e.path, r.start(e), e.size, report["result"].get(e.path) or files[e.path][1],
                  placed[e.path][0] if placed.get(e.path, (None, None))[1] == e.size else None]
                 for e in r.entries() if not e.is_dir and e.size and (e.path in report["result"] or e.path in files)]
    changed = [[e.path, at, e.size, files[e.path][1]] for e, at in held
               if e.path in report["result"] and e.path in files]
    return {"image": image, "input": changed}


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


def build(recipe: Mapping, out: str, *, progress: Callable[[int, int], object] | None = None,
          picked: Mapping[str, bytes] | None = None) -> dict:
    """Write the image ``recipe`` builds to ``out`` (never its input or a
    vanilla image, D36); :func:`image`'s report with the output's path,
    size and sha256. ``progress(done, total)`` follows the write; an
    exception it raises cancels it, and nothing is written. ``picked`` as
    :func:`image`'s."""
    stamp, base, layers, judge, prepared = _plan(recipe, picked=picked)
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


_NO_TOOL = ("preset: no tool {tool!r} with {kind!r} (AzurKit's: mods with packs, data with xbr, randomizer with plan, "
            "characters with characters, community with packs, files with put)")


def _pins(recipe: Mapping) -> list[dict]:
    """``recipe``'s community packs as a link and a mods file carry them, by
    id and sha12 (Q174: never their bytes), each refusal named."""
    return [{"id": pick["id"], "sha": pick["sha256"][:12]} for pick in _picks(recipe)]


def _completed(packs: object) -> tuple[dict, list[str]]:
    """A mods file's or link's packs, normalized, with each pack they require,
    as a person's tick moves them, and the lines saying so (``mods.settle``):
    no line for a build's manifest, which is complete."""
    given = mods.normalize(packs)
    names, lines = mods.settle(given, given)
    return {name: given.get(name, {}) for name in names}, lines


def _read(given: str | bytes | Mapping) -> dict:
    """A mods file read as a preset (``preset.read``), or one of Modkit's
    (``edits.modkit``: its edits as ``xbr`` operations, each checked as a
    build makes it of the vanilla config.xbr, ``tools.data.preview``); every
    refusal named."""
    found = preset.parse(given, modkit.is_mod)
    if not modkit.is_mod(found):
        return preset.read(found)
    made = modkit.edits(found, datatool.vanilla())
    rows = datatool.preview(made)
    return modkit.preset([(label, op, row.get("refused")) for (label, op, _), row in zip(made, rows)])


def read_mods(given: str | bytes | Mapping) -> dict:
    """A mods file (Q268: a preset or an AzurKit build's manifest, as JSON
    text or the object, a share link, or one of Modkit's mod files: its
    ``patches``, ``sections``, ``_keyed_patches`` and ``xbr_edits`` as
    ``xbr`` operations) as a recipe's ``{"packs", "xbr"}``,
    normalized, and ``randomizer`` (the seed and share string a randomized
    build's plan replays from, or the plan file it built); ``packs`` only when it has a packs layer (a
    build's packs are then its packs, with those they require, and no
    others), ``settled`` only when that added one (its lines, for a host to
    say), ``community`` its community packs' pins (a build resolves them).
    Every refusal named."""
    found = _read(given)
    out: dict = {}
    for layer in found["layers"]:
        if (layer["tool"], layer["kind"]) == ("mods", "packs"):
            out["packs"], settled = _completed(layer["recipe"])
            out |= {"settled": settled} if settled else {}
        elif (layer["tool"], layer["kind"]) == (xbr.TOOL, xbr.KIND) and set(layer["recipe"]) == {"ops"}:
            out["xbr"] = xbr.normalize(layer["recipe"]["ops"])
        elif (layer["tool"], layer["kind"]) == (generator.TOOL, generator.KIND):
            out["randomizer"] = generator.normalize(layer["recipe"])
        elif (layer["tool"], layer["kind"]) == (characters.TOOL, characters.KIND):
            out["character"] = _character(layer["recipe"])[0]
        elif (layer["tool"], layer["kind"]) == (communal.TOOL, communal.KIND) and set(layer["recipe"]) == {"packs"}:
            out["community"] = communal.normalize(layer["recipe"]["packs"])
        elif (layer["tool"], layer["kind"]) == (replaced.TOOL, replaced.KIND) and set(layer["recipe"]) == {"files"}:
            out["files"] = replaced.normalize(layer["recipe"]["files"])
        else:
            raise ValueError(_NO_TOOL.format(**layer))
    return out


def _character(given: object) -> tuple[dict, dict]:
    """A link's, a mods file's or a setup's character (``characters.normalize``
    less ``variant``, its recipe's sha12) and that as a link carries it:
    names and numbers only, so a recipe file's path (``variant_file``) is
    refused by name (Q174), as is a variant AzurKit holds no recipe of with
    that sha (a built-in, an installed one or one of yours, ``library``),
    naming what to Install or Update, or to import as yours."""
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
                         "of: install it from the Characters tab's community variants, or import its recipe file "
                         "as one of yours")
    if worn is not None and sha not in (None, worn.sha):
        mine = worn.source != "built-in"
        raise ValueError(f"preset: {character['species']!r} is recipe {sha} there and recipe {worn.sha} "
                         + ("in your variants: import its recipe file as yours to wear it" if mine else
                            "here: Install or Update it (the Characters tab's community variants), or update "
                            "AzurKit"))
    return character, character | ({"variant": worn.sha} if worn is not None else {})


def _shared(ops: list[dict]) -> list[dict]:
    """``ops``, refused by name unless each is a ``set`` (Q174: a link
    carries names and numbers, never a file's bytes)."""
    if raw := [str(k) for k, op in enumerate(ops, 1) if op["op"] != "set"]:
        raise ValueError(f"preset: a share link carries packs and set only (Q174), not xbr op {', '.join(raw)} "
                         "(replace_bytes)")
    return ops


_NO_LINK = ("preset: a share link never carries a replaced file (Q174): save a mods file for {}, and pick the file "
            "again where it is loaded")


def preset_encode(recipe: Mapping, report: Mapping | None = None) -> str:
    """The share link's fragment (``#p=…``) for ``recipe``'s randomizer
    (its seed, settings or share string and obsidian cost, checked as a
    build checks them), packs, normalized, and its ``set`` operations, never
    its image's path; given its build's report (:func:`image`), with the
    release it was built from and the sha256 of each file it changed. Names,
    numbers and hashes only (Q174): a recipe with a ``replace_bytes`` is
    refused by name; its ``character`` goes by name and numbers (a variant
    with its recipe's sha), and one naming a recipe file is refused; its
    ``community`` packs by id and their pack.json's sha12."""
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
    if pins := _pins(recipe):
        made["layers"].append({"tool": communal.TOOL, "kind": communal.KIND, "recipe": {"packs": pins}})
    if ops := (_shared if link else list)(xbr.normalize(recipe.get("xbr", []))):
        made["layers"].append({"tool": xbr.TOOL, "kind": xbr.KIND, "recipe": {"ops": ops}})
    if entries := replaced.normalize(recipe.get("files", [])):
        if link:
            raise ValueError(_NO_LINK.format(", ".join(e["path"] for e in entries)))
        made["layers"].append({"tool": replaced.TOOL, "kind": replaced.KIND, "recipe": {"files": entries}})
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
    (Q174), a character naming a recipe file or a variant recipe this
    AzurKit doesn't hold, or a community pack not installed at its pin, is
    refused by name, naming what to Install or Update."""
    return _loaded(preset.decode(text))


def _loaded(found: dict, *, link: bool = True) -> dict:
    """``found``, a checked preset, as a UI loads it (:func:`preset_decode`'s
    checks; a pack a pack requires is added, with a line in ``settled``); a
    mods file's (``link`` false) keeps a ``replace_bytes``."""
    for layer in found["layers"]:
        if (layer["tool"], layer["kind"]) == ("mods", "packs"):
            layer["recipe"], settled = _completed(layer["recipe"])
            found |= {"settled": settled} if settled else {}
        elif (layer["tool"], layer["kind"]) == (xbr.TOOL, xbr.KIND) and set(layer["recipe"]) == {"ops"}:
            layer["recipe"] = {"ops": (_shared if link else list)(xbr.normalize(layer["recipe"]["ops"]))}
        elif (layer["tool"], layer["kind"]) == (generator.TOOL, generator.KIND):
            layer["recipe"] = generator.check(layer["recipe"])
        elif (layer["tool"], layer["kind"]) == (characters.TOOL, characters.KIND):
            layer["recipe"] = _character(layer["recipe"])[1]
        elif (layer["tool"], layer["kind"]) == (communal.TOOL, communal.KIND) and set(layer["recipe"]) == {"packs"}:
            layer["recipe"] = {"packs": _pins({"community": layer["recipe"]["packs"]})}
        elif (layer["tool"], layer["kind"]) == (replaced.TOOL, replaced.KIND) and set(layer["recipe"]) == {"files"}:
            layer["recipe"] = {"files": replaced.normalize(layer["recipe"]["files"])}
            if link:
                raise ValueError(_NO_LINK.format(", ".join(e["path"] for e in layer["recipe"]["files"])))
        else:
            raise ValueError(_NO_TOOL.format(**layer))
    return found


def mods_file(given: Mapping) -> dict:
    """The Tools tab's mods files (Q268): ``{"text"}``, a mods file's JSON
    text (a preset, an AzurKit build's manifest or one of Modkit's mod
    files, :func:`read_mods`) or a share link, read as
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
        return {"preset": _loaded(_read(given["text"]), link=False)}
    made = _preset(given["recipe"], link=False) if "recipe" in given else given["preset"]
    return {"text": json.dumps(preset.check(made), indent=1, sort_keys=True, allow_nan=False) + "\n"}


def mods_diff(given: Mapping) -> dict:
    """What a mods file changes, before a build (Modkit's ``diff``):
    ``{"text"}``, a mods file's text (:func:`read_mods`' kinds), gives each
    of its edits as a build makes it of the vanilla config.xbr
    (``tools.data.preview``: a cell's table/entity/prop and its vanilla and
    new values, a byte edit's span, one of another file left to the build,
    or why a build refuses it), as ``{"edits"}``, with a Modkit mod's
    ``name`` and ``description``. What refuses the whole file is refused
    by name."""
    if not (isinstance(given, Mapping) and set(given) == {"text"} and isinstance(given["text"], str)):
        raise ValueError("mods_diff: {text}, a mods file's text")
    found = preset.parse(given["text"], modkit.is_mod)
    if modkit.is_mod(found):
        made = modkit.edits(found, datatool.vanilla())
        about = {key: found[key] for key in ("name", "description") if isinstance(found.get(key), str)}
    else:
        made = [(f"xbr op {k}", op, None) for k, op in enumerate(read_mods(found).get("xbr", []), 1)]
        about = {}
    return about | {"edits": datatool.preview(made)}


def entity_diff(given: Mapping) -> dict:
    """Two config.xbr entities side by side (Modkit's ``entity diff``):
    ``{"a", "b", "all"?}`` gives each table that holds either, every
    property they hold differently or only one holds (with ``all``, alike
    too), and the tables only one is in (``tools.data.compare``), from the
    config.xbr AzurKit ships. An entity no table holds is refused by
    name."""
    if not (isinstance(given, Mapping) and set(given) <= {"a", "b", "all"} and isinstance(given.get("a"), str)
            and isinstance(given.get("b"), str) and isinstance(given.get("all", False), bool)):
        raise ValueError("entity_diff: {a, b, all?}: two entities' names")
    return datatool.compare(given["a"], given["b"], given.get("all", False))


def mod_template(given: Mapping) -> dict:
    """A mods file of vanilla values to edit (Modkit's ``mod-template``):
    ``{"tables", "entity"?, "name"?}`` gives Modkit's mod file of every
    number cell of those config.xbr tables (or one entity's), by the
    file's own names, as ``_keyed_patches`` (``tools.data.template``):
    ``{"text", "tables", "entities", "cells", "left_out"}``, its JSON text,
    the counts and the tables that haven't the entity, which
    :func:`read_mods` and :func:`mods_file` take back as edits that change
    nothing until a value is. A table config.xbr hasn't, or an entity none
    of them has, is refused by name."""
    if not (isinstance(given, Mapping) and set(given) <= {"tables", "entity", "name"}
            and isinstance(given.get("tables"), list) and all(isinstance(t, str) for t in given["tables"])
            and isinstance(given.get("entity", ""), str) and isinstance(given.get("name", ""), str)):
        raise ValueError("mod_template: {tables: [names], entity?, name?}")
    made = datatool.template(given["tables"], given.get("entity"), given.get("name", "my-mod"))
    keyed = made["mod"]["_keyed_patches"]
    return {"text": json.dumps(made["mod"], indent=2) + "\n", "tables": len(keyed),
            "entities": sum(len(e) for e in keyed.values()),
            "cells": sum(len(p) for e in keyed.values() for p in e.values()), "left_out": made["left_out"]}


DATA = ("what", "ops", "packs", "kind", "name", "table", "file", "iso")   # what a Data tab's ask holds (:func:`data`)


def data(given: Mapping) -> dict:
    """The Data tab's config.xbr (Step 4.7a; ``tools.data``, from the
    vanilla file AzurKit ships, so before an image): ``{"what": "index"}``
    the tables by category and the pickers' lists, ``{"what": "view",
    "kind", "name"}`` one entity's cells (``kind`` player, critter, item,
    armor or weapon; the player has no ``name``; ``changes``, with no
    ``name``, every cell the operations change, by table, beside its
    vanilla value, then their byte edits), ``{"what": "table",
    "table"}`` a table as a grid. Each shows the tables as the recipe's
    ``xbr`` operations ``ops`` make them, every changed cell with its
    vanilla value, and marks each cell a slider of ``packs`` (the recipe's
    ticked packs and their values) also writes: the data edit wins, its
    layer last (D28). A pack whose values a build would refuse marks
    nothing here (the build names it). A refusal names the key, the view
    or the table.

    All files (Step 4.6h, Modkit's "All files…"): ``{"what": "files",
    "iso"}`` every ``.xbr`` of the image (its release's, the image checked
    as a build checks it, D27), config.xbr first; ``{"what": "tables",
    "file"}`` a file's keyed tables, read from the image (``iso``) but
    config.xbr's (only its TOC first: no vanilla file but config.xbr has
    any); a ``table`` ask with ``file`` (default config.xbr) shows that
    file's table."""
    if not isinstance(given, Mapping):
        raise ValueError("data: a JSON object")
    if unknown := sorted(set(given) - set(DATA), key=str):
        raise ValueError(f"data: no key {', '.join(map(repr, unknown))} (its keys: {', '.join(DATA)})")
    ops, what = given.get("ops") or [], given.get("what")
    if not isinstance(ops, list):
        raise ValueError("data: ops is a list of xbr operations")
    if what == "index":
        return datatool.index(ops)
    if what == "files":
        stamp = _stamp(_data_image(given, "All files"))
        return {"release": stamp.release.name, "label": stamp.release.label,
                "files": datatool.files(stamp.release.files)}
    if what not in ("view", "table", "tables"):
        raise ValueError(f"data: what is index, view, table, files or tables, not {what!r}")
    if what == "view":
        return datatool.view(given.get("kind"), given.get("name"), ops, _written(given.get("packs") or {}))
    file = given.get("file", datatool.FILE)
    if file == datatool.FILE:
        return (datatool.tables(ops) if what == "tables"
                else datatool.table(given.get("table"), ops, _written(given.get("packs") or {})))
    release, base = _keyed_file(given, file)
    if what == "tables":
        return datatool.tables(ops, file, base, release)
    return datatool.table(given.get("table"), ops, (), file, base, release)


def _data_image(given: Mapping, what: str) -> str:
    if not isinstance(iso_ := given.get("iso"), str):
        raise ValueError(f"data: {what} needs your image: pick it first (iso, its path)")
    return iso_


def _keyed_file(given: Mapping, file: object) -> tuple[gate.Release, bytes | None]:
    """``file`` of the image ``given["iso"]`` names (its build files checked,
    D27): its release, and its bytes when its TOC holds a keyed table (a
    ``tabl`` entry), else ``None``, read no further than its TOC."""
    if not isinstance(file, str):
        raise ValueError(f"data: file {file!r} is no gamedata/<name>.xbr")
    stamp = _stamp(_data_image(given, file))
    if not any(f["file"] == file for f in datatool.files(stamp.release.files)):
        raise ValueError(f"data: the {stamp.release.label} image has no {file}")
    with iso.Reader(stamp.path) as r:
        entry = r.lookup(file)
        if entry is None or entry.is_dir:
            raise ValueError(f"data: the image has no {file}")
        need = min(entry.size, xbrdoc.toc_size(r.range(entry, 0, min(entry.size, xbrdoc.HEADER.size))))
        if "tabl" not in xbrdoc.tags(r.range(entry, 0, need)):
            return stamp.release, None
        return stamp.release, r.read(entry)


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
    type and an example, never game bytes. An edit with ``file`` (another
    file's table, All files) reads that file from the image ``iso``."""
    if not (isinstance(given, Mapping) and "edit" in given and set(given) <= {"edit", "ops", "iso"}):
        raise ValueError("data_edit: {edit: {table, col, row, value}, ops}")
    if not isinstance(ops := given.get("ops") or [], list):
        raise ValueError("data_edit: ops is a list of xbr operations")
    edit = given["edit"]
    if isinstance(edit, Mapping) and edit.get("file", datatool.FILE) != datatool.FILE:
        release, base = _keyed_file(given, edit["file"])
        return datatool.check(edit, ops, base, release)
    return datatool.check(edit, ops)


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
    with noting(Steps(progress)) as steps:
        steps("spoiler")
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


def randomizer_settings(given: Mapping, *, progress: Callable[[dict], object] | None = None) -> dict:
    """What the Randomizer tab shows for ``given``: its ``settings`` (a
    settings file's table), ``share`` (a share string), ``file`` (a
    settings file's text, D144's Load settings) or ``plan`` (a plan file's
    object, Open a plan…: its own settings, refused by name unless it reads
    back on this database and is beatable under them), its
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
    id, name, rating, the ceiling's state, ``ratings``, each variant's as a
    number, and its toggle; D114, D275), the
    picks held and the forfeitable locations, what a build would leave
    unverified so far (``why_not``: the packs' movement past their logic
    floor, D83(c), a roll a skip on was proven at, an obsidian cost above
    vanilla's), the preflight's refusal (``preflight``, AZ-454, in plain
    words with what to change, and ``preflight_tick``, its "Tick <row>",
    Step 4.4u1; ``None``),
    the settings file of the settings (``file``, Save settings') and the
    skip groups (``groups``, D258: each group's picks, its highest rating
    and its tip).
    ``tools.randomizer.tab``; a refusal names the setting, the share string,
    the settings file or the pack. ``progress(record)`` hears the logic's
    read while the first ask reads it (``plan``, "Reading the randomizer's
    logic", counted: the shipped file's twentieths, a checkout's checks), and
    an ask once it is read hears nothing, so its bar never flashes
    (Step 4.4bd)."""
    with noting(Steps(progress and (lambda step: progress(step) if step["total"] else None))) as steps:
        steps("plan", "Reading the randomizer's logic")   # heard from its first count on: a read that is counted
        return _randomizer_settings(given)


def _randomizer_settings(given: Mapping) -> dict:
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


def tracker(given: Mapping, *, progress: Callable[[dict], object] | None = None,
            openers: Callable[[Mapping], list] | None = None) -> dict:
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
    count). With no ``plan`` (Step 4.4u3): the maps to browse before a
    seed is tracked, each spot with the item the vanilla game puts there
    (``vanilla``, state ``vanilla``), the world map and its levels by
    realm (``levels``), no image read. Modkit's tracker, the same verdicts on every host
    (``tools.randomizer.tracking``); ``progress(record)`` hears a plan's
    first view build its tracker and read the world map, the maps' exits
    counted on it; ``openers(plan)``: who works out a shaped plan's spoiler
    openers (none: this call; the app: its engine, :func:`azurkit.tools.randomizer.openers`);
    a refusal names what it refuses."""
    with noting(Steps(progress)) as steps:
        return tracking.view(given, progress=steps.report, openers=openers)


def art(path: str, part: str) -> dict:
    """One part of the item tracker's pictures, drawn from the image at
    ``path`` (Step 4.2c3: the wheel, the app and the site hold none; a
    host keeps what this gives and draws each part once),
    each file it reads checked against its release's vanilla file
    (``gate.NotVanillaError`` names one that isn't): ``"icons"`` gives
    ``{"pictures": {"icons": PNG bytes}, "sheet": {"tile", "columns", "names"}}``,
    the one icon sheet (the game's 2D menu art, or its model where it has none), and a level
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
    """A UI's remembered setup (D915; the page keeps one only with Remember
    settings ticked, D1156): the packs it had ticked, each setting it had
    changed, its pack ticked or not, and a loaded recipe's config.xbr
    ``set`` operations (``{"ticked": [pack], "values": {pack: {slider:
    value}}, "xbr": [operation]}``; never an image, its path or anything
    read from one), as the UI applies it, with ``dropped``: what no longer
    normalizes (a pack renamed or retired, a setting gone, a value its
    slider refuses, a pack without one it requires, an operation a link
    couldn't carry), each left out and named, never applied. A setup's
    ``randomizer`` (the tab's: ``on``, ``seed``, ``settings`` and
    ``obsidian_cost``, ``tools.randomizer.remembered``) comes back
    checked, or is dropped whole, by name, as is its ``character`` (the
    Characters tab's: a species or variant by name and its options, never a
    recipe file's path); its ``community`` packs (their ids, without a pin:
    an Update never drops one) come back while each is installed untouched,
    else dropped by name. It never refuses: a setup it can't read is dropped
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
    if "community" in setup:
        rando["community"], lost = _still(setup["community"])
        why += lost
    return {"ticked": on, "values": {name: v for name, v in values.items() if v}, "xbr": kept,
            "dropped": list(dict.fromkeys(dropped + why))} | rando


def _still(pins: object) -> tuple[list[dict], list[str]]:
    """A setup's community packs that can still be built, and each that
    can't, named."""
    if not isinstance(pins, list):
        return [], ["the community packs (not a list)"]
    kept, dropped = [], []
    for pin in pins:
        try:
            kept += [{"id": pick["id"]} for pick in _picks({"community": [pin]})]
        except ValueError as exc:
            dropped.append(str(exc))
    return kept, dropped


def file_entry(given: Mapping) -> dict:
    """``{"entry"}``: ``given`` (``{"path", "sha256", "size"}``, a picked
    file's) as a recipe's ``files`` holds it, or the refusal named: a file
    the build owns, a size past what an image's file holds
    (``edits.files``)."""
    return {"entry": replaced.normalize([given])[0]}


def saves(given: Mapping) -> dict:
    """The Tools tab's Saves (``tools.saves.session``'s asks: ``{"do":
    "open"}`` a slot's folder or files, or an xemu HDD image's slots,
    read-only; ``"edit"`` a text save's lines; ``"sign"`` the slot again, its
    ``flash`` and ``mcpx`` bytes and the key from them in memory for this call
    alone, the game's half from the ``default.xbe`` of the image at ``iso``;
    ``"save"`` a new folder; ``"zip"`` its bytes). A refusal names what and
    why."""
    from azurkit.tools.saves import session

    def xbe(path: str) -> bytes:
        with iso.Reader(path) as r:
            return r.read("default.xbe")
    return session.ask(given, xbe)


def community() -> dict:
    """The community packs the content folder holds, as the Patches tab
    ticks them: ``{"packs": [{"id", "version", "sha", "packs", "ops"} |
    {"id", "version", "refused"}]}`` (``community.held``: each one's sha12,
    its built-in packs' values and its edits in words, or why it can't be
    read, named, never bytes)."""
    from azurkit.tools.characters import content as kit

    return {"packs": communal.held(kit.installed(), lambda path: (kit.ROOT / path).read_bytes())}


def content_refusal(entry: Mapping, files: Mapping[str, bytes]) -> str | None:
    """Why a content entry can't be installed, or ``None``: a variant's
    recipe (``content.builtin_refusal``), a community pack
    (``community.refusal``). ``content.verify``'s ``refusal``."""
    from azurkit.tools.characters import content as kit

    return kit.builtin_refusal(entry, files) or communal.refusal(entry, files)


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
                with urllib.request.urlopen(where, timeout=10 if path == content.MANIFEST else 60) as reply:
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
                source=source, refusal=content_refusal)   # each file read to at most its listed size (SEC-9)
    return content({"source": given.get("source")})


def content_check(given: Mapping) -> dict:
    """The site's half of Install (its page fetches, this checks):
    ``given["manifest"]`` checked, and with ``id`` and ``files`` (``{path:
    bytes}``, what the page fetched of the entry and those it requires)
    every file verified as :func:`content_install` verifies it
    (``tools.characters.content.verify``): ``{"manifest", "install": [each
    entry's id it writes, those required first]}``, or the refusal named: none
    it writes goes below its installed version or, with ``source`` (the
    page's Content from), comes from another source than the one it was
    installed from (``tools.characters.content.held_to``, SEC-8)."""
    from azurkit.tools.characters import content as kit

    if not isinstance(given, Mapping):
        raise ValueError("content: a JSON object")
    manifest = kit.check(given.get("manifest"))
    if "id" not in given:
        return {"manifest": manifest, "install": []}
    if not isinstance(source := given.get("source"), str | None):
        raise ValueError("content: the source is a URL")
    chosen = kit.verify(manifest, given["id"], given.get("files") or {}, content_refusal)
    record = kit.installed()
    kit.held_to(kit.writes(chosen, given["id"], record), record, source)
    return {"manifest": manifest, "install": [e["id"] for e in chosen]}
