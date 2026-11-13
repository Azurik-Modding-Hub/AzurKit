"""``python -m devkit models clip-rest``: a variant's clip files re-rested on
the bones its own build places (the booblord pass's E3), so its recipe needs
no ``places``.

A clip file holds every bone's rest, and a build reads it only where each
node's rest is the dressed body's within 1e-5 (``clip_import``'s check). A
variant's jiggle bones are placed where the vertices they take sit
(``jiggle.rig``), so a reshaped mesh moves them and its clips stop holding;
a recipe's ``places`` pins them where another mesh's build put them
(booblord_high's are booblord's). This verb dresses the variant's mesh and
jiggle twice on the vanilla body, as a build's first stages do
(``_player_character._variant_body``: W24, W29 and W30): as its recipe
places them (the body its files hold on today) and with no ``places`` (its
own build's), then writes each ``.glb`` its ``gltf`` clip rows name (in its
clip folder: the content folder's for a built-in) with each jiggle bone's
node at its new rest and that bone's translation keys moved by as much (a
key is the bone's place, so the move keeps its motion about its rest; a
rotation or scale key is the same at any rest). A rest that turns, or a
keys accessor another channel shares, is refused by name.

Before it writes, it reads every animation of each new file on the new body
(the build's own read and 1e-5 check) and of the old file on the old one, and
compares the clips: every track of a bone that isn't a jiggle bone must be
the old clip's, or (the build thins a bone's turns by how far its farthest
child sits, which a moved jiggle bone under it changes) pose that bone within
twice the thinning's tolerance of the old clip, else it prints the clip and
bone and writes nothing (exit 1).
It prints each clip's tracks compared, each jiggle bone's move (mm), each new
file's size and sha256, and the ``clips`` rows that take them. Names, counts
and hashes only (the files are game assets: never commit or share them but
as the content repository's).

    uv run --locked python -m devkit models clip-rest booblord --recipe pick.json --out DIR [--variant-file PATH] [--iso PATH]
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
import shutil
import struct
import sys
import tempfile
import time
from pathlib import Path

from devkit.models import image

_GLB, _JSON, _BIN = b"glTF", 0x4E4F534A, 0x004E4942
_FLOAT = 5126


def read_glb(data: bytes) -> tuple[dict, bytes]:
    """A ``.glb``'s JSON document and its BIN chunk; ``ValueError`` for
    anything else (a ``.gltf``, another version, a torn file)."""
    if data[:4] != _GLB or len(data) < 20:
        raise ValueError("not a .glb (clip-rest rewrites a .glb's own chunk)")
    version, length = struct.unpack_from("<II", data, 4)
    size, kind = struct.unpack_from("<II", data, 12)
    if version != 2 or length != len(data) or kind != _JSON or 20 + size > len(data):
        raise ValueError("a .glb that isn't glTF 2's (its version, length or first chunk)")
    doc, at, chunk = json.loads(data[20:20 + size].decode("utf-8")), 20 + size, b""
    if at + 8 <= len(data):
        size2, kind2 = struct.unpack_from("<II", data, at)
        if kind2 != _BIN or at + 8 + size2 > len(data):
            raise ValueError("a .glb whose second chunk isn't its BIN")
        chunk = data[at + 8:at + 8 + size2]
    if any("uri" in b for b in doc.get("buffers", [])) or len(doc.get("buffers", [])) > 1:
        raise ValueError("a .glb with a buffer outside its BIN chunk")
    return doc, chunk


def write_glb(doc: dict, chunk: bytes) -> bytes:
    """``doc`` and ``chunk`` as a ``.glb`` (the JSON padded with spaces and
    the BIN with zeros to four bytes, as glTF has it)."""
    text = json.dumps(doc, separators=(",", ":"), allow_nan=False).encode("utf-8")
    text += b" " * (-len(text) % 4)
    chunk = bytes(chunk) + b"\0" * (-len(chunk) % 4)
    parts = struct.pack("<II", len(text), _JSON) + text + (struct.pack("<II", len(chunk), _BIN) + chunk if chunk
                                                           else b"")
    return _GLB + struct.pack("<II", 2, 12 + len(parts)) + parts


def _f32(values) -> list[float]:
    return [struct.unpack("<f", struct.pack("<f", float(v)))[0] for v in values]


def _off(a, b) -> float:
    """How far two rotations are apart, a component's (q and -q are one)."""
    return min(max(abs(x - y) for x, y in zip(a, b)), max(abs(x + y) for x, y in zip(a, b)))


def rerest(data: bytes, rests: dict[str, tuple], tolerance: float = 1e-5
           ) -> tuple[bytes, dict[str, tuple], tuple[str, ...]]:
    """The ``.glb`` ``data`` with each node ``rests`` names (bone name ->
    (translation, rotation, scale)) at that rest and its translation
    channels' keys moved by the rest's move (a CUBICSPLINE's values, its
    tangents as they are; every key of a LINEAR or STEP one); every other
    byte's meaning kept. Gives the new bytes, each re-rested node's move (its
    parent's frame, float32 as the file holds it) and the names of those
    whose keys moved with it. ``ValueError`` names a
    node whose rest would turn or scale (past ``tolerance``), a keys
    accessor another channel shares, or one that isn't plain float32."""
    doc, chunk = read_glb(data)
    buf = bytearray(chunk)
    named = {str(n.get("name", "")): i for i, n in enumerate(doc.get("nodes", []))}
    moves: dict[int, tuple[float, ...]] = {}
    out: dict[str, tuple] = {}
    for name, (t, r, s) in rests.items():
        if name not in named:
            continue
        node = doc["nodes"][named[name]]
        if "matrix" in node:
            raise ValueError(f"node {name}: a matrix, not a translation, rotation and scale")
        old_t = _f32(node.get("translation", (0.0, 0.0, 0.0)))
        old_r, old_s = node.get("rotation", (0.0, 0.0, 0.0, 1.0)), node.get("scale", (1.0, 1.0, 1.0))
        new_t, new_r, new_s = _f32(t), _f32(r), _f32(s)
        if _off(old_r, new_r) > tolerance or max(abs(x - y) for x, y in zip(old_s, new_s)) > tolerance:
            raise ValueError(f"node {name}: its rest would turn or scale (clip-rest moves a rest, its keys after it)")
        node["translation"], node["rotation"], node["scale"] = new_t, new_r, new_s
        move = tuple(b - a for a, b in zip(old_t, new_t))
        moves[named[name]] = out[name] = move
    uses: dict[int, set] = {}
    for anim in doc.get("animations", []):
        for c in anim["channels"]:
            s = anim["samplers"][c["sampler"]]
            uses.setdefault(s["input"], set()).add(("input",))
            uses.setdefault(s["output"], set()).add((c["target"].get("node"), c["target"]["path"]))
    shifted, keyed = set(), set()
    for anim in doc.get("animations", []):
        for c in anim["channels"]:
            node, path = c["target"].get("node"), c["target"]["path"]
            if node not in moves or path != "translation":
                continue
            s = anim["samplers"][c["sampler"]]
            a = s["output"]
            if uses[a] != {(node, path)}:
                raise ValueError(f"node {doc['nodes'][node].get('name')}: its translation keys' accessor {a} is "
                                 "another channel's too")
            if a not in shifted:
                _shift(doc, buf, a, moves[node], s.get("interpolation", "LINEAR") == "CUBICSPLINE")
                shifted.add(a)
                keyed.add(str(doc["nodes"][node].get("name")))
    return write_glb(doc, bytes(buf)), out, tuple(sorted(keyed))


def _shift(doc: dict, buf: bytearray, index: int, move, cubic: bool) -> None:
    """Accessor ``index``'s keys (a CUBICSPLINE's values: every third
    element from the second) moved by ``move``, its ``min`` and ``max``
    after them."""
    a = doc["accessors"][index]
    if a.get("sparse") or a.get("componentType") != _FLOAT or a.get("type") != "VEC3" or "bufferView" not in a:
        raise ValueError(f"accessor {index}: not plain float32 VEC3 keys")
    view = doc["bufferViews"][a["bufferView"]]
    stride, base, count = view.get("byteStride", 12), view.get("byteOffset", 0) + a.get("byteOffset", 0), a["count"]
    start = view.get("byteOffset", 0)
    end = start + view["byteLength"]
    if end > len(buf) or base < start or base + (count - 1) * stride + 12 > end:
        raise ValueError(f"accessor {index}: past its buffer view")
    values = []
    for j in range(count):
        at = base + j * stride
        v = struct.unpack_from("<3f", buf, at)
        if not cubic or j % 3 == 1:
            struct.pack_into("<3f", buf, at, *(x + d for x, d in zip(v, move)))
            v = struct.unpack_from("<3f", buf, at)
        values.append(v)
    if "min" in a:
        a["min"] = [min(v[c] for v in values) for c in range(3)]
    if "max" in a:
        a["max"] = [max(v[c] for v in values) for c in range(3)]


@dataclasses.dataclass(frozen=True)
class Compared:
    """One animation's clips compared: the tracks of the other bones (equal,
    all), the jiggle bones' (equal, all) and the names of the other bones
    whose tracks differ."""

    others: tuple[int, int]
    placed: tuple[int, int]
    differ: tuple[str, ...]


def drift(old_info, old, new_info, new, bones) -> float:
    """The most (a world matrix entry) ``bones`` (indices) sit apart when the
    clips ``old`` on ``old_info`` and ``new`` on ``new_info`` (``gltf._read``
    bodies) play, at each key time of their tracks and the export's
    evenly spread samples."""
    from azurkit.tools.characters import gltf

    if not bones:
        return 0.0
    times = {old.length * i / (gltf.POSE_SAMPLES - 1) for i in range(gltf.POSE_SAMPLES)}
    times |= {k[0] for c in (old, new) for t in c.bones if t.target in bones for k in t.keys}
    most = 0.0
    for t in sorted(x for x in times if x <= old.length + 1e-6):
        a, b = gltf._engine(old_info, old, t), gltf._engine(new_info, new, t)
        most = max(most, max(float(abs(a[k] - b[k]).max()) for k in bones))
    return most


def compare(old, new, placed: set[int], names) -> Compared:
    """The clip ``new`` (``clip_import.ImportedClip``) against ``old``,
    track by track ((bone, component)); ``placed`` the jiggle bones'
    indices, ``names`` every bone's name."""
    a = {(t.target, t.comp): t for t in old.clip.bones}
    b = {(t.target, t.comp): t for t in new.clip.bones}
    keys = set(a) | set(b)
    others = [k for k in keys if k[0] not in placed]
    mine = [k for k in keys if k[0] in placed]
    differ = sorted({names[k[0]] for k in others if a.get(k) != b.get(k)})
    return Compared((sum(a.get(k) == b.get(k) for k in others), len(others)),
                    (sum(a.get(k) == b.get(k) for k in mine), len(mine)), tuple(differ))


def bodies(variant, iso: Path) -> tuple[bytes, bytes, str, float]:
    """``variant``'s body on the vanilla ``iso`` after W24, W29 and W30 as its
    recipe places its jiggle bones and as its own build does (no
    ``places``), the body's name and the seconds both took; ``ValueError``
    names a variant with no jiggle, one another recipe places even with no
    ``places`` (``from`` it, or sized by shapes), or a step that fails."""
    from azurkit.tools.characters import _player_character as pc
    from azurkit.tools.characters import _player_variants as variants
    from azurkit.tools.characters import gltf

    if variant.jiggle is None:
        raise ValueError(f"{variant.name} has no jiggle: no bone of its clips is placed by its mesh")
    own = dataclasses.replace(variant, places=None)
    if (parent := variants.placing(own)) is not None:
        raise ValueError(f"{variant.name}'s jiggle bones are placed by {parent.name}'s build even with no places "
                         "(a recipe from another, or one its shapes size): re-rest that one's clips")
    characters, config = image.read(iso, "gamedata/characters.xbr", "gamedata/config.xbr")
    if not gltf.vanilla_characters(characters):
        raise ValueError(f"{iso}'s characters.xbr isn't vanilla (D27)")
    body, _ = gltf.resolve_body(characters, config, variant.base)
    start, made = time.monotonic(), []
    for v in (variant, own):   # W30 too: a mesh that lays new UVs refuses a dress without its paint
        made.append(pc._variant_body(characters, characters, body, v)[0])
    return made[0], made[1], body, time.monotonic() - start


def rests(characters: bytes, body: str, names) -> dict[str, tuple]:
    """Each bone ``names`` names at its rest in ``characters``'s ``body``, as
    ``model export`` writes its node (``gltf._rest_trs``)."""
    from azurkit.tools.characters import gltf

    info = gltf._read(characters, body)
    index = {b.name: k for k, b in enumerate(info.bones)}
    missing = [n for n in names if n not in index]
    if missing:
        raise ValueError(f"{body} has no bone {', '.join(missing)}")
    return {n: gltf._rest_trs(info, index[n]) for n in names}


def _files(variant) -> tuple[Path, dict[str, str]]:
    """``variant``'s clip folder and each file its ``gltf`` rows name, with
    the sha256 they name (one a file; ``ValueError`` for none, two)."""
    from azurkit.tools.characters._player_variants import clip_folder

    shas: dict[str, str] = {}
    for name, row in variant.clips.items():
        if isinstance(row, dict) and row.get("generator") == "gltf":
            if shas.setdefault(row["file"], row["sha256"]) != row["sha256"]:
                raise ValueError(f"{variant.name}: clip {name} names {row['file']} at another sha256")
    if not shas:
        raise ValueError(f"{variant.name} has no gltf clip")
    return clip_folder(variant), shas


def run(variant, iso: Path, out: Path) -> tuple[list[str], int]:
    """:mod:`this verb <devkit.models.clip_rest>` on ``variant``: its lines,
    and 0, or 1 where a clip's other bones moved (then nothing is written)."""
    from azurkit.tools.characters import clip_import, gltf

    bound = 2 * clip_import.THIN_TOLERANCE
    folder, shas = _files(variant)
    names = [b.bone for b in variant.jiggle.bones] if variant.jiggle is not None else []
    old_body, new_body, body, seconds = bodies(variant, iso)
    olds = rests(old_body, body, names)
    news = rests(new_body, body, names)
    old_info, new_info = gltf._read(old_body, body), gltf._read(new_body, body)
    bone_names = [b.name for b in new_info.bones]
    placed = {bone_names.index(n) for n in names}
    lines = [f"{variant.name} ({body}): {len(names)} jiggle bones placed as its recipe places them and as its own "
             f"build does, in {seconds:.0f} s"]
    lines.append("  moves (mm): " + ", ".join(
        f"{n} {1000 * math.dist(_f32(olds[n][0]), _f32(news[n][0])):.1f}" for n in names))
    part = Path(tempfile.mkdtemp(prefix=f".{out.name}.part-", dir=out.parent))
    try:
        rows, failed = {}, False
        for file, sha in sorted(shas.items()):
            path = folder / file
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != sha:
                raise ValueError(f"{path}: its sha256 isn't the recipe's {sha[:12]}")
            try:
                new, moved, keyed = rerest(data, news)
            except ValueError as exc:   # a refusal names the file it came from (D35, D992)
                raise ValueError(f"{file}: {exc}") from None
            (part / file).write_bytes(new)
            was = {c.name: c for c in clip_import.read_clips(old_body, body, path)}
            got = {c.name: c for c in clip_import.read_clips(new_body, body, part / file)}
            new_sha = hashlib.sha256(new).hexdigest()
            lines.append(f"  {file}: {len(data):,} B sha256 {sha[:12]} -> {len(new):,} B sha256 {new_sha[:12]}; "
                         f"{len(moved)} nodes re-rested, the places keyed on {len(keyed)} moved with them"
                         + (f" ({', '.join(keyed)})" if keyed else ""))
            for name in sorted(got):
                c = compare(was[name], got[name], placed, bone_names)
                apart = drift(old_info, was[name].clip, new_info, got[name].clip,
                              {bone_names.index(n) for n in c.differ})
                failed |= apart > bound
                lines.append(f"    {name:16s} other bones' tracks {c.others[0]}/{c.others[1]} equal, jiggle bones' "
                             f"{c.placed[0]}/{c.placed[1]}" + (f"; thinned apart: {', '.join(c.differ)}, posed within "
                                                              f"{apart:.1e}" + (f", past {bound:.0e}: DIFFER"
                                                                                if apart > bound else "")
                                                              if c.differ else ""))
            rows.update({n: {**r, "sha256": new_sha} for n, r in variant.clips.items()
                         if isinstance(r, dict) and r.get("generator") == "gltf" and r["file"] == file})
        if failed:
            shutil.rmtree(part)
            lines.append("a clip's other bones moved: nothing written")
            return lines, 1
        if out.exists():
            out.rmdir()
        part.rename(out)
    except BaseException:
        shutil.rmtree(part, ignore_errors=True)
        raise
    lines.append(f"wrote {', '.join(str(out / f) for f in sorted(shas))}")
    lines.append(f'recipe rows (with "places" dropped): "clips": {json.dumps(rows, separators=(", ", ": "))}')
    return lines, 0


def main(argv: list[str] | None = None) -> int:
    from azurkit.tools.characters._player_variants import laid_over, resolve

    ap = argparse.ArgumentParser(prog="python -m devkit models clip-rest", description=__doc__.split("\n\n")[0])
    ap.add_argument("variant", help="a built-in variant (booblord) or one of --variant-file's")
    ap.add_argument("--out", required=True, metavar="DIR", help="a new or empty folder for the re-rested files")
    ap.add_argument("--variant-file", default=None, metavar="PATH", help="a JSON file of variant recipes")
    ap.add_argument("--recipe", default=None, metavar="FILE",
                    help="a JSON object of recipe fields laid over the variant's (null drops one)")
    ap.add_argument("--iso", help="the vanilla image (default: the one AzurKit finds)")
    args = ap.parse_args(argv)
    try:
        variant = resolve(args.variant, args.variant_file)
        if variant is None:
            raise ValueError(f"{args.variant!r} is no variant")
        if args.recipe:
            variant = laid_over(variant, json.loads(Path(args.recipe).read_text(encoding="utf-8")))
        iso = image.find(args.iso)
        out = image.output(args.out, iso)
        lines, code = run(variant, iso, out)
    except (OSError, ValueError) as exc:
        print(f"clip-rest: {exc}", file=sys.stderr)
        return 1
    print("\n".join(lines))
    return code
