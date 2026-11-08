/* The paint's and the textures' kernels, compiled (D1009): tools/characters/textures.py's _dxt (a level's BC1 or BC2
 * blocks: integers only), paint.py's _raster (each texel's triangle and barycentric weights) and fdlibm.atan2 over many
 * points (paint._hsv's hue), every operation its Python twin's in the twin's order on doubles, with no contraction, so
 * the two agree bit for bit (tests/test_native.py). No libm, no libc, no allocation. Built by nativekit (C99, zig cc). */
#include <stdint.h>

#if defined(_WIN32)
#define API __declspec(dllexport)
#else
#define API __attribute__((visibility("default")))
#endif

typedef int64_t i64;

static double fab(double x) { return __builtin_fabs(x); }

static uint64_t bits_of(double x) {
    union { double d; uint64_t u; } v = { x };
    return v.u;
}

static double of_bits(uint64_t u) {
    union { uint64_t u; double d; } v = { u };
    return v.d;
}

static double hw(uint64_t high) { return of_bits(high << 32); }   /* fdlibm._hw */

/* ---- textures._dxt ------------------------------------------------------------------------------------------------ */

static i64 sum3(const unsigned char *p) { return (i64)p[0] + p[1] + p[2]; }

static i64 dist(const unsigned char *p, const unsigned char *q) {   /* sum(fdlibm.sq(p[c] - q[c]) for c in range(3)) */
    i64 s = 0;
    for (int c = 0; c < 3; c++) s += ((i64)p[c] - q[c]) * ((i64)p[c] - q[c]);
    return s;
}

static i64 rgb565(const unsigned char *p) {
    return (((i64)p[0] * 31 + 127) / 255 << 11) | (((i64)p[1] * 63 + 127) / 255 << 5) | (((i64)p[2] * 31 + 127) / 255);
}

static void rgb888(i64 v, i64 *c) {
    c[0] = ((v >> 11) & 31) * 255 / 31;
    c[1] = ((v >> 5) & 63) * 255 / 63;
    c[2] = (v & 31) * 255 / 31;
}

static void put(unsigned char *out, i64 *at, uint64_t v, int n) {   /* n bytes, little-endian */
    for (int i = 0; i < n; i++) out[(*at)++] = (unsigned char)(v >> (8 * i));
}

/* A level's (h x w RGBA8, rows top down) blocks as BC1 (dxt1) or BC2 into out, rows of blocks top to bottom, edge
 * texels replicated: textures._dxt, each min and max the first it meets. Answers the bytes written. */
API i64 az_dxt(const unsigned char *px, i64 h, i64 w, i64 dxt1, unsigned char *out) {
    static const unsigned char none[4] = {0, 0, 0, 0};
    i64 at = 0;
    for (i64 by = 0; by < h; by += 4)
        for (i64 bx = 0; bx < w; bx += 4) {
            const unsigned char *block[16];
            int op[16], no = 0;
            for (int y = 0; y < 4; y++)
                for (int x = 0; x < 4; x++) {
                    i64 yy = by + y < h - 1 ? by + y : h - 1, xx = bx + x < w - 1 ? bx + x : w - 1;
                    block[4 * y + x] = px + 4 * (yy * w + xx);
                }
            for (int i = 0; i < 16; i++)
                if (!dxt1 || block[i][3] >= 128) op[no++] = i;
            const unsigned char *high = none, *low = none;
            if (no) {   /* the block's own colours along its longest colour axis */
                const unsigned char *seed = block[op[0]];
                for (int i = 1; i < no; i++)
                    if (sum3(block[op[i]]) < sum3(seed)) seed = block[op[i]];
                high = block[op[0]];
                for (int i = 1; i < no; i++)
                    if (dist(block[op[i]], seed) > dist(high, seed)) high = block[op[i]];
                low = block[op[0]];
                for (int i = 1; i < no; i++)
                    if (dist(block[op[i]], high) > dist(low, high)) low = block[op[i]];
            }
            i64 a = rgb565(high), b = rgb565(low);
            int transparent = dxt1 && no != 16;
            if (transparent) {
                i64 lo = a < b ? a : b, hi = a < b ? b : a;
                a = lo, b = hi;
            } else {
                i64 hi = a > b ? a : b, lo = a > b ? b : a;
                a = hi, b = lo;
                if (a == b) {
                    if (a < 0xFFFF)
                        a += 1;
                    else
                        b -= 1;
                }
            }
            i64 colors[4][3];
            rgb888(a, colors[0]);
            rgb888(b, colors[1]);
            for (int c = 0; c < 3; c++) {
                if (transparent) {
                    colors[2][c] = (colors[0][c] + colors[1][c]) / 2;
                    colors[3][c] = 0;
                } else {
                    colors[2][c] = (2 * colors[0][c] + colors[1][c]) / 3;
                    colors[3][c] = (colors[0][c] + 2 * colors[1][c]) / 3;
                }
            }
            uint64_t bits = 0, alpha = 0;
            for (int i = 0; i < 16; i++) {
                const unsigned char *p = block[i];
                i64 choice = 0;
                if (transparent && p[3] < 128) {
                    choice = 3;
                } else {
                    i64 best = -1;
                    for (int c = 0; c < (transparent ? 3 : 4); c++) {
                        i64 s = 0;
                        for (int k = 0; k < 3; k++) s += (p[k] - colors[c][k]) * (p[k] - colors[c][k]);
                        if (best < 0 || s < best) best = s, choice = c;
                    }
                }
                bits |= (uint64_t)choice << (2 * i);
                alpha |= (uint64_t)(((i64)p[3] * 15 + 127) / 255) << (4 * i);
            }
            if (!dxt1) put(out, &at, alpha, 8);
            put(out, &at, (uint64_t)a, 2);
            put(out, &at, (uint64_t)b, 2);
            put(out, &at, bits, 4);
        }
    return at;
}

/* ---- fdlibm.atan2 ------------------------------------------------------------------------------------------------- */

typedef union { uint64_t u; double d; } bits64;   /* each constant its fdlibm.py bit pattern */
static const bits64 ATANHI[4] = {{0x3FDDAC670561BB4F}, {0x3FE921FB54442D18}, {0x3FEF730BD281F69B}, {0x3FF921FB54442D18}};
static const bits64 ATANLO[4] = {{0x3C7A2B7F222F65E2}, {0x3C81A62633145C07}, {0x3C7007887AF0CBBD}, {0x3C91A62633145C07}};
static const bits64 AT[11] = {{0x3FD555555555550D}, {0xBFC999999998EBC4}, {0x3FC24924920083FF}, {0xBFBC71C6FE231671},
                              {0x3FB745CDC54C206E}, {0xBFB3B0F2AF749A6D}, {0x3FB10D66A0D03D51}, {0xBFADDE2D52DEFD9A},
                              {0x3FA97B4B24760DEB}, {0xBFA2B4442C6A6C2F}, {0x3F90AD3AE322DA11}};
static const bits64 PI_BITS = {0x400921FB54442D18}, PI_LO_BITS = {0x3CA1A62633145C07};
#define PI_ (PI_BITS.d)
#define PI_LO (PI_LO_BITS.d)

static double atan_(double x) {   /* fdlibm.atan */
    if (x != x) return x;
    int sign = (int)(bits_of(x) >> 63);
    double ax = fab(x);
    int k;
    if (ax >= hw(0x44100000)) return sign ? -ATANHI[3].d : ATANHI[3].d;
    if (ax < hw(0x3FDC0000)) {
        if (ax < hw(0x3E400000)) return x;
        k = -1;
    } else {
        x = ax;
        if (ax < hw(0x3FF30000)) {
            if (ax < hw(0x3FE60000))
                k = 0, x = (2.0 * x - 1.0) / (2.0 + x);
            else
                k = 1, x = (x - 1.0) / (x + 1.0);
        } else if (ax < hw(0x40038000)) {
            k = 2, x = (x - 1.5) / (1.0 + 1.5 * x);
        } else {
            k = 3, x = -1.0 / x;
        }
    }
    double z = x * x, w = z * z;
    double s1 = z * (AT[0].d + w * (AT[2].d + w * (AT[4].d + w * (AT[6].d + w * (AT[8].d + w * AT[10].d)))));
    double s2 = w * (AT[1].d + w * (AT[3].d + w * (AT[5].d + w * (AT[7].d + w * AT[9].d))));
    if (k < 0) return x - x * (s1 + s2);
    z = ATANHI[k].d - (x * (s1 + s2) - ATANLO[k].d - x);
    return sign ? -z : z;
}

static int inf_(double x) { return fab(x) == __builtin_inf(); }

static double atan2_(double y, double x) {   /* fdlibm.atan2 */
    if (x != x || y != y) return x + y;
    if (x == 1.0) return atan_(y);
    int m = (int)(bits_of(y) >> 63) | (int)(2 * (bits_of(x) >> 63));
    if (y == 0) return m == 0 || m == 1 ? y : m == 2 ? PI_ : -PI_;
    if (x == 0) return m & 1 ? -PI_ / 2 : PI_ / 2;
    if (inf_(x)) {
        if (inf_(y)) return m == 0 ? PI_ / 4 : m == 1 ? -PI_ / 4 : m == 2 ? 3 * PI_ / 4 : -3 * PI_ / 4;
        return m == 0 ? 0.0 : m == 1 ? -0.0 : m == 2 ? PI_ : -PI_;
    }
    i64 ix = (i64)((bits_of(x) >> 32) & 0x7FFFFFFF), iy = (i64)((bits_of(y) >> 32) & 0x7FFFFFFF);
    if (ix + (64 << 20) < iy || inf_(y)) return m & 1 ? -PI_ / 2 : PI_ / 2;
    double z = (m & 2) && iy + (64 << 20) < ix ? 0.0 : atan_(fab(y / x));
    if (m == 0) return z;
    if (m == 1) return -z;
    if (m == 2) return PI_ - (z - PI_LO);
    return (z - PI_LO) - PI_;
}

/* fdlibm.atan2(y[i], x[i]) into out[i] for each of n points. */
API i64 az_atan2(const double *y, const double *x, i64 n, double *out) {
    for (i64 i = 0; i < n; i++) out[i] = atan2_(y[i], x[i]);
    return 0;
}

/* ---- paint._raster ------------------------------------------------------------------------------------------------ */

static double floor_(double x) {   /* math.floor's and numpy's floor of |x| < 2**52, a zero's sign kept */
    if (x == 0.0) return x;
    double i = (double)(i64)x;
    return i > x ? i - 1.0 : i;
}

static double min3(double a, double b, double c) {   /* Python's min(a, b, c): the first least */
    double m = a;
    if (b < m) m = b;
    if (c < m) m = c;
    return m;
}

static double max3(double a, double b, double c) {
    double m = a;
    if (b > m) m = b;
    if (c > m) m = c;
    return m;
}

/* paint._raster of m triangles whose corners' UVs times size are P (m x 3 x 2: uv[tris] * size): each texel's covering
 * triangle into tid (size x size, -1 as the caller filled it) and its barycentric weights into bary (size x size x 3,
 * zeros), the triangles drawn in order, a tiled one where it lands with the texture wrapped. -2 before a write, where a
 * corner isn't finite, lies 2**40 or more from 0 or is -0.0: the twin's. */
API i64 az_raster(const double *P, i64 m, i64 size, i64 *tid, double *bary) {
    for (i64 i = 0; i < 6 * m; i++)   /* a -0.0 too: numpy's least of a corner's and another's 0.0 may be either */
        if (!(fab(P[i]) < 0x1p40) || bits_of(P[i]) == 0x8000000000000000ull) return -2;
    double S = (double)size;
    for (i64 t = 0; t < m; t++) {
        const double *p = P + 6 * t;
        double tri[3][2];
        for (int d = 0; d < 2; d++) {   /* its lowest corner's tile at 0 */
            double lo = p[d];   /* numpy's min over the corners: finite, so the least */
            if (p[2 + d] < lo) lo = p[2 + d];
            if (p[4 + d] < lo) lo = p[4 + d];
            double f = floor_(lo / S) * S;
            for (int k = 0; k < 3; k++) tri[k][d] = p[2 * k + d] - f;
        }
        i64 reach[2];
        for (int d = 0; d < 2; d++) reach[d] = (i64)floor_(max3(tri[0][d], tri[1][d], tri[2][d]) / S);
        for (i64 du = 0; du <= reach[0]; du++)
            for (i64 dv = 0; dv <= reach[1]; dv++) {
                double a0 = tri[0][0] - (double)(du * size), a1 = tri[0][1] - (double)(dv * size);
                double b0 = tri[1][0] - (double)(du * size), b1 = tri[1][1] - (double)(dv * size);
                double c0 = tri[2][0] - (double)(du * size), c1 = tri[2][1] - (double)(dv * size);
                double den = (b1 - c1) * (a0 - c0) + (c0 - b0) * (a1 - c1);
                if (fab(den) < 1e-12) continue;
                i64 x0 = (i64)floor_(min3(a0, b0, c0)), x1 = -(i64)floor_(-max3(a0, b0, c0));
                i64 y0 = (i64)floor_(min3(a1, b1, c1)), y1 = -(i64)floor_(-max3(a1, b1, c1));
                x0 = x0 > 0 ? x0 : 0, y0 = y0 > 0 ? y0 : 0;
                x1 = x1 < size - 1 ? x1 : size - 1, y1 = y1 < size - 1 ? y1 : size - 1;
                for (i64 j = y0; j <= y1; j++)
                    for (i64 i = x0; i <= x1; i++) {
                        double gx = (double)i + 0.5, gy = (double)j + 0.5;
                        double l1 = ((b1 - c1) * (gx - c0) + (c0 - b0) * (gy - c1)) / den;
                        double l2 = ((c1 - a1) * (gx - c0) + (a0 - c0) * (gy - c1)) / den;
                        double l3 = 1.0 - l1 - l2;
                        if (l1 >= -1e-6 && l2 >= -1e-6 && l3 >= -1e-6) {
                            tid[j * size + i] = t;
                            bary[3 * (j * size + i)] = l1;
                            bary[3 * (j * size + i) + 1] = l2;
                            bary[3 * (j * size + i) + 2] = l3;
                        }
                    }
            }
    }
    return 0;
}
