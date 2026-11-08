"""``python -m devkit xbr inspect FILE --tag TAG``: the first records of the
first TOC entry tagged ``TAG``, each 4-byte column classified by a fixed
panel of heuristics (Modkit's ``xbr inspect``, ported in Step 4.6l), to
speed up reading a record layout without a Ghidra round trip.

Each column takes the first label that fits, in this order: ``zero`` (all
four bytes 0), ``fourcc`` (four printable alphanumeric ASCII bytes), ``int32``
(a float that is a small whole number, -255..255, is read as the int),
``f32`` (a finite float, ``|x| <= 1e9``, not under ``1e-30``), ``ptr`` (an
XBE address, 0x10000..0x400000), ``off`` (a value inside the file),
``int32`` (within +-2**20), else ``u32``. With no ``--stride`` the stride
is the one of 16, 20, 24, 28, 32, 40, 48, 64, 80 and 96 whose first eight
records most often start clean (a zero or fourcc word, half a point for a
float or small int).

The value column is the word as its label reads it; the word's own bytes
show only with ``--hex`` (a human's: it prints the file's bytes, as
``re xbe hexdump`` does).
"""

from __future__ import annotations

import argparse
import json
import math
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

from azurkit.core.xbr.nodes import parse_toc

_PRINTABLE = set(range(0x20, 0x7F))
_COMMON_STRIDES = (16, 20, 24, 28, 32, 40, 48, 64, 80, 96)
_IMAGE = (0x00010000, 0x00400000)   # the XBE's addresses a record may hold


@dataclass(frozen=True)
class FieldClassification:
    offset: int        # in the record
    raw: bytes
    best_type: str
    value_display: str


@dataclass
class RecordInspection:
    index: int
    file_offset: int
    stride: int
    fields: list[FieldClassification] = field(default_factory=list)


@dataclass
class SectionInspection:
    tag: str
    stride: int
    records: list[RecordInspection] = field(default_factory=list)
    auto_detected_stride: bool = False


def _looks_like_zero(raw: bytes) -> bool:
    return raw == b"\x00\x00\x00\x00"


def _looks_like_fourcc(raw: bytes) -> bool:
    return len(raw) == 4 and all(b in _PRINTABLE for b in raw) and raw.decode("ascii").isalnum()


def _looks_like_f32(raw: bytes) -> tuple[bool, float | None]:
    (val,) = struct.unpack("<f", raw)
    if not math.isfinite(val) or abs(val) > 1e9 or (val != 0.0 and abs(val) < 1e-30):
        return False, None
    return True, val


def _looks_like_small_int(raw: bytes) -> tuple[bool, int | None]:
    (val,) = struct.unpack("<i", raw)
    return (True, val) if -0x10_0000 <= val <= 0x10_0000 else (False, None)


def _classify(raw: bytes, file_size: int) -> tuple[str, str]:
    """The word's label and its value as that label reads it."""
    if _looks_like_zero(raw):
        return "zero", "0"
    if _looks_like_fourcc(raw):
        return "fourcc", raw.decode("ascii")
    ok_f, fval = _looks_like_f32(raw)
    if ok_f and fval == int(fval) and -0x100 < fval < 0x100:   # a small whole float reads as the int
        return "int32", str(int(fval))
    if ok_f:
        return "f32", f"{fval:.4g}"
    (val,) = struct.unpack("<I", raw)
    if _IMAGE[0] <= val < _IMAGE[1]:
        return "ptr", f"0x{val:08X}"
    if 0 < val < file_size:
        return "off", f"+0x{val:X}"
    ok_i, ival = _looks_like_small_int(raw)
    if ok_i:
        return "int32", str(ival)
    return "u32", f"0x{val:08X}"


def _stride_quality(data: bytes, base: int, size: int, stride: int, max_records: int = 8) -> float:
    """How many of the first records at ``stride`` start clean, as a share;
    a size past the file's end counts only the bytes the file holds."""
    if stride <= 0:
        return 0.0
    size = min(size, max(0, len(data) - base))
    count = min(size // stride, max_records) if size >= stride else 0
    if count < 2:
        return 0.0
    clean = 0.0
    for i in range(count):
        raw = data[base + i * stride:base + i * stride + 4]
        if _looks_like_zero(raw) or _looks_like_fourcc(raw):
            clean += 1
        elif _looks_like_f32(raw)[0] or _looks_like_small_int(raw)[0]:
            clean += 0.5
    return clean / count


def _auto_detect_stride(data: bytes, base: int, size: int) -> int:
    """The common stride that scores best; 16 when none scores."""
    best_stride, best_score = 16, -1.0
    for stride in _COMMON_STRIDES:
        if (score := _stride_quality(data, base, size, stride)) > best_score:
            best_stride, best_score = stride, score
    return best_stride


def inspect_xbr(path: str | Path, *, tag: str, entries: int = 3, stride: int | None = None,
                fields_per_row: int = 6) -> SectionInspection:
    """The first ``entries`` records of the first TOC entry tagged ``tag``,
    at ``stride`` (``None``: detected), ``fields_per_row`` columns each.
    ``OSError`` when the file can't be read, ``ValueError`` when it isn't
    an XBR or has no entry tagged ``tag`` (naming those it has)."""
    p = Path(path).expanduser().resolve()
    data = p.read_bytes()
    toc = parse_toc(data)
    target = next((e for e in toc if e.tag == tag), None)
    if target is None:
        raise ValueError(f"{p.name} has no TOC entry tagged {tag!r}. Available: {sorted({e.tag for e in toc})}")
    size, base = target.size, target.file_offset
    auto = stride is None
    stride = _auto_detect_stride(data, base, size) if auto else stride
    records = []
    for i in range(min(entries, size // max(stride, 1))):
        off = base + i * stride
        rec = RecordInspection(index=i, file_offset=off, stride=stride)
        for col in range(0, min(fields_per_row * 4, stride - 3), 4):
            raw = data[off + col:off + col + 4]
            if len(raw) < 4:
                break
            rec.fields.append(FieldClassification(col, raw, *_classify(raw, len(data))))
        records.append(rec)
    return SectionInspection(tag=tag, stride=stride, records=records, auto_detected_stride=auto)


def format_inspection(insp: SectionInspection, *, hexed: bool = False) -> str:
    lines = [f"Section {insp.tag!r}  stride={insp.stride} B  "
             f"{'(auto-detected)' if insp.auto_detected_stride else '(explicit)'}",
             f"{len(insp.records)} record(s) inspected."]
    for rec in insp.records:
        lines += ["", f"Record #{rec.index}  file 0x{rec.file_offset:06X}:"]
        for f in rec.fields:
            raw = f"  {f.raw.hex():<8s}" if hexed else ""
            lines.append(f"  + {f.offset:3d}{raw}  [{f.best_type:<6s}]  {f.value_display}")
    return "\n".join(lines)


def to_json(insp: SectionInspection, *, hexed: bool = False) -> dict:
    return {"tag": insp.tag, "stride": insp.stride, "auto_detected_stride": insp.auto_detected_stride,
            "records": [{"index": r.index, "file_offset": r.file_offset,
                         "fields": [{"offset": f.offset, "best_type": f.best_type, "value_display": f.value_display}
                                    | ({"raw": f.raw.hex()} if hexed else {}) for f in r.fields]}
                        for r in insp.records]}


def _positive(text: str) -> int:
    value = int(text, 0)
    if value < 1:
        raise argparse.ArgumentTypeError(f"{text} is not 1 or more")
    return value


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m devkit xbr inspect",
                                description="Classify the first records of a TOC entry's payload, column by column.")
    p.add_argument("path", help="an .xbr file (azurkit files IMAGE MEMBER OUT writes one out of an image)")
    p.add_argument("--tag", required=True, help="the TOC entry's four characters (surf, node, rdms ...)")
    p.add_argument("--entries", type=int, default=3, help="how many records (default 3)")
    p.add_argument("--stride", type=_positive, default=None, help="the record's size in bytes (default: detected)")
    p.add_argument("--fields-per-row", type=int, default=6, help="4-byte columns a record (default 6)")
    p.add_argument("--hex", action="store_true", help="each column's bytes too (a human's: it prints the file's bytes)")
    p.add_argument("--json", action="store_true", help="one JSON object")
    return p


def main(argv: list[str]) -> int:
    args = parser().parse_args(argv)
    try:
        insp = inspect_xbr(args.path, tag=args.tag, entries=args.entries, stride=args.stride,
                           fields_per_row=args.fields_per_row)
    except (OSError, ValueError) as exc:
        print(f"xbr inspect: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(to_json(insp, hexed=args.hex), indent=2) if args.json else format_inspection(insp, hexed=args.hex))
    return 0
