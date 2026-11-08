/* The mesh edit's ray kernel, compiled (D1009): tools/characters/mesh_edit.py's _ray_at, a round side's ray through a
 * point (its _exit, _exit_tapered, _shape, _across, _drape_exit, _drape_inside, _line_at and _smooth), every operation
 * its Python twin's in the twin's order on doubles, with no contraction, so the two agree bit for bit
 * (tests/test_native.py). A division by zero, which the twin raises, answers 2 instead, and its caller runs the twin.
 * No libm, no libc, no allocation. Built by nativekit (C99, zig cc). */
#include <stdint.h>

#if defined(_WIN32)
#define API __declspec(dllexport)
#else
#define API __attribute__((visibility("default")))
#endif

typedef int64_t i64;

/* A side's doubles (mesh_edit._ray_row packs them): its centre, frame (n, s, t), rays (the origin's s, n, t; a
 * drape's anchor n, t and tilt), inward sign, then its op's numbers, each optional one after a flag (1.0: given). */
enum {
    C0 = 0, FN = 3, FS = 6, FT = 9, RAYS = 12, ANCHOR = 15, SIGN = 18, RADIUS = 19, TAPER = 23, TAPER_IN, TAPER_BACK,
    TAPER_LOW = 27, BACK = 29, INNER, HAS_DRAPE, DRAPE, EASE = 37, HAS_IB, IB, BLEND = 42, HAS_GATE = 44, GATE,
    MIDLINE_N = 47, MIDLINE, HAS_BEHIND = 53, BEHIND, LINE_N = 57, HAS_WINDOW, WINDOW, LINE = 63
};

#define DRAPE_LOW 0.15                    /* mesh_edit.DRAPE_RISE */
#define DRAPE_HIGH 0.4
#define MIDLINE_SPAN 0.01                 /* mesh_edit.MIDLINE_SPAN */

static double fab(double x) { return __builtin_fabs(x); }
static double sqr(double x) { return __builtin_elementwise_sqrt(x); }   /* never errno, so never libm's sqrt */
static double sq(double x) { return x * x; }                            /* fdlibm.sq */

/* a / b, or *bad set where b is zero (the twin's ZeroDivisionError). */
static double dv(double a, double b, int *bad) {
    if (b == 0.0) {
        *bad = 1;
        return 0.0;
    }
    return a / b;
}

/* Python's `x or y` of floats: x unless it is zero. */
static double either(double x, double y) { return x != 0.0 ? x : y; }

/* Python's min(a, b): b only where it is less. */
static double least(double a, double b) { return b < a ? b : a; }

static double smooth(double x) { return x <= 0.0 ? 0.0 : x >= 1.0 ? 1.0 : x * x * (3.0 - 2.0 * x); }

static double dot(const double *a, const double *b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }

static double across_at(const double *S, int inward, double n, double t, int *bad) {
    double across = S[RADIUS], along = S[RADIUS + 1], up = S[RADIUS + 2], down = S[RADIUS + 3];
    if (inward && S[INNER] > 0.0) across = S[INNER];
    double taper = inward ? S[TAPER_IN] : S[TAPER];
    if (taper > 0.0 && t > 0.0) across *= 1.0 - taper * smooth(dv(t, up, bad));
    if (!inward) {
        double share = S[TAPER_BACK], reach = S[TAPER_BACK + 1];
        if (share > 0.0 && n < 0.0) across *= 1.0 - share * smooth(dv(-n, either(reach, either(S[BACK], along)), bad));
        share = S[TAPER_LOW], reach = S[TAPER_LOW + 1];
        if (share > 0.0 && t < 0.0) across *= 1.0 - share * smooth(dv(-t, either(reach, down), bad));
    }
    return across;
}

static double shape(const double *S, double sign, double s, double n, double t, int *bad) {
    double along = S[RADIUS + 1], up = S[RADIUS + 2], down = S[RADIUS + 3];
    if (S[BACK] > 0.0 && n < 0.0) along = S[BACK];
    double vert = t >= 0.0 ? up : down;
    double across = across_at(S, s * sign > 0.0, n, t, bad);
    double a = sq(dv(s, across, bad)), b = sq(dv(n, along, bad));
    return a + b + sq(dv(t, vert, bad));
}

static double exit_tapered(const double *S, double sign, const double *o, const double *u, int *bad) {
    if (!(shape(S, sign, o[0], o[1], o[2], bad) < 1.0) || *bad) return 0.0;
    double step = S[RADIUS];
    for (int i = 1; i < 4; i++) step = least(step, S[RADIUS + i]);
    step = step / 8.0;
    double lo = 0.0, hi = step;
    while (shape(S, sign, o[0] + hi * u[0], o[1] + hi * u[1], o[2] + hi * u[2], bad) < 1.0) {
        if (*bad) return 0.0;
        double next = hi + step;
        lo = hi, hi = next;
        if (hi > 4.0) return lo;
    }
    for (int i = 0; i < 40 && !*bad; i++) {
        double mid = (lo + hi) / 2.0;
        if (shape(S, sign, o[0] + mid * u[0], o[1] + mid * u[1], o[2] + mid * u[2], bad) < 1.0)
            lo = mid;
        else
            hi = mid;
    }
    return lo;
}

static double solve(const double *o, const double *u, double across, double along, double vert, int *bad) {
    double a = sq(dv(u[0], across, bad)) + sq(dv(u[1], along, bad));
    a = a + sq(dv(u[2], vert, bad));
    double b = dv(o[0] * u[0], across * across, bad) + dv(o[1] * u[1], along * along, bad);
    b = b + dv(o[2] * u[2], vert * vert, bad);
    double cc = sq(dv(o[0], across, bad)) + sq(dv(o[1], along, bad));
    cc = cc + sq(dv(o[2], vert, bad)) - 1.0;
    double disc = b * b - a * cc;
    if (!(disc >= 0.0)) return 0.0;
    return dv(-b + sqr(disc), a, bad);
}

static double exit_at(const double *S, double sign, const double *o, const double *u, int checked, int *bad) {
    double across = S[RADIUS], along = S[RADIUS + 1], up = S[RADIUS + 2], down = S[RADIUS + 3];
    if (S[TAPER] > 0.0 || S[TAPER_IN] > 0.0 || S[TAPER_BACK] > 0.0 || S[TAPER_LOW] > 0.0)
        return exit_tapered(S, sign, o, u, bad);
    if (!checked) {
        double vert = u[2] >= 0.0 ? up : down;
        double big_r = solve(o, u, across, along, vert, bad);
        if (S[INNER] > 0.0 && (o[0] + big_r * u[0]) * sign > 0.0) big_r = solve(o, u, S[INNER], along, vert, bad);
        return big_r;
    }
    int hi = u[2] >= 0.0, front = u[1] >= 0.0, inward = u[0] * sign > 0.0;
    double big_r = 0.0;
    for (int i = 0; i < 5 && !*bad; i++) {
        along = front || !(S[BACK] != 0.0) ? S[RADIUS + 1] : S[BACK];
        big_r = solve(o, u, inward && S[INNER] > 0.0 ? S[INNER] : across, along, hi ? up : down, bad);
        int g0 = o[2] + big_r * u[2] >= 0.0, g1 = o[1] + big_r * u[1] >= 0.0, g2 = (o[0] + big_r * u[0]) * sign > 0.0;
        if (g0 == hi && g1 == front && g2 == inward) break;
        hi = g0, front = g1, inward = g2;
    }
    return big_r;
}

/* _drape_inside: whether (s, n, t) is in the drape's hull, its place lam and the tangent's length. */
static int drape_inside(const double *S, double an, double at, double s, double n, double t, double tilt, double sign,
                        double *lam, double *length, int *bad) {
    *lam = 0.0, *length = 0.0;
    an += tilt * s;
    double across = S[RADIUS], along = S[RADIUS + 1], up = S[RADIUS + 2];
    if (S[INNER] > 0.0 && s * sign > 0.0) across = S[INNER];
    double k2 = 1.0 - sq(dv(s, across, bad));
    if (!(k2 > 0.0)) return 0;
    double k = sqr(k2);
    double big_a = along * k, big_b = up * k;
    double f = sq(dv(n, big_a, bad));
    if (f + sq(dv(t, big_b, bad)) <= 1.0) {
        *lam = 1.0;
        return 1;
    }
    double pn = dv(an, big_a, bad), pt = dv(at, big_b, bad);
    double d2 = pn * pn + pt * pt;
    if (!(d2 > 1.0)) return 0;
    double c1 = dv(1.0, d2, bad), c2 = dv(sqr(d2 - 1.0), d2, bad);
    double one0 = pn * c1 - c2 * pt, one1 = pt * c1 + c2 * pn, two0 = pn * c1 + c2 * pt, two1 = pt * c1 - c2 * pn;
    double tn = two1 > one1 ? two0 : one0, tt = two1 > one1 ? two1 : one1;
    tn = big_a * tn, tt = big_b * tt;
    if (!(an <= n && n <= tn && tn > an)) return 0;
    double l = dv(n - an, tn - an, bad);
    *lam = l;
    *length = sqr(sq(tn - an) + sq(tt - at));
    return t <= at + (tt - at) * l;
}

/* _drape_exit: where the ray leaves the drape's hull (*far), the place there and the tangent's length. */
static void drape_exit(const double *S, const double *o, const double *u, double big_r, double sign, double *far,
                       double *lam, double *length, int *bad) {
    double an = S[ANCHOR], at = S[ANCHOR + 1], tilt = S[ANCHOR + 2], l, len;
    double hi = dv(at - o[2], u[2], bad);
    if (u[1] - tilt * u[0] < 0.0) hi = least(hi, dv(an + tilt * o[0] - o[1], u[1] - tilt * u[0], bad));
    if (u[0] != 0.0) hi = least(hi, dv(S[RADIUS] * (u[0] > 0.0 ? 1.0 : -1.0) - o[0], u[0], bad));
    double step = big_r + 1e-6;
    *far = big_r, *lam = 1.0, *length = 0.0;
    if (!(hi > step) || !drape_inside(S, an, at, o[0] + step * u[0], o[1] + step * u[1], o[2] + step * u[2], tilt, sign,
                                      &l, &len, bad))
        return;
    double lo = step;
    for (int i = 0; i < 40 && !*bad; i++) {
        double mid = (lo + hi) / 2.0;
        if (drape_inside(S, an, at, o[0] + mid * u[0], o[1] + mid * u[1], o[2] + mid * u[2], tilt, sign, &l, &len, bad))
            lo = mid;
        else
            hi = mid;
    }
    drape_inside(S, an, at, o[0] + lo * u[0], o[1] + lo * u[1], o[2] + lo * u[2], tilt, sign, lam, length, bad);
    *far = lo;
}

static double line_at(const double *line, i64 m, double z) {
    if (!m) return 0.0;
    if (z <= line[0]) return line[1];
    for (i64 i = 0; i + 1 < m; i++) {
        double z0 = line[2 * i], y0 = line[2 * i + 1], z1 = line[2 * i + 2], y1 = line[2 * i + 3];
        if (z <= z1) return y0 + (y1 - y0) * (z - z0) / (z1 - z0);
    }
    return line[2 * m - 1];
}

/* _ray_at of the point p for the side S (an origin of its own unless o is given): 0 and out = u (3), r, R, k, w and
 * ramp; 1 for None (p at the origin); 2 where the twin raises (a division by zero). */
API i64 az_ray(const double *S, double p0, double p1, double p2, i64 given, double g0, double g1, double g2,
               double *out) {
    int bad = 0;
    const double *c = S + C0, *n = S + FN, *sa = S + FS, *ta = S + FT;
    double p[3] = {p0, p1, p2}, org[3], o[3];
    if (!given) {
        o[0] = S[RAYS], o[1] = S[RAYS + 1], o[2] = S[RAYS + 2];
        for (int i = 0; i < 3; i++) org[i] = c[i] + o[0] * sa[i] + o[1] * n[i] + o[2] * ta[i];
    } else {
        org[0] = g0, org[1] = g1, org[2] = g2;
        double d[3] = {org[0] - c[0], org[1] - c[1], org[2] - c[2]};
        o[0] = dot(d, sa), o[1] = dot(d, n), o[2] = dot(d, ta);
    }
    double q[3] = {p[0] - org[0], p[1] - org[1], p[2] - org[2]};
    double r = sqr(q[0] * q[0] + q[1] * q[1] + q[2] * q[2]);
    if (!(r > 0.0)) return 1;
    double uu[3] = {q[0] / r, q[1] / r, q[2] / r};
    double u[3] = {dot(uu, sa), dot(uu, n), dot(uu, ta)};
    double across = S[RADIUS], sign = S[SIGN];
    double big_r = exit_at(S, sign, o, u, (int)given, &bad);
    double ramp = 1.0;
    if (S[HAS_DRAPE] != 0.0 && u[2] > DRAPE_LOW && !bad) {
        double far, lam, length;
        drape_exit(S, o, u, big_r, sign, &far, &lam, &length, &bad);
        if (far > big_r) {
            double lo = S[DRAPE + 2], hi = S[DRAPE + 3];
            double fade = (1.0 - smooth(dv(dv(fab(o[0] + far * u[0]), across, &bad) - lo, hi - lo, &bad)))
                * smooth(dv(u[2] - DRAPE_LOW, DRAPE_HIGH - DRAPE_LOW, &bad));
            if (S[EASE] > 0.0) fade *= smooth(dv(lam * length, S[EASE], &bad));
            big_r += fade * (far - big_r);
            ramp = 1.0 - fade * (1.0 - smooth(lam));
        }
    }
    double k_up = S[BLEND], k_down = S[BLEND + 1];
    if (S[HAS_IB] != 0.0) {
        double kd = S[IB], x0 = S[IB + 1], x1 = S[IB + 2];
        double f = smooth(dv(fab(p[0]) - x0, x1 - x0, &bad));
        if (f < 1.0) k_down = kd + (k_down - kd) * f;
    }
    double k = k_down + (k_up - k_down) * (1.0 + u[2]) / 2.0;
    double w = S[HAS_GATE] != 0.0 ? smooth(dv(u[1] - S[GATE], S[GATE + 1] - S[GATE], &bad)) : 1.0;
    i64 mn = (i64)S[MIDLINE_N];
    if (mn) {
        const double *m = S + MIDLINE;
        double fade = (1.0 - smooth(dv(p[2] - m[0], m[1] - m[0], &bad))) * (1.0 - smooth(dv(fab(p[0]), m[2], &bad)));
        if (mn > 3) {
            double span = mn > 4 ? m[4] : MIDLINE_SPAN;
            fade *= 1.0 - smooth(dv(p[1] - m[3] + span, 2.0 * span, &bad));
        }
        w *= 1.0 - fade;
    }
    if (S[HAS_BEHIND] != 0.0) {
        double y = p[1] - line_at(S + LINE, (i64)S[LINE_N], p[2]);
        w *= S[BEHIND + 2] * (1.0 - smooth(dv(y - S[BEHIND], S[BEHIND + 1] - S[BEHIND], &bad)));
    }
    if (S[HAS_WINDOW] != 0.0) {
        const double *z = S + WINDOW;
        w *= smooth(dv(p[2] - z[0], z[1] - z[0], &bad)) * (1.0 - smooth(dv(p[2] - z[2], z[3] - z[2], &bad)));
    }
    if (bad) return 2;
    out[0] = uu[0], out[1] = uu[1], out[2] = uu[2], out[3] = r, out[4] = big_r, out[5] = k, out[6] = w, out[7] = ramp;
    return 0;
}

/* az_ray of n points p (3 doubles each) for the side S, from the origin g where given: each one's answer into code
 * (0, 1 or 2, as az_ray's) and its 8 doubles into out (code 0's). One call for a side's points (Pyodide's ctypes calls
 * cost far more than a ray in some browsers). */
API i64 az_rays(const double *S, i64 n, const double *p, i64 given, double g0, double g1, double g2, double *out,
                i64 *code) {
    for (i64 i = 0; i < n; i++) code[i] = az_ray(S, p[3 * i], p[3 * i + 1], p[3 * i + 2], given, g0, g1, g2, out + 8 * i);
    return 0;
}
