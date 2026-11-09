"""``python -m devkit models weapon-fit``: W35's arm fit (Modkit's
``scripts/weapon_fit.py``): for a body (or a built-in variant) wearing
Garret's staff moves, the turn of both ``*_arm_1`` in each of his attack
clips that keeps the prop out of its chest, as the shipped ``weapons.json``'s
``fits`` row (``tools.characters._player_weapons.fits``).

Per target it dresses the body in Balanced with the Axion staff and with
the farmer's hoe (no fit of its own), and for each of garret4's attack
clips baked onto it and each turn of :data:`OUT` x :data:`FORWARD`
(degrees: out from its sides, then forward) counts the ticks with a prop
vertex more than 1 cm inside its torso (``_player_weapons.Chest``).
:func:`choose` gives each clip the turn with the fewest ticks beyond
garret4's own holding the same prop in that clip (his staff reaches into
his chest in attack_3; the hoe on his staff chain), the worse prop's, whose
props go no lower than min(his lowest, 0) - 1 cm with each (his staff dips
2-11 cm under the floor in his elemental and smash moves, the longer hoe
more); ties go to the smaller turn. A clip no turn improves keeps none. It
prints one line per clip and the row (names and numbers only); ``--write``
puts each row in ``weapons.json`` (a body with no clip to turn loses its
row), a shipped file every build reads, so the weapon goldens are
re-recorded after it.

    uv run --locked python -m devkit models weapon-fit booblord townspeople/male_6 [--write] [-j N] [--iso PATH]
    uv run --locked python -m devkit models weapon-fit --all [--write]
"""

from __future__ import annotations

import argparse
import contextlib
import functools
import io
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from devkit.models import image

OUT = (0, 10, 20, 30)
"""The grid's outward turns (degrees about the body's forward axis)."""
FORWARD = (0, 15)
"""The grid's forward turns (degrees about its side axis)."""
PROPS = ("axion_staff", "farmers_hoe")
FLOOR_MARGIN = 0.01
"""How far (model units) under min(garret4's own lowest, 0) a fitted clip's prop may go."""


def _targets(names: list[str], every: bool) -> list[str]:
    from azurkit.tools.characters._player_variants import builtins
    from azurkit.tools.characters.retarget import MAPS

    if every:
        return sorted(MAPS) + [n for n, v in builtins().items() if v.mesh is not None or v.arms]
    return names


def _species(config: bytes) -> dict[str, str]:
    from azurkit.tools.characters._player_character import _species as rows
    from azurkit.tools.characters.ports import XbrDocument

    return {s: r["body"] for s, r in rows(XbrDocument.from_bytes(config).keyed_section("critters_engine")).items()
            if r["body"]}


def garret4_reference(characters: bytes, weapon: str, clips: list[str]) -> dict[str, tuple[int, float]]:
    """garret4 holding ``weapon``'s prop in each of ``clips`` (his own clips: his staff, or the hoe on his
    staff chain, his staff cut, as his build holds it: on its carriers, W31, which the copy rides since W41's
    step; Modkit's script copied it without them and stopped at "garret4 has no bone 'wpn_tip'"): its deep
    ticks and lowest z."""
    from azurkit.tools.characters._player_weapons import (Chest, add_carriers, copy_prop, cut_staff, loadout,
                                                          weapons)
    from azurkit.tools.characters.characters import read_body
    from azurkit.tools.characters.retarget import named_clip

    w = weapons()[weapon]
    if w.prop.own_on == "garret4":
        chest = Chest(characters, "garret4", w.prop.mesh.bones + ("staff_constraint",))
    else:
        body = read_body(characters, "garret4")
        lo = loadout(characters, body, "own", False, None, weapon)
        held, _ = copy_prop(cut_staff(add_carriers(characters, body, lo), lo)[0], body, lo)
        chest = Chest(held, "garret4", lo.prop.carriers)
    return {c: chest.ticks(named_clip(characters, "garret4", c)) for c in clips}


def fit(target: str, iso: str | None = None) -> dict:
    """``target``'s fit (module docstring) on ``iso``'s image (else the one
    AzurKit finds): {"body", "sha", "clips": {clip: [out, fwd]}, "lines"},
    with "error" where it can't be dressed (its row left as it is)."""
    try:
        return _fit(target, iso)
    except (StopIteration, ValueError) as exc:
        return {"body": target, "sha": None, "clips": {}, "error": True,
                "lines": [f"  {target}: not fitted: {exc or 'no species wears it'}"]}


def _fit(target: str, given: str | None) -> dict:
    from unittest import mock

    from azurkit.tools.characters import _player_character as pc
    from azurkit.tools.characters import _player_weapons as pw
    from azurkit.tools.characters import ports
    from azurkit.tools.characters._player_variants import arm_turns, builtins
    from azurkit.tools.characters.retarget import Rig, named_clip, turned

    iso = image.find(given)
    vanilla = ports.Vanilla(image.stamp(iso).release, iso)   # every file it reads checked (D27)
    game = ports.IsoStaging(vanilla)
    variant = builtins().get(target)
    bodies = _species(game.stored("config.xbr"))
    species = variant.base if variant is not None else next(s for s, b in sorted(bodies.items())
                                                            if b.casefold() == target.casefold())
    measured: dict[str, dict[str, dict[tuple[int, int], tuple[int, float]]]] = {}
    with (ports.building(ports.Build(vanilla)), mock.patch.dict(pw.fits(), clear=True),
          contextlib.redirect_stdout(io.StringIO())):
        for weapon in PROPS:
            d = pc._dress(ports.IsoStaging(vanilla), species, "own", None, variant=variant, weapon=weapon)
            if d.loadout.carry != pw.COPY:   # its own prop, carried in place (W26: the farmers' hoe), no fit
                continue
            built, _ = pw.copy_prop(d.characters, d.body, d.loadout)
            rig = Rig.read(built, d.body.name)
            chest = pw.Chest(built, d.body.name, d.loadout.prop.carriers)
            for pick in sorted({p for p in d.picks if p.startswith(pc.BAKED_DIR)} - {pc.BAKED_DIR + pc.G4_ROLL}):
                clip = named_clip(built, d.body.name, pick)
                for out in OUT:
                    for fwd in FORWARD:
                        measured.setdefault(weapon, {}).setdefault(pick[len(pc.BAKED_DIR):], {})[out, fwd] = chest.ticks(
                            turned(rig, clip, arm_turns(rig, out, fwd)) if out or fwd else clip)
    his = {w: garret4_reference(game.stored("characters.xbr"), w, sorted(measured[w])) for w in measured}
    clips, lines = choose(target, measured, his)
    return {"body": target if variant is None else variant.name,
            "sha": variant.sha if variant is not None else None, "clips": clips, "lines": lines}


def choose(target: str, measured: dict, his: dict) -> tuple[dict[str, list[int]], list[str]]:
    """Each clip's turn from ``measured`` ({prop: {clip: {(out, fwd): (ticks, lowest z)}}}, the props
    :data:`PROPS` it wore) against garret4's own ``his`` ({prop: {clip: (ticks, lowest z)}}): the turn with the
    fewest ticks beyond his, the worse prop's, among those whose every prop stays at or above min(his lowest, 0)
    - :data:`FLOOR_MARGIN` (every turn when none does), ties to the smaller turn; {clip: [out, fwd]} for each
    clip whose turn isn't (0, 0), and a line a clip and the total's."""
    worn = [w for w in PROPS if w in measured]
    clips, lines, before, after = {}, [], 0, 0
    for name in sorted(measured[worn[0]]):
        excess, floors = {}, {w: min(his[w][name][1], 0.0) - FLOOR_MARGIN for w in worn}
        for s in measured[worn[0]][name]:   # the worse prop's ticks past his own, and whether both clear the floor
            excess[s] = (max(max(0, measured[w][name][s][0] - his[w][name][0]) for w in worn),
                         all(measured[w][name][s][1] >= floors[w] for w in worn))
        allowed = [s for s, (_, ok) in excess.items() if ok] or list(excess)
        best = min(allowed, key=lambda s: (excess[s][0], s[0] + s[1], s))
        if best != (0, 0):
            clips[name] = [best[0], best[1]]
        before, after = before + excess[0, 0][0], after + excess[best][0]
        lines.append(f"  {target} {name}: excess {excess[0, 0][0]} unturned"
                     + ("" if excess[0, 0][1] else " (under the floor)") + f", {excess[best][0]} at out {best[0]} "
                     f"fwd {best[1]}" + ("" if excess[best][1] else " (under the floor)") + "; garret4's own "
                     + ", ".join(f"{w} {his[w][name][0]} (floor {floors[w]:.3f})" for w in worn))
    lines.append(f"  {target}: excess ticks {before} unturned, {after} fitted; {len(clips)} clips turned")
    return clips, lines


def write(rows: list[dict], path: Path) -> None:
    """Each row into ``path``'s ``fits`` (sorted, one line each), a row with no clip dropped, an errored one left
    as it is; nothing is written unless the result loads as a ``weapons.json`` (D35)."""
    from azurkit.tools.characters._player_weapons import load_weapons

    doc = json.loads(path.read_text(encoding="utf-8"))
    fits = dict(doc.get("fits", {}))
    for row in rows:
        if row.get("error"):
            continue
        fits.pop(row["body"], None)
        if row["clips"]:
            fits[row["body"]] = {**({"sha": row["sha"]} if row["sha"] else {}), "clips": row["clips"]}
    text = path.read_text(encoding="utf-8")
    head = text[:text.index(',\n "fits"')] if '"fits"' in text else text.rstrip()[:-1].rstrip()
    body = ",\n".join(f"  {json.dumps(k)}: {json.dumps(v, separators=(', ', ': '))}" for k, v in sorted(fits.items()))
    new = head + (',\n "fits": {\n' + body + "\n }\n}\n" if fits else "\n}\n")
    load_weapons(new)   # it reads back, or nothing is written
    path.write_text(new, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    from azurkit.tools.characters._player_weapons import WEAPONS_FILE

    ap = argparse.ArgumentParser(prog="python -m devkit models weapon-fit", description=__doc__.split("\n\n")[0])
    ap.add_argument("targets", nargs="*", help="a mapped body (townspeople/male_6) or a built-in variant (booblord)")
    ap.add_argument("--all", action="store_true", help="every body the bake maps and every built-in variant with "
                                                       "a mesh or arms of its own")
    ap.add_argument("--write", action="store_true", help="write the rows into weapons.json's fits")
    ap.add_argument("-j", type=int, default=1, help="targets fitted at once (processes)")
    ap.add_argument("--iso", help="the vanilla image (default: the one AzurKit finds)")
    args = ap.parse_args(argv)
    targets = _targets(args.targets, args.all)
    if not targets:
        ap.error("name a target, or --all")
    one = functools.partial(fit, iso=args.iso)
    if args.j > 1:
        with ProcessPoolExecutor(args.j) as pool:
            rows = list(pool.map(one, targets))
    else:
        rows = [one(t) for t in targets]
    for row in rows:
        print("\n".join(row["lines"]))
        if not row.get("error"):
            print(f"  row {row['body']}: " + json.dumps({k: v for k, v in row.items() if k in ("sha", "clips")}))
    if args.write:
        write(rows, WEAPONS_FILE)
        print(f"  wrote {sum(bool(r['clips']) for r in rows)} rows into {WEAPONS_FILE.name}")
    return 0
