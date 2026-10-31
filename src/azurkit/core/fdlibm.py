"""The transcendental functions a build calls, the same bits on every
platform (AZ-830): the character swap's sines, cosines and the rest reach
the bytes it writes, and each platform's libm (macOS's for CPython, musl's
under Pyodide, glibc's on Linux, the CRT's on Windows) rounds some results
differently, so ``math``'s and numpy's gave the site another image than the
app.

These are fdlibm's algorithms as musl carries them (its ``sin``, ``cos``,
``tan`` and ``__rem_pio2``'s small and medium arguments, ``acos``,
``atan``, ``atan2``, ``cbrt``; fdlibm 5.3's ``exp``; musl 1.1's ``log``,
FreeBSD's), in pure Python built only from IEEE double operations that are
correctly rounded on every platform: ``+``, ``-``, ``*``, ``/``,
``math.sqrt`` and the exact ones (comparisons, ``math.ldexp``,
``math.fabs``, bit patterns through ``struct``). Python never fuses a
multiply and an add, so each expression rounds as written here. Where
musl's code is fdlibm's, the result is musl's bit for bit (Pyodide's
``math``); ``exp`` and ``log`` (musl's are now ARM's table-driven ones) are
within an ulp of the true value (0.80 and 0.50 on a sweep), and
:func:`pow` (``exp(y * log(x))``) within about ``|y ln x| + 1`` ulps (51
on a sweep with ``|y ln x| <= 98``), which no build needs closer. An argument past
2**20 * pi/2 is reduced exactly with integers (musl's Payne-Hanek isn't
ported).

``sq`` and ``cube`` stand in for ``x ** 2`` and ``x ** 3``: CPython's
``float ** int`` calls the platform's ``pow`` (numpy's ``** 3`` too), whose
square isn't always ``x * x``. They take numpy arrays as they are.

    Copyright (C) 1993 by Sun Microsystems, Inc. All rights reserved.
    Developed at SunSoft, a Sun Microsystems, Inc. business.
    Permission to use, copy, modify, and distribute this software is freely
    granted, provided that this notice is preserved.
"""

from __future__ import annotations

import math
import struct
from fractions import Fraction

__all__ = ["acos", "atan", "atan2", "cbrt", "cos", "cube", "exp", "log", "pow", "sin", "sq", "tan"]

_D = struct.Struct("<d")
_Q = struct.Struct("<Q")


def _f(bits: int) -> float:
    """The double of a 64-bit pattern."""
    return _D.unpack(_Q.pack(bits))[0]


def _bits(x: float) -> int:
    return _Q.unpack(_D.pack(x))[0]


def _hw(high: int) -> float:
    """The least double whose high word is ``high`` (a threshold musl tests on the high word)."""
    return _f(high << 32)


def _low0(x: float) -> float:
    """``x`` with its low word cleared (fdlibm's SET_LOW_WORD(x, 0))."""
    return _f(_bits(x) & 0xFFFFFFFF00000000)


def sq(x):
    """``x * x``: ``x ** 2`` without the platform's ``pow``."""
    return x * x


def cube(x):
    """``x * x * x``: ``x ** 3`` without the platform's ``pow``."""
    return x * x * x


# --- argument reduction: x = n * pi/2 + (y0 + y1) ---------------------------------------------------------------

_TOINT = math.ldexp(1.5, 52)                   # 1.5 / DBL_EPSILON
_PIO4 = _f(0x3FE921FB54442D18)
_INVPIO2 = _f(0x3FE45F306DC9C883)
_PIO2_1 = _f(0x3FF921FB54400000)
_PIO2_1T = _f(0x3DD0B4611A626331)
_PIO2_2 = _f(0x3DD0B4611A600000)
_PIO2_2T = _f(0x3BA3198A2E037073)
_PIO2_3 = _f(0x3BA3198A2E000000)
_PIO2_3T = _f(0x397B839A252049C1)
_PIO4_HIGH = _hw(0x3FE921FC)    # |x| ~<= pi/4: ix <= 0x3fe921fb
_PI_BITS = 1280
_PI_INT: list[int] = []


def _pi_scaled() -> int:
    """floor(pi * 2**_PI_BITS), by Machin's formula in integers (once)."""
    if not _PI_INT:
        one = 1 << (_PI_BITS + 64)

        def atan_inv(n: int) -> int:
            total = term = one // n
            k, sign = 1, -1
            while term:
                term //= n * n
                k += 2
                total += sign * (term // k)
                sign = -sign
            return total
        _PI_INT.append((16 * atan_inv(5) - 4 * atan_inv(239)) >> 64)
    return _PI_INT[0]


def _rem_large(x: float) -> tuple[int, float, float]:
    """An argument past 2**20 * pi/2, reduced exactly: n, then the remainder as y0 + y1."""
    p, q = abs(x).as_integer_ratio()                  # |x| = p / q, q a power of two
    pi = _pi_scaled()                                 # pi/2 = pi / 2**(_PI_BITS + 1)
    num = (p << (_PI_BITS + 1)) // q                  # exact: |x| >= 2**20, so q is 1
    n = (2 * num + pi) // (2 * pi)
    rest = Fraction(num - n * pi, 1 << (_PI_BITS + 1))
    y0 = float(rest)
    y1 = float(rest - Fraction(y0))
    return (-n, -y0, -y1) if x < 0 else (n, y0, y1)


def _rem_pio2(x: float) -> tuple[int, float, float]:
    """musl's ``__rem_pio2`` for |x| > pi/4: ``(n, y0, y1)``."""
    ax = math.fabs(x)
    medium = False
    if ax < _hw(0x400F6A7B):                          # |x| ~<= 5pi/4
        if _hw(0x3FF921FB) <= ax < _hw(0x3FF921FC) or _hw(0x400921FB) <= ax < _hw(0x400921FC):
            medium = True                             # |x| ~= pi/2 or pi: cancellation
        elif ax < _hw(0x4002D97D):                    # |x| ~<= 3pi/4
            if x > 0:
                z = x - _PIO2_1
                y0 = z - _PIO2_1T
                return 1, y0, (z - y0) - _PIO2_1T
            z = x + _PIO2_1
            y0 = z + _PIO2_1T
            return -1, y0, (z - y0) + _PIO2_1T
        else:
            if x > 0:
                z = x - 2 * _PIO2_1
                y0 = z - 2 * _PIO2_1T
                return 2, y0, (z - y0) - 2 * _PIO2_1T
            z = x + 2 * _PIO2_1
            y0 = z + 2 * _PIO2_1T
            return -2, y0, (z - y0) + 2 * _PIO2_1T
    elif ax < _hw(0x401C463C):                        # |x| ~<= 9pi/4
        if ax < _hw(0x4015FDBD):                      # |x| ~<= 7pi/4
            if _hw(0x4012D97C) <= ax < _hw(0x4012D97D):
                medium = True                         # |x| ~= 3pi/2
            elif x > 0:
                z = x - 3 * _PIO2_1
                y0 = z - 3 * _PIO2_1T
                return 3, y0, (z - y0) - 3 * _PIO2_1T
            else:
                z = x + 3 * _PIO2_1
                y0 = z + 3 * _PIO2_1T
                return -3, y0, (z - y0) + 3 * _PIO2_1T
        elif _hw(0x401921FB) <= ax < _hw(0x401921FC):
            medium = True                             # |x| ~= 4pi/2
        elif x > 0:
            z = x - 4 * _PIO2_1
            y0 = z - 4 * _PIO2_1T
            return 4, y0, (z - y0) - 4 * _PIO2_1T
        else:
            z = x + 4 * _PIO2_1
            y0 = z + 4 * _PIO2_1T
            return -4, y0, (z - y0) + 4 * _PIO2_1T
    if not (medium or ax < _hw(0x413921FB)):          # |x| ~>= 2**20 * pi/2
        return _rem_large(x)
    fn = x * _INVPIO2 + _TOINT - _TOINT               # rint(x / (pi/2))
    n = int(fn)
    r = x - fn * _PIO2_1
    w = fn * _PIO2_1T                                 # 1st round, good to 85 bits
    if r - w < -_PIO4:
        n, fn = n - 1, fn - 1
        r, w = x - fn * _PIO2_1, fn * _PIO2_1T
    elif r - w > _PIO4:
        n, fn = n + 1, fn + 1
        r, w = x - fn * _PIO2_1, fn * _PIO2_1T
    y0 = r - w
    ex = (_bits(x) >> 52) & 0x7FF
    if ex - ((_bits(y0) >> 52) & 0x7FF) > 16:         # 2nd round, good to 118 bits
        t = r
        w = fn * _PIO2_2
        r = t - w
        w = fn * _PIO2_2T - ((t - r) - w)
        y0 = r - w
        if ex - ((_bits(y0) >> 52) & 0x7FF) > 49:     # 3rd round, good to 151 bits
            t = r
            w = fn * _PIO2_3
            r = t - w
            w = fn * _PIO2_3T - ((t - r) - w)
            y0 = r - w
    return n, y0, (r - y0) - w


# --- sin, cos, tan ------------------------------------------------------------------------------------------------

_S1, _S2, _S3 = _f(0xBFC5555555555549), _f(0x3F8111111110F8A6), _f(0xBF2A01A019C161D5)
_S4, _S5, _S6 = _f(0x3EC71DE357B1FE7D), _f(0xBE5AE5E68A2B9CEB), _f(0x3DE5D93A5ACFD57C)
_C1, _C2, _C3 = _f(0x3FA555555555554C), _f(0xBF56C16C16C15177), _f(0x3EFA01A019CB1590)
_C4, _C5, _C6 = _f(0xBE927E4F809C52AD), _f(0x3E21EE9EBDB4B1C4), _f(0xBDA8FAE9BE8838D4)


def _ksin(x: float, y: float, iy: int) -> float:
    z = x * x
    w = z * z
    r = _S2 + z * (_S3 + z * _S4) + z * w * (_S5 + z * _S6)
    v = z * x
    if not iy:
        return x + v * (_S1 + z * r)
    return x - ((z * (0.5 * y - v * r) - y) - v * _S1)


def _kcos(x: float, y: float) -> float:
    z = x * x
    w = z * z
    r = z * (_C1 + z * (_C2 + z * _C3)) + w * w * (_C4 + z * (_C5 + z * _C6))
    hz = 0.5 * z
    w = 1.0 - hz
    return w + (((1.0 - w) - hz) + (z * r - x * y))


def sin(x: float) -> float:
    x = float(x)
    ax = math.fabs(x)
    if ax < _PIO4_HIGH:
        return x if ax < _hw(0x3E500000) else _ksin(x, 0.0, 0)   # |x| < 2**-26: x
    if not math.isfinite(x):
        return x - x
    n, y0, y1 = _rem_pio2(x)
    n &= 3
    if n == 0:
        return _ksin(y0, y1, 1)
    if n == 1:
        return _kcos(y0, y1)
    if n == 2:
        return -_ksin(y0, y1, 1)
    return -_kcos(y0, y1)


def cos(x: float) -> float:
    x = float(x)
    ax = math.fabs(x)
    if ax < _PIO4_HIGH:
        return 1.0 if ax < _hw(0x3E46A09E) else _kcos(x, 0.0)   # |x| < 2**-27 * sqrt(2): 1
    if not math.isfinite(x):
        return x - x
    n, y0, y1 = _rem_pio2(x)
    n &= 3
    if n == 0:
        return _kcos(y0, y1)
    if n == 1:
        return -_ksin(y0, y1, 1)
    if n == 2:
        return -_kcos(y0, y1)
    return _ksin(y0, y1, 1)


_T = tuple(_f(b) for b in (
    0x3FD5555555555563, 0x3FC111111110FE7A, 0x3FABA1BA1BB341FE, 0x3F9664F48406D637, 0x3F8226E3E96E8493,
    0x3F6D6D22C9560328, 0x3F57DBC8FEE08315, 0x3F4344D8F2F26501, 0x3F3026F71A8D1068, 0x3F147E88A03792A6,
    0x3F12B80F32F0A7E9, 0xBEF375CBDB605373, 0x3EFB2A7074BF7AD4))
_PIO4LO = _f(0x3C81A62633145C07)


def _ktan(x: float, y: float, odd: int) -> float:
    big = math.fabs(x) >= _hw(0x3FE59428)             # |x| >= 0.6744
    sign = False
    if big:
        sign = x < 0 or (x == 0 and math.copysign(1.0, x) < 0)
        if sign:
            x, y = -x, -y
        x = (_PIO4 - x) + (_PIO4LO - y)
        y = 0.0
    z = x * x
    w = z * z
    T = _T
    r = T[1] + w * (T[3] + w * (T[5] + w * (T[7] + w * (T[9] + w * T[11]))))
    v = z * (T[2] + w * (T[4] + w * (T[6] + w * (T[8] + w * (T[10] + w * T[12])))))
    s = z * x
    r = y + z * (s * (r + v) + y) + s * T[0]
    w = x + r
    if big:
        s = float(1 - 2 * odd)
        v = s - 2.0 * (x + (r - w * w / (w + s)))
        return -v if sign else v
    if not odd:
        return w
    w0 = _low0(w)                                     # -1/(x+r), computed accurately
    v = r - (w0 - x)
    a = -1.0 / w
    a0 = _low0(a)
    return a0 + a * (1.0 + a0 * w0 + a0 * v)


def tan(x: float) -> float:
    x = float(x)
    ax = math.fabs(x)
    if ax < _PIO4_HIGH:
        return x if ax < _hw(0x3E400000) else _ktan(x, 0.0, 0)   # |x| < 2**-27: x
    if not math.isfinite(x):
        return x - x
    n, y0, y1 = _rem_pio2(x)
    return _ktan(y0, y1, n & 1)


# --- acos, atan, atan2 --------------------------------------------------------------------------------------------

_PIO2_HI, _PIO2_LO = _f(0x3FF921FB54442D18), _f(0x3C91A62633145C07)
_PS = tuple(_f(b) for b in (0x3FC5555555555555, 0xBFD4D61203EB6F7D, 0x3FC9C1550E884455, 0xBFA48228B5688F3B,
                            0x3F49EFE07501B288, 0x3F023DE10DFDF709))
_QS = tuple(_f(b) for b in (0xC0033A271C8A2D4B, 0x40002AE59C598AC8, 0xBFE6066C1B8D0159, 0x3FB3B8C5B12E9282))


def _r(z: float) -> float:
    p = z * (_PS[0] + z * (_PS[1] + z * (_PS[2] + z * (_PS[3] + z * (_PS[4] + z * _PS[5])))))
    q = 1.0 + z * (_QS[0] + z * (_QS[1] + z * (_QS[2] + z * _QS[3])))
    return p / q


def acos(x: float) -> float:
    x = float(x)
    ax = math.fabs(x)
    if math.isnan(x):
        return x
    if not ax < 1.0:
        if x == 1.0:
            return 0.0
        if x == -1.0:
            return 2 * _PIO2_HI
        raise ValueError("math domain error")
    if ax < 0.5:
        if ax < _hw(0x3C600001):                      # |x| < 2**-57
            return _PIO2_HI
        return _PIO2_HI - (x - (_PIO2_LO - x * _r(x * x)))
    if x < 0:
        z = (1.0 + x) * 0.5
        s = math.sqrt(z)
        w = _r(z) * s - _PIO2_LO
        return 2 * (_PIO2_HI - (s + w))
    z = (1.0 - x) * 0.5
    s = math.sqrt(z)
    df = _low0(s)
    c = (z - df * df) / (s + df)
    w = _r(z) * s + c
    return 2 * (df + w)


_ATANHI = tuple(_f(b) for b in (0x3FDDAC670561BB4F, 0x3FE921FB54442D18, 0x3FEF730BD281F69B, 0x3FF921FB54442D18))
_ATANLO = tuple(_f(b) for b in (0x3C7A2B7F222F65E2, 0x3C81A62633145C07, 0x3C7007887AF0CBBD, 0x3C91A62633145C07))
_AT = tuple(_f(b) for b in (
    0x3FD555555555550D, 0xBFC999999998EBC4, 0x3FC24924920083FF, 0xBFBC71C6FE231671, 0x3FB745CDC54C206E,
    0xBFB3B0F2AF749A6D, 0x3FB10D66A0D03D51, 0xBFADDE2D52DEFD9A, 0x3FA97B4B24760DEB, 0xBFA2B4442C6A6C2F,
    0x3F90AD3AE322DA11))


def atan(x: float) -> float:
    x = float(x)
    if math.isnan(x):
        return x
    sign = math.copysign(1.0, x) < 0
    ax = math.fabs(x)
    if ax >= _hw(0x44100000):                         # |x| >= 2**66
        return -_ATANHI[3] if sign else _ATANHI[3]
    if ax < _hw(0x3FDC0000):                          # |x| < 0.4375
        if ax < _hw(0x3E400000):                      # |x| < 2**-27
            return x
        k = -1
    else:
        x = ax
        if ax < _hw(0x3FF30000):                      # |x| < 1.1875
            if ax < _hw(0x3FE60000):                  # 7/16 <= |x| < 11/16
                k, x = 0, (2.0 * x - 1.0) / (2.0 + x)
            else:                                     # 11/16 <= |x| < 19/16
                k, x = 1, (x - 1.0) / (x + 1.0)
        elif ax < _hw(0x40038000):                    # |x| < 2.4375
            k, x = 2, (x - 1.5) / (1.0 + 1.5 * x)
        else:                                         # 2.4375 <= |x| < 2**66
            k, x = 3, -1.0 / x
    z = x * x
    w = z * z
    A = _AT
    s1 = z * (A[0] + w * (A[2] + w * (A[4] + w * (A[6] + w * (A[8] + w * A[10])))))
    s2 = w * (A[1] + w * (A[3] + w * (A[5] + w * (A[7] + w * A[9]))))
    if k < 0:
        return x - x * (s1 + s2)
    z = _ATANHI[k] - (x * (s1 + s2) - _ATANLO[k] - x)
    return -z if sign else z


_PI, _PI_LO = _f(0x400921FB54442D18), _f(0x3CA1A62633145C07)


def atan2(y: float, x: float) -> float:
    y, x = float(y), float(x)
    if math.isnan(x) or math.isnan(y):
        return x + y
    if x == 1.0:
        return atan(y)
    m = (math.copysign(1.0, y) < 0) | (2 * (math.copysign(1.0, x) < 0))   # 2*sign(x) + sign(y)
    if y == 0:
        return (y, y, _PI, -_PI)[m]
    if x == 0:
        return -_PI / 2 if m & 1 else _PI / 2
    if math.isinf(x):
        if math.isinf(y):
            return (_PI / 4, -_PI / 4, 3 * _PI / 4, -3 * _PI / 4)[m]
        return (0.0, -0.0, _PI, -_PI)[m]
    ix, iy = (_bits(x) >> 32) & 0x7FFFFFFF, (_bits(y) >> 32) & 0x7FFFFFFF
    if ix + (64 << 20) < iy or math.isinf(y):         # |y/x| > 2**64
        return -_PI / 2 if m & 1 else _PI / 2
    z = 0.0 if (m & 2) and iy + (64 << 20) < ix else atan(math.fabs(y / x))   # |y/x| < 2**-64, x < 0: 0
    if m == 0:
        return z
    if m == 1:
        return -z
    if m == 2:
        return _PI - (z - _PI_LO)
    return (z - _PI_LO) - _PI


# --- cbrt ---------------------------------------------------------------------------------------------------------

_B1, _B2 = 715094163, 696219795
_P = tuple(_f(b) for b in (0x3FFE03E60F61E692, 0xBFFE28E092F02420, 0x3FF9F1604A49D6C2, 0xBFE844CBBEE751D9,
                           0x3FC2B000D4E4EDD7))


def cbrt(x: float) -> float:
    x = float(x)
    bits = _bits(x)
    hx = (bits >> 32) & 0x7FFFFFFF
    if hx >= 0x7FF00000:
        return x + x
    if hx < 0x00100000:                               # zero or subnormal
        hx = (_bits(math.ldexp(x, 54)) >> 32) & 0x7FFFFFFF
        if hx == 0:
            return x
        hx = hx // 3 + _B2
    else:
        hx = hx // 3 + _B1
    t = _f((bits & (1 << 63)) | (hx << 32))
    r = (t * t) * (t / x)
    t = t * ((_P[0] + r * (_P[1] + r * _P[2])) + ((r * r) * r) * (_P[3] + r * _P[4]))
    t = _f((_bits(t) + 0x80000000) & 0xFFFFFFFFC0000000)
    s = t * t
    r = x / s
    w = t + t
    r = (r - t) / (w + r)
    return t + t * r


# --- exp, log, pow ------------------------------------------------------------------------------------------------

_LN2HI, _LN2LO, _INVLN2 = _f(0x3FE62E42FEE00000), _f(0x3DEA39EF35793C76), _f(0x3FF71547652B82FE)
_E = tuple(_f(b) for b in (0x3FC555555555553E, 0xBF66C16C16BEBD93, 0x3F11566AAF25DE2C, 0xBEBBBD41C5D26BF1,
                           0x3E66376972BEA4D0))


def exp(x: float) -> float:
    x = float(x)
    if math.isnan(x) or x == math.inf:
        return x
    if x > _f(0x40862E42FEFA39EF):                    # 709.78...: overflow
        raise OverflowError("math range error")
    if x < -745.13321910194110842:
        return 0.0
    ax = math.fabs(x)
    if ax >= _hw(0x3FD62E43):                         # |x| > 0.5 ln2
        if ax >= _hw(0x3FF0A2B2):                     # |x| >= 1.5 ln2
            k = int(_INVLN2 * x + (-0.5 if x < 0 else 0.5))
        else:
            k = -1 if x < 0 else 1
        hi = x - k * _LN2HI                           # exact here
        lo = k * _LN2LO
        x = hi - lo
    elif ax >= _hw(0x3E300001):                       # |x| > 2**-28
        k, hi, lo = 0, x, 0.0
    else:
        return 1 + x
    xx = x * x
    c = x - xx * (_E[0] + xx * (_E[1] + xx * (_E[2] + xx * (_E[3] + xx * _E[4]))))
    y = 1 + (x * c / (2 - c) - lo + hi)
    return y if k == 0 else math.ldexp(y, k)


_LG = tuple(_f(b) for b in (0x3FE5555555555593, 0x3FD999999997FA04, 0x3FD2492494229359, 0x3FCC71C51D8E78AF,
                            0x3FC7466496CB03DE, 0x3FC39A09D078C69F, 0x3FC2F112DF3E5244))


def log(x: float) -> float:
    x = float(x)
    if math.isnan(x) or x == math.inf:
        return x
    if x <= 0:
        if x == 0:
            return -math.inf
        raise ValueError("math domain error")
    if x == 1.0:
        return 0.0
    bits, k = _bits(x), 0
    if bits >> 52 == 0:                               # subnormal: scale up
        k, bits = -54, _bits(math.ldexp(x, 54))
    hx = (bits >> 32) + 0x3FF00000 - 0x3FE6A09E       # reduce x into [sqrt(2)/2, sqrt(2)]
    k += (hx >> 20) - 0x3FF
    hx = (hx & 0x000FFFFF) + 0x3FE6A09E
    x = _f((hx << 32) | (bits & 0xFFFFFFFF))
    f = x - 1.0
    hfsq = 0.5 * f * f
    s = f / (2.0 + f)
    z = s * s
    w = z * z
    t1 = w * (_LG[1] + w * (_LG[3] + w * _LG[5]))
    t2 = z * (_LG[0] + w * (_LG[2] + w * (_LG[4] + w * _LG[6])))
    r = t2 + t1
    dk = float(k)
    return s * (hfsq + r) + dk * _LN2LO - hfsq + f + dk * _LN2HI


def pow(x: float, y: float) -> float:
    """``x ** y``: ``y`` 0, 1, 2 and 3 by products (``sq``, ``cube``), else
    for ``x >= 0`` ``exp(y * log(x))``, 1 at ``x`` 1 and 0 at ``x`` 0 for
    ``y`` above 0."""
    x, y = float(x), float(y)
    if y == 0 or x == 1.0:
        return 1.0
    if y in (1.0, 2.0, 3.0):
        return x if y == 1.0 else x * x if y == 2.0 else x * x * x
    if x < 0:
        raise ValueError("pow: a negative base")
    if x == 0:
        return 0.0 if y > 0 else math.inf
    return exp(y * log(x))
