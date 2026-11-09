"""``python -m devkit models model LEAF [ARGS ...]``: a character body's
verbs (Modkit's ``azurik-mod model``, ported leaf by leaf from Step 4.15a1),
the ones ModelKit's adapter calls.

- ``dress`` dresses a variant (a built-in, or one of ``--variant-file``'s,
  with ``--recipe``'s fields laid over it) as a build dresses it, in memory
  on the verified vanilla image (D27), and writes its ``characters.xbr`` and
  ``index.xbr`` once the dress passed (D35).
- ``inspect`` reports a body's counts, budgets and problems.
- ``export`` writes a body as glTF 2.0 for Blender, or with ``--variant``
  a variant's textures as its build recolours them, a PNG a material row
  (Step 4.15a2).
- ``check`` runs a build's checks on an edited glTF of a body and prints
  the recipe row its ``mesh`` takes; ``import`` imports one with any
  topology (or its weights) through the writer; ``clips`` imports a glTF's
  animations as a body's clips; ``chains`` lists a body's hair and cloth
  chains and the spring rows a recipe needs (Step 4.15a2).
- ``jiggle`` previews a dressed variant's real-time springs (X41's twin,
  ``jiggle_rt``) over the physics scenarios and its clips (Step 4.15a3).
- ``pose`` writes every bone's world each tick of its clips with those
  springs, as an ``.npz``.
- ``rest`` writes a variant's rest positions for other values of its mesh
  ops on its frozen mesh (a shape slider's ends).
- ``preview`` renders a body's pictures with headless Blender.
- ``edit`` takes a body from its export through Blender, a pass a save
  (import, clips, inspect, preview), to a built image (Step 4.15a5).

A leaf reads ``--iso``'s image, else the one AzurKit finds
(``devkit.models.image``); ``inspect``, ``export`` and ``chains`` read any
image, a build's too, or ``--characters`` (a built ``characters.xbr``:
``dress --out``'s); ``check``, ``import`` and ``clips`` edit the image's
vanilla body (D27). What a leaf writes (``--out``) is a game asset: a new or
empty folder (``pose``, ``import``: a new file) outside this checkout and
the images' folders (D36). It prints counts, sizes and ``sha256``, never a byte or a
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
    checks' numbers. ``--variant`` (Step 2.203, D544): :func:`_export_variant`."""
    from azurkit.tools.characters import gltf

    if args.variant is not None or args.body is None:
        return _export_variant(args)
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


def _export_variant(args) -> int:
    """``export --variant`` (Step 2.203, D544): the variant's textures as
    its build recolours them, one PNG per material row
    (``colour_preview.rows``: the image's own body of its base, or for a
    recipe whose build changes the body, ``colour_preview.dresses``, the
    body ``dress`` dresses before its colours), written whole into ``--out``
    (a new or empty folder outside the checkout and the images' folders,
    D35, D36) once every row is made; each row's file, size and sha256 and
    the recipe row an edited one takes printed."""
    from azurkit.tools.characters import colour_preview, paint
    from azurkit.tools.characters._player_variants import colour_folder

    try:
        if args.body is not None or args.variant is None:
            raise ValueError("give BODY or --variant NAME (a variant's textures), not both" if args.body is not None
                             else "give BODY, or --variant NAME for a variant's textures")
        if args.clips or args.characters:
            raise ValueError("--variant writes the variant's textures as its build recolours them: no --clips or "
                             "--characters")
        variant = _variant(args)
        iso = image.find(args.iso)
        out = image.output(args.out, iso)
        colours = paint.located(variant.colours, colour_folder(variant)) if variant.colours else ()
        if colour_preview.dresses(variant):
            d = dressing.dress(colour_preview.uncoloured(variant), iso)
            characters, body = bytes(d.game["characters.xbr"]), d.body.removeprefix("characters/")
        else:
            characters, config = image.read(iso, "gamedata/characters.xbr", "gamedata/config.xbr")
            body = colour_preview.body_of(config, characters, variant.base)
        rows = colour_preview.rows(characters, body, colours)
        if not rows:
            raise ValueError(f"{body} draws no texture")
        pngs = colour_preview.pngs(variant.name, rows)
        files = dressing.write(out, pngs, tuple(pngs))
    except (OSError, ValueError) as exc:
        return _refused("export", exc)
    print(f"{variant.name} (a variant of {variant.base}, wearing {body}): {len(files)} rows' textures as its build "
          f"recolours them -> {out}")
    for (r, img), (name, (_, sha)) in zip(sorted(rows.items()), files.items()):
        print(f"  row {r}: {img.shape[1]}x{img.shape[0]} {name} (sha256 {sha})")
    print('an edited one, beside the recipe, is its row\'s first colours op: {"row": R, "ops": [{"op": "png", '
          '"file": "<the file>", "sha256": "<its sha256 after the edit>"}]} (the row\'s other ops after it)')
    return 0


def _vanilla(iso: Path, why: str, *names: str) -> list[bytes]:
    """The image's ``gamedata/characters.xbr`` and ``names``, once its
    characters.xbr is vanilla (an edit is made on vanilla, D27)."""
    from azurkit.tools.characters import gltf

    files = image.read(iso, "gamedata/characters.xbr", *names)
    if not gltf.vanilla_characters(files[0]):
        raise ValueError(f"{iso}'s characters.xbr isn't vanilla: {why} (D27)")
    return files


def _worn(config: bytes, body: str) -> str:
    """Who wears ``body``: the line ``check`` and ``import`` print."""
    from azurkit.tools.characters import lods

    worn = [w.species for w in lods.wearers(config, body)]
    return (f"worn by {', '.join(worn)} (a build of the recipe keeps the NPCs a level places vanilla's, P2)" if worn
            else "worn by no species")


def _check(args) -> int:
    """``check`` (Step 2.142): every check a build runs on ``args.file`` (an
    edited glTF of ``args.body``) against the image's vanilla body
    (``mesh_edit.plan``): what it would write, who wears the body and the
    recipe row with the file's sha256; writes nothing."""
    from azurkit.tools.characters import gltf, mesh_edit

    try:
        characters, config = _vanilla(image.find(args.iso), "an edit is checked against vanilla", "gamedata/config.xbr")
        body, _ = gltf.resolve_body(characters, config, args.body)
        path = Path(args.file).absolute()
        sha = mesh_edit.file_sha256(path)
        p = mesh_edit.plan(characters, body, mesh_edit.MeshSpec(gltf=(str(path), sha)))
    except (OSError, ValueError) as exc:
        return _refused("check", exc)
    e = p.gltf
    print(f"{p.body}: {e.vertices} glTF vertices for {p.vertices} ({e.merged} copies merged; ids from {e.carrier}"
          f"{', y up' if e.swapped else ''})"
          + (f"; ignored, no vertex id: {', '.join(e.ignored)}" if e.ignored else ""))
    print(f"{len(p.positions)} vertices moved (up to {p.largest:.3f} model units), normals recomputed on "
          f"{len(p.normals)}, {p.turned} triangles turned over")
    print(_worn(config, p.body))
    print(f'recipe row: "mesh": {{"gltf": {{"file": "{path.name}", "sha256": "{sha}"}}}}')
    return 0


def _import(args) -> int:
    """``import`` (Step 2.154): ``args.file`` (an edited glTF of
    ``args.body``) imported onto the image's vanilla body with any topology,
    or its weights only (``--weights``), through the writer
    (``gltf_import.read``, ``body_codec.write_asset``): what it kept,
    changed, added and removed, the groups written and the recipe row; with
    ``--out`` (a new file), the edited ``characters.xbr`` written whole."""
    import os

    from azurkit.tools.characters import body_codec, gltf, gltf_import

    mode = "weights" if args.weights else "topology"
    try:
        iso = image.find(args.iso)
        characters, config = _vanilla(iso, "an import is made onto vanilla", "gamedata/config.xbr")
        body, _ = gltf.resolve_body(characters, config, args.body)
        out = None
        if args.out:
            if (out := Path(args.out).absolute()).exists():
                raise ValueError(f"--out {out} exists already; give a new file")
            image.output(out, iso, file=True)
        path = Path(args.file).absolute()
        got = gltf_import.read(characters, body, path, mode)
        written = body_codec.write_asset(characters, got.asset)
        after = body_codec.read_asset(written, body).lods[0].groups
        if out is not None:
            out.parent.mkdir(parents=True, exist_ok=True)
            (part := out.with_name(f".{out.name}.part")).write_bytes(written)
            os.replace(part, out)
    except (OSError, ValueError) as exc:
        return _refused("import", exc)
    print(f"{body}: {got.vertices} glTF vertices imported ({mode}{', y up' if got.swapped else ''})"
          + (f"; ignored, not skinned to it: {', '.join(got.ignored)}" if got.ignored else ""))
    print(f"its vertices: {got.kept} kept, {got.changed} changed, {got.removed} removed, {got.added} added; "
          f"{got.triangles} triangles; {got.new_groups} groups added, {got.removed_groups} removed")
    if got.new_bones:
        print(f"new bones: {', '.join(got.new_bones)}")
    print(f"written: {len(after)} groups, {sum(len(g.vertices) for g in after)} vertices, "
          f"{sum(len(g.triangles) for g in after)} triangles, the largest palette "
          f"{max(len(g.palette) for g in after)}, "
          f"characters.xbr {len(characters)} -> {len(written)} B" + (" (unchanged)" if written == characters else ""))
    print(_worn(config, body))
    print(f'recipe row: "mesh": {{"gltf": {{"file": "{path.name}", "sha256": "{got.sha256}", "import": "{mode}"}}}}')
    if out is not None:
        print(f"wrote {out}")
    return 0


def _clips(args) -> int:
    """``clips`` (Step 2.154): the animations of ``args.file`` (all, or
    ``--clips``) as clips of ``args.body`` from the image's vanilla
    ``characters.xbr`` (``clip_import.read_clips``): each clip's tracks kept
    and made, whether it replaces one, its keys before and after thinning,
    its size and its root's travel, and a ``gltf`` clip's recipe row each;
    with ``--out`` (a new or empty folder), the edited ``characters.xbr``
    and ``index.xbr`` written whole (``clip_import.write_clips``)."""
    from azurkit.tools.characters import clip_import, gltf, mesh_edit
    from azurkit.tools.characters.retarget import write_clip

    try:
        iso = image.find(args.iso)
        characters, config, index = _vanilla(iso, "clips are imported onto vanilla", "gamedata/config.xbr",
                                             "gamedata/index/index.xbr")
        body, _ = gltf.resolve_body(characters, config, args.body)
        out = image.output(args.out, iso) if args.out else None
        path = Path(args.file).absolute()
        names = [c.strip() for c in args.clips.split(",") if c.strip()] if args.clips else None
        got = clip_import.read_clips(characters, body, path, names)
        written, indexed = clip_import.write_clips(characters, index, body, got)
        sha = mesh_edit.file_sha256(path)
        if out is not None:
            dressing.write(out, {"characters.xbr": written, "index.xbr": indexed})
    except (OSError, ValueError) as exc:
        return _refused("clips", exc)
    for c in got:
        print(f"{body}/{c.name}: {'replaces its clip' if c.replaces else 'a new clip'}, {c.clip.length:.3f} s, "
              f"{c.kept} bone tracks kept, {c.made} made from {c.channels} channels ({', '.join(c.interpolations)}"
              + (f"; LINEAR rotations within {c.slerp_deg:.2g} degrees of slerp" if "LINEAR" in c.interpolations
                 else "") + f"), {len(c.clip.markers)} marker tracks; keys {c.keys_before} -> {c.keys_after}, "
              f"clip {len(write_clip(c.clip))} B; its root moves {c.root_travel:.3f} model units along the floor")
        if not c.clip.markers:
            print(f"  {c.name} has no marker track: an attack column needs box and active")
    print(f"characters.xbr {len(characters)} -> {len(written)} B" + (" (unchanged)" if written == characters else "")
          + (f", index.xbr +{len(indexed) - len(index)} B" if indexed != index else ""))
    rows = ", ".join(f'"{c.name}": {{"generator": "gltf", "file": "{path.name}", "sha256": "{sha}", '
                     f'"animation": "{c.name}"}}' for c in got)
    print(f'recipe row: "clips": {{{rows}}}')
    if out is not None:
        print(f"wrote {out / 'characters.xbr'} and {out / 'index.xbr'}")
    return 0


def _chains(args) -> int:
    """``chains`` (Step 2.169a, D536): ``model_chains.chains``' report on
    ``args.body`` (a body or a species) in the image's characters.xbr or
    ``--characters``: its hair and cloth chains, each link's length and
    mass, the clips keying each chain and the ``jiggle.springs`` rows a
    recipe would need (``--json``: one object, the species too)."""
    from azurkit.tools.characters import gltf, model_chains

    try:
        characters, config, _ = _characters(args)
        body, species = gltf.resolve_body(characters, config, args.body)
        report = model_chains.chains(characters, body)
    except (OSError, ValueError) as exc:
        return _refused("chains", exc)
    if args.json:
        print(json.dumps(report | {"species": species}, indent=1))
        return 0
    if species:
        print(f"{species} wears {body}")
    print("\n".join(model_chains.lines(report)))
    return 0


NO_SPRING ="has no jiggle bone with a real-time spring"


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


def _edit(args) -> int:
    """``edit`` (Step 2.158, D465): ``devkit.models.edit``'s session on
    ``args.body`` in ``--work``, a pass a save, then ``--build``; exit 1
    naming the refusal (a refused pass is logged and the session goes on)."""
    import subprocess

    from devkit.models import edit

    try:
        edit.check_mode(args.headless, Path(args.script) if args.script else None)
        clips = tuple(c.strip() for c in args.clips.split(",") if c.strip()) if args.clips else ()
        session = edit.prepare(args.body, Path(args.work), iso=Path(args.iso) if args.iso else None,
                               name=args.variant, variant_file=Path(args.variant_file) if args.variant_file else None,
                               builtin=args.from_builtin, base=args.base, weights=args.weights, clips=clips)
        session.ram = args.ram
        if args.build:
            edit.check_build_out(Path(args.build), session.iso)
        print(f"{session.body} as variant {session.name!r} (base {session.species}) in {session.work}")
        edit.run(session, headless=args.headless, script=Path(args.script) if args.script else None,
                 blender=args.blender, preview=not args.no_preview)
        if session.last_ok is None:
            print("no save was read: nothing to build")
        if args.build:
            edit.build(session, Path(args.build))
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return _refused("edit", exc)
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
assets: never commit or share them.

--variant NAME writes a variant's textures instead, one PNG per material
row, <NAME>_row<R>.png, as its build recolours them (its colours), at the
texture's own size; an edited one is the row's colours png op
(docs/VARIANTS.md)."""

CHECK = """\
Runs every check a build runs on FILE (a .glb or .gltf that export wrote and
Blender or another tool moved vertices of) against BODY's vanilla mesh: the
vertex ids, the skeleton and the mesh frame, the triangles, UVs and skin
unchanged, no seam torn. Prints how many vertices it moves, who wears the
body, and the recipe row with the file's sha256 for a variant's "mesh".
Writes nothing."""

IMPORT = """\
Imports FILE (a .glb or .gltf that export wrote and Blender edited: new,
moved or deleted vertices and triangles, new bones, painted weights) onto
BODY's vanilla mesh, matched by its bones', materials' and vertices' names
and ids, and writes it through the model toolkit's writer (new strips, a
group past 31 bones split, the file grown in place). --weights takes only
the skin weights (the same topology). Prints what it kept, changed, added
and removed and the recipe row ("import": "topology" or "weights") for a
variant's "mesh"; --out writes the edited characters.xbr (a game asset) for
inspect and preview."""

CLIPS = """\
Reads FILE's animations (all, or --clips) as clips of BODY: each channel on
a bone's node (a <bone>__scale helper's scale its bone's) becomes the clip's
tracks (CUBICSPLINE keys as they are, LINEAR ones as straight runs, STEP
ones held); an animation export wrote comes back byte for byte, a changed
one keeps its clip's marker tracks, and every clip's pose is checked against
the file's. A clip of that name is replaced, any other added under the body.
--out (a new or empty folder outside the checkout) gets the edited
characters.xbr and index.xbr (game assets), written once every clip is
read."""

CHAINS = """\
Lists BODY's bone chains a variant's jiggle.springs rows could swing on X41
(D536): its hair and its cloth (loincloth panels, booblord's sash and
tabard, straps), found by their bones' names. Per chain: its links (each
one's length, to its child or its vertices' reach, and mass: the LOD-0
vertices it weighs at 0.25 or more and its weights' sum), its tip, and the
clips keying its first link (one that doesn't shows the link unhung under a
spring); then the rows a recipe would need, one a link that weighs a vertex,
with a starting spring of its kind to tune with jiggle --set (a cloth link
walled 5 mm off its clip's pose), against the 32 X41 holds. Reads the
image's characters.xbr (any image) or --characters."""

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

EDIT = """\
Exports BODY into --work (a new folder outside the checkout and the images'
folders, or one an earlier model edit made), opens it in Blender and reads
each save back: import (topology, or --weights) with the recipe's ops after
it, the saved animations as clips, inspect's budgets on the body as its
build leaves its LODs and preview's pictures, a log.jsonl row and
--work/recipe.json (the variant's recipe: --variant-file seeds it and is
never written). A refused save is logged and the session goes on. --build
OUT.iso builds the last passing recipe when Blender closes, on the packs on
by default for --ram's machine. --headless runs Blender in the background
with --script (agents and tests must: the interactive mode refuses to start
under $CLAUDECODE or $PYTEST_CURRENT_TEST). Everything it writes is a game
asset."""


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
    v.add_argument("body", nargs="?", default=None,
                   help="a body (barnacle, townspeople/female_2) or a species (town_female_2); none with --variant")
    v.add_argument("--variant", default=None, metavar="NAME",
                   help="a variant's textures as a PNG per material row: a built-in (booblord) or one of "
                        "--variant-file's")
    v.add_argument("--variant-file", default=None, metavar="PATH", help="a JSON file of variant recipes")
    v.add_argument("--out", required=True, metavar="DIR", help="a new or empty folder outside the checkout")
    v.add_argument("--clips", default=None, metavar="A,B", help="only these clips, by name (default: every clip)")
    characters(v)
    v = leaf("check", _check, "an edited glTF a variant's mesh can take, checked; writes nothing", CHECK)
    v.add_argument("body", help="a body (townspeople/female_2) or a species (town_female_2)")
    v.add_argument("file", help="the edited .glb or .gltf")
    v = leaf("import", _import, "an edited glTF with any topology (or its weights) imported and written", IMPORT)
    v.add_argument("body", help="a body (townspeople/female_2) or a species (town_female_2)")
    v.add_argument("file", help="the edited .glb or .gltf")
    v.add_argument("--weights", action="store_true", help="take only the skin weights (and new bones); the same "
                                                          "topology")
    v.add_argument("--out", default=None, metavar="FILE",
                   help="write the edited characters.xbr here (new, outside the checkout and the images' folders)")
    v = leaf("clips", _clips, "a glTF's animations imported as a body's clips", CLIPS)
    v.add_argument("body", help="a body (townspeople/female_2) or a species (town_female_2)")
    v.add_argument("file", help="a .glb or .gltf with animations")
    v.add_argument("--clips", default=None, metavar="A,B", help="only these animations, by name (default: every one)")
    v.add_argument("--out", default=None, metavar="DIR",
                   help="write characters.xbr and index.xbr into this new or empty folder")
    v = leaf("chains", _chains, "a body's hair and cloth chains X41's springs could drive, and the rows a recipe "
                                "needs", CHAINS)
    v.add_argument("body", help="a body (townspeople/female_2) or a species (town_female_2)")
    characters(v)
    v.add_argument("--json", action="store_true", help="the report as JSON")

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
    v = leaf("edit", _edit, "export, edit in Blender, import, inspect, preview and build in one verb", EDIT)
    v.add_argument("body", help="a species (town_female_2) or a body with --base")
    v.add_argument("--work", required=True, metavar="DIR", help="the work folder (new, or a model edit's)")
    v.add_argument("--variant", default=None, metavar="NAME",
                   help="the variant's name (default: the --variant-file's one recipe, else <species>_edit)")
    seed = v.add_mutually_exclusive_group()
    seed.add_argument("--variant-file", default=None, metavar="FILE",
                      help="a recipe file to start from (read, never written)")
    seed.add_argument("--from", dest="from_builtin", default=None, metavar="BUILTIN",
                      help="start from a built-in variant's recipe (its WAVs and clip files copied into --work)")
    v.add_argument("--base", default=None, metavar="SPECIES", help="the species that wears BODY")
    v.add_argument("--weights", action="store_true", help="read only the skin weights (the same topology)")
    v.add_argument("--clips", default=None, metavar="A,B", help="clips to export for editing (default none)")
    v.add_argument("--headless", action="store_true", help="Blender in the background, no window")
    v.add_argument("--script", default=None, metavar="PY", help="a bpy script the headless session runs")
    v.add_argument("--blender", default=None, metavar="PATH", help="the Blender executable")
    v.add_argument("--no-preview", action="store_true", help="no pictures per save")
    v.add_argument("--build", default=None, metavar="OUT.iso", help="build an image when Blender closes")
    v.add_argument("--ram", type=int, choices=RAMS, default=128, metavar="MIB",
                   help="the machine the body is for: 128 (default, D588), 64 (a retail Xbox) or 256 (with "
                        "qol_memory_upper256 on too), each pass weighed against its lines and --build made for it")
    return p


def main(argv: list[str]) -> int:
    args = parser().parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
