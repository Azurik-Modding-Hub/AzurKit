"""Blender's side of :mod:`devkit.models.blender.batch` (Step X.62):
run inside Blender (``blender --background --factory-startup
--python-exit-code 1 --python batch_inside.py -- JOB``), never
imported by the toolkit.

JOB is a JSON file that :func:`~devkit.models.blender.batch.render`
writes: ``body`` (an ``.npz``: ``vertices`` (V), ``uvs`` (V, 2),
``triangles`` (T, 3), ``material`` (T,) each triangle's material,
``materials`` their count and ``texture<k>`` each one's RGBA uint8
picture, top row first, empty for none), ``positions`` (an ``.npy``,
F x V x 3 float32) and ``normals`` (the same, or null: Blender's own
smooth normals), ``size`` ([W, H] a cell), ``views`` (rows of cameras:
``yaw``, ``ortho``, ``target``, ``elevation``, ``distance``), ``engine``
(``workbench`` or ``eevee``), ``cull``, ``clay``, ``background``,
``keep`` (the frames written to ``out``, an ``.npy``), ``mp4`` (``path``,
``fps``, ``crf``, ``ffmpeg``, or null), ``cells`` (a scratch file for
one render) and ``timing`` (the JSON its seconds go to).

It clears the startup scene and builds the body once: one mesh (its
vertices in the body's order, the triangles' corners carrying the
texture coordinates), one material a group with its picture as a
generated image (no file), the normals as a free ``custom_normal``
attribute on the vertices.  Then per frame it sets the positions (and
normals) and renders each camera's cell (Workbench: the sculpt rounds'
look; EEVEE: the materials under a sun and a fill), read back as raw
TGA, and joins them into the frame (each row of cameras side by side,
the rows top to bottom); kept frames go to ``out``, every frame to
ffmpeg's stdin.
"""

import json
import math
import os
import subprocess
import sys
import time


def _tga(path):
    """A raw 32-bit TGA's pixels, top row first, RGBA."""
    import numpy as np

    raw = np.fromfile(path, np.uint8)
    w, h = int(raw[12]) | int(raw[13]) << 8, int(raw[14]) | int(raw[15]) << 8
    if raw[2] != 2 or raw[16] != 32:
        raise SystemExit(f"{path}: not a raw 32-bit TGA (type {raw[2]}, {raw[16]} bits)")
    start = 18 + int(raw[0])
    px = raw[start:start + w * h * 4].reshape(h, w, 4)
    if not raw[17] & 0x20:      # bottom-left origin: the rows run up
        px = px[::-1]
    return px[..., (2, 1, 0, 3)]


def main(job_path):
    began = time.time()
    import bpy
    import numpy as np
    from mathutils import Vector

    job = json.load(open(job_path, encoding="utf-8"))
    sec = {"began": began}
    clock = time.perf_counter()
    body = np.load(job["body"])
    positions = np.load(job["positions"], mmap_mode="r")
    normals = np.load(job["normals"], mmap_mode="r") if job.get("normals") else None
    scene = bpy.context.scene
    for o in list(bpy.data.objects):        # the startup file's cube, light and camera
        bpy.data.objects.remove(o, do_unlink=True)

    tri = body["triangles"].astype(np.int32)
    mat = body["material"].astype(np.int32)
    whole = (tri[:, 0] != tri[:, 1]) & (tri[:, 1] != tri[:, 2]) & (tri[:, 0] != tri[:, 2])
    tri, mat = tri[whole], mat[whole]           # a degenerate triangle draws nothing either way
    me = bpy.data.meshes.new("body")
    me.vertices.add(int(body["vertices"]))        # each frame sets the positions
    me.loops.add(3 * len(tri))
    me.loops.foreach_set("vertex_index", tri.ravel())
    me.polygons.add(len(tri))
    me.polygons.foreach_set("loop_start", np.arange(0, 3 * len(tri), 3, dtype=np.int32))
    me.polygons.foreach_set("material_index", mat)
    me.polygons.foreach_set("use_smooth", np.ones(len(tri), bool))
    me.uv_layers.new(name="UVMap").data.foreach_set("uv", body["uvs"].astype(np.float32)[tri.ravel()].ravel())
    me.update(calc_edges=True)
    if normals is not None:
        me.attributes.new("custom_normal", "FLOAT_VECTOR", "POINT")
    for k in range(int(body["materials"])):
        m = bpy.data.materials.new(f"m{k}")
        m.diffuse_color, m.roughness, m.metallic = (1.0, 1.0, 1.0, 1.0), 1.0, 0.0    # as Blender's OBJ import
        m.blend_method = "HASHED"       # of "Kd 1 1 1" makes it (the sculpt rounds' pictures)
        if m.node_tree is None:
            m.use_nodes = True
        nodes = m.node_tree.nodes
        bsdf = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
        bsdf.inputs["Roughness"].default_value = 1.0
        bsdf.inputs["Specular IOR Level"].default_value = 0.0
        tex = body[f"texture{k}"]
        if tex.size:
            h, w = tex.shape[:2]
            img = bpy.data.images.new(f"t{k}", w, h, alpha=True)
            img.pixels.foreach_set((tex[::-1].astype(np.float32) / 255.0).ravel())
            node = nodes.new("ShaderNodeTexImage")
            node.image = img
            m.node_tree.links.new(node.outputs["Color"], bsdf.inputs["Base Color"])
            nodes.active = node
        me.materials.append(m)
    ob = bpy.data.objects.new("body", me)
    scene.collection.objects.link(ob)

    w, h = job["size"]
    render = scene.render
    render.resolution_x, render.resolution_y, render.resolution_percentage = w, h, 100
    render.film_transparent = False
    render.image_settings.file_format = "TARGA_RAW"
    render.image_settings.color_mode = "RGBA"
    world = bpy.data.worlds.new("grey")
    world.color = job["background"]
    scene.world = world
    if job["engine"] == "eevee":
        render.engine = "BLENDER_EEVEE"
        for name, energy, rot in (("sun", 3.0, (0.8, 0.0, 0.6)), ("fill", 1.2, (1.2, 0.0, -2.4))):
            light = bpy.data.objects.new(name, bpy.data.lights.new(name, "SUN"))
            light.data.energy = energy
            light.rotation_euler = rot
            scene.collection.objects.link(light)
    else:
        render.engine = "BLENDER_WORKBENCH"
        sh = scene.display.shading
        sh.light = "STUDIO"
        sh.color_type = "SINGLE" if job["clay"] else "TEXTURE"
        sh.single_color = (0.8, 0.8, 0.8)
        sh.show_cavity = True
        sh.cavity_type = "BOTH"
        sh.show_specular_highlight = True
        sh.show_backface_culling = bool(job["cull"])
        sh.background_type = "WORLD"
    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = "ORTHO"
    cam = bpy.data.objects.new("cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    sec["build"] = time.perf_counter() - clock

    rows = job["views"]
    cols = max(len(r) for r in rows)
    frames = len(positions)
    keep = {f: k for k, f in enumerate(job["keep"])}
    out = np.lib.format.open_memmap(job["out"], "w+", np.uint8, (len(keep), h * len(rows), w * cols, 4)) \
        if keep else None
    pipe = None
    if job.get("mp4"):
        mp4 = job["mp4"]
        pipe = subprocess.Popen(
            [mp4["ffmpeg"], "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba",
             "-s", f"{w * cols}x{h * len(rows)}", "-r", str(mp4["fps"]), "-i", "-",
             "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-pix_fmt", "yuv420p", "-c:v", "libx264",
             "-crf", str(mp4["crf"]), mp4["path"]], stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    for name in ("pose", "render", "read", "out"):
        sec[name] = 0.0
    cell = job["cells"]
    render.filepath = cell
    frame = np.zeros((h * len(rows), w * cols, 4), np.uint8)
    for f in range(frames):
        clock = time.perf_counter()
        me.vertices.foreach_set("co", np.ascontiguousarray(positions[f], np.float32).ravel())
        if normals is not None:
            me.attributes["custom_normal"].data.foreach_set(
                "vector", np.ascontiguousarray(normals[f], np.float32).ravel())
        me.update()
        sec["pose"] += time.perf_counter() - clock
        for i, row in enumerate(rows):
            for j, v in enumerate(row):
                clock = time.perf_counter()
                cam_data.ortho_scale = v["ortho"]
                a = math.radians(v["yaw"])     # 180: her front (the camera at +y); 270: her right side (+x)
                d = Vector((-math.sin(a), math.cos(a), 0.0))
                target = Vector(v["target"])
                cam.location = target - d * v["distance"] + Vector(
                    (0.0, 0.0, v["distance"] * math.tan(math.radians(v["elevation"]))))
                cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
                bpy.ops.render.render(write_still=True)
                took = time.perf_counter() - clock
                sec["render"] += took
                sec.setdefault("first_render", took)
                clock = time.perf_counter()
                frame[i * h:(i + 1) * h, j * w:(j + 1) * w] = _tga(cell)
                sec["read"] += time.perf_counter() - clock
        clock = time.perf_counter()
        if f in keep:
            out[keep[f]] = frame
        if pipe is not None:
            pipe.stdin.write(frame.tobytes())
        sec["out"] += time.perf_counter() - clock
    clock = time.perf_counter()
    if out is not None:
        out.flush()
    if pipe is not None:
        pipe.stdin.close()
        err = pipe.stderr.read().decode(errors="replace")
        if pipe.wait():
            raise SystemExit(f"ffmpeg exit {pipe.returncode}: {err[-300:]}")
    os.remove(cell)
    sec["finish"] = time.perf_counter() - clock
    sec["frames"], sec["cells"] = frames, frames * sum(len(r) for r in rows)
    with open(job["timing"], "w", encoding="utf-8") as fh:
        json.dump(sec, fh)


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1])
