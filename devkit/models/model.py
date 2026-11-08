"""``python -m devkit models model LEAF [ARGS ...]``: a character body's
verbs (Modkit's ``azurik-mod model``, ported leaf by leaf from Step 4.15a1),
the ones ModelKit's adapter calls.

- ``dress`` dresses a variant (a built-in, or one of ``--variant-file``'s,
  with ``--recipe``'s fields laid over it) as a build dresses it, in memory
  on the verified vanilla image (D27), and writes its ``characters.xbr`` and
  ``index.xbr`` once the dress passed (D35).
- ``inspect`` reports a body's counts, budgets and problems.
- ``export`` writes a body as glTF 2.0 for Blender.

A leaf reads ``--iso``'s image, else the one AzurKit finds
(``devkit.models.image``); ``inspect`` and ``export`` read any image, a
build's too, or ``--characters`` (a built ``characters.xbr``: ``dress
--out``'s). What a leaf writes (``--out``) is a game asset: a new or empty
folder outside this checkout and the images' folders (D36). It prints
counts, sizes and ``sha256``, never a byte. A refusal is one ``model LEAF:
...`` line on stderr and exit 1, as Modkit's; a usage error exits 2."""

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
    ``--recipe``'s fields laid over its recipe (``_player_variants.laid_over``);
    ``ValueError`` names a name that is no variant."""
    from azurkit.tools.characters._player_variants import laid_over, resolve

    variant = resolve(args.variant, args.variant_file)
    if variant is None:
        raise ValueError(f"{args.variant!r} is no variant")
    if args.recipe:
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
    return p


def main(argv: list[str]) -> int:
    args = parser().parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
