"""A link's clip (Step 4.78c, D1312): pictures of a replay, one a tick, to an MP4 by ffmpeg (dev only).

The owner reviews new links as a list, a row a link with a short xemu clip.  :class:`Frames` is a replay's
``on_tick`` (``Sandbox.replay(on_tick=)``): at each tick's update entry, the guest halted there, it takes the frame
on screen (:func:`picture`) once the guest has flipped since the last load or checkpoint restore, and skips the
ticks before that, never running the guest to freshen one (``Sandbox.screenshot`` advances a vblank at a time: a
clip's replay can't, its tick count is the check's).  :func:`encode` makes the MP4 at :data:`FPS` (a tick a frame);
a host without ffmpeg is refused by name (:func:`need`).

A clip is a picture of the game: its pictures and MP4 stay private (mode 0600, in a mode-700 folder), never in the
repository or a tracked file.  Offscreen only (``headless="1"``, deterministic for pictures that reproduce): the null
renderer draws nothing, and ``null_ram`` draws only by ``xemu-render-next``, which runs the guest.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

from devkit.xemu.oracle import DISPLAY_QUERY

FPS = 30   # a player tick a frame (vanilla's 30 ticks a second)


def need(tool: str) -> str:
    """The path of ``tool`` (ffmpeg, ffprobe); refused (SystemExit) by name where the host has none."""
    if (path := shutil.which(tool)) is None:
        raise SystemExit(f"clip: {tool} isn't installed (not on PATH): a clip is pictures made an MP4 by ffmpeg; "
                         "install ffmpeg (brew install ffmpeg)")
    return path


def picture(sb, dest: Path) -> Path | None:
    """The halted guest's frame on screen as a PNG at ``dest`` (mode 0600), or None while it predates the last load
    or checkpoint restore (``query-xemu-display``'s ``picture-stale``): never an advance to freshen it.  Refused
    (SystemExit) on the null renderer, ``null_ram`` and a build that can't date a picture: no ``query-xemu-display``
    (v0.15 on), or a reply without ``picture-stale`` (v0.16.1 on; before it ``flip-loads`` under ``loads`` missed a
    checkpoint restore, fresh for 1-6 vblanks while the picture was the loaded frame, and each clip try starts at
    one)."""
    st = sb.st
    if st.get("headless") == "null" or st.get("null_ram"):
        raise SystemExit("clip: the null renderer draws nothing and null_ram draws only by running the guest: a clip "
                         "runs offscreen (headless '1', deterministic)")
    if not st.get("display_query"):
        raise SystemExit(f"clip: this xemu can't date a picture (no {DISPLAY_QUERY}: v0.15 on)")
    d = sb.qmp(DISPLAY_QUERY).get("return", {})
    if "picture-stale" not in d:
        raise SystemExit(f"clip: this xemu's {DISPLAY_QUERY} gives no picture-stale (v0.16.1 on): without it a "
                         "picture just after a checkpoint restore can't be dated")
    if d["picture-stale"]:
        return None
    tmp = Path(sb.w) / f"clip.{os.getpid()}.png"   # xemu writes in W
    r = sb.qmp("screendump", filename=str(tmp), format="png")
    if "error" in r or not tmp.exists():
        raise SystemExit(f"clip: screendump: {r.get('error', {}).get('desc', 'no file written')}")
    dest = Path(dest)
    shutil.move(tmp, dest)
    dest.chmod(0o600)
    return dest


def private_dir(path: Path | str) -> Path:
    """``path`` resolved (the clip rows keep it, so ``list`` links a clip from any folder), made mode 700 where
    missing; one anyone else may enter is refused (a clip is a picture of the game)."""
    path = Path(path).resolve()
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == "posix" and path.stat().st_mode & 0o077:
        raise SystemExit(f"clip: {path.name}/ is open to others (mode {path.stat().st_mode & 0o777:o}): a clip is "
                         "a picture of the game, kept in a mode-700 folder")
    return path


class Frames:
    """A clip's pictures (a replay's ``on_tick``): one a tick once fresh, ``00001.png`` on, in ``folder``
    (private), a tick met twice (a popup's part again) pictured once; ``stale``: the ticks skipped before."""

    def __init__(self, folder: Path | str, take=picture) -> None:
        self.folder, self.take = Path(folder), take
        self.paths: list[Path] = []
        self.digests: list[str] = []
        self.ticks: set[int] = set()
        self.stale = 0

    def reset(self) -> None:
        """No picture yet (a try again starts its clip again)."""
        self.clear()
        private_dir(self.folder)

    def __call__(self, sb, k: int) -> None:
        if k in self.ticks:
            return
        self.ticks.add(k)
        p = self.take(sb, self.folder / f"{len(self.paths) + 1:05d}.png")
        if p is None:
            self.stale += 1
            return
        self.paths.append(p)
        self.digests.append(hashlib.sha256(Path(p).read_bytes()).hexdigest())

    def __len__(self) -> int:
        return len(self.paths)

    def distinct(self) -> float | None:
        """The share of consecutive pictures that differ (None under two)."""
        pairs = list(zip(self.digests, self.digests[1:]))
        return round(sum(a != b for a, b in pairs) / len(pairs), 4) if pairs else None

    def clear(self) -> None:
        """The pictures and their folder gone (only this clip's own names)."""
        for p in self.paths:
            Path(p).unlink(missing_ok=True)
        self.paths, self.digests, self.ticks, self.stale = [], [], set(), 0
        if self.folder.is_dir():
            for p in self.folder.glob("[0-9][0-9][0-9][0-9][0-9].png"):
                p.unlink()
            try:
                self.folder.rmdir()
            except OSError:
                pass   # something not a picture of ours: left


def probe(path: Path) -> float | None:
    """The MP4's duration in seconds by ffprobe (None without one)."""
    if (ff := shutil.which("ffprobe")) is None:
        return None
    r = subprocess.run([ff, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True, check=False)
    try:
        return round(float(r.stdout.strip()), 3)
    except ValueError:
        return None


def encode(frames: Frames, out: Path | str, fps: int = FPS) -> dict:
    """``frames``' pictures as an H.264 MP4 at ``out`` (mode 0600, ``fps`` a second, never over a file there):
    its bytes, the pictures and ffprobe's duration."""
    ff, out = need("ffmpeg"), Path(out)
    if not frames.paths:
        raise SystemExit(f"clip: {out.name}: no picture to encode")
    if out.exists():
        raise SystemExit(f"clip: {out.name} exists: a clip is never overwritten")
    part = out.with_name(f".{out.name}.part")
    cmd = [ff, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-framerate", str(fps), "-start_number", "1",
           "-i", str(frames.folder / "%05d.png"), "-frames:v", str(len(frames)), "-c:v", "libx264",
           "-pix_fmt", "yuv420p", "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-r", str(fps),
           "-movflags", "+faststart", "-f", "mp4", str(part)]
    r = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if r.returncode != 0 or not part.exists():
        part.unlink(missing_ok=True)
        tail = (r.stderr.strip().splitlines() or ["no output"])[-1][:200]
        raise SystemExit(f"clip: ffmpeg made no {out.name} (exit {r.returncode}): {tail}")
    part.chmod(0o600)
    os.replace(part, out)
    return {"bytes": out.stat().st_size, "pictures": len(frames), "duration_s": probe(out)}
