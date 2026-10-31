"""A glTF back into a body with any topology, or its skin weights alone
(Step 2.154, D443: the model toolkit's import), for
``azurik-mod model import`` and a variant's ``mesh.gltf`` with
``import``; Step 2.142's same-topology import of moved positions
(:mod:`azurik_mod.assets.mesh_edit`) stays as it is.

The file is a ``.glb`` or ``.gltf`` (its buffers beside it or data URIs;
untrusted data: only its JSON and buffers are read) that
``azurik-mod model export`` wrote and Blender, or any tool, edited.  It
is matched to the body by name: its one mesh skinned to a skin whose
joints are the body's bones by name (a ``<bone>__scale`` helper its
bone's), its materials the export's (``<body>_row<N>``, or
``<body>_gshd<G>_row<N>`` where two share a row; a Blender ``.001``
suffix dropped; or their ``azurik`` extras), its vertices by the
export's ids (``_AZ_VID``, or ``TEXCOORD_1``: Blender's ``UVMap.001``)
where they carry one.  Its frame comes from the skin, as Step 2.142's
(:func:`~azurik_mod.assets.mesh_edit.skin_frame`: Blender writes glTF's
y up).

- **Bones.**  A joint the body lacks is a new bone (both modes), added
  after the last (:func:`~azurik_mod.assets.skeleton.add_bone`) under
  the nearest joint above it in the file's node tree (a root when none),
  its bind the joint's inverse bind turned into the model's frame: a
  bone Blender added and weighted.  One whose bind carries a scale, or a
  new ``__scale`` helper, is refused.
- **``topology``** (new, moved and removed vertices, triangles and
  groups).  A vertex whose id is one of LOD 0's (its copies within
  :data:`~azurik_mod.assets.mesh_edit.COPIES`: one a split or a sculpt
  pulled apart, or an id a subdivision interpolated, is a new vertex) is
  that vertex: its position, UV, normal and skin kept byte for byte where
  the file's lie within the round trip's tolerances
  (:data:`~azurik_mod.assets.mesh_edit.MOVED`, ``UV_CHANGE``,
  :data:`NORMAL_CHANGE`, ``SKIN_CHANGE``), else the file's.  A triangle whose three
  corners are one group's ids is that group's; any other goes to the
  group of its material its corners' ids name most (else the first group
  of that material, else a new group of it), a corner of another group
  or none a new vertex there.  A body vertex a triangle drew that no
  triangle draws now is removed, a group left with no triangle removed, and
  a group whose triangles are its stored ones keeps its strip.  A new
  vertex needs a weight (refused by name otherwise) and takes its skin's
  four heaviest weights, renormalised; a missing normal is its faces'.
- **``weights``** (Blender-painted skin weights, any bones).  The same
  topology as Step 2.142's import asks (every drawn vertex there by id,
  the triangles the body's), positions, normals and UVs kept; each
  vertex whose skin moved past ``SKIN_CHANGE`` takes the file's (four
  heaviest, renormalised).

Palettes grow with new bones; :func:`~azurik_mod.assets.body_codec.write_asset`
then splits a group past 31.  Unchanged, a file reads back to the body
it came from, so the write gives the input's bytes.  Every refusal is a
:class:`ValueError` naming the file and the rule (D35).  Nothing here
prints a byte or a coordinate.
"""

from __future__ import annotations

import math
import re
import struct
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from azurkit.core import fdlibm
from azurkit.tools.characters import body_codec, mesh_edit, skeleton
from azurkit.tools.characters.body_codec import BodyAsset, Group, Vertex
from azurkit.tools.characters.gltf import HELPER

MODES = ("topology", "weights")
NORMAL_CHANGE = fdlibm.cos(math.radians(2.0))
"""An unmoved vertex's normal is the file's only past this cosine (2
degrees: Blender 5.2.2's round trip turns one of female_2's 0.6)."""


@dataclass(frozen=True)
class Imported:
    """What :func:`read` made of a file: the body as imported (not yet
    written: :func:`~azurik_mod.assets.body_codec.write_asset` writes and
    regroups it), the mode, the file's sha256 (Step 2.142's), the glTF
    vertices read, the body's vertices kept byte for byte, changed and
    removed, the vertices added, the triangles, the groups added and
    removed, the new bones, the meshes ignored and whether the file is y
    up."""

    asset: BodyAsset
    mode: str
    sha256: str
    vertices: int
    kept: int
    changed: int
    removed: int
    added: int
    triangles: int
    new_groups: int
    removed_groups: int
    new_bones: tuple[str, ...]
    ignored: tuple[str, ...]
    swapped: bool


def _binds(asset: BodyAsset) -> list[tuple[float, ...]]:
    return [struct.unpack_from("<16f", b.record, 0x60) for b in asset.bones]


def _quat(r) -> tuple[float, float, float, float]:
    """A rotation matrix's quaternion (x, y, z, w)."""
    t = r[0][0] + r[1][1] + r[2][2]
    if t > 0:
        s = math.sqrt(t + 1.0) * 2
        return ((r[2][1] - r[1][2]) / s, (r[0][2] - r[2][0]) / s, (r[1][0] - r[0][1]) / s, 0.25 * s)
    if r[0][0] > r[1][1] and r[0][0] > r[2][2]:
        s = math.sqrt(1.0 + r[0][0] - r[1][1] - r[2][2]) * 2
        return (0.25 * s, (r[0][1] + r[1][0]) / s, (r[0][2] + r[2][0]) / s, (r[2][1] - r[1][2]) / s)
    if r[1][1] > r[2][2]:
        s = math.sqrt(1.0 + r[1][1] - r[0][0] - r[2][2]) * 2
        return ((r[0][1] + r[1][0]) / s, 0.25 * s, (r[1][2] + r[2][1]) / s, (r[0][2] - r[2][0]) / s)
    s = math.sqrt(1.0 + r[2][2] - r[0][0] - r[1][1]) * 2
    return ((r[0][2] + r[2][0]) / s, (r[1][2] + r[2][1]) / s, 0.25 * s, (r[1][0] - r[0][1]) / s)


def _frame_matrix(axes) -> list[list[float]]:
    """The 4x4 that takes a file point to the model's (``axes`` as
    :func:`~azurik_mod.assets.mesh_edit.skin_frame` gives them)."""
    m = [[0.0] * 4 for _ in range(4)]
    for r, (c, s) in enumerate(axes):
        m[r][c] = s
    m[3][3] = 1.0
    return m


def _add_bones(asset: BodyAsset, doc: dict, buffers, skin: dict, bones: list, axes) -> list[str]:
    """The skin's joints the body lacks added as bones (module
    docstring), ``bones`` filled in for them; their names."""
    joints = skin["joints"]
    ibm = mesh_edit._values(doc, buffers, skin["inverseBindMatrices"]) if "inverseBindMatrices" in skin else None
    parent_of = {c: i for i, n in enumerate(doc.get("nodes", [])) for c in n.get("children", [])}
    names = {j: str(doc["nodes"][j].get("name", "")) for j in joints}
    todo = [k for k, b in enumerate(bones) if b is None]
    added = []
    frame = _frame_matrix(axes)
    while todo:
        progress = False
        for k in list(todo):
            j = joints[k]
            name = names[j]
            if name.endswith(HELPER) or not name:
                raise ValueError(f"the skin's joint {name!r} is no bone of {asset.name}, and a new bone needs a plain "
                                 "name (no __scale helper)")
            up = parent_of.get(j)
            while up is not None and up not in names:
                up = parent_of.get(up)
            parent = None
            if up is not None:
                pk = joints.index(up)
                if bones[pk] is None:
                    continue           # its parent first
                parent = asset.bones[bones[pk]].name
            if ibm is None:
                raise ValueError(f"new bone {name!r}: the skin has no inverse binds")
            inv = mesh_edit._matrix(ibm[k])                     # file point -> joint
            world = mesh_edit._mul(frame, mesh_edit._inverse(inv))    # joint -> model
            rot = [row[:3] for row in world[:3]]
            if any(abs(sum(rot[i][c] * rot[i][d] for i in range(3)) - (1.0 if c == d else 0.0)) > 1e-4
                   for c in range(3) for d in range(3)):
                raise ValueError(f"new bone {name!r}: its bind carries a scale or a shear (apply the armature's scale)")
            try:
                bones[k] = skeleton.add_bone(asset, name, parent, [world[i][3] for i in range(3)], _quat(rot))
            except ValueError as exc:
                raise ValueError(f"new bone {name!r}: {exc}") from None
            added.append(name)
            todo.remove(k)
            progress = True
        if not progress:
            raise ValueError("the skin's new joints form a cycle")
    return added


def _materials(doc: dict, asset: BodyAsset) -> dict[int, tuple[int, int]]:
    """Each file material's (``gshd``, row): its ``azurik`` extras, else
    its name as the export gives it (a Blender ``.NNN`` suffix dropped)."""
    have = []
    for g in asset.lods[0].groups:
        if g.material not in have:
            have.append(g.material)
    slug = asset.name.replace("/", "_")
    names = {}
    for gshd, row in have:
        plain = f"{slug}_row{row}"
        names.setdefault(plain, []).append((gshd, row))
    by_name = {}
    for key, ms in names.items():
        if len(ms) == 1:
            by_name[key] = ms[0]
        else:
            by_name.update({f"{slug}_gshd{g}_row{r}": (g, r) for g, r in ms})
            by_name[key] = ms[0]
    out = {}
    for i, m in enumerate(doc.get("materials", [])):
        extra = ((m.get("extras") or {}).get("azurik") or {})
        if isinstance(extra, dict) and (extra.get("gshd"), extra.get("row")) in {tuple(x) for x in have}:
            out[i] = (int(extra["gshd"]), int(extra["row"]))
            continue
        name = re.sub(r"\.\d{3}$", "", str(m.get("name", "")))
        if name in by_name:
            out[i] = by_name[name]
    return out


@dataclass
class _Corner:
    position: tuple
    normal: tuple | None
    uv: tuple
    skin: dict
    vid: tuple[int, int] | None
    material: tuple[int, int] | None


def _skin_of(js, ws, joints, bones) -> dict[int, float]:
    out: dict[int, float] = {}
    for jset, wset in zip(js, ws):
        for j, w in zip(jset, wset):
            if w > 0:
                b = bones[int(j)]
                out[b] = out.get(b, 0.0) + w
    return out


def read(characters_xbr: bytes, body: str, path: Path, mode: str = "topology") -> Imported:
    """The glTF ``path`` imported onto the body ``characters/<body>`` of
    ``characters_xbr`` in ``mode`` (:data:`MODES`; module docstring).
    :class:`ValueError` names the file and the first rule broken."""
    path = Path(path)
    try:
        return _read(characters_xbr, body, path, mode)
    except ValueError as exc:
        raise ValueError(f"{path.name}: {exc}") from None
    except (KeyError, IndexError, TypeError, AttributeError, struct.error, UnicodeDecodeError, OSError) as exc:
        raise ValueError(f"{path.name}: not a glTF this import reads ({type(exc).__name__}: {exc})") from None


def _read(characters_xbr: bytes, body: str, path: Path, mode: str) -> Imported:
    if mode not in MODES:
        raise ValueError(f"import mode {mode!r} is not one of {', '.join(MODES)}")
    asset = body_codec.read_asset(characters_xbr, body)
    if len(asset.lods) > 1:
        raise ValueError(f"{asset.name} has {len(asset.lods)} LODs; an import writes LOD 0 only")
    doc, buffers, sha = mesh_edit._load(path)
    names = asset.bone_names
    found, ignored = [], []
    for mi, m in enumerate(doc.get("meshes", [])):
        nodes = [n for n in doc.get("nodes", []) if n.get("mesh") == mi and "skin" in n]
        skins = [doc["skins"][n["skin"]] for n in nodes]
        if any(str(doc["nodes"][j].get("name", "")).removesuffix(HELPER) in names for s in skins for j in s["joints"]):
            found.append((mi, skins))
        else:
            ignored.append(str(m.get("name", f"mesh {mi}")))
    if not found:
        raise ValueError(f"no mesh is skinned to {asset.name}'s bones: export the mesh with its armature")
    if len(found) > 1:
        raise ValueError(f"meshes {', '.join(repr(doc['meshes'][mi].get('name', mi)) for mi, _ in found)} are all "
                         "skinned to its bones: keep one")
    mi, skins = found[0]
    if len(skins) != 1:
        raise ValueError(f"mesh {doc['meshes'][mi].get('name', mi)!r} needs one skinned node")
    skin = skins[0]
    bones, axes = mesh_edit.skin_frame(doc, buffers, skin, names, _binds(asset), asset.name, new_bones=True)
    new_bones = _add_bones(asset, doc, buffers, skin, bones, axes)
    materials = _materials(doc, asset)
    groups = asset.lods[0].groups
    counts = [len(g.vertices) for g in groups]

    def model(v) -> tuple:
        return tuple(s * v[c] for c, s in axes)

    # every corner of every primitive
    corners: list[_Corner] = []
    triangles: list[tuple[int, int, int]] = []
    for p in doc["meshes"][mi]["primitives"]:
        if p.get("mode", 4) != 4:
            raise ValueError(f"a primitive of mode {p.get('mode')} (triangles only)")
        a = p["attributes"]
        if "POSITION" not in a or "TEXCOORD_0" not in a:
            raise ValueError("a primitive has no POSITION or TEXCOORD_0 (its UVs): export them")
        pos = mesh_edit._values(doc, buffers, a["POSITION"])
        uvs = mesh_edit._values(doc, buffers, a["TEXCOORD_0"])
        nrm = mesh_edit._values(doc, buffers, a["NORMAL"]) if "NORMAL" in a else None
        ids = None
        for carrier in mesh_edit.CARRIERS:
            if carrier in a:
                ids = mesh_edit._values(doc, buffers, a[carrier])
                break
        sets_j, sets_w = [], []
        n = 0
        while f"JOINTS_{n}" in a and f"WEIGHTS_{n}" in a:
            sets_j.append(mesh_edit._values(doc, buffers, a[f"JOINTS_{n}"]))
            sets_w.append(mesh_edit._values(doc, buffers, a[f"WEIGHTS_{n}"]))
            n += 1
        if any(len(x) != len(pos) for x in (uvs, *(nrm and [nrm] or []), *(ids and [ids] or []), *sets_j, *sets_w)):
            raise ValueError("a primitive's attribute counts differ")
        material = materials.get(p.get("material", -1))
        if material is None and mode == "topology":
            m = doc.get("materials", [])[p["material"]] if "material" in p else {}
            raise ValueError(f"material {m.get('name', p.get('material'))!r} is none of {asset.name}'s (keep the "
                             "export's material names)")
        first = len(corners)
        for r in range(len(pos)):
            vid = None
            if ids is not None:
                g, i = ids[r][0], ids[r][1]
                rg, ri = round(g), round(i)
                if abs(g - rg) < 1e-3 and abs(i - ri) < 1e-3 and 0 <= rg < len(groups) and 0 <= ri < counts[rg]:
                    vid = (rg, ri)
            corners.append(_Corner(tuple(struct.unpack("<3f", struct.pack("<3f", *model(pos[r])))),
                                   model(nrm[r]) if nrm is not None else None, tuple(uvs[r]),
                                   _skin_of([s[r] for s in sets_j], [s[r] for s in sets_w], skin["joints"], bones),
                                   vid, material))
        flat = [x for (x,) in mesh_edit._values(doc, buffers, p["indices"])] if "indices" in p else list(range(len(pos)))
        if len(flat) % 3 or any(not 0 <= int(x) < len(pos) for x in flat):
            raise ValueError("a primitive's indices aren't whole triangles of its vertices")
        triangles += [tuple(first + int(x) for x in flat[t:t + 3]) for t in range(0, len(flat), 3)]

    # an id is a body vertex only where all its copies agree
    copies: dict[tuple[int, int], list[int]] = {}
    for k, c in enumerate(corners):
        if c.vid is not None:
            copies.setdefault(c.vid, []).append(k)
    for vid, ks in copies.items():
        spread = max(max(abs(corners[k].position[i] - corners[ks[0]].position[i]) for i in range(3)) for k in ks)
        if spread > mesh_edit.COPIES:
            for k in ks:
                corners[k].vid = None
    copies = {vid: ks for vid, ks in copies.items() if corners[ks[0]].vid is not None}

    original = [(list(g.vertices), list(g.triangles)) for g in groups]
    drawn = [{v for t in g.triangles for v in t} for g in groups]
    if mode == "weights":
        return _weights(asset, sha, corners, triangles, copies, original, drawn, new_bones, ignored, axes)

    # the body's vertices the file has: kept, or the file's
    kept = changed = 0
    for (g, j), ks in sorted(copies.items()):
        c = corners[ks[0]]
        v = groups[g].vertices[j]
        same_pos = max(abs(a - b) for a, b in zip(c.position, v.position)) <= mesh_edit.MOVED
        same_uv = max(abs(a - b) for a, b in zip(c.uv, v.uv)) <= mesh_edit.UV_CHANGE
        old_skin = v.skin(groups[g].palette)
        same_skin = max((abs(c.skin.get(b, 0.0) - old_skin.get(b, 0.0)) for b in {*c.skin, *old_skin}),
                        default=0.0) <= mesh_edit.SKIN_CHANGE
        n = _unit(c.normal)
        on = _unit(v.normal)
        same_n = n is None or (on is not None and sum(x * y for x, y in zip(n, on)) >= NORMAL_CHANGE and same_pos)
        if same_pos and same_uv and same_skin and same_n:
            kept += 1
            continue
        changed += 1
        if not c.skin:
            raise ValueError(f"vertex ({g}, {j}) has no weights")
        new = body_codec.make_vertex(v.position if same_pos else c.position,
                                     (v.normal if same_n else n) or on or (0.0, 0.0, 1.0),
                                     v.uv if same_uv else c.uv, old_skin if same_skin else c.skin, groups[g].palette,
                                     v.extra)
        groups[g].vertices[j] = new if not same_skin else Vertex(new.position, v.weights, new.normal, new.uv, v.extra,
                                                                  v.slots)

    # the triangles: each to its group, new corners new vertices there
    by_material: dict[tuple[int, int], list[int]] = {}
    for g, grp in enumerate(groups):
        by_material.setdefault(grp.material, []).append(g)
    placed: dict[tuple[int, int], int] = {}
    tris: dict[int, list[tuple[int, int, int]]] = {g: [] for g in range(len(groups))}
    added = new_groups = 0
    needs_normal: list[tuple[int, int]] = []
    for t in triangles:
        cs = [corners[k] for k in t]
        if all(c.vid is not None for c in cs) and len({c.vid[0] for c in cs}) == 1:
            g = cs[0].vid[0]
            tris[g].append(tuple(c.vid[1] for c in cs))
            continue
        material = cs[0].material
        votes = Counter(c.vid[0] for c in cs if c.vid is not None and groups[c.vid[0]].material == material)
        if votes:
            g = min(votes, key=lambda x: (-votes[x], x))
        elif by_material.get(material):
            g = by_material[material][0]
        else:
            groups.append(Group([], [], [], material))
            g = len(groups) - 1
            by_material.setdefault(material, []).append(g)
            tris[g] = []
            new_groups += 1
        local = []
        for k, c in zip(t, cs):
            if c.vid is not None and c.vid[0] == g:
                local.append(c.vid[1])
                continue
            key = (k, g)
            if key not in placed:
                if not c.skin:
                    raise ValueError("a new vertex has no weights: weight it to the armature")
                placed[key] = groups[g].add(c.position, _unit(c.normal) or (0.0, 0.0, 1.0), c.uv, c.skin)
                if _unit(c.normal) is None:
                    needs_normal.append((g, placed[key]))
                added += 1
            local.append(placed[key])
        tris[g].append(tuple(local))
    for g, grp in enumerate(groups):
        mine = tris[g]
        if g < len(original) and Counter(map(body_codec._canonical, mine)) == \
                Counter(map(body_codec._canonical, original[g][1])):
            grp.triangles = list(original[g][1])
        else:
            grp.triangles = mine
    if needs_normal:
        _face_normals(groups, needs_normal)
    removed = 0
    for g in range(len(original)):      # a vertex the body drew that no triangle draws now (Blender drops loose ones)
        used = {v for t in groups[g].triangles for v in t}
        gone = [j for j in drawn[g] if j not in used]
        if gone:
            removed += len(gone)
            groups[g].remove(gone)
    removed_groups = sum(1 for g in range(len(original)) if original[g][1] and not groups[g].triangles)
    asset.lods[0].groups = [grp for g, grp in enumerate(groups) if grp.triangles or (g < len(original)
                                                                                    and not original[g][1])]
    return Imported(asset, "topology", sha, len(corners), kept, changed, removed, added, len(triangles), new_groups,
                    removed_groups, tuple(new_bones), tuple(ignored), axes != [(0, 1.0), (1, 1.0), (2, 1.0)])


def _weights(asset, sha, corners, triangles, copies, original, drawn, new_bones, ignored, axes) -> Imported:
    """The ``weights`` mode (module docstring)."""
    groups = asset.lods[0].groups
    foreign = sum(1 for c in corners if c.vid is None)
    if foreign:
        raise ValueError(f"{foreign} vertices with no id of {asset.name}'s: weights import onto the same topology "
                         "(use import topology for new vertices)")
    missing = sum(1 for g in range(len(groups)) for j in drawn[g] if (g, j) not in copies)
    if missing:
        raise ValueError(f"{missing} of {asset.name}'s vertices missing (Merge by Distance joins seam copies)")
    got = Counter(body_codec._canonical(tuple(corners[k].vid for k in t)) for t in triangles)
    want = Counter(body_codec._canonical(tuple((g, v) for v in t)) for g, grp in enumerate(groups)
                   for t in grp.triangles)
    if got != want:
        raise ValueError(f"the triangles changed: {sum((want - got).values())} missing, {sum((got - want).values())} "
                         "new: weights import onto the same topology")
    kept = changed = 0
    for (g, j), ks in sorted(copies.items()):
        c = corners[ks[0]]
        v = groups[g].vertices[j]
        old = v.skin(groups[g].palette)
        if max((abs(c.skin.get(b, 0.0) - old.get(b, 0.0)) for b in {*c.skin, *old}), default=0.0) \
                <= mesh_edit.SKIN_CHANGE:
            kept += 1
            continue
        if not c.skin:
            raise ValueError(f"vertex ({g}, {j}) has no weights")
        new = body_codec.make_vertex(v.position, v.normal, v.uv, c.skin, groups[g].palette, v.extra)
        groups[g].vertices[j] = Vertex(v.position, new.weights, v.normal, v.uv, v.extra, new.slots)
        changed += 1
    return Imported(asset, "weights", sha, len(corners), kept, changed, 0, 0, len(triangles), 0, 0, tuple(new_bones),
                    tuple(ignored), axes != [(0, 1.0), (1, 1.0), (2, 1.0)])


def _unit(v) -> tuple | None:
    if v is None:
        return None
    n = math.sqrt(sum(c * c for c in v))
    return tuple(c / n for c in v) if n > 0 else None


def _face_normals(groups, which) -> None:
    """Each vertex of ``which`` (group, index) given its faces'
    area-weighted normal."""
    for g, j in which:
        grp = groups[g]
        acc = [0.0, 0.0, 0.0]
        for t in grp.triangles:
            if j in t:
                a, b, c = (grp.vertices[k].position for k in t)
                f = mesh_edit._cross(mesh_edit._sub(b, a), mesh_edit._sub(c, a))
                for i in range(3):
                    acc[i] += f[i]
        n = _unit(acc) or (0.0, 0.0, 1.0)
        v = grp.vertices[j]
        grp.vertices[j] = Vertex(v.position, v.weights, tuple(struct.unpack("<3f", struct.pack("<3f", *n))), v.uv,
                                 v.extra, v.slots)


__all__ = ["Imported", "MODES", "NORMAL_CHANGE", "read"]
