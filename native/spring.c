/* The springs' kernels, compiled (D1009): tools/characters/jiggle.py's keyed for one placed bone of a clip (az_spring:
 * its anchors' path smoothed into the drive, the Euler steps, the fit to its travel and turn, pose_at and the keyed
 * numbers) and _clear for one clip (az_clear: its frames, each link's least turns that keep the chain out of the body,
 * their ease, a held clip's drape and the keys it rewrites). Each is its Python twin's operations in the twin's order
 * on doubles, with no contraction, so the two agree bit for bit (tests/test_native.py); a sum() of floats is Python's
 * (CPython's Neumaier sum, from its int start 0), Python's min and max keep their first, numpy's max holds a NaN.
 * Where the twin raises (a division by zero, numpy's reduction of no points, a bone it can't index) or a number is
 * past the kernel (a turn past fdlibm's kernels' range), the kernel answers 2 and its caller runs the twin.
 * No libm, no libc, no allocation: the caller passes every buffer. Built by nativekit (C99, zig cc). */
#include <stdint.h>

#if defined(_WIN32)
#define API __declspec(dllexport)
#else
#define API __attribute__((visibility("default")))
#endif

typedef int64_t i64;

#define TWIN 2

static double fab(double x) { return __builtin_fabs(x); }
static double sqr(double x) { return __builtin_elementwise_sqrt(x); }   /* never errno, so never libm's sqrt */
static int finite(double x) { return __builtin_isfinite(x); }

static double of_bits(uint64_t u) {
    union { uint64_t u; double d; } v = { u };
    return v.d;
}

static double hw(uint64_t high) { return of_bits(high << 32); }   /* fdlibm._hw */

/* sum() of n >= 1 floats: 0 + x[0], then Neumaier's compensation, added at the end only if nonzero and finite. */
static double psum(const double *x, i64 n) {
    double f = 0.0 + x[0], c = 0.0;
    for (i64 i = 1; i < n; i++) {
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

static void qinv(const double *q, double *o) { o[0] = -q[0], o[1] = -q[1], o[2] = -q[2], o[3] = q[3]; }

/* retarget._turn: v turned by q, qmul(qmul(q, (*v, 0.0)), qinv(q))[:3]; o may be v. */
static void turn(const double *q, const double *v, double *o) {
    double a[4] = {v[0], v[1], v[2], 0.0}, inv[4];
    qinv(q, inv);
    qmul(q, a, a);
    qmul(a, inv, a);
    o[0] = a[0], o[1] = a[1], o[2] = a[2];
}

/* jiggle._matrix: q's rotation, row by row. */
static void matrix(const double *q, double *r) {
    double x = q[0], y = q[1], z = q[2], w = q[3];
    r[0] = 1.0 - 2.0 * (y * y + z * z), r[1] = 2.0 * (x * y - z * w), r[2] = 2.0 * (x * z + y * w);
    r[3] = 2.0 * (x * y + z * w), r[4] = 1.0 - 2.0 * (x * x + z * z), r[5] = 2.0 * (y * z - x * w);
    r[6] = 2.0 * (x * z - y * w), r[7] = 2.0 * (y * z + x * w), r[8] = 1.0 - 2.0 * (x * x + y * y);
}

/* jiggle._limit: u / sqrt(1 + (u / cap)^2); *bad at a cap of zero (the twin's ZeroDivisionError). */
static double limit(double u, double cap, int *bad) {
    if (cap == 0.0) {
        *bad = 1;
        return 0.0;
    }
    return u / sqr(1.0 + (u / cap) * (u / cap));
}

/* jiggle._vlimit into o (v itself where its length is zero). */
static void vlimit(const double *v, double cap, double *o, int *bad) {
    double n = sqr(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);
    if (n == 0.0) {
        o[0] = v[0], o[1] = v[1], o[2] = v[2];
        return;
    }
    double s = limit(n, cap, bad) / n;
    o[0] = v[0] * s, o[1] = v[1] * s, o[2] = v[2] * s;
}

/* Python's max(a, b) and min(a, b): the first unless the second is greater (less). */
static double pmax(double a, double b) { return b > a ? b : a; }
static double pmin(double a, double b) { return b < a ? b : a; }

/* Python's i % n for n > 0: never negative. */
static i64 mod(i64 i, i64 n) { return ((i % n) + n) % n; }

/* ---- az_spring: jiggle.keyed's spring of one placed bone --------------------------------------------------------- */

/* A bone's numbers (jiggle.keyed's): its parent's bind rotation, the anchors' places in it (_turn(qinv(bind), ...)
 * of each side), its rest translation, gravity in model units, the spring's gain, hang, drive cap (after a flag:
 * 1.0 capped), omega, damping, travel and turn, the sides' span, a one-shot's release, the clip's length, the
 * steps' clip time (dtau) and real time (dt). */
enum {
    S_BIND = 0, S_SIDES = 4, S_REST = 10, S_G = 13, S_GAIN, S_HANG, S_CAPPED, S_DRIVE, S_OMEGA, S_DAMPING, S_TRAVEL,
    S_TURN, S_SPAN, S_RELEASE, S_LENGTH, S_DTAU, S_DT, S_COUNT
};

/* jiggle._smooth of n samples s (3 doubles each) by the kn integer weights into out, each weight and their sum
 * as Python's int * float and float / int take them (the int rounded to a double; the caller: n >= 2 in a loop and
 * the sum not zero). */
static void smooth(const double *s, i64 n, i64 loop, const double *kernel, i64 kn, double total, double *out) {
    i64 half = kn / 2;
    for (i64 i = 0; i < n; i++) {
        double acc[3] = {0.0, 0.0, 0.0};
        for (i64 j = 0; j < kn; j++) {
            i64 m = i + j - half;
            m = loop ? mod(m, n - 1) : m < 0 ? 0 : m > n - 1 ? n - 1 : m;
            double c = kernel[j];
            acc[0] += c * s[3 * m];
            acc[1] += c * s[3 * m + 1];
            acc[2] += c * s[3 * m + 2];
        }
        for (int k = 0; k < 3; k++) out[3 * i + k] = acc[k] / total;
    }
}

/* jiggle.keyed's path for one placed bone, past its parent's pose: at each of n steps its parent's world rotation and
 * origin (world + 4 * (i * stride + col), origin + 3 * (i * stride + col)), num its numbers (S_*), kernel its drive's
 * kn integer weights and total their sum (each a double as Python rounds an int); its nkeys keys' five numbers (every
 * sub-th step's: _flat) into flat and its peaks (the largest translation and turn) into peaks. work: 18 n doubles. 0,
 * or TWIN where the twin raises (a division by zero), n is under 2 or a key's step past n. */
API i64 az_spring(const double *world, const double *origin, i64 stride, i64 col, i64 n, const double *num,
                  const double *kernel, i64 kn, double total, i64 loop, i64 sub, i64 nkeys, double *flat, double *peaks,
                  double *work) {
    if (n < 2 || total == 0.0 || sub < 1 || nkeys < 1 || (nkeys - 1) * sub > n - 1) return TWIN;
    int bad = 0;
    const double *bind = num + S_BIND;
    double dtau = num[S_DTAU], dt = num[S_DT], g = num[S_G], omega = num[S_OMEGA], gain = num[S_GAIN];
    double hang = num[S_HANG], damping = num[S_DAMPING], travel = num[S_TRAVEL], tn = num[S_TURN];
    double span = num[S_SPAN], release = num[S_RELEASE], length = num[S_LENGTH];
    if (dtau * dtau == 0.0 || span == 0.0) return TWIN;
    double *path_s = work, *pts = work + 3 * n, *drives = work + 6 * n, *path = work + 12 * n;
    double ib[4];
    qinv(bind, ib);
    for (int s = 0; s < 2; s++) {
        const double *side = num + S_SIDES + 3 * s;
        for (i64 i = 0; i < n; i++) {   /* the anchor: the parent's origin and the side turned by its rotation */
            const double *w = world + 4 * (i * stride + col), *o = origin + 3 * (i * stride + col);
            double t[3];
            turn(w, side, t);
            for (int k = 0; k < 3; k++) path_s[3 * i + k] = o[k] + t[k];
        }
        if (loop) {   /* the seam closed by a line */
            double gap[3];
            for (int k = 0; k < 3; k++) gap[k] = path_s[3 * (n - 1) + k] - path_s[k];
            for (i64 i = 0; i < n; i++)
                for (int k = 0; k < 3; k++)
                    path_s[3 * i + k] = path_s[3 * i + k] - gap[k] * (double)i / (double)(n - 1);
        }
        smooth(path_s, n, loop, kernel, kn, total, pts);
        double *d = drives + 3 * n * s;
        for (i64 i = 0; i < n; i++) {   /* the anchor's acceleration (none at a one-shot's ends) */
            if (!loop && (i == 0 || i == n - 1)) continue;
            const double *a0 = pts + 3 * (loop ? mod(i - 1, n - 1) : i - 1 > 0 ? i - 1 : 0);
            const double *a2 = pts + 3 * (loop ? mod(i + 1, n - 1) : i + 1 < n - 1 ? i + 1 : n - 1);
            for (int k = 0; k < 3; k++) d[3 * i + k] = (a0[k] + a2[k] - 2.0 * pts[3 * i + k]) / (dtau * dtau);
        }
        if (!loop)   /* the ends hold their neighbours' */
            for (int k = 0; k < 3; k++) {
                d[k] = n > 2 ? d[3 + k] : 0.0;
                d[3 * (n - 1) + k] = n > 2 ? d[3 * (n - 2) + k] : 0.0;
            }
        for (i64 i = 0; i < n; i++) {   /* in the parent's frame against its bind: gravity less the acceleration */
            const double *w = world + 4 * (i * stride + col);
            double rel[4], inv[4], f[3], down[3], u[3];
            qmul(w, ib, rel);
            qinv(rel, inv);
            double acc[3] = {-gain * d[3 * i], -gain * d[3 * i + 1], -gain * d[3 * i + 2]}, fall[3] = {0.0, 0.0, -g};
            turn(inv, acc, f);
            turn(inv, fall, down);
            u[0] = f[0] + hang * down[0], u[1] = f[1] + hang * down[1], u[2] = f[2] + hang * (down[2] + g);
            if (num[S_CAPPED] == 1.0)
                vlimit(u, num[S_DRIVE], d + 3 * i, &bad);
            else
                for (int k = 0; k < 3; k++) d[3 * i + k] = u[k];
        }
    }
    if (bad) return TWIN;
    int passes = loop ? 3 : 1;
    double state[2][6] = {{0.0}};
    for (int pas = 0; pas < passes; pas++)
        for (int s = 0; s < 2; s++) {
            double x[3] = {state[s][0], state[s][1], state[s][2]}, v[3] = {state[s][3], state[s][4], state[s][5]};
            const double *d = drives + 3 * n * s;
            double *p = path + 3 * n * s;
            for (i64 i = 0; i < n; i++) {
                if (pas == passes - 1)
                    for (int k = 0; k < 3; k++) p[3 * i + k] = x[k];
                if (i == n - 1) break;
                double dv[3];
                for (int k = 0; k < 3; k++)
                    dv[k] = d[3 * i + k] - omega * omega * x[k] - 2.0 * damping * omega * v[k];
                for (int k = 0; k < 3; k++) v[k] = v[k] + dt * dv[k];
                for (int k = 0; k < 3; k++) x[k] = x[k] + dt * v[k];
            }
            for (int k = 0; k < 3; k++) state[s][k] = x[k], state[s][3 + k] = v[k];
        }
    double *pl = path, *pr = path + 3 * n;
    if (loop)   /* the seam: the last pass's end is its start */
        for (int k = 0; k < 3; k++) pl[3 * (n - 1) + k] = pl[k], pr[3 * (n - 1) + k] = pr[k];
    double wide = 0.0, turned = 0.0;
    for (i64 i = 0; i < n; i++) {
        double sq[3];
        for (int k = 0; k < 3; k++) {
            double m = (pl[3 * i + k] + pr[3 * i + k]) / 2.0;
            sq[k] = m * m;
        }
        double a = sqr(psum(sq, 3));
        double t = pmax(fab(pl[3 * i + 2] - pr[3 * i + 2]), fab(pr[3 * i + 1] - pl[3 * i + 1])) / span;
        wide = i ? pmax(wide, a) : a;
        turned = i ? pmax(turned, t) : t;
    }
    double fit = 1.0, a = 1.0, b = 1.0;
    if (wide > travel) {
        if (wide == 0.0) return TWIN;
        a = travel / wide;
    }
    if (turned > tn) {
        if (turned == 0.0) return TWIN;
        b = tn / turned;
    }
    fit = pmin(pmin(fit, a), b);
    if (fit < 1.0)   /* the whole swing scaled to its stops */
        for (i64 i = 0; i < 6 * n; i++) path[i] = fit * path[i];
    double peak_move = 0.0, peak_turn = 0.0;
    for (i64 i = 0; i < n; i++) {   /* pose_at: a one-shot eases to rest by its end */
        const double *xl = pl + 3 * i, *xr = pr + 3 * i;
        double k = 1.0;
        if (release > 0.0 && dtau * (double)i > length - release) {
            double u = (length - dtau * (double)i) / release;
            k = u * u * (3.0 - 2.0 * u);
        }
        double mid[3] = {(xl[0] + xr[0]) / 2.0, (xl[1] + xr[1]) / 2.0, (xl[2] + xr[2]) / 2.0}, mean[3];
        vlimit(mid, travel, mean, &bad);
        for (int c = 0; c < 3; c++) mean[c] = k * mean[c];
        double roll = k * limit((xl[2] - xr[2]) / span, tn, &bad);
        double yaw = k * limit((xr[1] - xl[1]) / span, tn, &bad);
        if (bad) return TWIN;
        double sq[3] = {mean[0] * mean[0], mean[1] * mean[1], mean[2] * mean[2]};
        double m = sqr(psum(sq, 3)), r = pmax(fab(roll), fab(yaw));
        peak_move = i ? pmax(peak_move, m) : m;
        peak_turn = i ? pmax(peak_turn, r) : r;
        if (i % sub == 0 && i / sub < nkeys) {   /* _flat: the rest translation plus the mean in the parent's frame */
            double off[3], *o = flat + 5 * (i / sub);
            turn(ib, mean, off);
            o[0] = num[S_REST] + off[0], o[1] = num[S_REST + 1] + off[1], o[2] = num[S_REST + 2] + off[2];
            o[3] = roll / 2.0, o[4] = yaw / 2.0;
        }
    }
    peaks[0] = peak_move, peaks[1] = peak_turn;
    return 0;
}

/* ---- az_clear: jiggle._clear ------------------------------------------------------------------------------------- */

/* fdlibm.sin and cos of |x| under pi/4 (their kernels alone); *bad past it (the twin reduces it). */
typedef union { uint64_t u; double d; } bits64;   /* each constant its fdlibm.py bit pattern */
static const bits64 KS[6] = {{0xBFC5555555555549}, {0x3F8111111110F8A6}, {0xBF2A01A019C161D5},
                             {0x3EC71DE357B1FE7D}, {0xBE5AE5E68A2B9CEB}, {0x3DE5D93A5ACFD57C}};
static const bits64 KC[6] = {{0x3FA555555555554C}, {0xBF56C16C16C15177}, {0x3EFA01A019CB1590},
                             {0xBE927E4F809C52AD}, {0x3E21EE9EBDB4B1C4}, {0xBDA8FAE9BE8838D4}};

static double sin_(double x, int *bad) {
    double ax = fab(x);
    if (!(ax < hw(0x3FE921FC))) {
        *bad = 1;
        return 0.0;
    }
    if (ax < hw(0x3E500000)) return x;
    double z = x * x, w = z * z;
    double r = KS[1].d + z * (KS[2].d + z * KS[3].d) + z * w * (KS[4].d + z * KS[5].d);
    double v = z * x;
    return x + v * (KS[0].d + z * r);
}

static double cos_(double x, int *bad) {
    double ax = fab(x), y = 0.0;
    if (!(ax < hw(0x3FE921FC))) {
        *bad = 1;
        return 0.0;
    }
    if (ax < hw(0x3E46A09E)) return 1.0;
    double z = x * x, w = z * z;
    double r = z * (KC[0].d + z * (KC[1].d + z * KC[2].d)) + w * w * (KC[3].d + z * (KC[4].d + z * KC[5].d));
    double hz = 0.5 * z;
    w = 1.0 - hz;
    return w + (((1.0 - w) - hz) + (z * r - x * y));
}

/* numpy's max of n >= 1 values: a NaN holds. */
static double nmax(const double *x, i64 n) {
    double m = x[0];
    for (i64 i = 1; i < n; i++) {
        if (m != m) return m;
        if (x[i] != x[i] || x[i] > m) m = x[i];
    }
    return m;
}

/* The numbers a call passes (jiggle's constants, the clip's, the pivot's place). */
enum { N_TURN = 0, N_TOL, N_NEAR, N_DRAPE, N_DRAPE_RATE, N_REST, N_REACH, N_CELL, N_LENGTH, N_PU, N_COUNT = N_PU + 3 };
/* The sizes: links, keys, loop, held, posed bones a frame, skin and tail points, the rig's bones, the posed slots of
 * the first link's parent and the pivot's bone, CLEAR_SUB, CLEAR_STEPS, CLEAR_EASE and CLEAR_HOLD. */
enum { Z_L = 0, Z_NK, Z_LOOP, Z_HELD, Z_NP, Z_NS, Z_NT, Z_NB, Z_PARENT, Z_PIVOT, Z_SUB, Z_STEPS, Z_EASE, Z_HOLD, Z_COUNT };

typedef struct {
    i64 L, nk, loop, held, back, np, ns, nt, nb, sub, steps, ease, hold, count, n, parent, pivot;
    const double *num, *bone, *world, *origin, *sW, *sU, *sUN, *tW, *tU, *target, *keys;
    const i64 *slot, *linkof, *sB, *tB, *owner;
    double *R, *X, *N, *W0, *O0, *angle, *need, *at_key, *share, *was, *Wt, *Ot, *Wr, *Or, *Rl, *P, *g, *d, *bspan;
    i64 *own, *sel, *ok, *far, *keep, *has, *bucket, *order, *kb, *fill;
    unsigned char *done;
    int bad;
} K;

/* eased(c, f): link c's turns at frame f, lerped between its keys'. */
static void eased(const K *k, i64 c, i64 f, double *o) {
    i64 j = f / k->sub, q = f % k->sub;
    const double *a = k->angle + 2 * (k->count * c + j);
    double nxt[2] = {0.0, 0.0};
    if (q) nxt[0] = k->angle[2 * (k->count * c + (j + 1) % k->count)], nxt[1] = k->angle[2 * (k->count * c + (j + 1) % k->count) + 1];
    for (int x = 0; x < 2; x++) o[x] = a[x] + (nxt[x] - a[x]) * (double)q / (double)k->sub;
}

/* A posed bone's rotation and origin at frame f (slot s). */
static const double *pw_of(const K *k, i64 f, i64 s) { return k->world + 4 * (k->np * f + s); }
static const double *po_of(const K *k, i64 f, i64 s) { return k->origin + 3 * (k->np * f + s); }

/* turned(f, upto, extra, c_extra): frame f's chain with links before upto turned as eased, link cx by extra, into
 * W (L x 4) and Og (L x 3). */
static void turned(K *k, i64 f, i64 upto, const double *extra, i64 cx, double *W, double *Og) {
    i64 L = k->L;
    for (i64 i = 0; i < 4 * L; i++) W[i] = k->W0[4 * L * f + i];
    for (i64 i = 0; i < 3 * L; i++) Og[i] = k->O0[3 * L * f + i];
    for (i64 c = 0; c < L; c++) {
        double ps[2] = {0.0, 0.0};
        if (c == cx)
            ps[0] = extra[0], ps[1] = extra[1];
        else if (c < upto)
            eased(k, c, f, ps);
        if (!(ps[0] != 0.0 || ps[1] != 0.0)) continue;   /* NaN is truthy */
        double J[3];
        if (c) {   /* between its origin and its parent's */
            for (int i = 0; i < 3; i++) J[i] = (Og[3 * (c - 1) + i] + Og[3 * c + i]) / 2.0;
        } else {
            double t[3];
            const double *pk = pw_of(k, f, k->pivot), *po = po_of(k, f, k->pivot);
            turn(pk, k->num + N_PU, t);
            for (int i = 0; i < 3; i++) J[i] = po[i] + t[i];
        }
        const double *b = k->bone + 12 * c;
        double ib[4], carried[4], e[4] = {0.0, 0.0, 0.0, 1.0};
        qinv(b + 8, ib);
        qmul(c ? W + 4 * (c - 1) : pw_of(k, f, k->parent), ib, carried);
        for (int a = 0; a < 2; a++) {   /* pitched, then swung about its pitched fore-aft axis */
            double v = ps[a];
            if (v == 0.0) continue;
            double axis[3] = {a == 0 ? 1.0 : 0.0, a == 1 ? 1.0 : 0.0, 0.0}, t[3], h[4];
            turn(carried, axis, t);
            double sn = sin_(v / 2.0, &k->bad), cs = cos_(v / 2.0, &k->bad);
            h[0] = t[0] * sn, h[1] = t[1] * sn, h[2] = t[2] * sn, h[3] = cs;
            qmul(e, h, e);
        }
        for (i64 m = c; m < L; m++) {
            double rel[3], t[3];
            qmul(e, W + 4 * m, W + 4 * m);
            for (int i = 0; i < 3; i++) rel[i] = Og[3 * m + i] - J[i];
            turn(e, rel, t);
            for (int i = 0; i < 3; i++) Og[3 * m + i] = J[i] + t[i];
        }
    }
}

/* A bone's rotation (3x3) and origin at frame f as short skins the tail: a link's its turned chain's, else its posed
 * one's, else zeros (np.zeros' rows no pose wrote). */
static const double ZERO[9] = {0.0};

/* A value's bucket of nb over [lo, lo + nb w): never less for a greater value (each step rounds monotonically). */
static i64 bucket(double v, double lo, double w, i64 nb) {
    if (nb == 1) return 0;
    double t = (v - lo) / w;
    i64 b = t < 0.0 ? 0 : t >= (double)nb ? nb - 1 : (i64)t;
    return b;
}

/* The skin point x's unit normal at frame f (jiggle._skinned's normals of the frame's pose), worked out once. */
static const double *normal(K *k, i64 f, i64 x) {
    double *o = k->N + 3 * (k->ns * f + x);
    unsigned char *done = k->done + k->ns * f + x;
    if (*done) return o;
    o[0] = o[1] = o[2] = 0.0;
    for (int s = 0; s < 4; s++) {
        i64 b = k->sB[4 * x + s];
        const double *r = k->slot[b] >= 0 ? k->R + 9 * (k->np * f + k->slot[b]) : ZERO, *u = k->sUN + 12 * x + 3 * s;
        double w = k->sW[4 * x + s];
        for (int c = 0; c < 3; c++) o[c] += w * (r[3 * c] * u[0] + r[3 * c + 1] * u[1] + r[3 * c + 2] * u[2]);
    }
    double len = sqr(o[0] * o[0] + o[1] * o[1] + o[2] * o[2]);
    for (int c = 0; c < 3; c++) o[c] = o[c] / len;
    *done = 1;
    return o;
}

/* short(f, W, Og, sel): each of the m tail points sel's target less its signed distance from the skin at frame f, the
 * links posed W and Og, into gap. *bad for m 0 (numpy refuses the bounds of no points). */
static void short_(K *k, i64 f, const double *W, const double *Og, const i64 *sel, i64 m, double *gap) {
    if (m < 1) {
        k->bad = 1;
        return;
    }
    for (i64 c = 0; c < k->L; c++) matrix(W + 4 * c, k->Rl + 9 * c);
    double *P = k->P;
    for (i64 i = 0; i < m; i++) {   /* jiggle._skinned of the tail's points sel */
        i64 p = sel[i];
        double *o = P + 3 * i;
        o[0] = o[1] = o[2] = 0.0;
        for (int s = 0; s < 4; s++) {
            i64 b = k->tB[4 * p + s];
            const double *r, *og, *u = k->tU + 12 * p + 3 * s;
            i64 c = k->linkof[b];
            if (c >= 0)
                r = k->Rl + 9 * c, og = Og + 3 * c;
            else if (k->slot[b] >= 0)
                r = k->R + 9 * (k->np * f + k->slot[b]), og = po_of(k, f, k->slot[b]);
            else
                r = ZERO, og = ZERO;
            double w = k->tW[4 * p + s];
            for (int a = 0; a < 3; a++) {
                double t = r[3 * a] * u[0] + r[3 * a + 1] * u[1] + r[3 * a + 2] * u[2];
                o[a] += w * (og[a] + t);
            }
        }
    }
    /* jiggle._signed's distances (az_signed's): the skin points in reach of the points' bounds, the nearest each */
    const double *X = k->X + 3 * k->ns * f;
    double reach = k->num[N_REACH], cell = k->num[N_CELL], lo[3], hi[3];
    for (int c = 0; c < 3; c++) {
        lo[c] = hi[c] = P[c];
        for (i64 p = 1; p < m; p++) {   /* numpy's min and max: a NaN holds */
            double v = P[3 * p + c];
            if (v != v || v < lo[c]) lo[c] = lo[c] != lo[c] ? lo[c] : v;
            if (v != v || v > hi[c]) hi[c] = hi[c] != hi[c] ? hi[c] : v;
        }
        lo[c] = lo[c] - reach, hi[c] = hi[c] + reach;
    }
    i64 kept = 0, *keep = k->keep;
    for (i64 x = 0; x < k->ns; x++) {
        const double *y = X + 3 * x;
        if (y[0] >= lo[0] && y[0] <= hi[0] && y[1] >= lo[1] && y[1] <= hi[1] && y[2] >= lo[2] && y[2] <= hi[2])
            keep[kept++] = x;
    }
    int a = 0, open = 1;   /* a box of finite bounds: its points finite, so no distance is NaN */
    for (int c = 0; c < 3; c++) {
        if (!(finite(lo[c]) && finite(hi[c]))) open = 0;
        if (hi[c] - lo[c] > hi[a] - lo[a]) a = c;
    }
    i64 nb = 1;
    double w = 0.0;
    if (open && kept > 16) {   /* the kept points in buckets along the box's widest axis, each its values' span */
        nb = kept / 4 < 256 ? kept / 4 : 256;
        w = (hi[a] - lo[a]) / (double)nb;
        if (!(w > 0.0 && finite(w))) nb = 1;
    }
    i64 *start = k->bucket, *order = k->order;
    double *bmin = k->bspan, *bmax = k->bspan + 256;
    if (open) {
        for (i64 b = 0; b <= nb; b++) start[b] = 0;
        for (i64 i = 0; i < kept; i++) {
            i64 b = bucket(X[3 * keep[i] + a], lo[a], w, nb);
            k->kb[i] = b;
            start[b + 1]++;
        }
        for (i64 b = 0; b < nb; b++) start[b + 1] += start[b];
        for (i64 b = 0; b < nb; b++) k->fill[b] = start[b], bmin[b] = __builtin_inf(), bmax[b] = -__builtin_inf();
        for (i64 i = 0; i < kept; i++) {
            i64 b = k->kb[i];
            double v = X[3 * keep[i] + a];
            order[k->fill[b]++] = keep[i];
            if (v < bmin[b]) bmin[b] = v;
            if (v > bmax[b]) bmax[b] = v;
        }
    }
    for (i64 p = 0; p < m; p++) {
        const double *q = P + 3 * p;
        i64 j = -1;
        double near = 0.0, d;
        if (open) {   /* the least (distance, index) within reach: a bucket whose nearest value is farther is passed */
            near = reach * reach;
            i64 home = bucket(q[a], lo[a], w, nb);
            for (int side = 0; side < 3; side++) {
                i64 b = side == 0 ? home : side == 1 ? home + 1 : home - 1, step = side == 2 ? -1 : 1;
                for (; b >= 0 && b < nb; b += step) {
                    if (start[b] == start[b + 1]) {
                        if (side == 0) break;
                        continue;
                    }
                    if (side) {
                        double da = q[a] - (side == 1 ? bmin[b] : bmax[b]);
                        if (da * da > near) break;
                    }
                    for (i64 i = start[b]; i < start[b + 1]; i++) {
                        i64 x = order[i];
                        const double *y = X + 3 * x;
                        double dx = q[0] - y[0], dy = q[1] - y[1], dz = q[2] - y[2], d2 = dx * dx + dy * dy + dz * dz;
                        if (d2 < near || (d2 == near && (j < 0 || x < j))) j = x, near = d2;
                    }
                    if (side == 0) break;
                }
            }
        } else {
            for (i64 i = 0; i < kept; i++) {
                const double *y = X + 3 * keep[i];
                double dx = q[0] - y[0], dy = q[1] - y[1], dz = q[2] - y[2], d2 = dx * dx + dy * dy + dz * dz;
                if (j < 0 || (near == near && (d2 != d2 || d2 < near))) j = keep[i], near = d2;
            }
        }
        if (j < 0) {
            d = __builtin_inf();
        } else {
            const double *y = X + 3 * j, *n = normal(k, f, j);
            double e = (q[0] - y[0]) * n[0] + (q[1] - y[1]) * n[1] + (q[2] - y[2]) * n[2], aside = near - e * e;
            if (aside > cell * cell && aside > e * e) e = sqr(near);
            d = near <= reach * reach ? e : __builtin_inf();
        }
        gap[p] = k->target[sel[p]] - d;
    }
}

/* clear(v, pts): whether link c turned by v (sign's way about axis, the other base) leaves no point of pts short. */
static int clears(K *k, i64 f, i64 c, int axis, double base, double sign, double v, const i64 *pts, i64 m) {
    double extra[2];
    extra[axis] = sign * v, extra[1 - axis] = base;
    turned(k, f, c, extra, c, k->Wt, k->Ot);
    short_(k, f, k->Wt, k->Ot, pts, m, k->g);
    if (k->bad) return 0;
    return !(nmax(k->g, m) > k->num[N_TOL]);
}

typedef struct { i64 count; double hi; i64 rank; double turn; } Found;

/* Python's tuple a < b of two finds. */
static int less(const Found *a, const Found *b) {
    if (a->count != b->count) return a->count < b->count;
    if (a->hi != b->hi) return a->hi < b->hi;
    if (a->rank != b->rank) return a->rank < b->rank;
    if (a->turn != b->turn) return a->turn < b->turn;
    return 0;
}

/* least(f, c, sel, axis, base, ways, cheaper, hint, whole): the least of its finds. */
static Found least(K *k, i64 f, i64 c, const i64 *sel, i64 nsel, int axis, double base, const double *ways,
                   int nways, int cheaper, double hint, int whole) {
    double tn = k->num[N_TURN], tol = k->num[N_TOL];
    double lim = c ? tn - fab(base) : tn;
    Found best = {0, 0.0, 0, 0.0};
    for (int rank = 0; rank < nways; rank++) {
        double sign = ways[rank], extra[2];
        extra[axis] = sign * lim, extra[1 - axis] = base;
        turned(k, f, c, extra, c, k->Wt, k->Ot);
        short_(k, f, k->Wt, k->Ot, sel, nsel, k->g);
        if (k->bad) return best;
        i64 nok = 0, nstuck = 0;
        for (i64 i = 0; i < nsel; i++) {
            if (k->g[i] > tol)
                nstuck++;
            else
                k->ok[nok++] = sel[i];
        }
        double lo = 0.0, hi = lim;
        i64 steps = k->steps;
        if (nstuck && (whole || !nok || clears(k, f, c, axis, base, sign, 0.0, k->ok, nok))) {
            hi = 0.0, steps = 0;
        } else if (sign * hint > 0.0) {   /* a bracket a sixteenth of the most wide by the turn before */
            double h = pmin(fab(hint), lim), d = lim / 16.0;
            if (clears(k, f, c, axis, base, sign, h, k->ok, nok)) {
                lo = pmax(h - d, 0.0), hi = h;
                if (lo != 0.0 && clears(k, f, c, axis, base, sign, lo, k->ok, nok)) hi = lo, lo = 0.0;
            } else {
                lo = h, hi = pmin(h + d, lim);
                if (hi < lim && !clears(k, f, c, axis, base, sign, hi, k->ok, nok)) lo = hi, hi = lim;
            }
            steps = hi - lo <= d + 1e-12 ? 4 : k->steps;
        }
        if (k->bad) return best;
        for (i64 s = 0; s < steps; s++) {
            double mid = (lo + hi) / 2.0;
            if (clears(k, f, c, axis, base, sign, mid, k->ok, nok))
                hi = mid;
            else
                lo = mid;
        }
        if (k->bad) return best;
        Found got = {nstuck, hi, rank, sign * hi};
        if (rank == 0 || less(&got, &best)) best = got;
        if (!(nstuck || cheaper)) break;
    }
    return best;
}

/* ways(axis): the way of the link's nearest turn within CLEAR_HOLD frames and only that; else its parent link's way,
 * the other where that can't clear; else both, the cheaper. */
static int ways(const K *k, i64 f, int axis, const double *up, double *w, int *cheaper) {
    for (i64 dist = 0; dist <= k->hold; dist++)
        for (int side = 0; side < (dist ? 2 : 1); side++) {
            i64 d = side ? dist : -dist, at = f + d;
            if (!k->loop && (at < 0 || at >= k->n)) continue;
            double v = k->need[2 * mod(at, k->n) + axis];
            if (v != 0.0) {
                w[0] = __builtin_copysign(1.0, v);
                *cheaper = 0;
                return 1;
            }
        }
    if (up[axis] != 0.0) {
        w[0] = __builtin_copysign(1.0, up[axis]), w[1] = -__builtin_copysign(1.0, up[axis]);
        *cheaper = 0;
        return 2;
    }
    w[0] = 1.0, w[1] = -1.0;
    *cheaper = 1;
    return 2;
}

/* solve(sel): pitched; where that leaves some short, swung, or swung on the pitch, where that clears them all; else
 * the pitch alone. */
static void solve(K *k, i64 f, i64 c, const i64 *sel, i64 nsel, const double *hint, const double *up, double *got) {
    double w[2];
    int cheaper, nw = ways(k, f, 0, up, w, &cheaper);
    Found pitch = least(k, f, c, sel, nsel, 0, 0.0, w, nw, cheaper, hint[0], 0);
    if (k->bad) return;
    if (!pitch.count) {
        got[0] = pitch.turn, got[1] = 0.0;
        return;
    }
    nw = ways(k, f, 1, up, w, &cheaper);
    Found swing = least(k, f, c, sel, nsel, 1, 0.0, w, nw, cheaper, hint[1], 1);
    if (k->bad) return;
    if (!swing.count) {
        got[0] = 0.0, got[1] = swing.turn;
        return;
    }
    nw = ways(k, f, 1, up, w, &cheaper);
    Found both = least(k, f, c, sel, nsel, 1, pitch.turn, w, nw, cheaper, hint[1], 1);
    got[0] = pitch.turn, got[1] = both.count ? 0.0 : both.turn;
}

/* The search of link c: each frame's least turns (need), each key the most its spans need, eased into angle. */
static void search(K *k, i64 c) {
    i64 n = k->n, sub = k->sub, nown = 0, count = k->count;
    double tol = k->num[N_TOL], near = k->num[N_NEAR];
    for (i64 p = 0; p < k->nt; p++)
        if (k->held ? k->owner[p] >= c : k->owner[p] == c) k->own[nown++] = p;
    for (i64 i = 0; i < 2 * n; i++) k->need[i] = 0.0;
    i64 nkeys = (n + sub - 1) / sub;
    for (i64 o = 0; o < n && nown; o++) {   /* its keys' frames first, then those between */
        i64 f;
        if (o < nkeys)
            f = k->back ? (nkeys - 1 - o) * sub : o * sub;
        else {
            i64 b = o - nkeys;   /* the b-th frame between keys (from the end when back) */
            if (k->back) b = (n - nkeys) - 1 - b;
            f = b / (sub - 1) * sub + b % (sub - 1) + 1;
        }
        turned(k, f, c, 0, -1, k->Wt, k->Ot);
        short_(k, f, k->Wt, k->Ot, k->own, nown, k->d);
        if (k->bad) return;
        if (!(nmax(k->d, nown) > tol)) continue;
        i64 j = f / sub, q = f % sub;
        double hint[2] = {0.0, 0.0}, up[2] = {0.0, 0.0}, got[2];
        if (k->back) {
            if (f + sub < n) hint[0] = k->need[2 * (f + sub)], hint[1] = k->need[2 * (f + sub) + 1];
        } else if (f >= sub) {
            hint[0] = k->need[2 * (f - sub)], hint[1] = k->need[2 * (f - sub) + 1];
        }
        if (q) {
            const double *a = k->need + 2 * (j * sub), *b = k->need + 2 * mod((j + 1) * sub, n);
            for (int x = 0; x < 2; x++) hint[x] = a[x] + (b[x] - a[x]) * (double)q / (double)sub;
            if (hint[0] != 0.0 || hint[1] != 0.0) {
                turned(k, f, c, hint, c, k->Wt, k->Ot);
                short_(k, f, k->Wt, k->Ot, k->own, nown, k->g);
                if (k->bad) return;
                if (!(nmax(k->g, nown) > tol)) continue;
            }
        }
        if (c) eased(k, c - 1, f, up);
        i64 nsel = 0, nfar = 0;
        for (i64 i = 0; i < nown; i++) {
            if (k->d[i] > -near) k->sel[nsel++] = k->own[i];
            if (k->d[i] <= -near) k->far[nfar++] = k->own[i];
        }
        solve(k, f, c, k->sel, nsel, hint, up, got);
        if (k->bad) return;
        if (nfar) {   /* one farther off went in */
            turned(k, f, c, got, c, k->Wt, k->Ot);
            short_(k, f, k->Wt, k->Ot, k->far, nfar, k->g);
            if (k->bad) return;
            if (nmax(k->g, nfar) > tol) {
                solve(k, f, c, k->own, nown, hint, up, got);
                if (k->bad) return;
            }
        }
        k->need[2 * f] = got[0], k->need[2 * f + 1] = got[1];
    }
    double *at = k->at_key;   /* a key holds the most its spans each side need */
    for (i64 i = 0; i < 2 * count; i++) at[i] = 0.0;
    for (i64 f = 0; f < n; f++) {
        const double *v = k->need + 2 * f;
        i64 j = f / sub, is[2] = {j, k->loop ? (j + 1) % count : j + 1};
        for (int t = 0; t < (f % sub == 0 ? 1 : 2); t++)
            for (int x = 0; x < 2; x++)
                if (is[t] < count && fab(v[x]) > fab(at[2 * is[t] + x])) at[2 * is[t] + x] = v[x];
    }
    if (c)   /* under the first, both turns together at most CLEAR_TURN */
        for (i64 j = 0; j < count; j++) {
            double tn = k->num[N_TURN];
            if (tn == 0.0) {
                k->bad = 1;
                return;
            }
            double over = (fab(at[2 * j]) + fab(at[2 * j + 1])) / tn;
            if (over > 1.0) at[2 * j] = at[2 * j] / over, at[2 * j + 1] = at[2 * j + 1] / over;
        }
    for (i64 j = 0; j < count; j++) {   /* eased: the largest neighbour's turn, scaled down with its distance in keys */
        double best[2] = {0.0, 0.0};
        for (i64 d = -k->ease; d <= k->ease; d++) {
            i64 i = k->loop ? mod(j + d, count) : j + d;
            if (!(0 <= i && i < count)) continue;
            for (int x = 0; x < 2; x++) {
                double v = at[2 * i + x] * (1.0 - (double)(d < 0 ? -d : d) / ((double)k->ease + 1.0));
                if (fab(v) > fab(best[x])) best[x] = v;
            }
        }
        k->angle[2 * (count * c + j)] = best[0], k->angle[2 * (count * c + j) + 1] = best[1];
    }
}

/* out(share) of the drape: link c's key j turned back by share toward its unturned way; whether no point of the tail
 * under it comes nearer than was at a frame of window [w0, w1). */
static int draped(K *k, i64 c, i64 j, double share, const double *base, const double *up, i64 w0, i64 w1, i64 nown) {
    double *a = k->angle + 2 * (k->count * c + j);
    a[0] = base[0] - share * up[0], a[1] = base[1] - share * up[1];
    if (fab(a[0]) + fab(a[1]) > k->num[N_TURN]) return 0;
    for (i64 f = w0; f < w1; f++) {
        turned(k, f, k->L, 0, -1, k->Wt, k->Ot);
        short_(k, f, k->Wt, k->Ot, k->own, nown, k->g);
        if (k->bad) return 0;
        const double *was = k->was + k->nt * (f - w0);
        for (i64 i = 0; i < nown; i++)
            if (k->g[i] > was[i]) return 0;
    }
    return 1;
}

/* A held clip's drape (Step 2.193): each link under a lifted one turned back as far as the tail under it stays out. */
static void drape(K *k) {
    i64 n = k->n, sub = k->sub, count = k->count, L = k->L;
    double step = k->num[N_DRAPE_RATE] * k->num[N_LENGTH] / (double)(k->nk - 1 > 1 ? k->nk - 1 : 1);
    i64 rest = count;
    const double *last = k->X + 3 * k->ns * (n - 1);
    while (rest > 0) {   /* where the clip has come to rest: np.linalg.norm(...).max() <= CLEAR_REST */
        const double *x = k->X + 3 * k->ns * ((rest - 1) * sub);
        double m = 0.0;
        for (i64 p = 0; p < k->ns; p++) {   /* numpy's norm along the last axis (its squares summed in order) */
            double dx = x[3 * p] - last[3 * p], dy = x[3 * p + 1] - last[3 * p + 1], dz = x[3 * p + 2] - last[3 * p + 2];
            k->d[0] = sqr((dx * dx + dy * dy) + dz * dz);
            m = p ? nmax((double[2]){m, k->d[0]}, 2) : k->d[0];
        }
        if (!(m <= k->num[N_REST])) break;
        rest--;
    }
    double floor = k->num[N_TOL] - k->num[N_DRAPE];
    for (i64 c = 1; c < L; c++) {
        i64 nown = 0;
        for (i64 p = 0; p < k->nt; p++)
            if (k->owner[p] >= c) k->own[nown++] = p;
        for (i64 j = 0; j < count; j++) {
            k->has[j] = 0;
            double ups[2][64], up[2];
            for (int x = 0; x < 2; x++) {
                for (i64 a = 0; a < c; a++) ups[x][a] = k->angle[2 * (count * a + j) + x];
                up[x] = psum(ups[x], c);
            }
            if (fab(up[0]) + fab(up[1]) < 1e-3) continue;
            double base[2] = {k->angle[2 * (count * c + j)], k->angle[2 * (count * c + j) + 1]};
            i64 w0 = (j - 1) * sub + 1 > 0 ? (j - 1) * sub + 1 : 0, w1 = (j + 1) * sub < n ? (j + 1) * sub : n;
            for (i64 f = w0; f < w1; f++) {
                turned(k, f, L, 0, -1, k->Wt, k->Ot);
                short_(k, f, k->Wt, k->Ot, k->own, nown, k->was + k->nt * (f - w0));
                if (k->bad) return;
                double *was = k->was + k->nt * (f - w0);
                for (i64 i = 0; i < nown; i++) was[i] = was[i] != was[i] ? was[i] : was[i] > floor ? was[i] : floor;
            }
            double lo = 0.0, hi = !j || !k->has[j - 1] ? 1.0 : pmin(1.0, k->share[5 * (j - 1)] + step);
            if (draped(k, c, j, hi, base, up, w0, w1, nown)) {
                lo = hi;
            } else {
                for (i64 s = 0; s < k->steps; s++) {
                    double mid = (lo + hi) / 2.0;
                    if (draped(k, c, j, mid, base, up, w0, w1, nown))
                        lo = mid;
                    else
                        hi = mid;
                }
                draped(k, c, j, lo, base, up, w0, w1, nown);
            }
            if (k->bad) return;
            double *s = k->share + 5 * j;
            s[0] = lo, s[1] = base[0], s[2] = base[1], s[3] = up[0], s[4] = up[1];
            k->has[j] = 1;
        }
        for (i64 j = count - 2; j >= 0; j--) {   /* its share changes at most CLEAR_DRAPE_RATE, none at rest */
            if (!k->has[j] || !k->has[j + 1]) continue;
            double cap = k->share[5 * (j + 1)] + (j >= rest ? 0.0 : step), *s = k->share + 5 * j;
            if (s[0] > cap) {
                s[0] = cap;
                k->angle[2 * (count * c + j)] = s[1] - cap * s[3];
                k->angle[2 * (count * c + j) + 1] = s[2] - cap * s[4];
            }
        }
    }
}

/* What az_clear needs of work (doubles) and iwork (int64s) for these sizes, into need[0] and need[1]. */
API i64 az_clear_need(const i64 *z, i64 *need) {
    i64 L = z[Z_L], nk = z[Z_NK], loop = z[Z_LOOP], np = z[Z_NP], ns = z[Z_NS], nt = z[Z_NT], sub = z[Z_SUB];
    i64 n = (nk - 1) * sub + (loop ? 0 : 1), count = loop ? nk - 1 : nk;
    need[0] = n * np * 9 + 2 * n * ns * 3 + n * L * 7 + L * count * 2 + 2 * n + 2 * count + 5 * count +
              (2 * sub) * nt + 2 * L * 7 + L * 9 + nt * 3 + 3 * nt + 512 + 16;
    need[1] = z[Z_NB] + 4 * nt + 3 * ns + count + 2 * 257 + (n * ns + 7) / 8 + 16;
    return 0;
}

/* jiggle._clear of one clip past its glue: z its sizes (Z_*), num its numbers (N_*), slot each of the nb rig bones'
 * place among the np posed bones a frame (-1: none), link each link's bone, bone each link's jo, ra and its parent's
 * bind rotation (12 doubles), world and origin the posed bones at each frame (n x np x 4, n x np x 3), the skin's
 * (sB, sW, sU, sUN) and the tail's (tB, tW, tU, target, owner) points as the collider holds them, keys each link's
 * nk keys' five numbers; each link turned (turn[c] 1) its nk keys' six numbers into out (L x nk x 6). work and iwork
 * as az_clear_need. 0, or TWIN: the twin raises or a number is past the kernel. */
API i64 az_clear(const i64 *z, const double *num, const i64 *slot, const i64 *link, const double *bone,
                 const double *world, const double *origin, const i64 *sB, const double *sW, const double *sU,
                 const double *sUN, const i64 *tB, const double *tW, const double *tU, const double *target,
                 const i64 *owner, const double *keys, double *out, i64 *turn_, double *work, i64 *iwork) {
    K k = {0};
    k.L = z[Z_L], k.nk = z[Z_NK], k.loop = z[Z_LOOP], k.held = z[Z_HELD], k.np = z[Z_NP], k.ns = z[Z_NS];
    k.nt = z[Z_NT], k.nb = z[Z_NB], k.parent = z[Z_PARENT], k.pivot = z[Z_PIVOT], k.sub = z[Z_SUB];
    k.steps = z[Z_STEPS], k.ease = z[Z_EASE], k.hold = z[Z_HOLD];
    k.back = k.held && !k.loop;
    k.n = (k.nk - 1) * k.sub + (k.loop ? 0 : 1), k.count = k.loop ? k.nk - 1 : k.nk;
    i64 L = k.L, n = k.n, np = k.np, ns = k.ns, nt = k.nt, nb = k.nb, count = k.count;
    if (L < 1 || L > 64 || k.nk < 2 || k.sub < 2 || n < 1 || count < 1 || ns < 1 || nt < 1 || k.parent < 0 ||
        k.pivot < 0 || k.parent >= np || k.pivot >= np || k.ease < 0 || k.hold < 0 || k.steps < 0)
        return TWIN;
    for (i64 i = 0; i < 4 * ns; i++)
        if (sB[i] < 0 || sB[i] >= nb) return TWIN;
    for (i64 i = 0; i < 4 * nt; i++)
        if (tB[i] < 0 || tB[i] >= nb) return TWIN;
    k.num = num, k.bone = bone, k.world = world, k.origin = origin, k.sW = sW, k.sU = sU, k.sUN = sUN;
    k.tW = tW, k.tU = tU, k.target = target, k.keys = keys, k.slot = slot, k.sB = sB, k.tB = tB, k.owner = owner;
    double *w = work;
    k.R = w, w += n * np * 9;
    k.X = w, w += n * ns * 3;
    k.N = w, w += n * ns * 3;
    k.W0 = w, w += n * L * 4;
    k.O0 = w, w += n * L * 3;
    k.angle = w, w += L * count * 2;
    k.need = w, w += 2 * n;
    k.at_key = w, w += 2 * count;
    k.share = w, w += 5 * count;
    k.was = w, w += 2 * k.sub * nt;
    k.Wt = w, w += 4 * L;
    k.Ot = w, w += 3 * L;
    k.Wr = w, w += 4 * L;
    k.Or = w, w += 3 * L;
    k.Rl = w, w += 9 * L;
    k.P = w, w += 3 * nt;
    k.g = w, w += nt;
    k.d = w, w += nt;
    k.bspan = w;
    i64 *iw = iwork, *linkof = iw;
    iw += nb;
    k.own = iw, iw += nt;
    k.sel = iw, iw += nt;
    k.ok = iw, iw += nt;
    k.far = iw, iw += nt;
    k.keep = iw, iw += ns;
    k.order = iw, iw += ns;
    k.kb = iw, iw += ns;
    k.bucket = iw, iw += 257;
    k.fill = iw, iw += 257;
    k.has = iw, iw += count;
    k.done = (unsigned char *)iw;
    for (i64 i = 0; i < n * ns; i++) k.done[i] = 0;
    for (i64 b = 0; b < nb; b++) linkof[b] = -1;
    for (i64 c = 0; c < L; c++) {
        if (link[c] < 0 || link[c] >= nb) return TWIN;
        linkof[link[c]] = c;
    }
    k.linkof = linkof;
    for (i64 f = 0; f < n; f++) {   /* the frames: the body posed, its skin and the chain on its springs alone */
        for (i64 s = 0; s < np; s++) matrix(pw_of(&k, f, s), k.R + 9 * (np * f + s));
        i64 j = f / k.sub, q = f % k.sub;
        double u = (double)q / (double)k.sub;
        double *W = k.W0 + 4 * L * f, *Og = k.O0 + 3 * L * f;
        for (i64 c = 0; c < L; c++) {
            const double *a = keys + 5 * (k.nk * c + j), *zz = keys + 5 * (k.nk * c + (j + 1 < k.nk ? j + 1 : k.nk - 1));
            const double *b = bone + 12 * c;
            double f5[5], pw[4], po[3];
            for (int i = 0; i < 5; i++) f5[i] = a[i] + u * (zz[i] - a[i]);
            if (c) {
                for (int i = 0; i < 4; i++) pw[i] = W[4 * (c - 1) + i];
                for (int i = 0; i < 3; i++) po[i] = Og[3 * (c - 1) + i];
            } else {
                for (int i = 0; i < 4; i++) pw[i] = pw_of(&k, f, k.parent)[i];
                for (int i = 0; i < 3; i++) po[i] = po_of(&k, f, k.parent)[i];
            }
            double nn = sqr(f5[3] * f5[3] + f5[4] * f5[4] + 1.0);
            double v[4] = {0.0, f5[3] / nn, f5[4] / nn, 1.0 / nn}, local[4], t[3];
            qmul(b, v, local);
            qmul(local, b + 4, local);
            qmul(pw, local, W + 4 * c);
            turn(pw, f5, t);
            for (int i = 0; i < 3; i++) Og[3 * c + i] = po[i] + t[i];
        }
        double *o = k.X + 3 * ns * f;   /* jiggle._skinned of the skin: its positions (its normals as short asks) */
        for (i64 p = 0; p < ns; p++, o += 3) {
            o[0] = o[1] = o[2] = 0.0;
            for (int s = 0; s < 4; s++) {
                i64 bb = sB[4 * p + s];
                const double *r = slot[bb] >= 0 ? k.R + 9 * (np * f + slot[bb]) : ZERO;
                const double *og = slot[bb] >= 0 ? po_of(&k, f, slot[bb]) : ZERO, *uu = sU + 12 * p + 3 * s;
                double ww = sW[4 * p + s];
                for (int c = 0; c < 3; c++) {
                    double t = r[3 * c] * uu[0] + r[3 * c + 1] * uu[1] + r[3 * c + 2] * uu[2];
                    o[c] += ww * (og[c] + t);
                }
            }
        }
    }
    for (i64 i = 0; i < 2 * L * count; i++) k.angle[i] = 0.0;
    for (i64 c = 0; c < L; c++) {
        search(&k, c);
        if (k.bad) return TWIN;
    }
    if (k.back) {
        drape(&k);
        if (k.bad) return TWIN;
    }
    for (i64 c = 0; c < L; c++) {   /* a key it turns rewritten as the link's local translation and rotation */
        int any = 0;
        for (i64 j = 0; j < count; j++)
            if (k.angle[2 * (count * c + j)] != 0.0 || k.angle[2 * (count * c + j) + 1] != 0.0) any = 1;
        turn_[c] = any;
        if (!any) continue;
        double *o = out + 6 * k.nk * c;
        for (i64 j = 0; j < k.nk; j++) {
            for (int i = 0; i < 5; i++) o[6 * j + i] = keys[5 * (k.nk * c + j) + i];
            o[6 * j + 5] = 0.0;
        }
        const double *b = bone + 12 * c;
        for (i64 j = 0; j < count; j++) {
            if (!(k.angle[2 * (count * c + j)] != 0.0 || k.angle[2 * (count * c + j) + 1] != 0.0)) continue;
            turned(&k, j * k.sub, L, 0, -1, k.Wr, k.Or);
            if (k.bad) return TWIN;
            const double *pw = c ? k.Wr + 4 * (c - 1) : pw_of(&k, j * k.sub, k.parent);
            const double *po = c ? k.Or + 3 * (c - 1) : po_of(&k, j * k.sub, k.parent);
            double ijo[4], ipw[4], ira[4], q[4], rel[3], tl[3];
            qinv(b, ijo);
            qinv(pw, ipw);
            qinv(b + 4, ira);
            qmul(ipw, k.Wr + 4 * c, q);
            qmul(ijo, q, q);
            qmul(q, ira, q);
            if (!(q[3] > 0.0))
                for (int i = 0; i < 4; i++) q[i] = -q[i];
            if (q[3] == 0.0) return TWIN;
            for (int i = 0; i < 3; i++) rel[i] = k.Or[3 * c + i] - po[i];
            turn(ipw, rel, tl);
            double *e = o + 6 * j;
            e[0] = tl[0], e[1] = tl[1], e[2] = tl[2], e[3] = q[1] / q[3], e[4] = q[2] / q[3], e[5] = q[0] / q[3];
        }
        if (k.loop)
            for (int i = 0; i < 6; i++) o[6 * (k.nk - 1) + i] = o[i];
    }
    return 0;
}
