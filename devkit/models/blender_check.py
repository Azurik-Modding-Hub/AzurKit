"""``python -m devkit models blender-check``: the Blender batch
(``devkit.models.blender.batch``, Step X.62) run on the real Blender,
headless, on a made-up body: every frame back, the body cached, the MP4.

The test suite runs the batch renderer on a stand-in Blender; this verb
runs the real one (headless) on a made-up body, so it needs no game data:
a textured ball of about ``--vertices`` vertices, swaying through
``--frames`` poses (the last the first again), drawn from two views in a
row by one Blender.  It checks that every frame comes back, that each
pose draws its own picture and the repeated pose the same one, that the
ball is drawn on the ground (textured), that a second job on the same
body finds it in the cache and, with ffmpeg on the machine, that the MP4
is written; then it prints each stage's seconds.  Exit 0 when every
check passes, 1 when one fails (named).
"""

from __future__ import annotations

import argparse
import math
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

from devkit.models.blender import batch as bb


def ball(vertices: int) -> tuple[bb.Body, np.ndarray]:
    """A latitude-longitude ball 0.8 m across at z 0.95, red-and-white
    checked on one material, plain on the other; and its normals."""
    nu = max(8, int(math.sqrt(2 * vertices)))
    nv = max(4, vertices // nu)
    u, v = np.meshgrid(np.linspace(0, 2 * np.pi, nu), np.linspace(0.05, np.pi - 0.05, nv))
    points = np.stack([0.4 * np.sin(v) * np.cos(u), 0.4 * np.sin(v) * np.sin(u), 0.95 + 0.4 * np.cos(v)], -1)
    points = points.reshape(-1, 3)
    uvs = np.stack([u / (2 * np.pi), 1 - v / np.pi], -1).reshape(-1, 2)
    idx = np.arange(nu * nv).reshape(nv, nu)
    a, b, c, d = (idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel(), idx[1:, :-1].ravel(), idx[1:, 1:].ravel())
    quads = np.concatenate([np.stack([a, c, b], 1), np.stack([b, c, d], 1)]).reshape(2, -1, 3).transpose(1, 0, 2)
    top = len(quads) // 2
    check = (np.arange(64)[:, None] // 8 + np.arange(64)[None] // 8) % 2 == 0
    tex = np.where(check[..., None], (220, 60, 40, 255), (240, 240, 240, 255)).astype(np.uint8)
    normals = points - (0.0, 0.0, 0.95)
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    return bb.Body(points, uvs, [quads[:top].reshape(-1, 3), quads[top:].reshape(-1, 3)], [tex, None]), normals


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="python -m devkit models blender-check", description=__doc__.split("\n\n")[0])
    ap.add_argument("--vertices", type=int, default=4000, help="the ball's vertices, about (45000: a v4-size body)")
    ap.add_argument("--frames", type=int, default=12, help="poses, the last the first again")
    ap.add_argument("--engine", choices=("workbench", "eevee"), default="workbench")
    ap.add_argument("--blender", help="the Blender executable (default: model preview's search)")
    ap.add_argument("--out", type=Path, help="also keep the frames' sheet (PNG) and the MP4 in this folder")
    args = ap.parse_args(argv)
    body, normals = ball(args.vertices)
    n = max(2, args.frames)
    sway = [0.15 * math.sin(2 * math.pi * f / (n - 1)) for f in range(n - 1)] + [0.0]
    frames = [body.points + (s, 0.0, 0.0) for s in sway]
    views = [[bb.View(180.0, 1.2, (0.0, 0.0, 0.95)), bb.View(150.0, 1.2, (0.0, 0.0, 0.95))]]
    scratch = Path(tempfile.mkdtemp(prefix="azurik-batch-check-"))
    failed = []
    try:
        movie = scratch / "check.mp4" if shutil.which("ffmpeg") else None
        got = bb.render(body, frames, [normals] * n, views=views, size=(224, 320), engine=args.engine, mp4=movie,
                        blender=args.blender)
        again = bb.render(body, frames[:1], views=views, size=(224, 320), engine=args.engine, blender=args.blender)
        f = got.frames
        checks = {
            f"{n} frames back": f.shape == (n, 320, 448, 4),
            "each pose its own picture": all((f[k] != f[k + 1]).any() for k in range(n - 2)),
            "the repeated pose the same picture": np.array_equal(f[0], f[-1]),
            "the ball drawn on the ground": (f[0][160, 112, :3] != f[0][4, 4, :3]).any(),
            "textured (its red checks)": (f[0][..., 0].astype(int) - f[0][..., 1] > 80).any(),
            "the second job finds the body cached": again.body_cached,
            "the MP4 written": movie is None or (movie.is_file() and movie.stat().st_size > 0),
        }
        for name, ok in checks.items():
            print(f"{'ok' if ok else 'FAILED'}: {name}")
            if not ok:
                failed.append(name)
        s = got.seconds
        print(f"{len(body.points)} vertices, {n} frames x {len(views[0])} views ({args.engine}): "
              f"wall {s['wall']:.2f} s, Blender {s['blender']:.2f} s (launch {s['launch']:.2f}, "
              f"build {s['build']:.3f}, pose {s['pose']:.3f}, render {s['render']:.2f}, "
              f"first render {s['first_render']:.2f}, read {s['read']:.3f}, out {s['out']:.3f}, "
              f"finish {s['finish']:.2f}), inputs {s['inputs']:.3f}, slot wait {s['slot_wait']:.2f}; "
              f"{s['wall'] / n:.3f} s a frame")
        if args.out:
            from azurkit.tools.characters.draw import png_rgba
            args.out.mkdir(parents=True, exist_ok=True)
            (args.out / "check.png").write_bytes(png_rgba(np.concatenate(list(f), 0), level=6))
            if movie:
                shutil.copy(movie, args.out / "check.mp4")
    except ValueError as exc:
        print(f"FAILED: {exc}")
        failed.append(str(exc))
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
