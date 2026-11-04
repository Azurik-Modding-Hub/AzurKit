/* The randomizer's reach, compiled (D1009): the solver's least fixpoint (planner/solver.py's Logic._solve with
 * _escaping, _returners, _escape, _closure and _bfs, the simple algorithm) over the packed tables
 * azurkit.core.native.Tables writes. Integer logic only: no float, no libm, no allocation (the caller passes the
 * workspace az_reach_need sizes). Its Python twin, the reference and the fallback, is native.py's _twin;
 * tests/test_native.py holds the two equal bit for bit. Built by nativekit (C99, zig cc).
 *
 * Its answer is the twin's; its work is less (Step 4.4bk): sets are walked a word at a time, an escape reads only
 * the locations and credits of the nodes it has seen (each graph's rows by node, in the tables), a credit's verdict
 * in the backward search is worked out once its node is asked, and on tables whose takes never make a rule false
 * (H_MONO: no item lowers a counter and a refund key's pending counter is read only in sums that hold the key as
 * often) the state only grows from round to round, so: an escape ends once it reaches a node of the round's
 * backward search, which from there it would reach the start from (each credit that search let its node set is one
 * the escape credits there, and every edge it passed stays passable as the escape's state grows); and the searches
 * from the start (R, the backward one, R_phys's and the trick-free closures) are kept across the rounds, each
 * asking again only the edges it was refused and walking on from what they let in, which is the least fixpoint a
 * search from the start finds. The round's location rows are those of its safe nodes not yet collected, each kept
 * from its node's first safe round until its location is. An escape's counters, items and locations taken are the
 * round's until its first take. */
#include <stdint.h>

#if defined(_WIN32)
#define API __declspec(dllexport)
#else
#define API __attribute__((visibility("default")))
#endif

typedef int64_t i64;
typedef uint64_t u64;

#define ABI 2
#define MAGIC 0x314843524b5aLL   /* "ZKRCH1" */

/* The rules' bytecode: each rule starts at a word of the table; and/or name their children by position. */
enum { OP_FALSE, OP_TRUE, OP_COUNTER, OP_FLAG, OP_SUM, OP_AND, OP_OR };
/* The header's words; every offset is a word of the table. */
enum { H_MAGIC, H_ABI, H_N, H_F, H_L, H_C, H_I, H_START, H_G, H_KMAX, H_MMAX, H_ITEMS, H_DISC, H_YIELD, H_REFUND,
       H_FORCED, H_FORCED_PHYS, H_REGIONS, H_GRAPHS, H_MONO };
/* A graph's words. */
enum { G_ADJ, G_RADJ, G_K, G_CREDITS, G_CBN, G_M, G_LOCS, G_T, G_TELE, G_VICTORY, G_LBN };
/* A call's words. */
enum { C_GRAPH, C_PHYS, C_FREE, C_COLLECTED, C_TRAPS, C_LOG_CAP };

/* A search from the start kept across a call's rounds: its nodes and the edges it asked that didn't pass (each
 * edge's word in its CSR), on H_MONO's tables; else begun again each time. */
typedef struct {
    u64 *seen;
    i64 *blocked, nb, begun;
} Search;

typedef struct {
    const i64 *t, *gives;
    i64 n, f, l, c, it, start, nw, fw, lw, kw, mw, mono;
    i64 *queue, *list, *ec, *eh, *rows, nrows;
    Search main, back[2], phys, free;
    u64 *base, *dead, *eflags, *etook, *eseen, *esrc, *holds, *known, *at, *newf, *maybe, *eout,
        *settable, *fseen, *fflags, *now, *found, *walked, *cand, *alone, *rowed;
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
static int meets(const u64 *a, const u64 *b, i64 w) {
    for (i64 k = 0; k < w; k++)
        if (a[k] & b[k]) return 1;
    return 0;
}

static int evx(const i64 *t, i64 pc, const i64 *c, const u64 *f);

/* A rule's truth on counters `c` and flags `f`: a leaf here, a sum, and or or in evx. */
static inline int ev(const i64 *t, i64 pc, const i64 *c, const u64 *f) {
    const i64 *p = t + pc;
    if (p[0] == OP_TRUE) return 1;
    if (p[0] == OP_COUNTER) return c[p[1]] >= p[2];
    if (p[0] == OP_FLAG) return has(f, p[1]);
    return evx(t, pc, c, f);
}

static int evx(const i64 *t, i64 pc, const i64 *c, const u64 *f) {
    const i64 *p = t + pc;
    switch (p[0]) {
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

/* Logic._bfs: the nodes reached from `src` over the CSR at word `adj`; with `stop`, 1 once a node of it is reached
 * (the search then ends there, `seen` part of it), else 0. */
static int bfs(const K *k, i64 adj, const u64 *src, const i64 *c, const u64 *f, u64 *seen, const u64 *stop) {
    const i64 *t = k->t, *off = t + adj;
    i64 head = 0, tail = 0;
    copy(seen, src, k->nw);
    if (stop && meets(src, stop, k->nw)) return 1;
    for (i64 w = 0; w < k->nw; w++)
        for (u64 bits = src[w]; bits; bits &= bits - 1) k->queue[tail++] = w * 64 + __builtin_ctzll(bits);
    while (head < tail) {
        i64 u = k->queue[head++];
        for (i64 e = off[u]; e < off[u + 1]; e += 2) {
            i64 v = t[e];
            if (!has(seen, v) && ev(t, t[e + 1], c, f)) {
                put(seen, v);
                if (stop && has(stop, v)) return 1;
                k->queue[tail++] = v;
            }
        }
    }
    return 0;
}

/* `s` begun again from the start (every time on tables not H_MONO's); its first node queued. */
static i64 begin(const K *k, Search *s) {
    if (k->mono && s->begun) return 0;
    clear(s->seen, k->nw);
    put(s->seen, k->start);
    k->queue[0] = k->start;
    s->nb = 0;
    s->begun = 1;
    return 1;
}

/* Logic._bfs from the start over the CSR at word `adj`, kept in `s` (begin): its refused edges asked again, then on
 * from each node they let in; an edge refused again kept. */
static void grow(const K *k, i64 adj, Search *s, const i64 *c, const u64 *f) {
    const i64 *t = k->t, *off = t + adj;
    i64 head = 0, tail = begin(k, s), nb = 0;
    for (i64 j = 0; j < s->nb; j++) {
        i64 e = s->blocked[j], v = t[e];
        if (has(s->seen, v)) continue;
        if (ev(t, t[e + 1], c, f)) {
            put(s->seen, v);
            k->queue[tail++] = v;
        } else {
            s->blocked[nb++] = e;
        }
    }
    while (head < tail) {
        i64 u = k->queue[head++];
        for (i64 e = off[u]; e < off[u + 1]; e += 2) {
            i64 v = t[e];
            if (has(s->seen, v)) continue;
            if (ev(t, t[e + 1], c, f)) {
                put(s->seen, v);
                k->queue[tail++] = v;
            } else {
                s->blocked[nb++] = e;
            }
        }
    }
    s->nb = nb;
}

/* Logic._closure (no `never`): from the start, the nodes reached (`s`) and the flags credited where they are (`fl`,
 * this round's `fin` joined to the last round's on H_MONO's tables: below the least fixpoint, which it then finds). */
static void closure(const K *k, const i64 *g, Search *s, const i64 *c, const u64 *fin, u64 *fl) {
    const i64 *t = k->t, *cr = t + g[G_CREDITS];
    if (k->mono && s->begun) join(fl, fin, k->fw);
    else copy(fl, fin, k->fw);
    for (;;) {
        int any = 0;
        grow(k, g[G_ADJ], s, c, fl);
        clear(k->newf, k->fw);
        for (i64 j = 0; j < g[G_K]; j++) {
            const i64 *r = cr + 4 * j;
            if (!has(fl, r[0]) && has(s->seen, r[1]) && ev(t, r[3], c, fl)) {
                put(k->newf, r[0]);
                any = 1;
            }
        }
        if (!any) return;
        join(fl, k->newf, k->fw);
    }
}

/* The flags node `u` holds in the backward search: `base` and those its own credits set on it (a credit's verdict
 * worked out the first time its node is asked in this search: `known`, then `holds`). */
static const u64 *flags_at(const K *k, const i64 *g, const i64 *c, const u64 *base, i64 u) {
    const i64 *t = k->t, *cr = t + g[G_CREDITS], *cbn = t + g[G_CBN];
    const u64 *fu = base;
    for (i64 j = cbn[u]; j < cbn[u + 1]; j++) {
        i64 x = t[j];
        if (!has(k->known, x)) {
            put(k->known, x);
            if (!has(base, cr[4 * x]) && ev(t, cr[4 * x + 3], c, base)) put(k->holds, x);
        }
        if (has(k->holds, x)) {
            if (fu == base) {
                copy(k->at, base, k->fw);
                fu = k->at;
            }
            put(k->at, cr[4 * x]);
        }
    }
    return fu;
}

/* Logic._returners: the backward search from the start, an edge passable on `base` and the flags its own source
 * node can set on them, kept in `s` as grow keeps a forward one. */
static void returners(const K *k, const i64 *g, Search *s, const i64 *c, const u64 *base) {
    const i64 *t = k->t, *off = t + g[G_RADJ];
    i64 head = 0, tail = begin(k, s), nb = 0;
    clear(k->holds, k->kw);
    clear(k->known, k->kw);
    for (i64 j = 0; j < s->nb; j++) {
        i64 e = s->blocked[j], u = t[e];
        if (has(s->seen, u)) continue;
        if (ev(t, t[e + 1], c, flags_at(k, g, c, base, u))) {
            put(s->seen, u);
            k->queue[tail++] = u;
        } else {
            s->blocked[nb++] = e;
        }
    }
    while (head < tail) {
        i64 v = k->queue[head++];
        for (i64 e = off[v]; e < off[v + 1]; e += 2) {
            i64 u = t[e];
            if (has(s->seen, u)) continue;
            if (ev(t, t[e + 1], c, flags_at(k, g, c, base, u))) {
                put(s->seen, u);
                k->queue[tail++] = u;
            } else {
                s->blocked[nb++] = e;
            }
        }
    }
    s->nb = nb;
}

/* Logic._escape: the local closure from `node` with the round's state, starting with k->eflags; 1 once it reaches
 * the start (on H_MONO's tables, a node of `home`, the round's backward search). Leaves the nodes seen in k->eseen,
 * the flags in k->eflags. Its counters, items and locations taken are the round's until its first take copies them. */
static int escape(const K *k, const i64 *g, const u64 *home, const i64 *c, const i64 *held, const u64 *got, i64 node) {
    const i64 *t = k->t, *cr = t + g[G_CREDITS], *cbn = t + g[G_CBN], *lc = t + g[G_LOCS], *tp = t + g[G_TELE];
    const i64 *lbn = t + g[G_LBN], *ec = c;
    const u64 *stop = k->mono ? home : k->alone, *took = got;
    clear(k->esrc, k->nw);
    put(k->esrc, node);
    for (;;) {
        int any = 0;
        i64 nl = 0;
        if (bfs(k, g[G_ADJ], k->esrc, ec, k->eflags, k->eseen, stop)) return 1;
        for (i64 j = 0; j < g[G_T]; j++) {
            const i64 *r = tp + 4 * j;
            if (has(k->eseen, r[0]) && !has(k->eseen, r[1]) && !has(got, r[3]) && ev(t, r[2], ec, k->eflags)) {
                put(k->esrc, r[1]);
                any = 1;
            }
        }
        /* the locations (by row, in the rows' order) and the credits of the nodes seen */
        clear(k->cand, k->mw);
        clear(k->newf, k->fw);
        for (i64 w = 0; w < k->nw; w++)
            for (u64 bits = k->eseen[w]; bits; bits &= bits - 1) {
                i64 u = w * 64 + __builtin_ctzll(bits);
                for (i64 j = lbn[u]; j < lbn[u + 1]; j++) put(k->cand, t[j]);
                for (i64 j = cbn[u]; j < cbn[u + 1]; j++) {
                    const i64 *r = cr + 4 * t[j];
                    if (!has(k->eflags, r[0]) && ev(t, r[3], ec, k->eflags)) {
                        put(k->newf, r[0]);
                        any = 1;
                    }
                }
            }
        for (i64 w = 0; w < k->mw; w++)
            for (u64 bits = k->cand[w]; bits; bits &= bits - 1) {
                const i64 *r = lc + 3 * (w * 64 + __builtin_ctzll(bits));
                if (!has(took, r[0]) && ev(t, r[2], ec, k->eflags)) k->list[nl++] = r[0];
            }
        if (!any && !nl) return 0;
        if (nl && ec == c) {   /* the first take: the escape's own counters, items and locations from here */
            for (i64 j = 0; j < k->c; j++) k->ec[j] = c[j];
            for (i64 j = 0; j < k->it; j++) k->eh[j] = held[j];
            copy(k->etook, got, k->lw);
            ec = k->ec, took = k->etook;
        }
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
static void escaping(K *k, const i64 *g, Search *back, const i64 *c, const i64 *held, const u64 *got,
                     const u64 *nodes, i64 forced, const u64 *credited, u64 *out) {
    const i64 *t = k->t, *fo = t + t[forced];
    const u64 *home = back->seen;
    clear(out, k->nw);
    if (none(nodes, k->nw)) return;
    returners(k, g, back, c, k->base);
    for (i64 w = 0; w < k->nw; w++) out[w] = nodes[w] & home[w];
    clear(k->dead, k->nw);
    for (i64 v = 0; v < k->nw; v++)
        for (u64 left = nodes[v] & ~home[v]; left; left &= left - 1) {
            i64 n = v * 64 + __builtin_ctzll(left);
            if (has(k->dead, n)) continue;
            copy(k->eflags, k->base, k->fw);
            for (i64 j = fo[n]; j < fo[n + 1]; j++)
                if (has(credited, t[j])) put(k->eflags, t[j]);
            if (escape(k, g, home, c, held, got, n)) {
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

/* The most edges a graph of the tables has (a kept search's refused edges are at most those). */
static i64 edges(const i64 *t) {
    i64 most = 0;
    for (i64 j = 0; j < t[H_G]; j++) {
        const i64 *g = t + t[t[H_GRAPHS] + j], *off = t + g[G_ADJ];
        if ((off[t[H_N]] - off[0]) / 2 > most) most = (off[t[H_N]] - off[0]) / 2;
    }
    return most;
}

/* The workspace one call needs: its u64 words; `ints[0]` gets its i64 words. */
API i64 az_reach_need(const i64 *t, i64 *ints) {
    i64 nw = (t[H_N] + 63) / 64, fw = (t[H_F] + 63) / 64, lw = (t[H_L] + 63) / 64, kw = (t[H_KMAX] + 63) / 64;
    ints[0] = t[H_N] + 2 * t[H_MMAX] + t[H_C] + t[H_I] + 5 * edges(t) + 4;
    return 12 * nw + 6 * fw + 2 * lw + 2 * kw + (t[H_MMAX] + 63) / 64 + 4;
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
    k.n = t[H_N], k.f = t[H_F], k.l = t[H_L], k.c = t[H_C], k.it = t[H_I], k.start = t[H_START], k.mono = t[H_MONO];
    k.nw = (k.n + 63) / 64, k.fw = (k.f + 63) / 64, k.lw = (k.l + 63) / 64, k.kw = (t[H_KMAX] + 63) / 64;
    k.mw = (t[H_MMAX] + 63) / 64;
    k.queue = wi, k.list = wi + k.n, k.ec = k.list + t[H_MMAX], k.eh = k.ec + k.c;
    k.base = wb, k.back[0].seen = k.base + k.fw, k.back[1].seen = k.back[0].seen + k.nw;
    k.dead = k.back[1].seen + k.nw, k.eflags = k.dead + k.nw;
    k.etook = k.eflags + k.fw, k.eseen = k.etook + k.lw, k.esrc = k.eseen + k.nw, k.holds = k.esrc + k.nw;
    k.known = k.holds + k.kw, k.at = k.known + k.kw, k.newf = k.at + k.fw, k.maybe = k.newf + k.fw;
    k.eout = k.maybe + k.nw, k.settable = k.eout + k.nw, k.fseen = k.settable + k.fw, k.fflags = k.fseen + k.nw;
    k.now = k.fflags + k.fw, k.found = k.now + k.lw, k.walked = k.found + k.nw, k.cand = k.walked + k.nw;
    k.alone = k.cand + k.mw, k.rowed = k.alone + k.nw;
    k.main.blocked = k.eh + k.it, k.back[0].blocked = k.main.blocked + edges(t);
    k.back[1].blocked = k.back[0].blocked + edges(t), k.phys.blocked = k.back[1].blocked + edges(t);
    k.free.blocked = k.phys.blocked + edges(t), k.rows = k.free.blocked + edges(t), k.nrows = 0;
    k.main.seen = reached, k.phys.seen = phys, k.free.seen = k.fseen;
    k.main.begun = k.back[0].begun = k.back[1].begun = k.phys.begun = k.free.begun = 0;

    const i64 *gs = t + t[H_GRAPHS];
    const i64 *rg = t + gs[call[C_GRAPH]], *pg = t + gs[call[C_PHYS]], *fg = t + gs[call[C_FREE]];
    const i64 *lc = t + rg[G_LOCS], *lbn = t + rg[G_LBN], *cr = t + rg[G_CREDITS], *rf = t + t[H_REFUND];
    i64 cap = call[C_LOG_CAP];

    copy(k.base, flags, k.fw);
    clear(k.alone, k.nw);
    put(k.alone, k.start);
    clear(k.rowed, k.nw);
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
        grow(&k, rg[G_ADJ], &k.main, counters, flags);
        for (i64 w = 0; w < k.nw; w++) k.maybe[w] = reached[w] & ~safe[w];
        escaping(&k, rg, &k.back[0], counters, held, got, k.maybe, H_FORCED, flags, k.eout);
        join(safe, k.eout, k.nw);
        if (call[C_TRAPS]) {
            closure(&k, pg, &k.phys, counters, flags, k.settable);
        } else {
            clear(phys, k.nw);
            clear(k.settable, k.fw);
        }
        for (i64 w = 0; w < k.nw; w++) k.maybe[w] = phys[w] & ~safe[w];
        escaping(&k, pg, &k.back[1], counters, held, got, k.maybe, H_FORCED_PHYS, k.settable, k.eout);
        for (i64 w = 0; w < k.nw; w++) k.found[w] = k.maybe[w] & ~k.eout[w];
        if (call[C_FREE] == call[C_PHYS] || none(k.found, k.nw)) {
            copy(k.walked, k.found, k.nw);
        } else {
            closure(&k, fg, &k.free, counters, flags, k.fflags);
            for (i64 w = 0; w < k.nw; w++) k.walked[w] = k.found[w] & k.fseen[w];
        }
        join(traps, k.found, k.nw);
        join(freed, k.walked, k.nw);
        if (cap) {
            if (round >= cap) return -2;
            copy(found_log + round * k.nw, k.found, k.nw);
            copy(walked_log + round * k.nw, k.walked, k.nw);
        }
        /* the location rows of the safe nodes not yet collected (each row's node safe from its first round on: kept
         * until its location is collected), those that hold now in the rows' order */
        for (i64 w = 0; w < k.nw; w++) {
            for (u64 bits = safe[w] & ~k.rowed[w]; bits; bits &= bits - 1) {
                i64 u = w * 64 + __builtin_ctzll(bits);
                for (i64 j = lbn[u]; j < lbn[u + 1]; j++) k.rows[k.nrows++] = t[j];
            }
            k.rowed[w] |= safe[w];
        }
        clear(k.cand, k.mw);
        i64 kept = 0;
        for (i64 j = 0; j < k.nrows; j++) {
            const i64 *r = lc + 3 * k.rows[j];
            if (has(got, r[0]) || has(k.now, r[0])) continue;
            if (ev(t, r[2], counters, flags)) put(k.cand, k.rows[j]);
            else k.rows[kept++] = k.rows[j];
        }
        k.nrows = kept;
        for (i64 w = 0; w < k.mw; w++)
            for (u64 bits = k.cand[w]; bits; bits &= bits - 1) k.list[nl++] = lc[3 * (w * 64 + __builtin_ctzll(bits))];
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
