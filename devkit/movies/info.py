"""``python -m devkit movies info PATH``: a Bink movie's header (Modkit's
``movies info``, ported in Step 4.6l): its size, resolution, frame count,
frame rate, length and audio tracks, for one ``.bik`` or, given a folder,
each ``.bik`` directly in it as a table (one it can't read is left out).

The game's 14 movies (``movies/``; ``azurkit files IMAGE --extract
movies/Title.bik --out Title.bik`` writes one) are Bink 1 (``BIKi``)
files, 640x480 at 30 fps with one audio track. The header is 11
little-endian words: the magic, the file's size less 8, the frame count,
the largest frame's size, the frame count again (the one the game reads;
the first when it is 0), the width and height, the frame rate's numerator
and denominator, the video flags and the audio track count. No frame or
sample is decoded. A path that isn't there, a file shorter than the header
or one of another magic is one ``movies info:`` line and exit 1.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

MAGIC = b"BIKi"
HEADER = struct.Struct("<4s10I")   # 44 bytes


@dataclass(frozen=True)
class BinkInfo:
    path: str
    file_size: int
    declared_size: int     # the header's size less 8
    frame_count: int
    max_frame_bytes: int
    width: int
    height: int
    frame_rate_num: int
    frame_rate_den: int
    video_flags: int
    audio_track_count: int

    @property
    def fps(self) -> float:
        return self.frame_rate_num / self.frame_rate_den if self.frame_rate_den else 0.0

    @property
    def duration_seconds(self) -> float:
        return self.frame_count / self.fps if self.fps > 0 and self.frame_count > 0 else 0.0

    @property
    def resolution(self) -> str:
        return f"{self.width}x{self.height}"

    def to_json_dict(self) -> dict:
        return {"path": self.path, "file_size": self.file_size, "declared_size": self.declared_size,
                "frame_count": self.frame_count, "max_frame_bytes": self.max_frame_bytes, "width": self.width,
                "height": self.height, "frame_rate_num": self.frame_rate_num,
                "frame_rate_den": self.frame_rate_den, "fps": round(self.fps, 3),
                "duration_seconds": round(self.duration_seconds, 3), "resolution": self.resolution,
                "video_flags": self.video_flags, "audio_track_count": self.audio_track_count}


def inspect_bink_file(path: str | Path) -> BinkInfo:
    """The header of the ``.bik`` at ``path``; ``FileNotFoundError`` when it
    isn't there, ``ValueError`` when it is too short or not Bink 1."""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(f"{p}: no such file")
    with p.open("rb") as fh:
        head = fh.read(HEADER.size)
    if len(head) < HEADER.size:
        raise ValueError(f"{p.name}: file too small ({len(head)} B); need at least {HEADER.size} B for a Bink header")
    magic, declared, frames_a, max_frame, frames_b, width, height, num, den, flags, tracks = HEADER.unpack(head)
    if magic != MAGIC:
        raise ValueError(f"{p.name}: bad magic {magic!r}; expected {MAGIC!r} (Bink 1 / 1.9)")
    return BinkInfo(str(p), p.stat().st_size, declared, frames_b or frames_a, max_frame, width, height, num, den,
                    flags, tracks)


def inspect_directory(path: str | Path) -> list[BinkInfo]:
    """Each ``.bik`` directly in the folder ``path`` it can read, by name."""
    p = Path(path).expanduser().resolve()
    if not p.is_dir():
        raise NotADirectoryError(f"{p}: not a folder")
    out = []
    for f in sorted(p.glob("*.bik")):
        try:
            out.append(inspect_bink_file(f))
        except (OSError, ValueError):
            continue
    return out


def format_info(info: BinkInfo) -> str:
    return "\n".join([
        Path(info.path).name,
        f"  file size     : {info.file_size:,} B",
        f"  resolution    : {info.resolution}",
        f"  frame count   : {info.frame_count:,}",
        f"  frame rate    : {info.frame_rate_num}/{info.frame_rate_den}  ({info.fps:.3f} Hz)",
        f"  duration      : {info.duration_seconds:.2f} s",
        f"  audio tracks  : {info.audio_track_count}",
        f"  max frame     : {info.max_frame_bytes:,} B",
        f"  flags         : 0x{info.video_flags:08X}"])


def format_info_table(infos: list[BinkInfo]) -> str:
    if not infos:
        return "(no Bink files found)"
    heads = ("file", "size (MB)", "wxh", "frames", "fps", "dur", "tracks")
    row = lambda cells: "  ".join(c.ljust(24) if k == 0 else c.rjust(w)   # noqa: E731
                                  for k, (c, w) in enumerate(zip(cells, (24, 10, 9, 6, 5, 7, 6))))
    lines = [row(heads), row("-" * len(h) for h in heads)]
    for i in infos:
        lines.append(f"{Path(i.path).name:<24s}  {i.file_size / 2**20:>10.1f}  {i.resolution:>9s}  "
                     f"{i.frame_count:>6,d}  {i.fps:>5.2f}  {i.duration_seconds:>6.1f}s  {i.audio_track_count:>6d}")
    lines += ["", f"Total: {len(infos)} files, {sum(i.file_size for i in infos) / 2**20:.1f} MB, "
                  f"{sum(i.duration_seconds for i in infos):.1f} s playback"]
    return "\n".join(lines)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m devkit movies info", description="Read a Bink movie's header.")
    p.add_argument("path", help="a .bik file, or a folder of them (a table)")
    p.add_argument("--json", action="store_true", help="JSON: an object, or a folder's list")
    return p


def main(argv: list[str]) -> int:
    args = parser().parse_args(argv)
    p = Path(args.path)
    try:
        if p.is_dir():
            infos = inspect_directory(p)
            text = json.dumps([i.to_json_dict() for i in infos], indent=2) if args.json else format_info_table(infos)
        else:
            info = inspect_bink_file(p)
            text = json.dumps(info.to_json_dict(), indent=2) if args.json else format_info(info)
    except (OSError, ValueError) as exc:
        print(f"movies info: {exc}", file=sys.stderr)
        return 1
    print(text)
    return 0
