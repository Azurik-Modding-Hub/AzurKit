"""Xbox ADPCM, the codec the game's sounds play in, and the wave entry a
new sound is written as (Step 2.141; ``docs/RE_DATA.md`` § "fx.xbr wave
codec").

A wave entry is the 16-byte header 0xAC400 reads (rate, sample count,
channels, bits, streamed, codec, padding) and the payload 0xAC6F0 hands
``SetBufferData`` as it is: Xbox ADPCM, 36-byte blocks of 64 samples, a
block's header the first sample, its step index and a reserved 0, then
63 4-bit IMA codes, low nibble first, the 64th left 0.  0xAC6F0 takes the
buffer's length from the header, ``(count >> 6) * 36`` bytes for mono,
so :func:`wave_entry` writes ``count = 64 * blocks``.  Everything here is
mono at :data:`RATE`: a stereo entry's count holds half its frames, and
nothing the build writes needs two channels.

Ported from the Azurik Dialogue Studio (``audio_formats.py`` at
1436af407e83; MIT, "Copyright (c) 2026 Azurik Modding Hub contributors";
``NOTICE.md``), mono only: the IMA tables, :func:`_expand` and
:func:`_quantize` (its ``_expand``, ``_quantize``), :func:`encode` (its
``encode_xbox_adpcm``), :func:`decode` (its ``decode_xbox_adpcm``),
:func:`read_wav` (its ``_read_wav``) and :func:`_resampled` (its
``_resampled_frame``).  Ours: the downmix, the rate rule and
:func:`wave_entry`.
"""

from __future__ import annotations

import functools
import hashlib
import io
import math
import struct
import wave
from pathlib import Path
from typing import NamedTuple, Sequence
from azurkit.core import fdlibm

RATE = 22050
"""The rate every sound the build writes plays at (454 of fx.xbr's 669
inline waves use it)."""
LONGEST_WAVE = 5.776
"""The longest inline wave fx.xbr holds (s; Step 2.141's read): a longer
sound plays by the same rule, unseen in game."""
BLOCK, FRAMES = 36, 64
"""A mono block's bytes and the samples it holds."""
_STEP = tuple(int(v) for v in "7/8/9/10/11/12/13/14/16/17/19/21/23/25/28/31/34/37/41/45/50/55/60/66/73/80/88/97/107/118/130/143/157/173/190/209/230/253/279/307/337/371/408/449/494/544/598/658/724/796/876/963/1060/1166/1282/1411/1552/1707/1878/2066/2272/2499/2749/3024/3327/3660/4026/4428/4871/5358/5894/6484/7132/7845/8630/9493/10442/11487/12635/13899/15289/16818/18500/20350/22385/24623/27086/29794/32767".split("/"))
_INDEX = (-1, -1, -1, -1, 2, 4, 6, 8)


def _expand(code: int, predictor: int, index: int) -> tuple[int, int]:
    step = _STEP[index]
    delta = (step >> 3) + (step >> 2 if code & 1 else 0) + (step >> 1 if code & 2 else 0) + (step if code & 4 else 0)
    predictor = max(-32768, min(32767, predictor + (-delta if code & 8 else delta)))
    return predictor, max(0, min(88, index + _INDEX[code & 7]))


def _quantize(sample: int, predictor: int, index: int) -> tuple[int, int, int]:
    difference = sample - predictor
    code = 8 if difference < 0 else 0
    difference = abs(difference)
    step = _STEP[index]
    for bit, amount in ((4, step), (2, step >> 1), (1, step >> 2)):
        if difference >= amount:
            code |= bit
            difference -= amount
    return code, *_expand(code, predictor, index)


def encode(samples: Sequence[int]) -> bytes:
    """Mono PCM16 ``samples`` as Xbox ADPCM, padded with silence to whole
    64-sample blocks (never trimmed); each block's step index is the one
    nearest twice the mean step of its first 8 samples, and an all-zero
    block stays all zeros.  :class:`ValueError` for no samples or one an
    int16 can't hold."""
    values = list(samples)
    if not values:
        raise ValueError("Xbox ADPCM: no samples to encode")
    if any(not -32768 <= v <= 32767 for v in values):
        raise ValueError("Xbox ADPCM: a sample is outside int16")
    values += [0] * (-len(values) % FRAMES)
    out = bytearray()
    for first in range(0, len(values), FRAMES):
        block = bytearray(BLOCK)
        chunk = values[first:first + FRAMES]
        if any(chunk):
            predictor = chunk[0]
            average = sum(abs(chunk[i] - chunk[i - 1]) for i in range(1, 9)) / 8
            index = min(range(89), key=lambda i: abs(_STEP[i] - average * 2))
            struct.pack_into("<hBB", block, 0, predictor, index, 0)
            for frame, sample in enumerate(chunk[1:]):
                code, predictor, index = _quantize(sample, predictor, index)
                block[4 + frame // 2] |= code << (4 * (frame & 1))
        out += block
    return bytes(out)


def decode(payload: bytes) -> list[int]:
    """Mono Xbox ADPCM ``payload`` (whole 36-byte blocks) as PCM16, 64
    samples a block: the header's sample, then its 63 codes."""
    if not payload or len(payload) % BLOCK:
        raise ValueError(f"Xbox ADPCM: {len(payload)} bytes are not whole {BLOCK}-byte blocks")
    out: list[int] = []
    for start in range(0, len(payload), BLOCK):
        predictor, index, reserved = struct.unpack_from("<hBB", payload, start)
        if index > 88 or reserved:
            raise ValueError(f"Xbox ADPCM: block {start // BLOCK}'s header is not one")
        out.append(predictor)
        for frame in range(FRAMES - 1):
            code = payload[start + 4 + frame // 2] >> (4 * (frame & 1)) & 15
            predictor, index = _expand(code, predictor, index)
            out.append(predictor)
    return out


def wave_entry(samples: Sequence[int]) -> bytes:
    """A wave entry for mono ``samples`` at :data:`RATE`: the 16-byte
    header (rate, count = 64 x blocks, 1 channel, 4 bits, inline, codec 1
    Xbox ADPCM, 0) and the payload, so 0xAC6F0's length,
    ``(count >> 6) * 36``, is the payload's.  A part kept by its samples
    (:mod:`~azurkit.tools.characters.parts`, Step 4.6q: a variant's
    sounds are named for it, so a copy under another name encodes the same
    samples again), where each is a Python int an int16 holds."""
    from array import array

    from azurkit.tools.characters import parts

    values = list(samples)
    named = None
    if values and all(type(v) is int and -32768 <= v <= 32767 for v in values):
        named = parts.key("wave", hashlib.sha256(array("h", values).tobytes()).hexdigest())
        if (kept := parts.get(named, "wave")) is not None:
            return kept
    payload = encode(values)
    entry = struct.pack("<II4BI", RATE, len(payload) // BLOCK * FRAMES, 1, 4, 0, 1, 0) + payload
    if named is not None:
        parts.put(named, entry, len(entry))
    return entry


class WavInfo(NamedTuple):
    """What a WAV file held, for the build log."""

    rate: int
    channels: int
    bits: int
    frames: int


RADIUS = 16
"""The windowed sinc's reach, in source frames either side."""


@functools.lru_cache(maxsize=1024)
def _taps(phase: float, cutoff: float) -> tuple[int, tuple[float, ...], float]:
    """The windowed-sinc weights at a position ``phase`` past a source
    frame (``0 <= phase < 1``), low-passed to ``cutoff``: the first tap's
    frame from that one, each tap's weight in frame order and their sum,
    added in that order. A rate's positions fall on a few phases (44.1 kHz
    on one), so each is worked out once, not once a sample: each weight is
    the one :func:`_resampled` worked out at each frame, bit for bit
    (``frame - position`` is ``tap - phase``, ``phase`` the position less
    its frame exactly)."""
    first, weights, total = None, [], 0.0
    for tap in range(1 - RADIUS, RADIUS + 1):
        distance = tap - phase
        if abs(distance) >= RADIUS:
            continue
        x = distance * cutoff
        sinc = 1.0 if abs(x) < 1e-12 else fdlibm.sin(math.pi * x) / (math.pi * x)
        weights.append(cutoff * sinc * (0.5 + 0.5 * fdlibm.cos(math.pi * distance / RADIUS)))
        total += weights[-1]
        first = tap if first is None else first
    return first, tuple(weights), total


def _resampled(samples: Sequence[int], position: float, ratio: float) -> int:
    """The windowed-sinc value of mono ``samples`` at ``position`` (a
    source frame), low-passed to ``ratio`` (out rate / in rate) when it
    downsamples: :func:`_taps`' weights at its phase, summed in frame order
    over the frames ``samples`` holds."""
    centre = int(position)
    first, weights, total = _taps(position - centre, min(1.0, ratio) * 0.95)
    start = centre + first
    value = 0.0
    if start >= 0 and start + len(weights) <= len(samples):
        for sample, weight in zip(samples[start:start + len(weights)], weights):
            value += sample * weight
        return max(-32768, min(32767, round(value / total)))
    total = 0.0
    for index, weight in enumerate(weights, start):
        if 0 <= index < len(samples):
            total += weight
            value += samples[index] * weight
    return max(-32768, min(32767, round(value / total)))


def read_wav(path: str | Path) -> tuple[list[int], WavInfo]:
    """``path``'s sound as mono PCM16 at :data:`RATE` and what the file
    held: an uncompressed integer WAV of 8, 16, 24 or 32 bits, mono or
    stereo (downmixed, ``(left + right) >> 1``), at any rate (resampled
    with a windowed sinc to ``ceil(frames x RATE / rate)`` samples).  A
    file stdlib ``wave`` can't read (a float or compressed WAV), more
    than two channels or no frames raise :class:`ValueError` naming the
    file (D35).  There is no length limit.  A part kept by the file's
    bytes (:mod:`~azurkit.tools.characters.parts`, Step 4.6q: a copy of a
    variant reads its WAVs again), each call given its own list."""
    from azurkit.tools.characters import parts

    data = Path(path).read_bytes()
    named = parts.key("wav", hashlib.sha256(data).hexdigest())
    if (kept := parts.get(named)) is not None:
        return list(kept[0]), kept[1]
    samples, info = _read_wav(path, data)
    parts.put(named, (tuple(samples), info), 36 * len(samples))   # an int object and its slot each
    return samples, info


def _read_wav(path: str | Path, data: bytes) -> tuple[list[int], WavInfo]:
    """:func:`read_wav`'s work on the file's ``data``."""
    try:
        with wave.open(io.BytesIO(data), "rb") as source:
            channels, width, rate = source.getnchannels(), source.getsampwidth(), source.getframerate()
            frames = source.getnframes()
            raw = source.readframes(frames)
    except (wave.Error, EOFError, struct.error) as exc:
        raise ValueError(f"{path}: not an uncompressed integer PCM WAV ({exc}); float and "
                         "compressed WAVs aren't read") from None
    if channels not in (1, 2):
        raise ValueError(f"{path}: {channels} channels; a sound here is mono or stereo")
    if width not in (1, 2, 3, 4):
        raise ValueError(f"{path}: {8 * width}-bit samples; it reads 8, 16, 24 or 32")
    frames = len(raw) // (channels * width)
    if not frames or rate <= 0:
        raise ValueError(f"{path}: no sound (0 frames)")
    if width == 1:
        values = [(b - 128) * 256 for b in raw]
    else:
        shift = (width - 2) * 8
        values = [int.from_bytes(raw[i:i + width], "little", signed=True) >> shift
                  for i in range(0, frames * channels * width, width)]
    mono = values if channels == 1 else [(values[i] + values[i + 1]) >> 1 for i in range(0, len(values), 2)]
    info = WavInfo(rate, channels, 8 * width, frames)
    if rate == RATE:
        return mono, info
    out = -(-frames * RATE // rate)
    return [_resampled(mono, k * rate / RATE, RATE / rate) for k in range(out)], info


__all__ = ["BLOCK", "FRAMES", "LONGEST_WAVE", "RATE", "WavInfo", "decode", "encode", "read_wav", "wave_entry"]
