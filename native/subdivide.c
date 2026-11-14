/* The subdivision's split loop, compiled (D1009, Step 4.55d): tools/characters/mesh_edit.py's _subdivide past its
 * setup (its twin, _split_twin, the loop as it was): every triangle linked to its welded edges, the marks (a region
 * holds its centre and selects its corners and its longest edge in the final shape passes the region's edge, or a
 * hem's open edge does), the heap of the longest first, Rivara's longest-edge propagation from each, each split at its
 * edge's midpoint (PN's where smooth) unless a field or round op tears it or an old point lies there, its copies'
 * skins, normals and UVs, and at the end each open edge and its least triangle. A point's final position is the
 * twin's final(): _displace by positions.c's fields (az_moved), then each round's sides the point selects without
 * their bridge (_round_one: a pair's one ray, else each side's move, weighted by its squared length), by mesh.c's
 * az_ray. Every operation is its Python twin's, in the twin's order, on doubles, with no contraction, so the two agree
 * bit for bit (tests/test_native.py): a sum() of floats is CPython's Neumaier sum, a max() or min() keeps its first, a
 * tuple compares item by item and the heap is heapq's (its keys never NaN here). The twin's dicts and sets are lists
 * here, as no answer reads their order (an edge's triangles are sorted first, each time). What the twin raises on (a
 * division by zero, a float32 overflow, a skin with no weight, past SUBDIVIDE_MAX), a NaN key and an edge of more
 * than LIST triangles answer FAIL, and the caller runs the twin; ROOM where a buffer is short, the state kept: the
 * caller grows them and calls again, and the loop goes on where it stopped (a split checks its room before it writes).
 * No libm, no libc, no allocation: the caller passes every buffer. Built by nativekit (C99, zig cc). */
#include <stdint.h>

#if defined(_WIN32)
#define API __declspec(dllexport)
#else
#define API __attribute__((visibility("default")))
#endif

typedef int64_t i64;
typedef uint64_t u64;

i64 az_ray(const double *S, double p0, double p1, double p2, i64 given, double g0, double g1, double g2, double *out);
i64 az_moved(const double *rows, const i64 *idx, i64 n, const double *p, double *out);

enum { DONE = 0, FAIL = 1, ROOM = 5 };
enum { PH_START = 0, PH_POP = 1, PH_WALK = 2, PH_END = 3 };
#define LIST 32     /* the most triangles one welded edge holds here (more: the twin's) */
#define SKIN 16     /* the most bones a merged skin holds here */
#define SIDES 8     /* the most sides a round op has here */
#define STACK 64    /* the walk's stack: room for mesh_edit.LEPP_MAX */

/* The caller's buffers, by their place in its address list (int64 each). */
enum {
    P_WID, P_GS, P_HEAVY, P_SSTART, P_SBONE, P_SW, P_NRM, P_UV, P_BASE, P_FIN, P_HAVE,   /* by vertex */
    P_WPOS, P_WNRM, P_REP, P_ADJ, P_HASH,                                               /* by welded point */
    P_TRI, P_VER,                                                                       /* by triangle */
    P_EX, P_EY, P_EREF, P_EHEAD, P_ENEXT, P_NTRI, P_NNEXT,                              /* the edges' lists */
    P_HKEY, P_HT, P_HVER,                                                               /* the heap */
    P_REG, P_SEL, P_CLS, P_FSTART, P_FIDX, P_ROWS, P_RSTART, P_RROUND, P_RSIDE,         /* the regions, the ops */
    P_SBASE, P_SROW, P_SPAIR, P_SBRIDGE, P_SORIGIN, P_RAYS,                             /* the round sides */
    P_STACK, P_OPEN, NP
};
/* Its numbers (int64 each): the counts, the rooms, the loop's place. */
enum {
    S_PHASE, S_NV0, S_NV, S_CAPV, S_NW, S_CAPW, S_NT, S_CAPT, S_NE, S_CAPE, S_NN, S_CAPN, S_FREE, S_NH, S_CAPH, S_NSK,
    S_CAPSK, S_HCAP, S_REHASH, S_NREG, S_HEMS, S_SMOOTHS, S_NG, S_NB, S_NROUNDS, S_ADDED, S_MAXADD, S_LEPP, S_T0,
    S_GOTSM, S_DEPTH, S_NOPEN, NS
};
enum { D_STRETCH, D_TORN, D_SLIVER, D_GOTLEN, ND };

typedef struct {
    i64 *s;
    double *d;
    i64 *wid, *gs, *heavy, *sstart, *sbone, *have, *rep, *adj, *hash, *tri, *ver, *ex, *ey, *eref, *ehead, *enext;
    i64 *ntri, *nnext, *ht, *hver, *stack, *open;
    double *sw, *nrm, *uv, *base, *fin, *wpos, *wnrm, *hkey;
    const double *reg, *rows, *sbridge, *sorigin, *rays;
    const i64 *sel, *cls, *fstart, *fidx, *rstart, *rround, *rside, *sbase, *srow, *spair;
    i64 touch[2 * LIST], ntouch;
} K;

static double fab(double x) { return __builtin_fabs(x); }
static double root(double x) { return __builtin_elementwise_sqrt(x); }   /* never errno, so never libm's sqrt */
static i64 lo2(i64 a, i64 b) { return a < b ? a : b; }
static i64 hi2(i64 a, i64 b) { return a < b ? b : a; }

/* sum() of n >= 1 floats: 0 + x[0], then Neumaier's compensation, added at the end only if nonzero and finite. */
static double psum(const double *x, i64 n) {
    double f = 0.0 + x[0], c = 0.0;
    for (i64 i = 1; i < n; i++) {
        double e = x[i], t = f + e;
        if (fab(f) >= fab(e))
            c += (f - t) + e;
        else
            c += (e - t) + f;
        f = t;
    }
    if (c != 0.0 && __builtin_isfinite(c)) f += c;
    return f;
}

static double dot(const double *a, const double *b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }
static double norm(const double *a) { return root(a[0] * a[0] + a[1] * a[1] + a[2] * a[2]); }
static double dist(const double *a, const double *b) {   /* _norm(_sub(a, b)) */
    double u[3] = {a[0] - b[0], a[1] - b[1], a[2] - b[2]};
    return norm(u);
}
static double max3(double a, double b, double c) {   /* max(a, b, c): its first of the greatest */
    double m = a;
    if (b > m) m = b;
    if (c > m) m = c;
    return m;
}
/* _unit(v) into out: 1, or 0 for None (|v| not above 0). */
static int unit(const double *v, double *out) {
    double n = norm(v);
    if (!(n > 0.0)) return 0;
    out[0] = v[0] / n, out[1] = v[1] / n, out[2] = v[2] / n;
    return 1;
}
/* _f32(v): each as float32 holds it; 1 where one overflows (struct.pack's OverflowError). */
static int f32(const double *v, double *out) {
    for (int i = 0; i < 3; i++) {
        float y = (float)v[i];
        if (__builtin_isinf(y) && !__builtin_isinf(v[i])) return 1;
        out[i] = (double)y;
    }
    return 0;
}

/* ---- a point's final position (_subdivide's final) --------------------------------------------------------------- */
/* _lift's move along u into d: 1, 0 for None, -1 where the twin divides by zero (k 0). */
static int lift(const double *u, double r, double big_r, double k, double w, double *d) {
    if (!(w > 0.0 && r < big_r + k)) return 0;
    if (k == 0.0) return -1;
    double gap = r - big_r, h = (k - fab(gap)) / k;
    double f = (gap > 0.0 ? r : big_r) + (h > 0.0 ? h * h * k / 4.0 : 0.0), step = w * (f - r);
    d[0] = step * u[0], d[1] = step * u[1], d[2] = step * u[2];
    return 1;
}

static double smooth_max(double a, double b, double k) {   /* _smooth_max */
    double m = a > b ? a : b;
    if (k > 0.0) {
        double h = (k - fab(a - b)) / k;
        if (h > 0.0) m += h * h * k / 4.0;
    }
    return m;
}

/* _round_one(p, mine, False) in place: the nm sides mine (their global numbers). 0, or -1 where the twin raises. */
static int round_one(K *k, double *p, const i64 *mine, int nm) {
    double one[8], two[8], d[3];
    if (nm == 2 && k->spair[mine[0]]) {   /* a pair's one ray from its origin */
        const double *o = k->sorigin + 3 * mine[0];
        i64 a = az_ray(k->rays + k->srow[mine[0]], p[0], p[1], p[2], 1, o[0], o[1], o[2], one);
        i64 b = az_ray(k->rays + k->srow[mine[1]], p[0], p[1], p[2], 1, o[0], o[1], o[2], two);
        if (a == 2 || b == 2) return -1;
        if (a == 1 || b == 1) return 0;
        double big_r = smooth_max(one[4], two[4], k->sbridge[mine[0]]);
        int got = lift(one, one[3], big_r, (one[5] + two[5]) / 2.0, (one[6] + two[6]) / 2.0, d);
        if (got < 0) return -1;
        if (got) p[0] = p[0] + d[0], p[1] = p[1] + d[1], p[2] = p[2] + d[2];
        return 0;
    }
    double moves[SIDES][3];
    int nmv = 0;
    for (int i = 0; i < nm; i++) {
        i64 a = az_ray(k->rays + k->srow[mine[i]], p[0], p[1], p[2], 0, 0.0, 0.0, 0.0, one);
        if (a == 2) return -1;
        if (a == 1) continue;
        int got = lift(one, one[3], one[4], one[5], one[6], moves[nmv]);
        if (got < 0) return -1;
        nmv += got;
    }
    if (!nmv) return 0;
    if (nmv == 1) {
        d[0] = moves[0][0], d[1] = moves[0][1], d[2] = moves[0][2];
    } else {
        double w[SIDES], x[SIDES], total;
        for (int i = 0; i < nmv; i++) w[i] = dot(moves[i], moves[i]);
        total = psum(w, nmv);
        for (int c = 0; c < 3; c++) {
            if (total > 0.0) {
                for (int i = 0; i < nmv; i++) x[i] = w[i] * moves[i][c];
                d[c] = psum(x, nmv) / total;
            } else {
                d[c] = 0.0;
            }
        }
    }
    p[0] = p[0] + d[0], p[1] = p[1] + d[1], p[2] = p[2] + d[2];
    return 0;
}

/* final(): p moved by the field ops and round sides of the class of (h, group slot g) into out; 0, or -1 where the
 * twin raises. */
static int final_at(K *k, const double *p, i64 h, i64 g, double *out) {
    i64 c = k->cls[h * k->s[S_NG] + g], nf = k->fstart[c + 1] - k->fstart[c];
    double q[3] = {p[0], p[1], p[2]};
    if (nf > 0 && az_moved(k->rows, k->fidx + k->fstart[c], nf, p, q)) return -1;
    i64 e = k->rstart[c], end = k->rstart[c + 1];
    for (i64 i = 0; i < k->s[S_NROUNDS]; i++) {
        i64 mine[SIDES];
        int nm = 0;
        for (; e < end && k->rround[e] == i; e++) mine[nm++] = k->sbase[i] + k->rside[e];
        if (round_one(k, q, mine, nm)) return -1;
    }
    out[0] = q[0], out[1] = q[1], out[2] = q[2];
    return 0;
}

/* fin(v): vertex v's final position, worked out once; NULL where the twin raises. */
static const double *fin(K *k, i64 v) {
    if (!k->have[v]) {
        if (final_at(k, k->base + 3 * v, k->heavy[v], k->gs[v], k->fin + 3 * v)) return 0;
        k->have[v] = 1;
    }
    return k->fin + 3 * v;
}

/* ---- the welded edges and their triangles ------------------------------------------------------------------------ */
/* flat(a, b, c): a welded triangle with no area to split. */
static int flat(K *k, i64 a, i64 b, i64 c) {
    if (a == b || b == c || a == c) return 1;
    const double *pa = k->wpos + 3 * a, *pb = k->wpos + 3 * b, *pc = k->wpos + 3 * c;
    double u[3] = {pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2]}, v[3] = {pc[0] - pa[0], pc[1] - pa[1], pc[2] - pa[2]};
    double f[3] = {u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]};
    double longest = max3(dist(pa, pb), dist(pb, pc), dist(pc, pa));
    return !(norm(f) > k->d[D_SLIVER] * longest * longest);
}

static i64 find(K *k, i64 x, i64 y) {   /* the edge (x, y), x < y, or -1 */
    for (i64 e = k->adj[x]; e >= 0; e = k->enext[e])
        if (k->ey[e] == y) return e;
    return -1;
}

static i64 make(K *k, i64 x, i64 y) {   /* the edge (x, y), made where new; -1 where there is no room */
    i64 e = find(k, x, y);
    if (e >= 0) return e;
    if (k->s[S_NE] >= k->s[S_CAPE]) return -1;
    e = k->s[S_NE]++;
    k->ex[e] = x, k->ey[e] = y, k->eref[e] = 0, k->ehead[e] = -1, k->enext[e] = k->adj[x], k->adj[x] = e;
    return e;
}

static int refused(K *k, i64 a, i64 b) {
    i64 e = find(k, lo2(a, b), hi2(a, b));
    return e >= 0 && k->eref[e];
}

/* link(t): t on its three welded edges (none where it is flat); -1 where there is no room. */
static int link(K *k, i64 t) {
    const i64 *tr = k->tri + 3 * t;
    i64 w[3] = {k->wid[tr[0]], k->wid[tr[1]], k->wid[tr[2]]};
    if (flat(k, w[0], w[1], w[2])) return 0;
    for (int i = 0; i < 3; i++) {
        i64 e = make(k, lo2(w[i], w[(i + 1) % 3]), hi2(w[i], w[(i + 1) % 3])), n;
        if (e < 0) return -1;
        for (n = k->ehead[e]; n >= 0; n = k->nnext[n])
            if (k->ntri[n] == t) break;
        if (n >= 0) continue;
        n = k->s[S_FREE];
        if (n >= 0) {
            k->s[S_FREE] = k->nnext[n];
        } else {
            if (k->s[S_NN] >= k->s[S_CAPN]) return -1;
            n = k->s[S_NN]++;
        }
        k->ntri[n] = t, k->nnext[n] = k->ehead[e], k->ehead[e] = n;
    }
    return 0;
}

static void unlink(K *k, i64 t) {
    const i64 *tr = k->tri + 3 * t;
    i64 w[3] = {k->wid[tr[0]], k->wid[tr[1]], k->wid[tr[2]]};
    if (flat(k, w[0], w[1], w[2])) return;
    for (int i = 0; i < 3; i++) {
        i64 e = find(k, lo2(w[i], w[(i + 1) % 3]), hi2(w[i], w[(i + 1) % 3])), prev = -1;
        if (e < 0) continue;
        for (i64 n = k->ehead[e]; n >= 0; prev = n, n = k->nnext[n]) {
            if (k->ntri[n] != t) continue;
            if (prev < 0)
                k->ehead[e] = k->nnext[n];
            else
                k->nnext[prev] = k->nnext[n];
            k->nnext[n] = k->s[S_FREE], k->s[S_FREE] = n;
            break;
        }
    }
}

/* The edge e's triangles, ascending, into out; -1 past LIST. */
static i64 listed(K *k, i64 e, i64 *out) {
    i64 m = 0;
    if (e < 0) return 0;
    for (i64 n = k->ehead[e]; n >= 0; n = k->nnext[n]) {
        if (m == LIST) return -1;
        i64 t = k->ntri[n], j = m++;
        for (; j > 0 && out[j - 1] > t; j--) out[j] = out[j - 1];
        out[j] = t;
    }
    return m;
}

static void welded3(K *k, i64 t, i64 *w) {   /* t's welded points, ascending */
    const i64 *tr = k->tri + 3 * t;
    i64 a = k->wid[tr[0]], b = k->wid[tr[1]], c = k->wid[tr[2]], x;
    if (a > b) x = a, a = b, b = x;
    if (b > c) x = b, b = c, c = x;
    if (a > b) x = a, a = b, b = x;
    w[0] = a, w[1] = b, w[2] = c;
}

/* _open(e): whether one face bounds the edge e (a two-sided layer's twin counted once). */
static int open_edge(K *k, i64 e) {
    if (e < 0 || k->ehead[e] < 0) return 0;
    i64 first[3], other[3];
    welded3(k, k->ntri[k->ehead[e]], first);
    for (i64 n = k->nnext[k->ehead[e]]; n >= 0; n = k->nnext[n]) {
        welded3(k, k->ntri[n], other);
        if (other[0] != first[0] || other[1] != first[1] || other[2] != first[2]) return 0;
    }
    return 1;
}

/* ---- taken: every welded point's position (a set of float tuples: 0.0 and -0.0 one) ------------------------------ */
static u64 bits(double x) {
    union {
        double d;
        u64 u;
    } v;
    v.d = x == 0.0 ? 0.0 : x;
    return v.u;
}

static u64 hashed(const double *p) {
    u64 h = bits(p[0]) * 0x9E3779B97F4A7C15ull;
    h = (h ^ (h >> 31) ^ bits(p[1])) * 0xBF58476D1CE4E5B9ull;
    h = (h ^ (h >> 29) ^ bits(p[2])) * 0x94D049BB133111EBull;
    return h ^ (h >> 32);
}

static int taken(K *k, const double *p) {
    u64 mask = (u64)k->s[S_HCAP] - 1, at = hashed(p) & mask;
    for (; k->hash[at]; at = (at + 1) & mask) {
        const double *q = k->wpos + 3 * (k->hash[at] - 1);
        if (q[0] == p[0] && q[1] == p[1] && q[2] == p[2]) return 1;
    }
    return 0;
}

static void take(K *k, i64 w) {
    u64 mask = (u64)k->s[S_HCAP] - 1, at = hashed(k->wpos + 3 * w) & mask;
    while (k->hash[at]) at = (at + 1) & mask;
    k->hash[at] = w + 1;
}

/* ---- the heap (heapq's, over (key, t, version) tuples) ----------------------------------------------------------- */
static int less(K *k, i64 a, i64 b) {
    if (!(k->hkey[a] == k->hkey[b])) return k->hkey[a] < k->hkey[b];
    if (k->ht[a] != k->ht[b]) return k->ht[a] < k->ht[b];
    return k->hver[a] < k->hver[b];
}

static void swap(K *k, i64 a, i64 b) {
    double key = k->hkey[a];
    i64 t = k->ht[a], v = k->hver[a];
    k->hkey[a] = k->hkey[b], k->ht[a] = k->ht[b], k->hver[a] = k->hver[b];
    k->hkey[b] = key, k->ht[b] = t, k->hver[b] = v;
}

static void siftdown(K *k, i64 start, i64 pos) {
    while (pos > start) {
        i64 parent = (pos - 1) >> 1;
        if (!less(k, pos, parent)) break;
        swap(k, pos, parent);
        pos = parent;
    }
}

static void siftup(K *k, i64 pos) {
    i64 end = k->s[S_NH], start = pos, limit = end >> 1;
    while (pos < limit) {
        i64 child = 2 * pos + 1;
        if (child + 1 < end && !less(k, child, child + 1)) child++;
        swap(k, pos, child);
        pos = child;
    }
    siftdown(k, start, pos);
}

/* heappush((key, t, version)); -1 for a NaN key (the twin's order is its heap's then) or no room. */
static int push(K *k, double key, i64 t) {
    i64 n = k->s[S_NH];
    if (key != key || n >= k->s[S_CAPH]) return -1;
    k->hkey[n] = key, k->ht[n] = t, k->hver[n] = k->ver[t];
    k->s[S_NH] = n + 1;
    siftdown(k, 0, n);
    return 0;
}

/* ---- the loop ---------------------------------------------------------------------------------------------------- */
/* longest(t): t's longest welded edge in the final shape (each point at its first copy's), a refused one only when
 * all three are; ties by the points. 0, or -1 where the twin raises. */
static int longest(K *k, i64 t, i64 *x, i64 *y) {
    const i64 *tr = k->tri + 3 * t;
    i64 w[3] = {k->wid[tr[0]], k->wid[tr[1]], k->wid[tr[2]]}, lo[3], hi[3];
    const double *f[3];
    double len[3];
    int ok[3], any = 0, best = -1;
    for (int i = 0; i < 3; i++)
        if (!(f[i] = fin(k, k->rep[w[i]]))) return -1;
    for (int i = 0; i < 3; i++) {
        len[i] = dist(f[i], f[(i + 1) % 3]);
        lo[i] = lo2(w[i], w[(i + 1) % 3]), hi[i] = hi2(w[i], w[(i + 1) % 3]);
        ok[i] = !refused(k, lo[i], hi[i]);
        any |= ok[i];
    }
    for (int i = 0; i < 3; i++) {
        if (any && !ok[i]) continue;
        int more = best < 0 ? 1 : !(len[i] == len[best]) ? len[i] > len[best]
                                  : lo[i] != lo[best]   ? lo[i] > lo[best]
                                                        : hi[i] > hi[best];
        if (more) best = i;
    }
    *x = lo[best], *y = hi[best];
    return 0;
}

/* mark(t): 1 where t is marked (its longest final edge in *len, a smooth region's in *sm), 0 where not, -1 where the
 * twin raises. */
static int mark(K *k, i64 t, double *len, int *sm) {
    const i64 *tr = k->tri + 3 * t;
    i64 w[3] = {k->wid[tr[0]], k->wid[tr[1]], k->wid[tr[2]]}, ng = k->s[S_NG], x, y;
    if (flat(k, w[0], w[1], w[2])) return 0;
    for (int i = 0; i < 3; i++)
        if (refused(k, w[i], w[(i + 1) % 3])) return 0;
    u64 in = (u64)k->sel[k->heavy[tr[0]] * ng + k->gs[tr[0]]] & (u64)k->sel[k->heavy[tr[1]] * ng + k->gs[tr[1]]]
             & (u64)k->sel[k->heavy[tr[2]] * ng + k->gs[tr[2]]];
    if (!in) return 0;
    double c[3];
    for (int j = 0; j < 3; j++) {
        double v[3] = {k->wpos[3 * w[0] + j], k->wpos[3 * w[1] + j], k->wpos[3 * w[2] + j]};
        c[j] = psum(v, 3) / 3.0;
    }
    for (i64 r = 0; r < k->s[S_NREG]; r++) {
        const double *R = k->reg + 7 * r;
        double a = (c[0] - R[0]) / R[3], b = (c[1] - R[1]) / R[4], z = (c[2] - R[2]) / R[5];
        if ((in >> r & 1) && !(a * a + b * b + z * z < 1.0)) in &= ~((u64)1 << r);
    }
    if (!in) return 0;
    const double *f[3];
    for (int i = 0; i < 3; i++)
        if (!(f[i] = fin(k, tr[i]))) return -1;
    double length = max3(dist(f[0], f[1]), dist(f[1], f[2]), dist(f[2], f[0]));
    if (longest(k, t, &x, &y)) return -1;
    double span = dist(k->wpos + 3 * x, k->wpos + 3 * y), stretch = k->d[D_STRETCH];
    *sm = (in & (u64)k->s[S_SMOOTHS]) != 0;
    *len = length;
    u64 plain = in & ~(u64)k->s[S_HEMS], hem = in & (u64)k->s[S_HEMS];
    if (plain) {
        double edge = 0.0;
        int first = 1;
        for (i64 r = 0; r < k->s[S_NREG]; r++)
            if ((plain >> r & 1) && (first || k->reg[7 * r + 6] < edge)) edge = k->reg[7 * r + 6], first = 0;
        if (length > edge && span > edge / stretch) return 1;
    }
    if (hem) {
        double edge = 0.0;
        int first = 1;
        for (i64 r = 0; r < k->s[S_NREG]; r++)
            if ((hem >> r & 1) && (first || k->reg[7 * r + 6] < edge)) edge = k->reg[7 * r + 6], first = 0;
        for (int i = 0; i < 3; i++) {
            i64 a = lo2(w[i], w[(i + 1) % 3]), b = hi2(w[i], w[(i + 1) % 3]);
            if (open_edge(k, find(k, a, b)) && dist(f[i], f[(i + 1) % 3]) > edge && span > edge / stretch) return 1;
        }
    }
    return 0;
}

/* A merged skin: (bone, weight) pairs in the order the twin's dict first holds each. */
typedef struct {
    i64 bone[SKIN];
    double w[SKIN];
    int n;
} Skin;

/* skin[bone] = skin.get(bone, 0.0) + w for each of vertex v's (bone, w), halved where half; -1 past SKIN. */
static int merge(K *k, Skin *m, i64 v, int half) {
    for (i64 j = k->sstart[v]; j < k->sstart[v + 1]; j++) {
        i64 b = k->sbone[j];
        double w = half ? k->sw[j] / 2.0 : k->sw[j];
        int i = 0;
        while (i < m->n && m->bone[i] != b) i++;
        if (i == m->n) {
            if (m->n == SKIN) return -1;
            m->bone[i] = b, m->w[i] = 0.0, m->n++;
        }
        m->w[i] = m->w[i] + w;
    }
    return 0;
}

static int heavier(const Skin *m, int a, int b) {   /* (-w, bone) of a < that of b */
    if (!(-m->w[a] == -m->w[b])) return -m->w[a] < -m->w[b];
    return m->bone[a] < m->bone[b];
}

/* split(e = (wa, wb)): every triangle on the welded edge split at its midpoint (each copy of it its own new vertex),
 * unless a field op tears the edge or an old point lies there. 1 split (the triangles it made or changed in
 * k->touch), 0 torn or an old point, -1 where the twin raises (or a list past LIST), 2 where a buffer is short. */
static int split(K *k, i64 wa, i64 wb, int smooth) {
    i64 *s = k->s, list[LIST], m = listed(k, find(k, wa, wb), list), ng = s[S_NG];
    if (m <= 0) return -1;
    if (s[S_NV] + m > s[S_CAPV] || s[S_NW] + 1 > s[S_CAPW] || 2 * (s[S_NW] + 1) > s[S_HCAP] ||
        s[S_NT] + m > s[S_CAPT] || s[S_NE] + 3 * m > s[S_CAPE] || s[S_NN] + 3 * m > s[S_CAPN] ||
        s[S_NH] + 2 * m + 1 > s[S_CAPH] || s[S_NSK] + 4 * m > s[S_CAPSK])
        return 2;
    const double *pa = k->wpos + 3 * wa, *pb = k->wpos + 3 * wb;
    double mid[3], point[3];
    for (int c = 0; c < 3; c++) mid[c] = (pa[c] + pb[c]) / 2.0;
    if (smooth) {   /* PN triangles' edge midpoint: the cubic through both ends along their normals */
        const double *na = k->wnrm + 3 * wa, *nb = k->wnrm + 3 * wb;
        double d[3] = {pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2]}, wab = dot(d, na), wba = -dot(d, nb);
        for (int c = 0; c < 3; c++) mid[c] = mid[c] - (wab * na[c] + wba * nb[c]) / 8.0;
    }
    if (f32(mid, point)) return -1;
    for (i64 i = 0; i < m; i++) {   /* a field op that stops at a bone or group boundary tears the edge */
        const i64 *tr = k->tri + 3 * list[i];
        i64 ends[2];
        int ne = 0;
        for (int j = 0; j < 3; j++)
            if (k->wid[tr[j]] == wa || k->wid[tr[j]] == wb) {
                if (ne == 2) return -1;
                ends[ne++] = tr[j];
            }
        if (ne != 2) return -1;
        Skin sk = {.n = 0};
        if (merge(k, &sk, ends[0], 0) || merge(k, &sk, ends[1], 0) || !sk.n) return -1;
        int h = 0;
        for (int j = 1; j < sk.n; j++)
            if (heavier(&sk, j, h)) h = j;
        i64 g = k->gs[ends[0]], ch = k->cls[sk.bone[h] * ng + g];
        if (k->cls[k->heavy[ends[0]] * ng + g] == k->cls[k->heavy[ends[1]] * ng + g] &&
            k->cls[k->heavy[ends[1]] * ng + g] == ch)
            continue;   /* one continuous map over the edge */
        double fm[3];
        const double *f0, *f1;
        if (final_at(k, point, sk.bone[h], g, fm) || !(f0 = fin(k, ends[0])) || !(f1 = fin(k, ends[1]))) return -1;
        double full = dist(f0, f1), a = dist(fm, f0), b = dist(fm, f1);
        if ((b > a ? b : a) > k->d[D_TORN] * full) return 0;
    }
    if (taken(k, point)) return 0;   /* a sliver's chain of points on a line: none on an old point */
    i64 wm = s[S_NW]++;
    double *pw = k->wpos + 3 * wm, *nw = k->wnrm + 3 * wm;
    const double *wa_n = k->wnrm + 3 * wa, *wb_n = k->wnrm + 3 * wb;
    pw[0] = point[0], pw[1] = point[1], pw[2] = point[2];
    take(k, wm);
    k->adj[wm] = -1, k->rep[wm] = -1;
    int same = dot(wa_n, wb_n) >= 0.0;
    double sum[3];
    for (int c = 0; c < 3; c++) sum[c] = wa_n[c] + (same ? wb_n[c] : -wb_n[c]);
    if (!unit(sum, nw)) nw[0] = wa_n[0], nw[1] = wa_n[1], nw[2] = wa_n[2];
    i64 ka[LIST], kb[LIST], km[LIST], ncopies = 0;
    k->ntouch = 0;
    for (i64 i = 0; i < m; i++) {
        i64 t = list[i], *tr = k->tri + 3 * t, a = tr[0], b = tr[1], c = tr[2], r0 = c, r1 = a, r2 = b;
        i64 rot[3][3] = {{a, b, c}, {b, c, a}, {c, a, b}};
        for (int j = 0; j < 3; j++) {
            r0 = rot[j][0], r1 = rot[j][1], r2 = rot[j][2];
            i64 x = k->wid[r0], y = k->wid[r1];
            if ((x == wa && y == wb) || (x == wb && y == wa)) break;
        }
        i64 x0 = lo2(r0, r1), x1 = hi2(r0, r1), mv = -1;
        for (i64 j = 0; j < ncopies; j++)
            if (ka[j] == x0 && kb[j] == x1) mv = km[j];
        if (mv < 0) {
            Skin sk = {.n = 0};
            if (merge(k, &sk, r0, 1) || merge(k, &sk, r1, 1)) return -1;
            int order[SKIN], ntop = sk.n < 4 ? sk.n : 4;
            for (int j = 0; j < sk.n; j++) {   /* sorted by (-w, bone) */
                int q = j;
                for (; q > 0 && heavier(&sk, j, order[q - 1]); q--) order[q] = order[q - 1];
                order[q] = j;
            }
            if (!ntop) return -1;
            double top[4], n0[3], n1[3], nsum[3];
            for (int j = 0; j < ntop; j++) top[j] = sk.w[order[j]];
            double total = psum(top, ntop);
            if (total == 0.0) return -1;
            int ok0 = unit(k->nrm + 3 * r0, n0), ok1 = unit(k->nrm + 3 * r1, n1);
            if (ok0 && ok1 && dot(n0, n1) < 0.0) ok1 = 0;
            for (int j = 0; j < 3; j++) nsum[j] = (ok0 ? n0[j] : 0.0) + (ok1 ? n1[j] : 0.0);
            mv = s[S_NV]++;
            double *nm = k->nrm + 3 * mv;
            if (!unit(nsum, nm)) nm[0] = nw[0], nm[1] = nw[1], nm[2] = nw[2];
            k->wid[mv] = wm, k->gs[mv] = k->gs[r0], k->heavy[mv] = sk.bone[order[0]], k->have[mv] = 0;
            k->base[3 * mv] = pw[0], k->base[3 * mv + 1] = pw[1], k->base[3 * mv + 2] = pw[2];
            k->uv[2 * mv] = (k->uv[2 * r0] + k->uv[2 * r1]) / 2.0;
            k->uv[2 * mv + 1] = (k->uv[2 * r0 + 1] + k->uv[2 * r1 + 1]) / 2.0;
            for (int j = 0; j < ntop; j++)
                k->sbone[s[S_NSK]] = sk.bone[order[j]], k->sw[s[S_NSK]] = top[j] / total, s[S_NSK]++;
            k->sstart[mv + 1] = s[S_NSK];
            if (k->rep[wm] < 0) k->rep[wm] = mv;
            if (++s[S_ADDED] > s[S_MAXADD]) return -1;
            ka[ncopies] = x0, kb[ncopies] = x1, km[ncopies++] = mv;
        }
        unlink(k, t);
        i64 nt = s[S_NT]++;
        tr = k->tri + 3 * t;
        tr[0] = r0, tr[1] = mv, tr[2] = r2;
        k->tri[3 * nt] = mv, k->tri[3 * nt + 1] = r1, k->tri[3 * nt + 2] = r2;
        k->ver[t]++, k->ver[nt] = 0;
        if (link(k, t) || link(k, nt)) return -1;
        k->touch[k->ntouch++] = t, k->touch[k->ntouch++] = nt;
    }
    return 1;
}

/* The loop from where it stopped: DONE (at PH_END: the open edges written), FAIL, or ROOM. */
static i64 run(K *k) {
    i64 *s = k->s;
    double len;
    int sm;
    if (s[S_PHASE] == PH_START) {
        for (i64 w = 0; w < s[S_NW]; w++) take(k, w);
        for (i64 t = 0; t < s[S_NT]; t++)
            if (link(k, t)) return FAIL;
        for (i64 t = 0, n = s[S_NT]; t < n; t++) {
            int got = mark(k, t, &len, &sm);
            if (got < 0) return FAIL;
            if (!got) continue;
            if (len != len || s[S_NH] >= s[S_CAPH]) return FAIL;
            k->hkey[s[S_NH]] = -len, k->ht[s[S_NH]] = t, k->hver[s[S_NH]] = 0, s[S_NH]++;
        }
        for (i64 i = (s[S_NH] >> 1) - 1; i >= 0; i--) siftup(k, i);
        s[S_PHASE] = PH_POP;
    }
    for (;;) {
        if (s[S_PHASE] == PH_POP) {
            if (!s[S_NH]) {
                s[S_PHASE] = PH_END;
                return DONE;
            }
            i64 t0 = k->ht[0], v = k->hver[0], last = --s[S_NH];
            if (last > 0) {
                k->hkey[0] = k->hkey[last], k->ht[0] = k->ht[last], k->hver[0] = k->hver[last];
                siftup(k, 0);
            }
            if (v != k->ver[t0]) continue;
            int got = mark(k, t0, &len, &sm);
            if (got < 0) return FAIL;
            if (!got) continue;
            k->d[D_GOTLEN] = len, s[S_GOTSM] = sm, s[S_T0] = t0, k->stack[0] = t0, s[S_DEPTH] = 1;
            s[S_PHASE] = PH_WALK;
        }
        while (s[S_DEPTH] > 0) {   /* Rivara's longest-edge propagation: split an edge only where it is every
                                      triangle's on it longest */
            i64 t = k->stack[s[S_DEPTH] - 1], x, y, list[LIST], nxt = -1;
            if (longest(k, t, &x, &y)) return FAIL;
            i64 m = listed(k, find(k, x, y), list);
            if (m < 0) return FAIL;
            for (i64 i = 0; i < m && nxt < 0; i++) {
                i64 a, b;
                if (list[i] == t) continue;
                if (longest(k, list[i], &a, &b)) return FAIL;
                if (a != x || b != y) nxt = list[i];
            }
            if (nxt >= 0 && s[S_DEPTH] < s[S_LEPP]) {
                k->stack[s[S_DEPTH]++] = nxt;
                continue;
            }
            int got = split(k, x, y, (int)s[S_GOTSM]);
            if (got == 2) return ROOM;
            if (got < 0) return FAIL;
            if (!got) {   /* torn, or an old point: remembered, never split; the chain's start again */
                i64 e = find(k, x, y);
                if (!k->eref[e]) {
                    k->eref[e] = 1;
                    if (push(k, -k->d[D_GOTLEN], s[S_T0])) return FAIL;
                }
                s[S_DEPTH] = 0;
                break;
            }
            s[S_DEPTH]--;
            for (i64 i = 0; i < k->ntouch; i++) {
                int marked = mark(k, k->touch[i], &len, &sm);
                if (marked < 0 || (marked && push(k, -len, k->touch[i]))) return FAIL;
            }
        }
        s[S_PHASE] = PH_POP;
    }
}

/* _subdivide's split loop on the caller's buffers (p: their addresses, by P_*; s: the numbers, by S_*; d: STRETCH,
 * TORN, SLIVER and the walk's length): DONE once the heap is empty (then, called again at PH_END, the open edges
 * (x, y, least triangle) into P_OPEN and their count in S_NOPEN), FAIL where the twin answers, ROOM where a buffer is
 * short (grown, called again: on from where it stopped). */
API i64 az_subdivide(const i64 *p, i64 *s, double *d) {
    K k;
#define AT(T, i) ((T *)(uintptr_t)p[i])
    k.s = s, k.d = d;
    k.wid = AT(i64, P_WID), k.gs = AT(i64, P_GS), k.heavy = AT(i64, P_HEAVY), k.sstart = AT(i64, P_SSTART);
    k.sbone = AT(i64, P_SBONE), k.sw = AT(double, P_SW), k.nrm = AT(double, P_NRM), k.uv = AT(double, P_UV);
    k.base = AT(double, P_BASE), k.fin = AT(double, P_FIN), k.have = AT(i64, P_HAVE);
    k.wpos = AT(double, P_WPOS), k.wnrm = AT(double, P_WNRM), k.rep = AT(i64, P_REP), k.adj = AT(i64, P_ADJ);
    k.hash = AT(i64, P_HASH), k.tri = AT(i64, P_TRI), k.ver = AT(i64, P_VER);
    k.ex = AT(i64, P_EX), k.ey = AT(i64, P_EY), k.eref = AT(i64, P_EREF), k.ehead = AT(i64, P_EHEAD);
    k.enext = AT(i64, P_ENEXT), k.ntri = AT(i64, P_NTRI), k.nnext = AT(i64, P_NNEXT);
    k.hkey = AT(double, P_HKEY), k.ht = AT(i64, P_HT), k.hver = AT(i64, P_HVER);
    k.reg = AT(const double, P_REG), k.sel = AT(const i64, P_SEL), k.cls = AT(const i64, P_CLS);
    k.fstart = AT(const i64, P_FSTART), k.fidx = AT(const i64, P_FIDX), k.rows = AT(const double, P_ROWS);
    k.rstart = AT(const i64, P_RSTART), k.rround = AT(const i64, P_RROUND), k.rside = AT(const i64, P_RSIDE);
    k.sbase = AT(const i64, P_SBASE), k.srow = AT(const i64, P_SROW), k.spair = AT(const i64, P_SPAIR);
    k.sbridge = AT(const double, P_SBRIDGE), k.sorigin = AT(const double, P_SORIGIN), k.rays = AT(const double, P_RAYS);
    k.stack = AT(i64, P_STACK), k.open = AT(i64, P_OPEN);
#undef AT
    if (s[S_NREG] < 0 || s[S_NREG] > 63 || s[S_LEPP] < 1 || s[S_LEPP] > STACK) return FAIL;
    if (s[S_REHASH]) {   /* the set's room grew: every point again */
        for (i64 w = 0; w < s[S_NW]; w++) take(&k, w);
        s[S_REHASH] = 0;
    }
    if (s[S_PHASE] == PH_END) {
        i64 n = 0;
        for (i64 e = 0; e < s[S_NE]; e++) {
            if (!open_edge(&k, e)) continue;
            i64 least = k.ntri[k.ehead[e]];
            for (i64 j = k.nnext[k.ehead[e]]; j >= 0; j = k.nnext[j])
                if (k.ntri[j] < least) least = k.ntri[j];
            k.open[3 * n] = k.ex[e], k.open[3 * n + 1] = k.ey[e], k.open[3 * n + 2] = least, n++;
        }
        s[S_NOPEN] = n;
        return DONE;
    }
    return run(&k);
}
