"""Many frames of one body from one headless Blender (Step X.62).

:func:`render` draws a :class:`Body` (its vertices, texture coordinates,
triangles by material and each material's picture) in F poses with one
Blender process (``--background --factory-startup``: no window, the
user's preferences untouched) on
:mod:`devkit.models.blender.batch_inside`: the body and its pictures
are built once, then each frame's positions (and normals) are set and
each :class:`View`'s cell rendered.  A frame is its cells side by side,
its rows of views top to bottom (RGBA uint8); the frames ``keep`` names
come back as one array, and with ``mp4=`` every frame is piped into
ffmpeg as it renders (no PNG on the way).  Workbench draws the sculpt
rounds' look (the STUDIO light, the body's own textures, cavity, back
faces culled, a grey world, an orthographic camera 6 m off and 10 deg
above); EEVEE draws the materials under a sun and a fill.  Each stage's
seconds come back in :attr:`Batch.seconds` and, with ``log=``, as one
JSON line.

The body's arrays (its vertex count, texture coordinates, triangles and
pictures: not its positions, which each frame sets) are written once per
content: :func:`cached` keeps them in the AzurKit user cache by their
sha256, so every clip's job on one body shares them.  :func:`cached` and
:func:`cache_path` serve any input built from content (a dressed
``characters.xbr``, a rig's glTF export): the key is the sha256 of
everything the file depends on, the code included, never a work
folder's name; a miss is written to a temporary file and renamed, so
parallel jobs never read half a file, and a file no job has used for
:data:`KEEP_DAYS` days goes at the next miss of its kind.

:func:`slot` caps the Blenders running at once on the machine at
``$AZURIK_BLENDER_SLOTS`` (default :data:`SLOTS`): a job waits for a free
slot (a lock file the process and its Blender hold, freed when both
have ended); ``render`` takes one, and so do ``model preview``
(:mod:`devkit.models.preview`), the headless model edit and any other Blender job (``with
slot() as s: subprocess.run(..., pass_fds=s.fds)``).

Blender is ``blender=``, else ``$AZURIK_BLENDER``, else ``blender`` on
``PATH``, else ``/Applications/Blender.app``'s; ffmpeg is ``ffmpeg=``,
else ``ffmpeg`` on ``PATH``.  Every refusal is a :class:`ValueError`
naming what failed (D35), and a failed job writes no MP4.  The pictures
are of a game asset: keep them out of the repo (an MP4 inside the
checkout or an image's folder is refused: ``devkit.models.image.output``).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from platformdirs import user_cache_dir

try:
    import fcntl
except ImportError:         # Windows: no cap
    fcntl = None

CACHE = Path(user_cache_dir("AzurKit"))
"""The AzurKit user cache (``doctor --uninstall-hints`` lists it)."""
SLOTS = 8
"""Blenders at once on the machine by default (Step X.62's benchmark: 8
at once ran 5.7 times one's jobs a minute, each 26% slower)."""
TIMEOUT = 600
"""Seconds a job may take, plus 2 s a cell."""
KEEP_DAYS = 14
"""Days a cached file no job has used stays."""


@dataclass(frozen=True)
class View:
    """A camera: ``yaw`` degrees round the body (180 her front, the camera
    at +y; 270 her right side, at +x; 0 her back), ``ortho`` the frame's
    height in model units, looking at ``target`` from ``distance`` off and
    ``elevation`` degrees above it."""
    yaw: float
    ortho: float = 2.0
    target: tuple[float, float, float] = (0.0, 0.0, 0.95)
    elevation: float = 10.0
    distance: float = 6.0


@dataclass(frozen=True)
class Body:
    """A mesh to pose: ``points`` (V, 3), its rest positions in model
    units (z up, facing +y; only their count reaches Blender, where each
    frame sets the positions), ``uvs`` (V, 2) Blender's (v up: a game
    UV's ``1 - v``), and per material its ``triangles`` (T, 3, indices
    into ``points``) and its ``textures`` picture (h, w, 4 uint8, top row
    first, or ``None``).  A vertex no triangle uses is never drawn (a
    hidden part's)."""
    points: np.ndarray
    uvs: np.ndarray
    triangles: Sequence[np.ndarray]
    textures: Sequence[np.ndarray | None]

    def arrays(self) -> dict[str, np.ndarray]:
        """The ``.npz``'s arrays (:mod:`.batch_inside`)."""
        if len(self.triangles) != len(self.textures):
            raise ValueError(f"the body has {len(self.triangles)} materials' triangles and "
                             f"{len(self.textures)} textures")
        points = np.asarray(self.points, np.float32)
        uvs = np.asarray(self.uvs, np.float32)
        if points.ndim != 2 or points.shape[1] != 3 or uvs.shape != (len(points), 2):
            raise ValueError(f"the body's points {points.shape} and uvs {uvs.shape} aren't (V, 3) and (V, 2)")
        tri = [np.asarray(t, np.int32).reshape(-1, 3) for t in self.triangles]
        out = {"vertices": np.array(len(points)), "uvs": uvs, "materials": np.array(len(tri)),
               "triangles": np.concatenate(tri) if tri else np.zeros((0, 3), np.int32),
               "material": np.repeat(np.arange(len(tri), dtype=np.int32), [len(t) for t in tri])}
        if len(out["triangles"]) and not (0 <= out["triangles"].min() and out["triangles"].max() < len(points)):
            raise ValueError(f"a triangle names a vertex past the body's {len(points)}")
        for k, tex in enumerate(self.textures):
            tex = np.zeros((0, 0, 4), np.uint8) if tex is None else np.asarray(tex, np.uint8)
            if tex.ndim != 3 or tex.shape[2] != 4:
                raise ValueError(f"material {k}'s texture is {tex.shape}, not (h, w, 4) RGBA")
            out[f"texture{k}"] = tex
        return out


@dataclass
class Batch:
    """:func:`render`'s result: the kept ``frames`` (len(keep), H, W, 4),
    the ``mp4`` written, each stage's ``seconds`` and whether the body
    came from the cache."""
    frames: np.ndarray
    mp4: Path | None
    seconds: dict = field(default_factory=dict)
    body_cached: bool = False


def cache_path(kind: str, name: str) -> Path:
    """``name`` in the AzurKit user cache's ``kind`` folder (made)."""
    for part in (kind, name):
        if not part or part.startswith(".") or "/" in part or "\\" in part:
            raise ValueError(f"cache name {part!r}: one plain name, no folders")
    folder = CACHE / kind
    folder.mkdir(parents=True, exist_ok=True)
    return folder / name


def cached(kind: str, name: str, write: Callable[[Path], object]) -> tuple[Path, bool]:
    """The cached file ``kind``/``name`` and whether it was there (a hit
    marks it used); on a miss ``write(tmp)`` makes it, it is renamed into
    place and the kind's files unused for :data:`KEEP_DAYS` go.  ``name``
    carries the content key (the module docstring)."""
    path = cache_path(kind, name)
    if path.is_file():
        try:
            os.utime(path)
            return path, True
        except FileNotFoundError:               # another job's prune took it meanwhile: a miss
            pass
    fd, tmp = tempfile.mkstemp(prefix=f".{name}.", dir=path.parent)
    os.close(fd)
    try:
        write(Path(tmp))
        os.utime(tmp)                           # used now, whatever time write() left (a copy2 keeps its source's)
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)
    old = time.time() - KEEP_DAYS * 86400
    for f in path.parent.iterdir():
        with contextlib.suppress(OSError):      # another job's, gone or in use meanwhile
            if f.stat().st_mtime < old:
                f.unlink()
    return path, False


def content_key(*parts: bytes | str | Path | np.ndarray) -> str:
    """The sha256 (hex) of ``parts`` in order: bytes, text, a file's
    bytes (a :class:`~pathlib.Path`) or an array's dtype, shape and bytes."""
    h = hashlib.sha256()
    for p in parts:
        if isinstance(p, Path):
            p = p.read_bytes()
        elif isinstance(p, np.ndarray):
            p = f"{p.dtype.str}{p.shape}".encode() + np.ascontiguousarray(p).tobytes()
        elif isinstance(p, str):
            p = p.encode()
        h.update(len(p).to_bytes(8, "little") + p)
    return h.hexdigest()


def slots() -> int:
    """``$AZURIK_BLENDER_SLOTS``, else :data:`SLOTS`."""
    given = os.environ.get("AZURIK_BLENDER_SLOTS", "").strip()
    if not given:
        return SLOTS
    if not given.isdigit() or int(given) < 1:
        raise ValueError(f"AZURIK_BLENDER_SLOTS={given!r}: a whole number of Blenders, 1 or more")
    return int(given)


@dataclass(frozen=True)
class Slot:
    """A held Blender slot (:func:`slot`): the seconds ``waited`` for it and
    the lock's file descriptors, ``fds``, for the job's
    ``subprocess.run(..., pass_fds=s.fds)``: the job holds the slot too, so
    it stays taken while the job runs even if this process is killed."""
    waited: float
    fds: tuple[int, ...] = ()


@contextlib.contextmanager
def slot(wait: float | None = None) -> Iterator[Slot]:
    """Hold one of :func:`slots` machine-wide Blender slots while the block
    runs (an exclusive ``flock`` on ``blender-slots/<k>.lock`` in the cache,
    freed when every process given its :class:`Slot` ``fds`` has ended or
    let go), waiting for a free one, at most ``wait`` seconds (``None``: as
    long as it takes; then :class:`ValueError`)."""
    if fcntl is None:
        yield Slot(0.0)
        return
    n, start = slots(), time.monotonic()
    while True:
        for k in range(n):
            fd = os.open(cache_path("blender-slots", f"{k}.lock"), os.O_RDWR | os.O_CREAT, 0o644)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                os.close(fd)
                continue
            try:
                yield Slot(time.monotonic() - start, (fd,))
            finally:
                os.close(fd)        # frees the lock unless a job given it still runs
            return
        if wait is not None and time.monotonic() - start >= wait:
            raise ValueError(f"all {n} Blender slots are busy ({wait:g} s waited; AZURIK_BLENDER_SLOTS)")
        time.sleep(0.25)


def _stack(name: str, frames, count: int | None, vertices: int, path: Path) -> int:
    """Write ``frames`` (an (F, V, 3) array or a sequence of (V, 3) ones)
    as an F x V x 3 float32 ``.npy``; its F."""
    n = len(frames)
    if count is not None and n != count:
        raise ValueError(f"{n} frames of {name} for {count} frames of positions")
    out = np.lib.format.open_memmap(path, "w+", np.float32, (n, vertices, 3))
    for f, x in enumerate(frames):
        x = np.asarray(x)
        if x.shape != (vertices, 3):
            raise ValueError(f"frame {f}'s {name} are {x.shape}; the body has {vertices} vertices (V, 3)")
        out[f] = x
    out.flush()
    del out
    return n


def _savez(path: Path, arrays: dict) -> None:
    with open(path, "wb") as fh:
        np.savez(fh, **arrays)


def _ffmpeg(given: str | Path | None) -> str:
    for c in (given, shutil.which("ffmpeg"), "/opt/homebrew/bin/ffmpeg"):
        if c and Path(c).is_file() and os.access(c, os.X_OK):
            return str(c)
    raise ValueError("ffmpeg isn't found: give ffmpeg= (an MP4 needs it)")


def render(body: Body, positions, normals=None, *, views: Sequence[Sequence[View]], size: tuple[int, int] = (448, 640),
           engine: str = "workbench", cull: bool = True, clay: bool = False,
           background: tuple[float, float, float] = (0.30, 0.30, 0.32), keep: Sequence[int] | None = None,
           mp4: str | Path | None = None, fps: float = 15.0, crf: int = 20, blender: str | Path | None = None,
           ffmpeg: str | Path | None = None, log: str | Path | None = None) -> Batch:
    """``body`` posed at each of ``positions`` (an (F, V, 3) array or a
    sequence of F (V, 3) ones; ``normals`` alike, or ``None``: Blender's
    smooth normals) drawn from ``views`` (rows of :class:`View`), each cell
    ``size`` (W, H) pixels, by one Blender (the module docstring): the
    frames ``keep`` names (every frame by default; ``()`` none) and, with
    ``mp4``, an H.264 MP4 of every frame at ``fps``."""
    from devkit.models import image
    from devkit.models.preview import find_blender

    wall = time.perf_counter()
    rows = [[v if isinstance(v, View) else View(*v) for v in row] for row in views]
    if not rows or not all(rows):
        raise ValueError("views: rows of View, none empty")
    if engine not in ("workbench", "eevee"):
        raise ValueError(f"engine {engine!r} is workbench or eevee")
    w, h = (int(s) for s in size)
    if not (16 <= w <= 8192 and 16 <= h <= 8192):
        raise ValueError(f"size {w} x {h}: 16 to 8192 pixels a side")
    exe = find_blender(blender)
    movie = tool = None
    if mp4 is not None:
        movie = image.output(mp4, file=True)
        movie.parent.mkdir(parents=True, exist_ok=True)
        tool = _ffmpeg(ffmpeg)
    arrays = body.arrays()
    vertices = int(arrays["vertices"])
    seconds: dict = {}
    scratch = Path(tempfile.mkdtemp(prefix="azurik-batch-"))
    try:
        clock = time.perf_counter()
        key = content_key("blender-batch-body/1", *(x for k in sorted(arrays) for x in (k, arrays[k])))
        npz, was = cached("blender-bodies", f"{key[:32]}.npz", lambda p: _savez(p, arrays))
        frames = _stack("positions", positions, None, vertices, scratch / "positions.npy")
        if not frames:
            raise ValueError("no frames to render")
        if normals is not None:
            _stack("normals", normals, frames, vertices, scratch / "normals.npy")
        kept = list(range(frames)) if keep is None else [int(f) for f in keep]
        if len(set(kept)) != len(kept) or any(not 0 <= f < frames for f in kept):
            raise ValueError(f"keep {kept}: distinct frames of 0 to {frames - 1}")
        seconds["inputs"] = time.perf_counter() - clock
        job = scratch / "job.json"
        job.write_text(json.dumps({
            "body": str(npz), "positions": str(scratch / "positions.npy"),
            "normals": str(scratch / "normals.npy") if normals is not None else None, "size": [w, h],
            "views": [[{"yaw": v.yaw, "ortho": v.ortho, "target": list(v.target), "elevation": v.elevation,
                        "distance": v.distance} for v in row] for row in rows],
            "engine": engine, "cull": bool(cull), "clay": bool(clay), "background": list(background), "keep": kept,
            "out": str(scratch / "frames.npy"), "cells": str(scratch / "cell.tga"),
            "timing": str(scratch / "timing.json"),
            "mp4": {"path": str(scratch / "out.mp4"), "fps": fps, "crf": int(crf), "ffmpeg": tool} if movie else None}),
            encoding="utf-8")
        script = Path(__file__).with_name("batch_inside.py")
        cells = frames * sum(len(r) for r in rows)
        with slot() as held:
            seconds["slot_wait"] = held.waited
            start = time.time()
            try:
                run = subprocess.run([str(exe), "--background", "--factory-startup", "--python-exit-code", "1",
                                      "--python", str(script), "--", str(job)], capture_output=True, text=True,
                                     timeout=TIMEOUT + 2 * cells, pass_fds=held.fds)
            except subprocess.TimeoutExpired:
                raise ValueError(f"Blender took past {TIMEOUT + 2 * cells} s for {frames} frames") from None
            seconds["blender"] = time.time() - start
        timing = scratch / "timing.json"
        if run.returncode != 0 or not timing.is_file():
            tail = [x for x in (run.stdout + run.stderr).splitlines() if x.strip()][-4:]
            raise ValueError(f"Blender failed ({run.returncode}): {' | '.join(tail)}")
        inside = json.loads(timing.read_text(encoding="utf-8"))
        seconds["launch"] = inside.pop("began") - start
        seconds.update(inside)
        clock = time.perf_counter()
        got = np.load(scratch / "frames.npy") if kept else np.zeros((0, h * len(rows), w * max(map(len, rows)), 4),
                                                                      np.uint8)
        seconds["load"] = time.perf_counter() - clock
        if movie:
            if not (scratch / "out.mp4").is_file():
                raise ValueError(f"ffmpeg wrote no {movie.name}")
            shutil.move(scratch / "out.mp4", movie)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    seconds["wall"] = time.perf_counter() - wall
    if log is not None:
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"frames": frames, "vertices": vertices, "triangles": len(arrays["triangles"]),
                                 "views": [len(r) for r in rows], "size": [w, h], "engine": engine, "body": key[:12],
                                 "body_cached": was, "mp4": str(movie) if movie else None,
                                 "seconds": {k: round(v, 4) if isinstance(v, float) else v
                                             for k, v in seconds.items()}}) + "\n")
    return Batch(got, movie, seconds, was)


__all__ = ["CACHE", "KEEP_DAYS", "SLOTS", "TIMEOUT", "Batch", "Body", "Slot", "View", "cache_path", "cached",
           "content_key", "render", "slot", "slots"]
