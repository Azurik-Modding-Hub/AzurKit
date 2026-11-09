"""Record AzurKit's goldens, ``tests/goldens/``, from its own builds on the
player's images: what each case of ``tests/goldens/cases.json`` (its recipe,
edited by hand) builds, as names and sha256 only.

    uv run --locked python scripts/record_goldens.py [--check] [--workers N] [GOLDEN ...]

- ``packs.json`` and ``europe/packs.json`` (G1): a pack alone at the case's
  sliders, from the release's vanilla files: ``default.xbe`` and each file
  the pack's layer writes (``config.xbr`` by that name), at vanilla's sha256
  where the writes leave it so.
- ``sites.json`` and ``europe/sites.json``: each XBE pack case's bytes at
  every facts site it changes, by the release's own address (USA's ``.text``
  slack, past its section's file bytes, counts).
- ``shims.json`` (G2): each shim's prebuilt object's normalized sha256, the
  packs' and the swap's (``player_model_<stem>.o``, its ``ports.HELD``
  bytes written back from the USA image); ``tests/test_shims.py`` holds each
  object to its source's build.
- ``xbr_editor.json``: ``config.xbr`` after one cell's edit.
- ``pipelines.json`` and ``europe/pipelines.json`` (G3) and ``gui.json``
  (G4): a whole build's recipe through the sdk (Modkit's flags and GUI
  ticks, translated by :func:`recipe`, a case that dresses the player with
  its ``character``, :func:`wears`): each file it changes (Europe's but the
  XBRs both releases hold, :func:`shared`, which its USA case records), and
  for G3 the image without the build's root entries (``ISO``). A case that
  moves a level entity leaves out ``gamedata/training_room.xbr``,
  ``filelist.txt`` and ``ISO`` (:data:`LEVEL_PATCHED`: AZ-009, level_patches
  isn't ported).
- ``resources.json``: for each G3 case that dresses the player, each XBR
  its build changed, resource by resource (:func:`view`).
- ``close.json``: what lets another host's float maths (D1016: another BLAS
  rounds a matrix product otherwise, :func:`apart`) be compared to those
  builds with no reference file per platform, and no copy of their bytes:
  by sha256, each changed or added XBR resource's :func:`sketch` and each
  file's digest with those resources blanked (:func:`parts`), and each
  ``filelist.txt``'s without their md5s.
- ``probes.json``: the character recipes no G3 case builds without
  Azurik-Custom-Content's files or on Europe (a variant's mesh, paint and
  jiggle, a townsman's and the air elemental's own bodies), built over the
  packs on by default on both releases: each file's sha256 and resources.
- ``matches.json``: the Characters tab's match-Garret values (``sdk.match``)
  of each recipe on USA over the packs on by default.
- ``rando_plans.json``: the randomizer's plan of each case's seed and
  settings (``sdk.plan``): its attempt and sha256, the sha256 of its spoiler
  file (``azurkit spoiler``'s text) and, for the case marked ``file``, the
  plan file's object. G3's seed cases build it into an image.
- ``tracker.json``: the item tracker's verdicts on each case's plan at each
  of :func:`tracker_states`' states, the spoiler off and on: the
  ``sha256[:32]`` of its view (``view``: ``tracking.digest`` of
  ``sdk.tracker``) and of the maps' model the page draws of that view
  (``map``: ``web/mapview.mjs`` under ``node``, :data:`MAP_MODEL`).

The page's shipped pictures (Step 4.3f, D961), files rather than names and
sha256, are recorded the same way, each family by its name:

- ``art``: the tracker's pictures in ``web/art/`` (:func:`art`), drawn from
  the USA image as the tracker draws them, Modkit's committed files byte
  for byte.
- ``characters``: the Characters tab's species list (``species.json``) and
  its pictures and no-image view in ``web/characters/``
  (:func:`characters`), from both images.

The first recording is Modkit's last cut: for the core and packs families
oracle-packs-4 (Modkit 28d0b4110, Step 4.12a), for the models family
oracle-models-3 (Modkit 1648692, Step 4.12c), which this script's first run
wrote back unchanged but where AzurKit can't build a file (AZ-009); for the
randomizer's oracle-rando-6 (Modkit 8bfef0ca6, Step 4.12b), whose rows it
wrote back unchanged, each plan's ``spoiler`` added and ``tracker.json``
recorded equal to the digests of Modkit's own tracker. Only it
changes these files, and a commit that does names each golden it changed and
why. ``--check`` writes nothing and exits 1 naming each case that differs.
The images are the ones the gate finds (``AZURKIT_ISO``,
``AZURKIT_ISO_EUROPE``, else the user data folder); the cases that wear
booblord read her clips and voice in the content folder (``AZURKIT_CONTENT``:
``azurkit content install booblord``). The builds that dress the player run
in ``--workers`` processes (4), each dress fresh (``shipped.OFF``: no
shipped answer, D995, is taken; ``tests/test_characters.py`` holds each of
those to these builds' own).
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import json
import multiprocessing
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable, Collection, Mapping
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path, PurePath

import numpy as np

from azurkit import sdk
from azurkit.core import coff, facts, filelist, gate, iso
from azurkit.core.xbr import Document, edits
from azurkit.edits.layer import compose
from azurkit.edits.manifest import image
from azurkit.tools import mods
from azurkit.tools.characters import shipped
from azurkit.tools.mods import engine

shipped.OFF = True   # every dress fresh, in each process that imports this: the shipped answers are held to them
ROOT = Path(__file__).resolve().parent.parent
GOLDENS = ROOT / "tests" / "goldens"
CASES = GOLDENS / "cases.json"
SHIMS = ROOT / "src" / "azurkit" / "tools" / "mods" / "shims"   # shimkit.SHIMS: the packs' shims and objects
PLAYER_MODEL = ROOT / "src" / "azurkit" / "tools" / "characters" / "player_model"   # shimkit.PLAYER_MODEL: the swap's
G3 = ("pipelines.json", "europe/pipelines.json")
RESOURCES, PROBES, MATCHES, CLOSE = "resources.json", "probes.json", "matches.json", "close.json"
PLANS, TRACKER = "rando_plans.json", "tracker.json"   # the randomizer's
MAPVIEW = ROOT / "web" / "mapview.mjs"   # the page's maps, whose model of a tracker view tracker.json records
KIT = {"air": 3, "water": 3, "fire": 3, "earth": 3}   # Live's kit at tracker.json's "kit" state
INDEX = "gamedata/index/index.xbr"
CONFIG = engine.CONFIG
NAMES = {CONFIG: "config.xbr"}   # a file's name in G1 and the editor's golden (Modkit's)
FLOATS = ("gamedata/characters.xbr", "gamedata/fx.xbr")   # what a dress writes float maths into (D1016): close.json's
KEY, MOST_SUMS = 16, 64   # close.json: a sha256's digits a row is found by; its sums a resource, at most
ULPS, NEAR_ZERO = 4, 1e-9   # how far a float may be off, at most: "a few ULPs", and in metres or radians near zero
LEVEL_PATCHED = ("gamedata/training_room.xbr", "filelist.txt", "ISO")
ART = "web/art"   # the tracker's shipped pictures, from the checkout's root
PICTURES = "web/characters"   # the Characters tab's
SPECIES = "src/azurkit/tools/characters/species.json"   # picker.SPECIES
LONGEST = ("w1", "d2", "w3", "w4")   # the parts that draw longest (CPython 44, 33, 27, 25 s), started first
# Modkit's flags -> player_physics's sliders: apply-physics's, then randomize-full's
APPLY = {"gravity": "gravity", "walk_speed": "walk_speed_scale", "swim_speed": "swim_speed_scale",
         "jump_speed": "jump_speed_scale", "air_control_speed": "air_control_scale", "flap_height": "flap_height_scale",
         "flap_below_peak": "flap_below_peak_scale", "wing_flap_ceiling": "wing_flap_ceiling_scale",
         "flap_descent_fuel_cost": "flap_descent_fuel_cost_scale", "climb_speed": "climb_speed_scale",
         "roll_speed": "roll_speed_scale", "roll_time": "roll_time_scale"}
RANDOMIZE = {"gravity": "gravity", "player_walk_scale": "walk_speed_scale", "player_roll_scale": "roll_speed_scale",
             "player_roll_time_scale": "roll_time_scale", "player_climb_scale": "climb_speed_scale",
             "player_swim_scale": "swim_speed_scale", "player_jump_scale": "jump_speed_scale",
             "player_air_control_scale": "air_control_scale", "player_flap_scale": "flap_height_scale",
             "player_flap_below_peak_scale": "flap_below_peak_scale",
             "player_wing_flap_ceiling_scale": "wing_flap_ceiling_scale",
             "player_flap_descent_fuel_cost_scale": "flap_descent_fuel_cost_scale"}

FLAG_PACKS = {"gem_popups": "qol_gem_popups", "other_popups": "qol_other_popups", "pickup_anims": "qol_pickup_anims",
              "skip_logo": "qol_skip_logo", "fps_unlock": "fps_unlock"}   # randomize-full's flags that turn a pack on
SETTINGS = ("skip_ceiling", "movement_tier")   # randomize-full's settings flags over D144's defaults
# randomize-full's player flags -> a recipe's character (tools.characters.normalize)
FIELDS = {"player_character_mode": "mode", "player_character_size": "size", "player_character_scale": "scale",
          "player_attack_reach": "attack_reach", "player_attack_damage": "attack_damage",
          "player_attack_speed": "attack_speed", "player_character_anims": "anims",
          "player_character_sounds": "sounds", "player_weapon": "weapon", "player_jiggle_strength": "jiggle_strength",
          "player_jiggle_stiffness": "jiggle_stiffness"}
PLAYER_SLIDERS = ("player_character_scale", "player_attack_reach", "player_attack_damage", "player_attack_speed")


def _sha256(data) -> str:
    return hashlib.sha256(data).hexdigest()


def cases(golden: str) -> dict[str, dict]:
    """``{case: its recipe}`` of one golden."""
    return json.loads(CASES.read_text(encoding="utf-8"))[golden]


def recorded(golden: str) -> dict[str, dict]:
    return json.loads((GOLDENS / golden).read_text(encoding="utf-8"))


def _defaults() -> dict[str, dict]:
    return {name: {} for name, pack in mods.PACKS.items() if pack.default_on}


def _ops(mod: Mapping, path) -> list[dict]:
    """A Modkit mod's config.xbr cells and xbr_edits as ``xbr`` operations, in
    its order (one shape at a time); a replace's ``expected`` is the sha256
    of the bytes the image holds there."""
    cell = lambda table, entity, prop, value: {"op": "set", "file": CONFIG, "table": table,  # noqa: E731
                                               "entity": entity, "prop": prop, "value": value}
    ops = [cell(e["section"], e["entity"], e["property"], e["value"]) for e in mod.get("patches", [])]
    ops += [cell(table, entity, prop, value) for table, rows in mod.get("_keyed_patches", {}).items()
            for entity, props in rows.items() for prop, value in props.items()]
    for e in mod.get("xbr_edits", []):
        file = f"gamedata/{e['xbr_file']}"
        if e["op"] == "replace_bytes":
            with iso.Reader(path) as r:
                held = r.read(file)[e["offset"]:e["offset"] + len(e["value"]) // 2]
            ops.append({"op": "replace_bytes", "file": file, "offset": e["offset"], "value": e["value"],
                        "expected": {"sha256": _sha256(held), "size": len(held)}})
        else:
            if not (e["op"].startswith("set_keyed_") and file == CONFIG):
                raise ValueError(f"an xbr_edit AzurKit doesn't translate: {e['op']} in {file}")
            ops.append(cell(e["section"], e["entity"], e["prop"], e["value"]))
    return ops


def wears(case: Mapping) -> bool:
    """Whether a G3 case dresses the player (Modkit's ``player_species``):
    randomize-full with ``--player-character``, a ``--player-weapon`` or one
    of :data:`PLAYER_SLIDERS` other than 1.0 (garret4's own body; no case
    names one of his own weapons)."""
    args = case.get("args") or {}
    return args.get("command") == "randomize-full" and bool(
        args["player_character"] or args["player_weapon"]
        or any(args[k] not in (None, 1.0) for k in PLAYER_SLIDERS))


def seeded(case: Mapping) -> bool:
    """Whether a G3 case plans a seed (randomize-full without
    ``--no-randomize``): ``tests/test_randomizer.py``'s, but one that
    :func:`wears` a character, ``tests/test_characters.py``'s."""
    args = case.get("args") or {}
    return args.get("command") == "randomize-full" and not args["no_randomize"]


def character(case: Mapping, folder: Path | None = None) -> dict:
    """A G3 case's player flags as a recipe's ``character``: its
    ``--player-character``, else garret4's own body, and its variant file
    (the case's ``files``) written into ``folder``."""
    args = case["args"]
    out = {"species": args["player_character"] or "garret4"} | {
        FIELDS[k]: v for k, v in args.items() if k in FIELDS and v is not None}
    out |= {k.removeprefix("player_"): args[k] == "on" for k in ("player_attack_ground", "player_attack_balance")
            if args[k] is not None}
    if rel := args["player_variant_file"]:
        if folder is None:
            raise ValueError(f"a G3 case's variant file {rel} needs a folder to be written in")
        (path := folder / PurePath(rel).name).write_text(json.dumps(case["files"][rel]), encoding="utf-8")
        out["variant_file"] = str(path)
    return out


def recipe(golden: str, case: Mapping, path, folder: Path | None = None) -> dict:
    """A G3 (``pipelines.json``) or G4 (``gui.json``) case's recipe as a mods
    file's: apply-physics applies player_physics alone; patch,
    randomize-full and MCP pack_build_iso the packs on by default and those
    they name (randomize-full's flags, :data:`FLAG_PACKS`, and
    ``--enable-pack``), then the mod's operations, and randomize-full with
    a seed its ``randomizer`` (the seed, D144's settings with its settings
    flags, its obsidian cost) and the player's ``character`` if it
    :func:`wears` one (its variant file written into ``folder``); a GUI build
    its ticks over the packs on by default, its sliders and the Game Data
    editor's cells. A flag AzurKit doesn't translate is refused by name."""
    if golden == "gui.json":
        kwargs, packs = case["kwargs"], _defaults()
        for name, on in kwargs.get("packs", {}).items():
            packs[name] = packs.get(name, {}) if on else packs.pop(name, None)
        packs = {name: dict(kwargs.get("pack_params", {}).get(name, {})) for name, values in packs.items()
                 if values is not None}
        return {"packs": packs, "xbr": [{"op": "set", "file": CONFIG, "table": table, "entity": entity, "prop": prop,
                                         "value": value}
                                        for table, entity, prop, value in kwargs.get("config_edits", {}).get(
                                            "xbr_editor", [])]}
    args = case["args"]
    if case.get("mcp") == "pack_build_iso":
        return {"packs": _defaults() | {name: dict(args["params"].get(name, {})) for name in args["enable"]},
                "xbr": _ops(args["config_mod"], path)}
    if args["command"] == "apply-physics":
        return {"packs": {"player_physics": {APPLY[k]: v for k, v in args.items() if k in APPLY and v is not None}}}
    if args["command"] == "patch":
        return {"packs": _defaults(), "xbr": [op for mod in args["mod"] for op in _ops(mod, path)]}
    if not (args["command"] == "randomize-full" and args["ram"] == 128):
        raise ValueError(f"a G3 case AzurKit doesn't translate: {args['command']}")
    if left := [flag for flag in ("disable_pack", "pack_param", "plan", "settings", "share", "skip", "no_skip",
                                  "exclude_category", "player_shape", "player_variant_sounds", "player_speed_toggle")
                if args.get(flag)]:
        raise ValueError(f"a G3 case's flags AzurKit doesn't translate: {', '.join(left)}")
    physics = {RANDOMIZE[k]: v for k, v in args.items() if k in RANDOMIZE and v is not None}
    packs = _defaults() | {FLAG_PACKS[k]: {} for k in FLAG_PACKS if args.get(k)} | {
        name: {} for name in args.get("enable_pack") or ()}
    out = {"packs": packs | ({"player_physics": physics} if physics else {}),
           "xbr": _ops(args["config_mod"] or {}, path)} | ({"character": character(case, folder)} if wears(case) else {})
    if not args["no_randomize"]:
        from azurkit.tools.randomizer import layer
        from azurkit.tools.randomizer.planner.loader import kept_logic

        options = {k: args[k] for k in SETTINGS if args[k] is not None}
        out["randomizer"] = {"seed": str(args["seed"] if args["seed"] is not None else 42)} | (
            {"settings": layer.settings_doc(kept_logic().db.defaults) | options} if options else {}) | (
            {"obsidian_cost": args["obsidian_cost"]} if args["obsidian_cost"] is not None else {})
    return out


def level_patched(case: Mapping) -> bool:
    """Whether a G3 case's mods move a level entity (AZ-009)."""
    args = case["args"]
    mods_ = args.get("mod") or [args.get("config_mod") or {}]
    return any(mod.get("level_patches") for mod in mods_)


class Images:
    """Each release's verified image and its vanilla files, read once, and
    the builds that dress the player (:meth:`prebuild`), each built once."""

    def __init__(self, paths: Mapping[gate.Release, Path] | None = None):
        self._paths, self._stamps, self._files, self._built = dict(paths or {}), {}, {}, {}

    def stamp(self, release: gate.Release) -> gate.Stamp:
        if release not in self._stamps:
            if (path := self._paths.get(release) or gate.find(release)) is None:
                raise SystemExit(f"recording needs the {release.label} image: {gate.missing(release)}")
            self._stamps[release] = gate.verify(path, whole=False, releases=(release,))
        return self._stamps[release]

    def file(self, release: gate.Release, name: str) -> bytes:
        if (release, name) not in self._files:
            with iso.Reader(self.stamp(release).path) as r:
                self._files[release, name] = r.read(name)
        return self._files[release, name]

    def built(self, job: tuple) -> tuple:
        """A job's result (:func:`_job`), built here unless :meth:`prebuild` built it."""
        if job not in self._built:
            self._built[job] = _job(self._resolved(job))
        return self._built[job]

    def prebuild(self, jobs: list[tuple], workers: int) -> None:
        """Build ``jobs`` (:func:`_job`) in ``workers`` spawned processes, the
        variants' (booblord's take minutes) first; a build is the same in any
        process (each reads the content folder ``AZURKIT_CONTENT`` names)."""
        jobs = sorted({j for j in jobs if j not in self._built}, key=lambda j: ("booblord" not in str(j), j))
        if workers <= 1 or len(jobs) <= 1:
            for job in jobs:
                self.built(job)
            return
        with ProcessPoolExecutor(workers, mp_context=multiprocessing.get_context("spawn")) as pool:
            self._built |= dict(zip(jobs, pool.map(_job, [self._resolved(j) for j in jobs])))

    def _resolved(self, job: tuple) -> tuple:
        """``job`` with its release's image path."""
        return (*job, str(self.stamp(_release(job[-1])).path))


def _release(name: str) -> gate.Release:
    return next(r for r in gate.RELEASES if r.name == name)


def shared(name: str) -> bool:
    """An XBR both releases hold byte for byte (all but index.xbr): Europe's G3 records it in its USA case."""
    return name.endswith(".xbr") and name != INDEX


def view(vanilla: bytes, built: bytes, name: str) -> dict:
    """``resources.json``'s record of a built XBR ``name`` against its vanilla
    file: its sha256, size, TOC count and vanilla's, each vanilla entry whose
    payload changed (``[index, tag, size, sha256]``), each appended entry
    (``[name, tag, size, sha256, relocs]``) and, for ``index.xbr``, the
    records the build added (``[key, archive, fourcc]``, in the order their
    strings follow vanilla's)."""
    from azurkit.core.xbr.append import appended
    from azurkit.core.xbr.nodes import parse_toc
    from azurkit.tools.characters.index_xbr import _records

    def payload(data: bytes, e) -> bytes:
        return data[e.file_offset:e.file_offset + e.size]

    old, new = parse_toc(vanilla), parse_toc(built)
    out = {"sha256": _sha256(built), "size": len(built), "count": len(new), "vanilla_count": len(old),
           "changed": [[e.index, e.tag, e.size, _sha256(payload(built, e))] for e, v in zip(new, old)
                       if payload(built, e) != payload(vanilla, v)],
           "new": [[r.name, r.tag, len(r.payload), _sha256(r.payload), list(r.relocs)]
                   for r in appended(len(old), built)]}
    if name == INDEX:
        had = {r.key for r, _, _ in _records(vanilla, "index.xbr")[1]}
        added = sorted((k, r) for r, k, _ in _records(built, "index.xbr")[1] if r.key not in had)
        out["records"] = [[r.key, r.archive, r.fourcc] for _, r in added]
    return out


def parts(vanilla: bytes, built: bytes) -> tuple[dict[str, tuple[str, bytes]], str]:
    """The resources a built XBR changed or added, ``{sha256: (tag, payload)}``, and the sha256 of the file with them
    blanked."""
    from azurkit.core.xbr.nodes import parse_toc

    old, new = parse_toc(vanilla), parse_toc(built)
    spans = [e for e, v in zip(new, old) if built[e.file_offset:e.file_offset + e.size]
             != vanilla[v.file_offset:v.file_offset + v.size]] + new[len(old):]
    frame, held = bytearray(built), {}
    for e in spans:
        payload = built[e.file_offset:e.file_offset + e.size]
        held[_sha256(payload)] = (e.tag, payload)
        frame[e.file_offset:e.file_offset + e.size] = bytes(e.size)
    return held, _sha256(frame)


def _listed(text: bytes) -> str:
    """The sha256 of ``filelist.txt``'s bytes without the md5s of the XBRs a dress writes floats into."""
    lines = text.decode("latin-1").splitlines(keepends=True)
    for row in filelist.rows(text):
        if row.path in FLOATS:
            lines[row.line] = re.sub(row.md5, "", lines[row.line], flags=re.IGNORECASE)
    return _sha256("".join(lines).encode("latin-1"))


def _floats(tag: str, words: np.ndarray) -> np.ndarray:
    """Which of a resource's 32-bit words another host's float maths can round: a ``banm``'s length and every key
    (``retarget.read_clip``'s layout), whatever their bits (another BLAS leaves 1e-45 where this one leaves 0.0). None
    of any other tag, or of a ``banm`` that isn't a clip: only clips have differed by host, and a word's bits can't say
    it's a float (a strip's pair of indices reads as a tiny one, inside any float's room)."""
    out = np.zeros(len(words), bool)
    if tag != "banm" or len(words) < 5:
        return out
    pointer = words.view("<i4")
    for count, field in ((0, 1), (2, 3)):
        base = field * 4 + int(pointer[field])
        for track in range(max(0, int(pointer[count]))):
            record = (base + 0x14 * track) // 4
            if not 0 <= record <= len(words) - 5:
                return np.zeros(len(words), bool)
            keys, n = (record * 4 + 8 + int(pointer[record + 2])) // 4, 4 * max(0, int(pointer[record + 1]))
            out[max(0, keys):keys + n] = True
    out[4] = True
    return out


def _weighed(tag: str, payload: bytes, slots: int | None = None) -> tuple[str, list[float], list[float]]:
    """A resource as :func:`sketch` reads it: ``(its digest, its sums, how far each may be off)``."""
    n = len(payload) // 4
    words = np.frombuffer(payload, "<u4", n)
    values = words.view("<f4")
    float_like = _floats(tag, words) & np.isfinite(values)
    digest = _sha256(np.where(float_like, 0, words).astype("<u4").tobytes() + payload[n * 4:])
    at = np.arange(n, dtype=np.uint64)
    weights = 1 + ((at * 2654435761 >> 16) & 0xFFFF).astype(float) / 65536   # so that a moved value moves a sum
    count = slots or (max(1, min(n // 256, MOST_SUMS)) if float_like.any() else 1)
    slot = (at % count).astype(np.int64)
    sums = np.bincount(slot, weights * np.where(float_like, values, 0).astype(float), count)
    room = weights * np.where(float_like, ULPS * np.spacing(np.where(float_like, np.abs(values), 0)).astype(float) + NEAR_ZERO, 0)
    return digest, sums.tolist(), np.bincount(slot, room, count).tolist()


def sketch(tag: str, payload: bytes) -> str:
    """``close.json``'s record of a resource, its text: the first 16 digits of the sha256 of its 32-bit words with
    each float (:func:`_floats`) blanked, then the floats' sums, by word's place modulo up to :data:`MOST_SUMS` slots
    (one per 256 words), each float weighed by its place."""
    digest, sums, _ = _weighed(tag, payload)
    return " ".join([digest[:KEY], *(f"{value:.10g}" for value in sums)])


def near(tag: str, payload: bytes, held: str) -> str | None:
    """Whether ``payload`` is close enough to the resource a :func:`sketch` ``held`` records: None, or how it isn't.
    Every integer and the layout exact; each sum within what :data:`ULPS` ULPs on each of its floats (:data:`NEAR_ZERO`
    on one near zero, where another BLAS's rounding is a difference of about 1e-16 and no ULPs measure it) add up to.
    A float further off than its slot's room, a moved float or a changed integer is not."""
    digest, *sums = held.split()
    mine, got, room = _weighed(tag, payload, len(sums))
    if mine[:KEY] != digest:
        return "an integer or the layout differs"
    off = [(abs(g - float(w)), r) for g, w, r in zip(got, sums, room, strict=True) if abs(g - float(w)) > r]
    return f"{len(off)} of {len(sums)} float sums off, by {max(off)[0]:.3g} (room {max(off)[1]:.3g})" if off else None


@functools.cache
def _close() -> dict:
    return recorded(CLOSE)


def apart(name: str, built: Mapping[str, bytes], want: str, view_: Mapping | None, vanilla: bytes | None) -> list[str]:
    """How the built file ``name`` isn't close enough to the golden build's (its sha256 ``want``, for an XBR the
    golden's :func:`view` of it against ``vanilla``) on another host's float maths (D1016): nothing, or what differs.
    An XBR's sizes, tags, names, relocations, records and every byte outside its changed resources are exact, each
    changed resource :func:`near` its sketch; ``filelist.txt`` the same but for those XBRs' md5s, each its own
    file's. Any other file is exact: no float maths have reached one."""
    data, held = built[name], _close()
    if name == "filelist.txt":
        wrong = [row.path for row in filelist.rows(data) if row.path in built and row.md5 != filelist.md5(built[row.path])]
        return [f"filelist.txt: {path}'s md5 isn't its file's" for path in wrong] + (
            [] if held["frames"].get(want[:KEY]) == _listed(data)[:KEY] else ["filelist.txt: a line differs"])
    if name not in FLOATS or view_ is None or vanilla is None:
        return [f"{name}: sha256 {_sha256(data)[:12]}, not {want[:12]}"]
    got, payloads = view(vanilla, data, name), parts(vanilla, data)
    out = [f"{name}: {key}" for key in view_ if key not in ("sha256", "changed", "new") and got[key] != view_[key]]
    if held["frames"].get(want[:KEY]) != payloads[1][:KEY]:
        out.append(f"{name}: a byte outside its changed resources differs")
    for kind in ("changed", "new"):
        if [row[:3] + row[4:] for row in got[kind]] != [row[:3] + row[4:] for row in view_[kind]]:
            out.append(f"{name}: its {kind} resources aren't the golden's (their number, names, sizes or relocations)")
            continue
        out += [f"{name}: {mine[:3]}: {why}" for mine, row in zip(got[kind], view_[kind], strict=True) if mine != row
                and (why := near(*payloads[0][mine[3]], held["payloads"].get(row[3][:KEY], "0" * KEY)))]
    return out


def _resources(made, path: str, result: Mapping[str, str]) -> dict[str, dict]:
    """:func:`view` of each XBR a build changed (``result``)."""
    with iso.Reader(made) as built, iso.Reader(path) as vanilla:
        return {name: view(old, new, name) for name in sorted(result) if name.endswith(".xbr")
                and (new := built.read(name)) != (old := vanilla.read(name))}


def _sketches(made, path: str, result: Mapping[str, str]) -> dict[str, dict[str, str]]:
    """``close.json``'s rows of a build."""
    frames, payloads = {}, {}
    with iso.Reader(made) as built, iso.Reader(path) as vanilla:
        for name in result:
            if name == "filelist.txt":
                frames[result[name][:KEY]] = _listed(built.read(name))[:KEY]
            elif name in FLOATS:
                held, frame = parts(vanilla.read(name), new := built.read(name))
                frames[_sha256(new)[:KEY]] = frame[:KEY]
                payloads |= {sha[:KEY]: sketch(*part) for sha, part in held.items()}
    return {"frames": frames, "payloads": payloads}


def _job(job: tuple) -> tuple:
    """One build: ``("g3", golden, case, release, image)`` gives ``(its G3
    or G4 row, its resources or None, its ``close.json`` rows or None)``;
    ``("probe", case, release, image)`` its probe's record for the release
    and those rows."""
    kind, *rest, path = job
    if kind == "probe":
        case, name = rest
        probe = cases(PROBES)[case]
        with tempfile.TemporaryDirectory(prefix="azurkit-record-") as folder:
            character_ = probe["character"]
            if "variants" in probe:
                (recipes := Path(folder) / "probe.json").write_text(json.dumps(probe["variants"]), encoding="utf-8")
                character_ = character_ | {"variant_file": str(recipes)}
            made, report = sdk.image({"iso": path, "character": character_, "packs": _defaults()})
        return ({"files": {f: sha for f, sha in report["result"].items() if f != "filelist.txt"},
                 "resources": _resources(made, path, report["result"])}, _sketches(made, path, report["result"]))
    golden, case, name = rest
    spec = cases(golden)[case]
    with tempfile.TemporaryDirectory(prefix="azurkit-record-") as folder:
        made, report = sdk.image(recipe(golden, spec, path, Path(folder)) | {"iso": path})
    left = LEVEL_PATCHED if golden in G3 and level_patched(spec) else ()
    out = {f: sha for f, sha in report["result"].items()
           if f not in left and not (golden != "pipelines.json" and golden in G3 and shared(f))}
    if golden in G3 and not left:
        with iso.Reader(made) as r:
            files = {f: r.read(f) for f in report["result"] if f != "filelist.txt"}
        out["ISO"] = iso.read(path, files).sha256()
    dressed = wears(spec)
    return (out, _resources(made, path, report["result"]) if dressed else None,
            _sketches(made, path, report["result"]) if dressed else None)


def _layer(images: Images, release: gate.Release, spec: Mapping):
    pack = mods.PACKS[spec["pack"]]
    params = mods.normalize({pack.name: spec["params"]})[pack.name]
    base = {name: images.file(release, name) for name in pack.files()}
    return pack, base, mods.plan(pack, release, base, params)


def g1(images: Images, release: gate.Release, case: str, spec: Mapping) -> dict[str, str]:
    """A G1 case: ``default.xbe`` and each file its pack's layer writes."""
    pack, base, layer = _layer(images, release, spec)
    result = image(images.stamp(release), [layer], base)[1].result
    written = {engine.XBE, *(c.file for c in (*layer.changes, *layer.claims))}
    vanilla = {engine.XBE: facts.of(release).sha256} | {name: sha for name, (_, sha) in release.files.items()}
    return {NAMES.get(name, name): result.get(name, vanilla[name]) for name in written}


def sites(images: Images, release: gate.Release, case: str, spec: Mapping) -> dict[str, str]:
    """An XBE pack case's bytes at each facts site it changes (by sha256)."""
    pack, base, layer = _layer(images, release, spec)
    vanilla = base[engine.XBE]
    built = compose(base, [layer])[0].get(engine.XBE, vanilla)
    known, out = facts.of(release), {}
    for va, site in known.sites.items():
        s = max((s for s in known.sections if s.va <= va), key=lambda s: s.va)   # the slack is its section's
        at = s.raw + va - s.va
        if (span := bytes(built[at:at + site.size])) != vanilla[at:at + site.size]:
            out[f"0x{va:08X}"] = _sha256(span)
    return out


def editor(images: Images, release: gate.Release, case: str, spec: Mapping) -> dict[str, str]:
    """``config.xbr`` after the case's one edit: a number cell's value, or a string cell's text."""
    data = images.file(release, CONFIG)
    (table, entity, prop, value), = spec["edits"]
    doc = Document(data)
    writes = (edits.set_text(doc.tables[table], data, entity, prop, value) if isinstance(value, str)
              else edits.set_number(doc.tables[table], entity, prop, value))
    out = bytearray(data)
    for at, new in writes:
        out[at:at + len(new)] = new
    return {"config.xbr": _sha256(out)}


def build(golden: str) -> Callable[[Images, gate.Release, str, Mapping], dict[str, str]]:
    def run(images: Images, release: gate.Release, case: str, spec: Mapping) -> dict[str, str]:
        return images.built(("g3", golden, case, release.name))[0]
    return run


GOLDENS_BUILT = {   # golden -> (its release, what builds one case)
    "packs.json": (gate.USA, g1), "europe/packs.json": (gate.EUROPE, g1),
    "sites.json": (gate.USA, sites), "europe/sites.json": (gate.EUROPE, sites),
    "xbr_editor.json": (gate.USA, editor),
    "pipelines.json": (gate.USA, build("pipelines.json")),
    "europe/pipelines.json": (gate.EUROPE, build("europe/pipelines.json")), "gui.json": (gate.USA, build("gui.json")),
}
CASED = (*GOLDENS_BUILT, PROBES, MATCHES, PLANS)
"""The goldens whose rows are their cases' (``resources.json``'s are G3's that dress the player, ``shims.json``'s
the objects)."""


def shims(images: Images) -> dict[str, dict]:
    """G2: each shim's prebuilt object, by its normalized sha256: the packs'
    and the swap's, its held bytes written back (``ports.restored``)."""
    from azurkit.tools.characters import ports

    vanilla = ports.Vanilla(gate.USA, images.stamp(gate.USA).path)
    out = {f"{p.stem}.o": {"normalized sha256": coff.normalized_sha256(p.read_bytes())}
           for p in sorted(SHIMS.glob("*.o"))}
    return out | {f"player_model_{p.stem}.o": {"normalized sha256": coff.normalized_sha256(
        ports.restored(p.stem, coff.parse(p.read_bytes()), vanilla))} for p in sorted(PLAYER_MODEL.glob("*.o"))}


def matches(images: Images) -> dict[str, dict]:
    """The match-Garret values (``sdk.match``) of each recipe on USA over the
    packs on by default: Model size, Attack reach, speed and damage, and why
    none matches where none does."""
    from azurkit.tools import characters

    path = str(images.stamp(gate.USA).path)
    out = {}
    for name, worn in cases(MATCHES)["usa"].items():
        got = sdk.match({"iso": path, "packs": _defaults(), "character": worn})
        out[name] = {k: got["values"][slider] for k, slider in zip(("size", "reach", "speed", "damage"),
                                                                    characters.MATCHED)} | {"why": got["why"]}
    return {"usa": out}


def plan_recipe(case: Mapping) -> dict:
    """A ``rando_plans.json`` case (Modkit's seed and ``Settings`` fields) as
    the sdk's recipe, its settings as a settings file holds them."""
    from azurkit.tools.randomizer.planner.fill import settings_table
    from azurkit.tools.randomizer.planner.settings import Settings

    st = case["settings"]
    return {"seed": case["seed"], "settings": settings_table(Settings(
        st["skip_ceiling"], st["movement_tier"], st["skip_override"],
        frozenset(st["exclude_categories"]), st["sliders"]))}


@functools.cache
def profile(name: str) -> dict:
    """The plan file's object of ``rando_plans.json``'s case ``name`` (seed 2 under strict, default or max)."""
    return sdk.plan(plan_recipe(cases(PLANS)[name]))


def plans() -> dict[str, dict]:
    """``rando_plans.json``: each case's plan's attempt and sha256, its
    spoiler file's sha256 (``azurkit spoiler``'s lines) and, for the case
    marked ``file``, the plan file's object."""
    out = {}
    for name, case in cases(PLANS).items():
        doc, spoiler = profile(name), "\n".join(sdk.spoiler(profile(name))["lines"]) + "\n"
        out[name] = {"attempt": doc["attempt"], "sha256": doc["sha256"], "spoiler": _sha256(spoiler.encode())} | (
            {"plan": json.loads(json.dumps(doc))} if case.get("file") else {})
    return out


def shows_gems(marks: Mapping | None) -> bool:
    """A :func:`tracker_states` state the tracker shows with Gems on: its marks hold gems taken."""
    return bool((marks or {}).get("gems"))


def tracker_states(view: Callable, doc: dict) -> list[tuple]:
    """(state, marks, kit) of ``tracker.json``'s states for ``doc``, through
    ``view(doc, marks, spoiler)`` (a host's tracker): none, no mark; mid,
    three rounds of marking every spot reachable now; powers, every spot the
    plan put a power at; kit, no mark and Live's kit at air, water, fire and
    earth 3 (:data:`KIT`); gems (Step 4.2c3, R1.43), mid's marks with Live's
    gems taken at the first cluster (all its gems), the second (one) and the
    first gem (a host shows the gems when its marks hold some:
    :func:`shows_gems`)."""
    from azurkit.tools.randomizer.planner.loader import kept_logic

    mid = []
    for _ in range(3):
        spots = view(doc, {"collected": mid}, False)["spots"]
        mid = sorted(set(mid) | {loc for loc, s in spots.items() if s["state"] in ("near", "skip")})
    powers = sorted(loc for loc, s in view(doc, None, True)["spots"].items() if s["item"].startswith("power_"))
    full = {loc["id"]: loc["yield"] for g in kept_logic().db.generated.values() for loc in g["locations"]
            if loc["pool"] and not loc["dead"] and loc["class"] in ("gem", "cluster")}
    cluster, single = (sorted(loc for loc, n in full.items() if (n > 1) == c) for c in (True, False))
    gems = {cluster[0]: [0.5] * full[cluster[0]], cluster[1]: [None], single[0]: [1.25]}
    return [("none", None, None), ("mid", {"collected": mid}, None), ("powers", {"collected": powers}, None),
            ("kit", None, KIT), ("gems", {"collected": mid, "gems": gems}, None)]


#: The maps' model of each tracker view, as the page draws it (``web/mapview.mjs``'s ``marks()`` for each level and
#: ``badges()``, with the icons the engine draws): one canonical JSON text a view (``tests/test_site.py``'s MAP_MODEL
#: in the page), under ``node``, the views, levels and icons on its stdin.
MAP_MODEL = """import { marks, badges } from %s;
let text = "";
for await (const chunk of process.stdin) text += chunk;
const [views, levels, icons] = JSON.parse(text), have = (name) => icons.includes(name);
const sorted = (v) => Array.isArray(v) ? v.map(sorted) : v && typeof v === "object"
  ? Object.fromEntries(Object.keys(v).sort().map((k) => [k, sorted(v[k])])) : v;
process.stdout.write(JSON.stringify(views.map((view) => JSON.stringify(sorted({
  levels: Object.fromEntries(levels.map((lv) => [lv, marks(view, lv, have)])), badges: badges(view) })))));
"""


def tracker() -> dict[str, dict]:
    """``tracker.json``: by ``<case>/<state>/<plain|spoiler>``, the
    ``sha256[:32]`` of the tracker's view of the case's plan at each of
    :func:`tracker_states`' states (``view``) and of :data:`MAP_MODEL`'s
    model of it (``map``)."""
    from azurkit.tools.randomizer import tracking
    from azurkit.tools.randomizer.art import icons

    def view(doc, marks, spoiler, kit=None):
        return sdk.tracker({"plan": doc, "marks": marks, "kit": kit, "spoiler": spoiler, "gems": shows_gems(marks)})

    views = {}   # key -> (its view's digest, its view as JSON)
    for name, case in cases(TRACKER).items():
        doc = profile(case["plan"])
        for state, marks, kit in tracker_states(view, doc):
            for spoiler in (False, True):
                got = view(doc, marks, spoiler, kit)
                views[f"{name}/{state}/{'spoiler' if spoiler else 'plain'}"] = (tracking.digest(got), json.dumps(got))
    given = (f"[[{','.join(text for _, text in views.values())}],{json.dumps(list(tracking.GRID))},"
             f"{json.dumps(icons.names())}]")
    run = subprocess.run(["node", "--input-type=module", "--eval", MAP_MODEL % json.dumps(MAPVIEW.as_uri())],
                         input=given, capture_output=True, text=True, check=True)
    return {key: {"map": _sha256(model.encode())[:32], "view": _sha256(digest.encode())[:32]}
            for (key, (digest, _)), model in zip(views.items(), json.loads(run.stdout), strict=True)}


def _art_part(job: tuple[str, str]) -> tuple[str, dict]:
    path, part = job
    return part, sdk.art(path, part)


def _art_detail(job: tuple[str, str, float]) -> tuple[str, dict[str, bytes]]:
    from azurkit.tools.randomizer import art as drawn

    path, level, factor = job
    with drawn.Vanilla(path) as reader:
        return level, {name: drawn.png(img) for name, img in drawn.detail(reader, level, factor).items()}


def art(images: Images, workers: int, detail: Collection[str] | None = None) -> dict[str, bytes]:
    """The tracker's pictures the page ships, by their path: drawn from the
    USA image (``sdk.art``, one part a process, then ``sdk.art_world``;
    Europe's draw the same, ``tests/test_art.py``) under ``ART_VERSION``
    each picture (``icons.png``, the icon sheet; each floor's, ``world.png``),
    ``maps.json`` and ``floors.json`` (each level's storeys, the floor under
    a point, Live's Follow's: ``maps.storeys``), then each coarse level's floors again finer
    (``detail/<floor>.png``: ``art.detail`` at its ``art.detail_factor``,
    the largest first; only ``detail``'s levels when it names them, the
    tests'), ``index.json``, that version, where the sheet's tiles are
    (``icons``) and every coarse level's factor (``detail``), which the
    site's page reads first (``web/art.mjs``), and ``icons.css``, the
    tiles for the page's lists (``art.icons.css``)."""
    from azurkit.tools.randomizer import art as drawn
    from azurkit.tools.randomizer import tracking

    path, v = str(images.stamp(gate.USA).path), tracking.ART_VERSION
    order = sorted(tracking.ART_PARTS, key=lambda p: LONGEST.index(p) if p in LONGEST else len(LONGEST))
    with ProcessPoolExecutor(max(1, workers), mp_context=multiprocessing.get_context("spawn")) as pool:
        got = dict(pool.map(_art_part, [(path, part) for part in order]))
        factors = {lv: f for lv in tracking.GRID if (f := drawn.detail_factor(got[lv]["entry"])) is not None}
        finer = dict(pool.map(_art_detail, [(path, lv, factors[lv]) for lv in sorted(
            set(factors) if detail is None else set(factors) & set(detail),
            key=lambda lv: -factors[lv] ** 2 * got[lv]["entry"]["size"][0] * got[lv]["entry"]["size"][1])]))
    world = sdk.art_world({lv: {"entry": got[lv]["entry"], "thumb": got[lv]["thumb"]} for lv in tracking.GRID})
    out = {f"{v}/{name}.png": png for part in tracking.ART_PARTS for name, png in got[part]["pictures"].items()}
    out |= {f"{v}/{name}.png": png for lv in sorted(finer) for name, png in finer[lv].items()}
    shipped = {"version": v, "icons": got["icons"]["sheet"], "detail": factors}
    floors = {"unit": drawn.maps.STOREY_M, "levels": {lv: got[lv]["floors"] for lv in sorted(tracking.GRID)}}
    out |= {f"{v}/world.png": world["pictures"]["world"], f"{v}/maps.json": world["text"].encode(),
            f"{v}/floors.json": (json.dumps(floors, separators=(",", ":")) + "\n").encode(),
            "index.json": (json.dumps(shipped) + "\n").encode(),
            "icons.css": drawn.icons.css(v, got["icons"]["sheet"]).encode()}
    return {f"{ART}/{rel}": data for rel, data in out.items()}


def _variant(job: tuple[str, str]) -> tuple[str, dict | str]:
    """A built-in variant's two pictures at its recipe's defaults over the packs on by default (``sdk.preview``'s
    dress, as the page asks it), or why the engine refuses it."""
    path, name = job
    try:
        return name, sdk.preview({"iso": path, "packs": _defaults(), "character": {"species": name}})
    except ValueError as exc:
        return name, str(exc)


def recipe_keys(doc: Mapping) -> dict[str, str]:
    """Each built-in variant's key in ``web/characters/index.json``: the sha256 of its recipe as it builds
    (``recipe_of``: one ``from`` another with that one laid under it), so a look from booblord is drawn again when
    hers changes (Step 4.3's vase), not only when its own entry does; its title and notes draw nothing."""
    from azurkit.tools.characters import _player_variants as variants

    return {name: hashlib.sha256(json.dumps({k: v for k, v in variants.recipe_of(dict(doc), name, "built-in")[0].items()
                                             if k not in variants.LABELS}, sort_keys=True).encode()).hexdigest()
            for name in doc}


def characters(images: Images, workers: int) -> dict[str, bytes]:
    """The Characters tab's shipped files, by their path: ``species.json``,
    the ``[species, body, object]`` of each species the player can wear in
    ``critters_engine``'s order, as ``player_models`` and
    ``characters.object_bodies`` read both images (which agree, or this
    stops naming them); in ``web/characters/`` each
    body's two pictures (``picker.preview`` on the USA image, the app's
    draw: Europe's are the same, ``tests/test_characters.py``), each
    built-in variant's (:func:`_variant`; none for one the engine refuses),
    drawn again only when its recipe as it builds changes (:func:`recipe_keys`),
    and ``index.json``: the engine's view with no image and
    no content installed (``picker.view``, garret4 at every default), each
    species' and variant's pictures' file name and each variant's recipe
    digest (one refused too, so it isn't dressed at each check), and each
    weapon's preview: its title, line (``weapons.json``'s ``previews``) and
    pictures, an object's own (``picker.weapon_preview``, USA's) or those of
    the model it names."""
    from azurkit.tools import characters as kit
    from azurkit.tools.characters import _player_character as swap
    from azurkit.tools.characters import _player_variants as variants
    from azurkit.tools.characters import _player_weapons as arms
    from azurkit.tools.characters import content, picker
    from azurkit.tools.characters.characters import object_bodies

    read = {r: sdk._game(str(images.stamp(r).path))[1:] for r in gate.RELEASES}
    things = {r: object_bodies(read[r][1]) for r in read}
    rows = {r: [[m.species, m.body, m.body.casefold() in things[r]] for m in swap.player_models(*read[r])
                if m.status != swap.REFUSED] for r in read}
    if rows[gate.USA] != rows[gate.EUROPE]:
        raise SystemExit("species.json: the USA and Europe images list different species (player_models)")
    stem = lambda name: name.replace("/", "--")   # noqa: E731 (a body's file name)
    out = {SPECIES: (json.dumps(rows[gate.USA], separators=(",", ":")) + "\n").encode()}
    for body in dict.fromkeys(body for _, body, _ in rows[gate.USA]):
        out |= {f"{PICTURES}/{stem(body)}.{view}.png": png for view, png in picker.preview(read[gate.USA][1], body).items()}
    recipes = recipe_keys(json.loads(variants.BUILTIN.read_text(encoding="utf-8")))
    index = ROOT / PICTURES / "index.json"
    was = json.loads(index.read_text(encoding="utf-8")) if index.is_file() else {"recipes": {}, "variants": {}}
    files = lambda name: [f"{PICTURES}/variant--{stem(name)}.{view}.png" for view in ("front", "back")]   # noqa: E731
    kept = {n for n, key in recipes.items() if was["recipes"].get(n) == key
            and (n not in was["variants"] or all((ROOT / f).is_file() for f in files(n)))}
    drawn = [n for n in was["variants"] if n in kept]
    out |= {f: (ROOT / f).read_bytes() for n in drawn for f in files(n)}
    with ProcessPoolExecutor(max(1, workers), mp_context=multiprocessing.get_context("spawn")) as pool:
        for name, got in pool.map(_variant, [(str(images.stamp(gate.USA).path), n) for n in recipes if n not in kept]):
            if isinstance(got, dict):
                drawn.append(name)
                out |= dict(zip(files(name), (got["front"], got["back"])))
    shown = {s: stem(b) for s, b, _ in rows[gate.USA]} | {n: f"variant--{stem(n)}" for n in drawn}
    previews = {}
    for name, weapon in arms.weapons().items():
        said = arms.previews()[name]
        previews[name] = {"title": weapon.title, "line": said["line"],
                          "file": shown[said["model"]] if weapon.prop is None else f"weapon--{name}"}
        if weapon.prop is not None:
            out |= {f"{PICTURES}/weapon--{name}.{view}.png": png
                    for view, png in picker.weapon_preview(read[gate.USA][1], name).items()}
    real = picker.species_list
    picker.species_list = lambda: rows[gate.USA]   # the list just read, whatever species.json holds now
    try:
        with tempfile.TemporaryDirectory(prefix="azurkit-record-") as empty:
            view = picker.view(None, None, kit.normalize({"species": swap.PLAYER}), {"entries": content.states(None, {})},
                               Path(empty))
    finally:
        picker.species_list = real
    out[f"{PICTURES}/index.json"] = (json.dumps({
        "view": view, "species": {s: stem(b) for s, b, _ in rows[gate.USA]},
        "variants": {n: f"variant--{stem(n)}" for n in sorted(drawn)}, "recipes": recipes, "weapons": previews},
        sort_keys=True, separators=(",", ":")) + "\n").encode()
    return out


SHIPPED = {"art": (art, (ART,)), "characters": (characters, (PICTURES, SPECIES))}
"""Each family of shipped files: what makes them (``{path: bytes}``, from the checkout's root) and the paths it owns
(a folder's every file, which a recording leaves holding only what it made)."""


def kept_files(paths) -> dict[str, bytes]:
    """The files the checkout holds at ``paths`` (each a file, or a folder's every file but dot files)."""
    out = {}
    for rel in paths:
        if (where := ROOT / rel).is_file():
            out[rel] = where.read_bytes()
        for file in sorted(where.rglob("*")) if where.is_dir() else ():
            if file.is_file() and not file.name.startswith("."):
                out[file.relative_to(ROOT).as_posix()] = file.read_bytes()
    return out


def ship(made: Mapping[str, bytes], gone) -> None:
    """Write each file of ``made`` and remove each path of ``gone`` (and a folder it leaves empty)."""
    for rel, data in made.items():
        (ROOT / rel).parent.mkdir(parents=True, exist_ok=True)
        (ROOT / rel).write_bytes(data)
    for rel in gone:
        (ROOT / rel).unlink()
        for folder in (ROOT / rel).parents:
            if folder == ROOT or any(folder.iterdir()):
                break
            folder.rmdir()


def jobs(goldens) -> list[tuple]:
    """The builds that dress the player ``goldens`` need (:func:`_job`)."""
    out = [("g3", g, case, GOLDENS_BUILT[g][0].name) for g in G3 if g in goldens or RESOURCES in goldens or CLOSE in goldens
           for case, spec in cases(g).items() if wears(spec)]
    return out + [("probe", case, r.name) for case in (cases(PROBES) if PROBES in goldens or CLOSE in goldens else ())
                  for r in gate.RELEASES]


def record(golden: str, images: Images) -> dict[str, dict]:
    """The golden as AzurKit builds it."""
    if golden == "shims.json":
        return shims(images)
    if golden == MATCHES:
        return matches(images)
    if golden == PLANS:
        return plans()
    if golden == TRACKER:
        return tracker()
    if golden == PROBES:
        return {case: probe | {r.name: images.built(("probe", case, r.name))[0] for r in gate.RELEASES}
                for case, probe in cases(PROBES).items()}
    if golden == CLOSE:
        made = {"frames": {}, "payloads": {}}
        for job in jobs((CLOSE,)):
            for key, held in images.built(job)[-1].items():
                made[key] |= held
        return made
    if golden == RESOURCES:
        return {f"tests/goldens/{g}": {case: images.built(("g3", g, case, GOLDENS_BUILT[g][0].name))[1]
                                       for case, spec in cases(g).items() if wears(spec)} for g in G3}
    release, one = GOLDENS_BUILT[golden]
    return {case: one(images, release, case, spec) for case, spec in cases(golden).items()}


def rows(golden: str, data: Mapping) -> Mapping:
    """A golden's rows by case (``resources.json``'s by its G3 golden and case)."""
    return {f"{g}: {case}": row for g, held in data.items() for case, row in held.items()} if golden == RESOURCES else data


def text(rows: Mapping) -> str:
    return json.dumps(rows, indent=1, sort_keys=True) + "\n"


def write(path: Path, data: str) -> None:
    """``data`` written to ``path`` whole, then renamed into place: a
    re-record that stops partway leaves the old golden, and a test reading
    the goldens meanwhile never reads half of one (Modkit's Step X.81e)."""
    part = path.with_name(f".{path.name}.{os.getpid()}.part")
    try:
        part.write_text(data, encoding="utf-8")
        os.replace(part, path)
    finally:
        part.unlink(missing_ok=True)


def main(argv: list[str] | None = None, images: Images | None = None) -> int:
    names = [*GOLDENS_BUILT, "shims.json", RESOURCES, CLOSE, PROBES, MATCHES, PLANS, TRACKER, *SHIPPED]
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="write nothing; exit 1 naming each case that differs")
    ap.add_argument("--workers", type=int, default=4,
                    help="processes for the builds that dress the player and the shipped pictures (4)")
    ap.add_argument("golden", nargs="*", help=f"the goldens to record (default: all): {', '.join(names)}")
    args = ap.parse_args(argv)
    if unknown := [g for g in args.golden if g not in names]:
        ap.error(f"no golden {', '.join(unknown)} (the goldens: {', '.join(names)})")
    images, drift, goldens = images or Images(), [], args.golden or names
    images.prebuild(jobs(goldens), args.workers)
    for family in [g for g in goldens if g in SHIPPED]:
        make, paths = SHIPPED[family]
        made, now = make(images, args.workers), kept_files(paths)
        differs = sorted(rel for rel in made.keys() | now.keys() if made.get(rel) != now.get(rel))
        drift += [f"{family}: {rel}" for rel in differs]
        if not args.check and differs:
            ship({rel: made[rel] for rel in differs if rel in made}, [rel for rel in differs if rel not in made])
            print(f"wrote: {family} ({len(differs)} files)")
    for golden in [g for g in goldens if g not in SHIPPED]:
        made, path = record(golden, images), GOLDENS / golden
        held = recorded(golden) if path.exists() else {}
        new, old = rows(golden, made), rows(golden, held)
        drift += [f"{golden}: {case}" for case in sorted(new.keys() | old.keys()) if new.get(case) != old.get(case)]
        if not args.check and text(made) != (path.read_text(encoding="utf-8") if path.exists() else None):
            path.parent.mkdir(parents=True, exist_ok=True)
            write(path, text(made))
            print(f"wrote: {golden}")
    for line in drift:
        print(f"{'differs' if args.check else 'changed'}: {line}")
    return 1 if args.check and drift else 0


if __name__ == "__main__":
    sys.exit(main())
