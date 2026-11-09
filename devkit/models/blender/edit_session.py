"""Blender's side of ``model edit`` (Step 2.158, D465): run inside Blender
(``blender [DIR/edit.blend] --python edit_session.py -- JOB``, with
``--background --factory-startup`` in the headless mode), never imported
by the toolkit.

JOB is a JSON file: ``export`` (``model export``'s .gltf), ``blend``
(``DIR/edit.blend``), ``glb`` (``DIR/edit.glb``), ``saves``
(``DIR/edit.json``), ``script`` (a bpy script, or none) and
``headless``.  With no ``blend`` open it imports the export (its bone
shapes, unskinned meshes, removed) and saves ``blend``; then it
registers a persistent ``save_post`` handler: each save exports
everything (what is seen: modifiers applied, every action) to a temporary
name, moves it onto ``glb`` and then writes ``saves`` ({"n": its count}),
so the toolkit never reads a half-written file.  Headless, it runs
``script``, saves once and quits.  It never saves the user's
preferences.
"""

import json
import os
import runpy
import sys


def _export(job: dict) -> None:
    import bpy

    tmp = job["glb"] + ".tmp.glb"
    bpy.ops.export_scene.gltf(filepath=tmp, export_format="GLB", export_apply=True)
    os.replace(tmp, job["glb"])
    try:
        n = int(json.load(open(job["saves"], encoding="utf-8"))["n"])
    except (OSError, ValueError, KeyError, TypeError):
        n = 0
    with open(job["saves"] + ".tmp", "w", encoding="utf-8") as f:
        json.dump({"n": n + 1}, f)
    os.replace(job["saves"] + ".tmp", job["saves"])


def main(job_path: str) -> None:
    import bpy

    job = json.load(open(job_path, encoding="utf-8"))
    if os.path.normcase(bpy.data.filepath or "") != os.path.normcase(job["blend"]):
        if job["headless"]:
            bpy.ops.wm.read_factory_settings(use_empty=True)
        else:
            bpy.ops.wm.read_homefile(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=job["export"])
        for o in [o for o in bpy.context.scene.objects
                  if o.type == "MESH" and not any(m.type == "ARMATURE" for m in o.modifiers)]:
            bpy.data.objects.remove(o)      # the importer's bone shapes (an Icosphere)
        bpy.ops.wm.save_as_mainfile(filepath=job["blend"])

    @bpy.app.handlers.persistent
    def on_save(_):
        _export(job)

    bpy.app.handlers.save_post.append(on_save)
    if job["headless"]:
        if job.get("script"):
            runpy.run_path(job["script"], run_name="__main__")
        bpy.ops.wm.save_mainfile(filepath=job["blend"])


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1])
