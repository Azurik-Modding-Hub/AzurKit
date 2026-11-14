/* The mesh edit's position steps, compiled (D1009, Step 4.55b): tools/characters/mesh_edit.py's fields (_effect over
 * a run of points: _displace's moves and _det's det J, az_fields), its relax ops' Taubin sweeps (_relax's, az_relax),
 * its beneath sides' nearest cloth crossing (_beneath's grid and its numpy read, az_beneath), the island UVs'
 * conjugate gradients (_conjugate, az_cg), a bind's reach mixes (_ReachMix.each, az_mix) and, Step 4.55c, the jiggle
 * bones' shares (_share_rows' pushes by _effect and rounds by mesh.c's az_ray, az_shares). Every operation is its
 * Python twin's, in the twin's order, on doubles, with no contraction, so the two agree bit for bit
 * (tests/test_native.py); a sum() of floats is Python's (CPython's Neumaier sum since 3.12, from its int start 0).
 * What the twin raises on (a division by zero, a cell of a direction not finite) answers an error code, and its
 * caller runs the twin, which raises it. No libm, no libc, no allocation: the caller passes every buffer. Built by
 * nativekit (C99, zig cc). */
#include <stdint.h>

#if defined(_WIN32)
#define API __declspec(dllexport)
#else
#define API __attribute__((visibility("default")))
#endif

typedef int64_t i64;

#define COPIES 1e-6        /* mesh_edit.COPIES */
#define CELLS 48.0         /* mesh_edit.BENEATH_CELLS */
#define SPAN 50            /* a direction's cell on each axis lies in -SPAN..SPAN (a unit vector's, floor(48 u) +- 1) */
#define SIDE (2 * SPAN + 1)

static double fab(double x) { return __builtin_fabs(x); }
static int finite(double x) { return __builtin_isfinite(x); }
static double root(double x) { return __builtin_elementwise_sqrt(x); }   /* never errno, so never libm's sqrt */

/* a / b, or *bad set where b is zero (the twin's ZeroDivisionError). */
static double dv(double a, double b, int *bad) {
    if (b == 0.0) {
        *bad = 1;
        return 0.0;
    }
    return a / b;
}

/* sum() of n >= 1 floats a stride apart: 0 + x[0], then Neumaier's compensation, added at the end only if nonzero and
 * finite. */
static double psum(const double *x, i64 n, i64 stride) {
    double f = 0.0 + x[0], c = 0.0;
    for (i64 i = 1; i < n; i++) {
        double e = x[i * stride], t = f + e;
        if (fab(f) >= fab(e))
            c += (f - t) + e;
        else
            c += (e - t) + f;
        f = t;
    }
    if (c != 0.0 && finite(c)) f += c;
    return f;
}

/* ---- the fields ---------------------------------------------------------------------------------------------------
 * A placed op's row (mesh_edit._field_row packs it, FIELD_ROW doubles): its kind (0 a smooth scale, 1 a cone scale,
 * 2 a push, 3 a taper), its centre, then its numbers: a scale's radius and factors; a push's frame (n, s, t), depth,
 * radius (in, out, up, down), fold and height; a taper's plateau, half, reach (r0, r1) and factors (x, y). */
enum { KIND = 0, CX = 1, NUM = 4, FIELD_ROW = 24 };

/* _effect's displacement at p of the op row R into disp, and (jac) its Jacobian's rows into J: 0 outside its region,
 * 1 inside; *bad set where the twin divides by zero. */
static int effect(const double *p, const double *R, int jac, double *disp, double J[3][3], int *bad) {
    int kind = (int)R[KIND];
    const double *c = R + CX, *v = R + NUM;
    double u[3] = {p[0] - c[0], p[1] - c[1], p[2] - c[2]};
    if (kind == 0 || kind == 1) {
        const double *r = v, *s = v + 3;
        double q[3] = {dv(u[0], r[0], bad), dv(u[1], r[1], bad), dv(u[2], r[2], bad)};
        if (*bad) return 0;
        double d2 = q[0] * q[0] + q[1] * q[1] + q[2] * q[2];
        if (!(d2 < 1.0)) return 0;
        double phi, grad[3];
        if (kind == 0) {
            double e = 1.0 - d2;
            phi = e * e;
            for (int j = 0; j < 3; j++) grad[j] = dv(-4.0 * e * q[j], r[j], bad);
        } else {
            double d = root(d2), w = 1.0 - d;
            phi = w * w;
            for (int j = 0; j < 3; j++) grad[j] = d == 0.0 ? 0.0 : dv(-2.0 * w * q[j], d * r[j], bad);
        }
        for (int i = 0; i < 3; i++) disp[i] = phi * (s[i] - 1.0) * u[i];
        if (jac)
            for (int i = 0; i < 3; i++)
                for (int j = 0; j < 3; j++) J[i][j] = (s[i] - 1.0) * ((i == j ? phi : 0.0) + u[i] * grad[j]);
        return 1;
    }
    if (kind == 2) {
        const double *n = v, *sa = v + 3, *ta = v + 6;
        double depth = v[9], r_in = v[10], r_out = v[11], r_up = v[12], r_down = v[13], fold = v[14], height = v[15];
        double un = u[0] * n[0] + u[1] * n[1] + u[2] * n[2];
        if (!(un > -depth)) return 0;
        double a = u[0] * sa[0] + u[1] * sa[1] + u[2] * sa[2], bt = u[0] * ta[0] + u[1] * ta[1] + u[2] * ta[2];
        double ra = fab(c[0]) > COPIES && a * sa[0] * c[0] < 0.0 ? r_in : r_out;
        double rv = bt > 0.0 ? r_up : r_down;
        double big_a = dv(a, ra, bad), big_b = dv(bt, rv, bad);
        if (*bad) return 0;
        double rho2 = big_a * big_a + big_b * big_b;
        if (!(rho2 < 1.0)) return 0;
        double g, dg;
        if (un >= 0.0) {
            g = 1.0, dg = 0.0;
        } else {
            double x = dv(un + depth, depth, bad);
            g = x * x * (3.0 - 2.0 * x), dg = dv(6.0 * x * (1.0 - x), depth, bad);
        }
        double e = 1.0 - rho2, db_a = 0.0, db_b = 0.0, b;
        if (rho2 == 0.0) {
            b = 1.0;
        } else {
            double rho = root(rho2);
            double hi = e * e * (3.0 - 2.0 * e), gap = 2.0 * e * (1.0 - e) * (1.0 - e);
            double k = fold * (1.0 - dv(big_b, rho, bad)) / 2.0;
            b = hi + k * gap;
            if (jac) {
                double r3 = 2.0 * rho2 * rho;
                double slope = 6.0 * e * (1.0 - e) + k * 2.0 * (1.0 - e) * (1.0 - 3.0 * e);
                db_a = -2.0 * big_a * slope + dv(fold * big_b * big_a, r3, bad) * gap;
                db_b = -2.0 * big_b * slope - dv(fold * big_a * big_a, r3, bad) * gap;
            }
        }
        if (*bad) return 0;
        double k = height * b * g;
        for (int i = 0; i < 3; i++) disp[i] = k * n[i];
        if (jac) {
            double ga = dv(db_a, ra, bad), gb = dv(db_b, rv, bad), grad[3];
            for (int j = 0; j < 3; j++) grad[j] = height * (g * (ga * sa[j] + gb * ta[j]) + b * dg * n[j]);
            for (int i = 0; i < 3; i++)
                for (int j = 0; j < 3; j++) J[i][j] = n[i] * grad[j];
        }
        return 1;
    }
    double plateau = v[0], half = v[1], r0 = v[2], r1 = v[3], f0 = v[4], f1 = v[5];
    double dz = u[2], az = fab(dz), big_w, dw;
    if (az <= plateau) {
        big_w = 1.0, dw = 0.0;
    } else if (az < plateau + half) {
        double kz = dv(az - plateau, half, bad), e = 1.0 - kz * kz;
        big_w = e * e, dw = dv(-4.0 * e * kz, half, bad) * (dz > 0 ? 1.0 : -1.0);
    } else {
        return 0;
    }
    double r = root(u[0] * u[0] + u[1] * u[1]), big_g, dgr;
    if (r <= r0) {
        big_g = 1.0, dgr = 0.0;
    } else if (r < r1) {
        double vv = dv(r - r0, r1 - r0, bad);
        big_g = 1.0 - vv * vv * (3.0 - 2.0 * vv), dgr = dv(-6.0 * vv * (1.0 - vv), r1 - r0, bad);
    } else {
        return 0;
    }
    if (*bad) return 0;
    double f[2] = {1.0 - (1.0 - f0) * big_w * big_g, 1.0 - (1.0 - f1) * big_w * big_g};
    disp[0] = (f[0] - 1.0) * u[0], disp[1] = (f[1] - 1.0) * u[1], disp[2] = 0.0;
    if (jac) {
        for (int i = 0; i < 2; i++) {
            double a = 1.0 - (i ? f1 : f0);
            double df[3] = {r > 0 ? dv(-a * big_w * dgr * u[0], r, bad) : 0.0,
                            r > 0 ? dv(-a * big_w * dgr * u[1], r, bad) : 0.0, -a * dw * big_g};
            for (int j = 0; j < 3; j++) J[i][j] = (i == j ? f[i] - 1.0 : 0.0) + u[i] * df[j];
        }
        J[2][0] = J[2][1] = J[2][2] = 0.0;
    }
    return 1;
}

/* Each of n points pts (3 each) under its ops (the rows idx[start[i]..start[i+1]) of nops rows): det 0, _displace's
 * point moved and whether any op holds it (4 doubles, 1.0 or 0.0) into out; det 1, _det's det J (1 double). 0, or 1
 * where an op is no row and 2 where the twin divides by zero (its caller runs the twin). */
API i64 az_fields(const double *rows, i64 nops, const i64 *start, const i64 *idx, const double *pts, i64 n, i64 det,
                  double *out) {
    for (i64 i = 0; i < n; i++) {
        const double *p = pts + 3 * i;
        double d[3], J[3][3], m[3][3] = {{1.0, 0.0, 0.0}, {0.0, 1.0, 0.0}, {0.0, 0.0, 1.0}};
        double dx = 0.0, dy = 0.0, dz = 0.0;
        int inside = 0, bad = 0;
        for (i64 k = start[i]; k < start[i + 1]; k++) {
            if (idx[k] < 0 || idx[k] >= nops) return 1;
            if (!effect(p, rows + FIELD_ROW * idx[k], (int)det, d, J, &bad)) {
                if (bad) return 2;
                continue;
            }
            if (bad) return 2;
            inside = 1;
            if (det) {
                for (int a = 0; a < 3; a++)
                    for (int b = 0; b < 3; b++) m[a][b] += J[a][b];
            } else {
                dx += d[0], dy += d[1], dz += d[2];
            }
        }
        if (det) {
            out[i] = m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
                     + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]);
        } else {
            out[4 * i] = p[0] + dx, out[4 * i + 1] = p[1] + dy, out[4 * i + 2] = p[2] + dz;
            out[4 * i + 3] = inside ? 1.0 : 0.0;
        }
    }
    return 0;
}

/* ---- the relax ------------------------------------------------------------------------------------------------------
 * _relax's sweeps of one op: passes times each of nsteps steps, each free point (free[i], an index into pos's npos
 * points, 3 doubles each) moved towards the mean of its neighbours (nbr[start[i]..start[i+1]), sum()'s over their
 * count) by the step times its weight, its x kept at 0 where mid[i]; every point of a step from the step before
 * (work: 3 nfree doubles). 0, or 1 where an index is out of range or a point has no neighbour (the twin's). */
API i64 az_relax(double *pos, i64 npos, const i64 *free, i64 nfree, const i64 *start, const i64 *nbr,
                 const double *weight, const i64 *mid, const double *steps, i64 nsteps, i64 passes, double *work) {
    for (i64 i = 0; i < nfree; i++) {
        if (free[i] < 0 || free[i] >= npos || start[i + 1] <= start[i]) return 1;
        for (i64 k = start[i]; k < start[i + 1]; k++)
            if (nbr[k] < 0 || nbr[k] >= npos) return 1;
    }
    for (i64 pass = 0; pass < passes; pass++) {
        for (i64 s = 0; s < nsteps; s++) {
            double step = steps[s];
            for (i64 i = 0; i < nfree; i++) {
                const double *q = pos + 3 * free[i];
                i64 count = start[i + 1] - start[i];
                double m[3];
                for (int j = 0; j < 3; j++) {   /* sum() over the neighbours in order, over their count */
                    double f = 0.0 + pos[3 * nbr[start[i]] + j], c = 0.0;
                    for (i64 k = 1; k < count; k++) {
                        double e = pos[3 * nbr[start[i] + k] + j], t = f + e;
                        if (fab(f) >= fab(e))
                            c += (f - t) + e;
                        else
                            c += (e - t) + f;
                        f = t;
                    }
                    if (c != 0.0 && finite(c)) f += c;
                    m[j] = f / (double)count;
                }
                double f = step * weight[i];
                work[3 * i] = mid[i] ? 0.0 : q[0] + f * (m[0] - q[0]);
                work[3 * i + 1] = q[1] + f * (m[1] - q[1]);
                work[3 * i + 2] = q[2] + f * (m[2] - q[2]);
            }
            for (i64 i = 0; i < nfree; i++)
                for (int j = 0; j < 3; j++) pos[3 * free[i] + j] = work[3 * i + j];
        }
    }
    return 0;
}

/* ---- beneath --------------------------------------------------------------------------------------------------------
 * A beneath side's cloth: ntri triangles' corners (9 doubles each) seen from its origin o, each read through the cells
 * of the unit directions to its corners (floor(48 d) on each axis, padded by one), as _beneath's grid. A cell's
 * number: (i + SPAN) * SIDE^2 + (j + SPAN) * SIDE + (k + SPAN). */

/* A triangle's direction cells (lo, hi on each axis): 0, 1 where a corner is at the origin (no cell: skipped), 2 where
 * a direction isn't finite or its cell is past SPAN (the twin's). */
static int span_of(const double *t, const double *o, i64 *lo, i64 *hi) {
    double d[3][3];
    for (int k = 0; k < 3; k++) {
        double v[3] = {t[3 * k] - o[0], t[3 * k + 1] - o[1], t[3 * k + 2] - o[2]};
        double n = root(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);
        if (!(n > 0)) return 1;
        for (int a = 0; a < 3; a++) d[k][a] = v[a] / n;
    }
    for (int a = 0; a < 3; a++) {
        double mn = d[0][a], mx = d[0][a];
        for (int k = 1; k < 3; k++) {   /* Python's min and max: the first of equals (one value either way) */
            if (d[k][a] < mn) mn = d[k][a];
            if (d[k][a] > mx) mx = d[k][a];
        }
        double x = mn * CELLS, y = mx * CELLS;
        if (!finite(x) || !finite(y) || x < -SPAN || y > SPAN) return 2;
        i64 fl = (i64)x, fh = (i64)y;   /* floor: truncation, one less below zero where not whole */
        if ((double)fl > x) fl -= 1;
        if ((double)fh > y) fh -= 1;
        lo[a] = fl - 1, hi[a] = fh + 1;
        if (lo[a] < -SPAN || hi[a] > SPAN) return 2;
    }
    return 0;
}

/* How many cell entries the cloth makes (az_beneath's entries), its count by cell into cells (SIDE^3 + 1 words,
 * zeroed here); -1 where the twin answers (span_of's 2). */
API i64 az_beneath_need(const double *corners, i64 ntri, const double *o, i64 *cells) {
    for (i64 c = 0; c <= (i64)SIDE * SIDE * SIDE; c++) cells[c] = 0;
    i64 total = 0;
    for (i64 t = 0; t < ntri; t++) {
        i64 lo[3], hi[3];
        int got = span_of(corners + 9 * t, o, lo, hi);
        if (got == 2) return -1;
        if (got) continue;
        for (i64 i = lo[0]; i <= hi[0]; i++)
            for (i64 j = lo[1]; j <= hi[1]; j++)
                for (i64 k = lo[2]; k <= hi[2]; k++) {
                    cells[(i + SPAN) * SIDE * SIDE + (j + SPAN) * SIDE + (k + SPAN) + 1] += 1;
                    total += 1;
                }
    }
    return total;
}

/* The nearest crossing past the origin of each of nq rays (unit directions u, 3 each, in cells cell, 3 each) with the
 * cloth's triangles read through its cell (_beneath's numpy: each triangle's edges from its first corner, that corner
 * to the origin and their cross, the hit's tests), into near (NaN: none), from az_beneath_need's counts in cells
 * (made its starts here) and entries (its total words); table: 12 ntri doubles. 0. */
API i64 az_beneath(const double *corners, i64 ntri, const double *o, i64 *cells, i64 *entries, double *table,
                   const double *u, const i64 *cell, i64 nq, double *near) {
    const i64 all = (i64)SIDE * SIDE * SIDE;
    for (i64 c = 0; c < all; c++) cells[c + 1] += cells[c];
    for (i64 t = 0; t < ntri; t++) {
        const double *c = corners + 9 * t;
        double *T = table + 12 * t;
        for (int a = 0; a < 3; a++) {
            T[a] = c[3 + a] - c[a];          /* e1 */
            T[3 + a] = c[6 + a] - c[a];      /* e2 */
            T[6 + a] = o[a] - c[a];          /* tv */
        }
        T[9] = T[7] * T[2] - T[8] * T[1];    /* qv = tv x e1 */
        T[10] = T[8] * T[0] - T[6] * T[2];
        T[11] = T[6] * T[1] - T[7] * T[0];
        i64 lo[3], hi[3];
        if (span_of(c, o, lo, hi)) continue;
        for (i64 i = lo[0]; i <= hi[0]; i++)
            for (i64 j = lo[1]; j <= hi[1]; j++)
                for (i64 k = lo[2]; k <= hi[2]; k++) entries[cells[(i + SPAN) * SIDE * SIDE + (j + SPAN) * SIDE + (k + SPAN)]++] = t;
    }
    for (i64 c = all; c > 0; c--) cells[c] = cells[c - 1];   /* the fill moved each start to its end */
    cells[0] = 0;
    for (i64 q = 0; q < nq; q++) {
        const double *w = u + 3 * q;
        const i64 *ci = cell + 3 * q;
        near[q] = __builtin_nan("");
        if (ci[0] < -SPAN || ci[0] > SPAN || ci[1] < -SPAN || ci[1] > SPAN || ci[2] < -SPAN || ci[2] > SPAN) continue;
        i64 at = (ci[0] + SPAN) * SIDE * SIDE + (ci[1] + SPAN) * SIDE + (ci[2] + SPAN);
        int any = 0;
        double best = 0.0;
        for (i64 e = cells[at]; e < cells[at + 1]; e++) {
            const double *T = table + 12 * entries[e];
            double a1 = T[0], a2 = T[1], a3 = T[2], b1 = T[3], b2 = T[4], b3 = T[5], t1 = T[6], t2 = T[7], t3 = T[8];
            double q1 = T[9], q2 = T[10], q3 = T[11];
            double p1 = w[1] * b3 - w[2] * b2, p2 = w[2] * b1 - w[0] * b3, p3 = w[0] * b2 - w[1] * b1;
            double det = a1 * p1 + a2 * p2 + a3 * p3;
            double x = (t1 * p1 + t2 * p2 + t3 * p3) / det;
            double y = (w[0] * q1 + w[1] * q2 + w[2] * q3) / det;
            double dist = (b1 * q1 + b2 * q2 + b3 * q3) / det;
            if (fab(det) >= 1e-12 && x >= 0.0 && x <= 1.0 && y >= 0.0 && x + y <= 1.0 && dist > 0.0) {
                if (!any || dist < best) best = dist;
                any = 1;
            }
        }
        if (any) near[q] = best;
    }
    return 0;
}

/* ---- the island UVs' conjugate gradients --------------------------------------------------------------------------
 * _conjugate's: row k of A q is diag[k] q[k] plus sum() of w q[j] over its entries (cols, w from start[k] to
 * start[k + 1]), Neumaier's term by term; the dot products sum() over their terms in order and the rest elementwise,
 * from x (n, in and out) until r.r is no longer above tol times its first or is 0, d.Ad is no longer above 0, or after
 * maxit steps. work: 4 n doubles. 0, or 1 where an entry's column is out of range. */
static void apply(i64 n, const i64 *start, const i64 *cols, const double *w, const double *diag, const double *q,
                  double *out) {
    for (i64 k = 0; k < n; k++) {
        double f = 0.0, c = 0.0;
        if (start[k + 1] > start[k]) {
            f = 0.0 + w[start[k]] * q[cols[start[k]]];
            for (i64 e = start[k] + 1; e < start[k + 1]; e++) {
                double t = w[e] * q[cols[e]], s = f + t;
                c = c + (fab(f) >= fab(t) ? (f - s) + t : (t - s) + f);
                f = s;
            }
        }
        out[k] = diag[k] * q[k] + (c != 0.0 && finite(c) ? f + c : f);
    }
}

static double dotsum(const double *a, const double *b, i64 n, double *tmp) {
    for (i64 k = 0; k < n; k++) tmp[k] = a[k] * b[k];
    return psum(tmp, n, 1);
}

API i64 az_cg(i64 n, const i64 *start, const i64 *cols, const double *w, const double *diag, const double *b,
              double *x, double tol, i64 maxit, double *work) {
    if (n <= 0) return 0;
    for (i64 e = 0; e < start[n]; e++)
        if (cols[e] < 0 || cols[e] >= n) return 1;
    double *r = work, *d = work + n, *ad = work + 2 * n, *tmp = work + 3 * n;
    apply(n, start, cols, w, diag, x, ad);
    for (i64 k = 0; k < n; k++) r[k] = b[k] - ad[k], d[k] = r[k];
    double rr = dotsum(r, r, n, tmp), stop = rr * tol;
    for (i64 it = 0; it < maxit; it++) {
        if (!(rr > stop) || rr == 0.0) break;
        apply(n, start, cols, w, diag, d, ad);
        double dad = dotsum(d, ad, n, tmp);
        if (!(dad > 0.0)) break;
        double alpha = rr / dad;
        for (i64 k = 0; k < n; k++) x[k] = x[k] + alpha * d[k], r[k] = r[k] - alpha * ad[k];
        double rr2 = dotsum(r, r, n, tmp), beta = rr2 / rr;
        rr = rr2;
        for (i64 k = 0; k < n; k++) d[k] = r[k] + beta * d[k];
    }
    return 0;
}

/* ---- the binds' reach mix ----------------------------------------------------------------------------------------
 * _ReachMix.at of each of nq points q (3 each), read through its cell's rows (rows[start[c]..start[c + 1]) of the
 * cell c = cell[i], ascending): of those within the reach (d = ux ux + uy uy + uz uz < r2, from the rows' points at,
 * 3 each), each weighed (1 - d / r2)^2, the weights' sum and each bone's sum of a weight times the row's skin weight
 * (weights: nrows x nb), each in row order from 0.0 (numpy's cumsum), over the weights' sum; a bone held where a row
 * within the reach has it (has: nrows x nb bytes). Into out (nq x nb doubles: a held bone's share), held (nq x nb
 * bytes) and got (nq bytes: 1 a mix, 0 none within the reach). 0, or 1 where an index is out of range. */
API i64 az_mix(const double *at, i64 nrows, const double *weights, const unsigned char *has, i64 nb, const i64 *start,
               const i64 *rows, i64 ncells, const i64 *cell, const double *q, i64 nq, double r2, double *out,
               unsigned char *held, unsigned char *got) {
    for (i64 c = 0; c < ncells; c++)
        for (i64 e = start[c]; e < start[c + 1]; e++)
            if (rows[e] < 0 || rows[e] >= nrows) return 1;
    for (i64 i = 0; i < nq; i++)
        if (cell[i] < 0 || cell[i] >= ncells) return 1;
    for (i64 i = 0; i < nq; i++) {
        const double *p = q + 3 * i;
        double *o = out + nb * i, total = 0.0;
        unsigned char *h = held + nb * i;
        for (i64 b = 0; b < nb; b++) o[b] = 0.0, h[b] = 0;
        int any = 0;
        for (i64 e = start[cell[i]]; e < start[cell[i] + 1]; e++) {
            i64 r = rows[e];
            double ux = at[3 * r] - p[0], uy = at[3 * r + 1] - p[1], uz = at[3 * r + 2] - p[2];
            double d = ux * ux + uy * uy + uz * uz;
            if (!(d < r2)) continue;
            double x = 1.0 - d / r2, w = x == 1.0 ? 1.0 : x * x;   /* fdlibm.pow(x, 2.0) */
            total = total + w;
            for (i64 b = 0; b < nb; b++) {
                o[b] = o[b] + w * weights[nb * r + b];
                if (has[nb * r + b]) h[b] = 1;
            }
            any = 1;
        }
        got[i] = (unsigned char)any;
        if (any)
            for (i64 b = 0; b < nb; b++) o[b] = o[b] / total;
    }
    return 0;
}

/* ---- the jiggle bones' shares ---------------------------------------------------------------------------------------
 * shares_each's _share_rows over n points pts (3 each), width names: each point's share of each name, from 0.0, the
 * larger kept (Python's max(best, x): x only where it is greater), first by each push side s (FIELD_ROW doubles at
 * push + FIELD_ROW s, its names pnames[pstart[s]..pstart[s + 1])), where it holds the point and its height (the row's
 * last number) isn't 0: |its move| / |height|; then by each round side r (az_ray's row at rows + rstart[r], its names
 * qnames[qstart[r]..qstart[r + 1]), its pair's flag, bridge and origin at pair + 5 r): _round_share's, a pair's from
 * the point's ray and its mirror's (x negated) from its origin, 0.5 where either is at the origin, else w ramp split
 * smooth((R + k - r) / 2k), its R the two forms' smooth maximum over the bridge; a side's 1.0 at its origin, else
 * w ramp smooth((R + k - r) / 2k). Into out (n x width). 0; 1 where a name is out of range; 2 where the twin divides
 * by zero (its caller runs the twin). */
i64 az_ray(const double *S, double p0, double p1, double p2, i64 given, double g0, double g1, double g2, double *out);

static double smooth(double x) { return x <= 0.0 ? 0.0 : x >= 1.0 ? 1.0 : x * x * (3.0 - 2.0 * x); }   /* _smooth */

static double smooth_max(double a, double b, double k) {   /* _smooth_max */
    double m = a > b ? a : b;
    if (k > 0.0) {
        double h = (k - fab(a - b)) / k;
        if (h > 0.0) m += h * h * k / 4.0;
    }
    return m;
}

API i64 az_shares(const double *pts, i64 n, i64 width, const double *push, i64 npush, const i64 *pstart,
                  const i64 *pnames, const double *rows, const i64 *rstart, i64 nround, const double *pair,
                  const i64 *qstart, const i64 *qnames, double pair_split, double *out) {
    for (i64 s = 0; s < npush; s++)
        for (i64 e = pstart[s]; e < pstart[s + 1]; e++)
            if (pnames[e] < 0 || pnames[e] >= width) return 1;
    for (i64 s = 0; s < nround; s++)
        for (i64 e = qstart[s]; e < qstart[s + 1]; e++)
            if (qnames[e] < 0 || qnames[e] >= width) return 1;
    for (i64 i = 0; i < n; i++) {
        const double *p = pts + 3 * i;
        double *best = out + width * i, d[3], J[3][3], mine[8], other[8];
        int bad = 0;
        for (i64 c = 0; c < width; c++) best[c] = 0.0;
        for (i64 s = 0; s < npush; s++) {
            const double *R = push + FIELD_ROW * s;
            int in = effect(p, R, 0, d, J, &bad);
            if (bad) return 2;
            double height = R[NUM + 15];
            if (!in || height == 0.0) continue;
            double x = root(d[0] * d[0] + d[1] * d[1] + d[2] * d[2]) / fab(height);
            for (i64 e = pstart[s]; e < pstart[s + 1]; e++)
                if (x > best[pnames[e]]) best[pnames[e]] = x;
        }
        for (i64 s = 0; s < nround; s++) {
            const double *S = rows + rstart[s], *pr = pair + 5 * s;
            double x;
            if (pr[0] != 0.0) {
                i64 a = az_ray(S, p[0], p[1], p[2], 1, pr[2], pr[3], pr[4], mine);
                i64 b = az_ray(S, -p[0], p[1], p[2], 1, pr[2], pr[3], pr[4], other);
                if (a == 2 || b == 2) return 2;
                if (a == 1 || b == 1) {
                    x = 0.5;
                } else {
                    double r = mine[3], own = mine[4], k = mine[5], w = mine[6], ramp = mine[7], bridge = pr[1];
                    double big_r = smooth_max(own, other[4], bridge);
                    double split = smooth(0.5 + dv(own - other[4], 2.0 * (pair_split > bridge ? pair_split : bridge),
                                                   &bad));
                    x = w * ramp * split * smooth(dv(big_r + k - r, 2.0 * k, &bad));
                }
            } else {
                i64 a = az_ray(S, p[0], p[1], p[2], 0, 0.0, 0.0, 0.0, mine);
                if (a == 2) return 2;
                x = a == 1 ? 1.0 : mine[6] * mine[7] * smooth(dv(mine[4] + mine[5] - mine[3], 2.0 * mine[5], &bad));
            }
            if (bad) return 2;
            for (i64 e = qstart[s]; e < qstart[s + 1]; e++)
                if (x > best[qnames[e]]) best[qnames[e]] = x;
        }
    }
    return 0;
}
