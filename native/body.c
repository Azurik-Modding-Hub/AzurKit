/* The body writes' kernels, compiled (D1009): tools/characters/body_codec.py's stripify (az_strip: _stripped's greedy
 * strips, joined by degenerate triangles, and its check that the strip draws exactly its triangles). Each is its
 * Python twin's steps in the twin's order on integers, so the two agree exactly (tests/test_native.py): a dict's lists
 * keep their insertion order, Python's min keeps its first, a heap of unique (count, index) keys pops in their order
 * whatever its shape. Where the twin raises (a triangle that repeats a vertex, a strip that doesn't draw its
 * triangles) the kernel answers 2 and its caller runs the twin. No libc, no allocation: the caller passes every
 * buffer. Built by nativekit (C99, zig cc). */
#include <stdint.h>

#if defined(_WIN32)
#define API __declspec(dllexport)
#else
#define API __attribute__((visibility("default")))
#endif

typedef int64_t i64;
typedef uint64_t u64;

#define TWIN 2

/* ---- the directed edges: a hash of (p, q) to its edge, each edge's triangles in their order --------------------- */
typedef struct {
    i64 mask, edges;          /* the slots less one; the edges found */
    i64 *slot;                /* an edge's number + 1, 0 an empty slot */
    i64 *ep, *eq, *start, *count, *list;
} Edges;

static u64 mix(i64 p, i64 q) {
    u64 h = (u64)p * 0x9E3779B97F4A7C15ull + (u64)q * 0xC2B2AE3D27D4EB4Full;
    h ^= h >> 29;
    h *= 0xBF58476D1CE4E5B9ull;
    return h ^ (h >> 32);
}

static i64 find(const Edges *E, i64 p, i64 q) {
    for (u64 h = mix(p, q) & (u64)E->mask;; h = (h + 1) & (u64)E->mask) {
        i64 s = E->slot[h];
        if (s == 0) return -1;
        if (E->ep[s - 1] == p && E->eq[s - 1] == q) return s - 1;
    }
}

static i64 add(Edges *E, i64 p, i64 q) {
    u64 h = mix(p, q) & (u64)E->mask;
    for (;; h = (h + 1) & (u64)E->mask) {
        i64 s = E->slot[h];
        if (s == 0) break;
        if (E->ep[s - 1] == p && E->eq[s - 1] == q) return s - 1;
    }
    i64 e = E->edges++;
    E->slot[h] = e + 1, E->ep[e] = p, E->eq[e] = q, E->count[e] = 0;
    return e;
}

static i64 slots_for(i64 n) {
    i64 h = 8;
    while (h < 6 * n) h *= 2;
    return h;
}

/* ---- the strip ------------------------------------------------------------------------------------------------- */
typedef struct {
    const i64 *t;             /* the triangles, three corners each */
    Edges E;
    i64 *rev;                 /* each triangle's three reversed edges' numbers ((b, a), (c, b), (a, c)), -1 none */
    i64 *used, *mark;
} S;

/* neighbours(k, mark): the free triangles across k's edges (a mark of -1: none marked). */
static i64 neighbours(const S *s, i64 k, i64 epoch) {
    i64 n = 0;
    for (int i = 0; i < 3; i++) {
        i64 e = s->rev[3 * k + i];
        if (e < 0) continue;
        for (i64 a = s->E.start[e], z = a + s->E.count[e]; a < z; a++) {
            i64 j = s->E.list[a];
            if (!s->used[j] && s->mark[j] != epoch) n++;
        }
    }
    return n;
}

/* min(free, key=(neighbours(j, mark), j)) over edge e's free triangles, -1 for none. */
static i64 pick(const S *s, i64 e, i64 epoch) {
    if (e < 0) return -1;
    i64 best = -1, least = 0;
    for (i64 a = s->E.start[e], z = a + s->E.count[e]; a < z; a++) {
        i64 j = s->E.list[a];
        if (s->used[j] || s->mark[j] == epoch) continue;
        i64 n = neighbours(s, j, epoch);
        if (best < 0 || n < least) best = j, least = n;   /* the list is in index order: a tie keeps the first */
    }
    return best;
}

static i64 third(const S *s, i64 k, i64 p, i64 q) {
    i64 a = s->t[3 * k], b = s->t[3 * k + 1], c = s->t[3 * k + 2];
    if (p == a && q == b) return c;
    if (p == b && q == c) return a;
    return b;                 /* (c, a): the edge it was found by */
}

/* grow: seq (len indices) grown while a triangle off its last edge, its parity's, is free; the triangles taken in
 * taken. Returns seq's new length. */
static i64 grow(S *s, i64 epoch, i64 *seq, i64 len, i64 *taken, i64 *ntaken) {
    i64 nt = 0;
    for (;;) {
        i64 i = len, p, q;
        if (i % 2 == 0) p = seq[i - 2], q = seq[i - 1];
        else p = seq[i - 1], q = seq[i - 2];
        i64 best = pick(s, find(&s->E, p, q), epoch);
        if (best < 0 && nt > 0) {   /* a swap: u p q -> u p u q turns the run onto edge u-q */
            i64 u = seq[i - 3], last = seq[i - 1];
            if ((i + 1) % 2 == 0) p = u, q = last;
            else p = last, q = u;
            best = pick(s, find(&s->E, p, q), epoch);
            if (best >= 0) seq[len] = seq[len - 1], seq[len - 1] = u, len++;
        }
        if (best < 0) break;
        seq[len++] = third(s, best, p, q);
        taken[nt++] = best;
        s->mark[best] = epoch;
    }
    *ntaken = nt;
    return len;
}

/* the heap of (count, index), the least first */
static int below(const i64 *d, const i64 *k, i64 a, i64 b) { return d[a] < d[b] || (d[a] == d[b] && k[a] < k[b]); }

static void swap2(i64 *d, i64 *k, i64 a, i64 b) {
    i64 x = d[a], y = k[a];
    d[a] = d[b], k[a] = k[b], d[b] = x, k[b] = y;
}

static void down(i64 *d, i64 *k, i64 n, i64 i) {
    for (;;) {
        i64 l = 2 * i + 1, r = l + 1, m = i;
        if (l < n && below(d, k, l, m)) m = l;
        if (r < n && below(d, k, r, m)) m = r;
        if (m == i) return;
        swap2(d, k, i, m);
        i = m;
    }
}

static void up(i64 *d, i64 *k, i64 i) {
    while (i > 0) {
        i64 p = (i - 1) / 2;
        if (!below(d, k, i, p)) return;
        swap2(d, k, i, p);
        i = p;
    }
}

/* triples, ordered as Python's tuples */
static int tless(const i64 *x, i64 a, i64 b) {
    const i64 *p = x + 3 * a, *q = x + 3 * b;
    if (p[0] != q[0]) return p[0] < q[0];
    if (p[1] != q[1]) return p[1] < q[1];
    return p[2] < q[2];
}

static void tswap(i64 *x, i64 a, i64 b) {
    for (int i = 0; i < 3; i++) {
        i64 v = x[3 * a + i];
        x[3 * a + i] = x[3 * b + i], x[3 * b + i] = v;
    }
}

static void tsort(i64 *x, i64 n) {   /* a heapsort: equal triples are equal, so any order of them is the sorted one */
    for (i64 i = n / 2 - 1; i >= 0; i--)
        for (i64 j = i;;) {
            i64 l = 2 * j + 1, r = l + 1, m = j;
            if (l < n && tless(x, m, l)) m = l;
            if (r < n && tless(x, m, r)) m = r;
            if (m == j) break;
            tswap(x, j, m), j = m;
        }
    for (i64 end = n - 1; end > 0; end--) {
        tswap(x, 0, end);
        for (i64 j = 0;;) {
            i64 l = 2 * j + 1, r = l + 1, m = j;
            if (l < end && tless(x, m, l)) m = l;
            if (r < end && tless(x, m, r)) m = r;
            if (m == j) break;
            tswap(x, j, m), j = m;
        }
    }
}

static void canonical(i64 a, i64 b, i64 c, i64 *o) {   /* _canonical: turned so its least corner (the first) leads */
    i64 m = a;
    if (b < m) m = b;
    if (c < m) m = c;
    if (a == m) o[0] = a, o[1] = b, o[2] = c;
    else if (b == m) o[0] = b, o[1] = c, o[2] = a;
    else o[0] = c, o[1] = a, o[2] = b;
}

/* The words az_strip's work needs for n triangles. */
API i64 az_strip_need(i64 n) { return slots_for(n) + 33 * n + 32; }

/* body_codec._stripped of the n triangles t (three corners each): the strip's indices in out (6n + 8 words) and its
 * length in *len; 0, or TWIN where the twin raises. work: az_strip_need(n) words. */
static i64 strip_run(const i64 *t, i64 n, i64 *out, i64 *len, i64 *work) {
    *len = 0;
    for (i64 k = 0; k < n; k++) {
        i64 a = t[3 * k], b = t[3 * k + 1], c = t[3 * k + 2];
        if (a == b || b == c || a == c) return TWIN;   /* "triangle ... repeats a vertex" */
    }
    if (n == 0) return 0;      /* no triangle: the empty strip */
    S s;
    i64 H = slots_for(n), *w = work;
    s.t = t;
    s.E.mask = H - 1, s.E.edges = 0;
    s.E.slot = w, w += H;
    s.E.ep = w, w += 3 * n;
    s.E.eq = w, w += 3 * n;
    s.E.start = w, w += 3 * n;
    s.E.count = w, w += 3 * n;
    s.E.list = w, w += 3 * n;
    s.rev = w, w += 3 * n;
    s.used = w, w += n;
    s.mark = w, w += n;
    i64 *hd = w, *hk = w + n, *fill = w + 2 * n;   /* the heap; fill (3n) only while the edges are listed */
    w += 2 * n;
    i64 *fwd = w, *back = w + (2 * n + 4), *strip = w + (4 * n + 8);   /* 2n + 4 each, strip 4n + 8 */
    i64 *ftaken = w + (8 * n + 16), *btaken = w + (9 * n + 16), *taken = w + (10 * n + 16);   /* n, n, n + 1 */
    for (i64 h = 0; h < H; h++) s.E.slot[h] = 0;
    for (i64 k = 0; k < n; k++) {
        i64 a = t[3 * k], b = t[3 * k + 1], c = t[3 * k + 2];
        s.E.count[add(&s.E, a, b)]++;
        s.E.count[add(&s.E, b, c)]++;
        s.E.count[add(&s.E, c, a)]++;
    }
    for (i64 e = 0, at = 0; e < s.E.edges; e++) s.E.start[e] = at, fill[e] = at, at += s.E.count[e];
    for (i64 k = 0; k < n; k++) {   /* each edge's triangles in index order, as by_edge's lists */
        i64 a = t[3 * k], b = t[3 * k + 1], c = t[3 * k + 2];
        s.E.list[fill[find(&s.E, a, b)]++] = k;
        s.E.list[fill[find(&s.E, b, c)]++] = k;
        s.E.list[fill[find(&s.E, c, a)]++] = k;
        s.rev[3 * k] = find(&s.E, b, a), s.rev[3 * k + 1] = find(&s.E, c, b), s.rev[3 * k + 2] = find(&s.E, a, c);
        s.used[k] = 0, s.mark[k] = 0;
    }
    i64 hn = n, epoch = 0, m = 0, cap = 6 * n + 8;
    for (i64 k = 0; k < n; k++) hd[k] = neighbours(&s, k, -1), hk[k] = k;
    for (i64 i = n / 2 - 1; i >= 0; i--) down(hd, hk, hn, i);
    while (hn > 0) {
        i64 deg = hd[0], k = hk[0];
        hn--;
        if (hn > 0) hd[0] = hd[hn], hk[0] = hk[hn], down(hd, hk, hn, 0);
        if (s.used[k]) continue;
        i64 now = neighbours(&s, k, -1);
        if (now != deg) {
            hd[hn] = now, hk[hn] = k, up(hd, hk, hn), hn++;
            continue;
        }
        i64 a = t[3 * k], b = t[3 * k + 1], c = t[3 * k + 2], r[3][3] = {{a, b, c}, {b, c, a}, {c, a, b}};
        i64 best = -1, sl = 0, tn = 0;
        for (int o = 0; o < 3; o++) {
            i64 fn, bn;
            s.mark[k] = ++epoch;
            fwd[0] = r[o][0], fwd[1] = r[o][1], fwd[2] = r[o][2];
            i64 fl = grow(&s, epoch, fwd, 3, ftaken, &fn);
            back[0] = r[o][1], back[1] = r[o][0];
            i64 bl = grow(&s, epoch, back, 2, btaken, &bn) - 2;   /* back[2:] */
            if (bl % 2) {
                bl--;
                if (bn > 0) bn--;
            }
            if (best < 0 || 1 + fn + bn > best) {
                best = 1 + fn + bn, sl = 0, tn = 0;
                for (i64 i = bl - 1; i >= 0; i--) strip[sl++] = back[2 + i];
                for (i64 i = 0; i < fl; i++) strip[sl++] = fwd[i];
                taken[tn++] = k;
                for (i64 i = 0; i < fn; i++) taken[tn++] = ftaken[i];
                for (i64 i = 0; i < bn; i++) taken[tn++] = btaken[i];
            }
        }
        for (i64 i = 0; i < tn; i++) s.used[taken[i]] = 1;
        if (m + sl + 3 > cap) return TWIN;
        if (m) {
            out[m] = out[m - 1], m++;
            out[m++] = strip[0];
            if (m % 2) out[m++] = strip[0];
        }
        for (i64 i = 0; i < sl; i++) out[m++] = strip[i];
    }
    /* the check: strip_triangles(out), each canonical, sorted, against the triangles' own */
    i64 *have = s.E.slot, *want = s.E.slot + 3 * n, got = 0;   /* the edges are done with: their room is free */
    if (H < 6 * n) return TWIN;
    for (i64 i = 2; i < m; i++) {
        i64 a = out[i - 2], b = out[i - 1], c = out[i];
        if (a == b || b == c || a == c) continue;
        if (got == n) return TWIN;
        if (i % 2 == 0) canonical(a, b, c, have + 3 * got++);
        else canonical(b, a, c, have + 3 * got++);
    }
    if (got != n) return TWIN;
    for (i64 k = 0; k < n; k++) canonical(t[3 * k], t[3 * k + 1], t[3 * k + 2], want + 3 * k);
    tsort(have, n);
    tsort(want, n);
    for (i64 i = 0; i < 3 * n; i++)
        if (have[i] != want[i]) return TWIN;
    *len = m;
    return 0;
}

API i64 az_strip(const i64 *t, i64 n, i64 *out, i64 *len, i64 *work) { return strip_run(t, n, out, len, work); }

/* ---- the regroup: body_codec.regroup past its first test (its twin _split) ----------------------------------------- */
#define PALETTE_MAX 31
#define INDEX_MAX 0xFFFF
#define PUSH_MAX 22392
#define CHUNK 256
#define FIT_MAX 11140             /* the most triangles _least_push lets fit: the largest part ever stripped */

static int finite(double x) { return __builtin_isfinite(x); }
static double fab(double x) { return __builtin_fabs(x); }

/* sum() of three floats: 0 + x, then Neumaier's compensation, added at the end only if nonzero and finite */
static double sum3(double x, double y, double z) {
    double f = 0.0 + x, c = 0.0, v[2] = {y, z};
    for (int i = 0; i < 2; i++) {
        double t = f + v[i];
        if (fab(f) >= fab(v[i])) c += (f - t) + v[i];
        else c += (v[i] - t) + f;
        f = t;
    }
    if (c != 0.0 && finite(c)) f += c;
    return f;
}

static i64 push_bytes(i64 m) {   /* encode_strip's size for a strip of m indices */
    i64 pairs = m / 2;
    return 20 + 4 * pairs + 4 * ((pairs + CHUNK - 1) / CHUNK) + 8 * (m % 2);
}

static i64 least_push(i64 n) {   /* _least_push */
    i64 a = push_bytes(n + 2), b = push_bytes(n + 3);
    return a < b ? a : b;
}

#define NONE INT64_MIN

/* code_entry: the palette entry a slot code names, NONE for none; any negative entry is -1 */
static i64 code_entry(i64 b) {
    if (b >= 0x100) return b - 0x100;
    if (b < 0) return -1;
    if (b == 0 || b == 13 || b > 32) return NONE;
    return b <= 12 ? b - 1 : b - 2;
}

static i64 slot_code(i64 e) { return 0 <= e && e < PALETTE_MAX ? (e <= 11 ? e + 1 : e + 2) : 0x100 + e; }

static void isort(i64 *x, i64 n) {   /* integers ascending (a heapsort) */
    for (i64 i = n / 2 - 1; i >= 0; i--)
        for (i64 j = i;;) {
            i64 l = 2 * j + 1, r = l + 1, m = j;
            if (l < n && x[m] < x[l]) m = l;
            if (r < n && x[m] < x[r]) m = r;
            if (m == j) break;
            i64 v = x[j];
            x[j] = x[m], x[m] = v, j = m;
        }
    for (i64 end = n - 1; end > 0; end--) {
        i64 v = x[0];
        x[0] = x[end], x[end] = v;
        for (i64 j = 0;;) {
            i64 l = 2 * j + 1, r = l + 1, m = j;
            if (l < end && x[m] < x[l]) m = l;
            if (r < end && x[m] < x[r]) m = r;
            if (m == j) break;
            v = x[j];
            x[j] = x[m], x[m] = v, j = m;
        }
    }
}

/* (key, index) ascending, as sorted(c, key=lambda k: (centres[k][axis], k)): no key is a NaN */
static int kless(const double *key, i64 stride, i64 a, i64 b) {
    double x = key[stride * a], y = key[stride * b];
    return x < y || (x == y && a < b);
}

static void ksort(i64 *x, i64 n, const double *key, i64 stride) {
    for (i64 i = n / 2 - 1; i >= 0; i--)
        for (i64 j = i;;) {
            i64 l = 2 * j + 1, r = l + 1, m = j;
            if (l < n && kless(key, stride, x[m], x[l])) m = l;
            if (r < n && kless(key, stride, x[m], x[r])) m = r;
            if (m == j) break;
            i64 v = x[j];
            x[j] = x[m], x[m] = v, j = m;
        }
    for (i64 end = n - 1; end > 0; end--) {
        i64 v = x[0];
        x[0] = x[end], x[end] = v;
        for (i64 j = 0;;) {
            i64 l = 2 * j + 1, r = l + 1, m = j;
            if (l < end && kless(key, stride, x[m], x[l])) m = l;
            if (r < end && kless(key, stride, x[m], x[r])) m = r;
            if (m == j) break;
            v = x[j];
            x[j] = x[m], x[m] = v, j = m;
        }
    }
}

typedef struct { i64 *at, used; } Take;

static i64 *take(Take *k, i64 n) {
    i64 *p = k->at ? k->at + k->used : 0;
    k->used += n;
    return p;
}

typedef struct {
    i64 *dense, *vb, *tb, *tbn, *hslot, *setof, *sfirst, *scl, *cur, *perm, *stack, *vstamp, *vlocal, *pstamp,
        *nfirst, *tmark, *order, *tmp, *sout, *swork;
    i64 hmask;
} R;

static i64 pow2(i64 n) {
    i64 h = 8;
    while (h < n) h *= 2;
    return h;
}

static void layout(Take *k, R *r, i64 nv, i64 nt, i64 np) {
    i64 H = pow2(2 * nt), most = nt < FIT_MAX ? nt : FIT_MAX;
    r->hmask = H - 1;
    r->dense = take(k, np), r->vb = take(k, 4 * nv), r->tb = take(k, 12 * nt), r->tbn = take(k, nt);
    r->hslot = take(k, H), r->setof = take(k, nt), r->sfirst = take(k, nt), r->scl = take(k, nt);
    r->cur = take(k, np), r->perm = take(k, nt), r->stack = take(k, 2 * nt + 4);
    r->vstamp = take(k, nv), r->vlocal = take(k, nv), r->pstamp = take(k, np), r->nfirst = take(k, np);
    r->tmark = take(k, nt), r->order = take(k, nt), r->tmp = take(k, nt);
    r->sout = take(k, 6 * most + 8), r->swork = take(k, az_strip_need(most));
}

/* The words az_regroup's work needs: nv vertices, nt triangles, np palette entries. */
API i64 az_regroup_need(i64 nv, i64 nt, i64 np) {
    Take k = {0, 0};
    R r;
    layout(&k, &r, nv, nt, np);
    return k.used + 8;
}

static u64 set_hash(const i64 *ids, i64 n) {
    u64 h = 0x84222325CBF29CE4ull ^ (u64)n;
    for (i64 i = 0; i < n; i++) h = mix((i64)h, ids[i]);
    return h;
}

/* body_codec.regroup's split of a group that doesn't fit (its twin _split): its nv vertices' weights w and slot codes
 * s (four each) and positions (three), its np palette entries pal, its nt triangles t. Each part, in the twin's order:
 * parts[3p..3p+2] the ends of its triangles (ploc: three corners each, in their order, renumbered), of its vertices
 * (pvert: the group's, ascending; pcode: four slot codes each) and of its palette (ppal: the group's palette entries
 * it keeps, in order); *nparts the parts. 0, 1 where cap_parts or cap_pal can't hold them, or TWIN
 * where the twin raises or a centre isn't finite. dwork: 3nt doubles; work: az_regroup_need words. */
API i64 az_regroup(i64 nv, const double *w, const i64 *s, const double *pos, i64 np, const i64 *pal, i64 nt,
                   const i64 *t, i64 cap_parts, i64 cap_pal, i64 *nparts, i64 *parts, i64 *pvert, i64 *ploc, i64 *ppal, i64 *pcode, double *dwork, i64 *work) {
    Take k = {work, 0};
    R r;
    layout(&k, &r, nv, nt, np);
    *nparts = 0;
    if (nt == 0) return TWIN;
    for (i64 i = 0; i < 3 * nt; i++)
        if (t[i] < 0 || t[i] >= nv) return TWIN;   /* an index the twin's lists take otherwise or refuse */
    for (i64 e = 0; e < np; e++) {   /* each entry's bone as the first entry of its value */
        r.dense[e] = e;
        for (i64 f = 0; f < e; f++)
            if (pal[f] == pal[e]) {
                r.dense[e] = f;
                break;
            }
    }
    for (i64 v = 0; v < nv; v++) {   /* _bone_skin: the bones of each weight past 0, once each */
        i64 n = 0, *b = r.vb + 4 * v;
        for (int i = 0; i < 4; i++) {
            if (!(w[4 * v + i] > 0)) continue;
            i64 e = code_entry(s[4 * v + i]);
            if (e == NONE || e < 0 || e >= np) return TWIN;
            i64 d = r.dense[e], seen = 0;
            for (i64 j = 0; j < n; j++) seen |= b[j] == d;
            if (!seen) b[n++] = d;
        }
        for (i64 j = n; j < 4; j++) b[j] = -1;
    }
    for (i64 h = 0; h <= r.hmask; h++) r.hslot[h] = 0;
    i64 sets = 0;
    for (i64 q = 0; q < nt; q++) {   /* tri_bones, and the sets in their first triangles' order (left's keys) */
        i64 *ids = r.tb + 12 * q, n = 0;
        for (int c = 0; c < 3; c++)
            for (int i = 0; i < 4; i++) {
                i64 d = r.vb[4 * t[3 * q + c] + i], j = n;
                if (d < 0) continue;
                while (j > 0 && ids[j - 1] > d) j--;
                if (j > 0 && ids[j - 1] == d) continue;
                for (i64 m = n; m > j; m--) ids[m] = ids[m - 1];
                ids[j] = d, n++;
            }
        if (n > PALETTE_MAX) return TWIN;
        r.tbn[q] = n;
        u64 h = set_hash(ids, n) & (u64)r.hmask;
        for (;; h = (h + 1) & (u64)r.hmask) {
            i64 x = r.hslot[h];
            if (x == 0) {
                r.hslot[h] = sets + 1, r.sfirst[sets] = q, r.scl[sets] = -1, r.setof[q] = sets++;
                break;
            }
            const i64 *o = r.tb + 12 * r.sfirst[x - 1];
            i64 on = r.tbn[r.sfirst[x - 1]], same = on == n;
            for (i64 j = 0; same && j < n; j++) same = o[j] == ids[j];
            if (same) {
                r.setof[q] = x - 1;
                break;
            }
        }
    }
    i64 left = sets, cursor = 0, clusters = 0;
    while (left > 0) {   /* the clusters: grown from the first set left by those it holds, then the fewest new bones */
        while (r.scl[cursor] != -1) cursor++;
        for (i64 d = 0; d < np; d++) r.cur[d] = 0;
        i64 count = 0, *first = r.tb + 12 * r.sfirst[cursor];
        for (i64 j = 0; j < r.tbn[r.sfirst[cursor]]; j++) r.cur[first[j]] = 1, count++;
        for (;;) {
            i64 best = -1, least = 0;
            for (i64 x = cursor; x < sets; x++) {
                if (r.scl[x] != -1) continue;
                const i64 *ids = r.tb + 12 * r.sfirst[x];
                i64 n = r.tbn[r.sfirst[x]], miss = 0;
                for (i64 j = 0; j < n; j++) miss += !r.cur[ids[j]];
                if (miss == 0) r.scl[x] = clusters, left--;
            }
            for (i64 x = cursor; x < sets; x++) {
                if (r.scl[x] != -1) continue;
                const i64 *ids = r.tb + 12 * r.sfirst[x];
                i64 n = r.tbn[r.sfirst[x]], miss = 0;
                for (i64 j = 0; j < n; j++) miss += !r.cur[ids[j]];
                if (best < 0 || miss < least) best = x, least = miss;
            }
            if (best < 0 || count + least > PALETTE_MAX) break;
            const i64 *ids = r.tb + 12 * r.sfirst[best];
            for (i64 j = 0; j < r.tbn[r.sfirst[best]]; j++)
                if (!r.cur[ids[j]]) r.cur[ids[j]] = 1, count++;
        }
        clusters++;
    }
    for (i64 c = 0; c < clusters; c++) r.order[c] = 0;   /* each cluster's triangles, ascending, clusters in order */
    for (i64 q = 0; q < nt; q++) r.order[r.scl[r.setof[q]]]++;
    for (i64 c = 0, at = 0; c < clusters; c++) {
        i64 n = r.order[c];
        r.order[c] = at, r.tmp[c] = at, at += n;
    }
    for (i64 q = 0; q < nt; q++) r.perm[r.tmp[r.scl[r.setof[q]]]++] = q;
    double *cen = dwork;
    for (i64 q = 0; q < nt; q++)
        for (int c = 0; c < 3; c++) {
            double x = sum3(pos[3 * t[3 * q] + c], pos[3 * t[3 * q + 1] + c], pos[3 * t[3 * q + 2] + c]) / 3.0;
            if (!finite(x)) return TWIN;
            cen[3 * q + c] = x;
        }
    i64 top = 0;   /* todo: a stack of [start, end) of perm, the next on top */
    for (i64 c = clusters - 1; c >= 0; c--) r.stack[2 * top] = r.order[c], r.stack[2 * top + 1] = r.tmp[c], top++;
    for (i64 v = 0; v < nv; v++) r.vstamp[v] = 0;
    for (i64 d = 0; d < np; d++) r.pstamp[d] = 0, r.nfirst[d] = 0;
    for (i64 q = 0; q < nt; q++) r.tmark[q] = 0;
    i64 stamp = 0, np_out = 0, tri_at = 0, vert_at = 0, pal_at = 0;
    while (top > 0) {
        top--;
        i64 s0 = r.stack[2 * top], s1 = r.stack[2 * top + 1], n = s1 - s0, used = 0, npal = 0;
        stamp++;
        for (i64 i = s0; i < s1; i++)   /* _subgroup: its vertices and the bones they weigh */
            for (int c = 0; c < 3; c++) {
                i64 v = t[3 * r.perm[i] + c];
                if (r.vstamp[v] == stamp) continue;
                r.vstamp[v] = stamp, pvert[vert_at + used++] = v;
                for (int j = 0; j < 4 && r.vb[4 * v + j] >= 0; j++) r.pstamp[r.vb[4 * v + j]] = stamp;
            }
        for (i64 e = 0; e < np; e++) npal += r.pstamp[r.dense[e]] == stamp;
        int fits = npal <= PALETTE_MAX && used <= INDEX_MAX + 1 && least_push(n) <= PUSH_MAX;
        if (fits) {   /* the strip of its triangles, renumbered by its vertices in order */
            isort(pvert + vert_at, used);
            for (i64 j = 0; j < used; j++) r.vlocal[pvert[vert_at + j]] = j;
            for (i64 i = s0; i < s1; i++)
                for (int c = 0; c < 3; c++) ploc[3 * tri_at + 3 * (i - s0) + c] = r.vlocal[t[3 * r.perm[i] + c]];
            i64 len = 0;
            if (n > FIT_MAX) return TWIN;   /* never: least_push refuses it */
            if (strip_run(ploc + 3 * tri_at, n, r.sout, &len, r.swork) != 0) return TWIN;
            fits = push_bytes(len) <= PUSH_MAX;
        }
        if (fits) {   /* a part: its triangles, its palette, its vertices' slot codes in it */
            if (np_out == cap_parts || pal_at + npal > cap_pal) return 1;
            i64 m = 0;
            for (i64 e = 0; e < np; e++) {
                i64 d = r.dense[e];
                if (r.pstamp[d] != stamp) continue;
                ppal[pal_at + m] = e;
                m++;
            }
            for (i64 j = m - 1; j >= 0; j--) r.nfirst[r.dense[ppal[pal_at + j]]] = j;   /* the first entry of each */
            for (i64 j = 0; j < used; j++) {
                i64 v = pvert[vert_at + j];
                for (int i = 0; i < 4; i++)
                    pcode[4 * (vert_at + j) + i] = w[4 * v + i] > 0 ? slot_code(r.nfirst[r.dense[code_entry(s[4 * v + i])]])
                                                                    : 0;
            }
            tri_at += n, vert_at += used, pal_at += m;
            parts[3 * np_out] = tri_at, parts[3 * np_out + 1] = vert_at, parts[3 * np_out + 2] = pal_at;
            np_out++;
            continue;
        }
        if (n <= 1) return TWIN;   /* "a single triangle doesn't fit a group" */
        int axis = 0;   /* halved across its widest extent (the first of equals) at the median */
        double wide = 0.0;
        for (int a = 0; a < 3; a++) {
            double hi = cen[3 * r.perm[s0] + a], lo = hi;
            for (i64 i = s0 + 1; i < s1; i++) {
                double x = cen[3 * r.perm[i] + a];
                if (x > hi) hi = x;
                if (x < lo) lo = x;
            }
            if (a == 0 || hi - lo > wide) axis = a, wide = hi - lo;
        }
        for (i64 i = s0; i < s1; i++) r.order[i - s0] = r.perm[i];
        ksort(r.order, n, cen + axis, 3);
        for (i64 i = 0; i < n / 2; i++) r.tmark[r.order[i]] = stamp;
        i64 a = 0;
        for (i64 i = s0; i < s1; i++)
            if (r.tmark[r.perm[i]] == stamp) r.tmp[a++] = r.perm[i];
        i64 h = a;
        for (i64 i = s0; i < s1; i++)
            if (r.tmark[r.perm[i]] != stamp) r.tmp[a++] = r.perm[i];
        for (i64 i = 0; i < n; i++) r.perm[s0 + i] = r.tmp[i];
        r.stack[2 * top] = s0 + h, r.stack[2 * top + 1] = s1, top++;   /* the second half after the first */
        r.stack[2 * top] = s0, r.stack[2 * top + 1] = s0 + h, top++;
    }
    *nparts = np_out;
    return 0;
}

/* ---- the checks: body_codec.problems' of a group's vertices and triangles (its twin _vertex_problem, _bad) ------- */
/* Each of nv vertices' 14 floats f (position, weights, normal, uv, extra) and 4 slot codes s, against a palette of np
 * entries: res[0] the first vertex the twin names (-1: none), res[1] what it names (1 a float not finite, 2 a negative
 * weight, 3 a slot code outside the palette, 4 weights not summing to 1, their sum in *total), res[2] the triangles
 * of t (nt, three corners each) that repeat a vertex or name one past nv. Always 0. */
API i64 az_checks(i64 nv, const double *f, const i64 *s, i64 np, i64 fixable, i64 nt, const i64 *t, i64 *res,
                  double *total) {
    res[0] = -1, res[1] = 0, res[2] = 0, *total = 0.0;
    for (i64 j = 0; j < nv && res[0] < 0; j++) {
        const double *x = f + 14 * j, *wt = x + 3;
        const i64 *b = s + 4 * j;
        int kind = 0;
        for (int i = 0; i < 14 && !kind; i++)
            if (!(x[i] == x[i] && fab(x[i]) != __builtin_inf())) kind = 1;
        for (int i = 0; i < 4 && !kind; i++)
            if (wt[i] < 0) kind = 2;
        double live[4];
        int n = 0;
        for (int i = 0; i < 4 && !kind; i++) {
            if (!(wt[i] > 0)) continue;
            live[n++] = wt[i];
            i64 e = code_entry(b[i]);
            if ((b[i] > 0xFF && fixable) || e == NONE || e >= np) kind = 3;
        }
        if (!kind && n > 0) {
            double sum = 0.0 + live[0], c = 0.0;   /* sum(): Neumaier's, as Python's */
            for (int i = 1; i < n; i++) {
                double u = sum + live[i];
                if (fab(sum) >= fab(live[i])) c += (sum - u) + live[i];
                else c += (live[i] - u) + sum;
                sum = u;
            }
            if (c != 0.0 && finite(c)) sum += c;
            if (fab(sum - 1.0) > 1e-5) kind = 4, *total = sum;
        }
        if (kind) res[0] = j, res[1] = kind;
    }
    for (i64 q = 0; q < nt; q++) {
        i64 a = t[3 * q], b = t[3 * q + 1], c = t[3 * q + 2];
        res[2] += a == b || b == c || a == c || a < 0 || a >= nv || b < 0 || b >= nv || c < 0 || c >= nv;
    }
    return 0;
}

/* ---- the read-back: write_asset's test that two groups draw the same triangles (its twin the sorted compare) ----- */
/* Whether triangles a (na, three corners each) and b (nb) are the same when each is turned to lead with its least
 * corner (the first of equals) and both sorted: 1 or 0. work: 3(na + nb) words. */
API i64 az_same(const i64 *a, i64 na, const i64 *b, i64 nb, i64 *work) {
    if (na != nb) return 0;
    i64 *x = work, *y = work + 3 * na;
    for (i64 q = 0; q < na; q++) canonical(a[3 * q], a[3 * q + 1], a[3 * q + 2], x + 3 * q);
    for (i64 q = 0; q < nb; q++) canonical(b[3 * q], b[3 * q + 1], b[3 * q + 2], y + 3 * q);
    tsort(x, na);
    tsort(y, nb);
    for (i64 i = 0; i < 3 * na; i++)
        if (x[i] != y[i]) return 0;
    return 1;
}
