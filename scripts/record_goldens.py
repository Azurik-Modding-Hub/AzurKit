"""Record AzurKit's goldens, ``tests/goldens/``, from its own builds on the
player's images: what each case of ``tests/goldens/cases.json`` (its recipe,
edited by hand) builds, as names and sha256 only.

    uv run --locked python scripts/record_goldens.py [--check] [GOLDEN ...]

- ``packs.json`` and ``europe/packs.json`` (G1): a pack alone at the case's
  sliders, from the release's vanilla files: ``default.xbe`` and each file
  the pack's layer writes (``config.xbr`` by that name), at vanilla's sha256
  where the writes leave it so.
- ``sites.json`` and ``europe/sites.json``: each XBE pack case's bytes at
  every facts site it changes, by the release's own address (USA's ``.text``
  slack, past its section's file bytes, counts).
- ``shims.json`` (G2): each pack shim's prebuilt object's normalized
  sha256 (``tests/test_shims.py`` holds each object to its source's build).
- ``xbr_editor.json``: ``config.xbr`` after one cell's edit.
- ``pipelines.json`` (G3) and ``gui.json`` (G4): a whole build's recipe
  through the sdk (Modkit's flags and GUI ticks, translated by
  :func:`recipe`): each file it changes, and for G3 the image without the
  build's root entries (``ISO``). A case that moves a level entity leaves
  out ``gamedata/training_room.xbr``, ``filelist.txt`` and ``ISO``
  (:data:`LEVEL_PATCHED`: AZ-009, level_patches isn't ported).

The first recording is Modkit's last cut for the core and packs families
(oracle-packs-4, Modkit 28d0b4110), which this script's first run wrote
back unchanged (Step 4.12a). Only it changes these files, and a commit that
does names each golden it changed and why. ``--check`` writes nothing and
exits 1 naming each case that differs. The images are the ones the gate
finds (``AZURKIT_ISO``, ``AZURKIT_ISO_EUROPE``, else the user data folder).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

from azurkit import sdk
from azurkit.core import coff, facts, gate, iso
from azurkit.core.xbr import Document, edits
from azurkit.edits.layer import compose
from azurkit.edits.manifest import image
from azurkit.tools import mods
from azurkit.tools.mods import engine

ROOT = Path(__file__).resolve().parent.parent
GOLDENS = ROOT / "tests" / "goldens"
CASES = GOLDENS / "cases.json"
SHIMS = ROOT / "src" / "azurkit" / "tools" / "mods" / "shims"   # shimkit.SHIMS: the packs' shims and objects
CONFIG = engine.CONFIG
NAMES = {CONFIG: "config.xbr"}   # a file's name in G1 and the editor's golden (Modkit's)
LEVEL_PATCHED = ("gamedata/training_room.xbr", "filelist.txt", "ISO")
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


def recipe(golden: str, case: Mapping, path) -> dict:
    """A G3 (``pipelines.json``) or G4 (``gui.json``) case's recipe as a mods
    file's: apply-physics applies player_physics alone; patch,
    randomize-full (--no-randomize) and MCP pack_build_iso the packs on by
    default and those they name, then the mod's operations; a GUI build its
    ticks over the packs on by default, its sliders and the Game Data
    editor's cells."""
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
    if not (args["command"] == "randomize-full" and args["no_randomize"] and args["ram"] == 128):
        raise ValueError(f"a G3 case AzurKit doesn't translate: {args['command']}")
    physics = {RANDOMIZE[k]: v for k, v in args.items() if k in RANDOMIZE and v is not None}
    return {"packs": _defaults() | ({"player_physics": physics} if physics else {}),
            "xbr": _ops(args["config_mod"] or {}, path)}


def level_patched(case: Mapping) -> bool:
    """Whether a G3 case's mods move a level entity (AZ-009)."""
    args = case["args"]
    mods_ = args.get("mod") or [args.get("config_mod") or {}]
    return any(mod.get("level_patches") for mod in mods_)


class Images:
    """Each release's verified image and its vanilla files, read once."""

    def __init__(self, paths: Mapping[gate.Release, Path] | None = None):
        self._paths, self._stamps, self._files = dict(paths or {}), {}, {}

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


def _layer(images: Images, release: gate.Release, spec: Mapping):
    pack = mods.PACKS[spec["pack"]]
    params = mods.normalize({pack.name: spec["params"]})[pack.name]
    base = {name: images.file(release, name) for name in pack.files()}
    return pack, base, mods.plan(pack, release, base, params)


def g1(images: Images, release: gate.Release, spec: Mapping) -> dict[str, str]:
    """A G1 case: ``default.xbe`` and each file its pack's layer writes."""
    pack, base, layer = _layer(images, release, spec)
    result = image(images.stamp(release), [layer], base)[1].result
    written = {engine.XBE, *(c.file for c in (*layer.changes, *layer.claims))}
    vanilla = {engine.XBE: facts.of(release).sha256} | {name: sha for name, (_, sha) in release.files.items()}
    return {NAMES.get(name, name): result.get(name, vanilla[name]) for name in written}


def sites(images: Images, release: gate.Release, spec: Mapping) -> dict[str, str]:
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


def editor(images: Images, release: gate.Release, spec: Mapping) -> dict[str, str]:
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


def build(golden: str) -> Callable[[Images, gate.Release, Mapping], dict[str, str]]:
    def run(images: Images, release: gate.Release, spec: Mapping) -> dict[str, str]:
        path = images.stamp(release).path
        made, report = sdk.image(recipe(golden, spec, path) | {"iso": str(path)})
        left = LEVEL_PATCHED if golden == "pipelines.json" and level_patched(spec) else ()
        out = {name: sha for name, sha in report["result"].items() if name not in left}
        if golden == "pipelines.json" and not left:
            with iso.Reader(made) as r:
                files = {name: r.read(name) for name in report["result"] if name != "filelist.txt"}
            out["ISO"] = iso.read(path, files).sha256()
        return out
    return run


GOLDENS_BUILT = {   # golden -> (its release, what builds one case)
    "packs.json": (gate.USA, g1), "europe/packs.json": (gate.EUROPE, g1),
    "sites.json": (gate.USA, sites), "europe/sites.json": (gate.EUROPE, sites),
    "xbr_editor.json": (gate.USA, editor),
    "pipelines.json": (gate.USA, build("pipelines.json")), "gui.json": (gate.USA, build("gui.json")),
}


def shims() -> dict[str, dict]:
    """G2: each pack shim's prebuilt object, by its normalized sha256."""
    return {f"{p.stem}.o": {"normalized sha256": coff.normalized_sha256(p.read_bytes())}
            for p in sorted(SHIMS.glob("*.o"))}


def record(golden: str, images: Images) -> dict[str, dict]:
    """The golden as AzurKit builds it."""
    if golden == "shims.json":
        return shims()
    release, one = GOLDENS_BUILT[golden]
    return {case: one(images, release, spec) for case, spec in cases(golden).items()}


def text(rows: Mapping) -> str:
    return json.dumps(rows, indent=1, sort_keys=True) + "\n"


def main(argv: list[str] | None = None, images: Images | None = None) -> int:
    names = [*GOLDENS_BUILT, "shims.json"]
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="write nothing; exit 1 naming each case that differs")
    ap.add_argument("golden", nargs="*", help=f"the goldens to record (default: all): {', '.join(names)}")
    args = ap.parse_args(argv)
    if unknown := [g for g in args.golden if g not in names]:
        ap.error(f"no golden {', '.join(unknown)} (the goldens: {', '.join(names)})")
    images, drift = images or Images(), []
    for golden in args.golden or names:
        rows, path = record(golden, images), GOLDENS / golden
        held = recorded(golden) if path.exists() else {}
        drift += [f"{golden}: {case}" for case in sorted(rows.keys() | held.keys()) if rows.get(case) != held.get(case)]
        if not args.check and text(rows) != (path.read_text(encoding="utf-8") if path.exists() else None):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text(rows), encoding="utf-8")
            print(f"wrote: {golden}")
    for line in drift:
        print(f"{'differs' if args.check else 'changed'}: {line}")
    return 1 if args.check and drift else 0


if __name__ == "__main__":
    sys.exit(main())
