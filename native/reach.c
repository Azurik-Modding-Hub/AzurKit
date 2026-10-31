/* The randomizer's reach, compiled (D1009): the solver's least fixpoint (planner/solver.py's Logic._solve with
 * _escaping, _returners, _escape, _closure and _bfs, the simple algorithm) over the packed tables
 * azurkit.core.native.Tables writes. Integer logic only: no float, no libm, no allocation (the caller passes the
 * workspace az_reach_need sizes). Its Python twin, the reference and the fallback, is native.py's _twin;
 * tests/test_native.py holds the two equal bit for bit. Built by nativekit (C99, zig cc). */
#include <stdint.h>

#if defined(_WIN32)
#define API __declspec(dllexport)
#else
#define API __attribute__((visibility("default")))
#endif

typedef int64_t i64;
typedef uint64_t u64;

#define ABI 1
#define MAGIC 0x314843524b5aLL   /* "ZKRCH1" */

/* The rules' bytecode: each rule starts at a word of the table; and/or name their children by position. */
enum { OP_FALSE, OP_TRUE, OP_COUNTER, OP_FLAG, OP_SUM, OP_AND, OP_OR };
/* The header's words; every offset is a word of the table. */
enum { H_MAGIC, H_ABI, H_N, H_F, H_L, H_C, H_I, H_START, H_G, H_KMAX, H_MMAX, H_ITEMS, H_DISC, H_YIELD, H_REFUND,
       H_FORCED, H_FORCED_PHYS, H_REGIONS, H_GRAPHS };
/* A graph's words. */
enum { G_ADJ, G_RADJ, G_K, G_CREDITS, G_CBN, G_M, G_LOCS, G_T, G_TELE, G_VICTORY };
/* A call's words. */
enum { C_GRAPH, C_PHYS, C_FREE, C_COLLECTED, C_TRAPS, C_LOG_CAP };

typedef struct {
    const i64 *t, *gives;
    i64 n, f, l, c, it, start, nw, fw, lw, kw;
    i64 *queue, *list, *ec, *eh;
    u64 *base, *one, *home, *dead, *eflags, *etook, *eseen, *esrc, *holds, *at, *newf, *maybe, *eout, *settable,
        *fseen, *fflags, *now, *found, *walked;
} K;

static int has(const u64 *b, i64 i) { return (int)((b[i >> 6] >> (i & 63)) & 1u); }
static void put(u64 *b, i64 i) { b[i >> 6] |= (u64)1 << (i & 63); }
static void clear(u64 *b, i64 w) { for (i64 k = 0; k < w; k++) b[k] = 0; }
static void copy(u64 *d, const u64 *s, i64 w) { for (i64 k = 0; k < w; k++) d[k] = s[k]; }
static void join(u64 *d, const u64 *s, i64 w) { for (i64 k = 0; k < w; k++) d[k] |= s[k]; }
static int none(const u64 *b, i64 w) {
    for (i64 k = 0; k < w; k++)
        if (b[k]) return 0;
    return 1;
}

static int ev(const i64 *t, i64 pc, const i64 *c, const u64 *f) {
    const i64 *p = t + pc;
    switch (p[0]) {
    case OP_TRUE: return 1;
    case OP_COUNTER: return c[p[1]] >= p[2];
    case OP_FLAG: return has(f, p[1]);
    case OP_SUM: {
        i64 s = 0;
        for (i64 k = 0; k < p[2]; k++) s += c[p[3 + k]];
        return s >= p[1];
    }
    case OP_AND:
        for (i64 k = 0; k < p[1]; k++)
            if (!ev(t, p[2 + k], c, f)) return 0;
        return 1;
    case OP_OR:
        for (i64 k = 0; k < p[1]; k++)
            if (ev(t, p[2 + k], c, f)) return 1;
        return 0;
    default: return 0;
    }
}

/* Whether item `name` adds to counter `key` (Logic.items[name].get(key, 0) > 0). */
static int adds(const K *k, i64 name, i64 key) {
    const i64 *t = k->t, *io = t + t[H_ITEMS];
    for (i64 e = io[name]; e < io[name + 1]; e += 2)
        if (t[e] == key && t[e + 1] > 0) return 1;
    return 0;
}

/* Logic._take: collect location `loc` (its item, its yield; a disc counter counts the first copy; a refund key
 * taken off its spot drops its pending counter). */
static void take(const K *k, i64 *held, i64 *c, i64 loc) {
    const i64 *t = k->t, *io = t + t[H_ITEMS];
    i64 name = k->gives[loc];
    if (name < 0) return;
    i64 n = t[t[H_YIELD] + loc], key = t[t[H_REFUND] + 2 * loc], pend = t[t[H_REFUND] + 2 * loc + 1];
    int first = held[name] == 0;
    held[name] += n;
    for (i64 e = io[name]; e < io[name + 1]; e += 2) {
        i64 cn = t[e], inc = t[e + 1];
        c[cn] += t[t[H_DISC] + cn] ? (first ? inc : 0) : inc * n;
    }
    if (key >= 0 && adds(k, name, key) && c[pend] > 0) c[pend] -= 1;
}

/* Logic._bfs: the nodes reached from `src` over the CSR at word `adj`. */
static void bfs(const K *k, i64 adj, const u64 *src, const i64 *c, const u64 *f, u64 *seen) {
    const i64 *t = k->t, *off = t + adj;
    i64 head = 0, tail = 0;
    copy(seen, src, k->nw);
    for (i64 u = 0; u < k->n; u++)
        if (has(src, u)) k->queue[tail++] = u;
    while (head < tail) {
        i64 u = k->queue[head++];
        for (i64 e = off[u]; e < off[u + 1]; e += 2) {
            i64 v = t[e];
            if (!has(seen, v) && ev(t, t[e + 1], c, f)) {
                put(seen, v);
                k->queue[tail++] = v;
            }
        }
    }
}

/* Logic._closure (no `never`): from the start, the nodes reached and the flags credited where they are. */
static void closure(const K *k, const i64 *g, const i64 *c, const u64 *fin, u64 *seen, u64 *fl) {
    const i64 *t = k->t, *cr = t + g[G_CREDITS];
    copy(fl, fin, k->fw);
    clear(k->one, k->nw);
    put(k->one, k->start);
    for (;;) {
        int any = 0;
        bfs(k, g[G_ADJ], k->one, c, fl, seen);
        clear(k->newf, k->fw);
        for (i64 j = 0; j < g[G_K]; j++) {
            const i64 *r = cr + 4 * j;
            if (!has(fl, r[0]) && has(seen, r[1]) && ev(t, r[3], c, fl)) {
                put(k->newf, r[0]);
                any = 1;
            }
        }
        if (!any) return;
        join(fl, k->newf, k->fw);
    }
}

/* Logic._returners: the backward search from the start, an edge passable on `base` and the flags its own source
 * node can set on them. */
static void returners(const K *k, const i64 *g, const i64 *c, const u64 *base, u64 *seen) {
    const i64 *t = k->t, *cr = t + g[G_CREDITS], *cbn = t + g[G_CBN], *off = t + g[G_RADJ];
    i64 head = 0, tail = 0;
    clear(k->holds, k->kw);
    for (i64 j = 0; j < g[G_K]; j++)
        if (!has(base, cr[4 * j]) && ev(t, cr[4 * j + 3], c, base)) put(k->holds, j);
    clear(seen, k->nw);
    put(seen, k->start);
    k->queue[tail++] = k->start;
    while (head < tail) {
        i64 v = k->queue[head++];
        for (i64 e = off[v]; e < off[v + 1]; e += 2) {
            i64 u = t[e];
            const u64 *fu = base;
            if (has(seen, u)) continue;
            for (i64 j = cbn[u]; j < cbn[u + 1]; j++)
                if (has(k->holds, t[j])) {
                    if (fu == base) {
                        copy(k->at, base, k->fw);
                        fu = k->at;
                    }
                    put(k->at, cr[4 * t[j]]);
                }
            if (ev(t, t[e + 1], c, fu)) {
                put(seen, u);
                k->queue[tail++] = u;
            }
        }
    }
}

/* Logic._escape: the local closure from `node` with the round's state, starting with k->eflags; 1 once it reaches
 * the start. Leaves the nodes seen in k->eseen, the flags in k->eflags. */
static int escape(const K *k, const i64 *g, const i64 *c, const i64 *held, const u64 *got, i64 node) {
    const i64 *t = k->t, *cr = t + g[G_CREDITS], *lc = t + g[G_LOCS], *tp = t + g[G_TELE];
    for (i64 j = 0; j < k->c; j++) k->ec[j] = c[j];
    for (i64 j = 0; j < k->it; j++) k->eh[j] = held[j];
    copy(k->etook, got, k->lw);
    clear(k->esrc, k->nw);
    put(k->esrc, node);
    for (;;) {
        int any = 0;
        i64 nl = 0;
        bfs(k, g[G_ADJ], k->esrc, k->ec, k->eflags, k->eseen);
        if (has(k->eseen, k->start)) return 1;
        for (i64 j = 0; j < g[G_T]; j++) {
            const i64 *r = tp + 4 * j;
            if (has(k->eseen, r[0]) && !has(k->eseen, r[1]) && !has(got, r[3]) && ev(t, r[2], k->ec, k->eflags)) {
                put(k->esrc, r[1]);
                any = 1;
            }
        }
        for (i64 j = 0; j < g[G_M]; j++) {
            const i64 *r = lc + 3 * j;
            if (!has(k->etook, r[0]) && has(k->eseen, r[1]) && ev(t, r[2], k->ec, k->eflags)) k->list[nl++] = r[0];
        }
        clear(k->newf, k->fw);
        for (i64 j = 0; j < g[G_K]; j++) {
            const i64 *r = cr + 4 * j;
            if (!has(k->eflags, r[0]) && has(k->eseen, r[1]) && ev(t, r[3], k->ec, k->eflags)) {
                put(k->newf, r[0]);
                any = 1;
            }
        }
        if (!any && !nl) return 0;
        for (i64 j = 0; j < nl; j++) {
            put(k->etook, k->list[j]);
            take(k, k->eh, k->ec, k->list[j]);
        }
        join(k->eflags, k->newf, k->fw);
    }
}

/* Whether every flag of the `forced` CSR's row `m` that is `credited` is in `fl`. */
static int within(const K *k, const i64 *fo, i64 m, const u64 *credited, const u64 *fl) {
    for (i64 j = fo[m]; j < fo[m + 1]; j++)
        if (has(credited, k->t[j]) && !has(fl, k->t[j])) return 0;
    return 1;
}

/* Logic._escaping: those of `nodes` whose escape holds; a failed closure fails every node it saw whose starting
 * flags it held. Nodes in ascending id order (the solver's sorted order). */
static void escaping(const K *k, const i64 *g, const i64 *c, const i64 *held, const u64 *got, const u64 *nodes,
                     i64 forced, const u64 *credited, u64 *out) {
    const i64 *t = k->t, *fo = t + t[forced];
    clear(out, k->nw);
    if (none(nodes, k->nw)) return;
    returners(k, g, c, k->base, k->home);
    for (i64 w = 0; w < k->nw; w++) out[w] = nodes[w] & k->home[w];
    clear(k->dead, k->nw);
    for (i64 n = 0; n < k->n; n++) {
        if (!has(nodes, n) || has(k->home, n) || has(k->dead, n)) continue;
        copy(k->eflags, k->base, k->fw);
        for (i64 j = fo[n]; j < fo[n + 1]; j++)
            if (has(credited, t[j])) put(k->eflags, t[j]);
        if (escape(k, g, c, held, got, n)) {
            put(out, n);
            continue;
        }
        for (i64 w = 0; w < k->nw; w++)
            for (u64 bits = k->eseen[w]; bits; bits &= bits - 1) {
                i64 m = w * 64 + __builtin_ctzll(bits);
                if (within(k, fo, m, credited, k->eflags)) put(k->dead, m);
            }
    }
}

/* The workspace one call needs: its u64 words; `ints[0]` gets its i64 words. */
API i64 az_reach_need(const i64 *t, i64 *ints) {
    i64 nw = (t[H_N] + 63) / 64, fw = (t[H_F] + 63) / 64, lw = (t[H_L] + 63) / 64, kw = (t[H_KMAX] + 63) / 64;
    ints[0] = t[H_N] + t[H_MMAX] + t[H_C] + t[H_I] + 4;
    return 12 * nw + 6 * fw + 2 * lw + kw + 4;
}

API i64 az_abi(void) { return ABI; }

/* Logic._solve: the rounds of R, Safe, R_phys and the traps, collecting what is safe, until a round adds nothing.
 * `counters`, `held`, `flags` and `got` are the state, updated in place; `late` the guardian slots collected only
 * from the round that reaches them; `gives` each location's item (or -1). `out` gets the rounds and the victory.
 * Returns 0, -1 when the tables aren't this build's, -2 when the rounds outgrow the log. */
API i64 az_reach(const i64 *t, const i64 *call, i64 *counters, i64 *held, u64 *flags, u64 *got, const u64 *late,
                 const i64 *gives, u64 *reached, u64 *safe, u64 *phys, u64 *traps, u64 *after, u64 *freed,
                 i64 *loc_round, i64 *flag_round, u64 *found_log, u64 *walked_log, i64 *out, u64 *wb, i64 *wi) {
    K k;
    if (t[H_MAGIC] != MAGIC || t[H_ABI] != ABI) return -1;
    k.t = t;
    k.gives = gives;
    k.n = t[H_N], k.f = t[H_F], k.l = t[H_L], k.c = t[H_C], k.it = t[H_I], k.start = t[H_START];
    k.nw = (k.n + 63) / 64, k.fw = (k.f + 63) / 64, k.lw = (k.l + 63) / 64, k.kw = (t[H_KMAX] + 63) / 64;
    k.queue = wi, k.list = wi + k.n, k.ec = k.list + t[H_MMAX], k.eh = k.ec + k.c;
    k.base = wb, k.one = k.base + k.fw, k.home = k.one + k.nw, k.dead = k.home + k.nw, k.eflags = k.dead + k.nw;
    k.etook = k.eflags + k.fw, k.eseen = k.etook + k.lw, k.esrc = k.eseen + k.nw, k.holds = k.esrc + k.nw;
    k.at = k.holds + k.kw, k.newf = k.at + k.fw, k.maybe = k.newf + k.fw, k.eout = k.maybe + k.nw;
    k.settable = k.eout + k.nw, k.fseen = k.settable + k.fw, k.fflags = k.fseen + k.nw, k.now = k.fflags + k.fw;
    k.found = k.now + k.lw, k.walked = k.found + k.nw;

    const i64 *gs = t + t[H_GRAPHS];
    const i64 *rg = t + gs[call[C_GRAPH]], *pg = t + gs[call[C_PHYS]], *fg = t + gs[call[C_FREE]];
    const i64 *lc = t + rg[G_LOCS], *cr = t + rg[G_CREDITS], *rf = t + t[H_REFUND];
    i64 cap = call[C_LOG_CAP];

    copy(k.base, flags, k.fw);
    clear(safe, k.nw);
    put(safe, k.start);
    for (i64 loc = 0; loc < k.l; loc++)   /* Logic._pending */
        if (rf[2 * loc] >= 0 && !has(got, loc) && gives[loc] >= 0 && adds(&k, gives[loc], rf[2 * loc])
            && counters[rf[2 * loc + 1]] < 1)
            counters[rf[2 * loc + 1]] = 1;
    for (i64 w = 0; w < k.lw; w++) got[w] &= ~late[w];
    clear(k.now, k.lw);
    clear(traps, k.nw);
    clear(freed, k.nw);
    for (i64 j = 0; j < k.l; j++) loc_round[j] = -1;
    for (i64 j = 0; j < k.f; j++) flag_round[j] = -1;
    for (i64 round = 0;; round++) {
        int any = 0;
        i64 nl = 0;
        clear(k.one, k.nw);
        put(k.one, k.start);
        bfs(&k, rg[G_ADJ], k.one, counters, flags, reached);
        for (i64 w = 0; w < k.nw; w++) k.maybe[w] = reached[w] & ~safe[w];
        escaping(&k, rg, counters, held, got, k.maybe, H_FORCED, flags, k.eout);
        join(safe, k.eout, k.nw);
        if (call[C_TRAPS]) {
            closure(&k, pg, counters, flags, phys, k.settable);
        } else {
            clear(phys, k.nw);
            clear(k.settable, k.fw);
        }
        for (i64 w = 0; w < k.nw; w++) k.maybe[w] = phys[w] & ~safe[w];
        escaping(&k, pg, counters, held, got, k.maybe, H_FORCED_PHYS, k.settable, k.eout);
        for (i64 w = 0; w < k.nw; w++) k.found[w] = k.maybe[w] & ~k.eout[w];
        if (call[C_FREE] == call[C_PHYS] || none(k.found, k.nw)) {
            copy(k.walked, k.found, k.nw);
        } else {
            closure(&k, fg, counters, flags, k.fseen, k.fflags);
            for (i64 w = 0; w < k.nw; w++) k.walked[w] = k.found[w] & k.fseen[w];
        }
        join(traps, k.found, k.nw);
        join(freed, k.walked, k.nw);
        if (cap) {
            if (round >= cap) return -2;
            copy(found_log + round * k.nw, k.found, k.nw);
            copy(walked_log + round * k.nw, k.walked, k.nw);
        }
        for (i64 j = 0; j < rg[G_M]; j++) {
            const i64 *r = lc + 3 * j;
            if (!has(got, r[0]) && !has(k.now, r[0]) && has(safe, r[1]) && ev(t, r[2], counters, flags))
                k.list[nl++] = r[0];
        }
        clear(k.newf, k.fw);
        for (i64 j = 0; j < rg[G_K]; j++) {
            const i64 *r = cr + 4 * j;
            if (!has(flags, r[0]) && (has(safe, r[1]) || (r[2] && has(reached, r[1]))) && ev(t, r[3], counters, flags)) {
                put(k.newf, r[0]);
                any = 1;
            }
        }
        if (!any && !nl) {
            const i64 *rs = t + t[H_REGIONS];   /* [R, R slots, R + 1 offsets, nodes] */
            join(got, late, k.lw);
            clear(after, k.nw);
            for (i64 j = 0; j < rs[0]; j++)
                if (has(got, rs[1 + j]))
                    for (i64 e = rs[1 + rs[0] + j]; e < rs[2 + rs[0] + j]; e++)
                        if (has(phys, t[e])) put(after, t[e]);
            join(got, k.now, k.lw);
            out[0] = round + 1;
            out[1] = ev(t, rg[G_VICTORY], counters, flags);
            return 0;
        }
        for (i64 j = 0; j < nl; j++) {
            i64 loc = k.list[j];
            loc_round[loc] = round;
            if (call[C_COLLECTED]) {
                if (has(late, loc)) put(got, loc);
                put(k.now, loc);
            } else {
                put(got, loc);
                take(&k, held, counters, loc);
            }
        }
        for (i64 j = 0; j < k.f; j++)
            if (has(k.newf, j)) flag_round[j] = round;
        join(flags, k.newf, k.fw);
    }
}
