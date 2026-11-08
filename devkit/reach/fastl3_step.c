/* FastL3's step in C (Step R2.19m m2; azurik_mod/sim/l3_fast.py builds it with the pinned ziglang wheel's zig cc
 * into the AzurKit user cache and loads it with ctypes).  The project's own code: it calls Unicorn only through the
 * public C API's function pointers the caller hands it (whichever libunicorn the process loaded, the patched one or
 * the stock wheel's), so no Unicorn source or header is part of it.
 *
 * What it does, each the same as l3.L3's / l3_fast.FastL3's Python code it stands in for:
 *   fl3_fill    FastL3._fill, the virtual TLB's fill (a native UC_HOOK_TLB_FILL): code pages R+W+X, a fetch from
 *               another page counted and made code (rw_data's fault follows), a host call's lookup X alone, any
 *               other page R+W;
 *   h_entry     L3._update_entry: at the player update's entry with ECX the player and no row yet, the step's
 *               writes (the pad's floats first) written;
 *   h_camera    L3._camera: the camera direction the input builder reads written ([esp+0x14], when one is set) and
 *               read back;
 *   h_exit      L3._update_exit: at either RET, the blocks obs.read reads (deep=False) copied out for the caller to
 *               decode with obs.read itself;
 *   fl3_step    L3.step's player tick (scene=False) and L3._run: the pad's address, the main loop's poll between
 *               frames (a pending stream request returns 1 at once, before any write: the caller runs the Python
 *               step), the scheduler clock, the return slot, the register batch, the watchdog and emu_start.
 * A write is L3.write's: Unicorn's write, then (a page of it a code page, or code_inval off) the translations over
 * it dropped, else counted as a drop skipped (FastL3.ctl_remove_cache).  A read or write above L3's high bound
 * first maps the snapshot's high pages through the caller's touch callback (L3._touch), as L3.read and L3.write do.
 * An error inside a hook is kept (the first one) and stops the run, as Unicorn's Python binding does with a hook's
 * exception.
 *   h_walk      (Step R2.19m m4) the face loop of the static level's collision walk 0xD1B80 (head 0xD1E80): each face
 *               of a chunk's x range has its three i16 vertices put through the query's matrix ([esp+0x80..0xB8]) and
 *               stored as float32, then is dropped when all three lie below a bound or all above one ([esp+0x18,
 *               0x1C, 0x20], [esp+0xCC, 0xE8, 0xEC]); a face that isn't goes to the face test 0xB9E60.  At the head
 *               the hook works out the faces from ECX on that the game would drop, in C with the game's operations
 *               in its order (doubles: the x87 runs at 53 bits, round to nearest), and moves the loop's index (ECX and
 *               [esp+0x14]) to the first face it can't drop: one the game tests, one outside the exact envelope (a
 *               value not a zero or a double of dbl_fx's exponent range, a float32 store outside 2..253, a control
 *               word other than 53-bit round-to-nearest, a read that fails) or the range's last face.  The game then
 *               runs that face itself, whose every store, register and x87 slot is the one a dropped face also
 *               writes, so the state it leaves is the one the whole loop leaves.  The check mode moves nothing: it
 *               compares its decision on every face with the game's (the call path 0xD22B0, the merge 0xD22EE).  The watchdog is L3._Watchdog's: a thread looks at the step's deadline every 25 ms and stops a step
 * past it under the lock the step's arm and disarm take. */
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

typedef void uc_engine;
typedef int uc_err;
typedef struct { uint64_t paddr; int perms; } tlb_entry;   /* uc_tlb_entry: {uint64_t paddr; uc_prot perms;} */
typedef uc_err (*hook_add_t)(uc_engine *, size_t *, int, void *, void *, uint64_t, uint64_t, ...);
typedef uc_err (*hook_del_t)(uc_engine *, size_t);
typedef uc_err (*reg_read_t)(uc_engine *, int, void *);
typedef uc_err (*reg_write_t)(uc_engine *, int, const void *);
typedef uc_err (*reg_write_batch_t)(uc_engine *, int const *, void *const *, int);
typedef uc_err (*mem_read_t)(uc_engine *, uint64_t, void *, uint64_t);
typedef uc_err (*mem_write_t)(uc_engine *, uint64_t, const void *, uint64_t);
typedef uc_err (*emu_start_t)(uc_engine *, uint64_t, uint64_t, uint64_t, size_t);
typedef uc_err (*emu_stop_t)(uc_engine *);
typedef uc_err (*ctl_t)(uc_engine *, int, ...);
typedef void (*touch_t)(uint64_t, uint64_t);

#define MAXW 16          /* a step's writes, the pad's included */
#define WBUF 2048        /* their bytes */
#define NOB 5            /* obs.read's blocks without deep: entity, critter, player data, armor manager, slot */
#define OBN 0x170
#define NREG 16
#define NEED_PY 1
#define BATCH_ERR 2

typedef struct {         /* the API, the constants and the code pages (fl3_new's arguments, in this order) */
    void *hook_add, *hook_del, *reg_read, *reg_write, *reg_write_batch, *mem_read, *mem_write, *emu_start, *emu_stop,
        *ctl, *touch;
    int32_t r_ecx, r_esp, r_ebp, r_eip;
    int32_t hook_code, hook_tlb_fill, mem_fetch, ctl_remove_cache, code_inval;
    uint32_t player_update, camera_dir, update_ret0, update_ret1, stop, stack_esp, active_pad, controller_state,
        pad_size, stream_pending, entity, high;
    int32_t nfixed;
    int32_t fixed_ids[NREG];
    int32_t fixed_wide[NREG];    /* 1: a 32-bit value, 0: 16-bit (the FPU's control, status and tag words) */
    uint32_t fixed_vals[NREG];
    int32_t r_ebx, r_fpcw;
    uint32_t walk_head, walk_call, walk_merge;   /* the face loop's head, its face-test path, its merge (m4) */
} fl3_spec;

typedef struct {         /* a step's inputs and outputs (l3_fast._Io mirrors it) */
    uint8_t pad[72];
    int32_t nw;
    uint32_t wva[MAXW];
    uint32_t wlen[MAXW];
    uint8_t wdata[WBUF];
    int32_t cam_set;
    uint8_t cam[8];
    int32_t do_poll;
    double timeout_s;
    int32_t status, emu_err, hook_err;
    uint32_t eip, pv;
    int32_t in, row_done, cam_used_set;
    uint8_t cam_used[8];
    int32_t nob;
    uint32_t ob_va[NOB];
    uint32_t ob_n[NOB];
    uint8_t ob[NOB][OBN];
} fl3_io;

typedef struct {         /* counters (l3_fast._Stats mirrors it) */
    uint64_t fills, data_fetch, inval_skipped, steps;
    int32_t host;
    int32_t walk_mode;           /* 0 off, 1 drop faces, 2 check */
    uint64_t walk_heads, walk_dropped, walk_unsafe, walk_checked, walk_differ;
} fl3_stats;

typedef struct {
    hook_add_t hook_add;
    hook_del_t hook_del;
    reg_read_t reg_read;
    reg_write_t reg_write;
    reg_write_batch_t reg_write_batch;
    mem_read_t mem_read;
    mem_write_t mem_write;
    emu_start_t emu_start;
    emu_stop_t emu_stop;
    ctl_t ctl;
    touch_t touch;
    fl3_spec s;
    uc_engine *uc;
    uint8_t *code;               /* a bit a page (VA >> 12) */
    uint32_t *fetched;           /* the data pages fetched from, in order */
    int64_t nfetched, capfetched;
    fl3_io io;
    fl3_stats st;
    size_t h_fill, h_entry, h_camera, h_exit0, h_exit1, h_walk, h_wcall, h_wmerge;
    int hooks_on, fill_on;
    int wpred;                   /* check mode: the decision on the face the game is on (-1 none, 0 test, 1 drop) */
    int wcalled;
    void *regvals[NREG + 3];
    int32_t regids[NREG + 3];
    uint32_t regbuf[NREG + 3];
    uint16_t regbuf16[NREG + 3];
    pthread_t wd;
    pthread_mutex_t mu;
    double deadline;
    int armed, quit, wd_on;
} fl3_ctx;

static inline int is_code(const fl3_ctx *c, uint32_t p) { return (c->code[p >> 3] >> (p & 7)) & 1; }
static inline void set_code(fl3_ctx *c, uint32_t p) { c->code[p >> 3] |= (uint8_t)(1u << (p & 7)); }

static double now_s(void)
{
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (double)t.tv_sec + (double)t.tv_nsec * 1e-9;
}

static void *wd_main(void *p)
{
    fl3_ctx *c = p;
    for (;;) {
        usleep(25000);
        pthread_mutex_lock(&c->mu);
        if (c->quit) {
            pthread_mutex_unlock(&c->mu);
            return NULL;
        }
        if (c->armed && now_s() >= c->deadline) {
            c->emu_stop(c->uc);   /* again each period until disarmed: a stop before emu_start begins is lost */
        }
        pthread_mutex_unlock(&c->mu);
    }
}

/* FastL3.ctl_remove_cache's rule for [va, va + n) */
static void drop(fl3_ctx *c, uint32_t va, uint32_t n)
{
    uint32_t a = va >> 12, b = (uint32_t)(((uint64_t)va + n - 1) >> 12), p;
    if (c->s.code_inval) {
        int any = 0;
        if (b - a <= 1) {
            any = is_code(c, a) || is_code(c, b);
        } else {
            for (p = a; p <= b && !any; p++) {
                any = is_code(c, p);
            }
        }
        if (!any) {
            c->st.inval_skipped++;
            return;
        }
    }
    c->ctl(c->uc, c->s.ctl_remove_cache, (uint64_t)va, (uint64_t)va + n);
}

/* L3.read: 0, or Unicorn's error (above the high bound the snapshot's pages are touched first) */
static uc_err rd(fl3_ctx *c, uint32_t va, void *out, uint32_t n)
{
    uc_err e = c->mem_read(c->uc, va, out, n);
    if (e && (uint64_t)va + n > c->s.high) {
        c->touch(va, n);
        e = c->mem_read(c->uc, va, out, n);
    }
    return e;
}

/* L3.write */
static uc_err wr(fl3_ctx *c, uint32_t va, const void *data, uint32_t n)
{
    uc_err e;
    if ((uint64_t)va + n > c->s.high) {
        c->touch(va, n);
    }
    e = c->mem_write(c->uc, va, data, n);
    if (e) {
        return e;
    }
    if (n) {
        drop(c, va, n);
    }
    return 0;
}

static void hook_fail(fl3_ctx *c, uc_err e)
{
    if (!c->io.hook_err) {
        c->io.hook_err = e;
    }
    c->emu_stop(c->uc);
}

static bool fl3_fill(uc_engine *uc, uint64_t vaddr, int type, tlb_entry *e, void *ud)
{
    fl3_ctx *c = ud;
    uint32_t p = (uint32_t)(vaddr >> 12);
    (void)uc;
    c->st.fills++;
    e->paddr = vaddr & ~(uint64_t)0xFFF;
    if (is_code(c, p)) {
        e->perms = 7;
    } else if (type == c->s.mem_fetch) {
        if (c->s.code_inval && !c->st.host) {   /* a fetch, not a drop's lookup: counted; with rw_data it faults */
            c->st.data_fetch++;
            if (c->nfetched == c->capfetched) {
                int64_t cap = c->capfetched ? 2 * c->capfetched : 64;
                uint32_t *f = realloc(c->fetched, (size_t)cap * sizeof *f);
                if (f) {
                    c->fetched = f;
                    c->capfetched = cap;
                }
            }
            if (c->nfetched < c->capfetched) {
                c->fetched[c->nfetched++] = p;
            }
            set_code(c, p);
            e->perms = 7;
        } else {                                 /* uc_invalidate_tb's lookup (a drop over a data page, an unmap) */
            e->perms = 4;
        }
    } else {
        e->perms = 3;
    }
    return true;
}

static void h_entry(uc_engine *uc, uint64_t addr, uint32_t size, void *ud)
{
    fl3_ctx *c = ud;
    uint32_t ecx = 0, off = 0;
    int32_t i;
    uc_err e;
    (void)addr, (void)size;
    if ((e = c->reg_read(uc, c->s.r_ecx, &ecx))) {
        hook_fail(c, e);
        return;
    }
    if (ecx == c->s.entity && !c->io.in && !c->io.row_done) {
        if ((e = wr(c, c->io.pv, c->io.pad, sizeof c->io.pad))) {
            hook_fail(c, e);
            return;
        }
        for (i = 0; i < c->io.nw; i++) {
            if ((e = wr(c, c->io.wva[i], c->io.wdata + off, c->io.wlen[i]))) {
                hook_fail(c, e);
                return;
            }
            off += c->io.wlen[i];
        }
        c->io.in = 1;
    }
}

static void h_camera(uc_engine *uc, uint64_t addr, uint32_t size, void *ud)
{
    fl3_ctx *c = ud;
    uint32_t esp = 0;
    uc_err e;
    (void)addr, (void)size;
    if (!c->io.in) {
        return;
    }
    if ((e = c->reg_read(uc, c->s.r_esp, &esp))) {
        hook_fail(c, e);
        return;
    }
    if (c->io.cam_set && (e = wr(c, esp + 0x14, c->io.cam, 8))) {
        hook_fail(c, e);
        return;
    }
    if ((e = rd(c, esp + 0x14, c->io.cam_used, 8))) {
        hook_fail(c, e);
        return;
    }
    c->io.cam_used_set = 1;
}

static int block(fl3_ctx *c, uint32_t va, uint32_t n)
{
    uc_err e;
    int i = c->io.nob;
    c->io.ob_va[i] = va;
    c->io.ob_n[i] = n;
    if ((e = rd(c, va, c->io.ob[i], n))) {
        hook_fail(c, e);
        return 0;
    }
    c->io.nob = i + 1;
    return 1;
}

static uint32_t u32at(const uint8_t *b, uint32_t off)
{
    uint32_t v;
    memcpy(&v, b + off, 4);
    return v;
}

/* obs.read's reads without deep: the entity [0, 0x16C), the critter's [+0x154, +0x218), the player data's
 * [+0xCC, +0xE8), the armor manager's [+0x20, +0x28) and the slot's [+0x08, +0x3C) */
static void h_exit(uc_engine *uc, uint64_t addr, uint32_t size, void *ud)
{
    fl3_ctx *c = ud;
    uint32_t crit, pd, am, slot;
    (void)uc, (void)addr, (void)size;
    if (!c->io.in) {
        return;
    }
    c->io.in = 0;
    c->io.nob = 0;
    if (!block(c, c->s.entity, 0x16C)) {
        return;
    }
    crit = u32at(c->io.ob[0], 0x20);
    if (!block(c, crit + 0x154, 0x218 - 0x154)) {
        return;
    }
    pd = u32at(c->io.ob[1], 0);
    if (pd) {
        if (!block(c, pd + 0xCC, 0xE8 - 0xCC)) {
            return;
        }
        am = u32at(c->io.ob[2], 0);
        if (am) {
            if (!block(c, am + 0x20, 8)) {
                return;
            }
            slot = u32at(c->io.ob[3], 0);
            if (slot && !block(c, slot + 0x08, 0x3C - 0x08)) {
                return;
            }
        }
    }
    c->io.row_done = 1;
}

fl3_ctx *fl3_new(uc_engine *uc, const fl3_spec *s, const uint32_t *code, int64_t ncode)
{
    fl3_ctx *c = calloc(1, sizeof *c);
    int64_t i;
    if (!c) {
        return NULL;
    }
    c->code = calloc(1u << 17, 1);
    if (!c->code) {
        free(c);
        return NULL;
    }
    c->s = *s;
    c->uc = uc;
    c->hook_add = (hook_add_t)s->hook_add;
    c->hook_del = (hook_del_t)s->hook_del;
    c->reg_read = (reg_read_t)s->reg_read;
    c->reg_write = (reg_write_t)s->reg_write;
    c->reg_write_batch = (reg_write_batch_t)s->reg_write_batch;
    c->mem_read = (mem_read_t)s->mem_read;
    c->mem_write = (mem_write_t)s->mem_write;
    c->emu_start = (emu_start_t)s->emu_start;
    c->emu_stop = (emu_stop_t)s->emu_stop;
    c->ctl = (ctl_t)s->ctl;
    c->touch = (touch_t)s->touch;
    for (i = 0; i < ncode; i++) {
        if (code[i] < (1u << 20)) {
            set_code(c, code[i]);
        }
    }
    pthread_mutex_init(&c->mu, NULL);
    if (pthread_create(&c->wd, NULL, wd_main, c) == 0) {
        c->wd_on = 1;
    }
    return c;
}

void fl3_free(fl3_ctx *c)
{
    if (!c) {
        return;
    }
    if (c->wd_on) {
        pthread_mutex_lock(&c->mu);
        c->quit = 1;
        pthread_mutex_unlock(&c->mu);
        pthread_join(c->wd, NULL);
    }
    pthread_mutex_destroy(&c->mu);
    free(c->fetched);
    free(c->code);
    free(c);
}

fl3_io *fl3_io_of(fl3_ctx *c) { return &c->io; }
fl3_stats *fl3_stats_of(fl3_ctx *c) { return &c->st; }
int64_t fl3_fetched(fl3_ctx *c, int64_t from, uint32_t *out, int64_t cap)
{
    int64_t n = 0;
    while (from + n < c->nfetched && n < cap) {
        out[n] = c->fetched[from + n];
        n++;
    }
    return n;
}

/* the TLB fill hook (once, FastL3's vtlb) */
uc_err fl3_fill_hook(fl3_ctx *c)
{
    uc_err e = c->hook_add(c->uc, &c->h_fill, c->s.hook_tlb_fill, (void *)fl3_fill, c, 1, 0);
    c->fill_on = !e;
    return e;
}

/* the update's entry, camera and exit hooks on (1) or off (0) */
uc_err fl3_hooks(fl3_ctx *c, int on)
{
    uc_err e = 0;
    if (on && !c->hooks_on) {
        if ((e = c->hook_add(c->uc, &c->h_entry, c->s.hook_code, (void *)h_entry, c, c->s.player_update,
                             c->s.player_update)) ||
            (e = c->hook_add(c->uc, &c->h_camera, c->s.hook_code, (void *)h_camera, c, c->s.camera_dir,
                             c->s.camera_dir)) ||
            (e = c->hook_add(c->uc, &c->h_exit0, c->s.hook_code, (void *)h_exit, c, c->s.update_ret0,
                             c->s.update_ret0)) ||
            (e = c->hook_add(c->uc, &c->h_exit1, c->s.hook_code, (void *)h_exit, c, c->s.update_ret1,
                             c->s.update_ret1))) {
            return e;
        }
        c->hooks_on = 1;
    } else if (!on && c->hooks_on) {
        c->hook_del(c->uc, c->h_entry);
        c->hook_del(c->uc, c->h_camera);
        c->hook_del(c->uc, c->h_exit0);
        c->hook_del(c->uc, c->h_exit1);
        c->hooks_on = 0;
    }
    return e;
}

/* -- the collision walk's face loop (m4) ------------------------------------------------------------------------ */

/* a value the x87 at 53 bits holds as this double exactly: a zero, or dbl_fx's exponent range (the patch's rule) */
static inline int dok(double d)
{
    uint64_t b;
    uint32_t de;
    memcpy(&b, &d, 8);
    de = (uint32_t)(b >> 52) & 0x7ff;
    return (b << 1) == 0 || (de >= 2 && de <= 2045);
}

/* fstp dword: the double rounded to float32, when its exponent is in 2..253 or it is a zero (the patch's rule) */
static inline int f32ok(double d, float *out)
{
    float f = (float)d;
    uint32_t b, e;
    memcpy(&b, &f, 4);
    e = (b >> 23) & 0xff;
    *out = f;
    return (e >= 2 && e <= 253) || d == 0.0;
}

typedef struct {
    float m80, m84, m88, m90, m94, m98, ma0, ma4, ma8, mb0, mb4, mb8;   /* the matrix, [esp+0x80..0xB8] */
    float lo[3], hi[3];                                                 /* the bounds */
} walk_frame;

/* a vertex (i16 x, y, z) through the matrix as the game's x87 code does it: 0 outside the envelope */
static inline int wvert(const walk_frame *w, const uint8_t *v, float out[3])
{
    int16_t xi, yi, zi;
    double X, Y, Z, a, b, s;
    memcpy(&xi, v, 2);
    memcpy(&yi, v + 2, 2);
    memcpy(&zi, v + 4, 2);
    X = (double)xi;
    Y = (double)yi;
    Z = (double)zi;
    /* x' = ((m80 X + mA0 Z) + m90 Y) + mB0 */
    a = (double)w->m80 * X;
    b = (double)w->ma0 * Z;
    if (!dok(a) || !dok(b)) return 0;
    s = a + b;
    if (!dok(s)) return 0;
    a = (double)w->m90 * Y;
    if (!dok(a)) return 0;
    s = s + a;
    if (!dok(s)) return 0;
    s = s + (double)w->mb0;
    if (!dok(s) || !f32ok(s, &out[0])) return 0;
    /* y' = ((mA4 Z + m94 Y) + m84 X) + mB4 */
    a = (double)w->ma4 * Z;
    b = (double)w->m94 * Y;
    if (!dok(a) || !dok(b)) return 0;
    s = a + b;
    if (!dok(s)) return 0;
    a = (double)w->m84 * X;
    if (!dok(a)) return 0;
    s = s + a;
    if (!dok(s)) return 0;
    s = s + (double)w->mb4;
    if (!dok(s) || !f32ok(s, &out[1])) return 0;
    /* z' = ((mA8 Z + m98 Y) + m88 X) + mB8 */
    a = (double)w->ma8 * Z;
    b = (double)w->m98 * Y;
    if (!dok(a) || !dok(b)) return 0;
    s = a + b;
    if (!dok(s)) return 0;
    a = (double)w->m88 * X;
    if (!dok(a)) return 0;
    s = s + a;
    if (!dok(s)) return 0;
    s = s + (double)w->mb8;
    if (!dok(s) || !f32ok(s, &out[2])) return 0;
    return 1;
}

/* the game's decision on a face: 1 dropped (all three vertices below a bound or above one), 0 tested, -1 outside
 * the envelope */
static inline int wface(const walk_frame *w, const uint8_t *vtx, uint32_t nv, const uint8_t *face)
{
    float p[3][3];
    int k, ax;
    for (k = 0; k < 3; k++) {
        if (face[k] >= nv || !wvert(w, vtx + 6u * face[k], p[k])) {
            return -1;
        }
    }
    for (ax = 0; ax < 3; ax++) {
        if (p[0][ax] < w->lo[ax] && p[1][ax] < w->lo[ax] && p[2][ax] < w->lo[ax]) {
            return 1;
        }
    }
    for (ax = 0; ax < 3; ax++) {
        if (p[0][ax] > w->hi[ax] && p[1][ax] > w->hi[ax] && p[2][ax] > w->hi[ax]) {
            return 1;
        }
    }
    return 0;
}

static int wread(fl3_ctx *c, uint32_t *esp, uint32_t *ebx, int32_t *i, int32_t *end, walk_frame *w)
{
    uint8_t fr[0xF0];
    uint16_t fpcw = 0;
    if (c->reg_read(c->uc, c->s.r_fpcw, &fpcw) || (fpcw & 0x0F00) != 0x0200) {   /* 53-bit, round to nearest */
        return 0;
    }
    if (c->reg_read(c->uc, c->s.r_esp, esp) || c->reg_read(c->uc, c->s.r_ebx, ebx) ||
        c->reg_read(c->uc, c->s.r_ecx, i) || c->mem_read(c->uc, *esp, fr, sizeof fr)) {
        return 0;
    }
    memcpy(end, fr + 0x30, 4);
    memcpy(&w->m80, fr + 0x80, 4); memcpy(&w->m84, fr + 0x84, 4); memcpy(&w->m88, fr + 0x88, 4);
    memcpy(&w->m90, fr + 0x90, 4); memcpy(&w->m94, fr + 0x94, 4); memcpy(&w->m98, fr + 0x98, 4);
    memcpy(&w->ma0, fr + 0xA0, 4); memcpy(&w->ma4, fr + 0xA4, 4); memcpy(&w->ma8, fr + 0xA8, 4);
    memcpy(&w->mb0, fr + 0xB0, 4); memcpy(&w->mb4, fr + 0xB4, 4); memcpy(&w->mb8, fr + 0xB8, 4);
    memcpy(&w->lo[0], fr + 0x18, 4); memcpy(&w->lo[1], fr + 0x1C, 4); memcpy(&w->lo[2], fr + 0x20, 4);
    memcpy(&w->hi[0], fr + 0xCC, 4); memcpy(&w->hi[1], fr + 0xE8, 4); memcpy(&w->hi[2], fr + 0xEC, 4);
    return 1;
}

static void h_walk(uc_engine *uc, uint64_t addr, uint32_t size, void *ud)
{
    fl3_ctx *c = ud;
    uint32_t esp, ebx, nv;
    int32_t i, end, j, last;
    walk_frame w;
    uint8_t hdr[0x10], faces[4 * 256], vtx[6 * 256];
    (void)uc, (void)addr, (void)size;
    c->st.walk_heads++;
    c->wpred = -1;
    c->wcalled = 0;
    if (!wread(c, &esp, &ebx, &i, &end, &w) || i < 0 || i >= end) {
        c->st.walk_unsafe++;
        return;
    }
    if (c->mem_read(c->uc, ebx, hdr, 7)) {
        c->st.walk_unsafe++;
        return;
    }
    nv = hdr[6];
    last = c->st.walk_mode == 2 ? i + 1 : end - 1;   /* the check decides one face; the range's last stays the game's */
    if (last > i + 256) {
        last = i + 256;
    }
    if (last <= i || c->mem_read(c->uc, ebx + 0x16 + 6u * nv + 4u * (uint32_t)i, faces, 4u * (uint32_t)(last - i)) ||
        (nv && c->mem_read(c->uc, ebx + 0x16, vtx, 6u * nv))) {
        if (c->st.walk_mode == 2 && last > i) {
            c->st.walk_unsafe++;
        }
        return;
    }
    if (c->st.walk_mode == 2) {
        int d = wface(&w, vtx, nv, faces);
        if (d < 0) {
            c->st.walk_unsafe++;
            return;
        }
        c->wpred = d;
        return;
    }
    for (j = i; j < last; j++) {
        int d = wface(&w, vtx, nv, faces + 4 * (j - i));
        if (d != 1) {
            if (d < 0) {
                c->st.walk_unsafe++;
            }
            break;
        }
    }
    if (j > i) {
        uint32_t jj = (uint32_t)j;
        c->st.walk_dropped += (uint64_t)(j - i);
        c->reg_write(c->uc, c->s.r_ecx, &jj);
        c->mem_write(c->uc, esp + 0x14, &jj, 4);
    }
}

static void h_wcall(uc_engine *uc, uint64_t addr, uint32_t size, void *ud)
{
    fl3_ctx *c = ud;
    (void)uc, (void)addr, (void)size;
    c->wcalled = 1;
}

static void h_wmerge(uc_engine *uc, uint64_t addr, uint32_t size, void *ud)
{
    fl3_ctx *c = ud;
    (void)uc, (void)addr, (void)size;
    if (c->wpred >= 0) {          /* the game dropped the face (no call) or tested it: the check's decision */
        c->st.walk_checked++;
        c->st.walk_differ += (c->wpred == 1) == (c->wcalled != 0);
    }
    c->wpred = -1;
}

/* the face loop's hook: mode 1 drops faces, 2 checks every decision, 0 off */
uc_err fl3_walk(fl3_ctx *c, int mode)
{
    uc_err e;
    if (mode == c->st.walk_mode) {
        return 0;
    }
    if (c->st.walk_mode) {
        c->hook_del(c->uc, c->h_walk);
        if (c->st.walk_mode == 2) {
            c->hook_del(c->uc, c->h_wcall);
            c->hook_del(c->uc, c->h_wmerge);
        }
        c->st.walk_mode = 0;
    }
    if (!mode) {
        return 0;
    }
    if ((e = c->hook_add(c->uc, &c->h_walk, c->s.hook_code, (void *)h_walk, c, c->s.walk_head, c->s.walk_head))) {
        return e;
    }
    if (mode == 2 &&
        ((e = c->hook_add(c->uc, &c->h_wcall, c->s.hook_code, (void *)h_wcall, c, c->s.walk_call, c->s.walk_call)) ||
         (e = c->hook_add(c->uc, &c->h_wmerge, c->s.hook_code, (void *)h_wmerge, c, c->s.walk_merge,
                          c->s.walk_merge)))) {
        return e;
    }
    c->st.walk_mode = mode;
    c->wpred = -1;
    return 0;
}

static int need_py(fl3_ctx *c)
{
    c->io.status = NEED_PY;
    return NEED_PY;
}

/* L3.step's player tick (scene=False) with the hooks above: 0 when it ran (io.emu_err, io.hook_err, io.eip and the
 * row's blocks say how), NEED_PY when a read it must make fails or a stream request is pending (nothing written:
 * the caller runs the Python step), BATCH_ERR when the register batch fails (io.emu_err its error) */
int fl3_step(fl3_ctx *c)
{
    fl3_io *io = &c->io;
    uint32_t idx, pv, sched, stop = c->s.stop, esp = c->s.stack_esp, ebp, ecx = c->s.entity, sp;
    uint8_t padmem[0x54], clock[8], probe[8], latch[12], zeros[0x48];
    int32_t i, n = c->s.nfixed;
    uc_err e;
    io->status = io->emu_err = io->hook_err = 0;
    io->in = io->row_done = io->cam_used_set = 0;
    io->nob = 0;
    /* the reads first, so that a failing one leaves nothing written */
    if (rd(c, c->s.active_pad, &idx, 4)) {
        return need_py(c);
    }
    pv = c->s.controller_state + c->s.pad_size * (idx < 4 ? idx : 0);
    if (io->do_poll) {
        if (c->mem_read(c->uc, c->s.stream_pending, &sp, 4) == 0 && sp != c->s.stream_pending) {
            return need_py(c);   /* the main loop's stream poll runs guest code: the Python step's */
        }
        if (rd(c, pv, padmem, sizeof padmem)) {
            return need_py(c);
        }
    }
    if (rd(c, ecx + 0xC, &sched, 4) || rd(c, ecx + 0x18, clock, 8) || rd(c, sched + 0x10, probe, 8)) {
        return need_py(c);
    }
    io->pv = pv;
    if (io->do_poll) {   /* the main loop's poll 0xA2880: a button that read 0 frees its latch; then neutral */
        for (i = 0; i < 12; i++) {
            float f;
            memcpy(&f, padmem + 0x18 + 4 * i, 4);
            latch[i] = f == 0.0f ? 0 : padmem[0x48 + i];
        }
        memset(zeros, 0, sizeof zeros);
        if (wr(c, pv + 0x48, latch, 12) || wr(c, pv, zeros, sizeof zeros)) {
            return need_py(c);   /* not reached: those pages were read */
        }
    }
    if (rd(c, ecx + 0x18, clock, 8) || wr(c, sched + 0x10, clock, 8) || wr(c, esp, &stop, 4)) {
        return need_py(c);       /* not reached: those pages were read */
    }
    ebp = esp + 0x100;
    for (i = 0; i < n; i++) {
        c->regids[i] = c->s.fixed_ids[i];
        if (c->s.fixed_wide[i]) {
            c->regbuf[i] = c->s.fixed_vals[i];
            c->regvals[i] = &c->regbuf[i];
        } else {
            c->regbuf16[i] = (uint16_t)c->s.fixed_vals[i];
            c->regvals[i] = &c->regbuf16[i];
        }
    }
    c->regids[n] = c->s.r_esp;
    c->regbuf[n] = esp;
    c->regvals[n] = &c->regbuf[n];
    c->regids[n + 1] = c->s.r_ebp;
    c->regbuf[n + 1] = ebp;
    c->regvals[n + 1] = &c->regbuf[n + 1];
    c->regids[n + 2] = c->s.r_ecx;
    c->regbuf[n + 2] = ecx;
    c->regvals[n + 2] = &c->regbuf[n + 2];
    if ((e = c->reg_write_batch(c->uc, c->regids, c->regvals, n + 3))) {
        io->status = BATCH_ERR;  /* L3._run's batch raises its UcError as it is */
        io->emu_err = e;
        return BATCH_ERR;
    }
    pthread_mutex_lock(&c->mu);
    c->deadline = now_s() + io->timeout_s;
    c->armed = 1;
    pthread_mutex_unlock(&c->mu);
    io->emu_err = c->emu_start(c->uc, c->s.player_update, stop, 0, 0);
    pthread_mutex_lock(&c->mu);
    c->armed = 0;
    pthread_mutex_unlock(&c->mu);
    c->reg_read(c->uc, c->s.r_eip, &io->eip);
    c->st.steps++;
    return 0;
}
