/* The decimator's collapse loop, compiled (D1009): tools/characters/decimate.py's decimate() past its _Work setup (its
 * offers, wedge_map, cost, allowed, rehome and collapse, the heap of collapses by cost then point indices), every
 * float operation its Python twin's in the twin's order on doubles, with no contraction, so the two cut the same LOD
 * bit for bit (tests/test_native.py). The twin's sets are this file's lists; no result depends on their order (each
 * set the twin iterates feeds a test, a maximum or a minimum with its ties broken by index), and a NaN, whose order
 * Python's heap and min would hold otherwise, answers 3 instead, and its caller runs the twin. No libm, no libc, no
 * allocation: the caller passes every buffer (a pool or heap it outgrows answers 1 or 2: it calls again with more).
 * Built by nativekit (C99, zig cc). */
#include <stdint.h>

#if defined(_WIN32)
#define API __declspec(dllexport)
#else
#define API __attribute__((visibility("default")))
#endif

typedef int64_t i64;
typedef unsigned char u8;

#define SKIN_K 0.5        /* decimate.SKIN_K */
#define MIN_DOT 0.2       /* decimate.MIN_DOT */
#define TINY 1e-24        /* decimate._TINY */
#define INF __builtin_inf()
#define LOCKED 1
#define BORDER 2
#define TWO 4
#define ALIVE 8           /* a point's flags (pf): locked, border, two-sided only, alive */

typedef union { double d; i64 i; } bits;

typedef struct {
    i64 n, nt, nv;
    const double *pos, *sw, *limit2;
    u8 *pf, *alive;
    const u8 *backed, *sbad;
    const i64 *vpoint, *twin, *so, *sb;
    i64 *tris, *tp;
    double *quad, *norm;
    i64 *head, *nxt, *prv;                 /* each point's fan: a list of nodes 3t + j */
    i64 *hhead, *hnext, *hprev, *hof;      /* each live triangle's held positions (a max_error's) */
    i64 *bhead, *bq, *bnext, bfree, bcap;  /* each point's blocked collapses */
    i64 *heap, hn, hcap;                   /* (cost bits, p, q) */
    i64 *tmark, *pmark, stamp;
    i64 *ta, *tb, *tc, *td, *te, *mv;
    i64 count;
    int fault;                             /* 1 blocked pool full, 2 heap full, 3 a NaN or a skin the twin refuses */
} W;

static double fab(double x) { return __builtin_fabs(x); }
static double sqr(double x) { return __builtin_elementwise_sqrt(x); }

/* sum() of n floats from Python's int start 0 (CPython's Neumaier compensation, added at the end if nonzero and
 * finite); 0.0 for none. */
static double psum(const double *x, i64 n) {
    if (!n) return 0.0;
    double f = 0.0 + x[0], c = 0.0;
    for (i64 i = 1; i < n; i++) {
        double t = f + x[i];
        if (fab(f) >= fab(x[i]))
            c += (f - t) + x[i];
        else
            c += (x[i] - t) + f;
        f = t;
    }
    if (c != 0.0 && __builtin_isfinite(c)) f += c;
    return f;
}

static int has(const W *w, i64 t, i64 x) { return w->tp[3 * t] == x || w->tp[3 * t + 1] == x || w->tp[3 * t + 2] == x; }

/* Whether corner j of t is its point's first (the node that holds t in that point's fan). */
static int first(const W *w, i64 t, int j) {
    for (int k = 0; k < j; k++)
        if (w->tp[3 * t + k] == w->tp[3 * t + j]) return 0;
    return 1;
}

static void link(W *w, i64 x, i64 node) {
    w->prv[node] = -1, w->nxt[node] = w->head[x];
    if (w->head[x] >= 0) w->prv[w->head[x]] = node;
    w->head[x] = node;
}

static void unlink(W *w, i64 x, i64 node) {
    if (w->prv[node] >= 0)
        w->nxt[w->prv[node]] = w->nxt[node];
    else
        w->head[x] = w->nxt[node];
    if (w->nxt[node] >= 0) w->prv[w->nxt[node]] = w->prv[node];
}

static i64 node_of(const W *w, i64 t, i64 x) {
    for (int j = 0; j < 3; j++)
        if (w->tp[3 * t + j] == x) return 3 * t + j;   /* the first corner at x */
    return -1;
}

static void sort(i64 *a, i64 n) {
    for (i64 i = 1; i < n; i++) {
        i64 v = a[i], j = i;
        while (j > 0 && a[j - 1] > v) a[j] = a[j - 1], j--;
        a[j] = v;
    }
}

/* neighbours(x), sorted, into out; their count. */
static i64 neighbours(W *w, i64 x, i64 *out) {
    i64 n = 0, s = ++w->stamp;
    for (i64 node = w->head[x]; node >= 0; node = w->nxt[node]) {
        i64 t = node / 3;
        for (int j = 0; j < 3; j++) {
            i64 y = w->tp[3 * t + j];
            if (y != x && w->pmark[y] != s) w->pmark[y] = s, out[n++] = y;
        }
    }
    sort(out, n);
    return n;
}

/* fan[p] & fan[q] into out (the triangles on the edge); their count. */
static i64 shared(const W *w, i64 p, i64 q, i64 *out) {
    i64 n = 0;
    for (i64 node = w->head[p]; node >= 0; node = w->nxt[node])
        if (has(w, node / 3, q)) out[n++] = node / 3;
    return n;
}

/* wedge_map: each wedge u of p and its v at q (pairs into wd), their count, or -1 for None. */
static int wedge_map(const W *w, i64 p, i64 q, i64 *wd) {
    if ((w->pf[p] & LOCKED) || !((w->pf[p] & ALIVE) && (w->pf[q] & ALIVE))) return -1;
    i64 on[2], non = 0;
    for (i64 node = w->head[p]; node >= 0; node = w->nxt[node])
        if (has(w, node / 3, q)) {
            if (non == 2) return -1;
            on[non++] = node / 3;
        }
    if (non != ((w->pf[p] & BORDER) ? 1 : 2)) return -1;
    int nw = 0;
    for (i64 k = 0; k < non; k++) {
        i64 u = -1, v = -1, t = on[k];
        for (int j = 0; j < 3; j++) {
            i64 c = w->tris[3 * t + j];
            if (w->vpoint[c] == p)
                u = c;
            else if (w->vpoint[c] == q)
                v = c;
        }
        int found = 0;
        for (int i = 0; i < nw; i++)
            if (wd[2 * i] == u) {
                if (wd[2 * i + 1] != v) return -1;
                found = 1;
            }
        if (!found) wd[2 * nw] = u, wd[2 * nw + 1] = v, nw++;
    }
    for (i64 node = w->head[p]; node >= 0; node = w->nxt[node]) {
        i64 t = node / 3;
        for (int j = 0; j < 3; j++) {
            i64 c = w->tris[3 * t + j];
            if (w->vpoint[c] != p) continue;
            int found = 0;
            for (int i = 0; i < nw; i++) found |= wd[2 * i] == c;
            if (!found) return -1;
        }
    }
    if (w->pf[p] & TWO)
        for (int i = 0; i < nw; i++)
            if (wd[2 * i + 1] < 0 || w->twin[wd[2 * i + 1]] < 0) return -1;
    return nw;
}

static double error_at(const double *q, const double *x) {
    if (q[10] <= 0.0) return 0.0;
    double X = x[0], Y = x[1], Z = x[2];
    double e = (q[0] * X * X + q[4] * Y * Y + q[7] * Z * Z + q[9]
                + 2.0 * (q[1] * X * Y + q[2] * X * Z + q[3] * X + q[5] * Y * Z + q[6] * Y + q[8] * Z));
    return (0.0 > e ? 0.0 : e) / q[10];
}

/* The L1 distance of two wedges' skins, Python's sum over their bones in order. */
static double skin_gap(W *w, i64 u, i64 v) {
    if (w->sbad[u] || w->sbad[v]) {
        w->fault = 3;
        return 0.0;
    }
    double terms[64];
    i64 a = w->so[u], ae = w->so[u + 1], b = w->so[v], be = w->so[v + 1], n = 0;
    if (ae - a + be - b > 64) {
        w->fault = 3;
        return 0.0;
    }
    while (a < ae || b < be) {
        if (b >= be || (a < ae && w->sb[a] < w->sb[b]))
            terms[n++] = fab(w->sw[a++] - 0.0);
        else if (a >= ae || w->sb[b] < w->sb[a])
            terms[n++] = fab(0.0 - w->sw[b++]);
        else
            terms[n++] = fab(w->sw[a++] - w->sw[b++]);
    }
    return psum(terms, n);
}

static double cost(W *w, i64 p, i64 q, const i64 *wd, int nw) {
    double qs[11];
    const double *qp = w->quad + 11 * p, *qq = w->quad + 11 * q, *xp = w->pos + 3 * p, *xq = w->pos + 3 * q;
    for (int i = 0; i < 11; i++) qs[i] = qp[i] + qq[i];
    double c = error_at(qs, xq);
    double d[3] = {xp[0] - xq[0], xp[1] - xq[1], xp[2] - xq[2]};
    double length2 = d[0] * d[0] + d[1] * d[1] + d[2] * d[2];
    if (length2 > 0.0) {
        double worst = 0.0;
        for (int i = 0; i < nw; i++) {
            double s = skin_gap(w, wd[2 * i], wd[2 * i + 1]);
            if (s > worst) worst = s;
        }
        c += SKIN_K * worst * length2;
    }
    return c;
}

/* The triangle t's points as a sorted set (p read as q where asked); their count. */
static int point_set(const W *w, i64 t, i64 p, i64 q, i64 *out) {
    int n = 0;
    for (int j = 0; j < 3; j++) {
        i64 x = w->tp[3 * t + j];
        if (x == p) x = q;
        int seen = 0;
        for (int k = 0; k < n; k++) seen |= out[k] == x;
        if (!seen) out[n++] = x;
    }
    sort(out, n);
    return n;
}

static int allowed(W *w, i64 p, i64 q) {
    i64 *on = w->ta, *np = w->tb, *nq = w->tc, *opp = w->td;
    i64 non = shared(w, p, q, on), nop = 0, s = ++w->stamp;
    for (i64 k = 0; k < non; k++)
        for (int j = 0; j < 3; j++) {
            i64 x = w->tp[3 * on[k] + j];
            if (x != p && x != q && w->pmark[x] != s) w->pmark[x] = s, opp[nop++] = x;
        }
    sort(opp, nop);
    i64 a = neighbours(w, p, np), b = neighbours(w, q, nq), nboth = 0, i = 0, j = 0;
    while (i < a && j < b) {   /* the sorted intersection, into np's front */
        if (np[i] < nq[j])
            i++;
        else if (nq[j] < np[i])
            j++;
        else
            np[nboth++] = np[i], i++, j++;
    }
    if (nboth != nop) return 0;
    for (i64 k = 0; k < nop; k++)
        if (np[k] != opp[k]) return 0;
    const double *pos = w->pos;
    for (i64 node = w->head[p]; node >= 0; node = w->nxt[node]) {
        i64 t = node / 3;
        if (has(w, t, q)) continue;   /* on the edge */
        i64 key[3], other[3];
        int nk = point_set(w, t, p, q, key);
        for (i64 nd = w->head[q]; nd >= 0; nd = w->nxt[nd]) {
            i64 u = nd / 3;
            if (has(w, u, p)) continue;
            int no = point_set(w, u, -1, -1, other), same = no == nk;
            for (int k = 0; same && k < nk; k++) same = key[k] == other[k];
            if (same) return 0;
        }
        const double *c3[3];
        for (int k = 0; k < 3; k++) {
            i64 x = w->tp[3 * t + k];
            c3[k] = pos + 3 * (x == p ? q : x);
        }
        const double *A = c3[0], *B = c3[1], *C = c3[2];
        double ux = B[0] - A[0], uy = B[1] - A[1], uz = B[2] - A[2];
        double vx = C[0] - A[0], vy = C[1] - A[1], vz = C[2] - A[2];
        double nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
        double nn = nx * nx + ny * ny + nz * nz;
        if (nn <= TINY) return 0;
        const double *o = w->norm + 3 * t;
        double ox = o[0], oy = o[1], oz = o[2];
        double no = ox * ox + oy * oy + oz * oz;
        if (no > TINY && ox * nx + oy * ny + oz * nz <= MIN_DOT * sqr(no * nn)) return 0;
    }
    return 1;
}

static double dot3(const double *a, const double *b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }

static double seg2(const double *x, const double *a, const double *b) {
    double ab[3] = {b[0] - a[0], b[1] - a[1], b[2] - a[2]}, ax[3] = {x[0] - a[0], x[1] - a[1], x[2] - a[2]};
    double ll = dot3(ab, ab), k;
    if (ll <= 0.0) {
        k = 0.0;
    } else {
        k = dot3(ax, ab) / ll;
        k = 0.0 > k ? 0.0 : k;
        k = 1.0 < k ? 1.0 : k;
    }
    double d[3] = {ax[0] - k * ab[0], ax[1] - k * ab[1], ax[2] - k * ab[2]};
    return dot3(d, d);
}

static double tri2(const double *x, const double *a, const double *b, const double *c) {
    double ab[3] = {b[0] - a[0], b[1] - a[1], b[2] - a[2]}, ac[3] = {c[0] - a[0], c[1] - a[1], c[2] - a[2]};
    double ax[3] = {x[0] - a[0], x[1] - a[1], x[2] - a[2]};
    double n[3] = {ab[1] * ac[2] - ab[2] * ac[1], ab[2] * ac[0] - ab[0] * ac[2], ab[0] * ac[1] - ab[1] * ac[0]};
    double nn = dot3(n, n);
    if (nn > TINY) {
        double d00 = dot3(ab, ab), d01 = dot3(ab, ac), d11 = dot3(ac, ac), d20 = dot3(ax, ab), d21 = dot3(ax, ac);
        double s = (d11 * d20 - d01 * d21) / nn;
        double t = (d00 * d21 - d01 * d20) / nn;
        if (s >= 0.0 && t >= 0.0 && s + t <= 1.0) {
            double h = dot3(ax, n);
            return h * h / nn;
        }
    }
    double m = seg2(x, a, b), e = seg2(x, b, c), f = seg2(x, c, a);
    m = e < m ? e : m;
    return f < m ? f : m;
}

/* The distance from x to triangle u: its corners moved p -> q where u is in p's fan but not on the edge. */
static double tri_at(W *w, const double *x, i64 u, i64 p, i64 q, int moved) {
    const double *c[3];
    for (int k = 0; k < 3; k++) {
        i64 y = w->tp[3 * u + k];
        c[k] = w->pos + 3 * (moved && y == p ? q : y);
    }
    double d = tri2(x, c[0], c[1], c[2]);
    if (d != d) w->fault = 3;
    return d;
}

static int less(double d, i64 u, double bd, i64 bu) { return d < bd || (d == bd && u < bu); }

/* rehome: each held position that moves into mv as (i, old, new) triples; their count, or -1 for None. */
static i64 rehome(W *w, i64 p, i64 q, double limit2) {
    i64 *near = w->ta, *wide = w->tb, *ring = w->tc, nn = 0, nwide = -1, nmv = 0;
    i64 s = ++w->stamp;   /* tmark[u] == s: u is near */
    for (i64 node = w->head[q]; node >= 0; node = w->nxt[node])
        if (!has(w, node / 3, p)) w->tmark[node / 3] = s, near[nn++] = node / 3;
    for (i64 node = w->head[p]; node >= 0; node = w->nxt[node])
        if (!has(w, node / 3, q)) w->tmark[node / 3] = s, near[nn++] = node / 3;
    for (i64 node = w->head[p]; node >= 0; node = w->nxt[node]) {
        i64 t = node / 3;
        int moved = !has(w, t, q);
        for (i64 i = w->hhead[t]; i >= 0; i = w->hnext[i]) {
            const double *x = w->pos + 3 * i;
            if (moved && tri_at(w, x, t, p, q, 1) <= limit2) continue;
            double bd = INF;
            i64 bu = -1;
            for (i64 k = 0; k < nn; k++) {
                i64 u = near[k];
                double d = tri_at(w, x, u, p, q, has(w, u, p));
                if (k == 0 || less(d, u, bd, bu)) bd = d, bu = u;
            }
            if (w->fault) return -1;
            if (bd > limit2) {
                if (nwide < 0) {
                    i64 nr = 0, ps = ++w->stamp;
                    for (i64 k = 0; k < nn; k++)
                        for (int j = 0; j < 3; j++) {
                            i64 y = w->tp[3 * near[k] + j];
                            if (y == p) y = q;
                            if (y != q && w->pmark[y] != ps) w->pmark[y] = ps, ring[nr++] = y;
                        }
                    i64 ws = ++w->stamp;
                    nwide = 0;
                    for (i64 k = 0; k < nr; k++)
                        for (i64 nd = w->head[ring[k]]; nd >= 0; nd = w->nxt[nd]) {
                            i64 u = nd / 3;
                            if (w->tmark[u] == s || w->tmark[u] == ws || (has(w, u, p) && has(w, u, q))) continue;
                            w->tmark[u] = ws, wide[nwide++] = u;
                        }
                    sort(wide, nwide);
                }
                for (i64 k = 0; k < nwide; k++) {
                    i64 u = wide[k];
                    double d = tri_at(w, x, u, p, q, 0);
                    if (less(d, u, bd, bu)) bd = d, bu = u;
                }
                if (w->fault) return -1;
                if (bd > limit2) return -1;
            }
            w->mv[3 * nmv] = i, w->mv[3 * nmv + 1] = t, w->mv[3 * nmv + 2] = bu, nmv++;
        }
    }
    return nmv;
}

static void hold_move(W *w, i64 i, i64 u) {
    i64 t = w->hof[i];
    if (t >= 0) {
        if (w->hprev[i] >= 0)
            w->hnext[w->hprev[i]] = w->hnext[i];
        else
            w->hhead[t] = w->hnext[i];
        if (w->hnext[i] >= 0) w->hprev[w->hnext[i]] = w->hprev[i];
    }
    w->hof[i] = u, w->hprev[i] = -1, w->hnext[i] = w->hhead[u];
    if (w->hhead[u] >= 0) w->hprev[w->hhead[u]] = i;
    w->hhead[u] = i;
}

static void normal(W *w, i64 t) {
    const double *a = w->pos + 3 * w->tp[3 * t], *b = w->pos + 3 * w->tp[3 * t + 1], *c = w->pos + 3 * w->tp[3 * t + 2];
    double u[3] = {b[0] - a[0], b[1] - a[1], b[2] - a[2]}, v[3] = {c[0] - a[0], c[1] - a[1], c[2] - a[2]};
    double *n = w->norm + 3 * t;
    n[0] = u[1] * v[2] - u[2] * v[1], n[1] = u[2] * v[0] - u[0] * v[2], n[2] = u[0] * v[1] - u[1] * v[0];
}

static void collapse(W *w, i64 p, i64 q, const i64 *wd, int nw, i64 nmv) {
    for (i64 k = 0; k < nmv; k++) hold_move(w, w->mv[3 * k], w->mv[3 * k + 2]);
    i64 *on = w->te, non = shared(w, p, q, on);
    for (i64 k = 0; k < non; k++) {
        i64 t = on[k];
        w->alive[t] = 0;
        w->count -= 1 + w->backed[t];
        for (int j = 0; j < 3; j++)
            if (first(w, t, j)) unlink(w, w->tp[3 * t + j], 3 * t + j);
    }
    i64 *rest = w->ta, nr = 0;
    for (i64 node = w->head[p]; node >= 0; node = w->nxt[node]) rest[nr++] = node / 3;
    for (i64 k = 0; k < nr; k++) {
        i64 t = rest[k], node = node_of(w, t, p);
        unlink(w, p, node);
        for (int j = 0; j < 3; j++) {
            i64 c = w->tris[3 * t + j];
            for (int i = 0; i < nw; i++)
                if (wd[2 * i] == c) {
                    c = wd[2 * i + 1];
                    break;
                }
            w->tris[3 * t + j] = c;
            if (w->tp[3 * t + j] == p) w->tp[3 * t + j] = q;
        }
        normal(w, t);
        link(w, q, node);
    }
    w->head[p] = -1;
    w->pf[p] &= ~ALIVE;
    for (int i = 0; i < 11; i++) w->quad[11 * q + i] += w->quad[11 * p + i];
}

static int heap_less(const i64 *a, const i64 *b) {
    bits x, y;
    x.i = a[0], y.i = b[0];
    if (x.d != y.d) return x.d < y.d;
    return a[1] < b[1] || (a[1] == b[1] && a[2] < b[2]);
}

static void heap_swap(i64 *a, i64 *b) {
    for (int k = 0; k < 3; k++) {
        i64 t = a[k];
        a[k] = b[k], b[k] = t;
    }
}

static void push(W *w, double c, i64 p, i64 q) {
    if (c != c) {
        w->fault = 3;
        return;
    }
    if (w->hn >= w->hcap) {
        w->fault = 2;
        return;
    }
    bits b;
    b.d = c;
    i64 k = w->hn++, *h = w->heap;
    h[3 * k] = b.i, h[3 * k + 1] = p, h[3 * k + 2] = q;
    while (k > 0) {
        i64 up = (k - 1) / 2;
        if (!heap_less(h + 3 * k, h + 3 * up)) break;
        heap_swap(h + 3 * k, h + 3 * up);
        k = up;
    }
}

static void pop(W *w, double *c, i64 *p, i64 *q) {
    i64 *h = w->heap;
    bits b;
    b.i = h[0];
    *c = b.d, *p = h[1], *q = h[2];
    w->hn--;
    if (!w->hn) return;
    h[0] = h[3 * w->hn], h[1] = h[3 * w->hn + 1], h[2] = h[3 * w->hn + 2];
    i64 k = 0;
    for (;;) {
        i64 l = 2 * k + 1, r = l + 1, m = k;
        if (l < w->hn && heap_less(h + 3 * l, h + 3 * m)) m = l;
        if (r < w->hn && heap_less(h + 3 * r, h + 3 * m)) m = r;
        if (m == k) break;
        heap_swap(h + 3 * k, h + 3 * m);
        k = m;
    }
}

static void block(W *w, i64 p, i64 q) {
    for (i64 b = w->bhead[p]; b >= 0; b = w->bnext[b])
        if (w->bq[b] == q) return;
    if (w->bfree < 0) {
        w->fault = 1;
        return;
    }
    i64 b = w->bfree;
    w->bfree = w->bnext[b];
    w->bq[b] = q, w->bnext[b] = w->bhead[p], w->bhead[p] = b;
}

/* blocked.pop(x): its collapses into out (sorted); their count. */
static i64 unblock(W *w, i64 x, i64 *out) {
    i64 n = 0;
    for (i64 b = w->bhead[x], nb; b >= 0; b = nb) {
        nb = w->bnext[b];
        out[n++] = w->bq[b];
        w->bnext[b] = w->bfree, w->bfree = b;
    }
    w->bhead[x] = -1;
    sort(out, n);
    return n;
}

static void drop(W *w, i64 x) {
    for (i64 b = w->bhead[x], nb; b >= 0; b = nb) nb = w->bnext[b], w->bnext[b] = w->bfree, w->bfree = b;
    w->bhead[x] = -1;
}

static void offer(W *w, i64 p, i64 q) {
    i64 wd[8];
    int nw = wedge_map(w, p, q, wd);
    if (nw < 0)
        block(w, p, q);
    else
        push(w, cost(w, p, q, wd, nw), p, q);
}

/* The words of scratch az_decimate takes for n points, nt triangles and its pool and heap. */
API i64 az_decimate_need(i64 n, i64 nt, i64 bcap, i64 hcap) { return 7 * n + 9 * nt + 3 * n + 5 * (3 * nt + 8) + nt + 2 * bcap + 3 * hcap; }

/* decimate()'s loop on its _Work's packing (decimate._compiled): tris, tp, alive, quad and norm updated in place;
 * 0, or 1 (its blocked pool) or 2 (its heap) outgrown, 3 the twin's (a NaN; a skin it refuses), 4 scratch short. */
API i64 az_decimate(i64 n, const double *pos, u8 *pf, i64 nv, const i64 *vpoint, const i64 *twin, const i64 *so,
                    const i64 *sb, const double *sw, const u8 *sbad, i64 nt, i64 *tris, i64 *tp, u8 *alive,
                    const u8 *backed, double *quad, double *norm, i64 count, double target, i64 limited,
                    double limit2, i64 *scratch, i64 nscratch, i64 bcap, i64 hcap) {
    if (nscratch < az_decimate_need(n, nt, bcap, hcap)) return 4;
    W w = {0};
    w.n = n, w.nt = nt, w.nv = nv, w.pos = pos, w.pf = pf, w.vpoint = vpoint, w.twin = twin, w.so = so, w.sb = sb;
    w.sw = sw, w.sbad = sbad, w.tris = tris, w.tp = tp, w.alive = alive, w.backed = backed, w.quad = quad;
    w.norm = norm, w.count = count;
    i64 *s = scratch;
    w.head = s, s += n;
    w.hhead = s, s += nt;
    w.hnext = s, s += n;
    w.hprev = s, s += n;
    w.hof = s, s += n;
    w.bhead = s, s += n;
    w.pmark = s, s += n;
    w.nxt = s, s += 3 * nt;
    w.prv = s, s += 3 * nt;
    w.tmark = s, s += nt;
    w.mv = s, s += 3 * n;
    w.ta = s, s += 3 * nt + 8;
    w.tb = s, s += 3 * nt + 8;
    w.tc = s, s += 3 * nt + 8;
    w.td = s, s += 3 * nt + 8;
    w.te = s, s += 3 * nt + 8;
    w.bq = s, s += bcap;
    w.bnext = s, s += bcap;
    w.heap = s, w.hcap = hcap;
    for (i64 x = 0; x < n; x++) w.head[x] = w.bhead[x] = w.hof[x] = w.hnext[x] = w.hprev[x] = -1, w.pmark[x] = 0;
    for (i64 t = 0; t < nt; t++) w.hhead[t] = -1, w.tmark[t] = 0;
    for (i64 b = 0; b < bcap; b++) w.bnext[b] = b + 1 < bcap ? b + 1 : -1;
    w.bfree = bcap ? 0 : -1;
    for (i64 t = 0; t < nt; t++)
        if (alive[t])
            for (int j = 0; j < 3; j++)
                if (first(&w, t, j)) link(&w, tp[3 * t + j], 3 * t + j);
    if (limited)   /* hold(): each position held by its lowest live triangle */
        for (i64 x = 0; x < n; x++) {
            i64 low = -1;
            for (i64 node = w.head[x]; node >= 0; node = w.nxt[node])
                if (low < 0 || node / 3 < low) low = node / 3;
            if (low >= 0) hold_move(&w, x, low);
        }
    for (i64 p = 0; p < n && !w.fault; p++)
        if ((pf[p] & ALIVE) && !(pf[p] & LOCKED)) {
            i64 *ring = w.te, nr = neighbours(&w, p, ring);
            for (i64 k = 0; k < nr && !w.fault; k++) offer(&w, p, ring[k]);
        }
    while (w.hn && (double)w.count > target && !w.fault) {
        double c;
        i64 p, q, wd[8];
        pop(&w, &c, &p, &q);
        if (!((pf[p] & ALIVE) && (pf[q] & ALIVE))) continue;
        int nw = wedge_map(&w, p, q, wd);
        if (nw < 0 || !allowed(&w, p, q)) {
            block(&w, p, q);
            continue;
        }
        double now = cost(&w, p, q, wd, nw);
        if (now > c * (1.0 + 1e-9) + 1e-30) {
            push(&w, now, p, q);
            continue;
        }
        i64 nmv = 0;
        if (limited && (nmv = rehome(&w, p, q, limit2)) < 0) {
            if (w.fault) break;
            block(&w, p, q);
            continue;
        }
        collapse(&w, p, q, wd, nw, nmv);
        drop(&w, p);   /* blocked.pop(p) */
        i64 *ring = w.td, nr = neighbours(&w, q, ring);
        for (i64 k = 0; k < nr; k++) offer(&w, q, ring[k]), offer(&w, ring[k], q);
        i64 *again = w.tc;
        for (i64 k = 0; k < nr && !w.fault; k++) {
            i64 x = ring[k], m = unblock(&w, x, again);
            for (i64 j = 0; j < m; j++)
                if (again[j] != q) offer(&w, x, again[j]);
        }
    }
    return w.fault;
}
