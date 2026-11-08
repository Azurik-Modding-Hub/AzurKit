/* Step R2.19p: the reach engine's launch controllers in C (PLAN-v3's "R2.19p, the controllers in C"), built with the
 * kernel as one unit (this file includes kernel.c, so a tick's step inlines into the launch loop).
 *
 * p_launches runs one launch family on the kernel, as ``macros.launches`` runs it on ``backend.KernelSim``: each
 * launch under its controller (R0's ``macros._Run``, ``aim.Aim`` or ``aim.Sched``: the run-up and the press lead, the
 * roll's buttons, ``flap_due``, the recast, the predictive landing control and its curve, hold, home and brake, the
 * envelope's schedule, and the ends), each tick's pad from the row before, the ticks whose pads the family shares
 * stepped once and a pad that parts from the first's going on from that tick's saved Player (the same order, the same
 * saved states).  It returns each launch's end, the rows an outcome reads (the last, the first touch-down, the takeoff)
 * and its pads as the witness string's run-length segments (the stick, the buttons, the camera's f32 pair).
 *
 * A copy: the Python controllers stay the L3 route's and the reference, and ``reach_native/backend.py`` pins their
 * sources (``SHADOWS``: the kernel route refuses while one has moved) and passes every named constant in (``Consts``),
 * so a constant can't part from its copy.  The float rule: double arithmetic in Python's order, nothing contracted
 * (the pragma after kernel.c's include: the kernel's own floats keep the build's contraction, as kernel.c alone
 * compiles them), libm's sin, cos, atan2 and pow called through pointers (no sincos merge or pow(x, 2) rewrite: the
 * same libm calls CPython makes), and CPython's own hypot (its vector_norm), round, float
 * modulo, atan2 special cases and builtin sum ported.  Where Python would raise (a non-finite heading at the stick, a
 * non-finite landing time), p_launches returns -1 and the caller runs the family in Python, which raises as before.
 * Positions never leave the caller. */
#include <float.h>

#include "kernel.c"
#pragma STDC FP_CONTRACT OFF

enum { CK_WALKOFF = 0, CK_RUNJUMP = 1, CK_STANDJUMP = 2, CK_ROLLJUMP = 3 };
enum { CC_RUN = 0, CC_AIM = 1, CC_SCHED = 2 };
enum { CE_TICKS = 0, CE_SETTLED, CE_UNSETTLED, CE_WALKED, CE_DEAD, CE_AIRCAP, CE_STUCK, CE_STAYED, CE_FLAG };
enum { CB_Y = 1, CB_LT = 2, CB_BLACK = 4 };
#define CT_MAXL 32               /* the most launches a family runs here (more: the caller's Python) */

typedef struct {              /* the controllers' named constants, from their Python modules (``backend._consts``) */
    int ticks, air_cap, run_cap, stuck, still, settle, swim_hold, jump_hold, chain0, chain1, roll_y, roll_tap,
        roll_period, roll_ticks, cast_wait, turn, home_ticks, brake_ticks, tries;
    int airborne[2], dead[2], settled[2], swimming, slide;
    double flap_margin, h_air, descent_d, gravity, fps, flap_mult, short_m, home_m, brake_v, cam_rate, snap_deg,
        dead_raw, raw_scale, gate_raw, flat_nz, rest_mps, dt, gdt, blend;
} CtConsts;

typedef struct { int kind, flaps, rolls, recast, hold; double curve, lead, ac; } CtMac;   /* a Macro; ac its kit's */

typedef struct {              /* the family: its controller, start, run-up, target, home and schedule */
    int ctl, n, hp, has_target, has_home, nsched;
    double heading, cam, back, start[3], target[3], home[3];
    const double *sched;
} CtFam;

typedef struct {              /* a launch's answer (rows indexed from its first launch row; -1 none) */
    int end, code, n, first, first_state, air, took, took_state, last_state, flaps, seg0, nseg;
    double last[3], firstp[3], tookp[3];
} CtLOut;

typedef struct { int n, buttons; double sx, sy, cx, cy; } CtSeg;   /* a run of equal pads */

typedef struct { double sx, sy, yaw; int b; } CtCPad;              /* an ``l3.Pad``: its stick, its yaw, the buttons */

typedef struct {
    const CtMac *m;
    double cam, dx, dy;
    int jump_at, took, first, settle, settle_state, still, air, presses, rest, recasts, cast_at, pend;
    int n, air_i, flaps, first_state, lastb;
    double firstp[3];
    CtCPad *pads;               /* [ticks] the pads it saw, and the camera's f32 pair each one's row read */
    float *cam32;             /* [2 ticks] */
    double *pos;              /* [3 ticks] its rows' body centres */
    int *state;               /* [ticks] */
} CtRun;

/* -- CPython's maths ------------------------------------------------------------------------------------------- */
static double (*volatile CT_SIN)(double) = sin;
static double (*volatile CT_COS)(double) = cos;
static double (*volatile CT_ATAN2)(double, double) = atan2;
static double (*volatile CT_POW)(double, double) = pow;
static const double CT_PI = 3.141592653589793, CT_RAD2DEG = 180.0 / 3.141592653589793,
                    CT_DEG2RAD = 3.141592653589793 / 180.0;   /* math.pi; math.degrees' and radians' factors */

typedef struct { double hi, lo; } CtDL;
static inline CtDL ct_dl_fast_sum(double a, double b) { double x = a + b; double y = (a - x) + b; return (CtDL){x, y}; }
static inline CtDL ct_dl_mul(double x, double y) { double z = x * y; return (CtDL){z, fma(x, y, -z)}; }

/* mathmodule.c's ct_vector_norm (math.hypot) */
static double ct_vector_norm(int n, double *vec, double max, int found_nan) {
    double x, h, scale, csum = 1.0, frac1 = 0.0, frac2 = 0.0;
    CtDL pr, sm;
    int max_e;
    if (isinf(max)) return max;
    if (found_nan) return NAN;
    if (max == 0.0 || n <= 1) return max;
    frexp(max, &max_e);
    if (max_e < -1023) {
        for (int i = 0; i < n; i++) vec[i] /= DBL_MIN;
        return DBL_MIN * ct_vector_norm(n, vec, max / DBL_MIN, found_nan);
    }
    scale = ldexp(1.0, -max_e);
    for (int i = 0; i < n; i++) {
        x = vec[i];
        x *= scale;
        pr = ct_dl_mul(x, x);
        sm = ct_dl_fast_sum(csum, pr.hi);
        csum = sm.hi;
        frac1 += pr.lo;
        frac2 += sm.lo;
    }
    h = sqrt(csum - 1.0 + (frac1 + frac2));
    pr = ct_dl_mul(-h, h);
    sm = ct_dl_fast_sum(csum, pr.hi);
    csum = sm.hi;
    frac1 += pr.lo;
    frac2 += sm.lo;
    x = csum - 1.0 + (frac1 + frac2);
    h += x / (2.0 * h);
    return h / scale;
}

/* math.hypot of n (at most 3) coordinates */
double c_hypot(int n, const double *v) {
    double c[3], max = 0.0;
    int found_nan = 0;
    for (int i = 0; i < n; i++) {
        double x = fabs(v[i]);
        c[i] = x;
        found_nan |= isnan(x);
        if (x > max) max = x;
    }
    return ct_vector_norm(n, c, max, found_nan);
}

static double ct_hyp2(double x, double y) { double v[2] = {x, y}; return c_hypot(2, v); }

/* mathmodule.c's m_atan2 (math.atan2) */
static double ct_py_atan2(double y, double x) {
    if (isnan(x) || isnan(y)) return NAN;
    if (isinf(y)) {
        if (isinf(x)) return copysign(copysign(1., x) == 1. ? 0.25 * CT_PI : 0.75 * CT_PI, y);
        return copysign(0.5 * CT_PI, y);
    }
    if (isinf(x) || y == 0.) return copysign(copysign(1., x) == 1. ? 0. : CT_PI, y);
    return CT_ATAN2(y, x);
}

/* floatobject.c's float_rem (a % b) and float.__round__() (half to even; -0.0 comes back as int 0) */
static double ct_py_mod(double vx, double wx) {
    double mod = fmod(vx, wx);
    if (mod) { if ((wx < 0) != (mod < 0)) mod += wx; }
    else mod = copysign(0.0, wx);
    return mod;
}
static double ct_py_round(double x) {
    double r = round(x);
    if (fabs(x - r) == 0.5) r = 2.0 * round(x / 2.0);
    return r == 0.0 ? 0.0 : r;
}

/* builtins.sum of floats from int 0 (CPython 3.12+: Neumaier's compensation) */
static double ct_py_sum(const double *v, int n) {
    double f = 0.0 + v[0], c = 0.0;
    for (int i = 1; i < n; i++) {
        double x = v[i], t = f + x;
        if (fabs(f) >= fabs(x)) c += (f - t) + x;
        else c += (x - t) + f;
        f = t;
    }
    if (c && isfinite(c)) f += c;
    return f;
}

/* -- inputs.py ------------------------------------------------------------------------------------------------- */
static double ct_wrap(double a) { return ct_py_mod(a + CT_PI, 2 * CT_PI) - CT_PI; }

static double ct_heading_to(const double *p, const double *q) { return ct_py_atan2(-(q[0] - p[0]), q[1] - p[1]); }

static double ct_camera(double cam, int has, double heading, const CtConsts *K) {
    if (!has) return cam;
    double d = ct_wrap(heading - cam), lo = -K->cam_rate, hi = K->cam_rate;
    double mn = d < hi ? d : hi;          /* min(CAM_RATE, d) */
    return cam + (mn > lo ? mn : lo);     /* max(-CAM_RATE, ...) */
}

static double ct_gate_max(double cx, double cy, const CtConsts *K) {
    double a[2], sq[2];
    int k = 0;
    if (fabs(cx) > 1e-9) a[k++] = fabs(cx) / K->raw_scale;
    if (fabs(cy) > 1e-9) a[k++] = fabs(cy) / K->raw_scale;
    if (!k) return 0.0;
    for (int i = 0; i < k; i++) sq[i] = a[i] * a[i];
    double s1 = ct_py_sum(a, k), s2 = ct_py_sum(sq, k);
    double disc = CT_POW(K->dead_raw * s1, 2.0) - s2 * (k * CT_POW(K->dead_raw, 2.0) - CT_POW(K->gate_raw, 2.0));
    double v = (sqrt(0.0 > disc ? 0.0 : disc) - K->dead_raw * s1) / s2;
    return v < 1.0 ? v : 1.0;             /* min(1.0, v) */
}

/* the stick toward ``heading`` under ``cam`` at full tilt (magnitude 1); -1 where Python's round() raises */
static int ct_stick(int has, double heading, double cam, const CtConsts *K, double *sx, double *sy) {
    if (!has) { *sx = 0.0; *sy = 0.0; return 0; }
    double d = ct_wrap(heading - cam) * CT_RAD2DEG;
    if (!isfinite(d)) return -1;
    double q = ct_py_round(d / 90.0) * 90.0;
    double a = (fabs(d - q) <= K->snap_deg ? q : d) * CT_DEG2RAD;
    double cx = -CT_SIN(a), cy = CT_COS(a);
    cx = fabs(cx) < 1e-9 ? 0.0 : cx;
    cy = fabs(cy) < 1e-9 ? 0.0 : cy;
    double g = ct_gate_max(cx, cy, K), m = g < 1.0 ? g : 1.0;   /* min(max(1.0, 0.0), gate) */
    *sx = cx * m;
    *sy = cy * m;
    return 0;
}

/* -- macros.py ------------------------------------------------------------------------------------------------- */
static inline int ct_in2(int s, const int *set) { return s == set[0] || s == set[1]; }

static int ct_settled(const Player *p, const CtConsts *K) {   /* obs.settled */
    if (ct_in2(p->state, K->settled)) return 1;
    return p->state == K->slide && p->normal[2] >= K->flat_nz && ct_hyp2(p->vel[0], p->vel[1]) < K->rest_mps;
}

static int ct_flap_due(const Player *p, const CtConsts *K) {
    if (p->vel[2] > 0.0) return 0;
    double peak = p->peak_z;
    if (!isfinite(peak) || peak < -1e30) return 1;
    double d = peak + K->h_air - p->pos[2];
    if (d <= K->flap_margin) return 0;
    if (d >= K->descent_d - K->flap_margin) return 1;
    double v0f = sqrt(2 * K->gravity * (K->h_air < d ? K->h_air : d));
    return p->vel[2] - K->gravity / K->fps < v0f - K->flap_mult * v0f;
}

static int ct_roll_buttons(const CtMac *m, int k, int took, const CtConsts *K) {
    int i = k / K->roll_period, r = k % K->roll_period;
    if (k < K->roll_tap || (i < m->rolls - 1 && K->chain0 - 1 <= r && r <= K->chain1 - 1)) return CB_BLACK;
    int last = (m->rolls - 1) * K->roll_period;
    if (took < 0 && last + K->roll_y - 1 <= k && k < last + K->roll_ticks + K->jump_hold) return CB_Y;
    return 0;
}

/* -- aim.py ---------------------------------------------------------------------------------------------------- */
static double ct_x_after(double m, double v0, double ac, const CtConsts *K) {   /* physics.Physics.x_after */
    if (m <= 0) return 0.0;
    double r = K->blend;
    return K->dt * (m * ac + (v0 - ac) * r * (1 - CT_POW(r, m)) / (1 - r));
}

/* aim.landing: 1 with ``*out``, 0 None, -1 where Python's math.ceil raises */
static int ct_landing(const double *feet, const double *vel, const double *target, int toward, double ac,
                   const CtConsts *K, double *out) {
    double dx = target[0] - feet[0], dy = target[1] - feet[1];
    double d = ct_hyp2(dx, dy);
    if (d < 1e-6) { *out = 0.0; return 1; }
    double ux = dx / d, uy = dy / d;
    double a = -K->dt * K->gdt / 2, b = K->dt * (vel[2] - K->gdt / 2), c = feet[2] - target[2];
    double disc = b * b - 4 * a * c;
    if (disc < 0) return 0;
    double x = (-b - sqrt(disc)) / (2 * a);
    if (!isfinite(x)) return -1;
    double m = ceil(x);
    if (m < 1) return 0;
    double t = ac * toward;
    *out = ct_x_after(m, vel[0] * ux + vel[1] * uy, t, K) - d;
    return 1;
}

/* Aim.steer and Sched.steer: the stick's heading (``*has`` 0: at rest), whether the camera follows it, whether a flap
 * may go; -1 where Python raises */
static int ct_steer(CtRun *r, int t, const Player *prev, const CtFam *F, const CtConsts *K, int *has, double *h,
                    int *follow, int *shortf) {
    const CtMac *m = r->m;
    *has = 1; *h = F->heading; *follow = 1; *shortf = 1;
    if (F->ctl == CC_RUN) { *has = r->first < 0; return 0; }
    if (r->first >= 0) {                             /* Aim._landed */
        *has = 0;
        if (F->has_home) {
            int k = t - r->first;
            double f[2] = {prev->pos[0], prev->pos[1]}, vx = prev->vel[0], vy = prev->vel[1];
            double dx = F->home[0] - f[0], dy = F->home[1] - f[1];
            if (k < K->home_ticks && ct_hyp2(dx, dy) > K->home_m) { *has = 1; *h = ct_heading_to(f, F->home); }
            else if (k < K->brake_ticks && ct_hyp2(vx, vy) > K->brake_v && vx * dx + vy * dy < 0.0) {
                double o[2] = {0.0, 0.0}, q[2] = {-vx, -vy};
                *has = 1; *h = ct_heading_to(o, q);
            }
        }
    } else if (F->has_target && r->took >= 0) {
        double curve = t - r->took < K->turn ? m->curve : 0.0;
        if (m->hold) *h = ct_heading_to(prev->pos, F->target) + curve;
        else {                                       /* aim._steer */
            double f[3] = {prev->pos[0], prev->pos[1], prev->pos[2] - 1.0}, got[3];
            int S[3] = {1, 0, -1}, ok[3], s = 1, found = 0;
            double best = 0.0;
            for (int i = 0; i < 3; i++)
                if ((ok[i] = ct_landing(f, prev->vel, F->target, S[i], m->ac, K, &got[i])) < 0) return -1;
            for (int i = 0; i < 3; i++)
                if (ok[i] && (!found || fabs(got[i]) < best)) { found = 1; best = fabs(got[i]); s = S[i]; }
            double to = ct_heading_to(f, F->target);
            if (s == 1) *h = to + curve;
            else if (s == 0) *has = 0;
            else *h = to + CT_PI;
            *follow = s == 1;
            *shortf = !ok[0] || got[0] < -K->short_m;
        }
    }
    if (F->ctl == CC_SCHED) *shortf = 0;
    return 0;
}

/* _Run.pad (and Sched.pad): the next tick's pad from the rows so far (``prev`` the last, NULL none) */
static int ct_run_pad(CtRun *r, const Player *prev, const CtFam *F, const CtConsts *K, CtCPad *out) {
    const CtMac *m = r->m;
    int t = r->n, buttons = 0, has, follow, shortf;
    double h;
    if (ct_steer(r, t, prev, F, K, &has, &h, &follow, &shortf) < 0) return -1;
    if (r->jump_at < 0 && r->took < 0 && prev && (m->kind == CK_RUNJUMP || m->kind == CK_ROLLJUMP)) {
        if ((prev->pos[0] - F->start[0]) * r->dx + (prev->pos[1] - F->start[1]) * r->dy >= F->back - m->lead)
            r->jump_at = t;
    }
    if (m->kind == CK_ROLLJUMP) {
        if (r->jump_at >= 0) buttons = ct_roll_buttons(m, t - r->jump_at, r->took, K);
    } else if (r->jump_at >= 0 && t - r->jump_at < K->jump_hold) buttons = CB_Y;
    if (r->took >= 0 && r->first < 0 && !buttons && t - r->cast_at > K->cast_wait) {
        int flaps = prev->flaps_used;
        if (m->recast && prev->gauge <= 1e-6 && flaps < m->flaps && r->recasts < m->flaps && !(r->lastb & CB_Y)) {
            buttons = CB_LT | CB_Y; r->cast_at = t; r->recasts++;
        } else if (r->presses < m->flaps + 2 + r->recasts && flaps < m->flaps && shortf && !(r->lastb & CB_Y)
                   && ct_flap_due(prev, K)) {
            buttons = CB_Y; r->presses++;
        }
    }
    r->cam = ct_camera(r->cam, has && follow, h, K);
    if (ct_stick(has, h, r->cam, K, &out->sx, &out->sy) < 0) return -1;
    out->yaw = r->cam;
    out->b = buttons;
    if (F->ctl == CC_SCHED && r->pend < F->nsched && r->took >= 0 && r->first < 0 && !buttons
            && r->presses < m->flaps + 2 && prev->flaps_used < m->flaps && !(r->lastb & CB_Y)
            && (double)(t - r->took) >= F->sched[r->pend]) {
        r->pend++;
        r->presses++;
        out->b = CB_Y;
    }
    return 0;
}

/* _Run.seen (Aim.seen's still first): the row a pad made; the launch's end, or 0 */
static int ct_run_seen(CtRun *r, const CtCPad *pad, float cx, float cy, const Player *row, const CtFam *F,
                       const CtConsts *K) {
    const CtMac *m = r->m;
    if (F->ctl != CC_RUN && r->first >= 0 && (pad->sx != 0.0 || pad->sy != 0.0)) r->still = -1;
    int t = r->n;
    r->pads[t] = *pad;
    r->cam32[2 * t] = cx; r->cam32[2 * t + 1] = cy;
    for (int i = 0; i < 3; i++) r->pos[3 * t + i] = row->pos[i];
    r->state[t] = row->state;
    r->n++;
    r->lastb = pad->b;
    if (row->flaps_used > r->flaps) r->flaps = row->flaps_used;
    int airborne = ct_in2(row->state, K->airborne);
    if (airborne && r->air_i < 0) r->air_i = t;
    if (ct_in2(row->state, K->dead) || F->hp <= 0) return CE_DEAD;
    if (airborne) {
        if (r->took < 0 && r->jump_at < 0 && (m->kind == CK_RUNJUMP || m->kind == CK_ROLLJUMP)) return CE_WALKED;
        r->air++;
        if (r->took < 0) r->took = t;
        r->rest = c_hypot(3, row->vel) < 0.05 ? r->rest + 1 : 0;
        if (r->air > K->air_cap || r->rest >= K->stuck) return r->air > K->air_cap ? CE_AIRCAP : CE_STUCK;
    } else if (r->took >= 0 && r->first < 0) {
        r->first = t;
        r->first_state = row->state;
        for (int i = 0; i < 3; i++) r->firstp[i] = row->pos[i];
    }
    int rolling = m->kind == CK_ROLLJUMP && r->jump_at >= 0 ? K->roll_period * m->rolls + K->roll_ticks : 0;
    if (r->took < 0 && t >= K->run_cap + (r->jump_at >= 0 ? K->jump_hold : 0) + rolling) return CE_STAYED;
    if (r->first >= 0) {
        int still = ct_settled(row, K);
        r->still = still ? r->still + 1 : 0;
        if (r->settle < 0 && r->still >= K->still) { r->settle = t; r->settle_state = row->state; }
        if (r->settle >= 0 && (r->settle_state != K->swimming || t - r->settle >= K->swim_hold))
            return still ? CE_SETTLED : CE_UNSETTLED;
        if (r->settle < 0 && t - r->first >= K->settle) return CE_UNSETTLED;
    }
    return 0;
}

/* KernelSim._step: the pad as the kernel's (the camera the f32 pair l3.camera_dir packs), one tick; its code */
static int ct_kstep(World *w, Player *p, const CtCPad *pad, float *cx, float *cy) {
    Pad q;
    double out[10];
    *cx = (float)(-CT_SIN(pad->yaw));
    *cy = (float)CT_COS(pad->yaw);
    q.sx = (float)pad->sx; q.sy = (float)pad->sy; q.cx = *cx; q.cy = *cy; q.buttons = pad->b;
    p_run(w, p, 1, &q, out);
    return (int)out[9];
}

static inline int ct_pad_eq(const CtCPad *a, const CtCPad *b) {
    return a->sx == b->sx && a->sy == b->sy && a->b == b->b && a->yaw == b->yaw;
}

typedef struct { Player st; int has_st, ng, has_pad; int g[CT_MAXL]; CtCPad pad; } CtTodo;

/* macros.launches of ``F->n`` launches (``ms``) from Player ``p`` (left at the last group's end, as Python leaves the
 * simulator); ``out[i]`` each one's answer, its segments in ``segs`` (room for n x ticks); ``*ticks`` the kernel steps
 * run.  0, or -1 where Python raises (``p`` then undefined: the caller resets it) or the family is too large. */
int p_launches(World *w, Player *p, const CtConsts *K, const CtFam *F, const CtMac *ms, CtLOut *out, CtSeg *segs,
               int64_t *ticks) {
    int n = F->n, T = K->ticks, ends[CT_MAXL], codes[CT_MAXL], err = 0;
    if (n < 1 || n > CT_MAXL || T < 1) return -1;
    CtRun *R = calloc(n, sizeof(CtRun));
    char *mem = malloc((size_t)n * T * (sizeof(CtCPad) + 2 * sizeof(float) + 3 * sizeof(double) + sizeof(int)));
    CtTodo *todo = malloc(sizeof(CtTodo) * (CT_MAXL + 1));
    if (!R || !mem || !todo) { free(R); free(mem); free(todo); return -1; }
    char *at = mem;
    for (int i = 0; i < n; i++) {
        CtRun *r = R + i;
        r->m = ms + i;
        r->cam = F->cam;
        r->dx = -CT_SIN(F->heading); r->dy = CT_COS(F->heading);
        r->jump_at = ms[i].kind == CK_STANDJUMP ? 0 : -1;
        r->took = r->first = r->settle = r->air_i = -1;
        r->cast_at = -99;
        r->pads = (CtCPad *)at; at += sizeof(CtCPad) * T;
        r->pos = (double *)at; at += sizeof(double) * 3 * T;
        r->cam32 = (float *)at; at += sizeof(float) * 2 * T;
        r->state = (int *)at; at += sizeof(int) * T;
        ends[i] = CE_TICKS; codes[i] = 0;
    }
    *ticks = 0;
    int nt = 1;
    todo[0].has_st = 0; todo[0].has_pad = 0; todo[0].ng = n;
    for (int i = 0; i < n; i++) todo[0].g[i] = i;
    while (nt && !err) {
        CtTodo *tp = todo + --nt;
        if (tp->has_st) *p = tp->st;
        int g[CT_MAXL], ng = tp->ng, has_pad = tp->has_pad;
        CtCPad pad = tp->pad;
        memcpy(g, tp->g, sizeof(int) * ng);
        while (ng && R[g[0]].n < T) {
            if (!has_pad) {
                CtCPad pads[CT_MAXL], dp[CT_MAXL];
                int nd = 0, dn[CT_MAXL], dg[CT_MAXL][CT_MAXL];
                for (int j = 0; j < ng; j++)
                    if (ct_run_pad(R + g[j], R[g[j]].n ? p : NULL, F, K, pads + j) < 0) { err = 1; break; }
                if (err) break;
                pad = pads[0];
                for (int j = 0; j < ng; j++) {
                    if (ct_pad_eq(pads + j, &pad)) continue;
                    int k = 0;
                    while (k < nd && !ct_pad_eq(dp + k, pads + j)) k++;
                    if (k == nd) { dp[nd] = pads[j]; dn[nd++] = 0; }
                    dg[k][dn[k]++] = g[j];
                }
                if (nd) {
                    for (int k = 0; k < nd; k++) {
                        CtTodo *e = todo + nt++;
                        e->st = *p; e->has_st = 1; e->has_pad = 1; e->pad = dp[k]; e->ng = dn[k];
                        memcpy(e->g, dg[k], sizeof(int) * dn[k]);
                    }
                    int ng2 = 0;
                    for (int j = 0; j < ng; j++) if (ct_pad_eq(pads + j, &pad)) g[ng2++] = g[j];
                    ng = ng2;
                }
                has_pad = 1;
            }
            float cx, cy;
            int code = ct_kstep(w, p, &pad, &cx, &cy);
            (*ticks)++;
            if (code % 16 || ((code >> 4) & K->tries)) {
                for (int j = 0; j < ng; j++) { ends[g[j]] = CE_FLAG; codes[g[j]] = code; }
                break;
            }
            int ng2 = 0;
            for (int j = 0; j < ng; j++) {
                int e = ct_run_seen(R + g[j], &pad, cx, cy, p, F, K);
                if (e) ends[g[j]] = e;
                else g[ng2++] = g[j];
            }
            ng = ng2;
            has_pad = 0;
        }
        if (err) break;
        for (int j = 0; j < ng; j++)
            if (ends[g[j]] == CE_TICKS && R[g[j]].settle >= 0)
                ends[g[j]] = ct_settled(p, K) ? CE_SETTLED : CE_UNSETTLED;
    }
    int ns = 0;
    for (int i = 0; i < n && !err; i++) {
        CtRun *r = R + i;
        CtLOut *o = out + i;
        memset(o, 0, sizeof(CtLOut));
        o->end = ends[i]; o->code = codes[i]; o->n = r->n; o->first = r->first; o->air = r->air_i;
        o->flaps = r->flaps;
        o->took = -1;
        if (r->first >= 0) { o->first_state = r->first_state; memcpy(o->firstp, r->firstp, sizeof o->firstp); }
        if (r->n) {
            o->last_state = r->state[r->n - 1];
            memcpy(o->last, r->pos + 3 * (r->n - 1), sizeof o->last);
        }
        for (int j = r->air_i - 1; j >= 0; j--)
            if (r->state[j] == 0) {
                o->took = j; o->took_state = 0;
                memcpy(o->tookp, r->pos + 3 * j, sizeof o->tookp);
                break;
            }
        o->seg0 = ns;
        for (int t = 0; t < r->n; t++) {     /* l3_search.segments: a run of pads equal to its first */
            const CtCPad *q = r->pads + t;
            double cx = r->cam32[2 * t], cy = r->cam32[2 * t + 1];
            CtSeg *s = segs + ns - 1;
            if (ns > o->seg0 && s->sx == q->sx && s->sy == q->sy && s->buttons == q->b && s->cx == cx && s->cy == cy)
                s->n++;
            else segs[ns++] = (CtSeg){1, q->b, q->sx, q->sy, cx, cy};
        }
        o->nseg = ns - o->seg0;
    }
    free(R); free(mem); free(todo);
    return err ? -1 : 0;
}
