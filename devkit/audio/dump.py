"""``python -m devkit audio dump XBR --output DIR``: every ``wave`` entry of an
XBR (``gamedata/fx.xbr``'s sounds, a voice bank such as ``english.xbr``)
written out, classified, with a RIFF/WAVE wrapper for each one the game
decodes, so vgmstream, Audacity or ffmpeg play it (Modkit's ``audio dump``,
ported in Step 4.6l).

**The wave entry** (the game's parser 0xAC400, called by the wave-init
method 0xAC6F0 before the payload goes to
``IDirectSoundBuffer_SetBufferData``): a 16-byte header, then the codec's
bytes.

    +0x00  u32  sample rate (22050, 32000, 44100 ...; one sound plays at 8192)
    +0x04  u32  sample count (0xAC6F0 sizes the buffer from it: ADPCM
                (count >> 6) x 36 B a channel, so a stereo entry holds frames / 2)
    +0x08  u8   channels (1 or 2)
    +0x09  u8   bits a sample (PCM 8 or 16; Xbox ADPCM 4)
    +0x0A  u8   streamed: 1 makes the entry 20 bytes, its u32 at +0x10 the
                TOC index of the ``sdsr`` entry that holds the codec's bytes
    +0x0B  u8   codec (0 PCM, 1 Xbox ADPCM; the parser refuses any other,
                and the sound never plays)
    +0x0C  u32  unused
    +0x10  ...  the codec's bytes

Xbox DirectSound decodes ``WAVE_FORMAT_XBOX_ADPCM`` (0x0069) in hardware, so
a wrapper with that tag (36 bytes a channel a block, 64 samples a block, a
channel) plays as the game hears it; PCM gets ``WAVE_FORMAT_PCM``.

**The classes:** ``xbox-adpcm`` and ``pcm-raw`` (the header parses: a rate
the game uses, 1 or 2 channels, the codec's bits, at most 10 minutes; a WAV
is written), ``too-small`` (under 64 bytes), ``likely-animation`` (a TOC tag
in its first 64 bytes) and ``non-audio`` (the rest: the game doesn't decode
it either). An entry the same size as an earlier one whose first 32 bytes
match is marked its duplicate.

**The output:** ``DIR/waves/wave_NNNN.bin`` (the entry, a streamed one's
samples filled in from its ``sdsr``), ``wave_NNNN.wav`` beside each that
decodes (not with ``--no-wav``), ``wave_NNNN.preview.wav`` with
``--raw-previews`` beside each non-audio one (its bytes as 16-bit mono PCM,
for looking at, not audio), and ``DIR/manifest.json``: per entry its index,
offset, size, class, the entropy of its first 256 bytes, the sha256[:12] of
its first 32 (Modkit's manifest held those bytes in hex), its header, its
name from the XBR's own names (``core.xbr.nodes.named_resources``:
``fx/sound/<entity>/<key>``; fx.xbr names 574 of its 700) and its files.
An XBR it can't read is one ``audio dump:`` line and exit 1.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

from azurkit.core.xbr.nodes import named_resources, parse_toc

ANIMATION_TAGS = (b"gshd", b"ndbg", b"node", b"rdms", b"sprv", b"pbrw", b"pbrc", b"wave", b"surf")
RATES = frozenset({8000, 8192, 11025, 12000, 16000, 22050, 24000, 32000, 44100, 48000})
WAVE_FORMAT_PCM, WAVE_FORMAT_XBOX_ADPCM = 0x0001, 0x0069
CLASSES = ("xbox-adpcm", "pcm-raw", "non-audio", "likely-animation", "too-small")


@dataclass(frozen=True)
class WaveHeader:
    sample_rate: int
    sample_count: int
    channels: int
    bits_per_sample: int
    codec_id: int
    format_magic: int   # bytes 8-11 as one word, as Modkit's manifest kept it

    @property
    def duration_ms(self) -> int:
        return int(self.sample_count * 1000 // self.sample_rate) if self.sample_rate > 0 else 0

    def to_dict(self) -> dict:
        return {"sample_rate": self.sample_rate, "sample_count": self.sample_count,
                "duration_ms": self.duration_ms, "channels": self.channels,
                "bits_per_sample": self.bits_per_sample, "codec_id": self.codec_id,
                "format_magic": f"0x{self.format_magic:08x}"}


@dataclass(frozen=True)
class WaveEntry:
    index: int                 # among the file's wave entries
    file_offset: int
    size: int                  # the payload's, a streamed one's samples in
    classification: str
    entropy: float
    first_bytes_sha256: str    # sha256[:12] of the first 32 bytes, never the bytes
    output_rel: str
    header: WaveHeader | None = None
    wav_output_rel: str = ""
    name: str = ""
    duplicate_of: int = -1
    preview_output_rel: str = ""
    streamed_sdsr: int = -1    # the TOC index of the sdsr holding its samples

    def to_dict(self) -> dict:
        d = {"index": self.index, "file_offset": self.file_offset, "size": self.size,
             "classification": self.classification, "entropy": round(self.entropy, 4),
             "first_bytes_sha256": self.first_bytes_sha256, "output": self.output_rel}
        extra = {"header": self.header.to_dict() if self.header else None, "name": self.name,
                 "wav_output": self.wav_output_rel, "duplicate_of": self.duplicate_of,
                 "preview_wav": self.preview_output_rel, "streamed_sdsr": self.streamed_sdsr}
        return d | {k: v for k, v in extra.items() if v not in (None, "", -1)}


@dataclass
class DumpReport:
    source: str
    output_dir: str
    total_waves: int = 0
    written: int = 0
    wav_written: int = 0
    preview_wav_written: int = 0
    duplicates_detected: int = 0
    counts: dict[str, int] = field(default_factory=lambda: dict.fromkeys(CLASSES, 0))
    entries: list[WaveEntry] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"source": self.source, "output_dir": self.output_dir, "total_waves": self.total_waves,
                "written": self.written, "wav_written": self.wav_written,
                "preview_wav_written": self.preview_wav_written, "duplicates_detected": self.duplicates_detected,
                "classification_counts": dict(self.counts), "entries": [e.to_dict() for e in self.entries]}


def entropy_ratio(data: bytes) -> float:
    """Shannon entropy over bytes, scaled to 0..1 (1: as random as bytes get)."""
    if not data:
        return 0.0
    counts = [0] * 256
    for b in data:
        counts[b] += 1
    return -sum(c / len(data) * math.log2(c / len(data)) for c in counts if c) / 8.0 + 0.0   # 0.0, never -0.0


def parse_wave_header(payload: bytes) -> WaveHeader | None:
    """The 16-byte header as the game's parser takes it, or ``None`` where
    it wouldn't (or the fields aren't a sound's)."""
    if len(payload) < 16:
        return None
    rate, count = struct.unpack_from("<II", payload, 0)
    channels, bits, streamed, codec = payload[8:12]
    if (rate not in RATES or codec not in (0, 1) or channels not in (1, 2) or bits not in (4, 8, 16)
            or (codec == 0 and bits not in (8, 16)) or (codec == 1 and bits != 4) or count > rate * 600):
        return None
    return WaveHeader(rate, count, channels, bits, codec, channels | bits << 8 | streamed << 16 | codec << 24)


def resolve_streamed(payload: bytes, toc, data: bytes) -> tuple[bytes, int]:
    """``(payload, sdsr index)``: a streamed entry's header with its sdsr's
    bytes after it, as an inline one is; anything else as it is, ``-1``."""
    if len(payload) == 20 and payload[10] == 1:
        link = struct.unpack_from("<I", payload, 16)[0]
        if link < len(toc) and toc[link].tag == "sdsr":
            s = toc[link]
            return payload[:16] + data[s.file_offset:s.file_offset + s.size], link
    return payload, -1


def classify_entry(size: int, head: bytes, header: WaveHeader | None = None) -> str:
    if size < 64:
        return "too-small"
    if header is not None:
        return "xbox-adpcm" if header.bits_per_sample == 4 else "pcm-raw"
    return "likely-animation" if any(tag in head[:64] for tag in ANIMATION_TAGS) else "non-audio"


def _riff(fmt: bytes, payload: bytes) -> bytes:
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(payload)) + payload
    return b"RIFF" + struct.pack("<I", len(body)) + body


def build_raw_preview_wav(payload: bytes, *, sample_rate: int = 22050, channels: int = 1,
                          bits_per_sample: int = 16) -> bytes:
    """``payload`` as raw PCM at ``sample_rate``: a diagnostic picture of
    its bytes, not audio (padded to a whole 16-bit sample)."""
    align = channels * (bits_per_sample // 8)
    if bits_per_sample == 16 and len(payload) % 2:
        payload += b"\0"
    return _riff(struct.pack("<HHIIHH", WAVE_FORMAT_PCM, channels, sample_rate, sample_rate * align, align,
                             bits_per_sample), payload)


def build_wav(header: WaveHeader, payload: bytes) -> bytes:
    """The codec's bytes ``payload`` in a RIFF/WAVE of ``header``'s format."""
    ch, rate, bits = header.channels, header.sample_rate, header.bits_per_sample
    if bits == 4:   # Xbox ADPCM: 36 bytes a channel a block, 64 samples a block per channel
        align = 36 * ch
        fmt = struct.pack("<HHIIHHHH", WAVE_FORMAT_XBOX_ADPCM, ch, rate, int(align * rate / 64), align, bits, 2, 64)
    else:
        align = ch * (bits // 8)
        fmt = struct.pack("<HHIIHH", WAVE_FORMAT_PCM, ch, rate, rate * align, align, bits)
    return _riff(fmt, payload)


def dump_waves(xbr: str | Path, output_dir: str | Path, *, entropy_min: float = 0.0, only_audio: bool = False,
               emit_wav: bool = True, emit_raw_previews: bool = False,
               preview_sample_rate: int = 22050) -> DumpReport:
    """Write every wave entry of ``xbr`` into ``output_dir`` (made if
    missing) and its manifest: one under ``entropy_min`` or, with
    ``only_audio``, one that doesn't decode is listed but not written.
    ``OSError`` when a file can't be read or written, ``ValueError`` when
    ``xbr`` isn't an XBR."""
    src = Path(xbr).expanduser().resolve()
    data = src.read_bytes()
    toc = parse_toc(data)
    waves, names = [e for e in toc if e.tag == "wave"], named_resources(data)
    out = Path(output_dir).expanduser().resolve()
    (out / "waves").mkdir(parents=True, exist_ok=True)
    report = DumpReport(str(src), str(out), total_waves=len(waves))
    width, seen = max(4, len(str(len(waves) - 1))), {}
    for i, e in enumerate(waves):
        payload, sdsr = resolve_streamed(data[e.file_offset:e.file_offset + e.size], toc, data)
        head, header = payload[:64], parse_wave_header(payload)
        kind = classify_entry(len(payload), head, header)
        report.counts[kind] += 1
        ratio = entropy_ratio(payload[:256])
        duplicate_of = seen.setdefault((head[:32], len(payload)), i)
        duplicate_of = -1 if duplicate_of == i else duplicate_of
        report.duplicates_detected += duplicate_of >= 0
        write = not (entropy_min > 0.0 and ratio < entropy_min) and not (only_audio and kind not in CLASSES[:2])
        rel = f"waves/wave_{i:0{width}d}.bin"
        wav_rel = preview_rel = ""
        if write:
            (out / rel).write_bytes(payload)
            report.written += 1
            if emit_wav and header is not None:   # the codec's bytes only, as the game hands DirectSound
                wav_rel = rel[:-4] + ".wav"
                (out / wav_rel).write_bytes(build_wav(header, payload[16:]))
                report.wav_written += 1
            if emit_raw_previews and kind == "non-audio" and duplicate_of < 0:
                preview_rel = rel[:-4] + ".preview.wav"
                (out / preview_rel).write_bytes(build_raw_preview_wav(payload, sample_rate=preview_sample_rate))
                report.preview_wav_written += 1
        report.entries.append(WaveEntry(i, e.file_offset, len(payload), kind, ratio,
                                        hashlib.sha256(head[:32]).hexdigest()[:12], rel if write else "", header,
                                        wav_rel, names.get(e.index, ""), duplicate_of, preview_rel, sdsr))
    (out / "manifest.json").write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    return report


def format_report(report: DumpReport, *, preview: int = 0) -> str:
    c = report.counts
    lines = [f"Audio dump from {report.source}", f"  → {report.output_dir}", "",
             f"  total wave entries:      {report.total_waves}", f"  blobs written to disk:   {report.written}",
             f"  WAV wrappers emitted:    {report.wav_written}",
             f"  raw-PCM previews:        {report.preview_wav_written}",
             f"  duplicates detected:     {report.duplicates_detected}", "  classification:"]
    lines += [f"     {kind + ':':<22s}{c[kind]}" for kind in CLASSES]
    if preview > 0 and report.entries:
        lines += ["", f"  Preview (first {preview}):"]
        for e in report.entries[:preview]:
            dur = f" {e.header.duration_ms}ms" if e.header else ""
            name = f"  [{e.name}]" if e.name else ""
            lines.append(f"    [{e.index:4d}] {e.classification:<18s} size={e.size:>6} B  entropy={e.entropy:.2f}"
                         f"{dur}{name}  → {e.output_rel or '(skipped)'}")
    return "\n".join(lines)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m devkit audio dump",
                                description="Write an XBR's wave entries, a WAV each that decodes, and a manifest.")
    p.add_argument("xbr", help="an .xbr file of waves (gamedata/fx.xbr, a voice bank such as english.xbr)")
    p.add_argument("--output", "-o", required=True, help="the folder to write into (made if missing)")
    p.add_argument("--entropy-min", type=float, default=0.0,
                   help="list but don't write an entry whose first 256 bytes' entropy (0..1) is under this")
    p.add_argument("--only-audio", action="store_true", help="list but don't write an entry that doesn't decode")
    p.add_argument("--no-wav", action="store_true", help="no .wav beside each entry that decodes")
    p.add_argument("--raw-previews", action="store_true",
                   help="a .preview.wav of each non-audio entry's bytes as 16-bit mono PCM (to look at, not audio)")
    p.add_argument("--preview-sample-rate", type=int, default=22050, help="the previews' rate (default 22050)")
    p.add_argument("--preview", type=int, default=0, help="list the first N entries too")
    p.add_argument("--json", action="store_true", help="the manifest on stdout")
    return p


def main(argv: list[str]) -> int:
    args = parser().parse_args(argv)
    try:
        report = dump_waves(args.xbr, args.output, entropy_min=args.entropy_min, only_audio=args.only_audio,
                            emit_wav=not args.no_wav, emit_raw_previews=args.raw_previews,
                            preview_sample_rate=args.preview_sample_rate)
    except (OSError, ValueError) as exc:
        print(f"audio dump: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report.to_dict(), indent=2) if args.json else format_report(report, preview=args.preview))
    return 0
