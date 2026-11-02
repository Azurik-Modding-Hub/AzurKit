/* The dress's clip and skeleton kernels, compiled (D1009): tools/characters/retarget.py's engine model (pose and
 * origins over many clip times: evaluate's cubic Hermite, the Hamilton product, qnorm), its bake's rows (bake_clip's
 * linear path and _sampled's), characters._box's damage boxes and the byte runs of tools/characters/__init__.py's
 * _runs. Each is its Python twin's operations in the twin's order on doubles, with no contraction, so the two agree
 * bit for bit (tests/test_native.py); a sum() of floats is Python's (CPython's Neumaier sum since 3.12, from its int
 * start 0). No libm, no libc, no allocation: the caller passes every buffer. Built by nativekit (C99, zig cc). */
#include <stdint.h>

#if defined(_WIN32)
#define API __declspec(dllexport)
#else
#define API __attribute__((visibility("default")))
#endif

typedef int64_t i64;

#define FLT_MAX_ 3.4028234663852886e38   /* retarget.FLT_MAX */
#define BONE 15                           /* a bone's doubles: jo 0-3, rest q 4-7, ra 8-11, rest t 12-14 */
#define LINK 12                           /* a chain bone's: jo, rest q, ra */

static double fab(double x) { return __builtin_fabs(x); }
static int finite(double x) { return __builtin_isfinite(x); }

/* sum() of n >= 1 floats: 0 + x[0], then Neumaier's compensation, added at the end only if nonzero and finite. */
static double psum(const double *x, int n) {
    double f = 0.0 + x[0], c = 0.0;
    for (int i = 1; i < n; i++) {
        double t = f + x[i];
        if (fab(f) >= fab(x[i]))
            c += (f - t) + x[i];
        else
            c += (x[i] - t) + f;
        f = t;
    }
    if (c != 0.0 && finite(c)) f += c;
    return f;
}

/* retarget.qmul (Hamilton, (x, y, z, w)); o may be p or q. */
static void qmul(const double *p, const double *q, double *o) {
    double x1 = p[0], y1 = p[1], z1 = p[2], w1 = p[3], x2 = q[0], y2 = q[1], z2 = q[2], w2 = q[3];
    o[0] = w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2;
    o[1] = w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2;
    o[2] = w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2;
    o[3] = w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2;
}

/* retarget.qnorm: q over sqrt(sum(c * c)) or 1.0. */
static void qnorm(const double *q, double *o) {
    double s[4] = {q[0] * q[0], q[1] * q[1], q[2] * q[2], q[3] * q[3]};
    double n = __builtin_elementwise_sqrt(psum(s, 4));   /* never errno, so never libm's sqrt */
    if (n == 0.0) n = 1.0;
    for (int i = 0; i < 4; i++) o[i] = q[i] / n;
}

/* retarget._segment over n keys of 4 doubles (time, value, in, out). */
static i64 segment(const double *k, i64 n, double t, int left) {
    i64 lo = 0, hi = n - 1;
    while (hi - lo > 1) {
        i64 mid = (lo + hi) / 2;
        if (k[4 * mid] < t || (!left && k[4 * mid] == t))
            lo = mid;
        else
            hi = mid;
    }
    return lo;
}

/* retarget._cubic from the key at k: the value, and the slope into *slope when asked. */
static double cubic(const double *k, double t, double *slope) {
    double t0 = k[0], v0 = k[1], o0 = k[3], t1 = k[4], v1 = k[5], i1 = k[6];
    double dt = t1 - t0;
    if (o0 > FLT_MAX_ || dt <= 0) {
        if (slope) *slope = 0.0;
        return v0;
    }
    double s = (t - t0) / dt, m0 = dt * o0, m1 = dt * i1;
    if (!finite(m1)) m1 = 0.0;
    double a = 2 * (v0 - v1) + m1 + m0, b = 3 * (v1 - v0) - 2 * m0 - m1;
    if (slope) *slope = (3 * a * s * s + 2 * b * s + m0) / dt;
    return ((a * s + b) * s + m0) * s + v0;
}

/* retarget.evaluate (n >= 1; t not NaN where n is 1, which the caller holds). */
static double evaluate(const double *k, i64 n, double t) {
    if (t <= k[0]) return k[1];
    if (t >= k[4 * (n - 1)]) return k[4 * (n - 1) + 1];
    return cubic(k + 4 * segment(k, n, t, 0), t, 0);
}

/* retarget._slopes: the slope just before and just after t. */
static void slopes(const double *k, i64 n, double t, double *left, double *right) {
    double last = k[4 * (n - 1)];
    *left = *right = 0.0;
    if (k[0] < t && t <= last) cubic(k + 4 * segment(k, n, t, 1), t, left);
    if (k[0] <= t && t < last) cubic(k + 4 * segment(k, n, t, 0), t, right);
}

/* A component: its keys (index holds a key offset and count; a count of 0 is unkeyed, the rest value). */
static double comp(const i64 *index, const double *keys, double rest, double t) {
    return index[1] ? evaluate(keys + 4 * index[0], index[1], t) : rest;
}

/* retarget.pose and origins at each of nt times: world (nt x nb x 4) always, origin (nt x nb x 3) unless null.
 * parent[k] < k (a root's is negative); index holds ni bones x 7 components (T 0-2, q 3-6) x (offset, count). */
API i64 az_origins(const i64 *parent, const double *bone, i64 nb, const i64 *index, i64 ni, const double *keys,
                   const double *times, i64 nt, double *world, double *origin) {
    for (i64 i = 0; i < nt; i++) {
        double t = times[i], *w = world + 4 * nb * i;
        for (i64 k = 0; k < nb; k++) {
            const double *b = bone + BONE * k;
            double q[4], local[4];
            for (int c = 0; c < 4; c++)
                q[c] = k < ni ? comp(index + 2 * (7 * k + 3 + c), keys, b[4 + c], t) : b[4 + c];
            qnorm(q, q);
            qmul(b, q, local);
            qmul(local, b + 8, local);
            if (parent[k] < 0) {
                for (int c = 0; c < 4; c++) w[4 * k + c] = local[c];
            } else {
                qmul(w + 4 * parent[k], local, w + 4 * k);
            }
        }
        if (!origin) continue;
        double *o = origin + 3 * nb * i;
        for (i64 k = 0; k < nb; k++) {
            const double *b = bone + BONE * k;
            double v[4], turned[4];
            for (int c = 0; c < 3; c++)
                v[c] = k < ni ? comp(index + 2 * (7 * k + c), keys, b[12 + c], t) : b[12 + c];
            if (parent[k] < 0) {
                for (int c = 0; c < 3; c++) o[3 * k + c] = v[c];
                continue;
            }
            const double *p = w + 4 * parent[k];
            double inv[4] = {-p[0], -p[1], -p[2], p[3]};
            v[3] = 0.0;
            qmul(p, v, turned);
            qmul(turned, inv, turned);
            for (int c = 0; c < 3; c++) o[3 * k + c] = o[3 * parent[k] + c] + turned[c];
        }
    }
    return 0;
}

/* bake_clip's linear path: at each time, the 4x4 m (row-major) times the components' values, left slopes and right
 * slopes (index: 4 x (offset, count), rest: the 4 rest values for an unkeyed one); rows nt x 12. */
API i64 az_linear(const i64 *index, const double *keys, const double *rest, const double *m, const double *times,
                  i64 nt, double *rows) {
    for (i64 i = 0; i < nt; i++) {
        double t = times[i], x[3][4], p[4];
        for (int c = 0; c < 4; c++) {
            const i64 *ix = index + 2 * c;
            if (ix[1]) {
                x[0][c] = evaluate(keys + 4 * ix[0], ix[1], t);
                slopes(keys + 4 * ix[0], ix[1], t, &x[1][c], &x[2][c]);
            } else {
                x[0][c] = rest[c];
                x[1][c] = x[2][c] = 0.0;
            }
        }
        for (int v = 0; v < 3; v++)
            for (int r = 0; r < 4; r++) {
                for (int c = 0; c < 4; c++) p[c] = m[4 * r + c] * x[v][c];
                rows[12 * i + 4 * v + r] = psum(p, 4);
            }
    }
    return 0;
}

/* _sampled's at(t, ref): a x (the chain's locals' product) x c, normalised, negated where its dot with ref is < 0. */
static void chain_at(const double *link, const i64 *index, const double *keys, i64 nc, const double *a,
                     const double *c, double t, const double *ref, double *q) {
    double prod[4] = {0.0, 0.0, 0.0, 1.0};
    for (i64 f = 0; f < nc; f++) {
        const double *b = link + LINK * f;
        double v[4], local[4];
        for (int i = 0; i < 4; i++) v[i] = comp(index + 2 * (4 * f + i), keys, b[4 + i], t);
        qnorm(v, v);
        qmul(b, v, local);
        qmul(local, b + 8, local);
        qmul(prod, local, prod);
    }
    qmul(a, prod, q);
    qmul(q, c, q);
    qnorm(q, q);
    if (ref) {
        double d[4] = {q[0] * ref[0], q[1] * ref[1], q[2] * ref[2], q[3] * ref[3]};
        if (psum(d, 4) < 0)
            for (int i = 0; i < 4; i++) q[i] = -q[i];
    }
}

/* retarget._sampled's rows: at each time its rotation and one-sided slopes over h (length bounds the window);
 * index holds nc links x 4 components x (offset, count); rows nt x 12 (q, in, out). */
API i64 az_chain(const double *link, const i64 *index, const double *keys, i64 nc, const double *a, const double *c,
                 const double *times, i64 nt, double length, double h, double *rows) {
    const double *prev = 0;
    for (i64 i = 0; i < nt; i++) {
        double t = times[i], *q = rows + 12 * i, ql[4], qr[4];
        chain_at(link, index, keys, nc, a, c, t, prev, q);
        double lo = t - h > 0.0 ? t - h : 0.0, hi = t + h < length ? t + h : length;
        chain_at(link, index, keys, nc, a, c, lo, q, ql);
        chain_at(link, index, keys, nc, a, c, hi, q, qr);
        for (int r = 0; r < 4; r++) {
            q[4 + r] = t > lo ? (q[r] - ql[r]) / (t - lo) : 0.0;
            q[8 + r] = hi > t ? (qr[r] - q[r]) / (hi - t) : 0.0;
        }
        prev = q;
    }
    return 0;
}

/* _player_crossfade._curve at t (numpy's): key times finite and in order (the caller's), the segment the last key at
 * or before t, kept inside the keys. */
static double curve(const double *k, i64 n, double t) {
    if (n == 1) return k[1];
    i64 lo = 0, hi = n;   /* searchsorted(side="right"): the keys at or before t */
    while (lo < hi) {
        i64 mid = lo + ((hi - lo) >> 1);
        if (t < k[4 * mid])
            hi = mid;
        else
            lo = mid + 1;
    }
    i64 seg = lo - 1 < 0 ? 0 : lo - 1 > n - 2 ? n - 2 : lo - 1;
    const double *a0 = k + 4 * seg;
    double t0 = a0[0], v0 = a0[1], o0 = a0[3], t1 = a0[4], v1 = a0[5], i1 = a0[6], value = v0;
    double dt = t1 - t0;
    if (!(o0 > FLT_MAX_ || dt <= 0)) {
        double s = (t - t0) / dt, m0 = dt * o0, m1 = dt * i1;
        if (!finite(m1)) m1 = 0.0;
        double a = 2 * (v0 - v1) + m1 + m0, b = 3 * (v1 - v0) - 2 * m0 - m1;
        value = ((a * s + b) * s + m0) * s + v0;
    }
    return t <= k[0] ? k[1] : t >= k[4 * (n - 1)] ? k[4 * (n - 1) + 1] : value;
}

/* _player_crossfade.canon's (and _heights') norm: numpy's add.reduce of the squares, in order. */
static double norm4(const double *q) { return __builtin_elementwise_sqrt(((q[0] * q[0] + q[1] * q[1]) + q[2] * q[2]) + q[3] * q[3]); }

/* _player_crossfade.sample: each bone's q (canon'd: unit, w >= 0) and t at each time, the keyed components' curves
 * (index as az_origins'; 0 keys: the rest value); q nb x nt x 4, t nb x nt x 3. */
API i64 az_sample(const double *bone, i64 nb, const i64 *index, i64 ni, const double *keys, const double *times,
                  i64 nt, double *q, double *t) {
    for (i64 k = 0; k < nb; k++) {
        const double *b = bone + BONE * k;
        for (i64 i = 0; i < nt; i++) {
            double *qi = q + 4 * (nt * k + i), *ti = t + 3 * (nt * k + i);
            for (int c = 0; c < 7; c++) {
                const i64 *ix = index + 2 * (7 * k + c);
                double v = k < ni && ix[1] ? curve(keys + 4 * ix[0], ix[1], times[i]) : c < 3 ? b[12 + c] : b[1 + c];
                if (c < 3)
                    ti[c] = v;
                else
                    qi[c - 3] = v;
            }
            double n = norm4(qi), d = n > 0 ? n : 1.0;
            for (int c = 0; c < 4; c++) qi[c] = qi[c] / d;
            if (qi[3] < 0.0)
                for (int c = 0; c < 4; c++) qi[c] = -qi[c];
        }
    }
    return 0;
}

/* numpy's cross of 3-vectors. */
static void cross(const double *a, const double *b, double *o) {
    double x = a[1] * b[2] - a[2] * b[1], y = a[2] * b[0] - a[0] * b[2], z = a[0] * b[1] - a[1] * b[0];
    o[0] = x, o[1] = y, o[2] = z;
}

/* _player_crossfade._heights without points: each bone's height (z) at each time (out nb x nt) from a pose's q
 * (nb x nt x 4, normalised here) and t (nb x nt x 3); parent[k] < k; scratch holds 7 doubles a bone. */
API i64 az_heights(const i64 *parent, const double *bone, i64 nb, const double *q, const double *t, i64 nt,
                   double *out, double *scratch) {
    double *world = scratch, *at = scratch + 4 * nb;
    for (i64 i = 0; i < nt; i++) {
        for (i64 k = 0; k < nb; k++) {
            const double *b = bone + BONE * k, *qk = q + 4 * (nt * k + i), *v = t + 3 * (nt * k + i);
            double n = norm4(qk), d = n > 0 ? n : 1.0, u[4] = {qk[0] / d, qk[1] / d, qk[2] / d, qk[3] / d}, local[4];
            qmul(b, u, local);
            qmul(local, b + 8, local);
            double *w = world + 4 * k, *a = at + 3 * k;
            if (parent[k] < 0) {
                for (int c = 0; c < 4; c++) w[c] = local[c];
                for (int c = 0; c < 3; c++) a[c] = v[c];
            } else {
                const double *pw = world + 4 * parent[k], *pa = at + 3 * parent[k];
                double c2[3], c3[3];
                qmul(pw, local, w);
                cross(pw, v, c2);
                for (int c = 0; c < 3; c++) c2[c] = 2.0 * c2[c];
                cross(pw, c2, c3);
                for (int c = 0; c < 3; c++) a[c] = pa[c] + ((v[c] + pw[3] * c2[c]) + c3[c]);
            }
            out[nt * k + i] = a[2];
        }
    }
    return 0;
}

/* characters._rotate: v turned by q normalised (its plain sum of squares, sqrt or 1.0), each row's sum() of 3. */
static void rotate(const double *q, const double *v, double *o) {
    double x = q[0], y = q[1], z = q[2], w = q[3];
    double n = __builtin_elementwise_sqrt(x * x + y * y + z * z + w * w);
    if (n == 0.0) n = 1.0;
    x = x / n, y = y / n, z = z / n, w = w / n;
    double r[3][3] = {{1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)},
                      {2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)},
                      {2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)}};
    for (int i = 0; i < 3; i++) {
        double p[3] = {r[i][0] * v[0], r[i][1] * v[1], r[i][2] * v[2]};
        o[i] = psum(p, 3);
    }
}

/* characters._box of each of n markers' 12 values at scale: its low and high corners' bounds into out (n x 6). */
API i64 az_boxes(const double *values, i64 n, double scale, double *out) {
    for (i64 b = 0; b < n; b++) {
        const double *v = values + 12 * b;
        double half[3], *low = out + 6 * b, *high = low + 3;
        for (int i = 0; i < 3; i++) {
            half[i] = fab(v[7 + i] * v[10]);
            low[i] = __builtin_inf(), high[i] = -__builtin_inf();
        }
        for (int sx = -1; sx <= 1; sx += 2)
            for (int sy = -1; sy <= 1; sy += 2)
                for (int sz = -1; sz <= 1; sz += 2) {
                    double c[3] = {sx * half[0], sy * half[1], sz * half[2]}, corner[3];
                    rotate(v + 3, c, corner);
                    for (int i = 0; i < 3; i++) {
                        double p = (corner[i] + v[i]) * scale;
                        low[i] = p < low[i] ? p : low[i];
                        high[i] = p > high[i] ? p : high[i];
                    }
                }
    }
    return 0;
}

/* tools/characters _runs: each [start, end) where new differs from old (past old's end, all of it), the first cap
 * into out as pairs; the count of them all. */
API i64 az_runs(const unsigned char *old, i64 nold, const unsigned char *new, i64 nnew, i64 *out, i64 cap) {
    i64 count = 0, at = -1;
    for (i64 i = 0; i < nnew; i++) {
        int same = i < nold && old[i] == new[i];
        if (!same && at < 0) {
            at = i;
        } else if (same && at >= 0) {
            if (count < cap) out[2 * count] = at, out[2 * count + 1] = i;
            count++;
            at = -1;
        }
    }
    if (at >= 0) {
        if (count < cap) out[2 * count] = at, out[2 * count + 1] = nnew;
        count++;
    }
    return count;
}
