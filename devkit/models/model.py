"""``python -m devkit models model LEAF [ARGS ...]``: a character body's
verbs (Modkit's ``azurik-mod model``, ported leaf by leaf from Step 4.15a1),
the ones ModelKit's adapter calls.

- ``dress`` dresses a variant (a built-in, or one of ``--variant-file``'s,
  with ``--recipe``'s fields laid over it) as a build dresses it, in memory
  on the verified vanilla image (D27), and writes its ``characters.xbr`` and
  ``index.xbr`` once the dress passed (D35).
- ``inspect`` reports a body's counts, budgets and problems.
- ``export`` writes a body as glTF 2.0 for Blender.
- ``jiggle`` previews a dressed variant's real-time springs (X41's twin,
  ``jiggle_rt``) over the physics scenarios and its clips (Step 4.15a3).
- ``pose`` writes every bone's world each tick of its clips with those
  springs, as an ``.npz``.
- ``rest`` writes a variant's rest positions for other values of its mesh
  ops on its frozen mesh (a shape slider's ends).
- ``preview`` renders a body's pictures with headless Blender.

A leaf reads ``--iso``'s image, else the one AzurKit finds
(``devkit.models.image``); ``inspect`` and ``export`` read any image, a
build's too, or ``--characters`` (a built ``characters.xbr``: ``dress
--out``'s). What a leaf writes (``--out``) is a game asset: a new or empty
folder (``pose``: a new file) outside this checkout and the images' folders
(D36). It prints counts, sizes and ``sha256``, never a byte or a
coordinate. A refusal is one ``model LEAF: ...`` line on stderr and exit
1, as Modkit's; a usage error exits 2."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

from azurkit.tools.characters.model_inspect import RAMS
from devkit.models import dress as dressing
from devkit.models import image


def _refused(leaf: str, exc: Exception) -> int:
    print(f"model {leaf}: {exc}", file=sys.stderr)
    return 1


def _variant(args):
    """``args.variant`` (a built-in, or one of ``--variant-file``'s), with
    ``--recipe``'s fields laid over its recipe where the leaf takes one
    (``_player_variants.laid_over``); ``ValueError`` names a name that is no
    variant."""
    from azurkit.tools.characters._player_variants import laid_over, resolve

    variant = resolve(args.variant, args.variant_file)
    if variant is None:
        raise ValueError(f"{args.variant!r} is no variant")
    if getattr(args, "recipe", None):
        variant = laid_over(variant, json.loads(Path(args.recipe).read_text(encoding="utf-8")))
    return variant


def _dress(args) -> int:
    """``dress`` (Step X.65f): print the dress's log and the files' sizes and
    sha256 (``--json``: one object, W24's plan as numbers too)."""
    try:
        variant = _variant(args)
        iso = image.find(args.iso)
        out = image.output(args.out, iso)
        d = dressing.dress(variant, iso, ram=args.ram)
        files = dressing.write(out, d.game)
    except (OSError, ValueError) as exc:
        return _refused("dress", exc)
    if args.json:
        print(json.dumps({"variant": variant.name, "base": variant.base, "body": d.body, "ram": args.ram,
                          "recipe_sha": variant.sha, "seconds": round(d.seconds, 3), "out": str(out),
                          "files": {n: {"bytes": size, "sha256": sha} for n, (size, sha) in files.items()},
                          "plan": dressing.numbers(d.plan), "spring_rows": len(d.springs.get("rows", ())),
                          "log": list(d.log)}, indent=1))
        return 0
    print(f"{variant.name} (a variant of {variant.base}, wearing {d.body}): dressed in {d.seconds:.0f} s on the "
          f"default packs for {args.ram} MiB")
    for line in d.log:
        print(f"  {line}")
    print("wrote " + ", ".join(f"{out / n} ({size:,} B, sha256 {sha[:12]})" for n, (size, sha) in files.items()))
    return 0


def _characters(args) -> tuple[bytes, bytes, Path]:
    """``--characters`` (a characters.xbr file) or the image's, the image's
    config.xbr and the image read."""
    iso = image.find(args.iso)
    config, *found = image.read(iso, "gamedata/config.xbr", *(() if args.characters else ("gamedata/characters.xbr",)))
    return (Path(args.characters).read_bytes() if args.characters else found[0]), config, iso


def _inspect(args) -> int:
    """``inspect`` (Step 2.154): ``model_inspect``'s report on the body, its
    own load runs against the game's budget (with the image's fx.xbr when no
    ``--characters`` is given; the budget ``--memory-budget``'s, else a built
    image's default.xbe's, else what a build writes by default, D528;
    ``--ram`` the lines of a 64, 128 or 256 MiB machine, unless a built
    image lacks their packs); exit 1 when a problem, a format limit or the
    game's budget is passed (a warning only prints)."""
    from azurkit.core import facts, gate
    from azurkit.tools.characters import gltf, model_inspect

    try:
        characters, config, iso = _characters(args)
        body, _ = gltf.resolve_body(characters, config, args.body)
        fx = None if args.characters else image.read(iso, "gamedata/fx.xbr")[0]
        if args.memory_budget is not None and not math.isfinite(args.memory_budget):
            raise ValueError(f"--memory-budget {args.memory_budget} is not finite")
        xbe = None if args.characters or args.memory_budget is not None else image.read(iso, "default.xbe")[0]
        built = xbe is not None and hashlib.sha256(xbe).hexdigest() not in {facts.of(r).sha256 for r in gate.RELEASES}
        with image.swap(xbe if built else None):
            budget = (round(args.memory_budget * model_inspect.MiB) if args.memory_budget is not None
                      else model_inspect.budget_of(xbe) if built else model_inspect.default_budget())
            ram = args.ram
            if built and (got := model_inspect.lines_ram(xbe, ram)) != ram:
                lacks = model_inspect.UPPER_PACKS if got == 64 else (model_inspect.UPPER256_PACK,)
                print(f"model inspect: --ram {ram}: {iso}'s default.xbe lacks {' or '.join(lacks)}, "
                      f"so the {got} MiB lines", file=sys.stderr)
                ram = got
            report = model_inspect.inspect(characters, body, fx_xbr=fx, config_xbr=config, budget=budget, ram=ram)
    except (OSError, ValueError) as exc:
        return _refused("inspect", exc)
    print(json.dumps(report, indent=1) if args.json else "\n".join(model_inspect.lines(report)))
    return 1 if report["problems"] or any(b["level"] == "error" for b in report["budgets"]) else 0


def _export(args) -> int:
    """``export`` (Step 2.139, D332): the body as glTF 2.0
    (``gltf.export_body``), ``--clips`` a comma list; print counts and the
    checks' numbers."""
    from azurkit.tools.characters import gltf

    try:
        characters, config, iso = _characters(args)
        inputs = (iso, *([Path(args.characters)] if args.characters else []))
        out = image.output(args.out, *inputs)
        body, species = gltf.resolve_body(characters, config, args.body)
        if species:
            print(f"{species} wears {body}")
        clips = [c.strip() for c in args.clips.split(",") if c.strip()] if args.clips else None
        e = gltf.export_body(characters, body, out, clips, source_vanilla=gltf.vanilla_characters(characters),
                             protect=inputs)
    except (OSError, ValueError) as exc:
        return _refused("export", exc)
    c = e.checks
    print(f"{e.body}: {e.groups} groups, {e.vertices} vertices, {e.triangles} triangles, "
          f"{e.bones + e.helpers} joints ({e.bones} bones, {e.helpers} scale helpers), {e.materials} materials, "
          f"{e.textures} textures, {e.clips} clips ({e.channels} channels) -> {e.gltf}")
    if e.skipped:
        print(f"skipped {len(e.skipped)} clips with no bone track: {', '.join(e.skipped)}")
    if e.merged or e.replaced:
        print(f"merged {e.merged} repeated joints, replaced {e.replaced} zero normals")
    print(f"checks: rest {c.rest_m:.1e} m, clips {c.clip_matrix:.1e} (positions {c.clip_pos_m:.1e} m, "
          f"rotations {c.clip_rot_deg:.1e} degrees), {c.textures} textures")
    if c.rest_offset_m > gltf.TOLERANCE:
        print(f"its rest pose sits up to {c.rest_offset_m:.1e} m off the file's positions "
              f"(a rest scale off 1), as the game draws it")
    return 0


NO_SPRING = "has no jiggle bone with a real-time spring"


def _jiggle(args) -> int:
    """``jiggle`` (Step 2.156, D443): the variant dressed as ``dress``
    dresses it, its spring rows (``--set`` laid over them, no second dress)
    driven by X41's twin over the physics scenarios and its slot clips at the
    game's rates (``jiggle_rt.simulate``), at ``--hz`` and the other rate for
    the rate target; each run's numbers and the targets printed (``--json``:
    one object)."""
    import dataclasses

    from azurkit.tools.characters import jiggle_rt
    from azurkit.tools.characters.ports import finite_slider_value

    try:
        strength = finite_slider_value("--strength", args.strength)
        stiffness = finite_slider_value("--stiffness", args.stiffness)
        variant = _variant(args)
        tried, docs = jiggle_rt.with_sets(variant, args.set)
        springs = dressing.dress(variant, image.find(args.iso), ram=args.ram, strength=strength,
                                 stiffness=stiffness).springs
        if not springs:
            raise ValueError(f"the variant {variant.name!r} {NO_SPRING}")
        if tried.jiggle is not None:   # a body's chains.json hair keeps the dress's rows
            springs["rows"] = jiggle_rt.rows(springs["placed"], jiggle_rt.spring_bones(tried.jiggle),
                                             springs["binds"], stiffness, springs["parents"])
        clips = None if args.clip == "none" else args.clip
        runs = jiggle_rt.simulate(springs, strength=strength, hz=args.hz, clips=clips)
        other = jiggle_rt.simulate(springs, strength=strength, hz=90 - args.hz, clips=None)
        judged = jiggle_rt.targets(*((runs, other) if args.hz == 30 else (other, runs)),
                                   kinds_=jiggle_rt.kinds(springs))
    except (OSError, ValueError) as exc:
        return _refused("jiggle", exc)
    if args.json:
        print(json.dumps({"variant": variant.name, "strength": strength, "stiffness": stiffness, "hz": args.hz,
                          "runs": [dataclasses.asdict(r) for r in runs], "targets": judged,
                          "springs": docs}, indent=1))
        return 0
    print(f"{variant.name}: {len(springs['rows'])} spring rows on {springs['body']} drawn x{springs['drawn']:.4g}, "
          f"strength {strength:g}, stiffness {stiffness:g}, {args.hz} Hz (Step 2.156's twin of X41)")
    for line in jiggle_rt.report(runs, judged):
        print(line)
    if args.set:
        print("springs (recipe JSON): " + json.dumps(docs))
    return 0


def _pose(args) -> int:
    """``pose`` (Step X.65f): the variant dressed as ``dress`` dresses it,
    each of ``--clips`` (else every slot's) played as ``jiggle`` plays it,
    X41's twin over the engine's pose (``jiggle_rt.pose``), every bone's
    world each tick written to ``--out`` (a new ``.npz``, written whole once
    every clip is posed, D35); a line a clip."""
    from azurkit.tools.characters import jiggle_rt
    from azurkit.tools.characters.ports import finite_slider_value

    try:
        strength = finite_slider_value("--strength", args.strength)
        stiffness = finite_slider_value("--stiffness", args.stiffness)
        variant = _variant(args)
        iso = image.find(args.iso)
        if (out := Path(args.out).absolute()).exists():
            raise ValueError(f"--out {out} exists already; give a new file")
        image.output(out, iso)
        clips = [c.strip() for c in args.clips.split(",") if c.strip()] if args.clips else None
        d = dressing.dress(variant, iso, ram=args.ram, strength=strength, stiffness=stiffness)
        if not d.springs:
            raise ValueError(f"the variant {variant.name!r} {NO_SPRING} (its poses are its export's: "
                             "model export --characters)")
        posed = jiggle_rt.pose(d.springs, clips, hz=args.hz, strength=strength)
        posed.save(out, hz=args.hz, strength=strength, stiffness=stiffness, drawn=d.springs["drawn"])
    except (OSError, ValueError) as exc:
        return _refused("pose", exc)
    print(f"{variant.name} ({d.body}): {len(d.springs['rows'])} spring rows moving {sum(posed.sprung)} of "
          f"{len(posed.bones)} bones, strength {strength:g}, stiffness {stiffness:g}, {args.hz} Hz -> {out}")
    for p in posed.clips:
        print(f"  {p.clip} x{p.rate:.3g}{' (loop)' if p.loop else ''}: {len(p.now)} ticks")
    return 0


def _rest(args) -> int:
    """``rest`` (Step MK.3a, D598: a shape slider's ends for ModelKit): the
    variant's ``mesh`` prepared once on its base's vanilla body
    (``mesh_edit.prepare``), then each ``--values`` item's ``mesh`` (a
    recipe's or a round spec's; nothing else of it is read) through the
    position steps (``mesh_edit.positions``) into ``--out``/<i>.npy, float32
    (vertices, 3) as a build writes them, written whole once every item is
    posed (D35); counts and seconds printed, never a coordinate."""
    import io
    import time

    import numpy as np

    from azurkit.tools.characters import gltf, mesh_edit
    from azurkit.tools.characters._player_variants import _mesh, resolve

    try:
        variant = resolve(args.variant, args.variant_file)
        if variant is None or variant.mesh is None:
            raise ValueError(f"{args.variant!r} is no variant with a mesh")
        iso = image.find(args.iso)
        characters, config = image.read(iso, "gamedata/characters.xbr", "gamedata/config.xbr")
        if not gltf.vanilla_characters(characters):
            raise ValueError(f"{iso}'s characters.xbr isn't vanilla: a rest pose is planned on vanilla (D27)")
        out = image.output(args.out, iso)
        items = json.loads(Path(args.values).read_text(encoding="utf-8"))
        if not isinstance(items, list) or not all(isinstance(x, dict) and "mesh" in x for x in items):
            raise ValueError(f"--values {args.values}: not a list of objects with a mesh")
        builtin = variant.source == "built-in"
        specs = [_mesh(f"--values[{i}]", x["mesh"], builtin) for i, x in enumerate(items)]
        body, _ = gltf.resolve_body(characters, config, variant.base)
        t0 = time.perf_counter()
        prepared = mesh_edit.prepare(characters, body, variant.mesh, None if builtin else Path(variant.source).parent)
        print(f"{variant.name}: {body} prepared in {time.perf_counter() - t0:.1f} s, {len(prepared.base)} vertices")
        got = {}
        for i, spec in enumerate(specs):
            t0 = time.perf_counter()
            np.save(buf := io.BytesIO(), np.asarray(mesh_edit.positions(prepared, spec), dtype=np.float32))
            got[f"{i}.npy"] = buf.getvalue()
            print(f"values[{i}]: its rest pose in {time.perf_counter() - t0:.1f} s")
        dressing.write(out, got, tuple(got))
    except (OSError, ValueError) as exc:
        return _refused("rest", exc)
    print(f"wrote {len(got)} rest poses into {out} (<i>.npy, float32)")
    return 0


def _preview(args) -> int:
    """``preview`` (Step 2.154): render the body (the image's characters.xbr
    or ``--characters``), its LOD ``--lod`` in LOD 0's frame, with headless
    Blender into ``--out`` (``devkit.models.preview``): print each view's
    PNG."""
    from azurkit.tools.characters import gltf
    from devkit.models import preview

    try:
        characters, config, iso = _characters(args)
        body, _ = gltf.resolve_body(characters, config, args.body)
        views = [v.strip() for v in args.views.split(",") if v.strip()] if args.views else preview.DEFAULT_VIEWS
        hide = [h.strip() for h in args.hide.split(",") if h.strip()] if args.hide else ()
        report = preview.preview(characters, body, Path(args.out), views=views, size=args.size, engine=args.engine,
                                 clip=args.clip, time=args.time, hide=hide, blender=args.blender,
                                 protect=(iso, *([Path(args.characters)] if args.characters else [])),
                                 vanilla=gltf.vanilla_characters(characters), lod=args.lod)
    except (OSError, ValueError) as exc:
        return _refused("preview", exc)
    at = f" at {report['time']:g} s" if args.clip else ""
    print(f"{body}{f' LOD {args.lod}' if args.lod else ''} ({report['pose']}{at}): "
          f"{len(report['views'])} views, {args.size} px, a {report['frame_m']:.2f} m frame")
    for view, path in report["views"].items():
        print(f"  {view}: {path}")
    return 0


DRESS = """\
Dresses VARIANT (a built-in, or one of --variant-file's) as a build wearing
it does, in memory on the verified vanilla image (D27), on the packs on by
default (a default build's size lines: a 128 MiB machine's, --ram 64 a 64
MiB one's, --ram 256 a 256 MiB one's with qol_memory_upper256 on too), with
--recipe's fields (a JSON object; null drops one) laid over its recipe and
read as its own (a built-in's clip, sound and texture files stay its), and
writes the dressed characters.xbr and index.xbr into --out only once the
dress passed. Prints the dress's log and the files' sizes and sha256; --json
one object with W24's plan as numbers (no coordinate). The files are game
assets: export and inspect read them with --characters."""

INSPECT = """\
Decodes BODY whole and prints its bones and markers, each LOD's groups
(vertices, triangles, palette, push buffer bytes, strip indices a triangle,
material), its extent and height, its payloads' sizes, its own load runs
against the game's load budget (a player build's, its baked clips in; the
budget is --memory-budget's, else a built image's default.xbe's, else the
42 MiB every build writes by default, D528), every other budget (the
format's: 31 palette bones and 65,536 vertices a group, an error past them;
vanilla's largest push buffer and bones, a warning past them) and every
problem the writer would refuse. Each LOD has its triangles, push and bmsh
bytes and the load runs only it reaches, and each wearer its switch
distances; a LOD the game never draws is a warning. Reads the image's
characters.xbr and fx.xbr (any image: a build's too) or --characters. Exit 1
on a problem or an error."""

EXPORT = """\
Writes BODY (a characters.xbr body, or a species, which names the body it
wears) into --out as <body>.gltf, <body>.bin and one PNG per texture: its
most detailed mesh, its skeleton and skin, and its clips (all, or --clips)
as animations, turned from z up to glTF's y up at the root. Reads the
image's characters.xbr (any image) or --characters (a built one: dress
--out's). The files are read back and checked against the game's model
before they are kept; a failed check writes nothing. The files are game
assets: never commit or share them."""

JIGGLE = """\
Dresses VARIANT as dress does (writing nothing) and drives the twin of X41's
springs with it: physics scenarios (idle; the walk slot at 3.5, 4.0 and 4.9
m/s; the run; a start; the 3-tick stop; a jump at vanilla's speed; a 3.5 m
drop; a 31 rad/s spin; a knockback; a 6.8 m place; a swim stroke) on the
body's own slot clips, then every slot's clip at the rate the game plays it,
standing (the ladder's climb loops in place and with their root's travel
carried). Per run and spring row it prints the peak offset per axis (side,
forward, up; mm as drawn), its radius, the largest move in a tick, the ticks
over 10 mm, the raw radius over the travel and the ring's extrema, then each
acceptance target pass or FAIL. --set ROLE.FIELD=VALUE tries a spring value
without editing the recipe and prints the springs as recipe JSON to paste.
It can't run the engine's glides or aligned moves: xemu judges those. A
variant with no spring row exits 1."""

POSE = """\
Dresses VARIANT as dress does (writing none of its files) and plays each of
--clips (names under its body; default every slot's clip) as jiggle plays
them, standing at the rate the game plays them (a loop for 3 s, a one-shot
once from rest and held 1 s; a climb loop with its root's travel taken off,
as the game draws it) at --hz, X41's springs over the engine's pose: a spring
row's bone as the shim writes it and every bone under it carried with it.
Writes --out (a new .npz outside the checkout and the images' folders):
bones, parents, inverse_binds, sprung (the bones the springs move), clips,
rates, loops, carried (the climb loops) and, per clip i, now<i>, time<i> and
worlds<i> ((ticks, bones, 4, 4): the model frame, z up, column vectors, each
bone's scale in, so a vertex skins as sum of weight x worlds[bone] @
inverse_binds[bone]; a glTF joint <bone> or <bone>__scale of export's takes
its bone's), then hz, strength, stiffness and drawn. A variant with no spring
row exits 1 and writes nothing."""

REST = """\
Prepares VARIANT's mesh once on its base's vanilla body (the subdivision,
hems, islands, tubes and cuts its build makes), then runs each --values
item's mesh (a JSON list of objects with a "mesh": a recipe's or a ModelKit
round spec's) through the build's position steps on that mesh: its fields,
rounds, relax, insets, beneath, press, snap, ride and tucks. Writes
--out/<i>.npy, float32 (vertices, 3) in model units as the build writes them
(VARIANT's own values give its plan's positions exactly), for ModelKit's
shape sliders. An item's ops must be VARIANT's in their order with the
numbers the preparation laid (subdivide, hem, island, tube, a cut's but its
press amounts); else it is refused by name and nothing is written."""


PREVIEW = """\
Exports BODY (with --clip, posed at --time; else its bind pose) and renders
it with Blender in the background (no window, factory settings), one
orthographic PNG a view framed on the posed mesh, the body's own textures on
it, into --out (a new or empty folder outside the checkout and the images'
folders): <body>_<view>.png and <body>_views.json. Blender is --blender,
$AZURIK_BLENDER, `blender` on PATH or /Applications/Blender.app's, and waits
for one of the machine's $AZURIK_BLENDER_SLOTS (8) Blender slots. --lod K
draws the body's LOD K instead, framed on LOD 0 posed the same way: LOD 0's
camera and light, <body>_lod<K>_<view>.png. Reads the image's characters.xbr
(any image) or --characters. The pictures are of a game asset: keep them out
of the repo."""


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m devkit models model", description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="leaf", required=True, metavar="LEAF")

    def leaf(name: str, run, line: str, text: str) -> argparse.ArgumentParser:
        v = sub.add_parser(name, help=line, description=text, formatter_class=argparse.RawDescriptionHelpFormatter)
        v.add_argument("--iso", default=None, metavar="PATH",
                       help="the image to read (default: the vanilla one AzurKit finds, USA's first)")
        v.set_defaults(run=run)
        return v

    def characters(v: argparse.ArgumentParser) -> None:
        v.add_argument("--characters", default=None, metavar="FILE",
                       help="a characters.xbr to read instead of the image's (dress --out's)")

    v = leaf("dress", _dress, "a variant dressed as a build does: its characters.xbr and index.xbr", DRESS)
    v.add_argument("variant", help="a variant: a built-in (booblord) or one of --variant-file's")
    v.add_argument("--variant-file", default=None, metavar="PATH", help="a JSON file of variant recipes")
    v.add_argument("--recipe", default=None, metavar="FILE",
                   help="a JSON object of recipe fields laid over the variant's (null drops one)")
    v.add_argument("--out", required=True, metavar="DIR", help="a new or empty folder outside the checkout")
    v.add_argument("--json", action="store_true", help="the report as JSON")
    v.add_argument("--ram", type=int, choices=RAMS, default=128, metavar="MIB",
                   help="the machine the body is built for: 128 (default, D588), 64 or 256 (with "
                        "qol_memory_upper256 on too)")
    v = leaf("inspect", _inspect, "a body's counts, budgets and problems", INSPECT)
    v.add_argument("body", help="a body (townspeople/female_2) or a species (town_female_2)")
    characters(v)
    v.add_argument("--json", action="store_true", help="the report as JSON")
    v.add_argument("--memory-budget", type=float, default=None, metavar="MIB",
                   help="the game's load budget the own runs' lines follow (default: a built image's "
                        "default.xbe's, else the 42 a build writes by default, D528)")
    v.add_argument("--ram", type=int, choices=RAMS, default=128, metavar="MIB",
                   help="the machine the lines are for: 128 (default, D588), 64 (a retail Xbox) or 256 (xemu at "
                        "mem_limit 256, with qol_memory_upper256); a built image without the packs keeps its lines")
    v = leaf("export", _export, "a body, its skeleton, skin, textures and clips as glTF 2.0", EXPORT)
    v.add_argument("body", help="a body (barnacle, townspeople/female_2) or a species (town_female_2)")
    v.add_argument("--out", required=True, metavar="DIR", help="a new or empty folder outside the checkout")
    v.add_argument("--clips", default=None, metavar="A,B", help="only these clips, by name (default: every clip)")
    characters(v)

    def springy(v: argparse.ArgumentParser, recipe: bool = True) -> None:
        v.add_argument("variant", help="a variant: a built-in (booblord) or one of --variant-file's")
        v.add_argument("--variant-file", default=None, metavar="PATH", help="a JSON file of variant recipes")
        if recipe:
            v.add_argument("--recipe", default=None, metavar="FILE",
                           help="a JSON object of recipe fields laid over the variant's (null drops one)")
        v.add_argument("--strength", type=float, default=1.0, metavar="X",
                       help="the jiggle strength slider (default 1.0; any finite number)")
        v.add_argument("--stiffness", type=float, default=1.0, metavar="X",
                       help="the jiggle stiffness slider (default 1.0; any finite number)")
        v.add_argument("--hz", type=int, choices=(30, 60), default=30,
                       help="the pose rate: 30 (vanilla) or 60 (fps_unlock)")
        v.add_argument("--ram", type=int, choices=RAMS, default=128, metavar="MIB",
                       help="the machine the body is built for: 128 (default, D588), 64 or 256, as dress's")

    v = leaf("jiggle", _jiggle, "a variant's real-time jiggle (X41's springs) over its body's clips", JIGGLE)
    springy(v, recipe=False)
    v.add_argument("--clip", default="all", metavar="NAME|all|none",
                   help="the slot clips to play: all (default), one clip's name under the body, or none")
    v.add_argument("--set", action="append", default=[], metavar="ROLE.FIELD=VALUE",
                   help="a spring value to try (JSON or a word), e.g. bust.gain=2.5; repeatable")
    v.add_argument("--json", action="store_true", help="the runs and targets as JSON")
    v = leaf("pose", _pose, "every bone's world each tick of a variant's clips with X41's springs, as an .npz", POSE)
    springy(v)
    v.add_argument("--out", required=True, metavar="FILE",
                   help="the .npz to write (new, outside the checkout and the images' folders)")
    v.add_argument("--clips", default=None, metavar="A,B",
                   help="the clips to play, by name under the body (default: every slot's clip)")
    v = leaf("rest", _rest, "a variant's rest pose for other values of its mesh ops, on its frozen mesh", REST)
    v.add_argument("variant", help="a variant with a mesh: a built-in (booblord) or one of --variant-file's")
    v.add_argument("--variant-file", default=None, metavar="PATH", help="a JSON file of variant recipes")
    v.add_argument("--values", required=True, metavar="FILE",
                   help='a JSON list of objects whose "mesh" holds the values to pose')
    v.add_argument("--out", required=True, metavar="DIR", help="a new or empty folder outside the checkout")
    v = leaf("preview", _preview, "a body's pictures from headless Blender, its textures on", PREVIEW)
    v.add_argument("body", help="a body (townspeople/female_2) or a species (town_female_2)")
    v.add_argument("--out", required=True, metavar="DIR", help="a new or empty folder outside the checkout")
    v.add_argument("--views", default=None, metavar="A,B",
                   help="views: front, back, left, right, front_left, front_right, back_left, back_right, top, "
                        "below (default front,left,back,front_left)")
    v.add_argument("--clip", default=None, help="a clip to pose (default: the bind pose)")
    v.add_argument("--time", type=float, default=0.0, help="seconds into --clip (default 0)")
    v.add_argument("--size", type=int, default=768, help="pixels a side (default 768)")
    v.add_argument("--engine", choices=("workbench", "eevee"), default="workbench",
                   help="workbench (textured, studio light; the default) or eevee (its materials, a sun)")
    v.add_argument("--lod", type=int, default=0, metavar="K",
                   help="draw LOD K (default 0) in LOD 0's frame: a vanilla one, or one a build wrote (the shadow LOD)")
    v.add_argument("--hide", default=None, metavar="ROW,..",
                   help="leave out the faces of these materials (rowN or gshdG_rowN: female_2's vase is row3)")
    characters(v)
    v.add_argument("--blender", default=None, metavar="PATH", help="the Blender executable")
    return p


def main(argv: list[str]) -> int:
    args = parser().parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
