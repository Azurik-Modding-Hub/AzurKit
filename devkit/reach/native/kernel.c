/* Step R2.17's native movement and collision kernel (prototype): the player's ground and air ticks and the game's
 * move code ported from the USA default.xbe, run against a level's real collision triangles.
 *
 * Ported (VAs: docs/RE_MOVEMENT.md; the step's PROTO-native.txt):
 *   face test 0xB9E60   a sphere swept in a space whose z is scaled by rh/rv (0.5): one-sided faces, no hit unless
 *                       the move ends within r of the plane and moves into its front; a start within r + 0.001 of
 *                       the triangle is a contact at t 0 along (centre - closest point), its depth d; else the
 *                       plane, then the edges and vertices, d 0.  The record's normal is the space's contact normal
 *                       mapped back to world (x, y, z * rh/rv, normalised).
 *   level walk 0xD1B80  the faces in their stored order: each hit becomes the record, its t the next tmax, the
 *                       radius shrinks by its depth (0xD22DA-0xD22EB); collision_sweep keeps the least t.
 *   move 0x47380        up to 6 contacts a move: the remaining time cut by (1 - t), the velocity taken relative to
 *                       the reference w's part along the face, its normal part removed with the restitution table
 *                       {0, 0.25, 0.5, 1, 1, 1}, friction mu |vn| on the tangential part (mu 10, 0.2 slippery, 0
 *                       unless nz > 0.7071), a static stop to a separation of min(2d, 0.001) / dt, a 0.01 push off
 *                       when moving away, the target pushed out by d along the normal (z times rv/rh); the 7th
 *                       contact keeps the body where it is.
 *   walk 0x85F50        w = runSpeed |stick| along the stick's heading under the camera, projected on the stored
 *                       normal's plane at full length; gravity, the move; a 0.1 m ground probe (a miss leaves the
 *                       body at its end); the velocity from the tick's displacement, vz at most 0.
 *   jump 0x89060        Y's edge: h 1.1 (1.2 and air control 12 with an air shield), peak_z = z + h, vz := sqrt(2 g h)
 *                       (along the stored normal on a slope or slippery face), the tick ends there.
 *   flap 0x89300        Y's edge in the air, flaps left, the gauge: the flap law (physics.py), the tick ends there.
 *   airborne 0x89480    the 0.6^dt blend of v_xy toward air control x stick, gravity, the move with w = v.
 *   slope 0x8AE10, 0x89A70   states 3 and 4: a walkable floor within 1 m under the centre takes the body onto it;
 *                       else gravity and the move (w: state 3's stick term; state 4's taken as v, exact unless the
 *                       slope is slippery and walkable: noted ICE).
 *   classifier 0x85920  the contact's world normal: nz <= 0.6 air (a fast slide keeps 0.5 s), 0.6-0.7071 or slippery
 *                       slope, else a 1.3 m ray down from the tick's start confirms the floor; the dead stop (velocity
 *                       zeroed while falling) and the hard landing (0x8B100: a speed change of sqrt(2 g 2.9), then
 *                       its 13-tick clip in place).
 *   step-up 0x8B1D0, lip lift 0x86920   their decisions, and since Step R2.19f+ the lift's clip as FastL3 plays it:
 *                       the body put on the ledge that tick (1.236 m ahead at the ledge's height), still, then state
 *                       0x100 in place for 89 rows (anim 65, a high lip) or 37 (66, a low one), settling as the hard
 *                       landing's clip does, the walk on the next tick.  A step-up stops the run: where the game puts
 *                       the body on the step isn't the decision's point (0.16-0.19 m across, FastL3 on a5 and f2).
 *   volume query 0x60BD0 (Step R2.19e)   at each tick's start the body centre's field volumes (the world's
 *                       :c:func:`w_fields`, each :c:func:`f_add`'s): a platform's test 0x79D30 casts a ray straight up through its mesh and
 *                       holds the point when the first face it meets faces down (0xD2A40), its depth that face's
 *                       height over the point; the words OR'd (0x08 push, 0x100 water), the push vectors (pushX/Y/Z
 *                       turned by the platform's world matrix) summed, the deepest depth kept.
 *   pushes 0x89480      airborne in a push volume: the stick term T x 0.1 plus the push, blended at 0.3^dt (not
 *                       0.6^dt); with pushZ, T_z = 0.1 vz + pushZ and no gravity (updrafts and downdrafts: vz tends
 *                       to pushZ / 0.9, c = 1 - 0.3^dt = 0.039338 x 0.9 = 0.035404 [verified xemu calib §3]).
 *   swimming 0x8B700    in a water volume (and, entering, 0.25 m or more under its surface): v blends at 0.1^dt
 *                       toward the stick's 10 m/s stroke plus the push, vertically toward +-walkSpeed 5 (Y up, BLACK
 *                       down) plus pushZ, capped at pushZ within 0.25 m of the surface; the move with a 1 m sphere and
 *                       w = v, no gravity; out of the water state 6 walks if attached, else flies (0x8D1D8).
 *   springboards 0x89060   a ground tick attached to an autoSpring face (word 0x04) jumps: h := its springboard
 *                       height S (air control 9), or the kit's jump when S is 0; straight up, keeping v_xy.
 * movers (Step R2.19h1)   a world's moving solids: each mover's triangles in its own frame and a pose table (row
 *                       vectors, world = local R + t: the point transform 0xA3E50; one row a tick, recorded in the
 *                       game's whole steps), cycling (the row wraps) or a path (held at its last row), and a present
 *                       mask; a sweep meets each present mover at the clock's row (w_clock; a run's tick sets it to
 *                       the tick's end), and a body standing on one is carried with it from one row to the next
 *                       (the rigid move of its frame) before its tick: the ordering check of R2.19h1's hops, never a
 *                       witness (D845: FastL3's whole steps are).
 * Not ported (the run stops, L3 takes the launch): the step-up, the lip lift out of the water, the catch and the
 * climb (a climbable contact; out of the water too), the roll (BLACK), volumes that move or switch (STOP_PUSH,
 * STOP_WATER: the caller's flagged volumes), other states; a world with no movers is the load pose less the census's
 * absent platforms.
 * Double precision with the game's float32 stores at the state's fields.  Positions never leave the caller. */
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define F(x) ((double)(float)(x))

static const double G = 9.8, DT = 1.0 / 30.0, RH = 0.5, RV = 1.0, SKIN = 0.001, PUSH = 0.01, SEP = 0.001;
static const double REST[6] = {0.0, 0.25, 0.5, 1.0, 1.0, 1.0};
static const double FLOOR_NZ = 0.7071, LAND_NZ = 0.6, PROBE = 0.1, RAY = 1.3, RUN = 7.0;
static double HARD;           /* sqrt(2 g 2.9): 0x38B0C4, the hard landing's speed change */

typedef struct {
    int n;
    double *A, *B, *C;        /* vertices in the sphere space (z * zs), 3 each */
    double *ns, *D, *nw;      /* the space's unit normal and plane, the world unit normal */
    double *lo, *hi;          /* boxes in the space */
    int32_t *word;
    double gx0, gy0, cell;
    int gnx, gny;
    int64_t *cstart;
    int32_t *ctri;
    uint32_t *stamp, mark;
    double zs;                /* the space's z scale for the box (rh / rv) */
    int64_t tests;
    int32_t *cand;            /* a sweep's candidates */
    int ncap;
    /* movers (the header): mover m's triangles mloc[9 mstart[m] ..] in its frame, their words, its bounding
     * sphere (local centre, radius), its pose rows mpose[16 (moff[m] + row)], mT[m] of them, mcyc[m] wrapping */
    int nm;
    int64_t *mstart, *moff, *mT;
    int32_t *mcyc, *mword;
    double *mloc, *mc, *mrad, *mpose;
    uint8_t *present;
    int64_t now;              /* the clock: the pose row the movers are at */
    double *spring;           /* per face, its springboard height (NULL: none) */
    double *mspring;          /* per mover, its springboard height (NULL: none; ``w_mspring`` after ``w_movers``) */
    struct Fields *fields;    /* the field volumes a run on this world queries (``w_fields``; NULL: none) */
} World;

typedef struct {
    double t, d, n[3], p[3];  /* t in [0, 1]; depth; world normal; world contact point */
    int tri, kind;            /* kind 0 plane, 1 vertex, 2 edge, 3 overlap; tri a mover's own index when src >= 0 */
    uint32_t word;
    int src;                  /* -1 the static world, else the mover */
    double s;                 /* the face's springboard height (an autoSpring platform's S; 0 none) */
} Contact;

static inline double dot(const double *a, const double *b) { return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]; }
static inline void sub(double *o, const double *a, const double *b) { o[0] = a[0]-b[0]; o[1] = a[1]-b[1]; o[2] = a[2]-b[2]; }
static inline void cross(double *o, const double *a, const double *b) {
    o[0] = a[1]*b[2] - a[2]*b[1]; o[1] = a[2]*b[0] - a[0]*b[2]; o[2] = a[0]*b[1] - a[1]*b[0];
}

/* ---------------------------------------------------------------------------------------------- the world */
World *w_new(int n, const double *P, const int32_t *word, double cell, double zs) {
    World *w = calloc(1, sizeof(World));
    w->n = n; w->cell = cell; w->zs = zs;
    w->A = malloc(sizeof(double) * 3 * n); w->B = malloc(sizeof(double) * 3 * n); w->C = malloc(sizeof(double) * 3 * n);
    w->ns = malloc(sizeof(double) * 3 * n); w->nw = malloc(sizeof(double) * 3 * n); w->D = malloc(sizeof(double) * n);
    w->lo = malloc(sizeof(double) * 3 * n); w->hi = malloc(sizeof(double) * 3 * n);
    w->word = malloc(sizeof(int32_t) * n); w->stamp = calloc(n ? n : 1, sizeof(uint32_t));
    double gx0 = 1e30, gy0 = 1e30, gx1 = -1e30, gy1 = -1e30;
    for (int i = 0; i < n; i++) {
        const double *p = P + 9 * i;
        double a[3] = {p[0], p[1], p[2]}, b[3] = {p[3], p[4], p[5]}, c[3] = {p[6], p[7], p[8]};
        double e0[3], e1[3], nn[3];
        sub(e0, b, a); sub(e1, c, a); cross(nn, e0, e1);
        double l = sqrt(dot(nn, nn));
        for (int k = 0; k < 3; k++) w->nw[3*i+k] = l > 0 ? nn[k] / l : 0.0;
        a[2] *= zs; b[2] *= zs; c[2] *= zs;
        memcpy(w->A + 3*i, a, sizeof a); memcpy(w->B + 3*i, b, sizeof b); memcpy(w->C + 3*i, c, sizeof c);
        sub(e0, b, a); sub(e1, c, a); cross(nn, e0, e1);
        l = sqrt(dot(nn, nn));
        for (int k = 0; k < 3; k++) w->ns[3*i+k] = l > 0 ? nn[k] / l : 0.0;
        w->D[i] = dot(w->ns + 3*i, a);
        for (int k = 0; k < 3; k++) {
            double lo = fmin(a[k], fmin(b[k], c[k])), hi = fmax(a[k], fmax(b[k], c[k]));
            w->lo[3*i+k] = lo; w->hi[3*i+k] = hi;
        }
        w->word[i] = word[i];
        gx0 = fmin(gx0, w->lo[3*i]); gy0 = fmin(gy0, w->lo[3*i+1]);
        gx1 = fmax(gx1, w->hi[3*i]); gy1 = fmax(gy1, w->hi[3*i+1]);
    }
    if (n == 0) { gx0 = gy0 = 0; gx1 = gy1 = 1; }
    w->gx0 = floor(gx0) - cell; w->gy0 = floor(gy0) - cell;
    w->gnx = (int)((gx1 - w->gx0) / cell) + 2; w->gny = (int)((gy1 - w->gy0) / cell) + 2;
    int64_t cells = (int64_t)w->gnx * w->gny;
    w->cstart = calloc(cells + 1, sizeof(int64_t));
    for (int pass = 0; pass < 2; pass++) {
        int64_t *fill = pass ? calloc(cells, sizeof(int64_t)) : NULL;
        for (int i = 0; i < n; i++) {
            int x0 = (int)floor((w->lo[3*i] - w->gx0) / cell), x1 = (int)floor((w->hi[3*i] - w->gx0) / cell);
            int y0 = (int)floor((w->lo[3*i+1] - w->gy0) / cell), y1 = (int)floor((w->hi[3*i+1] - w->gy0) / cell);
            for (int y = y0; y <= y1; y++) for (int x = x0; x <= x1; x++) {
                int64_t k = (int64_t)y * w->gnx + x;
                if (!pass) w->cstart[k + 1]++;
                else w->ctri[w->cstart[k] + fill[k]++] = i;
            }
        }
        if (!pass) {
            for (int64_t k = 0; k < cells; k++) w->cstart[k + 1] += w->cstart[k];
            w->ctri = malloc(sizeof(int32_t) * (w->cstart[cells] ? w->cstart[cells] : 1));
        } else free(fill);
    }
    return w;
}

static void movers_free(World *w) {
    free(w->mstart); free(w->moff); free(w->mT); free(w->mcyc); free(w->mword); free(w->mloc); free(w->mc);
    free(w->mrad); free(w->mpose); free(w->present); free(w->mspring);
    w->mstart = w->moff = w->mT = NULL; w->mcyc = w->mword = NULL; w->mloc = w->mc = w->mrad = w->mpose = NULL;
    w->present = NULL; w->mspring = NULL; w->nm = 0;
}

void w_free(World *w) {
    if (!w) return;
    free(w->A); free(w->B); free(w->C); free(w->ns); free(w->nw); free(w->D); free(w->lo); free(w->hi);
    free(w->word); free(w->stamp); free(w->cstart); free(w->ctri); free(w->cand); movers_free(w); free(w->spring); free(w);
}

/* the movers (the header), copied: nm of them, mover m's triangles mloc[9 mstart[m] .. 9 mstart[m + 1]) (local),
 * their words, its mT[m] pose rows (16 doubles each, consecutive over the movers) and whether it cycles; all
 * present, the clock at 0 */
void w_movers(World *w, int nm, const int64_t *mstart, const double *mloc, const int32_t *mword, const int64_t *mT,
              const int32_t *mcyc, const double *mpose) {
    movers_free(w);
    w->nm = nm; w->now = 0;
    if (nm <= 0) return;
    int64_t nt = mstart[nm], rows = 0;
    for (int m = 0; m < nm; m++) rows += mT[m];
    w->mstart = malloc(sizeof(int64_t) * (nm + 1)); memcpy(w->mstart, mstart, sizeof(int64_t) * (nm + 1));
    w->mT = malloc(sizeof(int64_t) * nm); memcpy(w->mT, mT, sizeof(int64_t) * nm);
    w->mcyc = malloc(sizeof(int32_t) * nm); memcpy(w->mcyc, mcyc, sizeof(int32_t) * nm);
    w->mloc = malloc(sizeof(double) * 9 * (nt ? nt : 1)); memcpy(w->mloc, mloc, sizeof(double) * 9 * nt);
    w->mword = malloc(sizeof(int32_t) * (nt ? nt : 1)); memcpy(w->mword, mword, sizeof(int32_t) * nt);
    w->mpose = malloc(sizeof(double) * 16 * (rows ? rows : 1)); memcpy(w->mpose, mpose, sizeof(double) * 16 * rows);
    w->moff = malloc(sizeof(int64_t) * nm); w->mc = malloc(sizeof(double) * 3 * nm); w->mrad = malloc(sizeof(double) * nm);
    w->present = malloc(nm);
    for (int m = 0, off = 0; m < nm; off += (int)mT[m], m++) {
        w->moff[m] = off; w->present[m] = 1;
        double lo[3] = {1e30, 1e30, 1e30}, hi[3] = {-1e30, -1e30, -1e30}, r2 = 0.0;
        for (int64_t q = 9 * mstart[m]; q < 9 * mstart[m + 1]; q += 3)
            for (int k = 0; k < 3; k++) { lo[k] = fmin(lo[k], mloc[q + k]); hi[k] = fmax(hi[k], mloc[q + k]); }
        for (int k = 0; k < 3; k++) w->mc[3*m + k] = mstart[m + 1] > mstart[m] ? 0.5 * (lo[k] + hi[k]) : 0.0;
        for (int64_t q = 9 * mstart[m]; q < 9 * mstart[m + 1]; q += 3) {
            double d[3] = {mloc[q] - w->mc[3*m], mloc[q+1] - w->mc[3*m+1], mloc[q+2] - w->mc[3*m+2]};
            r2 = fmax(r2, dot(d, d));
        }
        w->mrad[m] = sqrt(r2);
    }
}

void w_present(World *w, int m, int on) { if (m >= 0 && m < w->nm) w->present[m] = (uint8_t)(on != 0); }
void w_clock(World *w, int64_t now) { w->now = now; }

static inline int64_t pose_row(int64_t t, int64_t T, int cyc) {
    if (T <= 0) return 0;
    if (cyc) { int64_t r = t % T; return r < 0 ? r + T : r; }
    return t < 0 ? 0 : (t >= T ? T - 1 : t);
}

static inline const double *pose(const World *w, int m, int64_t t) {
    return w->mpose + 16 * (w->moff[m] + pose_row(t, w->mT[m], w->mcyc[m]));
}

static inline void xf(const double *M, const double *p, double *o) {   /* local to world through row-vector M */
    o[0] = p[0]*M[0] + p[1]*M[4] + p[2]*M[8] + M[12];
    o[1] = p[0]*M[1] + p[1]*M[5] + p[2]*M[9] + M[13];
    o[2] = p[0]*M[2] + p[1]*M[6] + p[2]*M[10] + M[14];
}

static inline void ixf(const double *M, const double *q, double *o) {  /* world to local (M's rotation orthonormal) */
    double d[3] = {q[0] - M[12], q[1] - M[13], q[2] - M[14]};
    o[0] = d[0]*M[0] + d[1]*M[1] + d[2]*M[2];
    o[1] = d[0]*M[4] + d[1]*M[5] + d[2]*M[6];
    o[2] = d[0]*M[8] + d[1]*M[9] + d[2]*M[10];
}

/* each face's springboard height (an autoSpring platform's S, 0 for none): the contact carries it */
void w_spring(World *w, const double *S) {
    if (!w->spring) w->spring = malloc(sizeof(double) * (w->n ? w->n : 1));
    memcpy(w->spring, S, sizeof(double) * w->n);
}

/* each mover's springboard height (an autoSpring rig's S, 0 for none): a contact with its faces carries it, as a
 * static face's does (jump_init 0x89060 takes the attached face's +0x68 whatever owns the face) */
void w_mspring(World *w, const double *S) {
    if (w->nm <= 0) return;
    if (!w->mspring) w->mspring = malloc(sizeof(double) * w->nm);
    memcpy(w->mspring, S, sizeof(double) * w->nm);
}

int64_t w_tests(World *w) { return w->tests; }

/* the closest point of triangle abc to p (Ericson's) */
static void closest(const double *p, const double *a, const double *b, const double *c, double *q) {
    double ab[3], ac[3], ap[3], bp[3], cp[3];
    sub(ab, b, a); sub(ac, c, a); sub(ap, p, a);
    double d1 = dot(ab, ap), d2 = dot(ac, ap);
    if (d1 <= 0 && d2 <= 0) { memcpy(q, a, 3 * sizeof(double)); return; }
    sub(bp, p, b);
    double d3 = dot(ab, bp), d4 = dot(ac, bp);
    if (d3 >= 0 && d4 <= d3) { memcpy(q, b, 3 * sizeof(double)); return; }
    double vc = d1*d4 - d3*d2;
    if (vc <= 0 && d1 >= 0 && d3 <= 0) { double v = d1 / (d1 - d3); for (int k = 0; k < 3; k++) q[k] = a[k] + v*ab[k]; return; }
    sub(cp, p, c);
    double d5 = dot(ab, cp), d6 = dot(ac, cp);
    if (d6 >= 0 && d5 <= d6) { memcpy(q, c, 3 * sizeof(double)); return; }
    double vb = d5*d2 - d1*d6;
    if (vb <= 0 && d2 >= 0 && d6 <= 0) { double v = d2 / (d2 - d6); for (int k = 0; k < 3; k++) q[k] = a[k] + v*ac[k]; return; }
    double va = d3*d6 - d5*d4;
    if (va <= 0 && (d4 - d3) >= 0 && (d5 - d6) >= 0) {
        double v = (d4 - d3) / ((d4 - d3) + (d5 - d6));
        for (int k = 0; k < 3; k++) q[k] = b[k] + v*(c[k] - b[k]); return;
    }
    double den = 1.0 / (va + vb + vc), v = vb * den, x = vc * den;
    for (int k = 0; k < 3; k++) q[k] = a[k] + ab[k]*v + ac[k]*x;
}

static inline int lowest_root(double a, double b, double c, double tmax, double *t) {
    double det = b*b - 4.0*a*c;
    if (det < 0.0 || a == 0.0) return 0;
    double s = sqrt(det), r1 = (-b - s) / (2.0*a), r2 = (-b + s) / (2.0*a);
    if (r1 > r2) { double x = r1; r1 = r2; r2 = x; }
    if (r1 >= 0.0 && r1 < tmax) { *t = r1; return 1; }
    if (r2 >= 0.0 && r2 < tmax) { *t = r2; return 1; }
    return 0;
}

/* 0xB9E60 on one triangle (A, B, C, its unit normal n and plane D, all in the space): c the start, v the move,
 * r the radius, tmax the walk's best t so far.  1 and the contact's t, depth, space normal and space point when it
 * hits: a start within r + 0.001 of the triangle (closing on its closest point) is a contact at t 0 whatever tmax
 * is, depth r + 0.001 - its distance; else the plane, then the edges and vertices, earlier than tmax, depth 0. */
static int face(const double *A, const double *B, const double *C, const double *n, double D,
                const double *c, const double *v, double r, double tmax,
                double *t, double *d, double *ns, double *q, int *kind) {
    double s0 = dot(n, c) - D, nv = dot(n, v);
    if (!(s0 + nv < r)) return 0;
    if (!(nv < 0.0)) return 0;
    const double *V[3] = {A, B, C};
    if (r == 0.0) {                                          /* a ray */
        double tt = -s0 / nv, p[3], e[3], x[3], pa[3];
        if (tt < 0.0 || !(tt < tmax)) return 0;
        for (int k = 0; k < 3; k++) p[k] = c[k] + tt*v[k];
        for (int k = 0; k < 3; k++) {
            sub(e, V[(k+1)%3], V[k]); sub(pa, p, V[k]); cross(x, e, pa);
            if (dot(x, n) < 0.0) return 0;
        }
        *t = tt; *d = 0.0; memcpy(ns, n, 3 * sizeof(double)); memcpy(q, p, 3 * sizeof(double)); *kind = 0;
        return 1;
    }
    double rp = r + SKIN;
    if (s0 < rp) {                                           /* the start within r + 0.001: a contact now */
        double Q[3], cq[3];
        closest(c, A, B, C, Q);
        sub(cq, c, Q);
        double d2 = dot(cq, cq);
        if (d2 < rp*rp) {
            if (dot(cq, v) > 0.0) return 0;
            double dist = sqrt(d2);
            if (dist > 0.0) for (int k = 0; k < 3; k++) ns[k] = cq[k] / dist;
            else memcpy(ns, n, 3 * sizeof(double));
            *t = 0.0; *d = rp - dist > 0.0 ? rp - dist : 0.0; memcpy(q, Q, 3 * sizeof(double)); *kind = 3;
            return 1;
        }
    }
    double t0 = (r - s0) / nv;                               /* the plane: the sphere's nearest point */
    if (t0 >= 0.0 && t0 < tmax) {
        double p[3], e[3], x[3], pa[3];
        int in = 1;
        for (int k = 0; k < 3; k++) p[k] = c[k] + t0*v[k] - r*n[k];
        for (int k = 0; k < 3 && in; k++) {
            sub(e, V[(k+1)%3], V[k]); sub(pa, p, V[k]); cross(x, e, pa);
            if (dot(x, n) < 0.0) in = 0;
        }
        if (in) { *t = t0; *d = 0.0; memcpy(ns, n, 3 * sizeof(double)); memcpy(q, p, 3 * sizeof(double)); *kind = 0; return 1; }
    }
    double best = tmax, tt, vv = dot(v, v), bq[3] = {0, 0, 0};   /* the vertices and edges */
    int hit = 0, bk = 0;
    for (int k = 0; k < 3; k++) {
        double cq[3];
        sub(cq, c, V[k]);
        if (lowest_root(vv, 2.0*dot(v, cq), dot(cq, cq) - r*r, best, &tt)) { best = tt; hit = 1; bk = 1; memcpy(bq, V[k], sizeof bq); }
    }
    for (int k = 0; k < 3; k++) {
        const double *p1 = V[k], *p2 = V[(k+1)%3];
        double e[3], bv[3];
        sub(e, p2, p1); sub(bv, p1, c);
        double ee = dot(e, e), ev = dot(e, v), eb = dot(e, bv);
        double a = ee*(-vv) + ev*ev, b = ee*(2.0*dot(v, bv)) - 2.0*ev*eb, cc = ee*(r*r - dot(bv, bv)) + eb*eb;
        if (lowest_root(-a, -b, -cc, best, &tt)) {
            double f = (ev*tt - eb) / ee;
            if (f >= 0.0 && f <= 1.0) { best = tt; hit = 1; bk = 2; for (int m = 0; m < 3; m++) bq[m] = p1[m] + f*e[m]; }
        }
    }
    if (!hit) return 0;
    *t = best; *d = 0.0; *kind = bk;
    for (int k = 0; k < 3; k++) ns[k] = (c[k] + best*v[k] - bq[k]) / r;
    memcpy(q, bq, sizeof bq);
    return 1;
}

static int cmp_i32(const void *a, const void *b) { int x = *(const int32_t *)a, y = *(const int32_t *)b; return (x > y) - (x < y); }

/* collision_sweep 0x60870 and the level's walk 0xD1B80: the body (rh, rv; rh 0 a ray) from world c0 to world c1.
 * The triangles the box meets are tested in their stored order (the tern's chunks and faces, approximately the
 * walk's); each hit becomes the record (so of contacts at t 0 the last one tested is kept), the best t the next
 * test's tmax and the radius shrinks by its depth (0xD22DA-0xD22EB). */
int w_sweep(World *w, const double *c0, const double *c1, double rh, double rv, Contact *out) {
    double zs = rh > 0.0 ? rh / rv : 1.0, r = rh;
    double c[3] = {c0[0], c0[1], c0[2] * zs}, e[3] = {c1[0], c1[1], c1[2] * zs}, v[3];
    sub(v, e, c);
    double m = r + SKIN, bl[3], bh[3];
    for (int k = 0; k < 3; k++) { bl[k] = fmin(c[k], e[k]) - m; bh[k] = fmax(c[k], e[k]) + m; }
    double wz = w->zs;                                       /* the boxes are in the build's space */
    double blz = bl[2] / zs * wz, bhz = bh[2] / zs * wz;
    int x0 = (int)floor((bl[0] - w->gx0) / w->cell), x1 = (int)floor((bh[0] - w->gx0) / w->cell);
    int y0 = (int)floor((bl[1] - w->gy0) / w->cell), y1 = (int)floor((bh[1] - w->gy0) / w->cell);
    if (x0 < 0) x0 = 0; if (y0 < 0) y0 = 0;
    if (x1 >= w->gnx) x1 = w->gnx - 1; if (y1 >= w->gny) y1 = w->gny - 1;
    if (++w->mark == 0) { memset(w->stamp, 0, sizeof(uint32_t) * (w->n ? w->n : 1)); w->mark = 1; }
    int nc = 0;
    for (int y = y0; y <= y1; y++) for (int x = x0; x <= x1; x++) {
        int64_t k = (int64_t)y * w->gnx + x;
        for (int64_t q = w->cstart[k]; q < w->cstart[k+1]; q++) {
            int i = w->ctri[q];
            if (w->stamp[i] == w->mark) continue;
            w->stamp[i] = w->mark;
            const double *lo = w->lo + 3*i, *hi = w->hi + 3*i;
            if (lo[0] > bh[0] || hi[0] < bl[0] || lo[1] > bh[1] || hi[1] < bl[1] || lo[2] > bhz || hi[2] < blz) continue;
            if (nc == w->ncap) { w->ncap = w->ncap ? 2 * w->ncap : 256; w->cand = realloc(w->cand, sizeof(int32_t) * w->ncap); }
            w->cand[nc++] = i;
        }
    }
    if (nc > 48) qsort(w->cand, nc, sizeof(int32_t), cmp_i32);
    else for (int a = 1; a < nc; a++) {                      /* the usual few: an insertion sort */
        int32_t x = w->cand[a]; int b = a - 1;
        while (b >= 0 && w->cand[b] > x) { w->cand[b + 1] = w->cand[b]; b--; }
        w->cand[b + 1] = x;
    }
    double best = 1.0, bd = 0, bn[3] = {0, 0, 1}, bp[3] = {0, 0, 0};
    int bt = -1, bk = 0;
    for (int j = 0; j < nc; j++) {
        int i = w->cand[j];
        w->tests++;
        double t, d, ns[3], p[3];
        int kind;
        if (zs == wz) {
            if (!face(w->A + 3*i, w->B + 3*i, w->C + 3*i, w->ns + 3*i, w->D[i], c, v, r, best, &t, &d, ns, p, &kind))
                continue;
        } else {                                             /* a ray (zs 1): the triangle in world space */
            double A[3], B[3], C[3];
            for (int k2 = 0; k2 < 3; k2++) { A[k2] = w->A[3*i+k2]; B[k2] = w->B[3*i+k2]; C[k2] = w->C[3*i+k2]; }
            A[2] /= wz; B[2] /= wz; C[2] /= wz;
            const double *nwi = w->nw + 3*i;
            if (!face(A, B, C, nwi, dot(nwi, A), c, v, r, best, &t, &d, ns, p, &kind)) continue;
        }
        best = t; bt = i; bd = d; bk = kind; r -= d;
        memcpy(bn, ns, sizeof bn); memcpy(bp, p, sizeof bp);
    }
    int bsrc = -1;
    uint32_t bword = bt >= 0 ? (uint32_t)w->word[bt] : 0;
    for (int m = 0; m < w->nm; m++) {                        /* the movers, posed at the clock's row */
        if (!w->present[m] || w->mstart[m + 1] == w->mstart[m]) continue;
        const double *M = pose(w, m, w->now);
        double cw[3], c0w[3] = {c0[0], c0[1], c0[2]}, c1w[3] = {c1[0], c1[1], c1[2]};
        xf(M, w->mc + 3*m, cw);
        double reach = w->mrad[m] + rv + 0.01, out_ = 0.0;
        for (int k = 0; k < 3; k++) {
            double lo = fmin(c0w[k], c1w[k]) - reach, hi = fmax(c0w[k], c1w[k]) + reach;
            if (cw[k] < lo) out_ = fmax(out_, lo - cw[k]); else if (cw[k] > hi) out_ = fmax(out_, cw[k] - hi);
        }
        if (out_ > 0.0) continue;
        for (int64_t q = w->mstart[m]; q < w->mstart[m + 1]; q++) {
            double P[3][3], e0[3], e1[3], nn[3];
            for (int k = 0; k < 3; k++) { xf(M, w->mloc + 9*q + 3*k, P[k]); P[k][2] *= zs; }
            sub(e0, P[1], P[0]); sub(e1, P[2], P[0]); cross(nn, e0, e1);
            double l = sqrt(dot(nn, nn));
            if (!(l > 1e-12)) continue;
            for (int k = 0; k < 3; k++) nn[k] /= l;
            w->tests++;
            double t, d, ns[3], p[3];
            int kind;
            if (!face(P[0], P[1], P[2], nn, dot(nn, P[0]), c, v, r, best, &t, &d, ns, p, &kind)) continue;
            best = t; bt = (int)(q - w->mstart[m]); bd = d; bk = kind; r -= d; bsrc = m; bword = (uint32_t)w->mword[q];
            memcpy(bn, ns, sizeof bn); memcpy(bp, p, sizeof bp);
        }
    }
    if (bt < 0) return 0;
    out->t = best; out->d = bd; out->tri = bt; out->kind = bk; out->word = bword; out->src = bsrc;
    out->s = bsrc < 0 ? (w->spring ? w->spring[bt] : 0.0) : (w->mspring ? w->mspring[bsrc] : 0.0);
    double nw[3] = {bn[0], bn[1], bn[2] * zs}, l = sqrt(dot(nw, nw));   /* the space's normal to world */
    for (int k = 0; k < 3; k++) out->n[k] = l > 0 ? nw[k] / l : 0.0;
    out->p[0] = bp[0]; out->p[1] = bp[1]; out->p[2] = bp[2] / zs;
    return 1;
}

/* ------------------------------------------------------------------------------------------------ the move */
typedef struct {
    double pos[3], vel[3], w[3], dt;
    int f35;                  /* friction on any contact (ent+0x16c bit 2) */
    /* out */
    double out[3], vout[3];
    int contact, contacts, fallback;
    Contact first, A, B, Cc;  /* the first contact and the three slots (most upward, most level, most downward) */
    double rh, rv;            /* the body's radii (0: the player's 0.5 / 1.0; swimming's 1 m sphere, 0x8B9A9) */
} Move;

void w_move(World *w, Move *m) {
    const double rh = m->rh > 0.0 ? m->rh : RH, rv = m->rv > 0.0 ? m->rv : RV, ratio = rv / rh;
    double vel[3] = {F(m->vel[0]), F(m->vel[1]), F(m->vel[2])}, wv[3] = {m->w[0], m->w[1], m->w[2]};
    double pos[3] = {F(m->pos[0]), F(m->pos[1]), F(m->pos[2])}, rem = m->dt, tgt[3];
    for (int k = 0; k < 3; k++) tgt[k] = F(pos[k] + F(vel[k] * m->dt));
    int flag17 = 0, ri = 0;
    m->contact = 0; m->contacts = 0; m->fallback = 0;
    for (;;) {
        Contact c;
        if (!w_sweep(w, pos, tgt, rh, rv, &c)) break;
        rem = F((1.0 - c.t) * rem);
        if (!m->contact) { m->first = c; m->A = c; m->B = c; m->Cc = c; }
        else if (!flag17) { m->A = c; m->B = c; m->Cc = c; }
        else {
            if (c.n[2] > m->A.n[2]) m->A = c;
            if (fabs(c.n[2]) < fabs(m->B.n[2])) m->B = c;
            if (c.n[2] < m->Cc.n[2]) m->Cc = c;
        }
        m->contact = 1; m->contacts++;
        for (int k = 0; k < 3; k++) pos[k] = F(pos[k] + (tgt[k] - pos[k]) * c.t);
        if (++ri == 7) { m->fallback = 1; break; }
        const double *n = c.n;
        double nn = dot(n, n), kw = dot(n, wv) / nn, ref[3];
        for (int k = 0; k < 3; k++) { ref[k] = F(wv[k] - n[k]*kw); vel[k] = F(vel[k] - ref[k]); }
        double k2 = dot(vel, n) / nn, vn[3], vt[3], push[3] = {0, 0, 0};
        for (int k = 0; k < 3; k++) { vn[k] = F(n[k]*k2); vt[k] = F(vel[k] - vn[k]); }
        if (dot(vel, n) > 0.0) for (int k = 0; k < 3; k++) push[k] = F(n[k] * PUSH);
        double mu = 0.0;
        if (n[2] > FLOOR_NZ || m->f35) mu = (c.word & 1) ? 0.2 : 10.0;
        double fr = mu * sqrt(dot(vn, vn)), lt = sqrt(dot(vt, vt));
        double sep = fmin(2.0 * c.d, SEP);
        if (sep != sep) sep = SEP;
        sep /= m->dt;
        if (fr >= lt) {
            for (int k = 0; k < 3; k++) vel[k] = F(n[k] * sep);
        } else {
            double f = 1.0 - fr / lt;
            for (int k = 0; k < 3; k++) vel[k] = F(F(vt[k]*f) - F(vn[k]*REST[ri-1]));
            for (int k = 0; k < 3; k++) vel[k] = F(vel[k] + n[k]*sep);
        }
        for (int k = 0; k < 3; k++) vel[k] = F(F(vel[k] + push[k]) + ref[k]);
        double off[3] = {n[0]*c.d, n[1]*c.d, n[2]*c.d*ratio};
        for (int k = 0; k < 3; k++) tgt[k] = F(F(pos[k] + F(vel[k]*rem)) + off[k]);
        if (!flag17) flag17 = 1;                             /* the static level's hit object has bit 21 (dl) */
    }
    if (m->fallback) {                                       /* 0x47EFF: the 7th contact: the surface's velocity (0) */
        for (int k = 0; k < 3; k++) { tgt[k] = pos[k]; vel[k] = 0.0; }
    }
    for (int k = 0; k < 3; k++) { m->out[k] = tgt[k]; m->vout[k] = vel[k]; }
}

/* ---------------------------------------------------------------------------------------------- the player */
enum { S_WALK = 0, S_AIR = 2, S_SLOPE = 3, S_SLIDE = 4, S_SWIM = 6, S_HARD = 0x100 };
static const int CLIP_HARD = 13;   /* the hard landing's clip (anim 11): 13 rows of 0x100, its landing tick and 12 in
                                    * place [measured L3, FastL3] */
/* the clips a lip lift (anims 65 high, 66 low) plays in place in state 0x100 after the body is put on its ledge, in
 * rows of that state [measured FastL3, e7: Step R2.19f+'s clip probe; a step-up's anim 53 plays 5, not ported] */
static const int CLIP_LIP_HIGH = 89, CLIP_LIP_LOW = 37;
/* why a run stops: a state, a volume or a root-motion move the kernel doesn't port (L3 takes the launch on) */
enum { STOP_NONE = 0, STOP_STATE = 1, STOP_WATER = 2, STOP_PUSH = 3, STOP_STEPUP = 4, STOP_LIP = 5, STOP_CATCH = 6,
       STOP_CLIMB = 7, STOP_ROLL = 8 };
enum { ZERO_V = 8, TRY_ICE = 16 };   /* notes: the classifier's dead stop (ported); a fast slide's friction (approx.) */
/* the volume laws' constants (0x89480, 0x8B700; Step R2.19e): pinned by tests/test_reach_engine.py */
static const double PUSH_T = 0.1, PUSH_BASE = 0.3, AIR_BASE = 0.6, SWIM_BASE = 0.1, STROKE = 10.0, SWIM_V = 5.0,
                    SURFACE = 0.25, SWIM_R = 1.0, RAY_UP = 10000.0, NO_DEPTH = -50.0, SPRING_AC = 9.0;
enum { W_SLIP = 0x01, W_SPRING = 0x04, W_PUSH = 0x08, W_WATER = 0x100 };

typedef struct {
    double pos[3], vel[3], normal[3];
    double peak_z, gauge, ac, h, fall_ref;
    int state, flaps_used, flaps_max, shield, latch_y, prev_y, attached, f35;
    uint32_t word;
    int stop;                 /* why the run stopped (a state not ported), 0 none */
    int tries;                /* this tick's TRY_ flags: a law the game would try here, not ported */
    int contacts;             /* the last move's contacts */
    int clip;                 /* rows left of a clip (the hard landing's or a lift's) */
    double d4;                /* ent+0xD4: time a fast slide (state 4) has been off its slope */
    double state_t;           /* ent+0x9C: time in the state (the update's end adds dt, a new state resets it) */
    int on;                   /* the mover the body last stood on (a floor contact), -1 none */
    int64_t tick;             /* the movers' clock at the tick's start (p_run steps it) */
    double spring;            /* ent+0x68: the attached face's springboard height */
    uint32_t fields;          /* this tick's volume words (input+0x134) */
    double push[3], depth;    /* this tick's push (input+0x140) and depth under a surface (input+0x14C) */
} Player;

typedef struct { float sx, sy, cx, cy; int32_t buttons; } Pad;   /* buttons: 1 y, 2 lt, 4 black */

static void reinit(Player *p) {
    if (p->shield) { p->ac = 12.0; p->h = F(1.2); }
    else { p->ac = 9.0; p->h = F(1.1); }
}

/* consume_fuel 0x842D0 (physics.py's _consume): e / Flaps off the gauge; empty (2) when under half a step is left */
static int consume(Player *p, double e) {
    double step = e / (p->flaps_max > 0 ? p->flaps_max : 1), left = F(p->gauge - step);
    if (left < step / 2) { p->gauge = 0.0; return 2; }
    p->gauge = left;
    return 1;
}

/* the step-up 0x8B1D0's decision (its clip, anim 53, isn't ported): ``P`` the tick's start centre, ``B`` the move's
 * most level contact, ``dir`` the stick's direction.  1 when the game would step up. */
static int stepup_ok(World *w, const double *P, const Contact *B, const double *dir, double mag) {
    if (!(mag > 0.0)) return 0;
    double h = F(F(B->p[2] + 0.05) + 1.0);
    if (h > F(P[2] + 0.6)) return 0;
    double S[3] = {P[0], P[1], h}, E[3] = {F(S[0] + 1.1 * dir[0]), F(S[1] + 1.1 * dir[1]), h}, Q[3];
    Contact c;
    if (w_sweep(w, S, E, RH, RV, &c)) {
        for (int k = 0; k < 3; k++) Q[k] = F(S[k] + (E[k] - S[k]) * c.t - 0.05 * dir[k]);
        if (hypot(Q[0] - P[0], Q[1] - P[1]) < 0.3) return 0;
    } else memcpy(Q, E, sizeof Q);
    double D[3] = {Q[0], Q[1], F(Q[2] - 0.1)};
    if (!w_sweep(w, Q, D, RH, RV, &c)) return 0;
    return c.n[2] > FLOOR_NZ && !(c.word & 1);
}

/* the lip lift 0x86920's decision [the clearance sweeps' ends inferred]: a body 1.236 m (plus ``reach``: 0.5 from the
 * swim, 0x8BAB5) ahead swept down from 2.301 to 0.699 m over the centre onto a firm (nz >= 0.866) ledge whose feet sit
 * within 0.401 m of 0.9 (``*high``: anim 65) or 0.1 m (anim 66) over the centre, with room to get there; ``to`` the
 * centre on the ledge (where FastL3 puts it, that tick), ``on`` the ledge's contact. */
static int lip_ok(World *w, const double *P, const double *dir, double mag, double state_t, double reach, double *to,
                  int *high, Contact *on) {
    if (!(mag > 0.0) || !(state_t > 2.5 * DT)) return 0;
    double ahead = 1.236 + reach;
    double S[3] = {F(P[0] + ahead * dir[0]), F(P[1] + ahead * dir[1]), F(P[2] + 1.0 + 0.401 + 0.9)};
    double E[3] = {S[0], S[1], F(P[2] + 0.1 - 0.401 + 1.0)};
    Contact c;
    if (!w_sweep(w, S, E, RH, RV, &c)) return 0;
    if (c.d > 0.0 || (c.word & 1) || !(c.n[2] > FLOOR_NZ) || c.n[2] < 0.866) return 0;
    double cz = F(S[2] + (E[2] - S[2]) * c.t), feet = cz - 1.0;
    Contact ledge = c;
    *high = fabs(feet - F(P[2] + 0.9)) <= 0.401;
    if (!*high && !(fabs(feet - F(P[2] + 0.1)) <= 0.401)) return 0;
    double up[3] = {P[0], P[1], cz}, over[3] = {S[0], S[1], cz};
    if (w_sweep(w, P, up, 0.3, 0.3, &c)) return 0;
    if (w_sweep(w, up, over, 0.3, 0.3, &c)) return 0;
    memcpy(to, over, sizeof over);
    *on = ledge;
    return 1;
}

static void hard(Player *p) {                       /* player_hard_land 0x8B100: the surface's velocity, the clip */
    p->state = S_HARD; p->clip = CLIP_HARD;
    p->vel[0] = p->vel[1] = p->vel[2] = 0.0;
}

/* 0x85920: ``c`` the contact (have: one), ``m`` the move (its velocity in and out), ``ray0`` the tick's start
 * position (input+0x54), where the floor ray starts. */
static void classify(World *w, Player *p, const Contact *c, int have, const Move *m, const double *ray0) {
    int was = p->state;
    if (!have) {                                             /* a fast slide stays one 0.5 s off its slope, outside */
        if (was == S_SLIDE && p->d4 < 0.5 && p->push[2] == 0.0) {   /* an updraft (0x8596E: pushZ 0) */
            p->d4 = F(p->d4 + F(DT)); return;                /* 0x85985: the float dt constant */
        }
        p->state = S_AIR; return;
    }
    if (m->vout[0] == 0.0 && m->vout[1] == 0.0 && m->vout[2] == 0.0 && -0.5 * G * DT > m->vel[2]
            && m->vel[2] < -0.866 * sqrt(dot(m->vel, m->vel))) {       /* the move stopped dead, falling */
        p->normal[0] = 0.0; p->normal[1] = 0.0; p->normal[2] = 1.0;
        if (was != S_WALK && m->vout[2] - m->vel[2] >= HARD) { hard(p); return; }
        p->state = S_WALK; p->f35 = 1; p->tries |= ZERO_V;
        return;
    }
    if (p->push[2] > 0.0) { p->state = S_AIR; return; }     /* 0x85AA7: in an updraft a contact lands nothing and
                                                              * stores no normal (Step R2.19f+, NS.K) */
    for (int k = 0; k < 3; k++) p->normal[k] = F(c->n[k]);
    if (!(c->n[2] > LAND_NZ)) { if (was != S_SLIDE) p->state = S_AIR; return; }
    if ((c->word & 1) || !(c->n[2] > FLOOR_NZ)) { if (was != S_SLIDE) p->state = S_SLOPE; p->d4 = 0.0; return; }
    if (was != S_WALK && m->vout[2] - m->vel[2] >= HARD) { hard(p); return; }   /* player_hard_land */
    double e[3] = {ray0[0], ray0[1], F(ray0[2] - RAY)};
    Contact r;
    if (w_sweep(w, ray0, e, 0.0, 0.0, &r)) {
        for (int k = 0; k < 3; k++) p->normal[k] = F(r.n[k]);
        if (!(r.word & 1) && r.n[2] > FLOOR_NZ) p->state = S_WALK;
        else { if (was != S_SLIDE) p->state = S_SLOPE; p->d4 = 0.0; }
        return;
    }
    p->state = S_WALK;
}

static void landing(Player *p, const Contact *c) {
    p->attached = 1;
    p->word = c->word;
    p->on = c->n[2] > LAND_NZ ? c->src : -1;
    p->spring = c->s;
    if (c->n[2] > LAND_NZ) { p->fall_ref = c->p[2]; p->flaps_used = 0; }
}

/* a lip lift's clip (Step R2.19f+): the body put at ``to`` on its ledge (``on``), still, its clip of
 * ``n`` rows played in place as the hard landing's (state 0x100, settling), then a walk */
static int lift(Player *p, const double *to, int n, const Contact *on) {
    for (int k = 0; k < 3; k++) { p->pos[k] = to[k]; p->vel[k] = 0.0; p->normal[k] = F(on->n[k]); }
    p->state = S_HARD; p->clip = n;
    landing(p, on);
    return 0;
}

/* ------------------------------------------------------------------------------------- the field volumes */
typedef struct {
    World *mesh;              /* the volume's faces, as given then reversed (a ray up meets the copy facing down) */
    int n;                    /* the faces as given (an index under n: the given face faces down) */
    double lo[3], hi[3], push[3];
    uint32_t word;
    int stop;                 /* 0 modelled; else the stop it raises (a volume that moves or switches) */
} Vol;

typedef struct Fields { int n, cap; Vol *v; } Fields;

Fields *f_new(void) { return calloc(1, sizeof(Fields)); }
void f_free(Fields *f) { if (f) { free(f->v); free(f); } }

/* a volume: ``mesh`` its faces then the same reversed (``n`` each), its box, word, world push and stop code */
void f_add(Fields *f, World *mesh, int n, const double *lo, const double *hi, uint32_t word, const double *push,
           int stop) {
    if (f->n == f->cap) { f->cap = f->cap ? 2 * f->cap : 16; f->v = realloc(f->v, sizeof(Vol) * f->cap); }
    Vol *v = f->v + f->n++;
    v->mesh = mesh; v->n = n; v->word = word; v->stop = stop;
    memcpy(v->lo, lo, sizeof v->lo); memcpy(v->hi, hi, sizeof v->hi); memcpy(v->push, push, sizeof v->push);
}

/* the volume query 0x60BD0 at ``q`` (the body centre at the tick's start): each volume whose mesh holds it (a ray
 * up meets a face facing down first, 0xD2A40) ORs its word and adds its push, and one with the water bit (0x60DA8
 * tests word 0x100) keeps its depth (that face's height over q) if deeper (0x60DCB-0x60DDE: the deepest of them);
 * a held volume that moves or switches stops the run (its code). */
static int f_query(const Fields *f, const double *q, Player *p) {
    p->fields = 0; p->push[0] = p->push[1] = p->push[2] = 0.0; p->depth = NO_DEPTH;
    if (!f) return 0;
    for (int i = 0; i < f->n; i++) {
        const Vol *v = f->v + i;
        if (q[0] < v->lo[0] || q[0] > v->hi[0] || q[1] < v->lo[1] || q[1] > v->hi[1] || q[2] < v->lo[2]
                || q[2] > v->hi[2]) continue;
        double e[3] = {q[0], q[1], q[2] + RAY_UP};
        Contact c;
        if (!w_sweep(v->mesh, q, e, 0.0, 0.0, &c) || c.tri >= v->n) continue;
        if (v->stop) return v->stop;
        p->fields |= v->word;
        for (int k = 0; k < 3; k++) p->push[k] = F(p->push[k] + v->push[k]);
        if (v->word & W_WATER) {
            double depth = F(c.t * RAY_UP);
            if (!(p->depth > depth)) p->depth = depth;
        }
    }
    return 0;
}

/* the query at ``q`` (for checks): its stop, and out = {words, push x, y, z, depth} */
int f_probe(const Fields *f, const double *q, double *out) {
    Player p;
    memset(&p, 0, sizeof p);
    int s = f_query(f, q, &p);
    out[0] = p.fields; out[1] = p.push[0]; out[2] = p.push[1]; out[3] = p.push[2]; out[4] = p.depth;
    return s;
}

/* the volumes a run on ``w`` queries (the caller keeps them alive while ``w`` runs) */
void w_fields(World *w, Fields *f) { w->fields = f; }

/* v := T + (v0 - T) k as 0x89613 and 0x8B92A round it: x through a float, y not, z through a float */
static void blend(double *v, const double *v0, const double *T, double k) {
    v[0] = F(F((v0[0] - T[0]) * k) + T[0]);
    v[1] = F((v0[1] - T[1]) * k + T[1]);
    v[2] = F(F((v0[2] - T[2]) * k) + T[2]);
}

/* the swim tick 0x8B700 (the module header; the catch 0x87120 and the lip lift 0x86920 with reach 0.5 after a
 * contact stop the run: climbing out is L3's).  ``up`` / ``down`` the pad's Y / BLACK. */
static int swim(World *w, Player *p, const Pad *pad, const double *start, const double *dir, double mag, int up,
                int down) {
    int surface = p->depth < SURFACE;
    double stroke = F(mag * STROKE), vt = F((up - down) * SWIM_V), k = pow(SWIM_BASE, DT), T[3], v[3];
    T[0] = F(F(dir[0] * stroke) + p->push[0]);
    T[1] = F(F(dir[1] * stroke) + p->push[1]);
    T[2] = F(p->push[2] + vt);
    blend(v, p->vel, T, k);
    if (surface && !(v[2] < p->push[2])) v[2] = p->push[2];
    Move m = {0};
    for (int i = 0; i < 3; i++) { m.pos[i] = p->pos[i]; m.vel[i] = v[i]; m.w[i] = v[i]; }
    m.dt = DT; m.rh = SWIM_R; m.rv = SWIM_R;
    w_move(w, &m);
    p->contacts = m.contacts;
    if (m.contact) {
        if (pad->sy > 0.0f && (m.B.word & 3) == 2 && fabs(m.B.n[2]) < 0.2588) { p->stop = STOP_CATCH; return p->stop; }
        double to[3]; int high; Contact on;               /* climbing out (reach 0.5): L3's, not ported */
        if (lip_ok(w, start, dir, mag, p->state_t, 0.5, to, &high, &on)) { p->stop = STOP_LIP; return p->stop; }
    }
    p->state = S_SWIM;
    for (int i = 0; i < 3; i++) { p->vel[i] = m.vout[i]; p->pos[i] = m.out[i]; }
    if (m.contact) landing(p, &m.A); else { p->attached = 0; p->on = -1; }
    return 0;
}

/* one tick: the game's state machine for the ported states.  Returns the stop code (0: go on). */
int p_step(World *w, Player *p, const Pad *pad) {
    int y = (pad->buttons & 1) != 0, lt = (pad->buttons & 2) != 0, black = (pad->buttons & 4) != 0;
    double start[3] = {p->pos[0], p->pos[1], p->pos[2]};
    if (HARD == 0.0) HARD = F(sqrt(2.0 * G * F(2.9)));
    p->tries = 0;
    if ((p->stop = f_query(w->fields, start, p))) return p->stop;   /* the input build's volume query 0x85587 */
    int swims = (p->fields & W_WATER) && (p->state == S_SWIM || !(p->depth < SURFACE));   /* each state's swim first */
    if (black && !swims) { p->stop = STOP_ROLL; return p->stop; }   /* BLACK's roll: a root-motion clip */
    if (!p->prev_y) p->latch_y = 0;                         /* the main loop's poll frees a released latch */
    int edge = y && !p->latch_y && !lt;
    p->prev_y = y;
    double mag = sqrt((double)pad->sx * pad->sx + (double)pad->sy * pad->sy);
    double cam = atan2(-(double)pad->cx, (double)pad->cy);
    double hd = cam + atan2(-(double)pad->sx, (double)pad->sy);
    double dir[3] = {F(-sin(hd)), F(cos(hd)), 0.0};
    if (!(mag > 0.0)) mag = 0.0;
    if (lt && y && p->shield) p->gauge = 1.0;                /* a recast refills the gauge */
    if (p->state == S_HARD && p->clip > 1) {                /* a clip (a hard landing's or a lift's): */
        Move m = {0};                                        /* in place, settling */
        for (int i = 0; i < 3; i++) m.pos[i] = p->pos[i];
        m.vel[2] = F(p->vel[2] - F(G * DT));
        m.dt = DT;
        w_move(w, &m);
        for (int i = 0; i < 3; i++) { p->pos[i] = m.out[i]; p->vel[i] = 0.0; }
        if (m.vout[2] < 0.0) p->vel[2] = m.vout[2];
        --p->clip;
        return 0;
    }
    if (p->state == S_HARD) { p->state = S_WALK; p->clip = 0; }   /* the tick after its last row is the walk's own (a
                                                                 * jump on it: FastL3's step-up at a5 job a502) */
    if (swims) return swim(w, p, pad, start, dir, mag, y, black);
    int spring = p->attached && (p->word & W_SPRING);
    if (p->state == S_SWIM) {                                /* out of the water: a walk if attached, else the air */
        p->state = p->attached ? S_WALK : S_AIR;
        edge = spring = 0;
    }
    if (p->state == S_WALK || p->state == S_SLOPE || p->state == S_SLIDE) {
        if (edge || spring) {                                /* jump_init: Y's edge or an autoSpring face */
            if (y) p->latch_y = 1;
            if (spring && p->spring != 0.0) { p->ac = SPRING_AC; p->h = F(p->spring); }
            else reinit(p);
            p->peak_z = F(p->pos[2] + p->h);
            double v0 = F(sqrt(2.0 * G * p->h));
            if (!spring && p->attached && ((p->word & 1) || !(p->normal[2] > 0.7070999742))) {
                p->vel[0] = F(p->vel[0] + v0 * p->normal[0]);
                p->vel[1] = F(p->vel[1] + v0 * p->normal[1]);
                p->vel[2] = F(0.0 + v0 * p->normal[2]);
            } else {
                p->vel[2] = F(0.0 + v0);
            }
            p->state = S_AIR; p->flaps_used = 0; p->attached = 0; p->on = -1;
            return 0;
        }
        if (p->state == S_SLOPE || p->state == S_SLIDE) {
            /* 0x8AE10: a walkable floor within 1 m under the centre takes the body onto it */
            double e1[3] = {start[0], start[1], F(start[2] - 1.0)};
            Contact r;
            if (w_sweep(w, start, e1, 0.0, 0.0, &r) && !(r.word & 1) && r.n[2] > FLOOR_NZ) {
                if (-p->vel[2] >= HARD) { hard(p); landing(p, &r); return 0; }
                p->pos[0] = F(r.p[0]); p->pos[1] = F(r.p[1]); p->pos[2] = F(r.p[2] + 1.0);
                p->vel[2] = 0.0;
                landing(p, &r);
                for (int i = 0; i < 3; i++) p->normal[i] = F(r.n[i]);
                p->state = S_WALK;
                return 0;
            }
            /* the slope slide 0x89A70: under 6 m/s (3 from a fast slide) state 3, its stick term; else 4 */
            double sp = sqrt(dot(p->vel, p->vel)), wv[3];
            if (sp < (p->state == S_SLOPE ? 6.0 : 3.0)) {
                p->state = S_SLOPE;
                for (int i = 0; i < 3; i++) wv[i] = F(p->vel[i] + 2.0 * DT * mag * dir[i]);
                wv[2] = F(wv[2] - G * DT);
            } else {
                p->state = S_SLIDE;
                for (int i = 0; i < 3; i++) wv[i] = p->vel[i];
            }
            Move m = {0};
            for (int i = 0; i < 3; i++) { m.pos[i] = p->pos[i]; m.w[i] = wv[i]; }
            m.vel[0] = p->vel[0]; m.vel[1] = p->vel[1]; m.vel[2] = F(p->vel[2] - F(G * DT));
            m.dt = DT; m.f35 = p->f35;
            w_move(w, &m);
            p->f35 = 0;
            p->contacts = m.contacts;
            if (p->state == S_SLIDE && m.contact && (m.first.word & 1) && m.first.n[2] > FLOOR_NZ) p->tries |= TRY_ICE;
            for (int i = 0; i < 3; i++) { p->vel[i] = m.vout[i]; p->pos[i] = m.out[i]; }
            classify(w, p, &m.A, m.contact, &m, start);
            if (m.contact) landing(p, &m.A); else { p->attached = 0; p->on = -1; }
            return p->stop;
        }
        /* walk 0x85F50 */
        double s = RUN * mag, wv[3] = {s*dir[0], s*dir[1], s*dir[2]}, *n = p->normal;
        double nn = dot(n, n), k = dot(n, wv) / (nn > 0 ? nn : 1), wp[3];
        for (int i = 0; i < 3; i++) wp[i] = F(wv[i] - n[i]*k);
        double lp = dot(wp, wp);
        if (lp != 0.0) { double f = sqrt(dot(wv, wv)) / sqrt(lp); for (int i = 0; i < 3; i++) wp[i] = F(wp[i]*f); }
        Move m = {0};
        for (int i = 0; i < 3; i++) { m.pos[i] = p->pos[i]; m.w[i] = wp[i]; }
        m.vel[0] = p->vel[0]; m.vel[1] = p->vel[1]; m.vel[2] = F(p->vel[2] - F(G * DT));
        m.dt = DT; m.f35 = p->f35;
        w_move(w, &m);
        p->f35 = 0;
        p->contacts = m.contacts;
        if (m.contact && (m.B.word & 3) == 2 && fabs(m.B.n[2]) < 0.2588) { p->stop = STOP_CLIMB; return p->stop; }
        if (m.contact && !(m.B.n[2] > 0.8) && stepup_ok(w, start, &m.B, dir, mag)) {
            p->stop = STOP_STEPUP;       /* L3's: the kernel can't put the body where 0x8B1D0 does (the header) */
            return p->stop;
        }
        double P[3] = {m.out[0], m.out[1], m.out[2]}, E[3] = {P[0], P[1], F(P[2] - PROBE)}, np[3];
        double vel[3] = {m.vout[0], m.vout[1], m.vout[2]};
        Contact pr;
        int ph = w_sweep(w, P, E, RH, RV, &pr);
        if (ph) {
            for (int i = 0; i < 3; i++) np[i] = F(P[i] + (E[i] - P[i]) * pr.t);
            for (int i = 0; i < 3; i++) vel[i] = F((np[i] - p->pos[i]) / DT);
            if (vel[2] > 0.0) vel[2] = 0.0;
        } else {
            memcpy(np, E, sizeof np);                         /* a miss leaves the body at the probe's end */
            if (m.contact && vel[2] > 0.0) vel[2] = 0.0;
        }
        for (int i = 0; i < 3; i++) { p->pos[i] = np[i]; p->vel[i] = vel[i]; }
        const Contact *cr = NULL;
        if (!m.contact) cr = ph ? &pr : NULL;
        else if (!ph) cr = &m.A;
        else cr = (m.A.n[2] > pr.n[2]) ? &m.A : &pr;
        classify(w, p, cr, cr != NULL, &m, start);
        if (cr) landing(p, cr); else { p->attached = 0; p->on = -1; }
        return p->stop;
    }
    if (p->state == S_AIR) {
        if (edge && p->flaps_max > 0 && p->flaps_used < p->flaps_max && p->gauge != 0.0) {   /* wing_flap */
            p->latch_y = 1;
            reinit(p);
            int got = consume(p, 1.0);
            {
                p->flaps_used++;
                double d = F(p->peak_z + p->h) - p->pos[2];
                if (!(d > 0.0)) d = 0.0;
                double hh = d < p->h ? d : p->h, v0f = F(sqrt(2.0 * G * hh));
                if (d > 6.0) { if (got != 2) consume(p, 100.0); v0f = F(v0f * 0.5); }
                double vz = F(v0f * 1.5 + p->vel[2]);
                p->vel[2] = v0f < vz ? v0f : vz;
                return 0;
            }
        }
        /* airborne 0x89480: in a push volume the stick term is cut to 0.1 and the push added, the blend 0.3^dt; with
         * pushZ, T_z = 0.1 vz + pushZ and no gravity */
        double ac = p->ac * mag, T[3] = {F(ac * dir[0]), F(ac * dir[1]), p->vel[2]}, base = AIR_BASE, g = G;
        if (p->fields & W_PUSH) {
            T[0] = F(T[0] * PUSH_T + p->push[0]);
            T[1] = F(p->push[1] + T[1] * PUSH_T);
            base = PUSH_BASE;
            if (p->push[2] != 0.0) { T[2] = F(p->push[2] + F(p->vel[2] * PUSH_T)); g = 0.0; }
        }
        double v[3], kb = pow(base, DT);
        if (p->fields & W_PUSH) blend(v, p->vel, T, kb);
        else {        /* R2.19d's rounding (D835): blend's, the game's, moved a knife-edge landing after an inexact
                       * contact (the sweep's face order) and lost a find; it waits for that order's port */
            v[0] = F(T[0] + (p->vel[0] - T[0]) * kb);
            v[1] = F(T[1] + (p->vel[1] - T[1]) * kb);
            v[2] = p->vel[2];
        }
        Move m = {0};
        for (int i = 0; i < 3; i++) { m.pos[i] = p->pos[i]; m.w[i] = v[i]; }
        m.vel[0] = v[0]; m.vel[1] = v[1]; m.vel[2] = F(v[2] - F(g * DT));
        m.dt = DT; m.f35 = p->f35;
        w_move(w, &m);
        p->f35 = 0;
        p->contacts = m.contacts;
        if (m.contact && v[2] <= F(G * DT * 0.5) && !(m.B.n[2] > 0.6)) {   /* the lip lift 0x86920, the catch 0x87120 */
            double to[3]; int high; Contact on;
            if (lip_ok(w, start, dir, mag, p->state_t, 0.0, to, &high, &on))
                return lift(p, to, high ? CLIP_LIP_HIGH : CLIP_LIP_LOW, &on);
            if (pad->sy > 0.0f && (m.B.word & 3) == 2 && fabs(m.B.n[2]) < 0.2588) { p->stop = STOP_CATCH; return p->stop; }
        }
        for (int i = 0; i < 3; i++) { p->vel[i] = m.vout[i]; p->pos[i] = m.out[i]; }
        classify(w, p, &m.A, m.contact, &m, start);
        if (m.contact) landing(p, &m.A); else p->on = -1;
        return p->stop;
    }
    p->stop = STOP_STATE;
    return p->stop;
}

/* run n ticks of pads; out per tick: pos (3), vel (3), state, flaps_used, contacts, stop.  Returns the ticks run
 * (stops early at a stop code). */
int p_run(World *w, Player *p, int n, const Pad *pads, double *out) {
    int k = 0;
    for (; k < n; k++) {
        if (w->nm) {                                         /* the movers' tick: a body on one rides it */
            if (p->on >= 0 && p->on < w->nm && w->present[p->on]) {
                double l[3];
                ixf(pose(w, p->on, p->tick), p->pos, l);
                xf(pose(w, p->on, p->tick + 1), l, p->pos);
            }
            w->now = p->tick + 1;
        }
        int was = p->state;
        int s = p_step(w, p, pads + k);
        p->tick++;
        p->state_t = p->state == was ? F(p->state_t + DT) : 0.0;
        double *o = out + 10*k;
        for (int i = 0; i < 3; i++) { o[i] = p->pos[i]; o[3+i] = p->vel[i]; }
        o[6] = p->state; o[7] = p->flaps_used; o[8] = p->contacts; o[9] = s + 16 * p->tries;
        if (s) { k++; break; }
    }
    return k;
}
