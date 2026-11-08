"""devkit's model verbs, ``python -m devkit models model LEAF``
(``devkit/models/``, Step 4.15a1; Modkit's ``azurik-mod model``, its tests
ported leanly): ``dress`` dresses a variant with fields laid over its recipe
as a build dresses it (the swap's own ``tools.characters.dressed``, whose
move out of the plan G3's goldens pin) and writes what it dressed only once
the dress passed (D35), never inside the checkout (D36); ``inspect`` counts a
body and names each budget it passes; ``export`` writes a body as glTF from
the image or from a built ``characters.xbr``; ``jiggle`` and ``pose`` drive
a dressed variant's springs with X41's twin (Step 4.15a3), ``rest`` poses
its frozen mesh at other values. Each reads the USA image."""

from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import json
import os
import struct
from pathlib import Path

import pytest

from azurkit.core.xbr.append import NewResource, append_resources, rewrite_payloads
from azurkit.core.xbr.nodes import runs
from azurkit.tools.characters import body_codec, model_inspect
from azurkit.tools.characters._player_variants import BUILTIN, UNGRADED, _mesh, _variant, recipe_sha
from azurkit.tools.characters.characters import mesh_groups, mesh_points
from devkit.models import dress as dressing
from devkit.models import image, model

ROOT = Path(__file__).resolve().parent.parent
FEMALE_2 = "townspeople/female_2"


def _run(capsys, *argv: str) -> tuple[int, str, str]:
    """``python -m devkit models model ARGV``, in this process."""
    code = model.main(list(argv))
    out, err = capsys.readouterr()
    return code, out, err


def test_model_dress_writes_a_variants_build_with_fields_laid_over_its_recipe(usa_iso, tmp_path, capsys):
    """``model dress`` (Modkit's Step X.65f): the probe variant (G3's
    ``probes.json`` recipe file, booblord v3's mesh and more) with
    ``--recipe``'s fields laid over it (her mesh without its subdivide and
    tail, no jiggle, arms or textures) is dressed as a build dresses it:
    ``--out`` holds the characters.xbr and index.xbr the dress wrote, their
    sizes and sha256 in ``--json`` with W24's plan as the dress made it (her
    3,427 vertices, 14 ops, 7 tucked, the 768 it moves the only LOD-0
    vertices that differ from vanilla's); no spring row of hers, her base's
    hair's three (``chains.json``: a variant with no jiggle takes its
    body's); the laid-over recipe's sha. A field no recipe takes fails by
    name and writes nothing (D35), and an ``--out`` inside the checkout or
    an image's folder, named in any letter case the disk takes for it, is
    refused (D36)."""
    cases = json.loads((ROOT / "tests" / "goldens" / "cases.json").read_text(encoding="utf-8"))["probes.json"]
    recipes = next(case["variants"] for case in cases.values() if "variants" in case)
    (variant_file := tmp_path / "variants.json").write_text(json.dumps(recipes), encoding="utf-8")
    mesh = recipes["probe"]["mesh"]
    fields = {"mesh": {**mesh, "ops": [op for op in mesh["ops"] if op["op"] not in ("subdivide", "tube")]},
              "jiggle": None, "arms": None, "textures": None}

    def dress(out: Path, laid: dict) -> tuple[int, str, str]:
        (recipe := tmp_path / f"{out.name}.json").write_text(json.dumps(laid), encoding="utf-8")
        return _run(capsys, "dress", "probe", "--variant-file", str(variant_file), "--recipe", str(recipe),
                    "--out", str(out), "--json", "--iso", str(usa_iso))

    code, said, _ = dress(out := tmp_path / "dressed", fields)
    assert code == 0
    doc, files = json.loads(said), {n: (out / n).read_bytes() for n in ("characters.xbr", "index.xbr")}
    assert doc["files"] == {n: {"bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()} for n, b in files.items()}
    own = {k: v for k, v in (recipes["probe"] | fields).items() if v is not None}
    assert (doc["body"], doc["spring_rows"], doc["recipe_sha"]) == (FEMALE_2, 3, recipe_sha(own))
    plan = doc["plan"]
    assert (plan["body"], plan["vertices"], plan["ops"], plan["tucked"]) == (FEMALE_2, 3427, 14, 7)
    vanilla = mesh_points(image.read(usa_iso, "gamedata/characters.xbr")[0], FEMALE_2)
    assert sum(a != b for a, b in zip(vanilla, mesh_points(files["characters.xbr"], FEMALE_2))) == \
        plan["positions"] == 768
    code, _, err = dress(tmp_path / "refused", {"nonsense": 1})
    assert code == 1 and "nonsense" in err and not (tmp_path / "refused").exists()
    code, _, err = dress(image.CHECKOUT / "dressed", {})
    assert code == 1 and "inside the checkout" in err and not (image.CHECKOUT / "dressed").exists()
    (folder := tmp_path / "Images").mkdir()
    (held := folder / "usa.iso").touch()
    other = tmp_path / "images"   # the same folder where the disk ignores letter case (macOS), another where not
    same = other.exists() and os.path.samefile(other, folder)
    with pytest.raises(ValueError, match="an image's folder") if same else contextlib.nullcontext():
        image.output(other / "dressed", held)


def _accessor(doc: dict, blob: bytes, i: int) -> list[tuple]:
    """A glTF accessor's rows."""
    acc = doc["accessors"][i]
    width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[acc["type"]]
    code = {5126: "f", 5125: "I", 5123: "H", 5121: "B"}[acc["componentType"]]
    at = doc["bufferViews"][acc["bufferView"]].get("byteOffset", 0) + acc.get("byteOffset", 0)
    flat = struct.unpack_from(f"<{acc['count'] * width}{code}", blob, at)
    return [flat[k:k + width] for k in range(0, len(flat), width)]


def test_model_export_takes_a_built_characters_xbr(usa_iso, tmp_path, capsys):
    """``model export --characters FILE`` (Modkit's Step X.65f): a built
    characters.xbr (vanilla's with one of barnacle's vertices moved, as a
    build's W24 moves them; ``model dress --out``'s) exports as that file
    holds it, not as the image's, its root naming the file's sha256 and not
    vanilla, through the export's checks; ``--out`` may not be that file."""
    built = bytearray(image.read(usa_iso, "gamedata/characters.xbr")[0])
    g = next(g for g in mesh_groups(bytes(built), "barnacle") if g.lod == 0)
    x = struct.unpack_from("<f", built, g.vertices)[0] + 0.25
    struct.pack_into("<f", built, g.vertices, x)
    (path := tmp_path / "characters.xbr").write_bytes(bytes(built))

    def export(out: Path, *argv: str) -> dict:
        assert _run(capsys, "export", "barnacle", "--out", str(out), "--iso", str(usa_iso), *argv)[0] == 0
        gltf = next(out.glob("*.gltf"))
        doc, blob = json.loads(gltf.read_text(encoding="utf-8")), gltf.with_suffix(".bin").read_bytes()
        a = next(p for p in doc["meshes"][0]["primitives"] if _accessor(doc, blob, p["attributes"]["_AZ_VID"])[0][0]
                 == g.index)
        first = _accessor(doc, blob, a["attributes"]["POSITION"])[0]
        return next(n["extras"]["azurik"] for n in doc["nodes"] if "azurik" in n.get("extras", {})) | {"first": first}

    got, vanilla = export(tmp_path / "built", "--characters", str(path)), export(tmp_path / "vanilla")
    assert (got["characters_sha256"], got["vanilla"]) == (hashlib.sha256(built).hexdigest()[:12], False)
    assert vanilla["vanilla"] is True and got["first"][0] == pytest.approx(x, abs=1e-6) != vanilla["first"][0]
    code, _, err = _run(capsys, "export", "barnacle", "--characters", str(path), "--out", str(path))
    assert code == 1 and "the same file as" in err


def test_model_inspect_counts_a_body_and_names_what_passes_its_budgets(usa_iso, tmp_path, capsys, monkeypatch):
    """``model inspect`` (Modkit's Step 2.154, D443): vanilla female_2 is 93
    bones, 6 groups, 3,427 vertices and 5,151 triangles, over 1 tall, with
    every budget met and no problem, and a payload's size is no budget; her
    own load runs are 13 runs, 0.367 MiB (the load runs
    of characters.xbr's 2,655 and fx.xbr's 2,091, every entry in one, Step
    2.158); a zero ``banm`` under her name of the warning line's size makes
    a warning, of the error line's an error, and so does a ``bake`` (what a
    player build adds) of the error line's size (at 40 MiB on a 64 MiB
    machine); for a 128 MiB machine, the default (D588), a body past the 64
    MiB line is named as one that plays right only at 128 MiB, and one run
    past the single-run line is its own error row. The verb exits 1 on the
    error, its line naming a1's edges in play and what a build adds, and at
    the 42 MiB every build writes by default (D528) only warns; a skin group
    holding three times its triangles in one strip (written raw, past the
    writer's regroup) reports its push buffer past vanilla's largest (a
    warning) and names it among the problems."""
    data, fx = image.read(usa_iso, "gamedata/characters.xbr", "gamedata/fx.xbr")
    MiB, at40 = model_inspect.MiB, model_inspect.BUDGET
    with image.swap():   # the default budget: the packs' (ports.get_pack)
        report = model_inspect.inspect(data, FEMALE_2)
        assert (report["bones"], len(report["groups"]), report["lods"][0]["vertices"],
                report["lods"][0]["triangles"]) == (93, 6, 3427, 5151)
        assert not report["problems"] and not any(b["over"] for b in report["budgets"]) and report["extent"]["height"] > 1
        assert not any("payload" in b["what"] for b in report["budgets"])
        assert report["own_runs"] == {"bytes": 385024, "runs": 13, "largest": 208896, "by_tag": {
            "bmsh": 208896, "banm": 94208, "surf": 40960, "body": 32768, "gshd": 4096, "sprv": 4096}}
        assert [(len(r.runs), len(r.orphans)) for r in map(runs, (data, fx))] == [(2655, 0), (2091, 0)]
        for size, level in ((model_inspect.OWN_WARNING, "warning"), (model_inspect.OWN_ERROR, "error")):
            big = append_resources(data, [NewResource(f"characters/{FEMALE_2}/big", "banm", bytes(size))])
            assert {b["what"]: b["level"] for b in model_inspect.inspect(big, FEMALE_2, budget=at40, ram=64)["budgets"]
                    if b["over"]} == {"own load runs bytes": level}
        assert [b["level"] for b in model_inspect.inspect(data, FEMALE_2, bake=model_inspect.OWN_ERROR, budget=at40,
                                                          ram=64)["budgets"] if b["over"]] == ["error"]
        past64 = [model_inspect.lines(model_inspect.inspect(data, FEMALE_2, bake=15 * MiB, ram=ram)) for ram in (64, 128)]
        assert [any("plays right only on a 128 MiB one" in line for line in said) for said in past64] == [False, True]
        monkeypatch.setattr(model_inspect, "RUN_ERROR_128", model_inspect.OWN_WARNING)   # its 12 MiB banm run past it
        ran = model_inspect.inspect(big, FEMALE_2, ram=128)
        assert {b["what"]: b["level"] for b in ran["budgets"] if b["over"]} == {model_inspect.RUN: "error"}
        assert any(line.startswith("  error: largest own load run bytes 12.00 MiB, past the 10.00 MiB one run may take "
                                   "on a 128 MiB machine") for line in model_inspect.lines(ran))
    (tmp_path / "characters.xbr").write_bytes(big)
    given = ("inspect", "town_female_2", "--ram", "64", "--characters", str(tmp_path / "characters.xbr"),
             "--iso", str(usa_iso))
    code, out, _ = _run(capsys, *given, "--memory-budget", "40")
    assert code == 1
    assert ("error: own load runs bytes 12.37 MiB, past the 12 MiB a body may take of the game's 40 MiB beside a "
            "level loaded from a save and its menus (14 MiB with qol_memory_budget at 42)") in out
    assert "play keeps the inventory screen whole with 12.67 MiB of a build's and loses pieces of it with 15.79" in out
    assert "no player build's clips baked in: a build adds up to 3.8 MiB" in out
    code, out, _ = _run(capsys, *given)
    assert code == 0 and "warning: own load runs bytes 12.37 MiB, past 12 MiB, within 2 MiB of the 14 MiB line" in out
    asset = body_codec.read_asset(data, FEMALE_2)
    skin = asset.lods[0].groups[1]
    skin.triangles = skin.triangles + [(b, c, a) for a, b, c in skin.triangles] + [(c, a, b) for a, b, c in skin.triangles]
    payload, lods = body_codec.encode_body(asset)
    mesh, relocated = body_codec.encode_bmsh(asset.lods[0])
    raw = rewrite_payloads(data, {asset.index: payload, asset.lods[0].bmsh: mesh},
                           relocated={asset.index: lods, asset.lods[0].bmsh: relocated})
    with image.swap():
        report = model_inspect.inspect(raw, FEMALE_2)
    assert {b["what"]: b["level"] for b in report["budgets"] if b["over"]} == {"LOD 0 group 1 push buffer bytes": "warning"}
    assert any("group 1" in p and "push buffer" in p for p in report["problems"])


def _probe() -> dict:
    """G3's probe variant's recipe (``probes.json``'s recipe file): booblord
    v3's mesh with a finer bust and a tail, her arms and her jiggle."""
    cases = json.loads((ROOT / "tests" / "goldens" / "cases.json").read_text(encoding="utf-8"))["probes.json"]
    return next(case["variants"] for case in cases.values() if "variants" in case)["probe"]


def _v3(sash: bool = False) -> dict:
    """booblord v3, the recipe Modkit's model tests build on (her v4's 54
    mesh ops dress for minutes): her shipped recipe with the probe's mesh
    (less its finer bust and its tail), arms and jiggle, and none of her
    poses, textures, slots, victory_cancel, lods, weapon, idles or moves
    (their clips key v4's bones), nor her sounds' files (installed content's
    here); with ``sash`` her shipped ``jiggle.springs`` (her hair's and her
    sash's chains) but her ponytail's, which v3 lacks."""
    probe, recipe = _probe(), json.loads(BUILTIN.read_text(encoding="utf-8"))["booblord"]
    springs = recipe["jiggle"]["springs"]
    for key in ("poses", "textures", "slots", "victory_cancel", "lods", "weapon", "idles", *UNGRADED):
        recipe.pop(key, None)
    moves = {k for k, clip in recipe["clips"].items() if clip.get("file") in ("moves.glb", "idles.glb")}
    recipe["clips"] = {k: clip for k, clip in recipe["clips"].items() if k not in moves}
    recipe["columns"] = {c: clip for c, clip in recipe["columns"].items() if clip not in moves}
    recipe["carry"] = [c for c in recipe["carry"] if c in recipe["columns"]]
    ops = [op for op in probe["mesh"]["ops"] if op["op"] not in ("subdivide", "tube")]
    recipe |= {"mesh": {**probe["mesh"], "ops": ops}, "arms": probe["arms"], "jiggle": probe["jiggle"]}
    if sash:
        recipe["jiggle"] = {**probe["jiggle"], "springs": [r for r in springs if not r["bone"].startswith("ponytail")]}
    return recipe


def test_model_jiggle_previews_a_variants_springs_over_its_clips(usa_iso, tmp_path, monkeypatch, capsys):
    """``model jiggle`` (Modkit's Step 2.156, D443): booblord v3's preview
    (from a file, without her sounds) runs every physics scenario and every
    clip her slots play (her walk, the ladder's climb loops in place and
    carried) for every spring row (her hair chain's and her sash's too), and
    every acceptance target passes at her defaults (idle, the run's bust,
    the stop's ring, the landing, the walk slots', 30 against 60 Hz, a run
    from standing, her sash's walls and hems); ``--set bust.gain=0 --set
    bust.gravity=0`` leaves the bust still everywhere, rebuilding nothing
    else, and prints her springs as recipe JSON with that gain; beamlord,
    with no jiggle of its own, previews its body's 15 ``chains.json`` hair
    rows; a variant with no spring row (a keylord: its body lists no hair)
    exits 1 naming why."""
    from azurkit.tools.characters import jiggle_rt

    real, kept = dressing.dress, {}   # one dress a variant: --set lays its springs over the dress's
    monkeypatch.setattr(dressing, "dress", lambda variant, iso, **k: kept.get(variant.name) or kept.setdefault(
        variant.name, real(variant, iso, **k)))
    mine = tmp_path / "v3lord.json"
    mine.write_text(json.dumps({"v3lord": _v3(sash=True), "plain": {"base": "keylord"}}), encoding="utf-8")

    def preview(*argv: str) -> tuple[int, dict | str]:
        code, out, err = _run(capsys, "jiggle", *argv, "--variant-file", str(mine), "--json", "--iso", str(usa_iso))
        return code, json.loads(out) if code == 0 else err

    code, doc = preview("v3lord")
    names = [r["name"] for r in doc["runs"]]
    sash = {f"loincloth_{side}_{k}" for side in ("front", "back") for k in range(1, 5)}
    assert code == 0 and set(jiggle_rt.SCENARIOS) <= set(names) and all(
        set(r["peak"]) == {"bust", "glutes", "hair1", "hair2", "hair3"} | sash and set(r["chain"]) == sash
        for r in doc["runs"])
    assert {"clip walk x5.41 (loop)", "clip g4/climb_up x2 (loop)", "clip g4/climb_up x2 (loop, carried)"} <= set(names)
    assert len(names) > 60 and doc["targets"] == dict.fromkeys(("idle", "run", "stop", "landing", "walk", "rate",
                                                                "start", "chain"), True)
    _, still = preview("v3lord", "--clip", "none", "--set", "bust.gain=0", "--set", "bust.gravity=0")
    assert all(r["radius"]["bust"] == 0.0 and r["radius"]["glutes"] > 0.0 for r in still["runs"] if r["name"] != "idle")
    assert (still["springs"]["bust"]["gain"], still["springs"]["glutes"]["gain"]) == (0, 4.3)
    _, locks = preview("beamlord", "--clip", "none")   # no jiggle of its own: its body's chains.json rows
    assert all(set(r["peak"]) == {f"hair{i}" for i in range(1, 16)} for r in locks["runs"])
    code, err = preview("plain")
    assert code == 1 and model.NO_SPRING in err


def test_model_pose_writes_every_bones_world_with_x41s_springs_over_the_engines_pose(usa_iso, tmp_path, monkeypatch,
                                                                                      capsys):
    """``model pose`` (Modkit's Step X.65f): booblord v3's walk (a loop),
    g4/jump (a one-shot) and g4/climb_up (a climb loop, carried as the game
    draws it: its root's travel off every bone), played as ``model jiggle``
    plays them, every bone's world each tick in an .npz: a bone no spring
    row moves is the engine model's (the export's skinning) exactly, or
    carried; each row's centre not chained to another row moves off it by
    exactly the offset the twin shows, so its peak is ``jiggle``'s radius
    for that clip; at strength 0 every bone is the engine's within float32;
    a variant with no spring row exits 1 naming why and writes nothing."""
    import numpy as np

    from azurkit.tools.characters import gltf, jiggle_rt

    dressed = dressing.dress(_variant("booblord", _v3(), "built-in"), usa_iso)
    monkeypatch.setattr(dressing, "dress", lambda variant, iso, **k: dressed if variant.name == "booblord"
                        else dataclasses.replace(dressed, springs={}))   # one dress for the whole test
    springs, clips = dressed.springs, ["walk", "g4/jump", "g4/climb_up"]

    def posed(name: str, *argv: str):
        out = tmp_path / f"{name}{len(argv)}.npz"
        code, _, err = _run(capsys, "pose", name, "--clips", ",".join(clips), "--out", str(out), "--iso", str(usa_iso),
                            *argv)
        return np.load(out) if code == 0 else (code, err)

    got, still = posed("booblord"), posed("booblord", "--strength", "0")
    info, rows = gltf._read(springs["characters"], springs["body"]), springs["rows"]
    assert list(got["clips"]) == clips and list(got["bones"]) == [b.name for b in info.bones]
    assert [k for k, s in enumerate(got["sprung"]) if s] == [r.bone for r in rows]
    assert list(got["carried"]) == [False, False, True]
    root = list(got["parents"]).index(-1)
    for i, clip in enumerate(clips):
        run = [r for r in jiggle_rt.simulate(springs, clips=clip, scenarios=())
               if r.name.startswith(f"clip {clip} ")][-1]
        assert run.name.endswith("(loop, carried)") == got["carried"][i]
        worlds, source = got[f"worlds{i}"], dict(info.clips)[clip]
        engine = np.array([gltf._engine(info, source, float(t)) for t in got[f"time{i}"]])
        if got["carried"][i]:   # the engine root's travel off every bone
            engine[:, :, :3, 3] -= (engine[:, root, :3, 3] - gltf._engine(info, source, 0.0)[root][:3, 3])[:, None]
        free = np.abs(worlds[:, ~got["sprung"]] - engine[:, ~got["sprung"]]).max()
        assert free < 1e-6 if got["carried"][i] else free == 0.0
        assert np.abs(still[f"worlds{i}"] - engine).max() < 1e-6
        after = got[f"now{i}"] >= (1.0 if got["loops"][i] else 0.0)
        for r in (r for r in rows if r.chain < 0):
            centre = got["inverse_binds"][r.bone] @ [*r.centre, 1.0]
            moved = np.linalg.norm(((worlds[:, r.bone] - engine[:, r.bone]) @ centre)[:, :3], axis=1)
            assert moved[after].max() * springs["drawn"] * 1000.0 == pytest.approx(run.radius[r.role], abs=1e-3)
        assert max(run.radius.values()) > 3.0   # the springs swing
    code, err = posed("beamlord")
    assert code == 1 and model.NO_SPRING in err and not (tmp_path / "beamlord0.npz").exists()


def test_model_rest_poses_other_values_on_the_frozen_mesh_where_their_plans_put_them(usa_iso, tmp_path, capsys):
    """Modkit's Step MK.3a (D598, a shape slider's ends):
    ``mesh_edit.prepare`` keeps a spec's mesh (booblord v3's with the
    probe's subdivision over her bust, so the topology is new) and
    ``mesh_edit.positions`` runs the plan's own position steps on it: her
    values give her plan's final positions exactly, and her glutes' push 20 %
    higher (the split far from it, so her plan subdivides alike) that
    recipe's plan's; a changed number the preparation laid is refused by
    name. ``model rest`` writes each ``--values`` item's as float32
    <i>.npy, its plan's final positions, and an item with other ops writes
    nothing."""
    import numpy as np

    from azurkit.tools.characters import mesh_edit

    vanilla, probe = image.read(usa_iso, "gamedata/characters.xbr")[0], _probe()
    mesh = {**probe["mesh"], "ops": [op for op in probe["mesh"]["ops"] if op["op"] != "tube"]}
    higher = json.loads(json.dumps(mesh))
    next(op for op in higher["ops"] if op.get("name") == "glutes")["height"] *= 1.2
    base, up = (_mesh("m", m, True) for m in (mesh, higher))
    prepared = mesh_edit.prepare(vanilla, FEMALE_2, base)
    planned, raised = (mesh_edit.plan(vanilla, FEMALE_2, s) for s in (base, up))
    assert planned.added > 0 and mesh_edit.positions(prepared) == planned.final
    assert raised.added == planned.added and raised.final != planned.final
    assert mesh_edit.positions(prepared, up) == raised.final
    with pytest.raises(ValueError, match=r"mesh.ops\[0\] \(bust fine\): a number its preparation laid changed"):
        mesh_edit.positions(prepared, dataclasses.replace(up, ops=(dataclasses.replace(up.ops[0], edge=0.03),
                                                                   *up.ops[1:])))
    (mine := tmp_path / "v3lord.json").write_text(json.dumps({"v3lord": {"base": probe["base"], "mesh": mesh}}),
                                                  encoding="utf-8")

    def rest(out: Path, *items: dict) -> tuple[int, str]:
        (tmp_path / "values.json").write_text(json.dumps([{"mesh": m} for m in items]), encoding="utf-8")
        code, said, err = _run(capsys, "rest", "v3lord", "--variant-file", str(mine), "--values",
                               str(tmp_path / "values.json"), "--out", str(out), "--iso", str(usa_iso))
        return code, said + err

    code, said = rest(tmp_path / "out", mesh, higher)
    assert code == 0 and "values[1]: its rest pose in" in said
    for i, p in enumerate((planned, raised)):
        poses = np.load(tmp_path / "out" / f"{i}.npy")
        assert poses.dtype == np.float32 and np.array_equal(poses, np.array(p.final, np.float32))
    code, said = rest(tmp_path / "refused", {**mesh, "ops": mesh["ops"][1:]})
    assert code == 1 and "model rest: mesh.ops: not the prepared spec's ops" in said
    assert not (tmp_path / "refused").exists()
