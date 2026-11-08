"""``python -m devkit movies frames BIK --out DIR``: a Bink movie's frames as
PNGs (Modkit's ``movies frames``, ported in Step 4.6l). Bink 1 is
proprietary, so ffmpeg's open ``bink`` decoder writes them: ``--out`` is
required (there is no default beside the input, D36), never the input, and
a folder this run made is removed if ffmpeg fails. With no ffmpeg on PATH
it exits 1 naming it and writes nothing; ``--dry-run`` prints the plan,
the ffmpeg command, instead.

``--info`` needs no decoder: the header's fields and the per-frame offset
table's keyframe count. The table follows the header and each audio
track's descriptor (16 bytes a track in the game's Bink 1.9; 12 and 8 in
earlier revisions, tried in turn): ``frame count + 1`` words, each a
frame's offset with its low bit marking a keyframe, the last the end; the
layout whose first offset is the table's end, rising, the last within the
file, is the one. A refusal is one ``movies frames:`` line and exit 1.
"""

from __future__ import annotations

import argparse
import json
import shutil
import struct
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from azurkit.core import gate
from devkit.movies.info import HEADER, MAGIC, BinkInfo, inspect_bink_file

TRACK_SIZES = (16, 12, 8)   # an audio track's descriptor, by Bink revision


@dataclass(frozen=True)
class BinkFrameTable:
    info: BinkInfo
    offsets: tuple[int, ...]   # each frame's, the end left out
    keyframes: tuple[int, ...]

    def frame_size(self, idx: int) -> int:
        if not 0 <= idx < len(self.offsets):
            raise IndexError(idx)
        end = self.offsets[idx + 1] if idx + 1 < len(self.offsets) else self.info.file_size
        return max(end - self.offsets[idx], 0)


@dataclass
class BinkFramePlan:
    tool: str            # "ffmpeg" or "none"
    command: list[str]
    reason: str
    available: bool

    def to_json_dict(self) -> dict:
        return {"tool": self.tool, "command": list(self.command), "reason": self.reason, "available": self.available}


def describe_bink(path: Path) -> BinkFrameTable:
    """The header and per-frame offset table of the Bink 1 file ``path``;
    ``ValueError`` when it isn't one, or no track layout fits its table."""
    info = inspect_bink_file(path)
    data = Path(path).read_bytes()
    if data[:4] != MAGIC:
        raise ValueError(f"{path} is not a Bink 1 file")
    if info.frame_count <= 0:
        raise ValueError(f"{path}: header reports {info.frame_count} frames")
    last = ""
    for per_track in TRACK_SIZES:
        start = HEADER.size + per_track * max(0, info.audio_track_count)
        end = start + 4 * (info.frame_count + 1)
        if end > len(data):
            last = f"table with per_track={per_track} runs off EOF (end=0x{end:x}, size=0x{len(data):x})"
            continue
        raw = struct.unpack_from(f"<{info.frame_count + 1}I", data, start)
        offsets = tuple(v & ~1 for v in raw)
        if offsets[0] == end and all(a <= b for a, b in zip(offsets, offsets[1:])) and offsets[-1] <= len(data):
            return BinkFrameTable(info, offsets[:-1], tuple(i for i, v in enumerate(raw[:-1]) if v & 1))
        last = f"per_track={per_track}: first=0x{offsets[0]:x} expected=0x{end:x}"
    raise ValueError(f"{path}: couldn't auto-detect offset table layout; last attempt: {last}")


def plan_frame_extraction(path: Path, out_dir: Path, *, pattern: str = "frame_%04d.png") -> BinkFramePlan:
    """The ffmpeg command that writes the frames, or why there is none; runs nothing."""
    if (ffmpeg := shutil.which("ffmpeg")) is None:
        return BinkFramePlan("none", [], "ffmpeg is not on PATH; install it (brew install ffmpeg / apt install ffmpeg)",
                             False)
    return BinkFramePlan("ffmpeg", [ffmpeg, "-y", "-i", str(path), "-vf", "format=rgb24", str(out_dir / pattern)],
                         "ffmpeg detected on PATH: its 'bink' decoder reads Bink 1.x", True)


def extract_frames_via_ffmpeg(path: Path, out_dir: Path, *, pattern: str = "frame_%04d.png") -> BinkFramePlan:
    """Run the plan into ``out_dir``; ``RuntimeError`` naming ffmpeg when it
    isn't on PATH (nothing written) or with the last lines of its stderr
    when it fails (a folder this call made removed)."""
    out_dir = Path(out_dir)
    plan = plan_frame_extraction(path, out_dir, pattern=pattern)
    if not plan.available:
        raise RuntimeError(plan.reason)
    created = not out_dir.exists()
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(plan.command, check=True, capture_output=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        if created:
            shutil.rmtree(out_dir, ignore_errors=True)
        if isinstance(exc, FileNotFoundError):
            raise RuntimeError(f"ffmpeg not found when running plan: {exc}") from exc
        last = (exc.stderr or b"").decode(errors="replace").splitlines()[-3:]
        raise RuntimeError(f"ffmpeg failed with exit {exc.returncode}: "
                           + " / ".join(line.strip() for line in last)) from exc
    return plan


def _new_output(out: Path, source: Path) -> None:
    """D36: never the input or a vanilla image."""
    for name, other in [("the input", source)] + [(f"the vanilla {r.label} image", gate.find(r))
                                                  for r in gate.RELEASES]:
        if other and out.exists() and Path(other).exists() and out.samefile(other):
            raise ValueError(f"{out}: it is {name}, which movies frames never writes into")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m devkit movies frames",
                                description="Write a Bink movie's frames as PNGs by ffmpeg, or read its frame table.")
    p.add_argument("path", help="a .bik file")
    p.add_argument("--out", help="the folder the PNGs go into (needed but with --info)")
    p.add_argument("--pattern", default="frame_%04d.png", help="the PNGs' names (default frame_%%04d.png)")
    p.add_argument("--info", action="store_true", help="the header and its frame table only; no decoder")
    p.add_argument("--dry-run", action="store_true", help="print the plan instead of running ffmpeg")
    p.add_argument("--json", action="store_true", help="one JSON object")
    return p


def main(argv: list[str]) -> int:
    args = parser().parse_args(argv)
    bik = Path(args.path)
    try:
        if args.info:
            table = describe_bink(bik)
            payload = {"file": str(bik), "magic": "BIKi", "frame_count": table.info.frame_count,
                       "fps": round(table.info.fps, 3), "width": table.info.width, "height": table.info.height,
                       "audio_tracks": table.info.audio_track_count, "keyframe_count": len(table.keyframes)}
            print(json.dumps(payload, indent=2) if args.json else "\n".join(f"  {k}: {v}" for k, v in payload.items()))
            return 0
        if not args.out:
            raise ValueError("pass --out DIR; there is no default output folder (D36)")
        out = Path(args.out)
        _new_output(out, bik)
        if args.dry_run:
            plan = plan_frame_extraction(bik, out, pattern=args.pattern)
            if args.json:
                print(json.dumps(plan.to_json_dict(), indent=2))
            else:
                print(f"plan: {plan.reason}" + (f"\n  command: {' '.join(plan.command)}" if plan.command else "")
                      + ("" if plan.available else "\n  available: NO"))
            return 0
        extract_frames_via_ffmpeg(bik, out, pattern=args.pattern)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"movies frames: {exc}", file=sys.stderr)
        return 1
    print(f"extracted frames into {out}")
    return 0
