"""Blender's side of ``model preview`` (Step 2.154, D443): run
inside Blender (``blender --background --factory-startup --python
preview.py -- JOB``), never imported by the toolkit but for :data:`VIEWS`.

JOB is a JSON file: ``gltf`` (the export to render), ``out`` (the
folder), ``prefix``, ``views`` (names of :data:`VIEWS`), ``size``
(pixels, square), ``engine`` (``workbench`` or ``eevee``), ``clip`` and
``time`` (an animation and a time in seconds to pose, or none: the bind
pose), ``margin`` (the frame round the body, a share of its size),
``hide`` (material name endings, ``row3`` or ``gshd2955_row3``, whose
faces are left out), ``frame`` (another export, or none: its posed mesh's
bounds frame the camera, Step 2.166e's LOD 0 for a LOD K).  It
clears the startup scene, imports the glTF (Blender turns its y up to z
up: the body upright, facing +Y), poses it, frames each view's
orthographic camera on the posed mesh's bounds (``frame``'s, posed and
cut the same way, when given) and renders one PNG a
view with the body's own textures (workbench: textured, studio light;
eevee: its materials under a sun and a fill), then writes
``<prefix>views.json`` with each view's file and the frame's size.
"""

import json
import sys

VIEWS = {
    "front": (0.0, 1.0, 0.0),
    "back": (0.0, -1.0, 0.0),
    "left": (1.0, 0.0, 0.0),
    "right": (-1.0, 0.0, 0.0),
    "front_left": (0.7071, 0.7071, 0.0),
    "front_right": (-0.7071, 0.7071, 0.0),
    "back_left": (0.7071, -0.7071, 0.0),
    "back_right": (-0.7071, -0.7071, 0.0),
    "top": (0.0, 0.0001, 1.0),
    "below": (0.0, 0.0001, -1.0),
}
"""Each view's direction from the body to the camera (Blender's frame: z
up, the body facing +Y; ``left`` is the body's own left)."""


def _posed(job: dict, gltf: str) -> list:
    """A clear scene holding ``gltf`` posed and cut as ``job`` asks: its
    drawn vertices' world positions."""
    import bpy

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=gltf)
    scene = bpy.context.scene
    arms = [o for o in scene.objects if o.type == "ARMATURE"]
    meshes = [o for o in scene.objects if o.type == "MESH"
              and any(m.type == "ARMATURE" for m in o.modifiers)]
    for o in [o for o in scene.objects if o.type == "MESH" and o not in meshes]:
        bpy.data.objects.remove(o)      # the importer's bone shapes (an Icosphere)
    if job.get("clip"):
        action = bpy.data.actions.get(job["clip"])
        if action is None:
            raise SystemExit(f"no animation {job['clip']!r} in the file")
        for arm in arms:
            arm.animation_data_create()
            arm.animation_data.action = action
        fps = scene.render.fps / scene.render.fps_base
        scene.frame_set(int(round(float(job.get("time", 0.0)) * fps)) + int(action.frame_range[0]))
    else:
        for arm in arms:
            if arm.animation_data:
                arm.animation_data.action = None
            arm.data.pose_position = "REST"
    hide = [h for h in job.get("hide", [])]
    if hide:        # a material's faces left out (a prop in the way: the townswomen's vase is _row3)
        import bmesh
        for o in meshes:
            gone = {i for i, slot in enumerate(o.material_slots)
                    if slot.material and any(slot.material.name.split(".")[0].endswith("_" + h) for h in hide)}
            if gone:
                bm = bmesh.new()
                bm.from_mesh(o.data)
                bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index in gone], context="FACES")
                bm.to_mesh(o.data)
                bm.free()
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    points = []
    for o in meshes:        # the drawn vertices only: a group's loose ones would stretch the frame
        ev = o.evaluated_get(depsgraph)
        data = ev.to_mesh()
        used = {i for poly in data.polygons for i in poly.vertices}
        points += [ev.matrix_world @ data.vertices[i].co for i in sorted(used)]
        ev.to_mesh_clear()
    if not points:
        raise SystemExit("the file has no mesh")
    return points


def main(job_path: str) -> None:
    import bpy
    from mathutils import Vector

    job = json.load(open(job_path, encoding="utf-8"))
    framing = _posed(job, job["frame"]) if job.get("frame") else None
    points = _posed(job, job["gltf"])
    scene = bpy.context.scene

    def bounds(ps):
        return Vector([min(p[i] for p in ps) for i in range(3)]), Vector([max(p[i] for p in ps) for i in range(3)])
    lo, hi = bounds(framing or points)
    centre = (lo + hi) / 2
    size = max(hi - lo) * (1.0 + 2.0 * float(job.get("margin", 0.08)))
    lo, hi = bounds(points)
    extent = hi - lo

    cam_data = bpy.data.cameras.new("preview")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = size
    cam_data.clip_start, cam_data.clip_end = 0.01, 100.0 * size
    cam = bpy.data.objects.new("preview", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    render = scene.render
    render.resolution_x = render.resolution_y = int(job.get("size", 768))
    render.resolution_percentage = 100
    render.film_transparent = False
    render.image_settings.file_format = "PNG"
    world = bpy.data.worlds.new("preview")
    world.color = (0.18, 0.18, 0.2)
    scene.world = world
    if job.get("engine", "workbench") == "eevee":
        render.engine = "BLENDER_EEVEE"
        for name, energy, rot in (("sun", 3.0, (0.8, 0.0, 0.6)), ("fill", 1.2, (1.2, 0.0, -2.4))):
            light = bpy.data.objects.new(name, bpy.data.lights.new(name, "SUN"))
            light.data.energy = energy
            light.rotation_euler = rot
            scene.collection.objects.link(light)
    else:
        render.engine = "BLENDER_WORKBENCH"
        shading = scene.display.shading
        shading.light = "STUDIO"
        shading.color_type = "TEXTURE"
        shading.show_backface_culling = False
        shading.show_object_outline = False
        shading.background_type = "WORLD"
    done = {}
    for view in job["views"]:
        d = Vector(VIEWS[view]).normalized()
        cam.location = centre + d * (3.0 * size)
        cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
        path = f"{job['out']}/{job['prefix']}{view}.png"
        render.filepath = path
        bpy.ops.render.render(write_still=True)
        done[view] = path
    with open(f"{job['out']}/{job['prefix']}views.json", "w", encoding="utf-8") as f:
        json.dump({"views": done, "frame_m": size, "height_m": extent[2], "width_m": extent[0],
                   "depth_m": extent[1], "pose": job.get("clip") or "bind", "time": job.get("time", 0.0)}, f)


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1])
