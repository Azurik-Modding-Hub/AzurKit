/* The randomizer's fill attempt, compiled (Step 4.4ci57, D1141): one attempt of planner/fill.py's _Slots.attempt, its
 * Python twin and the reference, line for line, over the fill's blob (fill._NativeFill packs it) and the reach tables
 * azurkit.core.native.Tables writes (the plan's options' and each rung of a seed difficulty's ladder): the progression
 * items (own spots, safe spots, trades, the pin), the counted items by threshold band, the trap gate's repairs, the
 * useful items, the filler by class and the verify. Its reaches are reach.c's az_reach on caller workspace; its streams
 * CPython's random.Random(int) (MT19937 seeded by init_by_array, random()'s 53 bits) under fill.Rng's below, shuffle,
 * choice and weighted. Integers only: no float, no libm, no allocation, no libc. It tells no note: it logs each of the
 * twin's _Count calls (placed, reach) for its caller to tell. tests/test_native.py holds it to the twin bit for bit.
 * Built by nativekit with reach.c. */
#include <stdint.h>

#if defined(_WIN32)
#define API __declspec(dllexport)
#else
#define API __attribute__((visibility("default")))
#endif

typedef int64_t i64;
typedef uint64_t u64;
typedef uint32_t u32;

i64 az_reach(const i64 *t, const i64 *call, i64 *counters, i64 *held, u64 *flags, u64 *got, const u64 *late,
             const i64 *gives, u64 *reached, u64 *safe, u64 *phys, u64 *traps, u64 *after, u64 *freed,
             i64 *loc_round, i64 *flag_round, u64 *found_log, u64 *walked_log, i64 *out, u64 *wb, i64 *wi);
i64 az_reach_need(const i64 *t, i64 *ints);

#define FILL_MAGIC 0x314c4c49464bLL   /* "KFILL1" */
#define FILL_VERSION 1
#define MAX_REPAIRS 8                 /* fill.MAX_REPAIRS */
#define WEIGHT 3                      /* fill.USEFUL_MAJOR_WEIGHT */
#define TWO53 ((i64)1 << 53)

/* reach.c's header words this file reads */
enum { H_N = 2, H_F = 3, H_L = 4, H_C = 5, H_I = 6, H_ITEMS = 11, H_DISC = 12 };
/* The fill's blob: its header's words (each offset a word of the blob). */
enum { F_MAGIC, F_VERSION, F_L, F_I, F_NAMES, F_GRAPHS, F_START, F_LOCS, F_ITEMS, F_MOVE, F_GRAPH, F_HAVE, F_ONLY,
       F_PROG, F_USEFUL, F_COUNTED, F_GROUPS, F_NONGEM, F_KNOWN_FULL, F_KNOWN_NAME, F_STUB, F_GUARD, F_FULL, F_GIVES,
       F_MAXGROUP, F_HEAD };
/* A location's row, and its flags */
enum { L_FLAGS, L_VANILLA, L_KIND, L_GRAPH, L_NODE, L_LEVEL, L_FIRST, L_ITEMNAME, L_TEMPLATE, L_W };
enum { LF_POOL = 1, LF_EXCL = 2, LF_VAULT = 4, LF_MAJOR = 8, LF_PROVEN = 16, LF_OPEN = 32, LF_ONLY = 64 };
/* An item's row, its classes and flags */
enum { I_CLASS, I_BASE, I_FLAGS, I_START, I_COST, I_W };
enum { CL_PROG, CL_COUNTED, CL_USEFUL, CL_FILLER, CL_OTHER };
enum { IF_READ = 1, IF_VAULT = 2, IF_NEEDED = 4 };
/* A call's words: the told log's capacity, the tables (the plan's, then the rungs), the pin, each table's three graph
 * ids, and the three streams' seeds (progression, useful, filler: a key's word count and its two 32-bit words). */
enum { A_CAP, A_TABS, A_PIN, A_GRAPHS, A_STREAMS = A_GRAPHS + 12, A_W = A_STREAMS + 9 };
/* The answer's words, then the placement (L), a verify's reach for the reason and one for each repaired refusal
 * (MAX_REPAIRS + 1 of them: its victory, locations, trick-free traps and those after completion: VW words), and the
 * told log (A_CAP). */
enum { O_STATUS, O_CODE, O_A, O_B, O_NLOG, O_NREP, O_REACHES, O_PATHS, O_HEAD };
#define VW(s) (1 + (s)->lw + 2 * (s)->nw)
/* The reasons (fill._Stuck's words, which the caller writes) */
enum { W_NONE, W_NO_PROVEN, W_REPAIR_BUDGET, W_NO_SAFE_LEFT, W_VERIFY, W_VAULT_NONE, W_VAULT_UNSAFE, W_NO_SAFE,
       W_NO_FILLER };
/* The paths an attempt took (O_PATHS: the twin test's spread) */
enum { P_OWN = 1, P_TRADE = 2, P_TRADE_FAIL = 4, P_PIN = 8, P_PIN_MISS = 16, P_REPAIRED = 32, P_REPAIR_SWAP = 64,
       P_REPAIR_IN = 128, P_REPAIR_AT = 256, P_VAULT = 512 };

typedef struct {   /* a reach's answer kept: its locations, nodes, safe nodes, trick-free traps, those after completion */
    u64 *got, *nodes, *safe, *free, *after;
    i64 victory;
} R;

typedef struct {   /* CPython's random.Random: MT19937 */
    u32 mt[624];
    i64 i;
} MT;

typedef struct {
    const i64 *f, *call, *tabs[4];
    i64 L, I, G, nw, lw, namew, start, nplaced, err, nlog, cap, reaches, paths, rounds, cap_rounds;
    i64 *log, *out;
    /* the reach's own: its workspace, its rows, its sets */
    u64 *wb, *flags, *got, *late, *phys, *traps, *found_log, *walked_log;
    i64 *wi, *c, *held, *gives, *loc_round, *flag_round, *rout;
    R r[6];
    /* the attempt's state */
    i64 *placed, *base, *prog, *good, *snap, *assumed, *used, *sa, *sb, *list, *spots, *missed, *best, *pinned,
        *cand, *pairs, *outs, *ins, *sph, *bcount, *bstart, *border, npinned, npairs;
    u64 *gnew, *newt, *tmp, *acc, *coll, *was, *fresh;
    MT rng;
} S;

static int has(const u64 *b, i64 i) { return (int)((b[i >> 6] >> (i & 63)) & 1u); }
static void put_bit(u64 *b, i64 i) { b[i >> 6] |= (u64)1 << (i & 63); }
static void del_bit(u64 *b, i64 i) { b[i >> 6] &= ~((u64)1 << (i & 63)); }
static void clear(u64 *b, i64 w) { for (i64 k = 0; k < w; k++) b[k] = 0; }
static void copy(u64 *d, const u64 *s, i64 w) { for (i64 k = 0; k < w; k++) d[k] = s[k]; }
static void copy_i(i64 *d, const i64 *s, i64 n) { for (i64 k = 0; k < n; k++) d[k] = s[k]; }
static int any(const u64 *b, i64 w) {
    for (i64 k = 0; k < w; k++)
        if (b[k]) return 1;
    return 0;
}
static int meets(const u64 *a, const u64 *b, i64 w) {
    for (i64 k = 0; k < w; k++)
        if (a[k] & b[k]) return 1;
    return 0;
}

/* ---- the streams ---------------------------------------------------------------------------------------------- */
static void mt_seed(MT *m, u32 s) {
    m->mt[0] = s;
    for (i64 i = 1; i < 624; i++) m->mt[i] = 1812433253u * (m->mt[i - 1] ^ (m->mt[i - 1] >> 30)) + (u32)i;
    m->i = 624;
}

/* random.Random(n)'s seeding: init_by_array over n's 32-bit words, the lowest first */
static void mt_keyed(MT *m, const u32 *key, i64 len) {
    i64 i = 1, j = 0, k = 624 > len ? 624 : len;
    mt_seed(m, 19650218u);
    for (; k; k--) {
        m->mt[i] = (m->mt[i] ^ ((m->mt[i - 1] ^ (m->mt[i - 1] >> 30)) * 1664525u)) + key[j] + (u32)j;
        i++, j++;
        if (i >= 624) m->mt[0] = m->mt[623], i = 1;
        if (j >= len) j = 0;
    }
    for (k = 623; k; k--) {
        m->mt[i] = (m->mt[i] ^ ((m->mt[i - 1] ^ (m->mt[i - 1] >> 30)) * 1566083941u)) - (u32)i;
        i++;
        if (i >= 624) m->mt[0] = m->mt[623], i = 1;
    }
    m->mt[0] = 0x80000000u;
}

static u32 mt_next(MT *m) {
    if (m->i >= 624) {
        for (i64 k = 0; k < 624; k++) {
            u32 y = (m->mt[k] & 0x80000000u) | (m->mt[(k + 1) % 624] & 0x7fffffffu);
            m->mt[k] = m->mt[(k + 397) % 624] ^ (y >> 1) ^ ((y & 1u) ? 0x9908b0dfu : 0u);
        }
        m->i = 0;
    }
    u32 y = m->mt[m->i++];
    y ^= y >> 11;
    y ^= (y << 7) & 0x9d2c5680u;
    y ^= (y << 15) & 0xefc60000u;
    y ^= y >> 18;
    return y;
}

/* Rng.below: random()'s 53 bits as an integer, by rejection */
static i64 below(MT *m, i64 n) {
    i64 limit = TWO53 - TWO53 % n;
    for (;;) {
        i64 a = mt_next(m) >> 5, b = mt_next(m) >> 6, x = a * 67108864 + b;
        if (x < limit) return x % n;
    }
}

static void shuffle(MT *m, i64 *xs, i64 n) {
    for (i64 i = n - 1; i > 0; i--) {
        i64 j = below(m, i + 1), x = xs[i];
        xs[i] = xs[j], xs[j] = x;
    }
}

static void stream(S *s, int which) {
    const i64 *w = s->call + A_STREAMS + 3 * which;
    u32 key[2] = {(u32)w[1], (u32)w[2]};
    mt_keyed(&s->rng, key, w[0]);
}

/* ---- the blob's rows -------------------------------------------------------------------------------------------- */
static const i64 *loc_row(const S *s, i64 loc) { return s->f + s->f[F_LOCS] + L_W * loc; }
static const i64 *item_row(const S *s, i64 item) { return s->f + s->f[F_ITEMS] + I_W * item; }
static const u64 *have_row(const S *s, i64 g) { return (const u64 *)(s->f + s->f[F_HAVE]) + g * s->namew; }
static const u64 *bits(const S *s, i64 at) { return (const u64 *)(s->f + s->f[at]); }

/* _Slots.holds: the spot's proven mark holds for the item (AZ-725: some only for their 'only' items) */
static int holds(const S *s, i64 loc, i64 item) {
    i64 fl = loc_row(s, loc)[L_FLAGS];
    if (!(fl & LF_PROVEN)) return 0;
    if (!(fl & LF_ONLY)) return 1;
    const i64 *off = s->f + s->f[F_ONLY];
    for (i64 j = off[loc]; j < off[loc + 1]; j++)
        if (s->f[j] == item) return 1;
    return 0;
}

/* writer.Names.target: the name the spot is repointed to for the item, -1 for none (name ids below I are the items') */
static i64 target(const S *s, i64 loc, i64 item) {
    const i64 *row = loc_row(s, loc);
    i64 base = item_row(s, item)[I_BASE];
    if (base == row[L_ITEMNAME]) return -1;
    if (row[L_TEMPLATE] != row[L_ITEMNAME]) {
        i64 mv = s->f[s->f[F_MOVE] + base];
        if (mv >= 0 && has(have_row(s, row[L_GRAPH]), mv)) return mv;
    }
    return item;
}

/* _Budget.fits and take */
static int fits(const S *s, i64 loc, i64 item) {
    i64 name = target(s, loc, item), g = loc_row(s, loc)[L_GRAPH];
    if (name < 0 || has(have_row(s, g), name) || has(s->gnew + g * s->namew, name)) return 1;
    const i64 *gr = s->f + s->f[F_GRAPH] + 2 * g;
    return gr[0] && s->used[g] + item_row(s, name)[I_COST] <= gr[1];
}

static void take(S *s, i64 loc, i64 item) {
    i64 name = target(s, loc, item), g = loc_row(s, loc)[L_GRAPH];
    if (name < 0 || has(have_row(s, g), name) || has(s->gnew + g * s->namew, name)) return;
    put_bit(s->gnew + g * s->namew, name);
    s->used[g] += item_row(s, name)[I_COST];
}

/* _Slots.ok: the item rules for a spot of the right class */
static int ok(const S *s, i64 loc, i64 item) {
    const i64 *row = loc_row(s, loc), *ir = item_row(s, item);
    if ((ir[I_CLASS] == CL_PROG || ir[I_CLASS] == CL_COUNTED) && (row[L_FLAGS] & LF_EXCL)) return 0;
    if (ir[I_CLASS] == CL_PROG && !holds(s, loc, item)) return 0;
    if ((row[L_FLAGS] & LF_VAULT) && !(ir[I_FLAGS] & IF_VAULT) && item != row[L_VANILLA]) return 0;
    return fits(s, loc, item);
}

/* one of the twin's _Count calls: the items placed since the attempt began, and whether a reach follows */
static void told(S *s, int reach) {
    if (s->nlog < s->cap) s->log[s->nlog] = (s->nplaced - s->start) * 2 + reach;
    else s->err = -3;
    s->nlog++;
}

static void put(S *s, i64 loc, i64 item) {
    if (s->placed[loc] < 0) s->nplaced++;
    s->placed[loc] = item;
    take(s, loc, item);
    told(s, 0);
}

/* ---- the reach ------------------------------------------------------------------------------------------------- */
/* Logic.reach on table `ti` (0: the plan's options; 1..: the rungs) of the placement, `at` holding `item` over it (at
 * >= 0), the world's starting items held and, with `assumed`, the assumed ones; R_phys and the traps with `traps`, the
 * rounds' log with `logged`; `coll` the collected spots (their guardian slots collected from the round that reaches
 * them: replay), or none. Its answer into `r`. */
static i64 reach(S *s, i64 ti, i64 at, i64 item, int assumed, int traps, int logged, const u64 *coll, R *r) {
    const i64 *t = s->tabs[ti], *g3 = s->call + A_GRAPHS + 3 * ti, *io = t + t[H_ITEMS], *disc = t + t[H_DISC];
    const i64 *gives = s->f + s->f[F_GIVES];
    i64 nc = t[H_C], fw = (t[H_F] + 63) / 64;
    for (i64 j = 0; j < s->I; j++)
        s->held[j] = item_row(s, j)[I_START] + (assumed && s->assumed[j] > 0 ? s->assumed[j] : 0);
    for (i64 j = 0; j < nc; j++) s->c[j] = 0;
    for (i64 j = 0; j < s->I; j++) {   /* Logic._add, a copy at a time: a disc counter counts the first */
        i64 h = s->held[j];
        if (h <= 0) continue;
        for (i64 e = io[j]; e < io[j + 1]; e += 2) s->c[t[e]] += disc[t[e]] ? t[e + 1] : t[e + 1] * h;
    }
    for (i64 loc = 0; loc < s->L; loc++)
        s->gives[loc] = (loc_row(s, loc)[L_FLAGS] & LF_OPEN) ? (loc == at ? item : s->placed[loc]) : gives[loc];
    clear(s->flags, fw);
    if (coll) {
        const u64 *guard = bits(s, F_GUARD);
        for (i64 w = 0; w < s->lw; w++) s->got[w] = coll[w], s->late[w] = coll[w] & guard[w];
    } else {
        clear(s->got, s->lw);
        clear(s->late, s->lw);
    }
    i64 call[7] = {g3[0], g3[1], g3[2], coll != 0, traps, logged ? s->cap_rounds : 0, coll != 0};
    i64 rc = az_reach(t, call, s->c, s->held, s->flags, s->got, s->late, s->gives, r->nodes, r->safe, s->phys,
                      s->traps, r->after, r->free, s->loc_round, s->flag_round, s->found_log, s->walked_log, s->rout,
                      s->wb, s->wi);
    if (rc) return rc < 0 ? rc - 10 : -19;
    copy(r->got, s->got, s->lw);
    r->victory = s->rout[1];
    s->rounds = s->rout[0];
    s->reaches++;
    return 0;
}

/* the attempt's own reach(): a note, then the reach of the placement so far, the assumed items held */
static i64 areach(S *s, i64 at, i64 item, R *r) {
    told(s, 1);
    return reach(s, 0, at, item, 1, 0, 0, 0, r);
}

/* ---- the stuck reasons ------------------------------------------------------------------------------------------ */
static i64 stuck(S *s, i64 code, i64 a, i64 b) {
    s->out[O_CODE] = code, s->out[O_A] = a, s->out[O_B] = b;
    return 1;
}

/* a verify's reach kept at `w` for the caller's words: its victory, locations and traps */
static void keep(S *s, i64 *w, const R *r) {
    w[0] = r->victory;
    copy((u64 *)w + 1, r->got, s->lw);
    copy((u64 *)w + 1 + s->lw, r->free, s->nw);
    copy((u64 *)w + 1 + s->lw + s->nw, r->after, s->nw);
}

static i64 stuck_verify(S *s, const R *r) {
    keep(s, s->out + O_HEAD + s->L, r);
    return stuck(s, W_VERIFY, -1, -1);
}

/* _problems: how many (victory, the spots never collected, new trick-free traps), and whether the last is one */
static i64 problems(const S *s, const R *r, int *traps) {
    const u64 *full = bits(s, F_FULL), *known = bits(s, F_KNOWN_FULL);
    i64 n = !r->victory;
    int missed = 0;
    for (i64 w = 0; w < s->lw; w++)
        if (full[w] & ~r->got[w]) missed = 1;
    *traps = 0;
    for (i64 w = 0; w < s->nw; w++)
        if (r->free[w] & ~r->after[w] & ~known[w]) *traps = 1;
    return n + missed + *traps;
}

/* ---- the passes ------------------------------------------------------------------------------------------------ */
static i64 safe(const S *s, i64 item, const u64 *got, i64 *out) {
    const i64 *ng = s->f + s->f[F_NONGEM];
    i64 n = 0;
    for (i64 j = 1; j <= ng[0]; j++) {
        i64 loc = ng[j];
        if (s->placed[loc] < 0 && has(got, loc) && ok(s, loc, item)) out[n++] = loc;
    }
    return n;
}

/* fill's still: safe(item, got) once `spot` of the `n` spots took the item; only its graph's spots asked again */
static i64 still(S *s, i64 item, const u64 *got, i64 *spots, i64 n, i64 spot) {
    const i64 *ng = s->f + s->f[F_NONGEM];
    i64 g = loc_row(s, spot)[L_GRAPH], m = 0;
    clear(s->was, s->lw);
    for (i64 j = 0; j < n; j++) put_bit(s->was, spots[j]);
    for (i64 j = 1; j <= ng[0]; j++) {
        i64 loc = ng[j];
        if (s->placed[loc] >= 0 || !has(got, loc)) continue;
        if (loc_row(s, loc)[L_GRAPH] == g ? ok(s, loc, item) : has(s->was, loc)) spots[m++] = loc;
    }
    return m;
}

/* own: the spots the item opens by lying there (reached, not safe without it, collected once it lies there) */
static i64 own(S *s, i64 item, const R *r, i64 *out, i64 *n) {
    const i64 *ng = s->f + s->f[F_NONGEM];
    *n = 0;
    for (i64 j = 1; j <= ng[0]; j++) {
        i64 loc = ng[j], node = loc_row(s, loc)[L_NODE], rc;
        if (s->placed[loc] >= 0 || has(r->got, loc) || !has(r->nodes, node) || has(r->safe, node) || !ok(s, loc, item))
            continue;
        if ((rc = areach(s, loc, item, &s->r[1]))) return rc;
        if (has(s->r[1].got, loc)) out[(*n)++] = loc;
    }
    if (*n) s->paths |= P_OWN;
    return 0;
}

/* spots_for: own spots, else safe ones of `r` (none: a reach of its own into `mine`) */
static i64 spots_for(S *s, i64 item, const R *r, R *mine, i64 *out, i64 *n) {
    i64 rc;
    if (!r) {
        if ((rc = areach(s, -1, -1, mine))) return rc;
        r = mine;
    }
    if ((rc = own(s, item, r, out, n))) return rc;
    if (!*n) *n = safe(s, item, r->got, out);
    return 0;
}

/* rebudget: the placement and budget again from the base and `prog`; 0 once one is over its graph's budget */
static int rebudget(S *s, const i64 *prog) {
    copy_i(s->placed, s->base, s->L);
    s->nplaced = s->start;
    for (i64 g = 0; g < s->G; g++) s->used[g] = 0;
    clear(s->gnew, s->G * s->namew);
    for (i64 loc = 0; loc < s->L; loc++)
        if (prog[loc] >= 0) {
            if (!fits(s, loc, prog[loc])) return 0;
            put(s, loc, prog[loc]);
        }
    return 1;
}

/* the progression items placed so far (the placement off the base) into `prog` */
static void progs(S *s, i64 *prog) {
    for (i64 loc = 0; loc < s->L; loc++) prog[loc] = s->base[loc] < 0 ? s->placed[loc] : -1;
}

/* trade: no spot for `item` in `r`: it takes a placed progression item's spot (one its reach gets to, collected with
 * the item there and the other assumed), and the other goes on a spot of the reach with the item there; 1 once done */
static i64 trade(S *s, i64 item, const R *r, int *done) {
    i64 n = 0, rc, *snap = s->snap;
    *done = 0;
    progs(s, snap);
    for (i64 loc = 0; loc < s->L; loc++)
        if (snap[loc] >= 0 && has(r->nodes, loc_row(s, loc)[L_NODE])) s->cand[n++] = loc;
    shuffle(&s->rng, s->cand, n);
    for (i64 j = 0; j < n; j++) {
        i64 loc = s->cand[j], other = snap[loc], read = (item_row(s, other)[I_FLAGS] & IF_READ) != 0, m;
        if (!holds(s, loc, item)) continue;
        s->assumed[other] += read;
        if ((rc = areach(s, loc, item, &s->r[1]))) return rc;
        s->assumed[other] -= read;
        if (has(s->r[1].got, loc)) {
            snap[loc] = item;
            int fit = rebudget(s, snap);
            snap[loc] = other;
            if (fit) {
                if ((rc = spots_for(s, other, 0, &s->r[2], s->sb, &m))) return rc;
                if (m) {
                    put(s, s->sb[below(&s->rng, m)], other);
                    s->paths |= P_TRADE;
                    *done = 1;
                    return 0;
                }
            }
        }
        rebudget(s, snap);
    }
    s->paths |= P_TRADE_FAIL;
    return 0;
}

/* _Pin.pick: a needed item's spot among `spots` the most rungs miss, on a map level no pinned item holds yet */
static i64 pick(S *s, i64 item, const i64 *spots, i64 n, const R *r, i64 *loc) {
    i64 rc, top = 0, nb = 0, nf = 0;
    if (!(item_row(s, item)[I_FLAGS] & IF_NEEDED) || !has(r->got, spots[0])) {
        *loc = spots[below(&s->rng, n)];
        return 0;
    }
    for (i64 j = 0; j < n; j++) s->missed[j] = 0;
    for (i64 ti = 1; ti < s->call[A_TABS]; ti++) {
        if ((rc = reach(s, ti, -1, -1, 1, 0, 0, 0, &s->r[3]))) return rc;
        for (i64 j = 0; j < n; j++) s->missed[j] += !has(s->r[3].got, spots[j]);
    }
    for (i64 j = 0; j < n; j++)
        if (s->missed[j] > top) top = s->missed[j];
    if (!top) {
        *loc = spots[below(&s->rng, n)];
        s->paths |= P_PIN_MISS;
        return 0;
    }
    for (i64 j = 0; j < n; j++)
        if (s->missed[j] == top) s->best[nb++] = spots[j];
    for (i64 j = 0; j < nb; j++) {   /* a map level no pinned item holds, else all */
        int used = 0;
        for (i64 p = 0; p < s->npinned; p++)
            if (loc_row(s, s->pinned[p])[L_LEVEL] == loc_row(s, s->best[j])[L_LEVEL]) used = 1;
        if (!used) s->best[nf++] = s->best[j];
    }
    if (!nf) {
        nb = 0;
        for (i64 j = 0; j < n; j++)
            if (s->missed[j] == top) s->best[nb++] = spots[j];
        nf = nb;
    }
    *loc = s->best[below(&s->rng, nf)];
    s->pinned[s->npinned++] = *loc;
    s->paths |= P_PIN;
    return 0;
}

/* the counted items as blocks: a reach per threshold band, the band's lowest count assumed */
static i64 counted(S *s) {
    const i64 *p = s->f + s->f[F_COUNTED];
    i64 rc;
    for (i64 q = 0, items = *p++; q < items; q++) {
        i64 item = p[0], k = p[1];
        const i64 *lows = p + 2;
        while (k) {
            i64 low = lows[k - 1], n, band = k - low;
            s->assumed[item] = low;
            if ((rc = areach(s, -1, -1, &s->r[0]))) return rc;
            n = safe(s, item, s->r[0].got, s->sa);
            for (i64 j = 0; j < band; j++) {
                if (!n) return stuck(s, W_NO_SAFE_LEFT, item, k);
                i64 spot = s->sa[below(&s->rng, n)];
                put(s, spot, item);
                k--;
                n = still(s, item, s->r[0].got, s->sa, n, spot);
            }
        }
        p += 2 + p[1];
    }
    return 0;
}

/* whether the reach with `coll` collected frees the traps `newt` (the trick-free traps it has, stub levels aside) */
static i64 clears(S *s, const u64 *coll, int *yes) {
    const u64 *stub = bits(s, F_STUB);
    i64 rc = reach(s, 0, -1, -1, 0, 1, 0, coll, &s->r[5]);
    if (rc) return rc;
    *yes = 1;
    for (i64 w = 0; w < s->nw; w++)
        if (s->r[5].free[w] & ~stub[w] & s->newt[w]) *yes = 0;
    return 0;
}

/* _Slots.repairs on the verify's reach `r` (its rounds' log as the kernel left it): the swaps, into s->pairs */
static i64 repairs(S *s, const i64 *prog, const R *r) {
    const u64 *stub = bits(s, F_STUB), *known = bits(s, F_KNOWN_NAME);
    const i64 *ng = s->f + s->f[F_NONGEM];
    i64 rounds = s->rounds, nsph = 0, t = -1, u = -1, nouts = 0, nins = 0, back = -1, rc;
    s->npairs = 0;
    /* the locations by round (the twin's spheres: each round that collects something) */
    for (i64 j = 0; j < rounds; j++) s->bcount[j] = 0;
    for (i64 loc = 0; loc < s->L; loc++)
        if (s->loc_round[loc] >= 0) s->bcount[s->loc_round[loc]]++;
    for (i64 j = 0, at = 0; j < rounds; j++) s->bstart[j] = at, at += s->bcount[j];
    for (i64 j = 0; j < rounds; j++) s->bcount[j] = 0;
    for (i64 loc = 0; loc < s->L; loc++)
        if (s->loc_round[loc] >= 0) {
            i64 rr = s->loc_round[loc];
            s->border[s->bstart[rr] + s->bcount[rr]++] = loc;
        }
    /* new[i]: a sphere's trick-free traps since the last, less those after completion and the known ones */
    for (i64 w = 0; w < s->nw; w++) s->tmp[w] = ~(r->after[w] & ~stub[w]) & ~known[w];
    clear(s->acc, s->nw);
    for (i64 rr = 0; rr + 1 < rounds; rr++) {
        const u64 *walked = s->walked_log + rr * s->nw;
        for (i64 w = 0; w < s->nw; w++) s->acc[w] |= walked[w];
        if (!s->bcount[rr]) continue;
        for (i64 w = 0; w < s->nw; w++) s->acc[w] &= s->tmp[w];
        if (t < 0) {
            if (any(s->acc, s->nw)) t = nsph, copy(s->newt, s->acc, s->nw);
        } else if (!meets(s->acc, s->newt, s->nw)) {
            s->sph[nsph++] = rr;
            u = nsph - 1;
            break;
        }
        s->sph[nsph++] = rr;
        clear(s->acc, s->nw);
    }
    if (u < 0) return 0;
    {   /* the way out: the progression items of the sphere before u */
        i64 rr = s->sph[u - 1];
        for (i64 j = 0; j < s->bcount[rr]; j++)
            if (prog[s->border[s->bstart[rr] + j]] >= 0) s->outs[nouts++] = s->border[s->bstart[rr] + j];
    }
    clear(s->coll, s->lw);   /* got: sphere t's state, what the spheres before it collected */
    for (i64 loc = 0; loc < s->L; loc++)
        if (s->loc_round[loc] >= 0 && s->loc_round[loc] < s->sph[t]) put_bit(s->coll, loc);
    for (i64 i = t - 1; i >= 0 && back < 0; i--)
        for (i64 j = 0; j < s->bcount[s->sph[i]]; j++)
            if (prog[s->border[s->bstart[s->sph[i]] + j]] >= 0) back = i;
    if (back >= 0) {   /* the way in: the last progression items before t, those without which the traps aren't first */
        i64 rr = s->sph[back], kept = 0;
        for (i64 j = 0; j < s->bcount[rr]; j++)
            if (prog[s->border[s->bstart[rr] + j]] >= 0) s->ins[nins++] = s->border[s->bstart[rr] + j];
        for (i64 j = 0; j < nins; j++) {
            int yes;
            del_bit(s->coll, s->ins[j]);
            rc = clears(s, s->coll, &yes);
            put_bit(s->coll, s->ins[j]);
            if (rc) return rc;
            if (yes) s->list[kept++] = s->ins[j];
        }
        if (kept) {
            copy_i(s->ins, s->list, kept);
            nins = kept;
        }
        s->paths |= P_REPAIR_IN;
    } else {           /* none: the spots at the traps, and first the ways out that free them there */
        i64 kept = 0;
        for (i64 j = 1; j <= ng[0]; j++) {
            i64 loc = ng[j], fl = loc_row(s, loc)[L_FLAGS];
            if (has(s->newt, loc_row(s, loc)[L_NODE]) && (fl & LF_PROVEN) && !(fl & LF_EXCL) && !(fl & LF_VAULT))
                s->ins[nins++] = loc;
        }
        for (i64 j = 0; j < nouts; j++) {
            int yes, had = has(s->coll, s->outs[j]);
            put_bit(s->coll, s->outs[j]);
            rc = clears(s, s->coll, &yes);
            if (!had) del_bit(s->coll, s->outs[j]);
            if (rc) return rc;
            if (yes) s->list[kept++] = s->outs[j];
        }
        if (kept) {
            copy_i(s->outs, s->list, kept);
            nouts = kept;
        }
        s->paths |= P_REPAIR_AT;
    }
    for (i64 i = 0; i < nouts; i++)
        for (i64 j = 0; j < nins; j++) {
            i64 a = s->outs[i], b = s->ins[j];
            if (a != b && holds(s, b, prog[a]) && (prog[b] < 0 || holds(s, a, prog[b])))
                s->pairs[2 * s->npairs] = a, s->pairs[2 * s->npairs + 1] = b, s->npairs++;
        }
    return 0;
}

/* the counted items and the trap gate's repairs (the twin's loop over MAX_REPAIRS + 1 tries) */
static i64 settle(S *s) {
    i64 rc, why = 0, have_good = 0, *prog = s->prog, *good = s->good;
    s->npairs = 0;
    progs(s, prog);
    for (i64 fix = 0; fix <= MAX_REPAIRS; fix++) {
        rc = 0;
        if (fix) {
            i64 at = below(&s->rng, s->npairs), a = s->pairs[2 * at], b = s->pairs[2 * at + 1];
            for (i64 j = at; j + 1 < s->npairs; j++) s->pairs[2 * j] = s->pairs[2 * j + 2],
                                                     s->pairs[2 * j + 1] = s->pairs[2 * j + 3];
            s->npairs--;
            copy_i(prog, good, s->L);
            prog[b] = good[a];
            prog[a] = good[b];   /* good[b] < 0: a leaves the placement */
            s->paths |= P_REPAIR_SWAP;
            if (!rebudget(s, prog)) rc = stuck(s, W_REPAIR_BUDGET, prog[b], b);
        }
        if (!rc) rc = counted(s);
        if (!rc) {
            int traps;
            told(s, 1);
            if ((rc = reach(s, 0, -1, -1, 0, 1, 1, 0, &s->r[4]))) return rc;
            i64 n = problems(s, &s->r[4], &traps);
            if (!n) return 0;
            if (n > 1 || !traps) {
                rc = stuck_verify(s, &s->r[4]);
            } else {
                copy_i(good, prog, s->L);
                have_good = 1;
                if ((rc = repairs(s, prog, &s->r[4]))) return rc;
                stuck_verify(s, &s->r[4]);
                if (s->npairs) {
                    keep(s, s->out + O_HEAD + s->L + VW(s) * (1 + s->out[O_NREP]++), &s->r[4]);
                    s->paths |= P_REPAIRED;
                }
            }
        }
        if (rc < 0) return rc;
        if (rc > 0 && !have_good) return rc;
        why = 1;
        if (!s->npairs) return why;
    }
    return why;
}

/* the useful items: the vaults first, then the rest, leaning to major spots */
static i64 useful(S *s) {
    const i64 *p = s->f + s->f[F_USEFUL], *ng = s->f + s->f[F_NONGEM];
    i64 n = p[0], nv = 0, rc;
    stream(s, 1);
    copy_i(s->list, p + 1, n);
    shuffle(&s->rng, s->list, n);
    for (i64 j = 1; j <= ng[0]; j++)
        if ((loc_row(s, ng[j])[L_FLAGS] & LF_VAULT) && s->placed[ng[j]] < 0) s->spots[nv++] = ng[j];
    shuffle(&s->rng, s->spots, nv);
    for (i64 v = 0; v < nv; v++) {
        i64 vault = s->spots[v], nf = 0, item, at;
        for (i64 j = 0; j < n; j++)
            if (ok(s, vault, s->list[j])) s->sa[nf++] = s->list[j];
        if (!nf) return stuck(s, W_VAULT_NONE, -1, vault);
        item = s->sa[below(&s->rng, nf)];
        for (at = 0; s->list[at] != item; at++) {}
        for (i64 j = at; j + 1 < n; j++) s->list[j] = s->list[j + 1];
        n--;
        s->assumed[item] -= (item_row(s, item)[I_FLAGS] & IF_READ) != 0;
        if ((rc = areach(s, -1, -1, &s->r[0]))) return rc;
        if (!has(s->r[0].got, vault)) return stuck(s, W_VAULT_UNSAFE, item, vault);
        put(s, vault, item);
        s->paths |= P_VAULT;
    }
    for (i64 j = 0; j < n; j++) {
        i64 item = s->list[j], m, total = 0, x;
        s->assumed[item] -= (item_row(s, item)[I_FLAGS] & IF_READ) != 0;
        if ((rc = areach(s, -1, -1, &s->r[0]))) return rc;
        m = safe(s, item, s->r[0].got, s->sa);
        if (!m) return stuck(s, W_NO_SAFE, item, -1);
        for (i64 q = 0; q < m; q++) total += (loc_row(s, s->sa[q])[L_FLAGS] & LF_MAJOR) ? WEIGHT : 1;
        x = below(&s->rng, total);
        for (i64 q = 0; q < m; q++) {
            i64 w = (loc_row(s, s->sa[q])[L_FLAGS] & LF_MAJOR) ? WEIGHT : 1;
            if (x < w) {
                put(s, s->sa[q], item);
                break;
            }
            x -= w;
        }
    }
    return 0;
}

/* the filler: by class, the non-gem items on the non-gem spots left, single gems and each yield's clusters */
static i64 filler(S *s) {
    const i64 *p = s->f + s->f[F_GROUPS], *ng = s->f + s->f[F_NONGEM];
    stream(s, 2);
    for (i64 g = 0, groups = *p++; g < groups; g++) {
        i64 label = p[0], ns = p[1], ni, nsp = 0;
        const i64 *sp = p + 2, *its;
        if (ns < 0) {   /* the non-gem group: the spots left */
            for (i64 j = 1; j <= ng[0]; j++)
                if (s->placed[ng[j]] < 0) s->spots[nsp++] = ng[j];
            ns = 0;
        } else {
            copy_i(s->spots, sp, ns);
            nsp = ns;
        }
        its = sp + ns;
        ni = its[0];
        copy_i(s->list, its + 1, ni);
        shuffle(&s->rng, s->list, ni);
        shuffle(&s->rng, s->spots, nsp);
        for (i64 j = 0; j < nsp; j++) {
            i64 loc = s->spots[j], at = -1;
            for (i64 q = 0; q < ni && at < 0; q++)
                if (ok(s, loc, s->list[q])) at = q;
            if (at < 0) return stuck(s, W_NO_FILLER, label, loc);
            i64 item = s->list[at];
            for (i64 q = at; q + 1 < ni; q++) s->list[q] = s->list[q + 1];
            ni--;
            put(s, loc, item);
        }
        p = its + 1 + its[0];
    }
    return 0;
}

static i64 attempt(S *s) {
    const i64 *p = s->f + s->f[F_PROG];
    i64 n = p[0], rc;
    int done;
    stream(s, 0);
    copy_i(s->list, p + 1, n);
    shuffle(&s->rng, s->list, n);
    for (i64 j = 0; j < n; j++) {
        i64 item = s->list[j], m, loc;
        s->assumed[item] -= (item_row(s, item)[I_FLAGS] & IF_READ) != 0;
        if ((rc = areach(s, -1, -1, &s->r[0]))) return rc;
        if ((rc = spots_for(s, item, &s->r[0], 0, s->sa, &m))) return rc;
        if (m) {
            if (!s->call[A_PIN]) loc = s->sa[below(&s->rng, m)];
            else if ((rc = pick(s, item, s->sa, m, &s->r[0], &loc))) return rc;
            put(s, loc, item);
        } else {
            if ((rc = trade(s, item, &s->r[0], &done))) return rc;
            if (!done) return stuck(s, W_NO_PROVEN, item, -1);
        }
    }
    if ((rc = settle(s))) return rc;
    if ((rc = useful(s))) return rc;
    if ((rc = filler(s))) return rc;
    {
        int traps;
        told(s, 1);
        if ((rc = reach(s, 0, -1, -1, 0, 1, 0, 0, &s->r[4]))) return rc;
        if (problems(s, &s->r[4], &traps)) return stuck_verify(s, &s->r[4]);
    }
    return 0;
}

/* ---- the workspace ----------------------------------------------------------------------------------------------- */
typedef struct {
    i64 *base, at;
} Carve;

static i64 *words(Carve *c, i64 n) {
    i64 *p = c->base ? c->base + c->at : 0;
    c->at += n > 0 ? n : 1;
    return p;
}

/* the attempt's state laid out on `ws` (none: only its size), for the blob `f`, the tables and the call */
static i64 lay(S *s, const i64 *f, const i64 **tabs, const i64 *call, i64 *ws) {
    Carve c = {ws, 0};
    i64 ub = 0, ib = 0, fw = 1, nc = 1, nt = call[A_TABS], L = f[F_L], I = f[F_I], ng = f[f[F_NONGEM]];
    i64 np = f[f[F_PROG]] > 0 ? f[f[F_PROG]] : 1, maxg = f[F_MAXGROUP] > ng ? f[F_MAXGROUP] : ng;
    for (i64 ti = 0; ti < nt; ti++) {
        i64 ints, u = az_reach_need(tabs[ti], &ints), w = (tabs[ti][H_F] + 63) / 64;
        if (u > ub) ub = u;
        if (ints > ib) ib = ints;
        if (w > fw) fw = w;
        if (tabs[ti][H_C] > nc) nc = tabs[ti][H_C];
    }
    s->L = L, s->I = I, s->G = f[F_GRAPHS], s->nw = (tabs[0][H_N] + 63) / 64, s->lw = (L + 63) / 64;
    s->namew = (f[F_NAMES] + 63) / 64;
    s->cap_rounds = L + tabs[0][H_F] + 2;
    for (i64 ti = 1; ti < nt; ti++)
        if (L + tabs[ti][H_F] + 2 > s->cap_rounds) s->cap_rounds = L + tabs[ti][H_F] + 2;
    s->wb = (u64 *)words(&c, ub), s->wi = words(&c, ib);
    s->c = words(&c, nc), s->held = words(&c, I), s->gives = words(&c, L);
    s->loc_round = words(&c, L), s->flag_round = words(&c, fw * 64), s->rout = words(&c, 2);
    s->flags = (u64 *)words(&c, fw), s->got = (u64 *)words(&c, s->lw), s->late = (u64 *)words(&c, s->lw);
    s->phys = (u64 *)words(&c, s->nw), s->traps = (u64 *)words(&c, s->nw);
    s->found_log = (u64 *)words(&c, s->cap_rounds * s->nw), s->walked_log = (u64 *)words(&c, s->cap_rounds * s->nw);
    for (int j = 0; j < 6; j++) {
        R *r = &s->r[j];
        r->got = (u64 *)words(&c, s->lw);
        r->nodes = (u64 *)words(&c, s->nw), r->safe = (u64 *)words(&c, s->nw);
        r->free = (u64 *)words(&c, s->nw), r->after = (u64 *)words(&c, s->nw);
    }
    s->placed = words(&c, L), s->base = words(&c, L), s->prog = words(&c, L), s->good = words(&c, L);
    s->snap = words(&c, L), s->assumed = words(&c, I), s->used = words(&c, s->G);
    s->gnew = (u64 *)words(&c, s->G * s->namew);
    s->sa = words(&c, maxg), s->sb = words(&c, maxg), s->list = words(&c, maxg), s->spots = words(&c, maxg);
    s->missed = words(&c, ng), s->best = words(&c, ng), s->pinned = words(&c, np), s->cand = words(&c, L);
    s->pairs = words(&c, 2 * np * (ng > np ? ng : np)), s->outs = words(&c, L), s->ins = words(&c, L);
    s->sph = words(&c, s->cap_rounds), s->bcount = words(&c, s->cap_rounds), s->bstart = words(&c, s->cap_rounds);
    s->border = words(&c, L);
    s->newt = (u64 *)words(&c, s->nw), s->tmp = (u64 *)words(&c, s->nw), s->acc = (u64 *)words(&c, s->nw);
    s->coll = (u64 *)words(&c, s->lw), s->was = (u64 *)words(&c, s->lw), s->fresh = (u64 *)words(&c, s->lw);
    return c.at;
}

/* ---- the acceptance's reaches (difficulty.need and play) ---------------------------------------------------------- */
/* The call's words after the attempt's: need (0) or play (1), the rung's table, play's stop (-1: none). The answer's:
 * 0, or 1 once a stage passed the stop (play's None); need's victory; the notes play's reaches tell; the stages. */
enum { Q_MODE = A_W, Q_TABLE, Q_STOP, Q_W };
enum { Q_STATUS, Q_VICTORY, Q_NOTES, Q_STAGES, Q_HEAD };

static i64 count_new(const S *s, const u64 *now, const u64 *got, const u64 *prog, u64 *fresh) {
    i64 n = 0;
    for (i64 w = 0; w < s->lw; w++) fresh[w] = now[w] & ~got[w], n += __builtin_popcountll(fresh[w] & prog[w]);
    return n;
}

/* difficulty.play's rounds (needed true), the candidate's placement in s->placed */
static i64 play(S *s, i64 e, i64 stop, i64 *out) {
    u64 *got = s->coll, *prog = s->was, *fresh = s->fresh;   /* what was collected, the progression, the new */
    i64 cur = 0, rc, *stages = out + Q_HEAD;
    for (;;) {
        for (;;) {
            out[Q_NOTES]++;
            if ((rc = reach(s, e, -1, -1, 0, 0, 0, got, &s->r[0]))) return rc;
            i64 n = count_new(s, s->r[0].got, got, prog, fresh);
            if (s->r[0].victory || !any(fresh, s->lw)) break;
            cur += n;
            for (i64 w = 0; w < s->lw; w++) got[w] |= fresh[w];
            if (stop >= 0 && cur > stop) return 1;
        }
        if (s->r[0].victory) break;
        out[Q_NOTES]++;
        if ((rc = reach(s, 0, -1, -1, 0, 0, 0, got, &s->r[1]))) return rc;
        i64 n = count_new(s, s->r[1].got, got, prog, fresh);
        int some = any(fresh, s->lw);
        if (!some && !s->r[1].victory) return -5;   /* the play stuck under its own options: the twin says so */
        stages[out[Q_STAGES]++] = cur;
        cur = n;
        for (i64 w = 0; w < s->lw; w++) got[w] |= fresh[w];
        if (stop >= 0 && cur > stop) return 1;
        if (!some) break;
    }
    stages[out[Q_STAGES]++] = cur;
    return 0;
}

/* difficulty.need (Q_MODE 0: one reach of the rung's table, its victory) or play (1) of the candidate `placement`
 * (each location's item, -1 none, -2 not in the placement: its vanilla item counts as progression), on the attempt's
 * blob, tables and workspace (az_attempt_need's). Returns 0 with the answer in `out` (Q_HEAD + L + 1 words), or < 0:
 * the twin runs. */
API i64 az_accept(const i64 *f, const i64 *t0, const i64 *t1, const i64 *t2, const i64 *t3, const i64 *call,
                  const i64 *placement, i64 *ws, i64 *out) {
    const i64 *tabs[4] = {t0, t1, t2, t3};
    S s;
    i64 e = call[Q_TABLE];
    if (f[F_MAGIC] != FILL_MAGIC || f[F_VERSION] != FILL_VERSION || call[A_TABS] < 1 || call[A_TABS] > 4 || e < 0
        || e >= call[A_TABS])
        return -1;
    lay(&s, f, tabs, call, ws);
    s.f = f, s.call = call;
    for (int j = 0; j < 4; j++) s.tabs[j] = tabs[j];
    s.reaches = 0;
    for (i64 j = 0; j < Q_HEAD; j++) out[j] = 0;
    for (i64 j = 0; j < s.I; j++) s.assumed[j] = 0;
    clear(s.was, s.lw);
    for (i64 loc = 0; loc < s.L; loc++) {   /* difficulty.progression: the placement over vanilla */
        i64 x = placement[loc] == -2 ? loc_row(&s, loc)[L_VANILLA] : placement[loc];
        s.placed[loc] = placement[loc] < 0 ? -1 : placement[loc];
        if (x >= 0 && item_row(&s, x)[I_CLASS] == CL_PROG) put_bit(s.was, loc);
    }
    if (call[Q_MODE] == 0) {
        i64 rc = reach(&s, e, -1, -1, 0, 0, 0, 0, &s.r[0]);
        if (rc) return rc;
        out[Q_VICTORY] = s.r[0].victory;
        return 0;
    }
    clear(s.coll, s.lw);
    i64 rc = play(&s, e, call[Q_STOP], out);
    if (rc < 0) return rc;
    out[Q_STATUS] = rc;
    return 0;
}

/* The workspace words az_attempt (and az_accept) need for this blob, tables and call. */
API i64 az_attempt_need(const i64 *f, const i64 *t0, const i64 *t1, const i64 *t2, const i64 *t3, const i64 *call) {
    const i64 *tabs[4] = {t0, t1, t2, t3};
    S s;
    if (f[F_MAGIC] != FILL_MAGIC || f[F_VERSION] != FILL_VERSION || call[A_TABS] < 1 || call[A_TABS] > 4) return -1;
    return lay(&s, f, tabs, call, 0);
}

/* fill._Slots.attempt: one attempt on the blob `f` and tables t0 (the plan's options) and t1..t3 (the rungs, A_TABS
 * of them in all), its streams' seeds in `call`; `ws` its workspace (az_attempt_need's words), `out` its answer:
 * O_STATUS 0 (placed: the placement at O_HEAD, each location's item or -1) or 1 (stuck: O_CODE's reason and its ids),
 * the told log and the repaired refusals. Returns 0, or < 0 when it can't (the tables or the blob aren't this build's,
 * the told log outgrew A_CAP, a reach refused): the caller runs the twin. */
API i64 az_attempt(const i64 *f, const i64 *t0, const i64 *t1, const i64 *t2, const i64 *t3, const i64 *call, i64 *ws,
                   i64 *out) {
    const i64 *tabs[4] = {t0, t1, t2, t3};
    S s;
    i64 rc;
    if (f[F_MAGIC] != FILL_MAGIC || f[F_VERSION] != FILL_VERSION || call[A_TABS] < 1 || call[A_TABS] > 4) return -1;
    lay(&s, f, tabs, call, ws);
    s.f = f, s.call = call;
    for (int j = 0; j < 4; j++) s.tabs[j] = tabs[j];
    s.cap = call[A_CAP], s.out = out, s.log = out + O_HEAD + s.L + VW(&s) * (MAX_REPAIRS + 2);
    s.err = 0, s.nlog = 0, s.reaches = 0, s.paths = 0, s.npinned = 0, s.npairs = 0, s.rounds = 0;
    for (i64 j = 0; j < O_HEAD; j++) out[j] = 0;
    for (i64 loc = 0; loc < s.L; loc++) s.base[loc] = s.placed[loc] = loc_row(&s, loc)[L_FIRST];
    s.start = s.nplaced = f[F_START];
    for (i64 j = 0; j < s.I; j++) s.assumed[j] = 0;
    for (i64 loc = 0; loc < s.L; loc++) {   /* the vanilla items of the spots to fill that the logic reads */
        i64 v = loc_row(&s, loc)[L_VANILLA];
        if ((loc_row(&s, loc)[L_FLAGS] & LF_POOL) && s.base[loc] < 0 && (item_row(&s, v)[I_FLAGS] & IF_READ))
            s.assumed[v]++;
    }
    for (i64 g = 0; g < s.G; g++) s.used[g] = 0;
    clear(s.gnew, s.G * s.namew);
    rc = attempt(&s);
    if (rc < 0) return rc;
    if (s.err) return s.err;
    out[O_STATUS] = rc;
    out[O_NLOG] = s.nlog, out[O_REACHES] = s.reaches, out[O_PATHS] = s.paths;
    copy_i(out + O_HEAD, s.placed, s.L);
    return 0;
}
