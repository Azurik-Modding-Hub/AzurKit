"""Pictures of a body from Blender, headless (Step 2.154, D443:
``python -m devkit models model preview``).

:func:`preview` exports the body (:func:`~azurkit.tools.characters.gltf.export_body`,
with the clip to pose, if any) into a scratch folder, runs Blender
(``--background --factory-startup``: no window, the user's preferences
untouched) on :mod:`devkit.models.blender.preview` with a job file,
and moves the PNGs (``<body>_<view>.png``, one a view, the body's own
textures on it) and ``views.json`` (each view's file and the frame's
size) into the output folder; the scratch folder is then deleted.
``lod`` K (Step 2.166e, D537) draws the body's LOD K instead: the body
written with LOD K as its only LOD (:func:`lod_only`; a K it lacks is
refused by name), exported, and framed on LOD 0 posed the same way (its
export, ``frame`` in the job), so LOD K's pictures are LOD 0's camera and
light, named ``<body>_lod<K>_<view>.png``.
Blender is ``--blender``, else ``$AZURIK_BLENDER``, else ``blender`` on
``PATH``, else ``/Applications/Blender.app``'s (5.2.2 is what Step 2.154
ran).  The pictures are of a game asset: keep them out of the repo.
Every refusal is a :class:`ValueError` (D35): an output inside the
checkout or an image's folder (:func:`devkit.models.image.output`), an unknown view, no Blender, Blender failing (its
last lines named).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path

from devkit.models.blender.preview import VIEWS

DEFAULT_VIEWS = ("front", "left", "back", "front_left")
APP = Path("/Applications/Blender.app/Contents/MacOS/Blender")
TIMEOUT = 900
"""Seconds Blender may take."""


def find_blender(given: str | Path | None = None) -> Path:
    """The Blender to run (module docstring); :class:`ValueError` if none."""
    for c in (given, os.environ.get("AZURIK_BLENDER"), shutil.which("blender"), APP):
        if c and Path(c).is_file() and os.access(c, os.X_OK):
            return Path(c)
    raise ValueError("Blender isn't found: give --blender PATH (or set AZURIK_BLENDER)")


def lod_only(characters_xbr: bytes, body: str, lod: int) -> bytes:
    """``characters_xbr`` with the body ``characters/<body>``'s LOD ``lod``
    written as its only LOD (:func:`~azurkit.tools.characters.body_codec.write_asset`,
    its groups as stored), which the export draws as the body's mesh;
    :class:`ValueError` naming the body and a LOD it lacks."""
    from dataclasses import replace

    from azurkit.tools.characters import body_codec

    asset = body_codec.read_asset(characters_xbr, body)
    count = len(asset.lods)
    if not 0 <= lod < count:
        raise ValueError(f"{asset.name} has no LOD {lod}: "
                         + ("it has only LOD 0" if count == 1 else f"its LODs are 0 to {count - 1}"))
    return body_codec.write_asset(characters_xbr, replace(asset, lods=[asset.lods[lod]]), regroup_groups=False)


def preview(characters_xbr: bytes, body: str, out: Path, *, views: Sequence[str] = DEFAULT_VIEWS, size: int = 768,
            engine: str = "workbench", clip: str | None = None, time: float = 0.0, margin: float = 0.08,
            hide: Sequence[str] = (), blender: str | Path | None = None, protect: Sequence[Path] = (),
            vanilla: bool = True, lod: int = 0) -> dict:
    """The body ``characters/<body>`` rendered into the new or empty
    folder ``out`` (module docstring), ``clip`` posed at ``time`` (else
    the bind pose), the faces of the materials ``hide`` names left out
    (``row3``: female_2's vase), its LOD ``lod`` in LOD 0's frame:
    ``views.json``'s content, its views then the PNGs' paths in ``out``."""
    from azurkit.tools.characters import gltf
    from devkit.models import image
    from devkit.models.blender.batch import slot

    out = image.output(out, *map(Path, protect))
    shown = lod_only(characters_xbr, body, lod) if lod else characters_xbr
    unknown = [v for v in views if v not in VIEWS]
    if unknown or not views:
        raise ValueError(f"view {', '.join(map(repr, unknown)) or 'none'}: the views are {', '.join(VIEWS)}")
    if engine not in ("workbench", "eevee"):
        raise ValueError(f"engine {engine!r} is workbench or eevee")
    if not (64 <= int(size) <= 4096):
        raise ValueError(f"size {size}: 64 to 4096 pixels")
    exe = find_blender(blender)
    scratch = Path(tempfile.mkdtemp(prefix="azurik-preview-"))
    try:
        posed = [clip] if clip else []
        e = gltf.export_body(shown, body, scratch / "gltf", posed, source_vanilla=vanilla and not lod)
        frame = (gltf.export_body(characters_xbr, body, scratch / "frame", posed, source_vanilla=vanilla)
                 if lod else None)
        renders = scratch / "renders"
        renders.mkdir()
        prefix = f"{e.body.replace('/', '_')}_" + (f"lod{lod}_" if lod else "")
        job = scratch / "job.json"
        job.write_text(json.dumps({"gltf": str(e.gltf), "frame": str(frame.gltf) if frame else None,
                                   "out": str(renders), "prefix": prefix, "views": list(views),
                                   "size": int(size), "engine": engine, "clip": clip, "time": float(time),
                                   "margin": float(margin), "hide": list(hide), "lod": lod}), encoding="utf-8")
        script = Path(__file__).parent / "blender" / "preview.py"
        with slot() as held:                # at most 8 Blenders on the machine (Step X.62)
            run = subprocess.run([str(exe), "--background", "--factory-startup", "--python", str(script), "--",
                                  str(job)], capture_output=True, text=True, timeout=TIMEOUT, pass_fds=held.fds)
        made = renders / f"{prefix}views.json"
        if run.returncode != 0 or not made.is_file():
            tail = [x for x in (run.stdout + run.stderr).splitlines() if x.strip()][-4:]
            raise ValueError(f"Blender failed ({run.returncode}): {' | '.join(tail)}")
        report = json.loads(made.read_text(encoding="utf-8"))
        missing = [v for v in views if not Path(report["views"].get(v, "")).is_file()]
        if missing:
            raise ValueError(f"Blender wrote no picture of {', '.join(missing)}")
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists():
            out.rmdir()
        shutil.move(str(renders), str(out))
        report["views"] = {v: str(out / Path(p).name) for v, p in report["views"].items()}
        report["lod"] = lod
        (out / made.name).write_text(json.dumps(report), encoding="utf-8")
        return report
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


__all__ = ["APP", "DEFAULT_VIEWS", "TIMEOUT", "find_blender", "lod_only", "preview"]
