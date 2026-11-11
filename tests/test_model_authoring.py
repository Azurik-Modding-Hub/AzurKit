"""A character body's authoring engine (Step 4.15a2: Modkit's T11 tests,
``test_model_{export,import,write,lods,paint}``, ported and merged): what
``python -m devkit models model`` (``devkit/models/model.py``) and a
variant's build stand on, in ``src/azurkit/tools/characters/``.

- **glTF export and clips:** a body exported to glTF 2.0 skins and plays as
  the game draws it (``gltf.export_body``), and its animations come back as
  clips (``clip_import``, ``model clips``).
- **Mesh edits and imports:** an edited glTF's moved vertices (``mesh_edit``'s
  ``mesh.gltf``, ``model check``), any topology or painted weights
  (``gltf_import``, ``model import``), and every mesh op on synthetic
  sheets, chests and spheres (subdivide, round, hem, bind, reweight, cut,
  relax, island, atlas, tube, thicken, late scale).
- **The writer:** strips, a topology edit grown in place, the format's
  refusals, payloads re-paged, bones added and renamed, a body's subset and
  the player's size lines (``body_codec``, ``skeleton``, ``model_inspect``).
- **LODs:** the game's pick, the decimator, new and dropped LODs, W36's
  shadow LOD and W39's (``decimate``, ``lods``).
- **Paint and colours:** the bake, the paint ops, W38's recolour, the PNG
  round trip and ``model export --variant`` (``paint``, ``colour_preview``).

The glTF a test edits is ``model export``'s, turned into the shape Blender
5.2.2's default export writes it (Modkit's Step 2.142 design, measured
headless): positions and inverse binds in glTF's y up, the joints in
another order, two vertices split into copies, ``_AZ_VID`` dropped with
``TEXCOORD_1`` kept, a ``Cube`` mesh beside it, tiny weights dropped and the
rest renormalised, every position one float32 ulp off. No test runs a real
Blender. A test that reads game data reads the verified USA image (the
``usa`` fixture), and prints counts and hashes only."""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import struct
import subprocess
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from azurkit.core import iso
from azurkit.core.xbr.nodes import named_resources, parse_toc, runs
from azurkit.tools.characters import body_codec as bc
from azurkit.tools.characters import mesh_edit, paint
from azurkit.tools.characters.characters import body_at, mesh_groups, mesh_points, read_body
from azurkit.tools.characters.decimate import decimate, drawn, lod_chain
from azurkit.tools.characters.gltf import export_body
from azurkit.tools.characters.lods import FLT_MAX, pick, reach, thresholds
from azurkit.tools.characters.model_inspect import inspect, own_runs
from azurkit.tools.characters.render import body_meshes
from azurkit.tools.characters.retarget import Rig, origins, pose, read_clip
from devkit.models import model
from tests import _hosts

ROOT = Path(__file__).resolve().parent.parent
BODY = "townspeople/female_2"
BARNACLE = "barnacle"   # the smallest body with nearly every case: a 31-bone palette with slot bytes up to 32, 29 scale
#                         helpers, derived and sampled translations, 3 LODs
UP = np.array([[1.0, 0, 0], [0, 0, 1], [0, -1, 0]])     # the model's (x, y, z) in glTF's y up: (x, z, -y)
_CODES = {5126: "f", 5121: "B", 5123: "H", 5125: "I"}
_TYPES = {5126: "<f4", 5121: "u1", 5123: "<u2", 5125: "<u4"}
_WIDTHS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


@pytest.fixture(scope="session")
def usa(usa_iso):
    """A file of the verified USA image by its path (``gamedata/characters.xbr``), read once a session."""
    kept: dict[str, bytes] = {}

    def read(name: str) -> bytes:
        if name not in kept:
            with iso.Reader(usa_iso) as r:
                kept[name] = r.read(name)
        return kept[name]
    return read


@pytest.fixture
def building(usa_iso):
    """Inside it, the swap's modules read the packs and the USA image's
    vanilla files as a build's do (``ports.building``: ``model_inspect``'s
    budget lines, the player's load budget, W36 and W39)."""
    from azurkit.core import gate
    from azurkit.tools import characters, mods
    from azurkit.tools.characters import ports

    stamp = gate.verify(str(usa_iso), whole=False)
    with ports.building(ports.Build(ports.Vanilla(stamp.release, stamp.path, stamped=stamp), taken=[],
                                    packs=characters.packs_view(stamp.release, mods.PACKS))):
        yield


def _run(capsys, *argv: str) -> tuple[int, str, str]:
    """``python -m devkit models model ARGV``, in this process."""
    code = model.main(list(argv))
    out, err = capsys.readouterr()
    return code, out, err


# --------------------------------------------------------------------------- glTF export and clips

def _accessor(doc: dict, blob: bytes, i: int) -> np.ndarray:
    acc = doc["accessors"][i]
    view = doc["bufferViews"][acc["bufferView"]]
    width = _WIDTHS[acc["type"]]
    flat = struct.unpack_from(f"<{acc['count'] * width}{_CODES[acc['componentType']]}", blob,
                              view.get("byteOffset", 0) + acc.get("byteOffset", 0))
    return np.array(flat, float).reshape(acc["count"], width)

def _rotation(q) -> np.ndarray:
    x, y, z, w = np.asarray(q, float) / np.linalg.norm(q)
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])

def _worlds(doc: dict, trs: dict[int, tuple]) -> dict[int, np.ndarray]:
    world: dict[int, np.ndarray] = {}
    stack = [(r, np.eye(4)) for r in doc["scenes"][0]["nodes"]]
    while stack:
        i, parent = stack.pop()
        t, q, s = trs[i]
        local = np.eye(4)
        local[:3, :3], local[:3, 3] = _rotation(q) * np.asarray(s, float), t
        world[i] = parent @ local
        stack += [(c, world[i]) for c in doc["nodes"][i].get("children", [])]
    return world

def _cubic(times: np.ndarray, out: np.ndarray, t: float) -> np.ndarray:
    """glTF's CUBICSPLINE at ``t``: ``out`` holds (in, value, out) per key."""
    out = out.reshape(len(times), 3, -1)
    if t <= times[0]:
        return out[0, 1]
    if t >= times[-1]:
        return out[-1, 1]
    i = int(np.searchsorted(times, t, side="right")) - 1
    d = times[i + 1] - times[i]
    s = (t - times[i]) / d
    return ((2 * s ** 3 - 3 * s ** 2 + 1) * out[i, 1] + d * (s ** 3 - 2 * s ** 2 + s) * out[i, 2]
            + (-2 * s ** 3 + 3 * s ** 2) * out[i + 1, 1] + d * (s ** 3 - s ** 2) * out[i + 1, 0])

def test_a_body_exported_to_gltf_skins_and_plays_as_the_game_draws_it(usa, tmp_path):
    characters = usa("gamedata/characters.xbr")
    gltf = export_body(characters, BARNACLE, tmp_path / "out").gltf
    doc, blob = json.loads(gltf.read_text(encoding="utf-8")), gltf.with_suffix(".bin").read_bytes()
    rest = {i: (n.get("translation", (0, 0, 0)), n.get("rotation", (0, 0, 0, 1)), n.get("scale", (1, 1, 1)))
            for i, n in enumerate(doc["nodes"])}
    joints = doc["skins"][0]["joints"]
    binds = _accessor(doc, blob, doc["skins"][0]["inverseBindMatrices"]).reshape(-1, 4, 4).transpose(0, 2, 1)
    world = _worlds(doc, rest)
    rig = Rig.read(characters, BARNACLE)
    names = [b.name for b in rig.bones]
    groups = {g.index: g for g in mesh_groups(characters, BARNACLE) if g.lod == 0}
    points, first = np.array(mesh_points(characters, BARNACLE)), np.cumsum([0] + [g.count for g in groups.values()])

    for p in doc["meshes"][0]["primitives"]:
        a = p["attributes"]
        vid = _accessor(doc, blob, a["_AZ_VID"]).astype(int)
        g = groups[vid[0, 0]]
        pos, joint, weight = (_accessor(doc, blob, a[k]) for k in ("POSITION", "JOINTS_0", "WEIGHTS_0"))
        joint = joint.astype(int)
        # (a) the rest pose, skinned by glTF's rules, is the mesh as the game stores it
        skinned = sum(weight[:, i, None] * np.einsum("vxy,vy->vx", np.array([world[joints[j]] @ binds[j]
                                                                            for j in joint[:, i]]),
                                                      np.c_[pos, np.ones(len(pos))])[:, :3] for i in range(4))
        want = points[first[list(groups).index(g.index)] + vid[:, 1]] @ UP.T
        assert np.abs(skinned - want).max() < 1e-5
        # (b) each live weight's joint is its +56 slot byte's palette bone (or its helper), and the
        # decode is a bijection onto the palette: b-1 for every byte would put 32 past barnacle's 31
        # entries, b-2 for every byte 1 before them, a permuted pairing a live weight on a zero byte
        raw = np.frombuffer(characters, np.uint8, 60 * g.count, g.vertices).reshape(g.count, 60)
        slots, live = raw[:, 56:60].astype(int), raw[:, 12:28].copy().view("<f4") > 0
        entry = np.where(slots <= 12, slots - 1, slots - 2)[live]
        assert ((entry >= 0) & (entry < len(g.bones))).all()
        assert set(entry) == set(range(len(g.bones)))
        assert [doc["nodes"][joints[j]]["name"].removesuffix("__scale") for j in joint[live]] == \
            [names[g.bones[e]] for e in entry]

    # (c) every clip, and at 8 times each every bone's world rotation is the engine model's, and the
    # position of every bone no scale animates the ancestors of is retarget.origins'
    toc = parse_toc(characters)
    offsets = {n.casefold(): toc[i].file_offset for i, n in named_resources(characters).items()}
    anims = doc["animations"]
    assert sorted(a["name"] for a in anims) == list(read_body(characters, BARNACLE).clips)
    for anim in anims:
        clip = read_clip(characters, offsets[f"characters/{BARNACLE}/{anim['name']}".casefold()])
        scaled = {tr.target for tr in clip.bones if 7 <= tr.comp <= 9}
        for t in np.linspace(0.0, clip.length, 8):
            live_trs = {i: list(v) for i, v in rest.items()}
            for c in anim["channels"]:
                s = anim["samplers"][c["sampler"]]
                live_trs[c["target"]["node"]][("translation", "rotation", "scale").index(c["target"]["path"])] = \
                    _cubic(_accessor(doc, blob, s["input"])[:, 0], _accessor(doc, blob, s["output"]), t)
            got = _worlds(doc, live_trs)
            for k, (q, o) in enumerate(zip(pose(rig, clip, t), origins(rig, clip, t))):
                r = got[k][:3, :3] / np.linalg.norm(got[k][:3, :3], axis=0)
                cos = (np.trace(r.T @ UP @ _rotation(q)) - 1) / 2
                assert np.degrees(np.arccos(min(1.0, cos))) < 1e-4, (anim["name"], t, names[k])
                if not scaled & set(rig.ancestors(k)):
                    assert np.abs(got[k][:3, 3] - UP @ o).max() < 1e-5, (anim["name"], t, names[k])

def _animated(gltf, name: str, source: str, edit, hz: int = 30) -> None:
    """``gltf`` (an export's .gltf) with an animation ``name``: ``source``'s
    channels resampled LINEAR at ``hz``, as Blender exports them (a still
    one STEP), each value through ``edit(node, path, value)``."""
    doc, blob = json.loads(gltf.read_text(encoding="utf-8")), bytearray(gltf.with_suffix(".bin").read_bytes())

    def add(values: np.ndarray, kind: str) -> int:
        data = np.ascontiguousarray(values, "<f4").tobytes()
        blob.extend(b"\0" * (-len(blob) % 4))
        doc["bufferViews"].append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data)})
        blob.extend(data)
        rows = np.asarray(values, "<f4").reshape(len(values), -1)
        acc = {"bufferView": len(doc["bufferViews"]) - 1, "componentType": 5126, "count": len(rows), "type": kind}
        if kind == "SCALAR":
            acc["min"], acc["max"] = [float(rows.min())], [float(rows.max())]
        doc["accessors"].append(acc)
        return len(doc["accessors"]) - 1

    anim = next(a for a in doc["animations"] if a["name"] == source)
    length = anim["extras"]["length"]
    times = np.arange(0.0, length + 1e-9, 1 / hz)
    new = {"name": name, "channels": [], "samplers": []}
    for c in anim["channels"]:
        s = anim["samplers"][c["sampler"]]
        keys = _accessor(doc, bytes(blob), s["input"])[:, 0]
        out = _accessor(doc, bytes(blob), s["output"])
        values = np.array([edit(c["target"]["node"], c["target"]["path"], _cubic(keys, out, t)) for t in times])
        held = bool(np.all(np.float32(values) == np.float32(values[0])))     # Blender writes a still channel STEP
        new["samplers"].append({"input": add(times, "SCALAR"), "output": add(values, {3: "VEC3", 4: "VEC4"}[
            values.shape[1]]), "interpolation": "STEP" if held else "LINEAR"})
        new["channels"].append({"sampler": len(new["samplers"]) - 1, "target": c["target"]})
    doc["animations"].append(new)
    doc["buffers"][0]["byteLength"] = len(blob)
    gltf.with_suffix(".bin").write_bytes(bytes(blob))
    gltf.write_text(json.dumps(doc), encoding="utf-8")

def test_a_bodys_clips_come_back_from_gltf_animations(usa, usa_iso, tmp_path, monkeypatch, capsys):
    """Step 2.154 (D443): ``clip_import`` reads glTF animations back as
    clips.  The export's own (barnacle's, with its scale helpers, and
    female_2's) come back byte for byte and write characters.xbr
    unchanged; a new animation of female_2 (her walk resampled LINEAR at
    30 Hz as Blender 5.2.2 exports it, a still channel STEP, her left arm
    turned 20 degrees down) is a
    new clip whose pose is the file's (the import's check) and its arm
    20 degrees off the walk's, added under her with its index record; a
    channel on a node that is no bone fails by name.  Step 2.158: her idle
    keyed every 1/24 s (Blender's default) comes back thinned from the
    keys the import keeps of the file's (none it doesn't key; on the
    recording host 23,387 of 26,869: a component at its bone's rest is
    dropped, an exact float test, so another host keeps another count,
    D1016) to at most 2.4 times vanilla's 686 (1,625 measured), its pose
    within THIN_TOLERANCE of the unthinned clip's at 200 times.  ``model
    clips --out`` writes the clip and its index record as that, the
    recipe row naming the file's sha256, and writes nothing when a clip is
    refused."""
    from azurkit.tools.characters import clip_import
    from azurkit.tools.characters.index_xbr import parse_index_xbr
    from azurkit.tools.characters.retarget import named_clip, qangle, write_clip

    characters = usa("gamedata/characters.xbr")
    index = usa("gamedata/index/index.xbr")
    for body in (BARNACLE, "townspeople/female_2"):
        gltf = export_body(characters, body, tmp_path / body.replace("/", "_"), None).gltf
        got = clip_import.read_clips(characters, body, gltf)
        assert got and all(c.made == 0 and write_clip(c.clip) == write_clip(named_clip(characters, body, c.name))
                           for c in got)
        assert clip_import.write_clips(characters, index, body, got) == (characters, index)

    body = "townspeople/female_2"
    names = [n["name"] for n in json.loads(gltf.read_text(encoding="utf-8"))["nodes"]]
    arm = names.index("left_arm_1")
    turn = np.array([np.sin(np.radians(10)), 0.0, 0.0, np.cos(np.radians(10))])

    def edit(node, path, value):
        if node == arm and path == "rotation":
            x1, y1, z1, w1 = value
            x2, y2, z2, w2 = turn
            return (w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2, w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
                    w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2, w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2)
        return value

    _animated(gltf, "walk_raised", "walk", edit)
    got = {c.name: c for c in clip_import.read_clips(characters, body, gltf)}
    raised = got["walk_raised"]
    assert got["walk"].made == 0 and raised.made > 0 and not raised.replaces and \
        raised.interpolations == ("LINEAR", "STEP")
    out, index2 = clip_import.write_clips(characters, index, body, [raised])
    assert write_clip(named_clip(out, body, "walk_raised")) == write_clip(raised.clip)
    assert f"characters/{body}/walk_raised" in {r.key for r in parse_index_xbr(index2).records}
    code, said, _ = _run(capsys, "clips", "town_female_2", str(gltf), "--clips", "walk_raised", "--out",
                         str(tmp_path / "clips"), "--iso", str(usa_iso))
    assert code == 0 and "walk_raised: a new clip" in said
    assert f'"sha256": "{mesh_edit.file_sha256(gltf)}", "animation": "walk_raised"' in said
    assert [(tmp_path / "clips" / n).read_bytes() for n in ("characters.xbr", "index.xbr")] == [out, index2]
    rig = Rig.read(characters, body)
    k = rig.bones.index(next(b for b in rig.bones if b.name == "left_arm_1"))
    for t in (0.1, 0.5):
        walk, mine = pose(rig, named_clip(characters, body, "walk"), t), pose(rig, raised.clip, t)
        assert abs(qangle(walk[k], mine[k]) - 20.0) < 0.5

    from azurkit.tools.characters import gltf as gx
    _animated(gltf, "idle_24", "idle", lambda node, path, value: value, hz=24)
    thin = clip_import.read_clips(characters, body, gltf, ["idle_24"])[0]
    monkeypatch.setattr(clip_import, "THIN_HALVINGS", -1)   # no pass: the clip as the file keys it
    full = clip_import.read_clips(characters, body, gltf, ["idle_24"])[0]
    vanilla = sum(len(tr.keys) for tr in named_clip(characters, body, "idle").bones)
    doc = json.loads(gltf.read_text(encoding="utf-8"))
    idle = next(a for a in doc["animations"] if a["name"] == "idle_24")
    keyed = sum(doc["accessors"][s["input"]]["count"] * {"VEC3": 3, "VEC4": 4}[doc["accessors"][s["output"]]["type"]]
                for s in idle["samplers"])   # the file's keys, a component each
    assert vanilla == 686 and thin.keys_before == full.keys_after <= keyed and thin.keys_after <= 2.4 * vanilla
    if _hosts.recording():   # a component at its bone's rest is dropped, an exact float test: the count is a host's
        assert (keyed, thin.keys_before) == (26869, 23387)
    info = gx._read(characters, body)
    assert max(float(np.abs(a - b).max()) for t in np.linspace(0.0, full.clip.length, 200)
               for a, b in zip(gx._engine(info, thin.clip, float(t)), gx._engine(info, full.clip, float(t)))) \
        < clip_import.THIN_TOLERANCE

    doc = json.loads(gltf.read_text(encoding="utf-8"))
    next(a for a in doc["animations"] if a["name"] == "walk_raised")["channels"][0]["target"]["node"] = \
        names.index(body.replace("/", "_"))
    gltf.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ValueError, match="the node is no bone of"):
        clip_import.read_clips(characters, body, gltf, ["walk_raised"])
    code, _, err = _run(capsys, "clips", body, str(gltf), "--out", str(tmp_path / "refused"), "--iso", str(usa_iso))
    assert code == 1 and "the node is no bone of" in err and not (tmp_path / "refused").exists()


# --------------------------------------------------------------------------- glTF mesh edits, imports and the mesh ops

def _band(model: np.ndarray) -> np.ndarray:
    """The chest band the edit moves (the design's: 172 vertices)."""
    return (np.abs(model[:, 0]) <= 0.2) & (model[:, 2] >= 1.25) & (model[:, 2] <= 1.47) & (model[:, 1] >= 0.05)

def _shaped(export: Path, move: float = 0.10) -> dict:
    """``export`` (``model export``'s .gltf) as Blender writes it back,
    its chest band moved ``move`` along the model's +y."""
    doc, blob = json.loads(export.read_text(encoding="utf-8")), export.with_suffix(".bin").read_bytes()

    def read(i: int) -> np.ndarray:
        acc = doc["accessors"][i]
        view = doc["bufferViews"][acc["bufferView"]]
        return np.frombuffer(blob, _TYPES[acc["componentType"]], acc["count"] * _WIDTHS[acc["type"]],
                             view.get("byteOffset", 0)).reshape(acc["count"], -1).copy()

    skin = doc["skins"][0]
    order = list(reversed(range(len(skin["joints"]))))
    flip = np.eye(4)
    flip[:3, :3] = UP
    binds = read(skin["inverseBindMatrices"]).reshape(-1, 4, 4).transpose(0, 2, 1).astype(float)
    prims = []
    for p in doc["meshes"][0]["primitives"]:
        a = p["attributes"]
        model = read(a["POSITION"]).astype(float)
        model[_band(model), 1] += move
        w = read(a["WEIGHTS_0"]).astype(float)
        w[w < 1e-4] = 0.0
        prims.append({"POSITION": np.nextafter((model @ UP.T).astype(np.float32), np.float32(np.inf)),
                      "NORMAL": (read(a["NORMAL"]) @ UP.T).astype(np.float32), "TEXCOORD_0": read(a["TEXCOORD_0"]),
                      "TEXCOORD_1": read(a["TEXCOORD_1"]),
                      "JOINTS_0": np.array([order.index(j) for j in read(a["JOINTS_0"]).ravel()]).reshape(-1, 4),
                      "WEIGHTS_0": (w / w.sum(1, keepdims=True)).astype(np.float32),
                      "indices": read(p["indices"]).reshape(-1, 3).astype(np.int64), "material": p["material"]})
    for p, t in ((prims[0], 0), (prims[-1], 5)):     # two vertices split, one triangle each taking the copy
        v = int(p["indices"][t, 0])
        for k in ("POSITION", "NORMAL", "TEXCOORD_0", "TEXCOORD_1", "JOINTS_0", "WEIGHTS_0"):
            p[k] = np.concatenate([p[k], p[k][v:v + 1]])
        p["indices"][t, 0] = len(p["POSITION"]) - 1
    return {"doc": doc, "prims": prims, "joints": [skin["joints"][j] for j in order],
            "binds": [binds[j] @ np.linalg.inv(flip) for j in order]}

def _glb(shape: dict, out: Path) -> Path:
    """``shape`` written as a .glb: its mesh, a startup ``Cube`` beside it."""
    doc, blob, accessors, views = shape["doc"], bytearray(), [], []

    def add(values: np.ndarray, kind: str, component: int) -> int:
        data = np.ascontiguousarray(values, _TYPES[component]).tobytes()
        blob.extend(b"\0" * (-len(blob) % 4))
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data)})
        blob.extend(data)
        accessors.append({"bufferView": len(views) - 1, "componentType": component,
                          "count": len(data) // np.dtype(_TYPES[component]).itemsize // _WIDTHS[kind], "type": kind})
        return len(accessors) - 1

    kinds = {"POSITION": ("VEC3", 5126), "NORMAL": ("VEC3", 5126), "TEXCOORD_0": ("VEC2", 5126),
             "TEXCOORD_1": ("VEC2", 5126), "_AZ_VID": ("VEC2", 5126), "JOINTS_0": ("VEC4", 5121),
             "WEIGHTS_0": ("VEC4", 5126)}
    primitives = [{"attributes": {k: add(p[k], *kinds[k]) for k in kinds if k in p}, "mode": 4,
                   "indices": add(p["indices"].ravel(), "SCALAR", 5125), "material": p["material"]}
                  for p in shape["prims"]]
    cube = np.array([[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)], np.float32)
    faces = np.array([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1],
                      [2, 3, 7], [2, 7, 6], [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]])
    nodes = [*doc["nodes"], {"name": "Cube", "mesh": 1}]
    out_doc = {"asset": {"version": "2.0", "generator": "Khronos glTF Blender I/O"}, "scene": 0,
               "scenes": [{"nodes": [*doc["scenes"][0]["nodes"], len(nodes) - 1]}], "nodes": nodes,
               "meshes": [{"name": doc["meshes"][0]["name"], "primitives": primitives},
                          {"name": "Cube", "primitives": [{"attributes": {"POSITION": add(cube, "VEC3", 5126)},
                                                           "indices": add(faces.ravel(), "SCALAR", 5125)}]}],
               "skins": [{"joints": shape["joints"], "inverseBindMatrices": add(
                   np.array([b.T.ravel() for b in shape["binds"]], np.float32), "MAT4", 5126)}],
               "materials": doc["materials"], "accessors": accessors, "bufferViews": views,
               "buffers": [{"byteLength": len(blob)}]}
    text = json.dumps(out_doc).encode()
    text += b" " * (-len(text) % 4)
    blob.extend(b"\0" * (-len(blob) % 4))
    out.write_bytes(struct.pack("<4sII", b"glTF", 2, 28 + len(text) + len(blob)) + struct.pack("<II", len(text), 0x4E4F534A)
                    + text + struct.pack("<II", len(blob), 0x004E4942) + bytes(blob))
    return out

def _plan(characters: bytes, path: Path, body: str = BODY, sha: str | None = None) -> mesh_edit.MeshPlan:
    sha = sha or hashlib.sha256(path.read_bytes()).hexdigest()
    return mesh_edit.plan(characters, body, mesh_edit.MeshSpec(gltf=(path.name, sha)), path.parent)

@pytest.fixture(scope="module")
def exported(usa, tmp_path_factory) -> tuple[bytes, Path]:
    characters = usa("gamedata/characters.xbr")
    return characters, export_body(characters, BODY, tmp_path_factory.mktemp("f2") / "out", []).gltf


def test_an_edited_gltf_writes_its_moved_vertices_in_place(exported, usa_iso, tmp_path, capsys):
    """Step 2.142 (D390): a Blender-shaped edit of the export, its chest
    band moved 0.10 forward, writes exactly that band's 172 vertices, each
    at vanilla's + (0, 0.10, 0), ids read from TEXCOORD_1 through the
    y-up frame, the two split copies merged and the Cube named; the
    normals rewritten are unit and only round the band; every other byte
    of characters.xbr stays vanilla's.  ``model check`` prints those
    counts and the recipe row with the file's sha256, writing nothing."""
    characters, gltf = exported
    plan = _plan(characters, path := _glb(_shaped(gltf), tmp_path / "edit.glb"))
    code, said, _ = _run(capsys, "check", "town_female_2", str(path), "--iso", str(usa_iso))
    assert code == 0 and said.splitlines()[:2] == [
        f"{BODY}: 3429 glTF vertices for 3427 (2 copies merged; ids from TEXCOORD_1, y up); ignored, no vertex id: "
        "Cube",
        f"172 vertices moved (up to {plan.largest:.3f} model units), normals recomputed on {len(plan.normals)}, "
        f"{plan.turned} triangles turned over"]
    assert f'"gltf": {{"file": "edit.glb", "sha256": "{hashlib.sha256(path.read_bytes()).hexdigest()}"}}' in said
    assert sorted(p.name for p in tmp_path.iterdir()) == ["edit.glb"]
    groups = [g for g in mesh_groups(characters, BODY) if g.lod == 0]
    cells = {(g.index, j): g.vertices + 60 * j for g in groups for j in range(g.count)}
    old = {vid: struct.unpack_from("<3f", characters, at) for vid, at in cells.items()}
    band = {vid for vid, p in old.items() if _band(np.array([p]))[0]}
    assert (len(band), set(plan.positions)) == (172, band)
    assert all(np.abs(np.array(plan.positions[vid]) - old[vid] - (0, 0.10, 0)).max() < 1e-6 for vid in band)
    e = plan.gltf
    assert (e.carrier, e.merged, e.ignored, e.swapped, e.vertices) == ("TEXCOORD_1", 2, ("Cube",), True, 3429)

    written = bytearray(characters)
    mesh_edit.write(written, plan, characters)
    ring = set()   # the band's triangles' vertices, and every vertex at one of their places (the weld)
    for g, me in zip(groups, body_meshes(characters, parse_toc(characters), body_at(characters, BODY)[0])):
        for t in me.triangles.tolist():
            if any((g.index, v) in band for v in t):
                ring |= {(g.index, v) for v in t}
    places = {old[vid] for vid in ring}
    ring |= {vid for vid, p in old.items() if p in places}
    assert plan.normals and set(plan.normals) <= ring
    for vid, n in plan.normals.items():
        assert abs(np.linalg.norm(struct.unpack_from("<3f", written, cells[vid] + 28)) - 1) < 1e-6
    probe = bytearray(written)
    for vid in plan.positions:
        probe[cells[vid]:cells[vid] + 12] = characters[cells[vid]:cells[vid] + 12]
    for vid in plan.normals:
        probe[cells[vid] + 28:cells[vid] + 40] = characters[cells[vid] + 28:cells[vid] + 40]
    assert probe == characters

def _no_id(s):
    for p in s["prims"]:
        del p["TEXCOORD_1"]

def _drop_vertex(s):
    p = s["prims"][1]
    v = int(p["indices"][0, 0])
    p["indices"] = p["indices"][~(p["indices"] == v).any(1)]
    p["indices"][p["indices"] > v] -= 1
    for k in ("POSITION", "NORMAL", "TEXCOORD_0", "TEXCOORD_1", "JOINTS_0", "WEIGHTS_0"):
        p[k] = np.delete(p[k], v, 0)

def _foreign(s):
    for p in s["prims"]:
        p["_AZ_VID"] = p["TEXCOORD_1"].copy()
    s["prims"][1]["_AZ_VID"][3] = (0.0, 99999.0)

def _tear(s):
    s["prims"][0]["POSITION"][-1] += np.float32(0.001)

def _open_seam(s):
    p = s["prims"][1]
    first: dict[bytes, int] = {}
    for i, row in enumerate(p["POSITION"]):     # two vertices (two ids) vanilla keeps at one place
        if first.setdefault(row.tobytes(), i) != i:
            p["POSITION"][i, 0] += np.float32(0.001)
            return

def _flip(s):
    s["prims"][1]["indices"][7, [1, 2]] = s["prims"][1]["indices"][7, [2, 1]]

def _uv(s):
    s["prims"][1]["TEXCOORD_0"][9, 0] += np.float32(0.01)

def _weight(s):
    w = s["prims"][1]["WEIGHTS_0"]
    v = int(np.argmax((w > 0.3).sum(1) >= 2))
    w[v, 0] -= np.float32(0.1)
    w[v, 1] += np.float32(0.1)

def _bind(s):
    s["binds"][3] = s["binds"][3].copy()
    s["binds"][3][0, 3] += 0.01

def _scaled(s):
    s["binds"] = [b @ np.diag([1.01, 1.01, 1.01, 1.0]) for b in s["binds"]]

def _no_joints(s):
    s["joints"], s["binds"] = [], []

def _no_uv(s):
    for p in s["prims"]:
        del p["TEXCOORD_0"]

def test_an_edited_gltf_that_changes_more_than_positions_fails_by_name(exported, tmp_path):
    """D35, D390 (Step 2.142): a glTF edit fails by name, writing nothing,
    when no mesh carries an id, a vertex is gone or isn't the body's, a
    split copy or a seam vanilla keeps whole is pulled apart, a triangle
    turns over or goes, a UV or a weight moves or the UVs are gone, a
    bone's bind moves, the whole frame scales or the skin lists no joints,
    or the recipe's sha256 isn't the file's."""
    characters, gltf = exported
    for k, (mutate, said) in enumerate((
            (_no_id, "no mesh carries a vertex id"),
            (_drop_vertex, "1 of townspeople/female_2's vertices missing"),
            (_foreign, "1 vertices with no id of townspeople/female_2's"),
            (_tear, "copies lie 1 mm apart: a seam was torn"),
            (_open_seam, "1 seams open"),
            (_flip, "the triangles changed: 1 missing, 1 new"),
            (_uv, "UVs changed at 1 vertices"),
            (_weight, "the skin changed at 1 vertices"),
            (_bind, "the skeleton's bind pose changed"),
            (_scaled, "the mesh frame isn't townspeople/female_2's or an axis swap of it"),
            (_no_joints, "the skin lists 0 joints and 0 inverse binds"),
            (_no_uv, "a primitive has no TEXCOORD_0"))):
        shape = _shaped(gltf)
        mutate(shape)
        with pytest.raises(ValueError) as caught:
            _plan(characters, _glb(shape, tmp_path / f"m{k}.glb"))
        assert said in str(caught.value), (mutate.__name__, str(caught.value))
    path = _glb(_shaped(gltf), tmp_path / "edit.glb")
    with pytest.raises(ValueError, match="its sha256 is"):
        _plan(characters, path, BODY, "0" * 64)

def _cloth_y(X: np.ndarray, cloth: np.ndarray, q: np.ndarray, window: float) -> float | None:
    """The cloth's front (its triangles ``cloth`` at ``X``, seen along +y) over the point ``q``: the largest y of
    those covering q's (x, z) that lies no more than ``window`` behind q, else ``None``."""
    a, b, c = X[cloth[:, 0]][:, [0, 2]], X[cloth[:, 1]][:, [0, 2]], X[cloth[:, 2]][:, [0, 2]]
    e, f, p = b - a, c - a, q[[0, 2]] - a
    den = e[:, 0] * f[:, 1] - e[:, 1] * f[:, 0]
    ok = np.abs(den) > 1e-12
    den = np.where(ok, den, 1.0)
    u = (p[:, 0] * f[:, 1] - p[:, 1] * f[:, 0]) / den
    v = (e[:, 0] * p[:, 1] - e[:, 1] * p[:, 0]) / den
    y = X[cloth[:, 0], 1] + u * (X[cloth[:, 1], 1] - X[cloth[:, 0], 1]) + v * (X[cloth[:, 2], 1] - X[cloth[:, 0], 1])
    hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (y > q[1] - window)
    return float(y[hit].max()) if hit.any() else None

def test_a_mesh_op_moves_only_its_region_and_never_folds(exported):
    """Step 2.143 (D403): each deform op on female_2's vanilla mesh moves
    what its docstring says and nothing else.  A ``push`` (mirrored,
    limited to the skin, group 1) moves each vertex along its direction
    (mirrored with it) by at most its height, only inside its ellipse and
    in front of its depth gate, the vertex at its centre by the full
    height, and never folds (det J >= 1); a ``taper`` scales x and y about
    its line by exactly its factors on its plateau within its reach,
    leaves z and everything past its window or reach; a ``smooth`` scale
    moves each vertex by (1 - d^2)^2 (factors - 1)(p - c); a ``tuck`` of
    the pushed skin behind the top (group 4) moves skin only backwards,
    leaves every vertex it moves ``margin`` behind the top's front, and
    with a ``band`` only the vertices at those bind heights."""
    characters, _ = exported
    mesh = mesh_edit._read_mesh(characters, BODY)
    base = np.array(mesh.positions)
    group = np.array([g for g, _ in mesh.ids])
    index = {vid: k for k, vid in enumerate(mesh.ids)}
    origin = dict(zip(mesh.names, mesh.origins))

    def built(*ops):
        plan = mesh_edit.plan(characters, BODY, mesh_edit.MeshSpec(ops=ops))
        out = base.copy()
        for vid, p in plan.positions.items():
            out[index[vid]] = p
        return plan, out, np.linalg.norm(out - base, axis=1) > 1e-5

    push = mesh_edit.PushOp("spine_2", (0.05, 1.0, -0.3), 0.1, (0.06, 0.07, 0.12, 0.09), 0.15,
                            offset=(0.07, 0.12, 0.05), mirror=True, groups=(1,))
    plan, after, moved = built(push)
    assert moved.sum() > 100 and set(group[moved]) == {1} and plan.det_min >= 1 - 1e-9
    centres = []
    for side in (1.0, -1.0):
        c = np.array(origin["spine_2"]) + (0.07 * side, 0.12, 0.05)
        n, s, t = (np.array(v) for v in mesh_edit.push_frame((0.05 * side, 1.0, -0.3)))
        q = base - c
        inside = (q @ n > -0.15) & ((q @ s / 0.07) ** 2 + (q @ t / 0.12) ** 2 < 1)
        mine = moved & inside
        d = after[mine] - base[mine]
        assert np.abs(np.cross(d, n)).max() < 2e-5 and 0 < (d @ n).min() and (d @ n).max() <= 0.1 + 2e-5
        centres.append((c, n, mine))
    assert not (moved & ~(centres[0][2] | centres[1][2])).any()
    c, n, _ = centres[0]
    front = np.where((group == 1) & ((base - c) @ n >= 0))[0]
    near = front[np.argmin(np.linalg.norm(np.cross(base[front] - c, n), axis=1))]
    assert np.linalg.norm(after[near] - base[near]) > 0.09

    taper = mesh_edit.TaperOp("root_joint", (0.8, 0.9), 0.04, 0.08, (0.2, 0.3), offset=(0.0, 0.015, 0.12))
    plan, after, moved = built(taper)
    c = np.array(origin["root_joint"]) + (0.0, 0.015, 0.12)
    r = np.linalg.norm(base[:, :2] - c[:2], axis=1)
    core = (np.abs(base[:, 2] - c[2]) <= 0.04) & (r <= 0.2)
    assert core.sum() > 50 and plan.det_min > 0
    assert np.abs(after[core, :2] - (c[:2] + (base[core, :2] - c[:2]) * (0.8, 0.9))).max() < 2e-5
    assert np.abs(after[:, 2] - base[:, 2]).max() < 2e-5
    assert not moved[(np.abs(base[:, 2] - c[2]) >= 0.12) | (r >= 0.3)].any()

    smooth = mesh_edit.ScaleOp("spine_2", (0.2, 0.2, 0.2), (1.5, 1.2, 1.0), profile="smooth")
    plan, after, moved = built(smooth)
    c = np.array(origin["spine_2"])
    d2 = (((base - c) / 0.2) ** 2).sum(1)
    want = base + np.where(d2 < 1, (1 - d2) ** 2, 0.0)[:, None] * (np.array((1.5, 1.2, 1.0)) - 1) * (base - c)
    assert moved.sum() > 100 and np.abs(after - want).max() < 2e-5     # float32, and MOVED's 1e-5

    bulge = mesh_edit.PushOp("spine_2", (0.0, 1.0, 0.0), 0.05, (0.1, 0.1, 0.1, 0.1), 0.1, offset=(0.07, 0.1, 0.05),
                             mirror=True, groups=(1,))
    _, pushed, _ = built(bulge)
    top = np.array([t for t in mesh.triangles if all(group[v] == 4 for v in t)
                    and not any(mesh.names[mesh.heaviest[v]].startswith("loincloth") for v in t)
                    and sum(mesh.normals[v][1] for v in t) > 0])
    poking = [k for k in np.where(group == 1)[0] if pushed[k, 1] != base[k, 1]
              and (y := _cloth_y(pushed, top, pushed[k], 0.05)) is not None and pushed[k, 1] > y]
    assert len(poking) > 10
    for band in (None, (1.30, 1.40)):
        tuck = mesh_edit.TuckOp((1,), (4,), (0.0, 1.0, 0.0), 0.003, skip=("loincloth_front_1", "loincloth_back_1"),
                                strict=True, band=band, faces=True)
        plan, after, _ = built(bulge, tuck)
        back = np.where(np.abs(after - pushed).max(1) > 2e-5)[0]
        assert plan.tucked == len(back) > 0 and set(group[back]) == {1}
        assert np.abs((after - pushed)[back][:, [0, 2]]).max() < 2e-5 and (after - pushed)[back, 1].max() < 0
        for k in back:
            y = _cloth_y(after, top, after[k], 0.05)
            assert y is None or after[k, 1] <= y - 0.003 + 1e-5
        if band is not None:
            assert ((base[back, 2] >= 1.30) & (base[back, 2] <= 1.40)).all()

def _sphere_mesh(seam: bool = True) -> mesh_edit._Mesh:
    """An icosahedron on the unit sphere about z 1 as one group of a one-bone body (bone ``root`` at the origin),
    its vertices at x < 0 on y > 0 copied (a UV seam: the copies' UVs differ) for the faces west of it."""
    import math as m

    from azurkit.tools.characters.characters import MeshGroup
    phi = (1 + m.sqrt(5)) / 2
    raw = [(-1, phi, 0), (1, phi, 0), (-1, -phi, 0), (1, -phi, 0), (0, -1, phi), (0, 1, phi), (0, -1, -phi),
           (0, 1, -phi), (phi, 0, -1), (phi, 0, 1), (-phi, 0, -1), (-phi, 0, 1)]
    pos = [mesh_edit._f32(tuple(c / m.sqrt(1 + phi * phi) + (1.0 if i == 2 else 0.0) for i, c in enumerate(p)))
           for p in raw]
    faces = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2),
             (10, 7, 6), (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11),
             (6, 2, 10), (8, 6, 7), (9, 8, 1)]
    uv = [(0.5 + p[0] / 2, 0.5 + p[1] / 2) for p in pos]
    nrm = [tuple(c - (1.0 if i == 2 else 0.0) for i, c in enumerate(p)) for p in pos]
    tris = list(faces)
    if seam:     # the faces on x < 0 take copies of their y > 0 corners, with their own UVs
        copy = {}
        for t, f in enumerate(faces):
            if sum(pos[v][0] for v in f) < 0:
                g = []
                for v in f:
                    if pos[v][1] > 0:
                        if v not in copy:
                            copy[v] = len(pos)
                            pos.append(pos[v])
                            nrm.append(nrm[v])
                            uv.append((uv[v][0] + 2.0, uv[v][1]))
                        v = copy[v]
                    g.append(v)
                tris[t] = tuple(g)
    n = len(pos)
    return mesh_edit._Mesh("sphere", 1, (MeshGroup(0, 0, (0,), 0, 0, n),), tuple((0, j) for j in range(n)),
                           tuple(struct.pack("<3f", *p) for p in pos), tuple(pos), tuple(nrm), tuple(uv),
                           tuple({0: 1.0} for _ in range(n)), tuple(0 for _ in range(n)), tuple(tris), ("root",), (-1,),
                           ((0.0, 0.0, 0.0),), ((1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0),))

@pytest.mark.parametrize("smooth", [True, False])
def test_a_subdivided_region_stays_closed_and_rounds_onto_its_surface(smooth):
    """Step 2.154 (D438): ``subdivide`` splits a closed surface (an
    icosahedron, a UV seam cut through it) until every edge in its region
    is at most ``edge``, and it stays closed: every welded edge is two
    triangles', each directed once (no T-junction, every winding kept);
    a seam's copies of a new point are bit-identical with their own UVs
    halfway; the new weights sum to 1; with ``smooth`` the new points lie
    near the sphere through the old (PN triangles' midpoints), without it
    on the old flat faces, inside it.  Outside the region nothing splits."""
    mesh = _sphere_mesh()
    op = mesh_edit.SubdivideOp("root", (2.0, 2.0, 2.0), 0.3, offset=(0.0, 0.0, 1.0), smooth=smooth)
    out, base, _ = mesh_edit._subdivide(mesh, mesh_edit.MeshSpec(ops=(op,)), list(mesh.positions))
    weld = {k: out.keys[k] for k in range(len(out.ids))}
    directed = Counter((weld[t[i]], weld[t[(i + 1) % 3]]) for t in out.triangles for i in range(3))
    assert len(out.ids) > 3 * len(mesh.ids) and all(n == 1 for n in directed.values())
    assert all(directed[(b, a)] == 1 for a, b in directed)
    assert max(math.dist(base[t[i]], base[t[(i + 1) % 3]]) for t in out.triangles for i in range(3)) <= 0.3
    radius = [math.dist(base[k], (0.0, 0.0, 1.0)) for k in range(len(mesh.ids), len(out.ids))]
    if smooth:      # within 4% of the sphere from an icosahedron's 63-degree edges (its flat midpoints: 15%)
        assert 0.96 < min(radius) and max(radius) < 1.01
    else:
        assert max(radius) < 0.9999 and min(radius) < 0.9
    at: dict[bytes, list[int]] = {}
    for k, key in enumerate(out.keys):
        at.setdefault(key, []).append(k)
    seams = [ks for ks in at.values() if len(ks) > 1 and ks[0] >= len(mesh.ids)]
    assert seams and all(out.positions[ks[0]] == out.positions[k] and out.uvs[ks[0]] != out.uvs[k]
                         for ks in seams for k in ks[1:])
    assert all(abs(sum(s.values()) - 1.0) < 1e-12 for s in out.skins)
    half = mesh_edit.SubdivideOp("root", (0.6, 0.6, 0.6), 0.3, offset=(0.0, 0.9, 1.0), smooth=smooth)
    part, pbase, _ = mesh_edit._subdivide(mesh, mesh_edit.MeshSpec(ops=(half,)), list(mesh.positions))
    far = [t for t in part.triangles if all(pbase[v][1] < -0.5 for v in t)]
    assert len(part.ids) > len(mesh.ids) and far and all(max(t) < len(mesh.ids) for t in far)

def _sheet(step: float = 0.0125) -> mesh_edit._Mesh:
    """A flat 0.4 m square facing forward (y = 0.06, z 1.1..1.5), its left half (x < 0) weighted to bone ``a``, its
    right half to ``b`` (both at (0, 0, 1.3))."""
    from azurkit.tools.characters.characters import MeshGroup
    pos, nrm, uv, tris, skins = [], [], [], [], []
    n = round(0.4 / step)
    for j in range(n + 1):
        for i in range(n + 1):
            x = -0.2 + i * step
            pos.append(mesh_edit._f32((x, 0.06, 1.1 + j * step)))
            nrm.append((0.0, 1.0, 0.0))
            uv.append((i / n, j / n))
            skins.append({0 if x < -1e-9 else 1: 1.0})
    for j in range(n):
        for i in range(n):
            a = j * (n + 1) + i
            tris += [(a, a + n + 2, a + 1), (a, a + n + 1, a + n + 2)]
    return mesh_edit._Mesh("sheet", 1, (MeshGroup(0, 0, (0, 1), 0, 0, len(pos)),), tuple((0, j) for j in range(len(pos))),
                           tuple(struct.pack("<3f", *q) for q in pos), tuple(pos), tuple(nrm), tuple(uv), tuple(skins),
                           tuple(next(iter(s)) for s in skins), tuple(tris), ("a", "b"), (-1, 0),
                           ((0.0, 0.0, 1.3), (0.0, 0.0, 1.3)), ((1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, -1.3, 1.0),) * 2)

def test_a_subdivision_splits_every_long_edge_beside_one_it_cant_split():
    """AZ-660 (Step 2.158): a push on bone ``a`` with ``b`` kept tears every edge between the two halves of a sheet
    (no split shortens it), so a longest-edge chain that reaches one can't split it; the subdivision remembers that
    edge, never splits it and starts the chain again, so no triangle of its region (``a``'s half) keeps an edge past
    ``edge`` in the final shape (before, 31 did: the chain ended and its first triangle was dropped), and the sheet
    stays closed: every welded edge is one or two triangles', and its open edges still run its 1.6 m border."""
    mesh = _sheet()
    spec = mesh_edit.MeshSpec(keep=("b",), ops=(
        mesh_edit.SubdivideOp("a", (0.15, 0.15, 0.15), 0.01, smooth=False),
        mesh_edit.PushOp("a", (0.0, 1.0, 0.0), 0.06, (0.12, 0.12, 0.12, 0.12), 0.1, offset=(-0.02, 0.0, 0.0))))
    out, base, _ = mesh_edit._subdivide(mesh, spec, list(mesh.positions))
    placed, regions = mesh_edit._place(out, spec), mesh_edit._regions(out, spec)

    def final(k: int):
        ops = [op for op in placed if op.selects(out.heaviest[k], 0)]
        return mesh_edit._displace(base[k], ops)[0] if ops else base[k]
    inside = [t for t in out.triangles if any(
        r.holds(tuple(sum(base[v][c] for v in t) / 3 for c in range(3))) and all(r.selects(out.heaviest[v], 0) for v in t)
        for r in regions)]
    assert len(out.ids) > len(mesh.ids) + 500 and inside
    assert max(math.dist(final(t[i]), final(t[(i + 1) % 3])) for t in inside for i in range(3)) <= 0.01
    edges = Counter(tuple(sorted((out.keys[t[i]], out.keys[t[(i + 1) % 3]]))) for t in out.triangles for i in range(3))
    assert set(edges.values()) == {1, 2}
    at = {out.keys[k]: base[k] for k in range(len(out.ids))}
    assert sum(math.dist(at[a], at[b]) for (a, b), n in edges.items() if n == 1) == pytest.approx(1.6, abs=1e-5)

def test_a_subdivision_apart_from_a_layers_open_edges_leaves_them_as_the_other_ops_do():
    """Step 2.177b (its judge's F1: booblord_high's finer bust let her skin rise through her top's lip where the top
    ends on her side): a subdivide op ``apart`` {edges, band} leaves every triangle whose final centroid lies within
    the band of an open edge of those groups, so a sheet split everywhere keeps vanilla's triangles along its border,
    splits its middle as before and stays closed; a group the body hasn't fails by name."""
    mesh = _sheet()
    got = {}
    for apart in (None, ((0,), 0.03)):
        op = mesh_edit.SubdivideOp("a", (0.3, 0.3, 0.3), 0.006, offset=(0.0, 0.06, 0.0), smooth=False, apart=apart)
        out, base, _ = mesh_edit._subdivide(mesh, mesh_edit.MeshSpec(ops=(op,)), list(mesh.positions))
        edges = Counter(tuple(sorted((out.keys[t[i]], out.keys[t[(i + 1) % 3]]))) for t in out.triangles
                        for i in range(3))
        assert set(edges.values()) == {1, 2}
        border = [min(0.2 - abs(c[0]), 0.2 - abs(c[2] - 1.3)) for c in (
            tuple(sum(base[v][k] for v in t) / 3 for k in range(3)) for t in out.triangles)]
        got[apart] = [(sum(max(t) >= len(mesh.ids) for t, d in zip(out.triangles, border) if test(d)),
                       sum(1 for d in border if test(d))) for test in (lambda d: d < 0.012, lambda d: d > 0.05)]
    (near, n), (far, f) = got[None]
    assert near == n > 0 and far == f > 0
    (near, n), (far, f) = got[((0,), 0.03)]
    assert near == 0 < n and far == f > 0
    op = mesh_edit.SubdivideOp("a", (0.3, 0.3, 0.3), 0.006, apart=((7,), 0.03))
    with pytest.raises(ValueError, match="apart.edges: sheet has no LOD-0 group 7"):
        mesh_edit._subdivide(mesh, mesh_edit.MeshSpec(ops=(op,)), list(mesh.positions))

def test_a_subdivisions_nearer_normals_take_the_angle_rule_only_where_it_lies_nearer_the_ring():
    """Step 2.188 (D727): booblord_high's angle weights cleared the specks at her top's fin tips, but a crack point's
    own fan, a wide-angled sliver against whole faces, leaned its normal off its ring (a darker notch at her top's
    edge in game); ``normals`` "nearer" takes, per vertex, whichever of the two normals lies nearer the mean of its
    ring's: the angle's at a fin's tip, the area's at such a crack point."""
    from azurkit.tools.characters.characters import MeshGroup

    def lean(pos, tris, normals):
        n = len(pos)
        mesh = mesh_edit._Mesh("n", 1, (MeshGroup(0, 0, (0,), 0, 0, n),), tuple((0, j) for j in range(n)),
                               tuple(struct.pack("<3f", *q) for q in pos), tuple(pos), ((0.0, 1.0, 0.0),) * n,
                               ((0.0, 0.0),) * n, ({0: 1.0},) * n, (0,) * n, tuple(tris), ("root",), (-1,),
                               ((0.0, 0.0, 0.0),), ((1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0),))
        spec = mesh_edit.MeshSpec(ops=(mesh_edit.SubdivideOp("root", (0.1, 0.1, 0.1), 0.01, offset=(0.0, 0.06, 1.3),
                                                             normals=normals),))
        return math.degrees(math.acos(mesh_edit._smooth_normals(mesh, pos, {0}, mesh_edit._angled(mesh, spec, pos,
                                                                                                    {0}))[0][1]))

    ring = [(0.005 * math.cos(a * math.pi / 3), 0.06, 1.3 + 0.005 * math.sin(a * math.pi / 3)) for a in range(6)]
    fin = ([(0.0, 0.06, 1.3), *ring, (0.04, 0.064, 1.3), (0.04, 0.06, 1.3)],
           [(0, i % 6 + 1, i) for i in range(1, 7)] + [(0, 7, 8)])
    wide = [(0.05 * math.cos(math.radians(a)), 0.06, 1.3 + 0.05 * math.sin(math.radians(a))) for a in (0, 10, 20, 30)]
    e1, e2 = (0.0, 0.0, 1.0), (0.5, -math.sqrt(0.75), 0.0)      # a plane leaning 60 degrees off the whole faces'
    tip = [tuple(c + 0.003 * (math.cos(math.radians(t)) * u + math.sin(math.radians(t)) * v)
                 for c, u, v in zip((0.0, 0.06, 1.3), e1, e2)) for t in (100, 250)]
    crack = ([(0.0, 0.06, 1.3), *wide, *tip], [(0, 2, 1), (0, 3, 2), (0, 4, 3), (0, 5, 6)])
    got = {(name, rule): lean(*case, rule) for name, case in (("fin", fin), ("crack", crack))
           for rule in ("area", "angle", "nearer")}
    assert got[("fin", "area")] > 45 and got[("fin", "angle")] < 1 and got[("fin", "nearer")] < 1
    assert got[("crack", "area")] < 1 and got[("crack", "angle")] > 45 and got[("crack", "nearer")] < 1

def _chest(step: float = 0.0125, notch: bool = False) -> mesh_edit._Mesh:
    """A flat "chest" of two layers facing forward (y), one bone ``spine`` at (0, 0, 1.3): group 0 (a skin) at
    y = 0.06 over x -0.25..0.25, z 1.15..1.60, group 1 (a cloth) 2 mm in front of it over x -0.25..0.25, z 1.15..1.45,
    with (``notch``) a staircase cut into its top edge (a coarse hem's corners)."""
    from azurkit.tools.characters.characters import MeshGroup
    pos, nrm, uv, tris, groups = [], [], [], [], []
    nx = round(0.5 / step)
    for g, (y, z1) in enumerate(((0.06, 1.60), (0.062, 1.45))):
        nz = round((z1 - 1.15) / step)
        first = len(pos)
        for j in range(nz + 1):
            for i in range(nx + 1):
                pos.append(mesh_edit._f32((-0.25 + i * step, y, 1.15 + j * step)))
                nrm.append((0.0, 1.0, 0.0))
                uv.append((i / nx, j / nz))
        here = []
        for j in range(nz):
            for i in range(nx):
                if notch and g == 1 and j == nz - 1 and (i // 4) % 2 == 0:
                    continue
                a = first + j * (nx + 1) + i
                b, c, d = a + 1, a + nx + 1, a + nx + 2
                here += [(a, b, d), (a, d, c)]      # facing -y as written: turned to face +y below
        tris += [(t[0], t[2], t[1]) for t in here]
        groups.append(MeshGroup(0, g, (0,), 0, 0, len(pos) - first))
    n = len(pos)
    ids = tuple((0, j) for j in range(groups[0].count)) + tuple((1, j) for j in range(groups[1].count))
    return mesh_edit._Mesh("chest", 1, tuple(groups), ids, tuple(struct.pack("<3f", *q) for q in pos), tuple(pos),
                           tuple(nrm), tuple(uv), tuple({0: 1.0} for _ in range(n)), tuple(0 for _ in range(n)),
                           tuple(tris), ("spine",), (-1,), ((0.0, 0.0, 1.3),),
                           ((1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, -0.0, -0.0, -1.3, 1.0),))

def test_a_round_drapes_its_top_bridges_its_pair_and_keeps_its_skin_beneath_its_cloth():
    """Step 2.154 round 2 (D438): on a flat two-layer chest, a mirrored ``round`` pair per layer (the cloth's 7 mm
    bigger, its blend narrower than the skin's, so the skin's crease rises through it): with ``drape`` the skin's
    upper half above the breast's centre line is a straight slope from the anchor line down to the ellipsoid (its
    forward step per centimetre near constant) and nothing above the anchor moves; with ``bridge`` the cleavage's
    walls by x = 0 come forward (the valley filled), none back, and x = 0 stays on x = 0; ``beneath`` leaves no skin vertex in front of the
    cloth along the skin's rays, where without it some are."""
    mesh = _chest()
    base = list(mesh.positions)

    def pair(group: int, grow: float, blend: tuple, **kw) -> mesh_edit.RoundOp:
        return mesh_edit.RoundOp("spine", (0.12 + grow, 0.12 + grow, 0.09 + grow, 0.11 + grow), 0.06, blend,
                                 offset=(0.08, 0.05, 0.05), mirror=True, groups=(group,), name="breast right", **kw)

    def final(*ops) -> np.ndarray:
        spec = mesh_edit.MeshSpec(ops=ops)
        rounds = mesh_edit._rounds(mesh, spec)
        out = [mesh_edit._round_all(p, rounds, 0, mesh.ids[k][0]) for k, p in enumerate(base)]
        mesh_edit._beneath(mesh, spec, out)
        return np.array(out)

    drape = (0.03, 0.25, 0.5, 1.0, 0.0)       # the anchor line 3 cm in the chest, 25 cm over the bone
    plain = final(pair(0, 0.0, (0.06, 0.03)), pair(1, 0.007, (0.02, 0.02)))
    draped = final(pair(0, 0.0, (0.02, 0.03), drape=drape, bridge=0.06), pair(1, 0.007, (0.02, 0.02), drape=drape,
                                                                               bridge=0.06))
    P = np.array(base)
    skin = np.array([g == 0 for g, _ in mesh.ids])
    column = np.where(skin & (np.abs(P[:, 0] - 0.0875) < 1e-3))[0]
    slope = [(draped[a, 1] - draped[b, 1]) / (draped[b, 2] - draped[a, 2]) for a, b in zip(column, column[1:])
             if 1.42 <= P[a, 2] and P[b, 2] <= 1.4876]
    assert len(slope) >= 4 and max(slope) < 1.2 * min(slope) and min(slope) > 0.5
    assert np.abs(draped[skin & (P[:, 2] > 1.56)] - P[skin & (P[:, 2] > 1.56)]).max() < 1e-9
    middle = np.where(np.abs(P[:, 0]) < 1e-6)[0]
    assert np.abs(draped[middle, 0]).max() < 1e-9
    walls = np.where(skin & (np.abs(P[:, 2] - 1.35) < 0.03) & (np.abs(P[:, 0]) < 0.04) & (plain[:, 1] > 0.12))[0]
    lift = draped[walls, 1] - plain[walls, 1]
    assert len(walls) > 4 and lift.min() > -1e-6 and lift.max() > 0.005

    def poking(out: np.ndarray, ops) -> int:
        side = mesh_edit._rounds(mesh, mesh_edit.MeshSpec(ops=ops))[0][0]
        n, sa, ta = side.frame
        o = np.array(side.centre) + side.rays[0] * np.array(sa) + side.rays[1] * np.array(n) + side.rays[2] * np.array(ta)
        cloth = [t for t in mesh.triangles if mesh.ids[t[0]][0] == 1]
        count = 0
        for k in np.where(skin & (P[:, 0] > 0.04) & (P[:, 2] > 1.25) & (P[:, 2] < 1.45))[0]:
            u = out[k] - o
            r = np.linalg.norm(u)
            u /= r
            for t in cloth:
                a, b, c = out[list(t)]
                e1, e2 = b - a, c - a
                pv = np.cross(u, e2)
                det = e1 @ pv
                if abs(det) < 1e-12:
                    continue
                tv = o - a
                x = tv @ pv / det
                qv = np.cross(tv, e1)
                yy = u @ qv / det
                if 0 <= x <= 1 and 0 <= yy and x + yy <= 1 and e2 @ qv / det < r:
                    count += 1
                    break
        return count
    ops = (pair(0, 0.0, (0.06, 0.03)), pair(1, 0.007, (0.02, 0.02)))
    with_beneath = (pair(0, 0.0, (0.06, 0.03), beneath=((1,), 0.003)), ops[1])
    assert poking(final(*ops), ops) > 0 == poking(final(*with_beneath), with_beneath)

def test_a_hem_splits_relaxes_and_tapers_a_cloths_open_edge():
    """Step 2.154 round 2 (D438): a ``hem`` on a cloth whose top edge is a staircase splits its open edges in the
    region to at most ``edge``, relaxes the loop at the base (its sharpest turn far gentler: the stair's corners
    rounded) and draws the cloth within ``width`` of the edge ``inset`` towards its centre (the edge's own points by
    the whole inset), the skin under it untouched."""
    mesh = _chest(0.025, notch=True)
    hem = mesh_edit.HemOp("spine", (0.3, 0.3, 0.25), 0.01, offset=(0.0, 0.1, 0.12), groups=(1,), relax=30,
                          inset=0.004, width=0.015)
    spec = mesh_edit.MeshSpec(ops=(hem,))
    out, base, _ = mesh_edit._subdivide(mesh, spec, list(mesh.positions))

    def loop(m, pos):
        faces: dict = {}
        for t in m.triangles:
            if m.ids[t[0]][0] != 1:
                continue
            for i in range(3):
                e = (min(t[i], t[(i + 1) % 3]), max(t[i], t[(i + 1) % 3]))
                faces[e] = faces.get(e, 0) + 1
        return [e for e, c in faces.items() if c == 1 and pos[e[0]][2] > 1.40 and pos[e[1]][2] > 1.40
                and abs(pos[e[0]][0]) < 0.2 and abs(pos[e[1]][0]) < 0.2]

    def sharpest(m, pos) -> float:
        nb: dict = {}
        for a, b in loop(m, pos):
            nb.setdefault(a, []).append(b)
            nb.setdefault(b, []).append(a)
        worst = 0.0
        for v, (a, b) in ((v, w) for v, w in nb.items() if len(w) == 2):
            d1, d2 = np.subtract(pos[v], pos[a]), np.subtract(pos[b], pos[v])
            worst = max(worst, math.degrees(math.acos(np.clip(d1 @ d2 / np.linalg.norm(d1) / np.linalg.norm(d2), -1, 1))))
        return worst
    edges = loop(out, base)
    assert edges and max(math.dist(base[a], base[b]) for a, b in edges) <= 0.01 + 1e-9
    plain, _, _ = mesh_edit._subdivide(mesh, mesh_edit.MeshSpec(ops=(replace(hem, relax=0),)), list(mesh.positions))
    assert sharpest(out, base) < 0.5 * sharpest(plain, list(plain.positions))
    final = list(base)
    mesh_edit._insets(out, spec, base, final)
    rim = {v for e in edges for v in e}
    moved = [math.dist(final[v], base[v]) for v in rim]
    assert min(moved) > 0.0039 and max(moved) < 0.0041
    assert all(final[k] == base[k] for k in range(len(base)) if out.ids[k][0] == 0)

def test_a_hems_relax_never_turns_a_face_beside_the_edge_over():
    """AZ-673: a ``hem`` relaxes its loop at the base, where a split cloth's faces beside the edge are small; a full
    step pulled a spike's tip below the vertex just inside it and turned the faces between them over (booblord's top:
    about 190 folded triangles on her left breast's outer side).  Each loop point's step is halved until none of its
    faces turns, so the tip still moves down, short of the vertex inside it."""
    from azurkit.tools.characters.characters import MeshGroup
    pos = [(-0.025, 0.06, 1.40), (-0.0125, 0.06, 1.40), (0.0, 0.06, 1.40), (0.0125, 0.06, 1.40), (0.025, 0.06, 1.40),
           (-0.025, 0.06, 1.45), (-0.0125, 0.06, 1.45), (0.0, 0.06, 1.46), (0.0125, 0.06, 1.45), (0.025, 0.06, 1.45),
           (0.0, 0.06, 1.457)]
    pos = [mesh_edit._f32(q) for q in pos]
    tris = ((0, 1, 6), (0, 6, 5), (1, 2, 10), (1, 10, 6), (2, 3, 10), (3, 8, 10), (3, 4, 8), (4, 9, 8), (6, 10, 7),
            (10, 8, 7))
    n = len(pos)
    mesh = mesh_edit._Mesh("cloth", 1, (MeshGroup(0, 0, (0,), 0, 0, n),), tuple((0, j) for j in range(n)),
                           tuple(struct.pack("<3f", *q) for q in pos), tuple(pos), tuple((0.0, 1.0, 0.0) for _ in pos),
                           tuple((q[0], q[2]) for q in pos), tuple({0: 1.0} for _ in pos), tuple(0 for _ in pos), tris,
                           ("spine",), (-1,), ((0.0, 0.0, 1.3),),
                           ((1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, -0.0, -0.0, -1.3, 1.0),))
    hem = mesh_edit.HemOp("spine", (0.3, 0.3, 0.3), 0.06, offset=(0.0, 0.06, 0.13), groups=(0,), relax=1)
    out, base, _ = mesh_edit._subdivide(mesh, mesh_edit.MeshSpec(ops=(hem,)), list(pos))
    assert len(out.triangles) == len(tris)
    turned = [t for t in tris if np.dot(mesh_edit._face(base, t), mesh_edit._face(pos, t)) <= 0.0]
    assert not turned and pos[10][2] < base[7][2] < pos[7][2] - 0.001

def test_a_cloth_binds_to_the_skin_under_it_and_a_reweight_moves_a_share_by_height():
    """Step 2.154 round 2 (D438): on the two-layer chest with a second bone, ``bind`` gives each cloth vertex in its
    region the skin weights of the skin vertex nearest it in the final shape (the skin's left half on one bone, its
    right on the other: the cloth's halves follow), and ``reweight`` moves ``share`` of a vertex's weight on ``take``
    to ``into`` by the region's falloff times a smoothstep of its height (none under ``z[0]``), each sum still 1."""
    chest = _chest()
    P = np.array(chest.positions)
    skins = tuple({1: 1.0} if p[0] > 0.0 else {0: 1.0} for p in P)
    mesh = replace(chest, names=("spine", "thigh"), parents=(-1, 0), origins=((0.0, 0.0, 1.3), (0.0, 0.0, 1.0)),
                   binds=chest.binds * 2, skins=skins)
    base = list(mesh.positions)
    bind = mesh_edit.BindOp("spine", (0.3, 0.3, 0.3), (0,), offset=(0.0, 0.06, 0.0), groups=(1,))
    got = mesh_edit._bind(mesh, mesh_edit.MeshSpec(ops=(bind,)), base, base)
    cloth = [k for k, (g, _) in enumerate(mesh.ids) if g == 1 and abs(P[k, 0]) > 0.01]
    assert set(got) >= set(cloth) and all(got[k] == ({1: 1.0} if P[k, 0] > 0 else {0: 1.0}) for k in cloth)
    even = replace(mesh, skins=tuple({0: 0.5, 1: 0.5} for _ in P))
    move = mesh_edit.ReweightOp("spine", (0.5, 0.5, 0.5), ("thigh",), "spine", 0.6, z=(1.25, 1.45), groups=(0,))
    out = mesh_edit._reweight(even, mesh_edit.MeshSpec(ops=(move,)), base, {})
    column = sorted((P[k, 2], out.get(k, {0: 0.5, 1: 0.5})[1]) for k in range(len(P))
                    if mesh.ids[k][0] == 0 and abs(P[k, 0]) < 1e-6)
    assert all(w == 0.5 for z, w in column if z <= 1.25) and min(w for z, w in column) < 0.3
    assert all(abs(sum(s.values()) - 1.0) < 1e-12 for s in out.values())

def test_a_bind_with_reach_gives_neighbouring_cloth_neighbouring_weights_and_fade_keeps_its_edge_its_own():
    """Step 2.154 round 6 (D512: "why does her neck have jagged edges pointing out now?"): her strap by the neck took
    the nearest skin vertex's weights, the neck's for one vertex and the shoulder's for the next, and tore into
    slivers when she moved (round 4's A: 42 to 64 of its triangles turned over in idle and walk, 2 without the bind).
    The measure kept: the largest step in a bone's weight between neighbouring cloth vertices.  On the chest whose
    skin's halves sit on two bones, a plain bind steps 1.0 across x = 0; ``reach`` mixes the skin within it (a step
    under 0.3, each sum 1); ``fade`` keeps a vertex near the region's edge mostly its own; a bind reads the weights
    an earlier bind gave its ``to`` layer, and ``near`` binds only the vertices close to that layer."""
    chest = _chest()
    P = np.array(chest.positions)
    skins = tuple({1: 1.0} if p[0] > 0.0 else {0: 1.0} for p in P)
    mesh = replace(chest, names=("spine", "thigh"), parents=(-1, 0), origins=((0.0, 0.0, 1.3), (0.0, 0.0, 1.0)),
                   binds=chest.binds * 2, skins=skins)
    base = list(mesh.positions)

    def step(got: dict) -> float:
        worst = 0.0
        for t in mesh.triangles:
            if mesh.ids[t[0]][0] != 1 or not all(v in got for v in t):
                continue
            for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
                worst = max(worst, abs(got[a].get(1, 0.0) - got[b].get(1, 0.0)))
        return worst
    plain = mesh_edit.BindOp("spine", (0.3, 0.3, 0.3), (0,), offset=(0.0, 0.06, 0.0), groups=(1,))
    mixed = replace(plain, reach=0.05)
    got = {op: mesh_edit._bind(mesh, mesh_edit.MeshSpec(ops=(op,)), base, base) for op in (plain, mixed)}
    assert step(got[plain]) == 1.0 and step(got[mixed]) < 0.3
    assert all(abs(sum(s.values()) - 1.0) < 1e-12 for s in got[mixed].values())
    layered = replace(mesh, skins=tuple({1: 1.0} if g == 0 else {0: 1.0} for g, _ in mesh.ids))
    faded = mesh_edit._bind(layered, mesh_edit.MeshSpec(ops=(replace(plain, fade=True),)), base, base)
    d2 = {k: (P[k, 0] / 0.3) ** 2 + ((P[k, 1] - 0.06) / 0.3) ** 2 + ((P[k, 2] - 1.3) / 0.3) ** 2 for k in faded}
    centre = min(faded, key=d2.get)
    rim = [k for k in faded if d2[k] > 0.8]
    assert faded[centre][1] > 0.95 and rim and max(faded[k].get(1, 0.0) for k in rim) <= 0.04 + 1e-12
    assert all(abs(sum(s.values()) - 1.0) < 1e-12 for s in faded.values())
    # round 7: with a reach a layer binds to its own group, its weights mixed (the skin under her strap), else refused
    own = replace(mixed, groups=(0,))
    mine = mesh_edit._bind(mesh, mesh_edit.MeshSpec(ops=(own,)), base, base)
    skin = [t for t in mesh.triangles if mesh.ids[t[0]][0] == 0 and all(v in mine for v in t)]
    assert skin and max(abs(mine[a].get(1, 0.0) - mine[b].get(1, 0.0)) for t in skin
                        for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0]))) < 0.3
    with pytest.raises(ValueError, match="own group only with a reach"):
        mesh_edit._bind(mesh, mesh_edit.MeshSpec(ops=(replace(plain, groups=(0,)),)), base, base)
    # round 10 (D582: skin through her strap): the skin under the cloth binds to the cloth and takes the weights the
    # bind before it gave the cloth (the skin's mix), not the cloth's own; with ``near`` the skin past it keeps its own
    sheet = replace(mesh, skins=tuple(({1: 1.0} if P[k, 0] > 0.0 else {0: 1.0}) if g == 0 else {0: 1.0}
                                      for k, (g, _) in enumerate(mesh.ids)))
    under = mesh_edit.BindOp("spine", (0.3, 0.3, 0.3), (1,), offset=(0.0, 0.06, 0.0), groups=(0,), near=(0.003, 0.03))
    both = mesh_edit._bind(sheet, mesh_edit.MeshSpec(ops=(mixed, under)), base, base)
    cloth = {k for k in both if sheet.ids[k][0] == 1}
    lent = [k for k in both if sheet.ids[k][0] == 0 and P[k, 2] < 1.44]
    assert cloth and lent and all(
        both[k] == both[min(cloth, key=lambda j: (float(((P[j] - P[k]) ** 2).sum()), j))] for k in lent)
    assert any(both[k].get(1, 0.0) > 0.5 for k in lent)       # the cloth's own weights were all bone 0
    assert not [k for k in both if sheet.ids[k][0] == 0 and P[k, 2] > 1.48]
    # near measures to the layer's surface, not its nearest vertex (a coarse strap's corners 3.5 cm from the skin
    # under its quads' middles, 2 mm under them): that skin binds whole to the strap's bone
    coarse = _chest(0.05)
    Q = [(x + 0.025, y, z + 0.025) if g == 1 else (x, y, z) for (x, y, z), (g, _) in zip(coarse.positions, coarse.ids)]
    coarse = replace(coarse, names=("spine", "thigh"), parents=(-1, 0), origins=((0.0, 0.0, 1.3), (0.0, 0.0, 1.0)),
                     binds=coarse.binds * 2, positions=tuple(Q), skins=tuple({1: 1.0} if g == 1 else {0: 1.0}
                                                                          for g, _ in coarse.ids))
    strapped = mesh_edit._bind(coarse, mesh_edit.MeshSpec(ops=(replace(under, near=(0.003, 0.03)),)), Q, Q)
    middle = next(k for k, (g, _) in enumerate(coarse.ids) if g == 0 and np.allclose(Q[k], (0.0, 0.06, 1.3), atol=1e-6))
    corners = np.array([q for q, (g, _) in zip(Q, coarse.ids) if g == 1])
    assert np.linalg.norm(corners - Q[middle], axis=1).min() > 0.03 and strapped.get(middle) == {1: 1.0}

def test_a_cut_ends_a_cloth_in_one_straight_edge_pressed_into_the_skin_with_a_cord_along_it():
    """Step 2.154 round 6 (D513: her sash "cut diagonally" to "reveal a lot"): on the flat two-layer chest a ``cut``
    with a diagonal plane drops the cloth past it in its region and cuts the triangles it crosses: no cloth corner lies
    past it, the new edge's points lie on it (one straight line from the front), each new point's UV is its place's
    (the pattern isn't stretched) and the skin is untouched.  Its ``press`` sinks the cloth by the edge to ``thick``
    over a skin sunk ``depth``, the bare skin past the edge swelling out by up to ``swell`` and nothing farther than
    its reach moved; its ``trim`` lays a cord along the edge that rides it."""
    mesh = _chest()
    base = list(mesh.positions)
    n = (0.7071067811865476, 0.0, 0.7071067811865476)
    cut = mesh_edit.CutOp("spine", n, (0.3, 0.3, 0.3), (1,), offset=(0.0, 0.062, 0.0), under=(0,),
                          press=(0.004, 0.02, 0.0015, 0.001, (0.0, -0.5, 0.0)), trim=(0.003, 0.6, 8, (0.0, 0.0, 0.1, 1.0)))
    spec = mesh_edit.MeshSpec(ops=(cut,))
    out, got = mesh_edit._cut(mesh, spec, base)
    P = np.array(got)
    side = lambda q: (q[0] - 0.0) * n[0] + (q[2] - 1.3) * n[2]      # noqa: E731
    cloth = [t for t in out.triangles if out.ids[t[0]][0] == 1 and not out.fixed.intersection(t)]
    assert len(cloth) < sum(1 for t in mesh.triangles if mesh.ids[t[0]][0] == 1)
    assert max(side(P[v]) for t in cloth for v in t) <= mesh_edit.CUT_SNAP
    edge = sorted(dict(out.cuts)[0])
    assert len(edge) > 10 and max(abs(side(P[v])) for v in edge) <= mesh_edit.CUT_SNAP
    assert all(abs(out.uvs[v][0] - (P[v, 0] + 0.25) / 0.5) < 1e-6 and abs(out.uvs[v][1] - (P[v, 2] - 1.15) / 0.3) < 1e-6
               for v in edge)
    skin = [k for k, (g, _) in enumerate(out.ids) if g == 0]
    assert all(got[k] == base[k] for k in skin)
    final = list(got)
    mesh_edit._press(out, spec, final)
    mesh_edit._ride(out, final)
    F = np.array(final)
    at_edge = [v for v in edge]
    assert all(abs(math.dist(P[v], F[v]) - 0.004 - (0.002 * math.dist(P[v], (0.0, -0.5, 1.3)) / (P[v, 1] + 0.5) - 0.001))
               < 1e-4 for v in at_edge)        # 4 mm and the 2 mm gap (along the way in) less thick
    bare = [k for k in skin if side(P[k]) > 0.0]
    lift = max(F[k, 1] - P[k, 1] for k in bare)
    assert 0.0008 < lift <= 0.0015 + 1e-9
    far = [k for k in skin + [v for t in cloth for v in t] if min(math.dist(P[k], P[e]) for e in edge) > 0.0451]
    assert far and all(final[k] == got[k] for k in far)
    cord = [k for k, _, _ in out.trims]
    assert cord and all(min(math.dist(F[k], F[e]) for e in edge) < 0.0035 for k in cord)
    assert all(np.dot(mesh_edit._face(final, t), np.subtract(np.mean([final[v] for v in t], 0),
                                                             F[min(edge, key=lambda e: math.dist(F[e], np.mean([final[v] for v in t], 0)))]))
               > -1e-12 for t in out.triangles if out.fixed.intersection(t))

def test_a_cut_with_a_uv_box_drops_only_the_triangles_laid_in_it():
    """Step 2.154 round 9 (D552: a strand vanilla modelled as a fin of her face's skin, ended above her brow): a ``cut``
    with a ``uv`` box drops past its plane only the layer's triangles whose corners' UVs lie in the box (the cloth's
    right half, x > 0), and keeps the rest of the layer past it."""
    mesh = _chest()
    n = (0.0, 0.0, 1.0)
    cut = mesh_edit.CutOp("spine", n, (0.3, 0.3, 0.3), (1,), offset=(0.0, 0.062, 0.0), uv=(0.5, 0.0, 1.0, 1.0))
    out, got = mesh_edit._cut(mesh, mesh_edit.MeshSpec(ops=(cut,)), list(mesh.positions))
    past = [t for t in out.triangles if out.ids[t[0]][0] == 1 and min(got[v][2] for v in t) > 1.3 + mesh_edit.CUT_SNAP]
    assert past and all(max(got[v][0] for v in t) <= 1e-6 for t in past)
    assert sum(1 for t in mesh.triangles if mesh.ids[t[0]][0] == 1) > sum(1 for t in out.triangles if out.ids[t[0]][0] == 1)

def test_a_round_pair_moves_its_midline_with_its_neighbours_and_tapers_its_outer_side():
    """Step 2.154 rounds 3 and 4 (D438): on the flat chest, a mirrored ``round`` with ``pair`` moves every point along
    one ray from an origin on x = 0 (here behind the forms, inside their ``back`` half axis) to the two forms' smooth
    union: x = 0 stays on x = 0 and moves as far as its neighbours (the averaged moves of a plain mirrored pair leave it
    behind: a slit); ``taper`` narrows the upper pole on the armpit's side only, ``taper_back`` the outer side behind
    the centre and ``taper_low`` the lower pole's, the side by x = 0 kept; ``midline`` fades the move by x = 0 below
    its height and leaves the rest as it was."""
    mesh = _chest()
    base = list(mesh.positions)
    P = np.array(base)
    skin = np.array([g == 0 for g, _ in mesh.ids])

    def final(**kw) -> np.ndarray:
        op = mesh_edit.RoundOp("spine", (0.12, 0.12, 0.10, 0.10), kw.pop("origin", 0.06), (0.03, 0.02),
                               offset=(0.08, 0.10, 0.05), mirror=True, groups=(0,), name="breast right", **kw)
        rounds = mesh_edit._rounds(mesh, mesh_edit.MeshSpec(ops=(op,)))
        return np.array([mesh_edit._round_all(p, rounds, 0, 0) for p in base])

    def kept(out: np.ndarray) -> float:
        """How far x = 0 comes forward at z 1.35 as a share of its neighbours' 1.25 cm out."""
        row = skin & (np.abs(P[:, 2] - 1.35) < 1e-3)
        mid = out[row & (np.abs(P[:, 0]) < 1e-6), 1].max() - 0.06
        near = out[row & (np.abs(np.abs(P[:, 0]) - 0.0125) < 1e-3), 1].mean() - 0.06
        return mid / near
    plain = final()
    paired = final(pair=True, origin=0.16, back=0.25, bridge=0.04)
    middle = np.where(np.abs(P[:, 0]) < 1e-6)[0]
    assert np.abs(paired[middle, 0]).max() < 1e-9
    assert kept(plain) < 0.8 and kept(paired) > 0.9 and paired[middle, 1].max() > 0.15
    tapered = final(pair=True, origin=0.16, back=0.25, bridge=0.04, taper=0.5)
    high = skin & (P[:, 2] > 1.42) & (P[:, 2] < 1.44)
    moved = lambda out: np.abs(out[:, 1] - P[:, 1]) > 1e-4      # noqa: E731
    outer = lambda out: np.abs(out[high & moved(out), 0]).max()   # noqa: E731
    inner = lambda out: out[high & moved(out) & (P[:, 0] > 0), 0].min()   # noqa: E731
    assert outer(tapered) < outer(paired) - 0.01 and abs(inner(tapered) - inner(paired)) < 0.005
    centre, low = skin & (np.abs(P[:, 2] - 1.35) < 1e-3), skin & (np.abs(P[:, 2] - 1.275) < 1e-3)
    near = np.abs(P[:, 0]) < 0.04
    for kw, row in (({"taper_back": (0.4, 0.10)}, centre), ({"taper_low": (0.3, 0.0)}, low)):
        narrowed = final(pair=True, origin=0.16, back=0.25, bridge=0.04, **kw)
        widest = lambda out: np.abs(out[row & moved(out), 0]).max()     # noqa: E731
        assert widest(narrowed) < widest(paired) - 0.01, kw
        assert np.abs(narrowed[row & near] - paired[row & near]).max() < 0.001, kw
    faded = final(pair=True, origin=0.16, back=0.25, bridge=0.04, midline=(1.25, 1.33, 0.03))
    mid = low & (np.abs(P[:, 0]) < 1e-6)
    assert (faded[mid, 1] - P[mid, 1]).max() < 0.4 * (paired[mid, 1] - P[mid, 1]).max()
    assert np.array_equal(faded[np.abs(P[:, 0]) >= 0.03], paired[np.abs(P[:, 0]) >= 0.03])
    # round 9 (D550, D548): a midline's fade behind a y only (this skin lies in front of it: no fade), and a lower
    # blend of its own by x = 0 (the move changes within its x full, none past its x none)
    assert np.array_equal(final(pair=True, origin=0.16, back=0.25, bridge=0.04, midline=(1.25, 1.33, 0.03, 0.0)), paired)
    assert np.array_equal(final(pair=True, origin=0.16, back=0.25, bridge=0.04, midline=(1.25, 1.33, 0.03, 0.03, 0.02)),
                          paired)       # its span: this skin 1 cm past the fade's front reach (0.03 + 0.02) is past it too
    half = final(pair=True, origin=0.16, back=0.25, bridge=0.04, midline=(1.25, 1.33, 0.03, 0.06, 0.02))
    assert 0.0 < (half[mid, 1] - faded[mid, 1]).max() < (paired[mid, 1] - faded[mid, 1]).max()   # half faded at y 0.06
    long = final(pair=True, origin=0.16, back=0.25, bridge=0.04, inner_blend=(0.06, 0.02, 0.04))
    assert np.array_equal(long[np.abs(P[:, 0]) >= 0.04], paired[np.abs(P[:, 0]) >= 0.04])
    assert np.abs(long[np.abs(P[:, 0]) <= 0.02] - paired[np.abs(P[:, 0]) <= 0.02]).max() > 1e-4
    # round 11 (D606, D607): ``behind`` keeps the move behind a depth (this skin, y 0.06, behind 0.07: all of it; in
    # front of 0.04: none; halfway across 0.05-0.07: half, times its share), ``window`` to its heights
    assert np.array_equal(final(pair=True, origin=0.16, back=0.25, bridge=0.04, behind=(0.07, 0.09, 1.0, ())), paired)
    assert np.array_equal(final(behind=(0.02, 0.04, 1.0, ())), P)
    assert np.allclose(final(behind=(0.05, 0.07, 0.6, ()))[skin] - P[skin], 0.3 * (plain - P)[skin], atol=1e-6)
    # round 11b: swapped, the move kept in front of y full (this skin in front of 0.05: all of it; behind 0.07: none)
    assert np.array_equal(final(behind=(0.05, 0.03, 1.0, ())), plain)
    assert np.array_equal(final(behind=(0.09, 0.07, 1.0, ())), P)
    assert np.allclose(final(behind=(0.07, 0.05, 0.6, ()))[skin] - P[skin], 0.3 * (plain - P)[skin], atol=1e-6)
    tilted = final(behind=(-0.005, 0.005, 1.0, ((1.30, 0.05), (1.40, 0.07))))   # the depths from a line through y 0.06
    below, above = skin & (P[:, 2] < 1.30), skin & (P[:, 2] > 1.40)    # level past its ends: 1 cm in front, 1 cm behind
    assert np.array_equal(tilted[below], P[below]) and np.array_equal(tilted[above], plain[above])
    kept = final(window=(1.30, 1.32, 1.38, 1.40))
    out_z, in_z = (P[:, 2] < 1.30) | (P[:, 2] > 1.40), (P[:, 2] >= 1.32) & (P[:, 2] <= 1.38)
    assert np.array_equal(kept[out_z], P[out_z]) and np.array_equal(kept[in_z], plain[in_z])
    assert np.abs(plain[out_z] - P[out_z]).max() > 1e-3

def test_a_relax_smooths_its_region_keeping_its_midline_and_its_open_edges():
    """Step 2.154 round 3 (D438): ``relax`` on a rough patch of the chest's skin and cloth smooths it (each point's
    distance from its neighbours' mean falls), a point on x = 0 stays on it, the cloth's open edge (its top hem) and
    everything outside the region stay put."""
    mesh = _chest()
    base = list(mesh.positions)
    rough = [(p[0], p[1] + (0.004 if (round(p[0] / 0.0125) + round(p[2] / 0.0125)) % 2 else -0.004), p[2])
             if abs(p[2] - 1.35) < 0.08 and abs(p[0]) < 0.1 else p for p in base]
    op = mesh_edit.RelaxOp("spine", (0.15, 0.2, 0.12), 20, offset=(0.0, 0.06, 0.05), groups=(0, 1))
    final = list(rough)
    moved = mesh_edit._relax(mesh, mesh_edit.MeshSpec(ops=(op,)), base, final)
    P, R, F = np.array(base), np.array(rough), np.array(final)
    patch = (np.abs(P[:, 2] - 1.35) < 0.03) & (np.abs(P[:, 0]) < 0.05)
    assert moved > 100 and np.abs(F[patch, 1] - 0.06).max() < 0.4 * np.abs(R[patch, 1] - 0.06).max() + 0.002
    assert np.abs(F[np.abs(P[:, 0]) < 1e-6, 0]).max() == 0.0
    top = np.array([g == 1 for g, _ in mesh.ids]) & (np.abs(P[:, 2] - 1.45) < 1e-4)
    assert (F[top] == R[top]).all()
    far = (np.abs(P[:, 2] - 1.35) > 0.13) | (np.abs(P[:, 0]) > 0.16)
    assert (F[far] == R[far]).all()

def test_an_island_lays_its_region_into_its_rect_and_an_atlas_the_rest_into_its_own():
    """Step 2.154 round 3 (D456): a mirrored ``island`` on the chest's skin cuts each side's triangles off as their own
    UV island (no vertex shared with a triangle outside it, the two sides apart at x = 0, its corners' source UVs
    kept), laid inside its own rect; an ``atlas`` lays every other UV of the groups into its rect."""
    mesh = _chest()
    island = mesh_edit.IslandOp("spine", (0.12, 0.2, 0.15), ((0.5, 0.0, 1.0, 0.5), (0.0, 0.5, 0.5, 1.0)),
                                offset=(0.08, 0.06, 0.05), mirror=True, groups=(0,))
    atlas = mesh_edit.AtlasOp((0, 1), (0.0, 0.0, 0.5, 0.5))
    spec = mesh_edit.MeshSpec(ops=(island, atlas))
    out, base = mesh_edit._split_islands(mesh, spec, list(mesh.positions))
    side = mesh_edit._island_of(out, spec, base)
    assert len(out.ids) > len(mesh.ids) and {0, 1} <= set(side)
    users: dict[int, set] = {}
    for t, i in zip(out.triangles, side):
        for v in t:
            users.setdefault(v, set()).add(i)
    assert all(len(u) == 1 for u in users.values())
    assert all(c == tuple(mesh.uvs[v] for v in t) for c, t in zip(out.corners[:len(mesh.triangles)], mesh.triangles))
    uvs = mesh_edit._island_uvs(out, spec, base, base)
    laid = dict(uvs)
    groups = mesh_edit._atlas(out, spec, uvs, laid)
    assert groups == (0, 1)
    for t, i in zip(out.triangles, side):
        u0, v0, u1, v1 = ((0.5, 0.0, 1.0, 0.5), (0.0, 0.5, 0.5, 1.0), (0.0, 0.0, 0.5, 0.5))[i]
        assert all(u0 <= uvs[v][0] <= u1 and v0 <= uvs[v][1] <= v1 for v in t)

def test_an_island_with_a_uv_box_keeps_vanillas_layout_stretched_onto_its_rect():
    """Step 2.154 round 8 (D552, her face's few texels): an ``island`` with a ``uv`` box takes only the triangles whose
    corners' UVs lie in it, keeps their layout stretched by one map from the box onto its rect (inside the margin),
    splits off only the vertices other triangles use too (a seam round it, none inside), and leaves every other UV."""
    mesh = _sheet()
    island = mesh_edit.IslandOp("a", (0.3, 0.1, 0.3), ((0.5, 0.5, 1.0, 1.0),), offset=(0.0, 0.06, 0.0), groups=(0,),
                                uv=(0.25, 0.25, 0.75, 0.75))
    spec = mesh_edit.MeshSpec(ops=(island,))
    out, base = mesh_edit._split_islands(mesh, spec, list(mesh.positions))
    side = mesh_edit._island_of(out, spec, base)
    inside = [t for t, i in zip(out.triangles, side) if i == 0]
    assert len(inside) == 2 * 16 * 16
    rim = {v for t in inside for v in t} & {v for t, i in zip(out.triangles, side) if i < 0 for v in t}
    assert not rim and len(out.ids) == len(mesh.ids) + 4 * 16
    uvs = mesh_edit._island_uvs(out, spec, base, base)
    m = mesh_edit.ISLAND_MARGIN / 4
    for v in {v for t in inside for v in t}:
        u0, v0 = out.uvs[v]
        assert uvs[v] == pytest.approx((0.5 + m + (u0 - 0.25) * (1 - 4 * m), 0.5 + m + (v0 - 0.25) * (1 - 4 * m)), abs=1e-6)
    assert set(uvs) == {v for t in inside for v in t}

def test_a_tube_makes_skinned_geometry_facing_out_with_shares_rising_along_it():
    """Step 2.154 round 3 (D485, D488): a ``tube`` adds ``rings`` rings of ``sides`` + 1 points (a UV seam) and a tip
    to its group, every triangle facing away from the curve, its UVs in its rect, its weights its bone's (no other op
    moves them: fixed), and ``segments`` named shares that are 0 at its root and rise to the last one's 1 at its tip."""
    mesh = _chest()
    tube = mesh_edit.TubeOp("spine", ((0.0, -0.1, 0.3), (0.0, -0.15, 0.2), (0.0, -0.16, 0.0)), (0.02, 0.03, 0.01),
                            1, (0.1, 0.1, 0.3, 0.5), sides=8, rings=6, segments=2, name="tail")
    out, base = mesh_edit._generate(mesh, mesh_edit.MeshSpec(ops=(tube,)), list(mesh.positions))
    made = range(len(mesh.ids), len(out.ids))
    assert len(made) == 6 * 9 + 1 and set(made) == set(out.fixed)
    assert all(out.ids[k][0] == 1 and out.skins[k] == {0: 1.0} for k in made)
    assert all(0.1 <= out.uvs[k][0] <= 0.3 and 0.1 <= out.uvs[k][1] <= 0.5 for k in made)
    new = out.triangles[len(mesh.triangles):]
    rings = np.array([np.mean([base[len(mesh.ids) + r * 9 + c] for c in range(8)], 0) for r in range(6)])
    for t in new:
        a, b, c = (np.array(base[v]) for v in t)
        centre = (a + b + c) / 3
        nearest = rings[np.argmin(np.linalg.norm(rings - centre, axis=1))]
        assert np.cross(b - a, c - a) @ (centre - nearest) > -1e-9
    shares = dict(out.segments)
    assert set(shares) == {"tail 1", "tail 2"}
    root = [k for k in made if base[k][2] > 1.59]
    tip = max(made, key=lambda k: -base[k][2])
    assert all(k not in shares["tail 1"] and k not in shares["tail 2"] for k in root)
    assert shares["tail 2"][tip] == 1.0
    assert all(shares["tail 1"].get(k, 0.0) + shares["tail 2"].get(k, 0.0) <= 1.0 + 1e-12 for k in made)

def test_a_faceted_tube_gives_each_face_its_own_corners_with_the_face_normal():
    """Step 2.154 round 8 (D533: "a small faceted gem"): with ``facets`` each of a tube's triangles has three vertices
    of its own whose normal is its face's (facing out), so it shades flat; its shape, UV rect and named shares as a
    smooth tube's."""
    mesh = _chest()
    path, radius = ((0.0, 0.2, 0.1), (0.0, 0.21, 0.1), (0.0, 0.22, 0.1)), (0.004, 0.008, 0.004)
    smooth = mesh_edit.TubeOp("spine", path, radius, 1, (0.1, 0.1, 0.3, 0.5), sides=8, rings=3, segments=1, name="gem")
    cut = replace(smooth, facets=True)
    out_s, base_s = mesh_edit._generate(mesh, mesh_edit.MeshSpec(ops=(smooth,)), list(mesh.positions))
    out, base = mesh_edit._generate(mesh, mesh_edit.MeshSpec(ops=(cut,)), list(mesh.positions))
    new = out.triangles[len(mesh.triangles):]
    made = range(len(mesh.ids), len(out.ids))
    assert len(new) == len(out_s.triangles) - len(mesh.triangles) and len(made) == 3 * len(new)
    assert sorted(v for t in new for v in t) == list(made) and set(made) == set(out.fixed)
    assert np.allclose(sorted(map(tuple, np.round(base[len(mesh.ids):], 9))),
                       sorted(map(tuple, np.round([base_s[v] for t in out_s.triangles[len(mesh.triangles):] for v in t], 9))))
    for t in new:
        a, b, c = (np.array(base[v]) for v in t)
        n = np.cross(b - a, c - a)
        n /= np.linalg.norm(n)
        assert all(np.allclose(out.normals[v], n) for v in t)
        centre = (a + b + c) / 3
        assert n @ (centre - np.array((0.0, centre[1], 1.4))) > -1e-9      # facing out of its axis
    assert all(0.1 <= out.uvs[k][0] <= 0.3 and 0.1 <= out.uvs[k][1] <= 0.5 for k in made)
    assert set(dict(out.segments)) == {"gem 1"} and max(dict(out.segments)["gem 1"].values()) == 1.0

def _two_sided(n: int = 4, step: float = 0.05) -> mesh_edit._Mesh:
    """A sheet of no thickness facing both ways (y = 0.06, x -0.1..0.1, z 1.2..1.4), one bone at (0, 0, 1.3): its
    front copies facing +y, then its back copies at the same places facing -y (their triangles wound the other way)."""
    from azurkit.tools.characters.characters import MeshGroup
    pos, nrm, tris = [], [], []
    for side, ny in ((0, 1.0), (1, -1.0)):
        first = len(pos)
        for j in range(n + 1):
            for i in range(n + 1):
                pos.append(mesh_edit._f32((-0.1 + i * step, 0.06, 1.2 + j * step)))
                nrm.append((0.0, ny, 0.0))
        for j in range(n):
            for i in range(n):
                a = first + j * (n + 1) + i
                quad = [(a, a + n + 2, a + 1), (a, a + n + 1, a + n + 2)]      # facing +y
                tris += quad if side == 0 else [(t[0], t[2], t[1]) for t in quad]
    k = len(pos)
    return mesh_edit._Mesh("cloth", 1, (MeshGroup(0, 0, (0,), 0, 0, k),), tuple((0, j) for j in range(k)),
                           tuple(struct.pack("<3f", *q) for q in pos), tuple(pos), tuple(nrm),
                           tuple((q[0], q[2]) for q in pos), ({0: 1.0},) * k, (0,) * k, tuple(tris), ("root",), (-1,),
                           ((0.0, 0.0, 1.3),), ((1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, -1.3, 1.0),))

def test_a_thickened_layers_sides_end_its_depth_apart_and_rims_close_its_open_edges_facing_out():
    """Step 2.177d (D698: her sash's folds and hem edges a sheet of no thickness): a ``thicken`` op moves each side of
    a two-sided layer half its ``depth`` along its own normal, so the copies of a point end ``depth`` apart, and joins
    every edge the two sides leave open together by two triangles facing out of the layer, none over its inner edges."""
    mesh = _two_sided()
    spec = mesh_edit.MeshSpec(ops=(mesh_edit.ThickenOp("root", (1.0, 1.0, 1.0), 0.004, offset=(0.0, 0.06, 0.0)),))
    base = list(mesh.positions)
    out = mesh_edit._rims(mesh, spec, base)
    rims = out.triangles[len(mesh.triangles):]
    assert len(rims) == 2 * 16 and out.ids == mesh.ids
    final = list(base)
    mesh_edit._thicken(out, spec, base, final)
    half = len(base) // 2
    assert all(abs(final[k][1] - 0.062) < 1e-8 and abs(final[k + half][1] - 0.058) < 1e-8 for k in range(half))
    assert all(final[k][0] == base[k][0] and final[k][2] == base[k][2] for k in range(len(base)))
    for t in rims:
        f = np.array(mesh_edit._face(final, t))
        centre = np.mean([final[v] for v in t], 0)
        assert f @ (centre - np.array((0.0, 0.06, 1.3))) > 0 and abs(f[1]) < 1e-12
        assert {mesh.normals[v][1] for v in t} == {1.0, -1.0}

def test_a_late_scale_moves_the_skin_last_and_tells_the_rig_its_moves():
    """Step 2.187 (D725, AZ-734: her skin showed through her top's strap by her neck, and any move of it shifted her
    breast bones, which her clips' rests hold): a ``late`` scale is no field: the position step leaves the shape as
    without it (the binds, tubes and UVs read that) and returns its moves, its displacement at each vertex it selects
    there, which the plan adds last and W29 takes back off before it places its jiggle bones; its cloth untouched."""
    mesh = _chest(step=0.025)
    lift = mesh_edit.PushOp("spine", (0.0, 1.0, 0.0), 0.004, (0.1, 0.1, 0.1, 0.1), 0.05, offset=(0.0, 0.06, 0.0))
    dent = mesh_edit.ScaleOp("spine", (0.1, 0.03, 0.1), (1.0, 0.5, 1.0), offset=(0.0, 0.05, 0.0), profile="smooth",
                             groups=(0,), late=True)
    base = list(mesh.positions)
    fielded, *_ = mesh_edit._positions(mesh, base, mesh_edit.MeshSpec(ops=(lift,)))
    final, placed, *_, late = mesh_edit._positions(mesh, base, mesh_edit.MeshSpec(ops=(lift, dent)))
    assert placed == 1 and final == fielded and late and all(mesh.ids[k][0] == 0 for k in late)
    side = mesh_edit._place(mesh, mesh_edit.MeshSpec(ops=(replace(dent, late=False),)))[0]
    for k, p in enumerate(fielded):
        want = mesh_edit._effect(p, side)
        d = (0.0, 0.0, 0.0) if want is None or mesh.ids[k][0] != 0 else want[0]
        assert np.allclose(late.get(k, (0.0, 0.0, 0.0)), d, atol=1e-12)
    moved = mesh_edit._moved(fielded, late)
    assert min(q[1] - p[1] for p, q in zip(fielded, moved)) < -0.002     # the skin under the lifted cloth went deeper

def test_a_tapered_thickening_ends_flush_where_its_layer_meets_the_cloth_it_leaves_thin():
    """Step 2.187 (D724, AZ-735: a step showed below her belt where her sash's thick part began): with a ``taper``
    each point's depth eases in by a smoothstep of its distance to the layer's points a triangle outside it shares,
    so its copies there stay together and unmoved, a point the taper's length away or more is the full depth apart,
    one between is the eased share of it, and no rim closes an edge whose ends don't move (none of no area)."""
    mesh = _two_sided()
    op = mesh_edit.ThickenOp("root", (1.0, 1.0, 0.1), 0.004, offset=(0.0, 0.06, -0.1), taper=0.075)
    spec = mesh_edit.MeshSpec(ops=(op,))      # rows z 1.2-1.3 thickened, their top edge at z = 1.3 shared with z 1.3-1.4
    base = list(mesh.positions)
    out = mesh_edit._rims(mesh, spec, base)
    rims = out.triangles[len(mesh.triangles):]
    final = list(base)
    mesh_edit._thicken(out, spec, base, final)
    half, s = len(base) // 2, 0.05 / 0.075
    for k in range(half):
        z, front, back = base[k][2], final[k][1] - 0.06, final[k + half][1] - 0.06
        want = 0.002 if z < 1.21 else 0.002 * s * s * (3 - 2 * s) if z < 1.26 else 0.0
        assert abs(front - want) < 1e-8 and abs(back + want) < 1e-8, (z, front, back)
    assert all(final[k] == base[k] for k in range(len(base)) if base[k][2] > 1.29)
    assert len(rims) == 4 * 2 + 4 * 2 - 2     # the hem's 4 edges and the sides' 4, none along the top edge, one
    for t in rims:                            # triangle each where a side edge meets it
        f = np.array(mesh_edit._face(final, t))
        assert np.linalg.norm(f) > 1e-9 and max(base[v][2] for v in t) <= 1.3 + 1e-9
        assert f @ (np.mean([final[v] for v in t], 0) - np.array((0.0, 0.06, 1.25))) > 0

def test_a_tube_fades_onto_a_bone_along_it_and_takes_the_weights_where_the_ops_put_its_skin():
    """Step 2.154 round 6 (D512): a ponytail lying on her back and a necklace on her chest.  ``fade`` eases a tube's
    weights from its bone at its root to the fade's bone at its tip over that share of its length (so its tip moves
    with the back); ``reach`` gives each vertex the ``follow`` groups' weights where they are in the final shape (a
    necklace on a form the ops moved far from its base: the base's nearest vertex lay elsewhere), each sum 1."""
    chest = _chest()
    mesh = replace(chest, names=("spine", "neck"), parents=(-1, 0), origins=((0.0, 0.0, 1.3), (0.0, 0.0, 1.5)),
                   binds=chest.binds * 2)
    tail = mesh_edit.TubeOp("neck", ((0.0, -0.1, 0.1), (0.0, -0.15, 0.0), (0.0, -0.16, -0.2)), (0.02, 0.03, 0.01),
                            1, (0.1, 0.1, 0.3, 0.5), sides=8, rings=9, fade=("spine", 0.3, 0.9))
    out, base = mesh_edit._generate(mesh, mesh_edit.MeshSpec(ops=(tail,)), list(mesh.positions))
    rows = [[len(mesh.ids) + r * 9 + c for c in range(9)] for r in range(9)]
    on_spine = [out.skins[row[0]].get(0, 0.0) for row in rows]
    assert on_spine[0] == 0.0 and on_spine[-1] == 1.0 and all(b >= a for a, b in zip(on_spine, on_spine[1:]))
    assert all(abs(sum(out.skins[k].values()) - 1.0) < 1e-12 for row in rows for k in row)
    skins = tuple({1: 1.0} if p[0] > 0.0 else {0: 1.0} for p in chest.positions)   # the skin's halves on two bones
    mesh = replace(mesh, skins=skins)
    chain = mesh_edit.TubeOp("spine", ((-0.1, 0.0631, 0.05), (0.1, 0.0631, 0.05)), (0.001, 0.001), 1,
                             (0.0, 0.0, 1.0, 1.0), sides=8, rings=9, follow=(0,), reach=0.03)
    spec = mesh_edit.MeshSpec(ops=(chain,))
    out, base = mesh_edit._generate(mesh, spec, list(mesh.positions))
    made = {i: vs for i, vs, _ in out.tubes}[0]
    got = mesh_edit._tube_weights(out, spec, base, {})
    assert set(got) == set(made) and all(abs(sum(w.values()) - 1.0) < 1e-12 for w in got.values())
    mid = [k for k in made if abs(base[k][0]) < 0.002]
    assert mid and all(out.skins[k] in ({0: 1.0}, {1: 1.0}) for k in mid) and all(0.2 < got[k][1] < 0.8 for k in mid)
    moved = [(p[0] - 0.15, p[1], p[2]) if g == 0 else p for p, (g, _) in zip(base, out.ids)]    # bone 1's half under it
    got = mesh_edit._tube_weights(out, spec, moved, {})
    assert all(got[k] == {1: 1.0} for k in made if base[k][0] > -0.07)
    # round 11 (D605): a reach a path point, along it as its radius (a chain's shoulder runs on the skin right under
    # them): none at x -0.1 (its nearest alone), 6 cm at +0.1, so at x +0.04 (4.2 cm) bone 0's half is in its mix
    spec = mesh_edit.MeshSpec(ops=(replace(chain, reach=(0.0, 0.06)),))
    out, base = mesh_edit._generate(mesh, spec, list(mesh.positions))
    (_, made, reach), = out.tubes
    got = mesh_edit._tube_weights(out, spec, base, {})
    assert min(reach) == 0.0 and abs(max(reach) - 0.06) < 1e-12
    assert all(got[k] == {0: 1.0} for k in made if base[k][0] < -0.09)
    assert all(0.0 < got[k].get(0, 0.0) < 0.5 for k in made if abs(base[k][0] - 0.04) < 0.003)
    # round 11b: ``smooth`` low-passes those weights along the rings (sigma 0 at x -0.1 to 2 cm at +0.1): each ring's
    # points alike, bone 1's share rising along x with no step, the sigma-0 ring its points' own; a smooth with no
    # reach or with facets is refused
    sharp = mesh_edit.MeshSpec(ops=(replace(chain, reach=0.005),))
    spec = mesh_edit.MeshSpec(ops=(replace(chain, reach=0.005, smooth=(0.0, 0.02)),))
    out, base = mesh_edit._generate(mesh, spec, list(mesh.positions))
    (_, made, _), = out.tubes
    before, got = mesh_edit._tube_weights(out, sharp, base, {}), mesh_edit._tube_weights(out, spec, base, {})
    rings = [made[r * 9:(r + 1) * 9] for r in range(9)]
    assert all(got[k] == before[k] for k in rings[0]) and all(abs(sum(w.values()) - 1.0) < 1e-12 for w in got.values())
    assert all(got[k] == got[ring[0]] for ring in rings[1:] for k in ring)
    share = [got[ring[0]].get(1, 0.0) for ring in rings[1:]]
    assert all(b >= a for a, b in zip(share, share[1:])) and 0.0 < share[3] < 1.0
    for bad in (replace(chain, reach=0.0, smooth=0.01), replace(chain, smooth=0.01, facets=True)):
        with pytest.raises(ValueError, match=r"smooth: low-passes a reach's weights"):
            mesh_edit._generate(mesh, mesh_edit.MeshSpec(ops=(bad,)), list(mesh.positions))
    # ``under``: that share of each ring's weights the follow surface's right under its centre (barycentric), the rest
    # the reach's: a 6 cm reach mixes both halves near the middle, under 1 gives every ring off it its own half's bone
    wide = replace(chain, reach=0.06)
    out, base = mesh_edit._generate(mesh, mesh_edit.MeshSpec(ops=(replace(wide, under=1.0),)), list(mesh.positions))
    (_, made, _), = out.tubes
    mixed, got, half = (mesh_edit._tube_weights(out, mesh_edit.MeshSpec(ops=(replace(wide, under=u),)), base, {})
                        for u in (0.0, 1.0, 0.5))
    far = [k for k in made if abs(base[k][0]) > 0.03]
    assert far and all(0.0 < mixed[k].get(0, 0.0) < 1.0 for k in far if abs(base[k][0]) < 0.05)
    assert all(got[k] == ({1: 1.0} if base[k][0] > 0 else {0: 1.0}) for k in far)
    assert all(abs(half[k].get(1, 0.0) - (mixed[k].get(1, 0.0) + got[k].get(1, 0.0)) / 2) < 1e-12 for k in made)
    with pytest.raises(ValueError, match=r"under: mixes the surface under"):
        mesh_edit._generate(mesh, mesh_edit.MeshSpec(ops=(replace(chain, reach=0.0, under=1.0),)), list(mesh.positions))
    # a recipe's tube carries both, one number or one a path point (round 11b's review: P3's chain fix)
    from azurkit.tools.characters._player_variants import _mesh_op
    tube = {"op": "tube", "bone": "spine", "path": [[-0.1, 0.0631, 0.05], [0.1, 0.0631, 0.05]], "radius": [0.001] * 2,
            "group": 1, "rect": [0.0, 0.0, 1.0, 1.0], "follow": [0], "reach": 0.03}
    parsed = _mesh_op("op", {**tube, "smooth": 0.01, "under": [0.0, 0.5], "skip": ["neck"]})
    assert (parsed.smooth, parsed.under, parsed.skip) == (0.01, (0.0, 0.5), ("neck",))
    # Step 2.154b: ``skip`` gives a bone's share to its nearest ancestor not skipped (a chain kept off her arm), and
    # refuses a root bone
    spec = mesh_edit.MeshSpec(ops=(replace(wide, skip=("neck",)),))
    out, base = mesh_edit._generate(mesh, spec, list(mesh.positions))
    (_, made, _), = out.tubes
    assert all(set(w) == {0} and abs(w[0] - 1.0) < 1e-12 for w in mesh_edit._tube_weights(out, spec, base, {}).values())
    with pytest.raises(ValueError, match=r"skip: bones of .* with a parent, on a tube with a reach"):
        mesh_edit._generate(mesh, mesh_edit.MeshSpec(ops=(replace(wide, skip=("spine",)),)), list(mesh.positions))

def test_hung_tubes_take_one_weight_set_after_the_reskin_and_the_bones_keep_their_places():
    """Step 2.168r (its looks judge's F1: her gem, lying across her cleavage, took each breast on its own side and
    stretched into a rod as they moved apart): W29 gives every vertex of the tubes a recipe hangs under one name
    (``hang``) one weight set after the reskin, the mean of theirs, its four heaviest bones renormalized, so the
    pendant moves as one piece; their shares (and so the bones' places) are their own vertices' as before; a recipe's
    tube carries the name, only with a reach."""
    from azurkit.tools.characters import body_codec
    from azurkit.tools.characters.jiggle import _hang, _ridden, _slot_byte
    from azurkit.tools.characters._player_variants import _mesh_op

    tube = {"op": "tube", "bone": "spine", "path": [[-0.1, 0.0631, 0.05], [0.1, 0.0631, 0.05]], "radius": [0.001] * 2,
            "group": 1, "rect": [0.0, 0.0, 1.0, 1.0], "follow": [0], "reach": 0.03, "hang": "pendant"}
    assert _mesh_op("op", tube).hang == "pendant"
    with pytest.raises(ValueError, match=r"hang: W29 hangs a tube that rides the skin as one piece"):
        _mesh_op("op", {**tube, "reach": 0.0})
    # her pendant across two breasts (bones 7 and 8 of the palette's 5..9): each vertex its own side's, and a squish
    # (9) on a few; one vertex of another tube, not hung, keeps its own
    v = body_codec.Vertex((0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0))
    rows = [{7: 0.8, 5: 0.2}, {8: 0.8, 5: 0.2}, {7: 0.5, 8: 0.3, 5: 0.1, 9: 0.1}, {8: 0.9, 6: 0.1}, {7: 1.0}]
    palette = [5, 6, 7, 8, 9]
    pad = [[0] * (4 - len(r)) for r in rows]
    group = body_codec.Group(palette, [replace(v, weights=tuple([*r.values(), *pad[k]]),
                                               slots=tuple([*(_slot_byte(palette.index(b)) for b in r), *pad[k]]))
                                       for k, r in enumerate(rows)], [], (0, 0))
    riders = {(0, k): ((1, 4), 0.035, "pendant") for k in range(4)} | {(0, 4): ((1, 4), 0.035, "")}
    _hang([group], riders)
    sets = {tuple(zip(group.vertices[k].weights, group.vertices[k].slots)) for k in range(4)}
    assert len(sets) == 1 and group.vertices[4].weights[0] == 1.0
    mean = {5: 0.125, 6: 0.025, 7: 0.325, 8: 0.5, 9: 0.025}      # the four heaviest: 6 and 9 tie, 6 the lower bone
    got = {palette[body_codec.code_entry(s)]: w for w, s in zip(group.vertices[0].weights, group.vertices[0].slots)
           if w > 0}
    assert set(got) == {5, 6, 7, 8} and abs(sum(got.values()) - 1.0) < 1e-6
    assert all(abs(got[b] - mean[b] / 0.975) < 1e-6 for b in got)
    # the shares: a hung rider's own place, as before (the name rides along)
    plain = {(1, i): (-0.05 + 0.005 * i, 0.06, 1.35) for i in range(21)} | {(0, 0): (-0.04, 0.0631, 1.35)}
    mine = {vid: 1.0 for vid, p in plain.items() if p[0] < 0.0}
    assert _ridden({(0, 0): ((1,), 0.03, "pendant")}, mine, plain, {1}) == _ridden({(0, 0): ((1,), 0.03, "")}, mine,
                                                                                   plain, {1})

@pytest.mark.parametrize("grid", [False, True])
def test_a_nearest_search_gives_the_full_scans_vertex_ties_and_float_rounding_included(monkeypatch, grid):
    """Step X.63: a follow tube's and a jiggle cloth's nearest vertex (``mesh_edit._nearest``) is the one ``min``
    over every vertex gives with the caller's key, chunk by chunk: equidistant and coincident vertices tie to the
    lower index, and a key whose float rounding isn't numpy's (``** 2``) still ranks the nearest few; from a grid's
    cells too (Step 2.179), a query whose nearest lie past them by the full scan."""
    monkeypatch.setattr(mesh_edit, "NEAR_ROWS", 5000)      # 4 queries a chunk
    monkeypatch.setattr(mesh_edit, "GRID_PAIRS", 0 if grid else 1 << 62)
    rng = np.random.default_rng(7)
    lattice = [(0.25 * a, 0.25 * b, 0.25 * c) for a in range(-3, 4) for b in range(-3, 4) for c in range(-2, 3)]
    pts = lattice + [tuple(p) for p in rng.uniform(-1, 1, (300, 3))] + lattice[:40]
    queries = ([(x + 0.125, y, z) for x, y, z in lattice[::3]] + [tuple(q) for q in rng.uniform(-1, 1, (200, 3))]
               + pts[::7] + [(3.0, 0.0, 0.0), (0.5, -1.6, 0.9)])

    def key(j, q):
        return (pts[j][0] - q[0]) ** 2 + (pts[j][1] - q[1]) ** 2 + (pts[j][2] - q[2]) ** 2, j
    assert mesh_edit._nearest(pts, queries, key) == [min(range(len(pts)), key=lambda j: key(j, q)) for q in queries]

def test_a_binds_nearest_search_gives_the_loops_vertex_widening_ties_and_none_included():
    """Step X.65c: a bind's nearest ``to`` vertex (``mesh_edit._bind_nearest``) is its loop's: the least
    (squared distance, index) in the 27 cells about the vertex's, else within 2, 4 or 8 cells (not the nearest
    beyond them), equidistant and coincident vertices to the lower index, none past 8 cells."""
    cell = mesh_edit.BIND_CELL
    rng = np.random.default_rng(11)
    lattice = [(cell * a, cell * b, cell * c) for a in range(-2, 3) for b in range(-2, 3) for c in range(0, 2)]
    far = [(cell * 3.5, 0.0, 0.0), (cell * 6.5, 0.0, 0.0), (cell * 12.5, 0.0, 0.0), (cell * 30.0, 0.0, 0.0)]
    to = lattice + [tuple(p) for p in rng.uniform(-0.05, 0.05, (200, 3))] + lattice[::4] + far
    final = to + [(x + cell / 2, y, z + cell / 2) for x, y, z in lattice] + [tuple(q) for q in rng.uniform(-0.06, 0.06, (300, 3))] \
        + [(cell * (x + 0.5), 0.0, 0.0) for x in (-4, 9, 17, 22, 60)] + [(-cell * 25, cell * 25, 0.0)]
    grid: dict = {}
    for k in range(len(to)):
        grid.setdefault(tuple(math.floor(final[k][c] / cell) for c in range(3)), []).append(k)
    ks = list(range(len(to), len(final))) + list(range(0, len(to), 9))

    def loop(q):
        ci, best, reach = tuple(math.floor(q[c] / cell) for c in range(3)), None, 1
        while best is None and reach <= 8:
            for j in (j for a in range(-reach, reach + 1) for b in range(-reach, reach + 1)
                      for c in range(-reach, reach + 1) for j in grid.get((ci[0] + a, ci[1] + b, ci[2] + c), ())):
                d = (final[j][0] - q[0]) * (final[j][0] - q[0]) + (final[j][1] - q[1]) * (final[j][1] - q[1]) \
                    + (final[j][2] - q[2]) * (final[j][2] - q[2])
                best = (d, j) if best is None or (d, j) < best else best
            reach *= 2
        return best
    want = {k: best[1] for k in ks if (best := loop(final[k])) is not None}
    assert mesh_edit._bind_nearest(final, grid, ks) == want and len(want) == len(ks) - 2

def test_a_harmonic_islands_solve_gives_the_loops_uvs_to_the_bit(monkeypatch):
    """Step X.65c: ``mesh_edit._conjugate``, the island UVs' conjugate gradients in numpy, gives the loop's
    answer to the bit on a jittered disc's cotangent system: each row's terms summed in ``sum``'s compensated
    order, the dot products ``sum``'s, the steps rounded as the loop rounds them."""
    rng = np.random.default_rng(5)
    cells = [(a, b) for a in range(13) for b in range(13) if (a - 6) ** 2 + (b - 6) ** 2 <= 37]
    at = {ab: v for v, ab in enumerate(cells)}
    final = [(0.01 * a + rng.normal(0, 0.002), 0.01 * b + rng.normal(0, 0.002), 0.003 * math.sin(a * b))
             for a, b in at]
    tris = [t for (a, b), v in at.items() for t in ((v, at.get((a + 1, b)), at.get((a, b + 1))),
                                                     (at.get((a + 1, b)), at.get((a + 1, b + 1)), at.get((a, b + 1))))
            if None not in t]
    rim = {v for (a, b), v in at.items() if not all((a + x, b + y) in at for x, y in ((1, 0), (-1, 0), (0, 1), (0, -1)))}
    uv = {v: ((final[v][0] - 0.06) * 7.0, (final[v][1] - 0.06) * 7.0) if v in rim else (0.5, 0.5) for v in range(len(at))}
    free = sorted(set(range(len(at))) - rim)

    def loop(packed, diag, b, x):
        def apply(q):
            return [diag[k] * q[k] + sum(w * q[j] for j, w in packed[k]) for k in range(len(q))]
        x, ax = list(x), apply(x)
        r = [b[k] - ax[k] for k in range(len(x))]
        d, rr = list(r), sum(e * e for e in r)
        stop = rr * mesh_edit.UNWRAP_TOLERANCE
        for _ in range(mesh_edit.UNWRAP_MAX):
            if not rr > stop or rr == 0.0:
                break
            ad = apply(d)
            dad = sum(d[k] * ad[k] for k in range(len(d)))
            if not dad > 0.0:
                break
            alpha = rr / dad
            for k in range(len(x)):
                x[k] += alpha * d[k]
                r[k] -= alpha * ad[k]
            rr2 = sum(e * e for e in r)
            rr, beta = rr2, rr2 / rr
            for k in range(len(d)):
                d[k] = r[k] + beta * d[k]
        return x
    solved, real = [], mesh_edit._conjugate
    monkeypatch.setattr(mesh_edit, "_conjugate", lambda *a: solved.append((a, real(*a))) or solved[-1][1])
    mesh_edit._harmonic(tris, final, uv, free)
    assert len(solved) == 2 and len(free) > 60
    for args, got in solved:
        assert list(map(float.hex, got)) == list(map(float.hex, loop(*args)))

def test_a_preparation_is_kept_for_equal_bytes_in_a_new_object(monkeypatch):
    """Step X.63: W24's plan and every jiggle bone's shares ask ``_prepared`` of a fresh copy of the staged file:
    equal bytes reuse the last preparation (their own lists), other bytes or a mutable buffer prepare anew."""
    calls = []
    monkeypatch.setattr(mesh_edit, "_prepare", lambda c, *a: calls.append(1) or ("mesh", [1], None, None, {2}, 3))
    monkeypatch.setattr(mesh_edit, "_LAST_PREPARED", [None])
    spec, data = mesh_edit.MeshSpec(), bytes(range(256)) * 64
    first = mesh_edit._prepared(data, "body", spec, None)
    again = mesh_edit._prepared(bytes(bytearray(data)), "body", spec, None)
    assert len(calls) == 1 and again == first == ("mesh", [1], None, None, {2}, 3) and again[1] is not first[1]
    mesh_edit._prepared(data[:-1] + b"x", "body", spec, None)
    mesh_edit._prepared(bytearray(data[:-1] + b"x"), "body", spec, None)
    assert len(calls) == 3

def test_a_preparation_kept_while_another_is_looked_up_answers_only_the_spec_asked(monkeypatch):
    """The app's engine runs a Check beside a preview, each on its own thread, so another call may keep its
    preparation while this one compares the kept key to its spec (a recipe of yours is parsed anew each call,
    an equal spec in another object: the dataclass's ``__eq__``, where the threads switch): the kept entry is
    read once, so a call answers its own spec's preparation, never the one kept meanwhile."""
    monkeypatch.setattr(mesh_edit, "_prepare", lambda c, body, spec, base: (f"mesh of {spec.keep[0]}", [], None, None,
                                                                             set(), 0))
    monkeypatch.setattr(mesh_edit, "_LAST_PREPARED", [None])
    data, other = bytes(range(256)), mesh_edit.MeshSpec(keep=("B",))

    class Kept(mesh_edit.MeshSpec):
        """A's spec as kept, whose compare lets the other thread keep B's first."""

        def __eq__(self, spec):
            if not switched:
                switched.append(None)
                switched[0] = mesh_edit._prepared(data, "body", other, None)
            return isinstance(spec, mesh_edit.MeshSpec) and self.keep == spec.keep
        __hash__ = mesh_edit.MeshSpec.__hash__
    switched = []
    assert mesh_edit._prepared(data, "body", Kept(keep=("A",)), None)[0] == "mesh of A" and not switched
    assert mesh_edit._prepared(bytes(bytearray(data)), "body", mesh_edit.MeshSpec(keep=("A",)), None)[0] == "mesh of A"
    assert switched[0][0] == "mesh of B"   # the other call, mid-compare, kept its own

def _new_joint(shape: dict, name: str, parent: int, origin) -> int:
    """A joint ``name`` added to the skin under node ``parent``, its bind at ``origin`` (the model's frame,
    no turn); its index in the skin."""
    doc = shape["doc"]
    doc["nodes"].append({"name": name, "translation": [0.0, 0.0, 0.0]})
    doc["nodes"][parent].setdefault("children", []).append(len(doc["nodes"]) - 1)
    flip = np.eye(4)
    flip[:3, :3] = UP
    bind = np.eye(4)
    bind[:3, 3] = -np.asarray(origin, float)
    shape["joints"].append(len(doc["nodes"]) - 1)
    shape["binds"].append(bind @ np.linalg.inv(flip))
    return len(shape["joints"]) - 1

def test_a_gltf_imported_with_any_topology_writes_its_new_vertices_triangles_groups_and_bones(exported, usa_iso, tmp_path,
                                                                                               capsys):
    """Step 2.154 (D443): ``gltf_import`` reads a Blender-shaped edit of
    the export with any topology.  Unchanged (one normal turned 0.6
    degrees, as Blender 5.2.2's round trip turns one), it writes
    characters.xbr byte for byte (as the weights import does).  With 100
    of the skin's
    triangles split at their centroids (corners whose ids Blender
    interpolated: new vertices), 10 of the top's deleted (the vertices only
    they drew removed) and a new quad on group 0's material skinned to a
    new joint under spine_2, the written body has the 100 new skin
    vertices after the old ones (each the corner's skin) and 200 more
    triangles, the top 10 fewer, the quad's 4 vertices in group 0 on the
    new bone (93, under spine_2, its bind where the joint's is), every
    untouched group and vertex byte for byte, and a variant's mesh with
    ``"import": "topology"`` builds the same, as ``model import --out``
    writes it; a material not the body's or a new vertex with no weight
    fails by name, and an ``--out`` that exists is refused."""
    from azurkit.tools.characters import body_codec, gltf_import

    characters, gltf = exported
    vanilla = body_codec.read_asset(characters, BODY)
    unchanged = _shaped(gltf, 0.0)
    n = unchanged["prims"][0]["NORMAL"]      # Blender 5.2.2's round trip turns one of female_2's normals 0.6 degrees
    c, s_ = np.cos(np.radians(0.6)), np.sin(np.radians(0.6))
    n[177] = (np.array([[c, -s_, 0], [s_, c, 0], [0, 0, 1]]) @ n[177]).astype(np.float32)
    for mode in ("topology", "weights"):
        same = gltf_import.read(characters, BODY, _glb(unchanged, tmp_path / f"same-{mode}.glb"), mode)
        assert body_codec.write_asset(characters, same.asset) == characters
        assert (same.changed, same.added, same.removed, same.ignored, same.swapped) == (0, 0, 0, ("Cube",), True)

    shape = _shaped(gltf, 0.0)
    skin, top, first = shape["prims"][1], shape["prims"][4], shape["prims"][0]
    tris = []
    for k, (a, b, c) in enumerate(skin["indices"]):
        if k >= 100:
            tris.append((a, b, c))
            continue
        m = len(skin["POSITION"])
        for key in ("POSITION", "NORMAL", "TEXCOORD_0"):
            skin[key] = np.concatenate([skin[key], skin[key][[a, b, c]].mean(0, keepdims=True).astype(np.float32)])
        skin["TEXCOORD_1"] = np.concatenate([skin["TEXCOORD_1"], np.float32([[1.5, 0.5]])])
        for key in ("JOINTS_0", "WEIGHTS_0"):
            skin[key] = np.concatenate([skin[key], skin[key][a:a + 1]])
        tris += [(a, b, m), (b, c, m), (c, a, m)]
    skin["indices"] = np.array(tris)
    dropped, top["indices"] = top["indices"][-10:], top["indices"][:-10]
    names = [n["name"] for n in shape["doc"]["nodes"]]
    joint = _new_joint(shape, "breast_l", names.index("spine_2"), (0.08, 0.10, 1.35))
    spine = shape["joints"].index(names.index("spine_2"))
    quad = (np.float32([[x, 0.2, z] for x in (0.06, 0.1) for z in (1.33, 1.37)]) @ UP.T).astype(np.float32)
    shape["prims"].append({"POSITION": quad, "NORMAL": np.float32([[0, 0, -1]] * 4), "TEXCOORD_0": np.float32([[0.5, 0.5]] * 4),
                           "TEXCOORD_1": np.float32([[0.5, 0.5]] * 4), "JOINTS_0": np.array([[joint, spine, 0, 0]] * 4),
                           "WEIGHTS_0": np.float32([[0.7, 0.3, 0, 0]] * 4), "indices": np.array([[0, 1, 3], [0, 3, 2]]),
                           "material": first["material"]})
    got = gltf_import.read(characters, BODY, _glb(shape, tmp_path / "edit.glb"))
    assert (got.added, got.new_bones, got.new_groups) == (104, ("breast_l",), 0)
    back = body_codec.read_asset(body_codec.write_asset(characters, got.asset), BODY)
    g = back.lods[0].groups
    assert [len(x.vertices) for x in g][2:] == [len(x.vertices) for x in vanilla.lods[0].groups][2:4] + \
        [len(g[4].vertices), 202]
    assert g[2].vertices == vanilla.lods[0].groups[2].vertices and g[5].vertices == vanilla.lods[0].groups[5].vertices
    assert g[1].vertices[:1899] == vanilla.lods[0].groups[1].vertices and len(g[1].vertices) == 1999
    alone = set(dropped.ravel()) - set(top["indices"].ravel())
    assert len(g[1].triangles) == 3051 + 200 and len(g[4].triangles) == 710 and len(g[4].vertices) == 480 - len(alone)
    for k in range(100):     # each new vertex the skin of the corner it was given (Blender drops weights under 1e-4)
        mine, theirs = g[1].skin(1899 + k), vanilla.lods[0].groups[1].skin(int(skin["indices"][3 * k][0]))
        assert max(abs(mine.get(b, 0.0) - theirs.get(b, 0.0)) for b in {*mine, *theirs}) < 1e-3
    assert back.bone_names[93] == "breast_l" and back.bones[93].parent == back.bone_names.index("spine_2")
    bind = struct.unpack_from("<16f", back.bones[93].record, 0x60)
    assert np.abs(np.array(bind[12:15]) + (0.08, 0.10, 1.35)).max() < 1e-5
    mine = [j for j, v in enumerate(g[0].vertices) if 93 in g[0].skin(j)]
    assert len(mine) == 4 and all(g[0].skin(j)[93] == pytest.approx(0.7, abs=1e-6) for j in mine)
    # a variant's mesh.gltf with "import": "topology" builds the same body (W24)
    path = tmp_path / "edit.glb"
    plan = mesh_edit.plan(characters, BODY, mesh_edit.MeshSpec(gltf=(path.name, got.sha256), gltf_import="topology"),
                          tmp_path)
    edited = bytearray(characters)
    mesh_edit.write(edited, plan, characters)
    assert bytes(edited) == body_codec.write_asset(characters, gltf_import.read(characters, BODY, path).asset)
    code, said, _ = _run(capsys, "import", "town_female_2", str(path), "--out", str(tmp_path / "out.xbr"), "--iso",
                         str(usa_iso))
    assert code == 0 and "104 added" in said and "new bones: breast_l" in said and '"import": "topology"' in said
    assert (tmp_path / "out.xbr").read_bytes() == bytes(edited)
    code, _, err = _run(capsys, "import", "town_female_2", str(path), "--out", str(tmp_path / "out.xbr"), "--iso",
                        str(usa_iso))
    assert code == 1 and "exists already" in err

    def foreign_material(s):
        s["doc"]["materials"].append({"name": "nope"})
        s["prims"][-1]["material"] = len(s["doc"]["materials"]) - 1

    for edit, refusal in ((foreign_material, "material 'nope' is none of"),
                          (lambda s: s["prims"][-1]["WEIGHTS_0"].__setitem__(slice(None), 0.0), "has no weights")):
        bad = _shaped(gltf, 0.0)
        bad["prims"].append({**shape["prims"][-1], "JOINTS_0": np.array([[spine, 0, 0, 0]] * 4),
                             "WEIGHTS_0": np.float32([[1, 0, 0, 0]] * 4)})
        edit(bad)
        with pytest.raises(ValueError, match=refusal):
            gltf_import.read(characters, BODY, _glb(bad, tmp_path / "bad.glb"))

def test_skin_weights_painted_in_a_gltf_import_onto_any_bones_and_regroup(exported, tmp_path):
    """Step 2.154 (D443): ``gltf_import``'s ``weights`` mode takes a
    Blender-painted skin onto the same topology: the chest band's
    vertices repainted 0.6 on a new joint under spine_2 and 0.4 on their
    heaviest bone come back so (float32, slot 0 the heaviest), the new
    bone added; every other vertex byte for byte, no position, normal or
    UV moved; the skin's group, its palette past 31, splits into groups
    of at most 31 bones; a new vertex fails by name."""
    from azurkit.tools.characters import body_codec, gltf_import

    characters, gltf = exported
    vanilla = body_codec.read_asset(characters, BODY)
    shape = _shaped(gltf, 0.0)
    names = [n["name"] for n in shape["doc"]["nodes"]]
    joint = _new_joint(shape, "breast_l", names.index("spine_2"), (0.08, 0.10, 1.35))
    skin = shape["prims"][1]
    band = _band(skin["POSITION"].astype(float) @ UP)
    heaviest = skin["JOINTS_0"][band, 0]
    skin["JOINTS_0"][band] = np.stack([np.full(band.sum(), joint), heaviest, np.zeros(band.sum()),
                                       np.zeros(band.sum())], 1)
    skin["WEIGHTS_0"][band] = (0.6, 0.4, 0.0, 0.0)
    got = gltf_import.read(characters, BODY, _glb(shape, tmp_path / "paint.glb"), "weights")
    assert (got.new_bones, got.changed, got.added) == (("breast_l",), int(band.sum()), 0)
    back = body_codec.read_asset(body_codec.write_asset(characters, got.asset), BODY)
    assert back.bone_names[93] == "breast_l" and len(back.lods[0].groups) > 6
    assert all(len(g.palette) <= body_codec.PALETTE_MAX for g in back.lods[0].groups)
    by_place = {}
    for g in back.lods[0].groups:
        for j, v in enumerate(g.vertices):
            by_place.setdefault((v.position, v.uv), []).append(g.skin(j))
    painted = {int(i) for i in skin["TEXCOORD_1"][band, 1]}
    for gi, g in enumerate(vanilla.lods[0].groups):
        for j, v in enumerate(g.vertices):
            skins = by_place[(v.position, v.uv)]
            if gi == 1 and j in painted:
                assert {93: pytest.approx(0.6, abs=1e-6)}.items() <= skins[0].items()
            else:
                assert any(s == g.skin(j) for s in skins)
    shape["prims"][1]["TEXCOORD_1"][0] = (1.5, 0.5)
    with pytest.raises(ValueError, match="weights import onto the same topology"):
        gltf_import.read(characters, BODY, _glb(shape, tmp_path / "new.glb"), "weights")

def test_a_harmonic_island_over_two_groups_lays_them_as_one_surface():
    """Step 2.154 round 9 (D552, her right brow, whose triangles lie in two of her skin's groups): a harmonic
    ``island`` over a sheet whose right half is a second group (its own vertices at the left half's places along
    x = 0) lays both halves as one surface: every triangle with UV area, each place's vertices at one UV."""
    from dataclasses import replace

    from azurkit.tools.characters.characters import MeshGroup
    m = _sheet(0.05)
    ids, keys, pos, nrm, uvs, skins, heavy = (list(x) for x in (m.ids, m.keys, m.positions, m.normals, m.uvs, m.skins,
                                                                 m.heaviest))
    copy: dict[int, int] = {}
    tris = []
    for t in m.triangles:
        if sum(m.positions[v][0] for v in t) > 0:
            for v in t:
                if v not in copy:
                    copy[v] = len(ids)
                    ids.append((1, len(copy) - 1))
                    for lst in (keys, pos, nrm, uvs, skins, heavy):
                        lst.append(lst[v])
            t = tuple(copy[v] for v in t)
        tris.append(t)
    two = replace(m, groups=(m.groups[0], MeshGroup(0, 1, (0, 1), 0, 0, len(copy))), ids=tuple(ids), keys=tuple(keys),
                  positions=tuple(pos), normals=tuple(nrm), uvs=tuple(uvs), skins=tuple(skins), heaviest=tuple(heavy),
                  triangles=tuple(tris))
    spec = mesh_edit.MeshSpec(ops=(mesh_edit.IslandOp("a", (0.5, 0.2, 0.5), ((0.0, 0.0, 1.0, 1.0),),
                                                      offset=(0.0, 0.06, 0.0), groups=(0, 1)),))
    out, base = mesh_edit._split_islands(two, spec, list(two.positions))
    uvs = mesh_edit._island_uvs(out, spec, base, base)
    laid = [t for t in out.triangles if all(v in uvs for v in t)]
    assert len(laid) == len(out.triangles)
    area = [abs((uvs[b][0] - uvs[a][0]) * (uvs[c][1] - uvs[a][1]) - (uvs[c][0] - uvs[a][0]) * (uvs[b][1] - uvs[a][1]))
            for a, b, c in laid]
    assert min(area) > 1e-5
    at: dict[bytes, set] = {}
    for v in uvs:
        at.setdefault(out.keys[v], set()).add(uvs[v])
    assert all(len(u) == 1 for u in at.values())

def test_a_snapped_cut_puts_its_edge_back_on_its_surface_and_lays_one_cord_along_it():
    """Step 2.154 round 9 (D549, the judges: her sash's edge snapped within 2 mm of its line, its cord one unbroken
    spline, its foot rounded into the lower hem): on the flat chest a ``snap`` cut with a ``corner`` (a second plane
    under it, their corner rounded) has every edge point on the rounded surface after the press moved them off it, no
    cloth past it, and one cord: its rings in one run of even steps riding the edge."""
    mesh = _chest()
    base = list(mesh.positions)
    n = (0.8944271909999159, 0.0, 0.4472135954999579)
    cut = mesh_edit.CutOp("spine", n, (0.3, 0.3, 0.3), (1,), offset=(0.0, 0.062, 0.0), under=(0,),
                          press=(0.004, 0.02, 0.0015, 0.001, (0.0, -0.5, 0.0)), trim=(0.003, 0.6, 8, (0.0, 0.0, 0.1, 1.0)),
                          snap=True, corner=((0.0, 0.0, -1.0), (0.0, 0.0, -0.155), 0.02))
    spec = mesh_edit.MeshSpec(ops=(cut,))
    out, got = mesh_edit._cut(mesh, spec, base)
    final = list(got)
    mesh_edit._press(out, spec, final)
    planes = mesh_edit._cut_planes(out, cut)
    edge = dict(out.cuts)[0]
    assert max(abs(mesh_edit._cut_value(final[v], planes)[0]) for v in edge) > 1e-4       # the press moved it off
    mesh_edit._snap(out, spec, final)
    mesh_edit._ride(out, final)
    assert max(abs(mesh_edit._cut_value(final[v], planes)[0]) for v in edge) < 1e-6
    assert len(out.splines) == 1 and {k for k, _, _ in out.trims} == {k for row in out.splines[0][2] for k in row} | set(
        out.splines[0][3])
    centres = [np.mean([final[k] for k in row[:8]], 0) for row in out.splines[0][2]]
    steps = np.linalg.norm(np.diff(centres, axis=0), axis=1)
    assert steps.max() < 1.2 * steps.mean() and steps.mean() <= mesh_edit.CORD_STEP * 1.2
    assert max(abs(mesh_edit._cut_value(tuple(cc), planes)[0]) for cc in centres) < 0.002
    low = [v for v in edge if final[v][2] < 1.145 + 0.02]
    assert low and all(mesh_edit._cut_value(final[v], planes)[0] > -1e-9 for v in low)
    cloth = [t for t in out.triangles if out.ids[t[0]][0] == 1 and not out.fixed.intersection(t)]
    assert max(mesh_edit._cut_value(got[v], planes)[0] for t in cloth for v in t) <= mesh_edit.CUT_SNAP
    # round 11 (judge 0's F4): a ``foot`` lifts the cord over 2 cm from its lower end, easing to none 2 cm past it
    footed = mesh_edit.MeshSpec(ops=(replace(cut, foot=(0.02, 0.0005)),))
    out2, got2 = mesh_edit._cut(mesh, footed, base)
    final2 = list(got2)
    for step in (mesh_edit._press, mesh_edit._snap, mesh_edit._ride):
        step(out2, footed, final2) if step is not mesh_edit._ride else step(out2, final2)
    lifted = [np.mean([final2[k] for k in row[:8]], 0) for row in out2.splines[0][2]]
    off = np.linalg.norm(np.subtract(lifted, centres), axis=1)
    lo = int(np.argmin([c[2] for c in centres]))
    along = np.abs(np.arange(len(centres)) - lo) * steps.mean()
    assert all(abs(off[along < 0.019] - 0.0005) < 1e-4) and off[along > 0.0405].max() < 1e-9


# --------------------------------------------------------------------------- the writer

def _soup(seed: int, holes: float = 0.1, turned: float = 0.2) -> list[tuple[int, int, int]]:
    """A grid with ``holes``, a share of its windings ``turned``, a fan and a fin (an edge three triangles share)."""
    rng = random.Random(seed)
    n = 9
    out = []
    for y in range(n):
        for x in range(n):
            a, b, c, d = y * (n + 1) + x, y * (n + 1) + x + 1, (y + 1) * (n + 1) + x, (y + 1) * (n + 1) + x + 1
            for t in ((a, b, d), (a, d, c)):
                if rng.random() < holes:
                    continue
                out.append(t if rng.random() >= turned else (t[0], t[2], t[1]))
    hub = 1000
    out += [(hub, hub + 1 + k, hub + 2 + k) for k in range(7)] + [(0, 1, 2000)]
    rng.shuffle(out)
    return out

@pytest.mark.parametrize("seed", range(4))
def test_a_strip_draws_exactly_its_triangles_with_their_windings(seed):
    for tris in (_soup(seed), _soup(seed, 0.0, 0.0)):
        strip = bc.stripify(tris)
        assert Counter(map(bc._canonical, bc.strip_triangles(strip))) == Counter(map(bc._canonical, tris))
        push = bc.encode_strip(strip)
        assert bc.strip_indices(push, 0, len(push)) == strip
        assert bc._least_push(len(tris)) <= len(push)    # no strip of them is shorter: past PUSH_MAX, none is made
    assert all(bc._least_push(n) == min(len(bc.encode_strip([0] * k)) for k in range(n + 2, n + 600))
               for n in (0, 1, 2, 509, 510, 511, 512, 11139, 11140, 11141))
    assert len(strip) < 1.7 * len(tris)    # a clean surface strips about as tightly as vanilla (1.635 a triangle)

def _surface(asset: bc.BodyAsset) -> Counter:
    """Each LOD's drawn triangles as (LOD, material, three vertices in bone space), rotation-free."""
    out = Counter()
    for n, lod in enumerate(asset.lods):
        for g in lod.groups:
            keys = [(v.position, v.normal, v.uv, tuple(sorted(v.skin(g.palette).items()))) for v in g.vertices]
            for t in g.triangles:
                i = min(range(3), key=lambda j: keys[t[j]])
                out[n, g.material, tuple(keys[t[(i + j) % 3]] for j in range(3))] += 1
    return out

def test_a_topology_edit_grows_the_file_in_place_and_moves_nothing_else(usa):
    data = usa("gamedata/characters.xbr")
    asset = bc.read_asset(data, BODY)
    groups = asset.lods[0].groups
    skin, arms, hand, vase = groups[1], groups[2], groups[3], groups[5]
    # the skin's triangles split at their centroids: 3x the triangles, a strip past PUSH_MAX
    tris = []
    for t in skin.triangles:
        vs = [skin.vertices[k] for k in t]
        weights: dict[int, float] = {}
        for k in t:
            for b, w in skin.skin(k).items():
                weights[b] = weights.get(b, 0.0) + w / 3
        m = skin.add(*(tuple(sum(v.position[c] for v in vs) / 3 for c in range(3)),
                       tuple(sum(v.normal[c] for v in vs) / 3 for c in range(3)),
                       tuple(sum(v.uv[c] for v in vs) / 3 for c in range(2))), weights)
        tris += [(t[0], t[1], m), (t[1], t[2], m), (t[2], t[0], m)]
    skin.triangles = tris
    # the forearms and right hand merged into one group (a palette past 31), the vase removed
    merged = bc.Group(list(arms.palette), list(arms.vertices), list(arms.triangles), arms.material)
    for k in range(len(hand.vertices)):
        merged.add(hand.vertices[k].position, hand.vertices[k].normal, hand.vertices[k].uv, hand.skin(k))
    merged.triangles += [tuple(v + len(arms.vertices) for v in t) for t in hand.triangles]
    assert len(merged.palette) > bc.PALETTE_MAX
    asset.lods[0].groups = [groups[0], skin, merged, groups[4]]
    want = _surface(asset)

    out = bc.write_asset(data, asset)
    back = bc.read_asset(out, BODY)
    assert _surface(back) == want
    assert all(len(g.palette) <= bc.PALETTE_MAX and len(g.vertices) <= bc.INDEX_MAX + 1 for g in back.lods[0].groups)
    assert all(len(g.stored[1]) <= bc.PUSH_MAX for g in back.lods[0].groups)
    assert len(back.lods[0].groups) > 4 and vase.material not in {g.material for g in back.lods[0].groups}

    toc, toc2 = parse_toc(data), parse_toc(out)
    h, h2 = struct.unpack_from("<15I", data), struct.unpack_from("<15I", out)
    mine = {asset.index, asset.lods[0].bmsh}
    assert (h2[3], h2[4], named_resources(out)) == (h[3], h[4], named_resources(data))
    assert toc2[asset.lods[0].bmsh].size > toc[asset.lods[0].bmsh].size + 0x10000
    for e, e2 in zip(toc, toc2):
        if e.index not in mine:
            assert (e2.tag, e2.flags, e2.rel_offset % 0x1000, out[e2.file_offset:e2.file_offset + e2.size]) == \
                (e.tag, e.flags, e.rel_offset % 0x1000, data[e.file_offset:e.file_offset + e.size]), e.index

    def fields(d, t, hh):
        """Each relocation entry as (TOC entry, offset in its payload, the value there)."""
        out_ = []
        for r in struct.unpack_from(f"<{hh[7]}I", d, hh[8]):
            e = next(x for x in t if x.rel_offset <= r < x.rel_offset + x.size)
            out_.append((e.index, r - e.rel_offset, struct.unpack_from("<I", d, hh[4] + r)[0]))
        return out_
    before, after = fields(data, toc, h), fields(out, toc2, h2)
    assert [f for f in after if f[0] != asset.lods[0].bmsh] == [f for f in before if f[0] != asset.lods[0].bmsh]
    assert [f for f in after if f[0] == asset.lods[0].bmsh] == \
        [(asset.lods[0].bmsh, 8 + 40 * g + 32, x.material[0]) for g, x in enumerate(back.lods[0].groups)]

@pytest.mark.parametrize(("edit", "refusal"), [
    (lambda a: a.lods[0].groups[1].triangles.append((0, 0, 1)), "repeat a vertex or name one past"),
    (lambda a: a.lods[0].groups[1].triangles.append((0, 1, 99999)), "repeat a vertex or name one past"),
    (lambda a: a.lods[0].groups[0].vertices.__setitem__(
        0, bc.Vertex((float("nan"), 0.0, 0.0), (1.0, 0.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 0.0), slots=(1, 0, 0, 0))),
     "a float isn't finite"),
    (lambda a: a.lods[0].groups[0].vertices.__setitem__(
        0, bc.Vertex((0.0, 0.0, 0.0), (0.5, 0.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 0.0), slots=(1, 0, 0, 0))),
     "weights sum to"),
    (lambda a: a.lods[0].groups[0].vertices.__setitem__(
        0, bc.Vertex((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 0.0), slots=(13, 0, 0, 0))),
     "outside the 8-entry palette"),
    (lambda a: setattr(a.lods[0].groups[0], "material", (0, 0)), "is no gshd row"),
    (lambda a: setattr(a.bones[1], "record", a.bones[1].record[:8] + struct.pack("<h", 90) + a.bones[1].record[10:]),
     "isn't an earlier bone"),
    ("female_1", "is also characters/townspeople/female_1's mesh"),   # her LOD 0's bmsh
])
def test_a_mesh_the_format_cant_hold_is_refused_by_name(usa, edit, refusal):
    data = usa("gamedata/characters.xbr")
    asset = bc.read_asset(data, BODY)
    if edit == "female_1":
        asset.lods[0].bmsh = bc.read_asset(data, "townspeople/female_1").lods[0].bmsh
    else:
        edit(asset)
    with pytest.raises(ValueError, match="model write: .*" + refusal):
        bc.write_asset(data, asset)

def test_a_payload_outgrowing_a_shared_page_re_pages_the_entries_after_it(usa):
    """Step 2.158 (D465, D491; the toolkit review's case): the run builder
    0xA4C00 loads an entry that isn't page-aligned with the run its page
    starts, so a payload that outgrows the slack before one (gshd 511, 16 B
    past it, ahead of characters/bosses/boulder in their one run) moves
    that one to the next page start as a new run's head: every entry stays
    in a run, every other run keeps its members, every other payload's
    bytes and its relocated fields move with it, and the grown one keeps
    its own."""
    import hashlib

    from azurkit.core.xbr.append import relocations, rewrite_payloads
    from azurkit.core.xbr.nodes import runs

    data = usa("gamedata/characters.xbr")
    toc = parse_toc(data)
    boulder = next(i for i, n in named_resources(data).items() if n == "characters/bosses/boulder")
    before = runs(data)
    assert boulder == 512 and next(r.members for r in before.runs if r.head == before.of[511]) == (511, 512)
    grown = data[toc[511].file_offset:toc[511].file_offset + toc[511].size] + bytes(16)
    out = rewrite_payloads(data, {511: grown})
    after, toc2 = runs(out), parse_toc(out)
    assert not after.orphans and after.of[boulder] == boulder
    assert {r.members for r in after.runs} == {r.members for r in before.runs} - {(511, 512)} | {(511,), (512,)}

    def payload(d, t, i):
        return hashlib.sha256(d[t[i].file_offset:t[i].file_offset + t[i].size]).hexdigest()
    assert all(payload(data, toc, i) == payload(out, toc2, i) for i in range(len(toc)) if i != 511)
    assert payload(out, toc2, 511) == hashlib.sha256(grown).hexdigest()

    def inside(d, t):   # each payload's relocated fields, from its start
        rows = sorted(relocations(d))
        return {i: [r - t[i].rel_offset for r in rows if t[i].rel_offset <= r < t[i].rel_offset + t[i].size]
                for i in range(len(t)) if t[i].size}
    assert inside(data, toc) == inside(out, toc2)

def test_a_bone_added_and_one_renamed_keep_every_clip_palette_and_marker_index(usa, tmp_path):
    from azurkit.tools.characters import skeleton
    from azurkit.tools.characters.characters import mesh_groups
    from azurkit.tools.characters.gltf import export_body
    from azurkit.tools.characters.retarget import Rig, qangle

    data = usa("gamedata/characters.xbr")
    asset = bc.read_asset(data, BODY)
    q = (0.1, 0.2, 0.0, 0.97)
    k = skeleton.add_bone(asset, "breast_l", "spine_3", (0.08, 0.1, 1.35), q)
    skeleton.rename_bone(asset, "joint32", "jaw_end")
    for bad, why in ((lambda: skeleton.add_bone(asset, "jaw_end", "head", (0, 0, 1)), "has a bone 'jaw_end' already"),
                     (lambda: skeleton.add_bone(asset, "x", "no_such_bone", (0, 0, 1)), "has no bone 'no_such_bone'"),
                     (lambda: skeleton.rename_bone(asset, "head", "neck"), "has a bone 'neck' already")):
        with pytest.raises(ValueError, match=why):
            bad()
    out = bc.write_asset(data, asset)

    rig, old = Rig.read(out, BODY), Rig.read(data, BODY)
    assert (k, len(rig.bones), rig.bones[k].name, rig.bones[rig.bones[k].parent].name) == (93, 94, "breast_l", "spine_3")
    assert max(abs(a - b) for a, b in zip(rig.positions[k], (0.08, 0.1, 1.35))) < 1e-6   # its inverse bind's origin
    norm = sum(c * c for c in q) ** 0.5
    assert qangle(rig.world[k], tuple(c / norm for c in q)) < 1e-3                       # its composed bind rotation
    assert [b.name for b in rig.bones[:93]] == [("jaw_end" if b.name == "joint32" else b.name) for b in old.bones]
    assert [b.__dict__ | {"name": ""} for b in rig.bones[:93]] == [b.__dict__ | {"name": ""} for b in old.bones]
    toc, toc2 = parse_toc(data), parse_toc(out)
    names = named_resources(data)
    for i, n in names.items():
        if n.startswith(f"characters/{BODY}/"):
            assert out[toc2[i].file_offset:toc2[i].file_offset + toc2[i].size] == \
                data[toc[i].file_offset:toc[i].file_offset + toc[i].size], n
    assert [g.bones for g in mesh_groups(out, BODY)] == [g.bones for g in mesh_groups(data, BODY)]
    back = bc.read_asset(out, BODY)
    assert [(b.name, b.record[8:]) for b in back.bones[:93]] == [(b.name, b.record[8:]) for b in asset.bones[:93]]
    assert [(m.name, m.record[8:]) for m in back.markers] == [(m.name, m.record[8:]) for m in asset.markers]
    # the export's checks pass on it: the rest pose skins and every clip poses through the new bone
    export = export_body(out, BODY, tmp_path / "out", ["idle", "walk"], source_vanilla=False)
    assert export.bones == 94 and export.checks.rest_m < 1e-5

def test_a_body_subset_keeps_only_the_named_groups_and_their_bones(usa):
    """Step 2.159b (G-a): female_0_base cut to LOD0's vase group (the
    townswomen's thrown vase) writes a body of one LOD and one bone,
    vase_joint (a root), drawing exactly that group; cut to LOD0's
    forearms group and LOD1's skin, it keeps the bones their palettes
    name and every ancestor of theirs, in order, each record as stored
    but its parent renumbered, and draws exactly those two groups (by
    bone name); a missing LOD, group or marker is refused by name."""
    data = usa("gamedata/characters.xbr")
    body = "townspeople/female_0_base"
    asset = bc.read_asset(data, body)

    def drawn(a: bc.BodyAsset, lods) -> Counter:
        names = a.bone_names
        out = Counter()
        for n, groups in zip(lods, (lod.groups for lod in a.lods)):
            for g in groups:
                for t in g.triangles:
                    out[n, g.material, tuple(sorted((g.vertices[k].position, tuple(sorted(
                        (names[b], w) for b, w in g.skin(k).items()))) for k in t))] += 1
        return out

    vase = bc.subset(asset, {0: [5]})
    back = bc.read_asset(bc.write_asset(data, vase), body)
    assert ([b.name for b in back.bones], back.bones[0].parent, len(back.lods), back.markers) == (
        ["vase_joint"], -1, 1, [])
    assert [(g.palette, len(g.vertices)) for g in back.lods[0].groups] == [([0], 202)]
    assert back.bones[0].record[8:] == asset.bones[asset.bone("vase_joint")].record[8:]
    assert drawn(back, [0]) == drawn(bc.BodyAsset(body, 0, b"", asset.bones, [], [
        bc.Lod(0, [asset.lods[0].groups[5]])]), [0])

    cut = bc.subset(asset, {0: [2], 1: [1]})
    named = {asset.bones[b].name for g in (asset.lods[0].groups[2], asset.lods[1].groups[1]) for b in g.palette}
    want: set[int] = set()
    for b in (k for k, x in enumerate(asset.bones) if x.name in named):
        while b >= 0 and b not in want:
            want.add(b)
            b = asset.bones[b].parent
    back = bc.read_asset(bc.write_asset(data, cut), body)
    assert [x.name for x in back.bones] == [asset.bones[k].name for k in sorted(want)]
    assert [back.bone_names[x.parent] if x.parent >= 0 else None for x in back.bones] == [
        asset.bones[asset.bones[k].parent].name if asset.bones[k].parent >= 0 else None for k in sorted(want)]
    assert all(x.record[10:] == asset.bones[k].record[10:] for x, k in zip(back.bones, sorted(want)))
    assert drawn(back, [0, 1]) == drawn(bc.BodyAsset(body, 0, b"", asset.bones, [], [
        bc.Lod(0, [asset.lods[0].groups[2]]), bc.Lod(0, [asset.lods[1].groups[1]])]), [0, 1])
    for groups, markers, why in (({2: [0]}, (), "no LOD 2"), ({0: [6]}, (), "LOD 0: no group 6"),
                                 ({0: [5]}, ("m_alpha",), "no marker 'm_alpha'"), ({0: []}, (), "keeps no group")):
        with pytest.raises(ValueError, match=why):
            bc.subset(asset, groups, markers)

def test_the_size_lines_follow_the_built_budget_and_a_128_or_256_mib_target_takes_its_own_only_with_its_packs(
        usa, building, monkeypatch):
    """Step 2.162b (D515): the player's own-runs lines (refuse, warn) move
    with the load budget a build's default.xbe holds, by its distance from
    vanilla's 40 MiB, down below it and up to 42 MiB only (the game's
    memory check cuts a raised limit, so more room doesn't last).
    Step 2.162i (D576): a player build for a 128 MiB machine (a recipe's
    ``ram`` 128) whose default.xbe carries qol_memory_upper64 and
    qol_memory_upper64_gpu weighs the body's own runs against Step
    2.162n's measured lines (D625: the CPU runs from the upper 64 MiB's
    top down): refused past 49.5 MiB and warned past 38 at the 42 MiB
    budget (a 49.49 MiB body kept the levels whole), lower under 42 as
    the 64 MiB lines are, and refused, whatever its total, when one run
    passes the largest that kept the levels whole (42.34 MiB, that body's
    mesh run, above 64 MiB; 43.11 never loaded; model inspect's row
    too).  A body past the 64 MiB lines there gets a log
    line saying it plays right only at 128 MiB (Step 2.162k, D588:
    128 MiB is the default target; model inspect's text says it too).  At
    64 MiB, or at 128 without both packs, the 64 MiB lines (14 and 12)
    hold, and the refusal names what the 128 MiB lines would let
    through.  Step 2.162l (D600, D610): a 256 MiB target whose default.xbe
    carries qol_memory_upper256 too is refused past 127 MiB (a 128.21 MiB
    body played) or one run past 113.53 (that body's mesh run; 128.90
    never loaded), and warned past 48 (the frame rate held with 48.25),
    with a line saying a body past the 128 MiB lines plays right only at
    256; at 128 MiB a body those lines would take is refused naming the
    tick for 256, and at 256 without the pack the 128 MiB lines hold (a
    refusal names ticks, as AzurKit's pages and CLI take them)."""
    from azurkit.tools.characters import model_inspect as mi
    from azurkit.tools.characters._player_character import _load_budget
    from azurkit.core import gate
    from azurkit.edits.layer import compose
    from azurkit.tools import mods
    from azurkit.tools.mods import engine

    MiB = mi.MiB
    assert [mi.lines_for(b * MiB, 64) for b in (36, 40, 42, 44)] == [
        (8 * MiB, 6 * MiB), (12 * MiB, 10 * MiB), (14 * MiB, 12 * MiB), (14 * MiB, 12 * MiB)]
    assert [mi.lines_for(b * MiB, 128) + (mi.run_line_for(b * MiB),) for b in (40, 42, 44)] == [
        (95 * MiB // 2, 36 * MiB, 10838 * 4096 - 2 * MiB), (99 * MiB // 2, 38 * MiB, 10838 * 4096),
        (99 * MiB // 2, 38 * MiB, 10838 * 4096)]

    def built(*packs: str) -> bytes:
        base, layers = {engine.XBE: usa(engine.XBE), engine.CONFIG: usa(engine.CONFIG)}, []
        for name, params in mods.normalize(dict.fromkeys(("qol_memory_budget", *packs), {})).items():   # 42 MiB
            layers.append(mods.plan(mods.PACKS[name], gate.USA, base, params, [c for la in layers for c in la.claims]))
        return bytes(compose(base, layers)[0][engine.XBE])

    stage1, both = built("qol_memory_upper64"), built("qol_memory_upper64", "qol_memory_upper64_gpu")
    u256 = built("qol_memory_upper64", "qol_memory_upper64_gpu", "qol_memory_upper256")
    own: list[dict] = []
    monkeypatch.setattr(mi, "own_runs", lambda *_a, **_k: own[-1])

    def build(xbe: bytes, ram: int, mib: float, run: float = 30.0):
        own.append({"bytes": round(mib * MiB), "runs": 2, "largest": round(min(mib, run) * MiB),
                    "by_tag": {"bmsh": round(mib * MiB)}})
        try:
            return _load_budget({"default.xbe": xbe, "characters.xbr": b""}, "b", "who", False, ram)
        except ValueError as exc:
            return str(exc)

    quiet, ok, warned, refused = (build(both, 128, mib) for mib in (13.9, 37.9, 49.4, 49.6))
    xbox = ("MiB, pass the 14 MiB a 64 MiB machine takes: this build plays right only on a 128 MiB one (xemu at "
            "mem_limit 128); on a 64 MiB Xbox it loses pieces and textures, and a larger one hangs loading (xemu "
            "at 64; without qol_memory_upper64 and qol_memory_upper64_gpu the build refuses the body)")
    assert quiet == [] and ok == [f"  Player model budget: its own load runs, 37.90 {xbox}"]
    assert len(warned) == 2 and "past 38 MiB of the 42 MiB budget on a 128 MiB machine" in warned[0]
    assert warned[1].endswith(f"49.40 {xbox}")
    assert "pass the 49.5 MiB" in refused and "tick qol_memory_upper64 " not in refused
    assert len(build(both, 128, 45.0, run=10838 / 256)) == 2   # the warning and the 64 MiB Xbox's line
    assert "its largest own load run, 42.35 MiB of 45.00 MiB (bmsh 45.00), passes the 42.34 MiB one run" in \
        build(both, 128, 45.0, run=42.35)
    assert "tick qol_memory_upper64 " not in build(both, 64, 45.0, run=42.35)   # the 128 MiB machine refuses it too
    for xbe, ram in ((stage1, 128), (both, 64)):
        said = build(xbe, ram, 20.0)
        assert "pass the 14 MiB" in said and ("or tick qol_memory_upper64 and qol_memory_upper64_gpu for a 128 MiB "
                                              "machine (line 49.5 MiB)") in said, said
    assert "past 12 MiB of the 42 MiB budget (" in build(both, 64, 13.0)[0]

    assert [mi.lines_for(b * MiB, 256) + (mi.run_line_for(b * MiB, 256),) for b in (40, 42)] == [
        (125 * MiB, 46 * MiB, 29063 * 4096 - 2 * MiB), (127 * MiB, 48 * MiB, 29063 * 4096)]
    said = build(u256, 256, 45.9)   # under 48 MiB: the 64 MiB machine's line alone
    assert len(said) == 1 and "plays right only on a 128 or 256 MiB one (xemu at mem_limit 128 or 256)" in said[0]
    warned = build(u256, 256, 100.0, run=90.0)
    assert len(warned) == 2 and "past 48 MiB of the 42 MiB budget on a 256 MiB machine" in warned[0]
    assert "this build plays right only on a 256 MiB one (xemu v0.16.2 or later at mem_limit 256)" in warned[1]
    assert "plays right only on a 256 MiB one" in build(u256, 256, 45.0, run=43.0)[-1]   # one run past 128's line
    assert "pass the 127 MiB a 256 MiB machine with qol_memory_upper256" in build(u256, 256, 127.1, run=90.0)
    assert "passes the 113.53 MiB one run may take on a 256 MiB machine" in build(u256, 256, 120.0, run=113.6)
    for xbe, ram in ((both, 128), (both, 256)):   # at 256 without the pack, the 128 MiB lines
        said = build(xbe, ram, 100.0, run=90.0)
        assert "pass the 49.5 MiB" in said and ("or tick qol_memory_upper256 for a 256 MiB machine (line 127 MiB, "
                                              "one run 113.53") in said, said


# --------------------------------------------------------------------------- LODs

@pytest.mark.parametrize("cells, far, count, kept, steady, fades", [
    ((1000.0,) * 4, 1000.0, 2, [1000.0] * 4, [0], []),                          # garret4: LOD 1 only his shadow's
    ((15.0, 10.0, 15.0, 20.0), 70.0, 4, [15.0, 15.0, 15.0, 20.0], [0, 3], [1, 2]),  # fire_elemental
    ((15.0, 30.0, 40.0, 50.0), 70.0, 5, [15.0, 30.0, 40.0, 50.0], [0, 1, 2, 3, 4], []),  # water_lizard (sleeth)
    ((35.0, 55.0, 70.0, 60.0), 70.0, 4, [35.0, 55.0, 70.0, 70.0], [0, 1, 2], []),  # golem: LOD 3 at farClip
    ((15.0, 30.0, 40.0, 50.0), 70.0, 6, [15.0, 30.0, 40.0, 50.0], [0, 1, 2, 3, 4], []),  # LOD 5 never
    ((-5.0, None, None, None), FLT_MAX, 3, [0.0, FLT_MAX, FLT_MAX, FLT_MAX], [0, 1], []),  # missing cells
])
def test_the_pick_draws_these_lods_at_rest_and_in_its_fades(cells, far, count, kept, steady, fades):
    """The loader's switch distances (a missing cell FLT_MAX, each at least
    the one before and 0), the LODs some distance up to ``farClip`` aims
    for, and the ones the ease's snap draws only in a fade; checked again by
    walking a critter out and back a quarter metre a frame at 30 fps under
    the game's ease (+0x284 clamped to [T-1, T] going out, [T, T+1] coming
    in; a fractional value draws LODs k and k + 1; culled past ``farClip``,
    where it doesn't move)."""
    assert thresholds(cells) == kept
    assert reach(kept, far, count) == (steady, sorted(steady + fades))
    cur, seen = 0.0, set()
    path = [i / 4 for i in range(int(min(far, 2000.0) * 4) + 8)]
    for d in path + path[::-1]:
        if d > far:
            continue
        t = pick(d, kept, count)
        cur = min(max(cur + 2 / 30, t - 1), t) if cur < t else min(max(cur - 2 / 30, t), t + 1) if cur > t else cur
        seen |= {math.floor(cur), math.ceil(cur)}
    assert sorted(seen) == sorted(steady + fades)

def test_model_inspect_reports_which_lods_the_game_draws_and_what_dropping_a_never_drawn_one_frees(usa, building):
    """garret4 (the player's species) switches at 1000 m, his farClip, and
    casts a realtime shadow (a shadowSize, no shadowTextureName) drawn from
    his LOD 1: ``model inspect`` with config.xbr says so.  No wearer reaches
    golem's LOD 3 (golem culls at 70 m, where LOD 3 would start; kingkong
    stays at LOD 0): never drawn, a warning counting its ``bmsh``
    and the one load run only it reaches (what dropping it frees), and the
    report says a LOD the game draws adds to the load and saves none."""
    from azurkit.tools.characters.model_inspect import lines

    data = usa("gamedata/characters.xbr")
    config = usa("gamedata/config.xbr")
    garret4 = inspect(data, "garret4", config_xbr=config)
    assert [(w["species"], w["steady"], w["shadow_lod"]) for w in garret4["wearers"]] == [("garret4", [0], 1)]
    assert [row["drawn"] for row in garret4["lods"]] == ["steady", "shadow"] and garret4["never_drawn"]["lods"] == []
    golem = inspect(data, "golem", config_xbr=config)
    lod3 = golem["lods"][3]
    run = next(r for r in runs(data).runs if lod3["bmsh"] in r.members)
    assert run.members == (lod3["bmsh"],) and lod3["run_bytes"] == run.size
    assert [(w["species"], w["shadow_lod"]) for w in golem["wearers"]] == [("golem", None), ("kingkong", None)]
    assert [row["drawn"] for row in golem["lods"]] == ["steady", "steady", "steady", "never"]
    assert golem["never_drawn"] == {"lods": [3], "bmsh_bytes": lod3["bmsh_bytes"], "run_bytes": run.size}
    text = lines(golem)
    assert f"warning: LOD 3 is never drawn (no wearer's switch distances and farClip reach it, even in a fade): " \
        f"bmsh {lod3['bmsh_bytes']} B, its own runs {run.size} B" in text
    assert "LODs load with the body, drawn or not: a LOD saves draw work and adds its own runs to the load budget; " \
        "dropping one the game never draws frees its own runs" in text

def _area(points) -> float:
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = points
    ux, uy, uz, vx, vy, vz = bx - ax, by - ay, bz - az, cx - ax, cy - ay, cz - az
    return ((uy * vz - uz * vy) ** 2 + (uz * vx - ux * vz) ** 2 + (ux * vy - uy * vx) ** 2) ** 0.5 / 2

def _grid(n: int = 12) -> bc.Lod:
    """Two flat sheets, skinned to one bone: group 0 an n x n grid with an
    open outline and a UV seam down its middle column (each point there two
    vertices, the left side's UVs and the right side's, 1 apart); group 1
    a two-sided sheet beside it, each triangle followed by its back (the
    reverse winding, on vertices of its own with the normal turned)."""
    def sheet(two_sided: bool) -> bc.Group:
        verts, index, tris = [], {}, []

        def vert(x, y, side):
            if (x, y, side) not in index:
                index[x, y, side] = len(verts)
                at = (x * 0.125 + (4.0 if two_sided else 0.0), y * 0.125, 0.0)
                uv = (x / n + (1.0 if side == 1 else 0.0), y / n)
                verts.append(bc.Vertex(at, (1.0, 0.0, 0.0, 0.0), (0.0, 0.0, -1.0 if side == "back" else 1.0), uv,
                                       slots=(1, 0, 0, 0)))
            return index[x, y, side]
        for y in range(n):
            for x in range(n):
                side = "front" if two_sided else int(x >= n // 2)
                a, b, c, d = (vert(x + i, y + j, side) for j in (0, 1) for i in (0, 1))
                for t in ((a, b, d), (a, d, c)):
                    tris.append(t)
                    if two_sided:
                        back = [vert(x + i, y + j, "back") for j in (0, 1) for i in (0, 1)]
                        m = dict(zip((a, b, c, d), back))
                        tris.append((m[t[0]], m[t[2]], m[t[1]]))
        return bc.Group([0], verts, tris, (1, 0))
    return bc.Lod(7, [sheet(False), sheet(True)])

def test_a_decimated_grid_keeps_its_seam_outline_and_both_sides_from_its_own_vertices():
    """Collapses that cost nothing (both sheets are flat) leave a few
    triangles of each, every vertex one of its group's own: the outline
    whole (the area kept: a border moves only along itself), no triangle
    across the seam (each side's UVs) and the seam's points the same on
    both sides (it moves with its twin edge), and the two-sided sheet's
    every triangle with its back on the turned vertices."""
    lod = _grid()
    out = decimate(lod, max_error=1e-6)
    assert out.bmsh is None and len(out.groups) == 2
    for a, b in zip(lod.groups, out.groups):
        assert len(b.triangles) <= len(a.triangles) / 6
        assert b.palette == a.palette and set(b.vertices) <= set(a.vertices)
        assert sum(_area([b.vertices[k].position for k in t]) for t in b.triangles) == \
            pytest.approx(sum(_area([a.vertices[k].position for k in t]) for t in a.triangles))
    seam = out.groups[0]
    sides = [{seam.vertices[k].uv[0] >= 1.0 for k in t} for t in seam.triangles]
    assert all(len(s) == 1 for s in sides) and {True, False} == set().union(*sides)
    on_seam = {(v.position, v.uv[0] >= 1.0) for t in seam.triangles for v in (seam.vertices[k] for k in t)
               if v.position[0] == 0.75}
    assert {p for p, right in on_seam if right} == {p for p, right in on_seam if not right}
    two = out.groups[1]
    faces = {}
    for t in two.triangles:
        pts = [two.vertices[k].position for k in t]
        (ax, ay, _), (bx, by, _), (cx, cy, _) = pts
        up = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax) > 0
        assert {two.vertices[k].normal[2] > 0 for k in t} == {up}
        faces.setdefault(frozenset(pts), []).append(up)
    assert all(sorted(v) == [False, True] for v in faces.values())

def _surface_distance(points, triangles):
    """Each point's distance to the nearest of ``triangles`` (three corners
    each): the plane's inside the triangle, else the nearest edge's."""
    import numpy as np

    q = np.asarray(points, float)
    a, b, c = (np.asarray([t[i] for t in triangles], float) for i in range(3))
    qq = (q * q).sum(-1)[:, None]

    def dot(x):                                     # q . x for every point and triangle
        return q @ x.T

    def seg(x, y):
        xy = y - x
        ll = (xy * xy).sum(-1)
        qx = dot(xy) - (x * xy).sum(-1)
        k = np.clip(qx / ll, 0, 1)
        d2 = qq - 2 * dot(x) + (x * x).sum(-1) - k * (2 * qx - k * ll)
        return np.sqrt(np.maximum(d2, 0))
    ab, ac = b - a, c - a
    n = np.cross(ab, ac)
    d00, d01, d11 = (ab * ab).sum(-1), (ab * ac).sum(-1), (ac * ac).sum(-1)
    d20, d21 = dot(ab) - (a * ab).sum(-1), dot(ac) - (a * ac).sum(-1)
    den = d00 * d11 - d01 * d01
    s, t = (d11 * d20 - d01 * d21) / den, (d00 * d21 - d01 * d20) / den
    plane = np.abs(dot(n) - (a * n).sum(-1)) / np.sqrt((n * n).sum(-1))
    edge = np.minimum(np.minimum(seg(a, b), seg(b, c)), seg(c, a))
    return np.where((s >= 0) & (t >= 0) & (s + t <= 1), plane, edge).min(-1)

def test_female_2_at_0_30_writes_reads_back_and_a_cut_to_a_pixel_at_15_m_stays_within_it(usa):
    """female_2's LOD 0 (5,151 triangles) cut to 0.30: every vertex one of
    its group's own, every palette its group's, nothing the format or the
    game can't hold, written over her LOD 0 and read back, and every one of
    her vertices within a pixel at 15 m (town_female_2's first switch
    distance) of the cut surface.  Cut instead to that pixel
    (``max_error``), she draws fewer triangles and every vertex still lies
    within it: a distance, not the quadric's mean (its stop let her surface
    move 7 cm)."""
    from azurkit.tools.characters.lods import pixel_error

    data = usa("gamedata/characters.xbr")
    asset = bc.read_asset(data, BODY)
    lod0 = asset.lods[0]
    out = decimate(lod0, 0.30)
    assert drawn(lod0) == 5151 and 0.25 * 5151 < drawn(out) <= 0.30 * 5151
    for g in out.groups:
        src = [s for s in lod0.groups if (s.material, s.palette) == (g.material, g.palette)]
        assert len(src) == 1 and set(g.vertices) <= set(src[0].vertices)
    cut = replace(asset, lods=[replace(out, bmsh=lod0.bmsh)])
    assert bc.problems(cut, data) == []
    back = bc.read_asset(bc.write_asset(data, cut), BODY)
    assert drawn(back.lods[0]) == drawn(out)
    points = [v.position for g in lod0.groups for v in g.vertices]
    for lod in (back.lods[0], decimate(lod0, max_error=pixel_error(1, 15.0))):
        tris = [[g.vertices[k].position for k in t] for g in lod.groups for t in g.triangles]
        assert _surface_distance(points, tris).max() <= pixel_error(1, 15.0)
    assert drawn(lod) < drawn(out)

def test_the_decimator_writes_equal_bytes_under_two_hash_seeds(usa, tmp_path):
    """Ties go by index, never by hash order: female_2 at 0.30 written in
    two processes with different ``PYTHONHASHSEED`` gives one file."""
    code = ("import hashlib, sys\nfrom dataclasses import replace\nfrom azurkit.tools.characters import body_codec as bc\n"
            "from azurkit.tools.characters.decimate import decimate\n"
            "data = open(sys.argv[1], 'rb').read()\na = bc.read_asset(data, sys.argv[2])\n"
            "a.lods[0] = replace(decimate(a.lods[0], 0.30), bmsh=a.lods[0].bmsh)\n"
            "print(hashlib.sha256(bc.write_asset(data, a)).hexdigest())\n")
    (path := tmp_path / "characters.xbr").write_bytes(usa("gamedata/characters.xbr"))
    procs = [subprocess.Popen([sys.executable, "-c", code, str(path), BODY], cwd=ROOT,
                              env=dict(os.environ, PYTHONHASHSEED=str(h)), stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True) for h in (0, 1)]
    runs = [(p.wait(timeout=240), *p.communicate()) for p in procs]
    assert runs[0] == runs[1] and runs[0][0] == 0, runs[0][2][-2000:]
    assert runs[0][1].strip() != hashlib.sha256(usa("gamedata/characters.xbr")).hexdigest()

def test_female_2_takes_two_new_lods_that_read_back_clean_and_drops_them_again(usa, building):
    """female_2 (one LOD) with LODs at 0.32 and 0.16 of hers: two unnamed
    ``bmsh`` entries appended, each a load run of its own, named by the
    body's relocated LOD list (3 at +8 and +16), and nothing ``model
    inspect`` finds wrong; her own runs grow by exactly those two runs
    and her body's run by the pages its new records and push buffers
    take.  Dropped again, her count is 1, the two entries stay in the file
    unreferenced and her own runs are vanilla's."""
    data = usa("gamedata/characters.xbr")
    count, before = len(parse_toc(data)), own_runs(data, BODY)
    asset = bc.read_asset(data, BODY)
    asset.lods += lod_chain(asset.lods[0], (0.32, 0.16))
    out = bc.write_asset(data, asset)
    assert [lod.bmsh for lod in asset.lods[1:]] == [count, count + 1]
    back = bc.read_asset(out, BODY)
    assert [(lod.bmsh, drawn(lod)) for lod in back.lods] == [(lod.bmsh, drawn(lod)) for lod in asset.lods]
    at = parse_toc(out)[asset.index].file_offset
    assert struct.unpack_from("<i", out, at + 8) + struct.unpack_from("<i", out, at + 16) == (3, 3)
    assert inspect(out, BODY)["problems"] == []
    part = runs(out)
    new = [r for r in part.runs if r.head in (count, count + 1)]
    assert [r.members for r in new] == [(count,), (count + 1,)] and not {count, count + 1} & set(named_resources(out))

    def body_run(d: bytes) -> int:
        return next(r.size for r in runs(d).runs if r.head == asset.index)
    grown, added = body_run(out) - body_run(data), sum(r.size for r in new)
    assert grown > 0 and own_runs(out, BODY) == {
        "bytes": before["bytes"] + added + grown, "runs": before["runs"] + 2,
        "largest": max(before["largest"], body_run(out), *(r.size for r in new)),
        "by_tag": before["by_tag"] | {"bmsh": before["by_tag"]["bmsh"] + added, "body": body_run(out)}}
    back.lods = back.lods[:1]
    dropped = bc.write_asset(out, back)
    assert len(parse_toc(dropped)) == count + 2 and not bc._users(dropped, count) and not bc._users(dropped, count + 1)
    assert own_runs(dropped, BODY) == before and inspect(dropped, BODY)["problems"] == []

def test_catalisk_keeps_its_four_lods_when_one_is_cut_anew(usa, building):
    """catalisk's LOD 1 cut again from her LOD 0 at vanilla's share: her
    four LODs read back, the new one an appended ``bmsh``, LODs 0, 2 and 3
    their vanilla entries byte for byte, and the old LOD 1 unreferenced."""
    data = usa("gamedata/characters.xbr")
    count = len(parse_toc(data))
    asset = bc.read_asset(data, "catalisk")
    old = [lod.bmsh for lod in asset.lods]
    assert len(old) == 4
    asset.lods[1] = decimate(asset.lods[0], drawn(asset.lods[1]) / drawn(asset.lods[0]))
    out = bc.write_asset(data, asset)
    assert [lod.bmsh for lod in bc.read_asset(out, "catalisk").lods] == [old[0], count, old[2], old[3]]
    assert inspect(out, "catalisk")["problems"] == [] and not bc._users(out, old[1])
    toc, toc2 = parse_toc(data), parse_toc(out)
    for i in (old[0], old[2], old[3]):
        assert out[toc2[i].file_offset:toc2[i].file_offset + toc2[i].size] == \
            data[toc[i].file_offset:toc[i].file_offset + toc[i].size]

def test_a_big_one_lod_body_the_player_wears_casts_its_shadow_from_a_coarse_lod_no_screen_draws(usa, building,
                                                                                                 monkeypatch):
    """W36 (Step 2.166c, the X.68 audit's item 5): the player's realtime
    shadow draws LOD 1, LOD 0 for a one-LOD body, so a big body is drawn
    twice a frame.  female_2 worn by garret4 (W1), under
    :data:`~azurkit.tools.characters.decimate.SHADOW_MIN` triangles or with her
    recipe's ``lods.shadow`` false, is written byte for byte; past it (the
    line lowered under her 5,151) she takes a LOD 1 cut coarse from her
    LOD 0, which stays byte for byte: ``model inspect`` says only the
    realtime shadow draws it and counts its own runs, garret4's switch at
    his farClip keeps it off his screen and town_female_2's at 15 m is
    moved past hers (FLT_MAX), and the log line says what the load grew
    by; a load refusal the LOD alone causes names ``"lods": {"shadow":
    false}``.  Named by its inputs (Step 4.37m1: a build's names of her
    file and of her LOD 0), what W36 kept is what it takes again with no
    cut made here (a cut started ahead of that LOD 0, Step 2.179, starts
    none), the same bytes; one started at another share isn't taken.  A
    body with LODs of its own (catalisk) refuses ``lods.shadow``."""
    from azurkit.tools.characters import decimate as dm
    from azurkit.tools.characters import model_inspect as mi
    from azurkit.tools.characters._player_character import _load_budget, write_shadow_lod
    from azurkit.tools.characters.ports import XbrDocument
    from azurkit.tools.characters.ports import point_keyed_string

    data = usa("gamedata/characters.xbr")

    def worn(species: str):
        doc = XbrDocument.from_bytes(usa("gamedata/config.xbr"))
        engine = doc.keyed_section("critters_engine")
        point_keyed_string(engine, "garret4", "body", species, "body")
        return {"characters.xbr": bytearray(data)}, engine, doc
    for shadow in (None, False):
        game, engine, doc = worn("town_female_2")
        config = bytes(doc.raw)
        assert write_shadow_lod(game, engine, BODY, shadow) == ([], 0) and game["characters.xbr"] == data
        assert bytes(doc.raw) == config
    monkeypatch.setattr(dm, "SHADOW_MIN", 5000)
    game, engine, doc = worn("town_female_2")
    named = {"known": "her file's name", "mesh": "her LOD 0's"}   # as the build names them by their inputs
    said, added = write_shadow_lod(game, engine, BODY, **named)
    out = bytes(game["characters.xbr"])
    report = inspect(out, BODY, config_xbr=bytes(doc.raw))
    lod0, lod1 = report["lods"]
    assert report["problems"] == [] and lod0["drawn"] == "steady" and lod1["drawn"] == "shadow"
    assert lod1["triangles"] <= 0.2 * lod0["triangles"] and lod1["run_bytes"] > 0
    assert [(w["species"], w["steady"], w["shadow_lod"]) for w in report["wearers"]] == [
        ("garret4", [0], 1), ("town_female_2", [0], None)]
    assert [w["thresholds"] for w in report["wearers"]] == [[1000.0] * 4, [FLT_MAX] * 4]
    toc, toc2 = parse_toc(data), parse_toc(out)
    at = lod0["bmsh"]
    assert out[toc2[at].file_offset:toc2[at].file_offset + toc2[at].size] == \
        data[toc[at].file_offset:toc[at].file_offset + toc[at].size]
    grew = own_runs(out, BODY)["bytes"] - own_runs(data, BODY)["bytes"]
    assert said == [f"  Player model: {BODY}'s shadow LOD (W36): LOD 1, {lod1['triangles']} of LOD 0's 5151 "
                    f"triangles (cut at {dm.SHADOW_RATIO:g} within {dm.SHADOW_ERROR * 100:g} cm), drawn only in "
                    f"garret4's realtime shadow, {grew / 2 ** 20:.2f} MiB more own runs; town_female_2's "
                    "lodThreshold1 past its farClip, so no screen draws it"] and added == grew
    lod0_in = bc.read_asset(data, BODY).lods[0]   # Step 2.179: a cut started ahead of this LOD 0 is the one W36 takes
    assert dm.cut_ahead(lod0_in, dm.SHADOW_RATIO, mesh=named["mesh"]) and dm._AHEAD[0] is None   # kept: none starts
    with monkeypatch.context() as here:
        here.setattr(dm, "decimate", None)   # this process cuts nothing
        game, engine, _ = worn("town_female_2")
        assert write_shadow_lod(game, engine, BODY, **named) == (said, added) and game["characters.xbr"] == out
    dm.cut_ahead(lod0_in, dm.SHADOW_RATIO / 2, mesh=named["mesh"])   # one at another share isn't
    game, engine, _ = worn("town_female_2")
    assert write_shadow_lod(game, engine, BODY, **named) == (said, added) and game["characters.xbr"] == out
    monkeypatch.setattr(mi, "own_runs", lambda *_a, **_k: {"bytes": 15 * mi.MiB, "runs": 2, "largest": mi.MiB,
                                                            "by_tag": {}})
    monkeypatch.setattr(mi, "budget_of", lambda _xbe: mi.ROOM)
    monkeypatch.setattr(mi, "lines_ram", lambda _xbe, _ram: 64)
    monkeypatch.setattr(mi, "lines_for", lambda _budget, _tier: (14 * mi.MiB, 12 * mi.MiB))
    for shadow, named in ((2 * mi.MiB, True), (mi.MiB // 2, False)):   # 15 MiB past a 14 MiB line, 13 or 14.5 without it
        with pytest.raises(ValueError, match="make its mesh or clips smaller") as refused:
            _load_budget({"default.xbe": b"", "characters.xbr": b""}, BODY, "who", False, 64, shadow)
        assert ('or "lods": {"shadow": false} (W36\'s shadow LOD added 2.00 MiB)' in str(refused.value)) is named
    game, engine, _ = worn("catalisk")
    with pytest.raises(ValueError, match="lods.shadow: catalisk has 4 LODs, and the shadow draws its own LOD 1"):
        write_shadow_lod(game, engine, "catalisk", True)

def test_a_variants_lods_read_back_switching_at_its_distance_and_ride_in_the_players_copy(usa, building, monkeypatch):
    """W39 (Step 2.166d, D537's L4): female_2 worn by garret4 with a
    recipe's ``"lods": {"ratio": [0.3], "at": [9]}`` takes a LOD 1 cut
    anew from her LOD 0 (byte for byte), which reads back clean: garret4
    switches to it past 9 m (his other cells his farClip) and
    town_female_2 past her own 15 m, and the realtime shadow draws it, so
    W36 adds no shadow LOD (its line lowered under her 5,151 triangles);
    W38's copy of her body for the player carries both LODs.  ``"ratio":
    []`` drops catalisk's three LODs past her LOD 0."""
    from azurkit.tools.characters import decimate as dm
    from azurkit.tools.characters.paint import skin_key, write_colours
    from azurkit.tools.characters._player_character import write_lods, write_shadow_lod
    from azurkit.tools.characters._player_variants import Lods, _colours
    from azurkit.tools.characters.ports import XbrDocument
    from azurkit.tools.characters.ports import point_keyed_string

    data = usa("gamedata/characters.xbr")

    def worn(body: str):
        doc = XbrDocument.from_bytes(usa("gamedata/config.xbr"))
        engine = doc.keyed_section("critters_engine")
        point_keyed_string(engine, "garret4", "body", body, "body")
        return {"characters.xbr": bytearray(data)}, engine, doc
    game, engine, doc = worn("town_female_2")
    said, added = write_lods(game, engine, BODY, Lods((0.3,), (9.0,)))
    out = bytes(game["characters.xbr"])
    report = inspect(out, BODY, config_xbr=bytes(doc.raw))
    lod0, lod1 = report["lods"]
    assert report["problems"] == [] and [lod0["drawn"], lod1["drawn"]] == ["steady", "steady"]
    assert 0.25 * 5151 < lod1["triangles"] <= 0.3 * 5151 and lod1["run_bytes"] > 0
    assert [(w["species"], w["thresholds"], w["steady"], w["shadow_lod"]) for w in report["wearers"]] == [
        ("garret4", [9.0, 1000.0, 1000.0, 1000.0], [0, 1], 1), ("town_female_2", [15.0, 20.0, 25.0, 30.0], [0, 1], None)]
    toc, toc2 = parse_toc(data), parse_toc(out)
    at = lod0["bmsh"]
    assert out[toc2[at].file_offset:toc2[at].file_offset + toc2[at].size] == \
        data[toc[at].file_offset:toc[at].file_offset + toc[at].size]
    grew = own_runs(out, BODY)["bytes"] - own_runs(data, BODY)["bytes"]
    assert said == [f"  Player model: {BODY}'s LODs (W39): LOD 1 {lod1['triangles']} of LOD 0's 5151 triangles (cut at "
                    f"0.3), garret4 switching at 9 m, town_female_2 at its own 15 m; its realtime shadow draws LOD 1; "
                    f"{grew / 2 ** 20:.2f} MiB more own runs"] and added == grew > 0
    monkeypatch.setattr(dm, "SHADOW_MIN", 5000)
    assert write_shadow_lod(game, engine, BODY) == ([], 0) and game["characters.xbr"] == out
    index = usa("gamedata/index/index.xbr")
    copied, _, _ = write_colours(out, index, BODY, _colours("colours", [{"ops": [{"op": "hsv", "hue": 120}]}]))
    mine = bc.read_asset(copied, skin_key(BODY)[len("characters/"):])
    assert [drawn(lod) for lod in mine.lods] == [5151, lod1["triangles"]]
    assert inspect(copied, skin_key(BODY)[len("characters/"):])["problems"] == []
    game, engine, _ = worn("catalisk")
    said, added = write_lods(game, engine, "catalisk", Lods(()))
    assert [drawn(lod) for lod in bc.read_asset(bytes(game["characters.xbr"]), "catalisk").lods] == [
        drawn(bc.read_asset(data, "catalisk").lods[0])]
    assert said == [f"  Player model: catalisk's 3 LODs past LOD 0 dropped (W39), {-added / 2 ** 20:.2f} MiB fewer own "
                    "runs"] and added < 0

def test_a_mesh_edit_of_a_body_with_lods_cuts_them_anew_from_its_edited_lod_0(usa, usa_iso, building, monkeypatch):
    """Step 2.166d (D537's design 0(b)): a variant's mesh may edit a body
    with LODs of its own (catalisk's four; refused before), and the build
    runs W39 for it with no ``lods`` (the vanilla image beside it), which
    cuts its LODs 1-3 anew from the edited LOD 0 at their vanilla shares
    of its triangles: four LODs read back clean, LOD 0 as the edit wrote
    it, LODs 1-3 appended and drawn from its edited vertices (moved ones
    among them), the old ones unreferenced, garret4's switch distances
    his.  The build (``model dress``'s) stops after W39."""
    from azurkit.tools.characters import _player_character as pc
    from azurkit.tools.characters._player_variants import load_variants
    from devkit.models import dress as dressing

    data = usa("gamedata/characters.xbr")
    op = {"op": "scale", "bone": "head", "radius": [0.6, 0.6, 0.6], "factors": [1.3, 1.3, 1.3]}
    variant = load_variants(json.dumps({"bigheaded": {"base": "catalisk", "mesh": {"ops": [op]}}}),
                            "test")["bigheaded"]
    seen = {}

    class Stop(Exception):
        pass

    def w39(game, engine, body, spec, vanilla=None, **kw):
        seen.update(body=body, spec=spec, vanilla=vanilla, edited=bytes(game["characters.xbr"]))
        seen["said"], seen["added"] = write_lods(game, engine, body, spec, vanilla, **kw)
        seen.update(out=bytes(game["characters.xbr"]), config=bytes(engine.document.raw))
        raise Stop
    write_lods = pc.write_lods
    monkeypatch.setattr(pc, "write_lods", w39)
    with pytest.raises(Stop):
        dressing.dress(variant, usa_iso)
    assert (seen["body"], seen["spec"], seen["vanilla"] == data) == ("catalisk", None, True)
    edited, out, said, added = seen["edited"], seen["out"], seen["said"], seen["added"]
    vanilla, entry, back = (bc.read_asset(x, "catalisk") for x in (data, edited, out))
    count = len(parse_toc(edited))
    assert [lod.bmsh for lod in back.lods] == [entry.lods[0].bmsh, count, count + 1, count + 2]
    assert inspect(out, "catalisk")["problems"] == [] and not bc._users(out, entry.lods[1].bmsh)
    toc, toc2 = parse_toc(edited), parse_toc(out)
    at = entry.lods[0].bmsh
    assert out[toc2[at].file_offset:toc2[at].file_offset + toc2[at].size] == \
        edited[toc[at].file_offset:toc[at].file_offset + toc[at].size]
    mine = {v.position for g in back.lods[0].groups for v in g.vertices}
    moved = mine - {v.position for g in vanilla.lods[0].groups for v in g.vertices}
    for lod in back.lods[1:]:
        assert {v.position for g in lod.groups for v in g.vertices} <= mine
    assert moved & {v.position for g in back.lods[1].groups for v in g.vertices}
    shares = [drawn(lod) / drawn(vanilla.lods[0]) for lod in vanilla.lods[1:]]
    assert said == [f"  Player model: catalisk's 3 LODs past LOD 0 cut anew from its edited LOD 0 at their vanilla "
                    "shares (W39): " + ", ".join(f"LOD {k} {drawn(lod)} triangles ({r:.3g} of LOD 0's)"
                                                 for k, (lod, r) in enumerate(zip(back.lods[1:], shares), 1))
                    + f"; its wearers switch at their own distances; {added / 2 ** 20:+.2f} MiB own runs"]
    report = inspect(out, "catalisk", config_xbr=seen["config"])
    assert [w["thresholds"] for w in report["wearers"] if w["species"] == "garret4"] == [[1000.0] * 4]


# --------------------------------------------------------------------------- paint and colours

def _quad() -> paint.View:
    """Two triangles, a 1 x 1 quad at z 1 facing +y, one bone, group 0: their new UVs the whole texture, their old
    UVs (each corner's) its left half."""
    pos = np.array([[0.0, 0.0, 1.0], [1.0, 0.0, 1.0], [1.0, 0.0, 2.0], [0.0, 0.0, 2.0]])
    tris = np.array([[0, 1, 2], [0, 2, 3]])
    uvs = np.array([[0.0, 1.0], [1.0, 1.0], [1.0, 0.0], [0.0, 0.0]])
    old = uvs * np.array([0.5, 1.0])
    return paint.View(pos, np.tile([0.0, 1.0, 0.0], (4, 1)), uvs, old[tris], pos.copy(), np.zeros(4, int),
                      np.zeros(4, int), tris, ("root",), ((0.0, 0.0, 0.0),), (-1,))

def test_a_bake_redraws_the_old_texture_through_new_uvs_and_paints_only_its_hue_window():
    """The bake draws each texel the triangles cover from the old texture at the same surface point's old UV (the
    old texture's left half, red over blue, stretched over the whole new one, at twice the size), and a ``skin`` op
    turns only the texels in its hue window (the red) to the median of its ``from`` texels in its ``match`` window
    (the blue), the blue kept."""
    src = np.zeros((8, 8, 4), np.uint8)
    src[..., 3] = 255
    src[:4, :4, :3] = (200, 30, 30)        # the left half's top: red
    src[4:, :4, :3] = (20, 60, 200)        # its bottom: blue
    src[:, 4:, :3] = (0, 200, 0)           # the right half (no old UV reaches it): green
    view = _quad()
    plain = paint.bake(view, src, (0,), paint.TextureSpec(1, 16))
    assert plain.shape == (16, 16, 4)
    assert (plain[2, 2, :3] == (200, 30, 30)).all() and (plain[13, 13, :3] == (20, 60, 200)).all()
    assert not (plain[..., 1] == 200).any()        # nothing of the right half comes through
    skin = paint.PaintOp("skin", paint.Region(), {"hue": (330.0, 30.0), "sat": 0.2, "value": 0.1},
                         paint.Region())
    painted = paint.bake(view, src, (0,), paint.TextureSpec(1, 16, ops=(skin,)))
    assert (painted[2, 2, :3] == (20, 60, 200)).all() and (painted[13, 13, :3] == (20, 60, 200)).all()

def test_a_bake_samples_the_old_texture_padded_past_its_triangles_so_an_islands_edge_takes_nothing_from_beyond():
    """Round 9 (D552, her face's midline seam): the old texture is padded from the texels the triangles' old UVs
    cover before the bake samples it, so the new texels along the old island's edge (the quad's old UVs end at the
    texture's middle) stay the island's red, not mixed with the black past it."""
    src = np.zeros((8, 8, 4), np.uint8)
    src[..., 3] = 255
    src[:, :4, :3] = (200, 30, 30)         # the left half (the old UVs'): red; the right half black
    out = paint.bake(_quad(), src, (0,), paint.TextureSpec(1, 16)).astype(int)
    assert (out[:, 15, :3] == (200, 30, 30)).all()

def test_strands_streak_only_dark_texels_along_v_and_add_a_sheen_where_the_surface_faces_the_light():
    """Round 4 (D485): a ``strands`` op adds faint streaks to the texels at most ``below`` in value (black hair), the
    same down each column of the texture (along v) and different across it, plus its ``sheen`` where the surface
    faces its light, all in its tint; the red texels are left as they were.  Round 6 (D512, "blacker"): ``dark``
    scales those texels first."""
    src = np.zeros((8, 8, 4), np.uint8)
    src[..., 3] = 255
    src[:4, :4, :3] = (200, 30, 30)        # the top: red
    view = _quad()
    hair = paint.PaintOp("strands", paint.Region(), {"below": 0.12, "count": 3.0, "value": 0.12, "sheen": 0.0})
    out = paint.bake(view, src, (0,), paint.TextureSpec(0, 32, ops=(hair,))).astype(int)
    black = out[20:29, 4:28, :3]
    assert (out[3:12, 4:28, :3] == (200, 30, 30)).all()
    assert np.ptp(black, axis=0).max() <= 1 and np.ptp(black[0, :, 2]) > 10 and black.max() <= round(0.12 * 0.8 * 255)
    lit = paint.PaintOp("strands", paint.Region(), {"value": 0.0, "sheen": 0.2, "from": (0.0, 1.0, 0.0)})
    shone = paint.bake(view, src, (0,), paint.TextureSpec(0, 32, ops=(lit,))).astype(int)
    assert (shone[20:29, 4:28, :3] == np.round(0.2 * np.array([0.55, 0.62, 0.8]) * 255)).all()
    src[4:, :, :3] = 20
    plain = paint.PaintOp("strands", paint.Region(), {"value": 0.0, "sheen": 0.0})
    dark = paint.PaintOp("strands", paint.Region(), {"value": 0.0, "sheen": 0.0, "dark": 0.5})
    a, b = (paint.bake(view, src, (0,), paint.TextureSpec(0, 32, ops=(o,))).astype(int) for o in (plain, dark))
    assert (a[20:29, 4:28, :3] == 20).all() and (b[20:29, 4:28, :3] == 10).all() and (b[3:12] == a[3:12]).all()

def test_a_fill_paints_its_regions_texels_one_colour_mixed_by_its_share_and_leaves_the_rest():
    """Round 8 (D533, a blue gem on a material with no blue; D552, a lip colour over her face's shading, her eyes'
    whites apart from their lids): a ``fill`` op gives every texel of the triangles its region selects (by place, or
    by a ``uv`` rect their new UVs lie in) its ``colour``, or with ``mix`` that share of it over the texel's own; the
    texels of the triangles it leaves out keep the old texture's."""
    src = np.zeros((8, 8, 4), np.uint8)
    src[..., 3] = 255
    src[:, :4, :3] = (200, 30, 30)         # the old texture's left half: red
    view = _quad()
    region = paint.Region("root", radius=(0.5, 0.5, 0.5), offset=(1.0, 0.0, 1.0))
    gem = paint.PaintOp("fill", region, {"colour": (0.1, 0.3, 0.9)})
    out = paint.bake(view, src, (0,), paint.TextureSpec(0, 16, ops=(gem,))).astype(int)
    assert (out[13, 13, :3] == (26, 76, 230)).all()        # the first triangle's (its centroid near (1, 0, 1))
    assert (out[2, 2, :3] == (200, 30, 30)).all()          # the second's, left as it was
    lip = paint.PaintOp("fill", region, {"colour": (0.0, 0.0, 1.0), "mix": 0.5})
    out = paint.bake(view, src, (0,), paint.TextureSpec(0, 16, ops=(lip,))).astype(int)
    assert (abs(out[13, 13, :3] - (100, 15, 143)) <= 1).all() and (out[2, 2, :3] == (200, 30, 30)).all()
    eye = paint.PaintOp("fill", paint.Region(uv=(0.5, 0.5, 1.0, 1.0)), {"colour": (0.1, 0.3, 0.9)})
    out = paint.bake(view, src, (0,), paint.TextureSpec(0, 16, ops=(eye,))).astype(int)
    assert (out[13, 13, :3] == (26, 76, 230)).all() and (out[2, 2, :3] == (200, 30, 30)).all()

def test_a_feathered_region_eases_its_op_in_by_each_texels_place_not_by_its_triangles_edges():
    """Round 7 (D512, her neck's jagged edge): a region's ``feather`` picks texels by their own rest place and eases
    the op in over that distance inside its ``z`` band's edge, so the edge runs level across the quad (each texel row
    one colour) and fades over the band; with none, the edge follows the triangles' diagonal (a row half each)."""
    src = np.zeros((8, 8, 4), np.uint8)
    src[..., 3] = 255
    src[:, :4, :3] = (200, 30, 30)         # the old texture's left half: red
    view = _quad()

    def bake(**kw):        # the red texels to half their own red (the skin colour: the red's median, lifted 0.5)
        op = paint.PaintOp("skin", paint.Region(None, z=(0.0, 1.5), **kw), {
            "hue": (330.0, 30.0), "sat": 0.2, "value": 0.1, "match": (330.0, 30.0), "lift": 0.5}, paint.Region())
        return paint.bake(view, src, (0,), paint.TextureSpec(1, 32, ops=(op,))).astype(int)
    crisp, soft = bake(), bake(feather=0.25)
    # a texel row r is at z 2 - (r + 0.5) / 32: rows 0-15 above the band (z > 1.5), 16-23 its feathered edge
    assert np.ptp(crisp[12, 6:26, 0]) > 90                      # crisp: the triangles' diagonal splits the row
    assert np.ptp(soft[2:30, 6:26, 0], axis=1).max() <= 2       # feathered: every row level
    reds = soft[2:30, 16, 0]
    assert (reds[:14] == 200).all() and (np.diff(reds) <= 0).all() and (reds[22:] == 100).all()
    assert 100 < reds[17] < 200

def test_a_sharpen_steepens_an_edge_the_bake_stretched_and_leaves_the_flat_texels_round_it():
    """Step 2.177d (D698: her face's detail from her paint source at the face's own scale): a ``sharpen`` op adds
    ``amount`` of each texel's difference from its blur, the blur ``texels`` source texels wide at the region's own
    stretch (here 64 new texels a side from 8 x 16 old ones), so the step the bilinear bake drew as a ramp is steeper
    and the flat texels away from it keep their colour."""
    src = np.zeros((16, 16, 4), np.uint8)
    src[..., 3] = 255
    src[:, :4, :3] = 40                    # the old UVs' half: dark, then light
    src[:, 4:8, :3] = 200
    view = _quad()
    sharp = paint.PaintOp("sharpen", paint.Region(), {"amount": 1.0, "texels": 0.6})
    plain, out = (paint.bake(view, src, (0,), paint.TextureSpec(0, 64, ops=ops)).astype(int)[32, :, 0]
                  for ops in ((), (sharp,)))
    assert out[35] - out[29] > plain[35] - plain[29] + 20
    assert (abs(out[12:21] - plain[12:21]) <= 1).all() and (abs(out[44:53] - plain[44:53]) <= 1).all()

def test_recolour_keeps_untouched_blocks_and_every_stored_level():
    """Step 2.170b (D539, W38): a ``colours`` op runs on every level a texture stores, re-encoded in its own format
    at its own offsets: no-op ops give the payload back byte for byte, a block no texel of which changes keeps its
    bytes (the grey half under a red hue window), and hue +120 turns the red half green on each level within the
    encoder's error (DXT1, DXT3 and BGRA8); a ``swap`` from the red to a tan keeps its shading (the darker red stays
    the darker tan); ``spread`` 0 puts every hue of a window at its middle; a list or a payload too short for its
    chain is refused by name."""
    import pytest

    from azurkit.tools.characters import textures

    img = np.full((16, 16, 4), 255, np.uint8)
    img[:, :8, :3] = (200, 30, 30)         # the left half red
    img[:, 8:, :3] = (128, 128, 128)       # the right half grey
    img[8:, :8, :3] = (100, 15, 15)        # the red's bottom quarter darker
    hsv = paint.PaintOp("hsv", paint.Region(), {"hue": 120.0, "window": (330.0, 30.0)})
    swap = paint.PaintOp("swap", paint.Region(), {"from": (200 / 255, 30 / 255, 30 / 255), "to": (0.88, 0.7, 0.55)})
    noop = paint.PaintOp("hsv", paint.Region(), {"window": (100.0, 140.0), "soft": 0.0})
    for fmt in textures.FORMATS.values():
        payload = textures.surf(img, fmt)
        assert paint.recolour(payload, (noop,)) == payload
        green = paint.recolour(payload, (hsv,))
        at, olds = 40 + 88, textures.levels(payload)
        for level, (old, new) in enumerate(zip(olds, textures.levels(green))):
            lw = old.shape[1]
            n = textures.level_bytes(fmt, lw, lw)
            if level == 0 and fmt in textures.BLOCK:    # the grey blocks' bytes as they were
                size, bw = textures.BLOCK[fmt], lw // 4
                for by in range(lw // 4):
                    for bx in range(2, 4):
                        k = at + (by * bw + bx) * size
                        assert green[k:k + size] == payload[k:k + size]
            reds = old[..., 0].astype(int) - old[..., 1] > 100
            if reds.any():
                assert (new[reds][:, 1].astype(int) - new[reds][:, 0] > 100).all(), (fmt, level)
                assert (np.abs(new[reds][:, 1].astype(int) - old[reds][:, 0]) <= 16).all(), (fmt, level)
            assert (new[..., 3] == old[..., 3]).all()
            at += n
        tan = textures.levels(paint.recolour(payload, (swap,)))[0].astype(int)
        assert abs(tan[2, 2, 0] - 224) <= 12 and abs(tan[2, 2, 2] - 140) <= 12, fmt
        assert tan[12, 2, :3].sum() < tan[2, 2, :3].sum() * 0.6       # the shading kept
        assert (np.abs(tan[:, 8:, :3] - 128) <= 4).all()                # the grey untouched
    blues = np.full((4, 4, 4), 255, np.uint8)
    blues[:2, :, :3], blues[2:, :, :3] = (20, 100, 200), (60, 20, 200)      # hues 213 and 252
    narrow = paint.PaintOp("hsv", paint.Region(), {"window": (190.0, 270.0), "spread": 0.0})
    hue = paint.hsv_of(textures.levels(paint.recolour(textures.surf(blues, 0x10), (narrow,)))[0][..., :3] / 255.0)[0]
    assert np.allclose(hue, 230.0, atol=1.0)        # spread 0: every hue in the window at its middle
    with pytest.raises(ValueError, match="an animated list has no texels"):
        paint.recolour(textures.list_surf([1, 2])[0], (hsv,))
    wide = bytearray(textures.surf(img, 0x10))
    wide[28:32] = np.float32(32.0).tobytes()
    with pytest.raises(ValueError, match="a 32x16 texture: its 1536 B hold no whole chain of its levels"):
        paint.recolour(bytes(wide), (hsv,))

def test_a_png_colour_op_is_its_rows_texture_at_every_stored_level_in_its_format_and_the_ops_after_it_recolour_it(
        tmp_path):
    """D544 (Step 2.203, the PNG round trip): a ``colours`` entry's ``png`` op (its file beside the recipe, its
    sha256 checked) makes the texture the PNG, alpha too, every level it stores the PNG's box-filtered level of that
    size, in the texture's own format (BGRA8 byte for byte as a new surf of it; DXT within the encoder's error, a
    block whose texels the PNG keeps keeping its bytes); the ops before it (the every-row ones) are replaced, those
    after it recolour it.  Refused by name: a PNG of another size, one whose sha256 isn't the recipe's, one with no
    folder, and in the loader a png op on every row or after another op."""
    import hashlib

    import pytest

    from azurkit.tools.characters import textures
    from azurkit.tools.characters._player_variants import _colours
    from azurkit.tools.characters.draw import png_rgba

    img = np.full((16, 16, 4), 255, np.uint8)
    img[:, :8, :3] = (200, 30, 30)         # the texture: its left half red, its right half grey
    img[:, 8:, :3] = (128, 128, 128)
    hue = paint.PaintOp("hsv", paint.Region(), {"hue": 120.0, "window": (190.0, 270.0)})   # blue to red
    for fmt in textures.FORMATS.values():
        payload = textures.surf(img, fmt)
        edit = textures.levels(payload)[0].copy()        # the texture as exported, its left half painted blue
        edit[:, :8, :3], edit[:4, :4, 3] = (20, 40, 220), 0
        (tmp_path / "row0.png").write_bytes(png_rgba(edit))
        ref = {"file": "row0.png", "sha256": hashlib.sha256((tmp_path / "row0.png").read_bytes()).hexdigest()}
        (spec,) = paint.located(_colours("colours", [{"row": 0, "ops": [{"op": "png", **ref}]}]), tmp_path)
        made = paint.recolour(payload, (hue, *spec.ops))     # the every-row hsv first: the png replaces it
        assert textures.info(made) == textures.info(payload) and len(made) == len(payload)
        chain = textures.chain(edit)
        if fmt == 0x10:
            assert made == textures.surf(edit, fmt)
        for level, (got, want) in enumerate(zip(textures.levels(made), chain)):
            seen = want[..., 3] >= 128                  # a DXT1 texel under alpha 128 is black, transparent
            assert np.abs(got[seen][:, :3].astype(int) - want[seen][:, :3]).max() <= 24, (fmt, level)
        assert (textures.levels(made)[0][..., 3] == edit[..., 3]).all() or fmt == 0x40   # DXT3's 4-bit alpha
        if fmt in textures.BLOCK:                       # the grey half's blocks: the payload's bytes
            size, at = textures.BLOCK[fmt], 128
            for by in range(4):
                k = at + (by * 4 + 2) * size
                assert made[k:k + 2 * size] == payload[k:k + 2 * size], (fmt, by)
        red = textures.levels(paint.recolour(payload, (*spec.ops, hue)))[0]
        assert (red[8:, :8, 0].astype(int) - red[8:, :8, 2] > 100).all()
        assert (red[:, 8:] == textures.levels(payload)[0][:, 8:]).all()     # the grey as the texture stores it
    small = tmp_path / "small.png"
    small.write_bytes(png_rgba(np.zeros((8, 8, 4), np.uint8)))
    (spec,) = paint.located((paint.ColourSpec(0, (paint.PaintOp("png", paint.Region(), {
        "file": "small.png", "sha256": hashlib.sha256(small.read_bytes()).hexdigest()}),)),), tmp_path)
    with pytest.raises(ValueError, match="png small.png is 8x8, its texture 16x16"):
        paint.recolour(textures.surf(img, 0x20), spec.ops)
    wrong = [{"row": 0, "ops": [{"op": "png", "file": "small.png", "sha256": "0" * 64}]}]
    with pytest.raises(ValueError, match="png small.png: its sha256 is [0-9a-f]{64}, not the recipe's 0{64}"):
        paint.located(_colours("colours", wrong), tmp_path)
    with pytest.raises(ValueError, match="png small.png: no folder holds the recipe's files"):
        paint.located(_colours("colours", wrong), None)
    for entry in ({"ops": wrong[0]["ops"]}, {"row": 0, "ops": [{"op": "hsv", "hue": 9}, *wrong[0]["ops"]]}):
        with pytest.raises(ValueError, match="a png op is a row's texture: first in an entry naming its row"):
            _colours("colours", [entry])


def test_a_variants_rows_export_as_png_and_an_edited_one_is_its_rows_texture_in_the_players_copy(usa, usa_iso, tmp_path,
                                                                                                 capsys):
    """D544 (Step 2.203, the PNG round trip): ``model export --variant`` writes each row town_female_3's LOD 0 draws
    with a texture as the recipe's build recolours it (hue +120 on every row), at the texture's own size; an edited
    one (row 0's, a square painted blue), named by row 0's ``png`` op beside the recipe with a hue window after it,
    is row 0's texture in the player's copy a build makes (``characters/<body>/v/skin``): every level it stores
    re-encoded from the PNG in its own format (``paint.recolour``'s bytes), its base level the PNG's within DXT's
    error, the blue turned red, the hue +120 not run twice; the NPCs' row keeps vanilla's texture.  A second export
    into the folder is refused (an edited PNG is never overwritten)."""
    from azurkit.tools.characters import render, textures
    from azurkit.tools.characters._player_variants import load_variants
    from azurkit.tools.characters.draw import png_rgba
    from devkit.models import dress as dressing

    hue = {"op": "hsv", "hue": 120}
    folder, out = tmp_path / "mine", tmp_path / "out"
    folder.mkdir()
    file = folder / "recipe.json"
    file.write_text(json.dumps({"mine": {"base": "town_female_3", "colours": [{"ops": [hue]}]}}), encoding="utf-8")
    argv = ("export", "--variant", "mine", "--variant-file", str(file), "--out", str(out), "--iso", str(usa_iso))
    assert _run(capsys, *argv)[0] == 0
    stored = usa("gamedata/characters.xbr")
    toc, body = parse_toc(stored), "townspeople/female_3"
    surfs = {row: render.material(stored, toc, g, row)["textures"][0]
             for g, row in sorted(set(paint.materials(stored, body).values()))}
    assert sorted(p.name for p in out.iterdir()) == [f"mine_row{r}.png" for r in sorted(surfs)] == [
        f"mine_row{r}.png" for r in range(4)]
    tint = paint.located(load_variants(file.read_text(encoding="utf-8"), str(file))["mine"].colours, folder)[0].ops
    for r, surf in surfs.items():
        assert (textures.read_png((out / f"mine_row{r}.png").read_bytes())
                == paint.recoloured(render.surf_image(stored, toc, surf), tint)).all(), r

    edit = textures.read_png((out / "mine_row0.png").read_bytes())
    edit[:32, :32, :3] = (20, 40, 220)
    (folder / "row0.png").write_bytes(png_rgba(edit))
    png = {"op": "png", "file": "row0.png", "sha256": hashlib.sha256((folder / "row0.png").read_bytes()).hexdigest()}
    window = {"op": "hsv", "hue": 120, "window": [200, 260], "soft": 0}
    file.write_text(json.dumps({"mine": {"base": "town_female_3", "colours": [
        {"ops": [hue]}, {"row": 0, "ops": [png, window]}]}}), encoding="utf-8")
    variant = load_variants(file.read_text(encoding="utf-8"), str(file))["mine"]
    built = bytes(dressing.dress(variant, usa_iso).game["characters.xbr"])
    btoc, names = parse_toc(built), named_resources(built)
    copy = next(i for i, n in names.items() if n == f"characters/{body}/v/skin")
    (cg,) = [g for g, r in paint.drawn_rows(built, btoc, copy) if r == 0]
    (npc,) = [g for g, r in set(paint.materials(built, body).values()) if r == 0]
    made = render.material(built, btoc, cg, 0)["textures"][0]
    payload = built[btoc[made].file_offset:btoc[made].file_offset + btoc[made].size]
    every, row0 = paint.located(variant.colours, folder)
    vanilla = stored[toc[surfs[0]].file_offset:toc[surfs[0]].file_offset + toc[surfs[0]].size]
    assert payload == paint.recolour(vanilla, every.ops + row0.ops)      # every level, in its own format
    assert textures.info(payload) == textures.info(vanilla)
    got, want = textures.levels(payload)[0], paint.recoloured(edit, row0.ops[1:])
    seen = want[..., 3] >= 128
    assert np.abs(got[seen][:, :3].astype(int) - want[seen][:, :3]).mean() <= 1        # the PNG's, not hue +120 again
    assert (got[4:28, 4:28, 0].astype(int) - got[4:28, 4:28, 2] > 100).all()           # the blue square red
    assert render.material(built, btoc, npc, 0)["textures"][0] == surfs[0] != made
    code, _, err = _run(capsys, *argv)
    assert code == 1 and "already holds something" in err


def test_a_recipe_on_garret4_with_a_look_exports_its_rows_recoloured_once(usa, usa_iso, tmp_path, capsys):
    """Step 2.206 (the rebase review's D2): a recipe on garret4's own body whose build changes his body (a mesh op)
    and recolours his own rows in place: ``model export --variant`` writes each row his vanilla texture recoloured
    once (hue +120, not +240: ``colour_preview.uncoloured`` dresses him without his colours)."""
    from azurkit.tools.characters import render, textures
    from azurkit.tools.characters._player_variants import load_variants

    op = {"op": "scale", "bone": "spine_2", "radius": [0.2, 0.2, 0.2], "factors": [1.2, 1.2, 1.2]}
    file, out = tmp_path / "recipe.json", tmp_path / "out"
    file.write_text(json.dumps({"g4c": {"base": "garret4", "mesh": {"ops": [op]},
                                        "colours": [{"ops": [{"op": "hsv", "hue": 120}]}]}}), encoding="utf-8")
    (hue,) = load_variants(file.read_text(encoding="utf-8"), str(file))["g4c"].colours
    assert _run(capsys, "export", "--variant", "g4c", "--variant-file", str(file), "--out", str(out),
                "--iso", str(usa_iso))[0] == 0
    vanilla = usa("gamedata/characters.xbr")
    toc = parse_toc(vanilla)
    surfs = {row: render.material(vanilla, toc, g, row)["textures"][0]
             for g, row in sorted(set(paint.materials(vanilla, "garret4").values()), key=lambda m: (m[1], m[0]))
             if render.material(vanilla, toc, g, row).get("textures")}
    assert sorted(p.name for p in out.iterdir()) == sorted(f"g4c_row{r}.png" for r in surfs) != []
    for r, s in surfs.items():
        assert (textures.read_png((out / f"g4c_row{r}.png").read_bytes())
                == paint.recoloured(render.surf_image(vanilla, toc, s), hue.ops)).all(), r
