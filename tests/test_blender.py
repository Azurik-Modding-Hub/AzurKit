"""devkit's headless Blender (``devkit/models/blender/``, Step 4.15a4;
Modkit's ``model preview``, Blender batch and ``model edit``, their tests
ported): ``model preview`` exports a body and renders a picture a view (a
LOD in LOD 0's frame), the batch draws many frames of one body from one
Blender, the body cached by its content and at most
``$AZURIK_BLENDER_SLOTS`` Blenders on the machine, and ``model edit``
(Step 4.15a5) reads each Blender save back in a pass. Blender isn't part
of the test environment: a stand-in, run by this Python, writes what Blender
would."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest

from devkit.models import image, model, preview
from devkit.models.blender import batch as bb


def _stand_in(tmp_path: Path, source: str) -> Path:
    """A stand-in Blender: ``source`` run by this Python (an executable
    script; on Windows a ``.cmd`` running it)."""
    if os.name == "nt":
        (script := tmp_path / "blender.py").write_text(source, encoding="utf-8")
        (stub := tmp_path / "blender.cmd").write_text(f'@"{sys.executable}" "{script}" %*\n', encoding="utf-8")
        return stub
    (stub := tmp_path / "blender").write_text(f"#!{sys.executable}\n{source}", encoding="utf-8")
    stub.chmod(0o755)
    return stub


def _no_blender(monkeypatch, tmp_path: Path) -> None:
    """No Blender found but one given: no ``$AZURIK_BLENDER``, none on PATH, no app."""
    monkeypatch.delenv("AZURIK_BLENDER", raising=False)
    monkeypatch.setattr(preview, "APP", tmp_path / "no-app")
    monkeypatch.setattr(preview.shutil, "which", lambda _: None)


_STUB = '''
import json, os, sys, zlib, struct
argv = sys.argv[1:]
job = json.load(open(argv[-1], encoding="utf-8"))
doc = json.load(open(job["gltf"], encoding="utf-8"))
png = b"\\x89PNG\\r\\n\\x1a\\n" + b"".join(struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
                                      for t, d in ((b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)),
                                                   (b"IDAT", zlib.compress(b"\\0\\0\\0\\0\\0")), (b"IEND", b"")))
views = {}
for v in job["views"]:
    views[v] = os.path.join(job["out"], job["prefix"] + v + ".png")
    open(views[v], "wb").write(png)
json.dump({"views": views, "frame_m": 2.0, "height_m": 1.7, "width_m": 0.6, "depth_m": 0.4,
           "pose": job["clip"] or "bind", "time": job["time"]},
          open(os.path.join(job["out"], job["prefix"] + "views.json"), "w", encoding="utf-8"))
json.dump({"argv": argv, "job": job, "images": len(doc.get("images", [])), "animations": [a["name"] for a in doc.get("animations", [])]},
          open(os.environ["AZURIK_STUB_LOG"], "w", encoding="utf-8"))
'''


def test_model_preview_renders_each_view_through_headless_blender(usa_iso, tmp_path, monkeypatch, capsys):
    """Modkit's Step 2.154 (D443): ``model preview`` exports the body with
    its textures and the clip it poses, runs Blender headless
    (``--background --factory-startup --python blender/preview.py -- JOB``,
    here a stand-in that writes the pictures as Blender would) with the
    views, size, clip, time and hidden materials asked, and moves a PNG a
    view and ``views.json`` into ``--out``, printing each; an unknown view,
    an output inside the checkout and a missing Blender exit 1 by name."""
    stub = _stand_in(tmp_path, _STUB)
    log = tmp_path / "called.json"
    monkeypatch.setenv("AZURIK_STUB_LOG", str(log))
    out = tmp_path / "out"

    def run(*argv: str) -> tuple[int, str, str]:
        code = model.main(["preview", "townspeople/female_2", *argv, "--iso", str(usa_iso)])
        return code, *capsys.readouterr()

    code, printed, _ = run("--out", str(out), "--views", "front,top", "--size", "320", "--clip", "idle", "--time",
                           "0.5", "--hide", "row3", "--blender", str(stub))
    assert code == 0
    called = json.loads(log.read_text(encoding="utf-8"))
    assert called["argv"][:3] == ["--background", "--factory-startup", "--python"]
    assert Path(called["argv"][3]).parts[-2:] == ("blender", "preview.py") and called["argv"][4] == "--"
    assert {k: called["job"][k] for k in ("views", "size", "clip", "time", "hide")} == \
        {"views": ["front", "top"], "size": 320, "clip": "idle", "time": 0.5, "hide": ["row3"]}
    assert called["images"] > 0 and called["animations"] == ["idle"]
    assert sorted(p.name for p in out.iterdir()) == [
        "townspeople_female_2_front.png", "townspeople_female_2_top.png", "townspeople_female_2_views.json"]
    assert printed.splitlines() == ["townspeople/female_2 (idle at 0.5 s): 2 views, 320 px, a 2.00 m frame",
                                    f"  front: {out / 'townspeople_female_2_front.png'}",
                                    f"  top: {out / 'townspeople_female_2_top.png'}"]
    _no_blender(monkeypatch, tmp_path)
    for over, refusal in (({"--views": "sideways"}, "the views are"),
                          ({"--out": str(image.CHECKOUT / "previews")}, "inside the checkout"),
                          ({"--blender": str(tmp_path / "nowhere")}, "Blender isn't found")):
        given = {"--out": str(tmp_path / "again"), "--blender": str(stub), **over}
        code, _, err = run(*(x for pair in given.items() for x in pair))
        assert code == 1 and err.startswith("model preview: ") and refusal in err
    assert not (tmp_path / "again").exists() and not (image.CHECKOUT / "previews").exists()


_BATCH_STUB = '''
import json, os, sys, time
inherited = []                          # the files this Blender was given open (the slot's lock)
for fd in range(3, 64):
    try:
        inherited.append(os.fstat(fd).st_ino)
    except OSError:
        pass
import numpy as np
argv = sys.argv[1:]
job = json.load(open(argv[-1], encoding="utf-8"))
body, pos = np.load(job["body"]), np.load(job["positions"])
(w, h), rows = job["size"], job["views"]
shape = (len(job["keep"]), h * len(rows), w * max(map(len, rows)), 4)
out = np.lib.format.open_memmap(job["out"], "w+", np.uint8, shape)
for k, f in enumerate(job["keep"]):
    out[k] = int(pos[f][0, 0])          # a frame drawn as its first vertex's x
out.flush()
if job["mp4"]:
    open(job["mp4"]["path"], "wb").write(b"mp4")
json.dump({"began": time.time(), "build": 0.0, "frames": len(pos)}, open(job["timing"], "w", encoding="utf-8"))
with open(os.environ["AZURIK_STUB_LOG"], "a", encoding="utf-8") as f:
    f.write(json.dumps({"argv": argv, "job": job, "vertices": int(body["vertices"]), "inherited": inherited}) + "\\n")
'''


def test_a_batch_renders_every_frame_of_a_body_from_one_headless_blender_and_writes_the_body_once(tmp_path,
                                                                                                    monkeypatch):
    """Modkit's Step X.62: ``batch.render`` draws F poses of one body with
    one Blender launch (``--background --factory-startup
    --python-exit-code 1 --python blender/batch_inside.py -- JOB``, here a
    stand-in that draws a frame as its first vertex's x), the frames
    ``keep`` names back in its order and every frame piped to the MP4;
    the body's arrays go to the cache once by their content, so a second
    job on the same body finds them (and an old unused file goes, but
    never one just written with an old time, as a copy keeps); Blender
    holds the slot's lock too, so a killed caller's Blender still fills
    its slot; a frame that doesn't fit the body, a keep past the frames
    and a missing Blender fail by name, and with
    ``AZURIK_BLENDER_SLOTS=1`` a held slot leaves none (Windows has no
    ``flock``, so no cap: as Modkit's)."""
    monkeypatch.setattr(bb, "CACHE", tmp_path / "cache")
    stub = _stand_in(tmp_path, _BATCH_STUB)
    log = tmp_path / "called.jsonl"
    monkeypatch.setenv("AZURIK_STUB_LOG", str(log))
    pts = np.zeros((4, 3))
    body = bb.Body(pts, np.zeros((4, 2)), [np.array([[0, 1, 2]]), np.array([[0, 2, 3]])],
                   [np.full((2, 2, 4), 9, np.uint8), None])
    frames = [pts + (10.0 * f, 0, 0) for f in range(5)]
    views = [[bb.View(180.0), bb.View(270.0)], [bb.View(0.0, 0.85, (0.0, 0.0, 1.18))]]
    stale = bb.cache_path("blender-bodies", "old.npz")
    stale.write_bytes(b"")
    os.utime(stale, (0, 0))
    got = bb.render(body, frames, views=views, size=(16, 24), keep=[4, 1], mp4=tmp_path / "out" / "a.mp4",
                    blender=stub, ffmpeg=stub)
    called = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert len(called) == 1 and called[0]["vertices"] == 4
    assert called[0]["argv"][:5] == ["--background", "--factory-startup", "--python-exit-code", "1", "--python"]
    assert Path(called[0]["argv"][5]).parts[-2:] == ("blender", "batch_inside.py") and called[0]["argv"][6] == "--"
    assert called[0]["job"]["mp4"]["fps"] == 15.0 and (tmp_path / "out" / "a.mp4").is_file()
    held = {os.stat(bb.cache_path("blender-slots", "0.lock")).st_ino} if bb.fcntl else set()
    assert held <= set(called[0]["inherited"]) and len(held) == (bb.fcntl is not None)
    assert got.frames.shape == (2, 48, 32, 4) and [int(f[0, 0, 0]) for f in got.frames] == [40, 10]
    assert not got.body_cached and got.seconds["frames"] == 5
    again = bb.render(body, np.array(frames), views=views, size=(16, 24), blender=stub)
    called = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert again.body_cached and called[1]["job"]["body"] == called[0]["job"]["body"] and len(again.frames) == 5
    assert len(list((tmp_path / "cache" / "blender-bodies").iterdir())) == 1 and not stale.exists()
    old = tmp_path / "old"
    old.write_bytes(b"")
    os.utime(old, (0, 0))
    copied = [bb.cached("blender-bodies", "copied.npz", lambda p: shutil.copy2(old, p)) for _ in range(2)]
    assert [(path.is_file(), hit) for path, hit in copied] == [(True, False), (True, True)]
    _no_blender(monkeypatch, tmp_path)
    (found := tmp_path / "found" / "x.xiso").parent.mkdir()
    found.write_bytes(b"image")
    monkeypatch.setenv("AZURKIT_ISO", str(found))
    for positions, kwargs, refusal in (([pts[:3]], {}, r"frame 0's positions are \(3, 3\); the body has 4"),
                                       (frames, {"keep": [5]}, r"keep \[5\]: distinct frames of 0 to 4"),
                                       (frames, {"blender": tmp_path / "nowhere"}, "Blender isn't found"),
                                       (frames, {"mp4": image.CHECKOUT / "a.mp4"}, "inside the checkout"),
                                       (frames, {"mp4": found}, "an image's folder")):
        with pytest.raises(ValueError, match=refusal):
            bb.render(body, positions, views=views, **{"blender": stub, **kwargs})
    assert len(log.read_text(encoding="utf-8").splitlines()) == 2 and found.read_bytes() == b"image"
    monkeypatch.setenv("AZURIK_BLENDER_SLOTS", "1")
    with bb.slot():
        if bb.fcntl is None:
            with bb.slot(wait=0) as second:
                assert second.fds == ()
        else:
            with pytest.raises(ValueError, match="all 1 Blender slots are busy"), bb.slot(wait=0):
                pass


_LOD_STUB = '''
import json, os, sys
job = json.load(open(sys.argv[-1], encoding="utf-8"))


def triangles(path):
    doc = json.load(open(path, encoding="utf-8"))
    return sum(doc["accessors"][p["indices"]]["count"] // 3 for p in doc["meshes"][0]["primitives"])
views = {v: os.path.join(job["out"], job["prefix"] + v + ".png") for v in job["views"]}
for path in views.values():
    open(path, "wb").write(b"png")
json.dump({"views": views, "frame_m": 2.0, "pose": "bind", "time": 0.0},
          open(os.path.join(job["out"], job["prefix"] + "views.json"), "w", encoding="utf-8"))
json.dump({"shown": triangles(job["gltf"]), "frame": job["frame"] and triangles(job["frame"])},
          open(os.environ["AZURIK_STUB_LOG"], "w", encoding="utf-8"))
'''


def test_a_lod_is_previewed_in_lod_0s_frame_and_a_model_edit_pass_prints_each_lod_its_build_draws(usa_iso, tmp_path,
                                                                                                   monkeypatch):
    """Modkit's Step 2.166e (D537): ``model preview --lod K`` draws the
    body's LOD K alone (catalisk's LOD 2, its triangles and no other's)
    framed on its LOD 0 posed the same way (that export is the job's
    ``frame``) into ``<body>_lod<K>_<view>.png``; a LOD the body lacks is
    refused by name.  A ``model edit`` pass weighs the body as its build
    leaves its LODs: female_2 (the W36 line lowered under her 5,151
    triangles) takes the shadow LOD her build cuts, worn by garret4, and
    the pass prints each LOD's row as ``model inspect`` does, LOD 1 drawn
    only in his realtime shadow.  Step 2.166d: with a recipe's ``lods`` the
    pass takes the LOD 1 W39 cuts instead, drawn on screen past 9 m."""
    from azurkit.tools.characters import decimate as dm
    from azurkit.tools.characters import gltf
    from azurkit.tools.characters._player_character import write_shadow_lod
    from azurkit.tools.characters.model_inspect import inspect, lod_line
    from azurkit.tools.characters.ports import XbrDocument, point_keyed_string
    from devkit.models import edit

    body = "townspeople/female_2"
    data, config, index = image.read(usa_iso, "gamedata/characters.xbr", "gamedata/config.xbr",
                                     "gamedata/index/index.xbr")
    stub = _stand_in(tmp_path, _LOD_STUB)
    log = tmp_path / "called.json"
    monkeypatch.setenv("AZURIK_STUB_LOG", str(log))
    report = preview.preview(data, "catalisk", tmp_path / "out", views=("front",), lod=2, blender=stub)
    with edit._building(usa_iso):   # the swap's state, where model_inspect reads the packs' budget
        rows = inspect(data, "catalisk")["lods"]
    assert json.loads(log.read_text(encoding="utf-8")) == {"shown": rows[2]["triangles"], "frame": rows[0]["triangles"]}
    assert report["lod"] == 2 and sorted(p.name for p in (tmp_path / "out").iterdir()) == [
        "catalisk_lod2_front.png", "catalisk_lod2_views.json"]
    for who, lod, refusal in (("catalisk", 4, "catalisk has no LOD 4: its LODs are 0 to 3"),
                              ("catalisk", -1, "catalisk has no LOD -1: its LODs are 0 to 3"),
                              (body, 1, f"{body} has no LOD 1: it has only LOD 0")):
        with pytest.raises(ValueError, match=refusal):
            preview.preview(data, who, tmp_path / "never", lod=lod, blender=stub)

    monkeypatch.setattr(dm, "SHADOW_MIN", 5000)
    work = tmp_path / "work"
    e = gltf.export_body(data, body, work / "export", [])
    shutil.copy2(e.gltf, work / edit.SAVED)   # her save: the export unchanged
    shutil.copy2(e.gltf.with_suffix(".bin"), work / e.gltf.with_suffix(".bin").name)
    session = edit.Session(work, usa_iso, body, "town_female_2", "tester", "topology", e.gltf, data, config, index,
                           {"base": "town_female_2", "mode": "own"})
    said: list[str] = []
    row = edit.run_pass(session, preview=False, say=said.append)
    doc = XbrDocument.from_bytes(config)
    engine = doc.keyed_section("critters_engine")
    point_keyed_string(engine, "garret4", "body", "town_female_2", "body")
    game = {"characters.xbr": bytearray(data)}
    with edit._building(usa_iso):
        write_shadow_lod(game, engine, body)
        built = inspect(bytes(game["characters.xbr"]), body, config_xbr=bytes(doc.raw))
    assert row["ok"] and [n["drawn"] for n in built["lods"]] == ["steady", "shadow"], row
    assert said[1:3] == [f"  {lod_line(built, n)}" for n in built["lods"]]
    assert said[2].endswith("; drawn only in a realtime shadow") and f"({built['lods'][1]['share']['triangles']} " \
        "of LOD 0's)" in said[2]
    assert row["lods"] == [{"lod": n["lod"], "triangles": n["triangles"], "push_bytes": n["push_bytes"],
                            "bmsh_bytes": n["bmsh_bytes"], "run_bytes": n["run_bytes"],
                            "share": n["share"]["triangles"], "drawn": n["drawn"]} for n in built["lods"]]
    recipe = json.loads((work / edit.RECIPE).read_text(encoding="utf-8"))
    recipe["tester"]["lods"] = {"ratio": [0.3], "at": [9]}
    (work / edit.RECIPE).write_text(json.dumps(recipe), encoding="utf-8")
    row = edit.run_pass(session, preview=False, say=said.append)
    assert row["ok"] and [n["drawn"] for n in row["lods"]] == ["steady", "steady"], row
    assert 0.25 * 5151 < row["lods"][1]["triangles"] <= 0.3 * 5151


_EDIT_STUB = '''
import json, os, struct, sys
argv = sys.argv[1:]
job = json.load(open(argv[-1], encoding="utf-8"))
doc = json.load(open(job["export"], encoding="utf-8"))
blob = open(os.path.join(os.path.dirname(job["export"]), doc["buffers"][0]["uri"]), "rb").read()
del doc["buffers"][0]["uri"]
text = json.dumps(doc).encode()
text += b" " * (-len(text) % 4)
blob += b"\\0" * (-len(blob) % 4)
glb = struct.pack("<II", len(text), 0x4E4F534A) + text + struct.pack("<II", len(blob), 0x004E4942) + blob
if not os.environ.get("AZURIK_STUB_NO_SAVE"):
    open(job["glb"], "wb").write(b"glTF" + struct.pack("<II", 2, 12 + len(glb)) + glb)
    json.dump({"n": 1}, open(job["saves"], "w", encoding="utf-8"))
json.dump({"argv": argv, "job": job}, open(os.environ["AZURIK_STUB_LOG"], "w", encoding="utf-8"))
'''


def test_model_edit_headless_pass_imports_the_save_writes_the_recipe_and_opens_no_window(usa_iso, tmp_path,
                                                                                        monkeypatch, capsys):
    """Modkit's Step 2.158 (D465, D491): ``model edit --headless`` exports
    the body into its work folder, runs Blender with ``--background
    --factory-startup`` and a script's exception as its exit code, and the
    session script (a stand-in that saves the export unchanged as
    ``edit.glb``, as Blender's save hook would), reads the save back in
    one pass (a log row weighing her own runs as her build will, its bake
    included; ``recipe.json``'s ``mesh.gltf`` the save's file, sha256 and
    import), leaves out her own ``idle`` (``--clips idle``: no column
    plays it, so a build would play vanilla's) and leaves its
    ``--variant-file`` as it was, the file its recipe names copied beside
    the session's; a run that saves nothing is refused with no pass and
    no image; the interactive mode under ``$CLAUDECODE`` is refused before
    any process starts."""
    from azurkit.tools.characters import mesh_edit

    stub = _stand_in(tmp_path, _EDIT_STUB)
    log = tmp_path / "called.json"
    monkeypatch.setenv("AZURIK_STUB_LOG", str(log))
    seed = tmp_path / "seed.json"
    spin = {"generator": "gltf", "file": "spin.glb", "sha256": "0" * 64, "animation": "spin"}
    seed.write_text(json.dumps({"tester": {"base": "town_female_2", "mode": "own", "title": "T", "clips": {"spin": spin}}}),
                    encoding="utf-8")
    (tmp_path / "spin.glb").write_bytes(b"spin")
    before = seed.read_bytes()
    work = tmp_path / "work"

    def edit(*more: str) -> tuple[int, str]:
        code = model.main(["edit", "town_female_2", "--work", str(work), "--variant-file", str(seed), "--blender",
                           str(stub), "--no-preview", "--iso", str(usa_iso), *more])
        return code, capsys.readouterr().err

    assert edit("--headless", "--clips", "idle")[0] == 0
    called = json.loads(log.read_text(encoding="utf-8"))
    assert called["argv"][:5] == ["--background", "--factory-startup", "--python-exit-code", "1", "--python"]
    assert Path(called["argv"][5]).parts[-2:] == ("blender", "edit_session.py") and called["argv"][6] == "--"
    rows = [json.loads(line) for line in (work / "log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1 and rows[0]["ok"] and rows[0]["vertices"] == 3427 and rows[0]["unplayed"] == ["idle"], rows
    assert 1.5 < rows[0]["bake_mib"] < rows[0]["own_runs_mib"] - 0.3, rows   # her vanilla runs are 0.367 MiB
    recipe = json.loads((work / "recipe.json").read_text(encoding="utf-8"))["tester"]
    assert recipe["mesh"]["gltf"] == {"file": "edit.glb", "sha256": mesh_edit.file_sha256(work / "edit.glb"),
                                      "import": "topology"} and recipe["title"] == "T" and recipe["clips"] == {"spin": spin}
    assert seed.read_bytes() == before and (work / "spin.glb").read_bytes() == b"spin"
    monkeypatch.setenv("AZURIK_STUB_NO_SAVE", "1")
    code, err = edit("--headless", "--build", str(tmp_path / "never.iso"))
    assert code == 1 and not (tmp_path / "never.iso").exists() and "Blender saved nothing" in err
    assert len((work / "log.jsonl").read_text(encoding="utf-8").splitlines()) == 1
    log.unlink()
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("CLAUDECODE", "1")
    work = tmp_path / "never"
    code, err = edit()
    assert code == 1 and not log.exists() and not work.exists()
    assert "an agent or a test runs model edit --headless" in err
