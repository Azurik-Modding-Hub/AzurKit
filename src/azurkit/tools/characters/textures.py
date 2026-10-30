"""New textures for an archive: DXT1/DXT3/BGRA8 ``surf`` payloads with
their mip chains, animated lists, a recolour of a vanilla texture and a
PNG of the user's (Step 2.157, D362, D446).

The ``surf`` layout (``docs/XBR_FORMAT.md`` § "Graphics resources";
Step 2.157's census of all 1,490 textures and 77 lists of characters.xbr
and fx.xbr, every header rebuilt from three numbers):

- a texture: +0 the type, the format (0x10 BGRA8, 0x20 DXT1, 0x40 DXT3)
  with bit 28 (a mip chain); +4 0x40001; +28/+32 the f32 width and
  height; +40 the i32 88 (the texels at +128, a self-relative pointer);
  every other header byte 0.  The texels are every level of the chain
  down to 1x1, each at least one 4x4 block (DXT), DXT blocks in row
  order, BGRA8 linear (the loader swizzles it, 0x9CA50); the payload is
  that, 128-aligned.  A square power-of-two texture's TOC size is
  exactly that (all 1,467 square ones of characters.xbr and fx.xbr);
  the 23 non-square ones' chain rule is unread, so :func:`surf` takes
  square power-of-two images only.
- an animated list: +0 1, +4 the frame count and +8 the i32 4, a
  self-relative pointer to +12, the frame ``surf`` indices (each a
  relocated field): 12 + 4 x frames bytes (:func:`list_surf`).

The BC1/BC2 encoder is a port of Azurik Level Studio's
``asset_editing._dxt`` (commit 6c23060, MIT; ``NOTICE.md``): endpoints
picked from the block's own colours along its longest colour axis (the
darkest, the farthest from it, the farthest from that), edge texels
replicated; an opaque block always has c0 > c1 (equal endpoints are
nudged apart), so the GPU never decodes it in three-colour mode with a
transparent index (``render._dxt_colors``), DXT3's colour block too; a
DXT1 block with a texel under alpha 128 is three-colour with index 3
transparent.  Integer arithmetic only, so the bytes are the same on
every machine.  The chain is box-filtered (each level the rounded mean
of 2x2 texels).

:func:`recolor` maps a texture's luminance through a colour ramp (alpha
kept): the electric blue of an effect from its vanilla shape.
:func:`read_png` reads an 8-bit RGB or RGBA, non-interlaced PNG (every
row filter); :func:`~azurik_mod.xbr.draw.png_rgba` writes one.  Nothing
here prints a byte.
"""

from __future__ import annotations

import math
import struct
import zlib
from collections.abc import Sequence

import numpy as np

from azurkit.tools.characters import render

FORMATS = {"dxt1": 0x20, "dxt3": 0x40, "bgra8": 0x10}
"""A ``surf``'s formats by name: the low 16 bits of its type word."""
MIPS = 0x10000000
"""The type word's bit for a mip chain (every texture of characters.xbr and fx.xbr has one)."""
LIST = 1
"""The type word of an animated list."""
HEADER = 128
TEXELS = 88
"""+40's self-relative pointer to the texels at +128."""
BLOCK = {0x20: 8, 0x40: 16}


def _check_size(w: int, h: int) -> None:
    if w != h or w < 1 or w & (w - 1) or w > 4096:
        raise ValueError(f"a {w}x{h} texture: only square power-of-two sizes up to 4096 have a known chain rule")


def level_sizes(w: int, h: int) -> list[tuple[int, int]]:
    """The chain's levels, ``w`` x ``h`` down to 1x1."""
    out = [(w, h)]
    while out[-1] != (1, 1):
        lw, lh = out[-1]
        out.append((max(1, lw // 2), max(1, lh // 2)))
    return out


def level_bytes(fmt: int, w: int, h: int) -> int:
    """One level's texel bytes in format ``fmt``."""
    if fmt in BLOCK:
        return max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * BLOCK[fmt]
    if fmt == 0x10:
        return w * h * 4
    raise ValueError(f"surf format 0x{fmt:X} isn't one of {', '.join(f'0x{v:X}' for v in FORMATS.values())}")


def surf_size(fmt: int, w: int, h: int) -> int:
    """A ``w`` x ``h`` texture's payload size: the header and its chain, 128-aligned."""
    n = HEADER + sum(level_bytes(fmt, lw, lh) for lw, lh in level_sizes(w, h))
    return -(-n // 128) * 128


def header(fmt: int, w: int, h: int) -> bytes:
    """A texture's 128-byte header (the module docstring)."""
    level_bytes(fmt, 1, 1)
    out = bytearray(HEADER)
    struct.pack_into("<II", out, 0, fmt | MIPS, 0x40001)
    struct.pack_into("<ff", out, 28, float(w), float(h))
    struct.pack_into("<i", out, 40, TEXELS)
    return bytes(out)


def chain(rgba: np.ndarray) -> list[np.ndarray]:
    """``rgba`` (h, w, 4 uint8) and its box-filtered levels down to 1x1."""
    out = [np.ascontiguousarray(rgba, dtype=np.uint8)]
    while out[-1].shape[:2] != (1, 1):
        a = out[-1].astype(np.int32)
        if a.shape[0] > 1:
            a = a[0::2] + a[1::2]
        else:
            a = a * 2
        if a.shape[1] > 1:
            a = a[:, 0::2] + a[:, 1::2]
        else:
            a = a * 2
        out.append(((a + 2) // 4).astype(np.uint8))
    return out


def _rgb565(rgb) -> int:
    return ((rgb[0] * 31 + 127) // 255 << 11) | ((rgb[1] * 63 + 127) // 255 << 5) | ((rgb[2] * 31 + 127) // 255)


def _rgb888(value: int) -> tuple[int, int, int]:
    return (((value >> 11) & 31) * 255 // 31, ((value >> 5) & 63) * 255 // 63, (value & 31) * 255 // 31)


def _dxt(rgba: np.ndarray, fmt: int) -> bytes:
    """One level as BC1 (0x20) or BC2 (0x40) blocks, rows of blocks top to
    bottom, edge texels replicated (Level Studio's ``_dxt``, ported)."""
    height, width = rgba.shape[:2]
    px = [[tuple(int(c) for c in rgba[y, x]) for x in range(width)] for y in range(height)]
    dxt1 = fmt == 0x20
    out = bytearray()
    for by in range(0, height, 4):
        for bx in range(0, width, 4):
            block = [px[min(by + y, height - 1)][min(bx + x, width - 1)] for y in range(4) for x in range(4)]
            opaque = [p for p in block if not dxt1 or p[3] >= 128]
            if opaque:   # the block's own colours along its longest colour axis
                seed = min(opaque, key=lambda p: sum(p[:3]))
                high = max(opaque, key=lambda p: sum((p[c] - seed[c]) ** 2 for c in range(3)))
                low = max(opaque, key=lambda p: sum((p[c] - high[c]) ** 2 for c in range(3)))
            else:
                low = high = (0, 0, 0, 0)
            a, b = _rgb565(high), _rgb565(low)
            transparent = dxt1 and len(opaque) != 16
            if transparent:
                a, b = min(a, b), max(a, b)
            else:
                a, b = max(a, b), min(a, b)
                if a == b:
                    if a < 0xFFFF:
                        a += 1
                    else:
                        b -= 1
            colors = [_rgb888(a), _rgb888(b)]
            if transparent:
                colors += [tuple((colors[0][c] + colors[1][c]) // 2 for c in range(3)), (0, 0, 0)]
            else:
                colors += [tuple((2 * colors[0][c] + colors[1][c]) // 3 for c in range(3)),
                           tuple((colors[0][c] + 2 * colors[1][c]) // 3 for c in range(3))]
            bits = 0
            for index, p in enumerate(block):
                if transparent and p[3] < 128:
                    choice = 3
                else:
                    choice = min(range(3 if transparent else 4),
                                 key=lambda c: sum((p[k] - colors[c][k]) ** 2 for k in range(3)))
                bits |= choice << (2 * index)
            if not dxt1:
                out += struct.pack("<Q", sum(((p[3] * 15 + 127) // 255) << (4 * i) for i, p in enumerate(block)))
            out += struct.pack("<HHI", a, b, bits)
    return bytes(out)


def encode(rgba: np.ndarray, fmt: int) -> bytes:
    """One level (h, w, 4 uint8) in format ``fmt``: DXT1/DXT3 blocks or
    BGRA8 texels."""
    if fmt in BLOCK:
        return _dxt(rgba, fmt)
    if fmt == 0x10:
        return np.ascontiguousarray(rgba[:, :, [2, 1, 0, 3]], dtype=np.uint8).tobytes()
    level_bytes(fmt, 1, 1)
    raise AssertionError


def surf(rgba: np.ndarray, fmt: int) -> bytes:
    """A ``surf`` payload of ``rgba`` (a square power-of-two image) in
    format ``fmt`` with its whole chain (the module docstring)."""
    h, w = rgba.shape[:2]
    _check_size(w, h)
    body = b"".join(encode(level, fmt) for level in chain(rgba))
    out = header(fmt, w, h) + body
    return out + bytes(surf_size(fmt, w, h) - len(out))


def list_surf(frames: Sequence[int]) -> tuple[bytes, tuple[int, ...]]:
    """An animated list of the ``surf`` TOC indices ``frames``: its payload
    and the offsets of its relocated fields."""
    if not frames:
        raise ValueError("an animated list needs at least one frame")
    return (struct.pack(f"<IIi{len(frames)}I", LIST, len(frames), 4, *frames),
            tuple(12 + 4 * k for k in range(len(frames))))


def info(payload: bytes) -> dict:
    """A ``surf`` payload's kind: {"list": frame indices} or {"format",
    "width", "height"}."""
    kind = struct.unpack_from("<I", payload, 0)[0]
    if kind == LIST:
        n = struct.unpack_from("<I", payload, 4)[0]
        return {"list": list(struct.unpack_from(f"<{n}I", payload, 12))}
    w, h = (int(v) for v in struct.unpack_from("<2f", payload, 28))
    return {"format": kind & 0xFFFF, "width": w, "height": h, "mips": bool(kind & MIPS)}


def levels(payload: bytes) -> list[np.ndarray]:
    """Every level of a texture payload, decoded as (h, w, 4) RGBA uint8."""
    i = info(payload)
    if "list" in i:
        raise ValueError("an animated list has no texels: decode its frames")
    fmt, w, h = i["format"], i["width"], i["height"]
    at = 40 + struct.unpack_from("<i", payload, 40)[0]
    out = []
    for lw, lh in level_sizes(w, h) if i["mips"] else [(w, h)]:
        out.append(render.texels(payload, at, fmt, lw, lh))
        at += level_bytes(fmt, lw, lh)
    return out


def ramp_colors(ramp) -> tuple[np.ndarray, np.ndarray]:
    """A ramp's stops (positions 0-1) and colours (0-1): ``[[r, g, b] ...]``
    evenly spaced, or ``[[t, r, g, b] ...]`` with ascending t."""
    if not isinstance(ramp, (list, tuple)) or len(ramp) < 2:
        raise ValueError(f"ramp {ramp!r}: at least two colours, each [r, g, b] or [t, r, g, b]")
    width = {len(c) if isinstance(c, (list, tuple)) else 0 for c in ramp}
    if width not in ({3}, {4}) or not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                                         and math.isfinite(v) for c in ramp for v in c):
        raise ValueError(f"ramp {ramp!r}: every stop is [r, g, b] or every one [t, r, g, b], finite numbers")
    a = np.array(ramp, dtype=np.float64)
    t = a[:, 0] if width == {4} else np.linspace(0.0, 1.0, len(a))
    if np.any(np.diff(t) < 0):
        raise ValueError(f"ramp {ramp!r}: its positions t don't ascend")
    return t, a[:, -3:]


def recolor(rgba: np.ndarray, ramp, gamma: float = 1.0, gain: float = 1.0) -> np.ndarray:
    """``rgba`` with each texel's luminance (Rec. 601, times ``gain``,
    clipped to 0-1, to the power ``gamma``) looked up in ``ramp``
    (:func:`ramp_colors`, each channel clipped to 0-1); alpha kept."""
    for name, v in (("gamma", gamma), ("gain", gain)):
        if not (isinstance(v, (int, float)) and math.isfinite(v) and v > 0):
            raise ValueError(f"recolor {name} {v!r}: a finite number above 0")
    t, colors = ramp_colors(ramp)
    lum = (rgba[..., 0] * 0.299 + rgba[..., 1] * 0.587 + rgba[..., 2] * 0.114) / 255.0
    lum = np.clip(lum * gain, 0.0, 1.0) ** gamma
    out = np.empty_like(rgba, dtype=np.uint8)
    for c in range(3):
        out[..., c] = np.floor(np.clip(np.interp(lum, t, colors[:, c]), 0.0, 1.0) * 255.0 + 0.5)
    out[..., 3] = rgba[..., 3]
    return out


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else b if pb <= pc else c


def read_png(blob: bytes) -> np.ndarray:
    """An 8-bit RGB or RGBA, non-interlaced PNG as (h, w, 4) uint8 (RGB
    opaque); any other kind is refused by name."""
    if blob[:8] != (b"\x89PNG" + "\r\n\x1a\n".encode("latin-1")):
        raise ValueError("not a PNG")
    at, idat, head = 8, b"", None
    while at + 12 <= len(blob):
        n, tag = struct.unpack_from(">I4s", blob, at)
        chunk = blob[at + 8:at + 8 + n]
        if len(chunk) != n or zlib.crc32(tag + chunk) & 0xFFFFFFFF != struct.unpack_from(">I", blob, at + 8 + n)[0]:
            raise ValueError(f"PNG chunk {tag!r}: cut off or a bad CRC")
        if tag == b"IHDR":
            head = struct.unpack(">IIBBBBB", chunk)
        elif tag == b"IDAT":
            idat += chunk
        elif tag == b"IEND":
            break
        at += 12 + n
    if head is None or head[2] != 8 or head[3] not in (2, 6) or head[4:] != (0, 0, 0):
        raise ValueError("the PNG isn't 8-bit RGB or RGBA, non-interlaced")
    w, h, bpp = head[0], head[1], 3 if head[3] == 2 else 4
    raw = zlib.decompress(idat)
    stride = w * bpp
    if len(raw) != h * (stride + 1):
        raise ValueError("the PNG's image data isn't its size")
    img = np.zeros((h, stride), np.uint8)
    prev = bytearray(stride)
    for y in range(h):
        kind, row = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        if kind == 1:
            for x in range(bpp, stride):
                row[x] = (row[x] + row[x - bpp]) & 0xFF
        elif kind == 2:
            row = bytearray((r + p) & 0xFF for r, p in zip(row, prev))
        elif kind == 3:
            for x in range(stride):
                row[x] = (row[x] + ((row[x - bpp] if x >= bpp else 0) + prev[x]) // 2) & 0xFF
        elif kind == 4:
            for x in range(stride):
                row[x] = (row[x] + _paeth(row[x - bpp] if x >= bpp else 0, prev[x],
                                          prev[x - bpp] if x >= bpp else 0)) & 0xFF
        elif kind:
            raise ValueError(f"PNG row {y}: filter {kind} isn't one of 0-4")
        img[y] = np.frombuffer(bytes(row), np.uint8)
        prev = row
    img = img.reshape(h, w, bpp)
    if bpp == 3:
        img = np.concatenate((img, np.full((h, w, 1), 255, np.uint8)), 2)
    return img


__all__ = ["FORMATS", "LIST", "MIPS", "chain", "encode", "header", "info", "level_bytes", "level_sizes", "levels",
           "list_surf", "ramp_colors", "read_png", "recolor", "surf", "surf_size"]
