"""Sounds a build makes from a recipe's numbers (Step 2.141; D384, D386):
simple original sounds, made at build time so the recipe is their
source and the goldens pin their bytes.

The sample loop is integer arithmetic only (no float, ``math``,
``random`` or numpy), so a sound is the same on every platform and
Python: numpy's random streams aren't promised stable across versions
(NEP 19) and libm may differ by an ulp, which could move a sample.

- :func:`whoosh` (``generator: "whoosh"`` in a variant's ``sfx``): noise
  through a band that sweeps up and down ``swells`` times, loudest at
  each swell's top, the air a spin or a swing moves.
- :func:`thud` (the bare-hands kit's hit, Step 2.159a, D502): a low
  thump falling in pitch over a little low noise, dying away fast, a
  fist or palm landing soft.
"""

from __future__ import annotations

from azurkit.tools.characters.xbox_adpcm import RATE

_M = 0xFFFFFFFF
LOW, HIGH = 4096, 32768
"""The band's one-pole coefficients (Q16) at a swell's foot and top:
about 230 Hz and 2.4 kHz at 22050 Hz (approximate: a one-pole's
cut-off is ``-ln(1 - a) * rate / 2 pi``)."""
PEAK = 16384
"""A sound's peak sample (-6 dBFS)."""
FADE = RATE // 200
"""The linear fade in and out (5 ms), so a sound starts and ends at 0."""


def mix32(seed: int, take: int) -> int:
    """A 32-bit state from ``seed`` and ``take`` (murmur3's finaliser over
    their golden-ratio sum), never 0 (xorshift's fixed point)."""
    x = (seed * 0x9E3779B1 + take * 0x85EBCA77 + 0x165667B1) & _M
    x ^= x >> 16
    x = x * 0x85EBCA6B & _M
    x ^= x >> 13
    x = x * 0xC2B2AE35 & _M
    x ^= x >> 16
    return x or 1


def whoosh(length: float, swells: int, seed: int, take: int = 0) -> list[int]:
    """A whoosh ``length`` s long at :data:`RATE` (the one float step,
    ``round(length * RATE)`` samples) as PCM16: xorshift32 noise (13, 17,
    5) seeded by :func:`mix32` (``seed``, ``take``), through two cascaded
    one-pole low-passes whose difference is a band, its coefficient swept
    by a triangle that rises and falls ``swells`` times from :data:`LOW` to
    :data:`HIGH` and back, the band scaled by the same triangle, faded in
    and out over :data:`FADE` samples and scaled to a peak of
    :data:`PEAK`.  Each ``take`` is another noise stream of the same
    shape."""
    n = round(length * RATE)
    if n <= 0 or swells <= 0:
        raise ValueError(f"whoosh: length {length!r} s and swells {swells!r} make no sound")
    state, lp1, lp2, out = mix32(seed, take), 0, 0, []
    span = 2 * 65536
    for i in range(n):
        state ^= state << 13 & _M
        state ^= state >> 17
        state ^= state << 5 & _M
        noise = (state >> 16) - 32768
        q = i * swells * span // n % span
        tri = q if q <= 65536 else span - q
        a = LOW + (HIGH - LOW) * tri // 65536
        lp1 += (noise - lp1) * a >> 16
        lp2 += (lp1 - lp2) * a >> 16
        out.append((lp1 - lp2) * tri >> 16)
    fade = min(FADE, n // 2)
    for k in range(fade):
        out[k] = out[k] * k // fade
        out[n - 1 - k] = out[n - 1 - k] * k // fade
    peak = max(map(abs, out))
    return [v * PEAK // peak for v in out] if peak else out


THUD_HIGH, THUD_LOW = 150, 55
"""A thud's pitch (Hz) at its start and at its end."""
THUD_NOISE = 6144
"""Its noise's one-pole low-pass coefficient (Q16, about 100 Hz at 22050 Hz)."""
ATTACK = RATE // 500
"""A thud's linear rise (2 ms)."""


def _sine(phase: int) -> int:
    """A sine of a Q16 cycle's ``phase`` (0-65535) to +/-32768, by two
    parabolas (within about 6% of the sine; integer only)."""
    u = phase & 0x7FFF
    y = 4 * u * (32768 - u) >> 15
    return y if phase & 0x8000 == 0 else -y


def thud(length: float, seed: int, take: int = 0) -> list[int]:
    """A thud ``length`` s long at :data:`RATE` (``round(length * RATE)``
    samples) as PCM16: a sine (:func:`_sine`) falling linearly from
    :data:`THUD_HIGH` to :data:`THUD_LOW` Hz (x3) over xorshift32 noise
    (seeded by :func:`mix32` with ``seed`` and ``take``) through a
    one-pole low-pass (:data:`THUD_NOISE`, x4), rising over
    :data:`ATTACK` samples and dying as the cube of the time left, faded
    out over :data:`FADE` samples and scaled to a peak of :data:`PEAK`."""
    n = round(length * RATE)
    if n <= ATTACK:
        raise ValueError(f"thud: length {length!r} s makes no sound past its {ATTACK}-sample rise")
    state, lp, phase, out = mix32(seed, take), 0, 0, []
    for i in range(n):
        state ^= state << 13 & _M
        state ^= state >> 17
        state ^= state << 5 & _M
        lp += ((state >> 16) - 32768 - lp) * THUD_NOISE >> 16
        phase = (phase + (THUD_HIGH + (THUD_LOW - THUD_HIGH) * i // n) * 65536 // RATE) & 0xFFFF
        left = (n - i) * 65536 // n
        level = (left * left >> 16) * left >> 16
        if i < ATTACK:
            level = level * i // ATTACK
        out.append((3 * _sine(phase) + 4 * lp) * level >> 18)
    fade = min(FADE, n // 2)
    for k in range(fade):
        out[n - 1 - k] = out[n - 1 - k] * k // fade
    peak = max(map(abs, out))
    return [v * PEAK // peak for v in out] if peak else out


__all__ = ["ATTACK", "FADE", "HIGH", "LOW", "PEAK", "THUD_HIGH", "THUD_LOW", "THUD_NOISE", "mix32", "thud", "whoosh"]
