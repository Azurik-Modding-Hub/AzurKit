"""A PNG's image data inflated with bounds (D992's SEC-5): a picture's
file is untrusted input (a community variant's texture, a recipe's colours,
a glTF folder a player names), and zlib inflates one small file to
gigabytes (a ratio of about 1,029: 64 MiB of file to about 66 GB).

:func:`png_rows` refuses a picture past :data:`MAX_SIDE` squared before it
inflates a byte, inflates at most one byte past the rows its header
promises, and refuses any other length: a bomb costs a bounded read, never
the host's memory. The characters' decoders read through it
(``textures.read_png``, ``gltf``'s read-back of an export's pictures)."""

from __future__ import annotations

import zlib

MAX_SIDE = 4096
"""A picture's pixels at most ``MAX_SIDE * MAX_SIDE`` (the review's default)."""


def png_rows(idat: bytes, width: int, height: int, channels: int) -> bytes:
    """The filtered rows of a ``width`` by ``height`` PNG of ``channels``
    bytes a pixel (each row its filter byte and ``width * channels``
    bytes), inflated from its joined IDAT chunks ``idat``; ``ValueError``
    for a picture past :data:`MAX_SIDE` squared, before it inflates, and
    for data that isn't a zlib stream or isn't the rows' size."""
    if width < 1 or height < 1 or width * height > MAX_SIDE * MAX_SIDE:
        raise ValueError(f"a PNG of {width}x{height}: past the {MAX_SIDE}x{MAX_SIDE} pixels a picture may hold")
    expected = height * (width * channels + 1)
    stream = zlib.decompressobj()
    try:
        raw = stream.decompress(idat, expected + 1)
    except zlib.error as exc:
        raise ValueError(f"the PNG's image data isn't zlib ({exc})") from None
    if len(raw) != expected or not stream.eof:
        raise ValueError("the PNG's image data isn't its size")
    return raw
