/* X41: a worn body's jiggle bones swing on real-time springs driven by
 * the player's own drawn motion (Step 2.156; D443, D444, D445).
 *
 * Why.  The game has no secondary motion, and Step 2.143's springs were
 * baked into each clip's keys at the rate the game plays it, scaled down
 * so no clip passes its travel: they barely move (AZ-656), and a clip
 * can't know the landing, hit, spin or stop it is played through.  Here
 * the springs run every pose from the bone's place as it is drawn.
 *
 * What.  This shim replaces the per-bone CALL of anim_bone_matrix
 * (0xCA470) at 0xCB5CB inside the pose's matrix builder 0xCB550 (Europe
 * 0xCB74B -> 0xCA5F0), which every way a critter's bones are built goes
 * through (the 30 Hz pose, critter_init's first pose, the staff-wall
 * re-pose, the marker pass's rest rebuild).  At bone 0 (ESI = 0)
 * jiggle_begin decides whether this build is the player's: the scene
 * global (a bytes param read from the image's own load at 0x513D3) ->
 * +0x2C the world -> +0xC0 the player critter, whose anim object
 * (+0x17C) is this one (EBX), with a PlayerControl (+0x180), a drawn
 * scale (+0x188) other than 0 and the body's bone count the table's.
 * Every other critter's bone costs five instructions and a tail call to
 * the game's 0xCA470.  On the player's build, once per new clock (the
 * anim's clock +4 -> +0x10, f64) it calls critter_model_matrix (0x42200)
 * on the player, its 3x3 times the drawn scale: the drawn place, the
 * aligned-node term included (2.6 m at a climb-over, docs/RE_XBE.md).
 * 0x42200 may run the marker pass, which may rebuild the bones through
 * this hook: a static busy flag keeps that nested build vanilla
 * (player_model_jiggle_build stays 0), and X26's two latch words (their
 * VAs a bytes param, 0 without X26) are put back after the call, so the
 * game's own calls see the sequence they would.  Another anim, player
 * or controller or the clock going back resets every row and draws this
 * build vanilla, with no 0x42200 call; a matrix that isn't finite resets
 * them after it.  A clip change keeps the springs: anim_play_clip
 * (0xCAD40) stamps +0x28 and +0x30 with -1 on every one, so +0x30 < 0 is
 * no sign of a new anim.  critter_init's first pose fails the player
 * test: critter_spawn (0x53F2C) returns before 0x53F5B sets world+0xC0.
 * jiggle_bone runs after the game's 0xCA470 built the bone: a bone the
 * table maps (and whose record's parent is the row's) steps its row's
 * springs once a new clock (jiggle_rt.py's Twin, step for step: two
 * probes carried by the bone into the world by that matrix, their
 * velocity filtered and differenced, softly capped, a damped spring per
 * axis stepped in 1/120 s substeps by the build's own transition
 * matrices, the state stop bouncing; a teleport, glide-mode change or
 * gap kicking nothing) and writes its world (+0x70) := Q x world, Q the
 * offset's move in the bone's frame (wbind x O x ib): the squash's
 * volume-keeping scale about the centre (D481), then the rigid move.
 * The gain scales the springs' motion (the mass from its world rest); the
 * hang (its world rest from the bone's turned rest sag) shows at 1, so a
 * fast tilt throws nothing.  A same-clock rebuild applies the kept Q to
 * this build's world.  The local (+0x30) and T/q/S stay as the game
 * sampled them, so nothing piles up (+0x2C).  Children are built from
 * the written world by the game's own loop, so a row whose bone descends
 * from another row's (its chain, D485: a ponytail's links) is carried by
 * that row's swing: its drive takes the swing in full (the written world
 * against the posed one, which the parent row keeps) and only the clip's
 * own motion at the pace.  Strength (a float param, the slider) scales
 * the shown offset.
 *
 * A run's start kicks (Step 2.156b, D518, AZ-678; jiggle_rt.py's Twin):
 * once she moves off (START on the ground, state 0) after standing (under
 * REST), the kick's clock counts the steps' time; while she runs (RUN_ON)
 * and it is under a row's kick_time, e = 1 - t / kick_time, that row's
 * level drive is held to 1 - kick_hold x e of itself (none below 0) before
 * the cap, so a turn into the run doesn't swing the forms sideways first
 * and take the cap's share from the up drive, and its up drive (her first
 * footfalls' push) raised to 1 + kick x e after it.  A stop (under START),
 * a jump, a hit or any other state ends it, and any state but the ground's
 * disarms it until she stands again, so a landing never starts one (a
 * standing jump steered forward lands running); a walk has none.
 *
 * A landing's impact (Step 2.174, D584, D619; jiggle_rt.py's Twin): for a
 * row with an impact, the step a probe falling faster than IMPACT_FALL
 * (its filtered velocity before the step) is first pushed up while she
 * isn't in the air (state AIR) but was within LAND_TIME (so a clip's own
 * drop while she stands, a death's or a victory's, opens none), it is
 * owed impact x that speed as a push along the bone's up as drawn (-down:
 * the crouch bends her forward), after the cap, spread evenly over
 * LAND_TIME in place of its own up drive, which stays held for LAND_TIME
 * and, for a landing begun in the hard landing (HARD), through that
 * crouch, whose sink and rise would cut the dive and brake the rebound.
 * So a longer fall bounces the forms further, held only by the travel's
 * soft limit and the state stop.
 * A row's wall (Step 2.169b, D536: booblord's sash and tabard, a chain
 * of links each on its own row): a unit axis in the bone's bind axes,
 * toward her (the panel's face after the clip's hang), and a stop, m as
 * drawn.  Each probe's allowance is the stop less how far its parents'
 * swing already carries it in along the axis off the clip's pose (qs -
 * qa, the probe as built from the parent row's written world less the
 * probe as the clip poses it, into the bind axes by the drawn matrix and
 * the bone's inverse), so the stops don't add up down a chain: where the
 * raw offset passes it, that part comes off the mass and its inward speed
 * bounces with RESTITUTION, as the state stop's; after the soft limit the
 * shown offset is held to it.  No tip comes nearer her than its stop off
 * the clip's pose, a link its parent swung in is turned back out, and
 * outward and sideways stay free; at a gain of 0 no wall acts.
 *
 * ABI: at the CALL EBX = the anim, ESI = the bone's offset (index x
 * 0xB0), EAX = the runtime bone, EDI = &the parent's scale, [ESP + 4]
 * after it the parent's world; 0xCA470 keeps EBX, ESI, EDI and EBP and
 * pops its argument (RET 4), and 0xCB550 reads none of EAX, ECX and EDX
 * after it.  The stub keeps EBX, ESI, EDI and EBP, leaves the x87 stack
 * empty, calls its C 16-byte aligned and returns with RET 4.  0x42200
 * takes ESI = a 16-byte aligned out (a .bss buffer) and the critter on
 * the stack (RET 4).  All arithmetic is x87 double (-mcpu=pentium3, no
 * SSE2, AZ-021); sqrt is fsqrt.
 */

#include "azurik_vanilla.h"   /* and azurik.h: AZURIK_FLOAT_PARAM, AZURIK_BYTES_PARAM */

#define ROWS        32
#define BONES       256
#define TWO_PROBES  1u
#define RESTS       2u
#define GAP         0.25
#define GAP_STEPS   30
#define EDGE        0.999999
#define MAX_STEPS   32
#define TELEPORT2   1.0       /* (1 m)^2                                */
#define KNEE        0.6
#define BOUND       3.0
#define RESTITUTION 0.3
#define SWIMMING    6
#define HIT         0x102     /* a hit reaction keeps the medium it began in */
#define AIR         2         /* in the air: no landing starts           */
#define HARD        0x100     /* a hard landing's crouch: an open one holds */
#define IMPACT_FALL 3.0       /* m/s: a faster fall lands with the impact */
#define LAND_TIME   0.15      /* s: a landing's push, the probe's own held */
#define LN2         0.6931471805599453
#define PACE_LIMIT  700.0
#define SQUASH_LIMIT 1.0
#define REST2       1.0       /* (m/s)^2: standing, so moving off kicks   */
#define START2      4.0       /* (2 m/s)^2: moving off; under it, none    */
#define RUN2        25.0      /* (5 m/s)^2: running: the kick applies     */
#define AN_LAYERS   0x40      /* anim: its 3 layers, 0x40 bytes each      */
#define LY_FLAGS    0x08      /* layer: 0 free                            */
#define LY_WEIGHT   0x1C
#define LY_RATE     0x20

#define AN_BODY     0x00      /* anim -> its body (+0: the bone count)   */
#define AN_CLOCK    0x04      /* anim -> its clock (+0x10: now, f64)      */
#define AN_BONES    0x08      /* anim -> its runtime bones (0xB0 each)    */
#define BN_WORLD    0x70      /* runtime bone: its world (model space)    */
#define SC_WORLD    0x2C      /* scene -> its world                       */
#define WD_PLAYER   0xC0      /* world -> the player critter              */
#define CR_ANIM     0x17C     /* critter -> its anim object               */
#define CR_CONTROL  0x180     /* critter -> its PlayerControl             */
#define CR_SCALE    0x188     /* critter: its drawn scale                 */
#define CR_MODE     0x19C     /* critter: 0x42070's glide mode            */
#define PC_VELOCITY 0x24      /* PlayerControl: its velocity, m/s         */
#define PC_STATE    0x94      /* PlayerControl: its move state            */

typedef struct row {
    int bone, parent;
    unsigned flags;
    int chain;            /* the row its bone descends from + 1; 0 none  */
    double phi_land[4], gamma_land[2], phi_swim[4], gamma_swim[2];
    double alpha, g_land, g_swim, sag_land, sag_swim;
    float accel, gain;
    float travel[3], weights[3], centre[3], pivot[3];
    float sides, turn, rot_share, pace;
    float squash[3], kick;
    float kick_hold, kick_time, impact, spare;
    float wall[4];        /* a unit axis in the bind axes, toward her; its stop, m as drawn (axis 0: none) */
    float ib[16], wbind[16];
} Row;

typedef struct table {
    char magic[4];
    unsigned rows, bones, flags;
    double h;
    float kappa, drawn;
    unsigned char map[BONES];
    Row row[ROWS];
} Table;

_Static_assert(sizeof(Row) == 400, "jiggle_rt.py packs ROW_SIZE");
_Static_assert(sizeof(Table) == 288 + ROWS * 400, "jiggle_rt.py packs TABLE_SIZE");
_Static_assert(__builtin_offsetof(Row, accel) == 152 && __builtin_offsetof(Row, squash) == 224
               && __builtin_offsetof(Row, kick_time) == 244 && __builtin_offsetof(Row, impact) == 248
               && __builtin_offsetof(Row, wall) == 256 && __builtin_offsetof(Row, ib) == 272,
               "jiggle_rt.py's row layout");

typedef struct state {
    double u[2][3], v[2][3], prev[2][3], vf[2][3];
    double qprev[2][3];   /* the probes in the model, last step         */
    double qaprev[2][3];  /* the same as the clip poses them (a chain)  */
    double mprev[16];     /* the drawn matrix, last step                */
    double acc;
    double q[16];
    double wa[16], wo[16];   /* this build's world as the clip poses it, as written */
    unsigned stamp;          /* the build that set wa and wo            */
    int live, warm, has_q, mode, swim, wrote;
    double land[2];          /* a landing's push still to give, m/s     */
    double lt[2];            /* s since its landing; < 0: none open      */
    double rate[2];          /* its push, m/s^2                          */
    double air;              /* s since she was in the air; < 0: longer  */
    int hard[2];             /* it met the ground in a hard landing      */
} State;

typedef struct shown {
    float offset[3];   /* mm as drawn: side, forward, up              */
    float roll, yaw;   /* rad                                          */
    float raw;         /* the offset's raw radius over its travel      */
    double now;
    float scale[3];    /* the squash's, along side, forward, up        */
    float pad;
} Shown;

_Static_assert(sizeof(Shown) == 48, "jiggle_rt.py's SHOWN_SIZE");

typedef struct kick {
    double t;          /* s since she moved off                        */
    int on, running, armed;
    unsigned starts;
} Kick;

volatile const Table player_model_jiggle_bones __attribute__((used, section(".rdata"))) = {{0}};
AZURIK_BYTES_PARAM(player_model_jiggle_scene, 4);
AZURIK_BYTES_PARAM(player_model_jiggle_x26, 8);
AZURIK_FLOAT_PARAM(player_model_jiggle_strength, 1.0f);

char *player_model_jiggle_build __attribute__((used));   /* the anim being jiggled, else 0 */
unsigned player_model_jiggle_steps __attribute__((used));
unsigned player_model_jiggle_resets __attribute__((used));
float player_model_jiggle_m[16] __attribute__((used));   /* 0x42200 x the drawn scale        */
Shown player_model_jiggle_shown[ROWS] __attribute__((used));
State player_model_jiggle_state[ROWS] __attribute__((used));
Kick player_model_jiggle_kick __attribute__((used));   /* the run-start clock */

static float g_raw[16] __attribute__((aligned(16)));
static int g_busy, g_have, g_step;
static unsigned g_build;
static double g_clock, g_dt, g_rate;
static char *g_anim, *g_player, *g_control;
static float g_scale;

#define T player_model_jiggle_bones
#define AT(p, off, type) (*(type *)((char *)(p) + (off)))

static int fin(double x)
{
    return x - x == 0.0;
}

static double root(double x)
{
    double r;

    __asm__("fsqrt" : "=t"(r) : "0"(x));
    return r;
}

/* out := critter_model_matrix(critter) (0x42200: ESI the out, the critter
 * on the stack, RET 4). */
__attribute__((naked, noinline, used))
static void model_matrix(void *critter, float *out)
{
    __asm__ volatile (
        "pushl %%esi              \n\t"
        "movl 0xc(%%esp), %%esi   \n\t"   /* the out     */
        "pushl 0x8(%%esp)         \n\t"   /* the critter */
        "calll \"_critter_model_matrix@4\" \n\t"
        "popl %%esi               \n\t"
        "retl                     \n\t"
        : : : "memory"
    );
}

/* e^x by scaling and squaring (jiggle_rt._exp). */
static double expo(double x)
{
    double e = 1.0, a = x < 0.0 ? -x : x;
    int s = 0, n;

    while (a > 0.5 && s < 2000) {
        x *= 0.5;
        a *= 0.5;
        s++;
    }
    for (n = 16; n > 0; n--)
        e = 1.0 + x / n * e;
    while (s-- > 0)
        e *= e;
    return e;
}

/* ln x, x > 0 (jiggle_rt._ln). */
static double ln(double x)
{
    double z, z2, term, total = 0.0;
    int k = 0, n;

    while (x > 1.5 && k < 1100) {
        x *= 0.5;
        k++;
    }
    while (x < 0.75 && k > -1100) {
        x *= 2.0;
        k--;
    }
    z = (x - 1.0) / (x + 1.0);
    z2 = z * z;
    term = z;
    for (n = 0; n < 20; n++) {
        total += term / (2 * n + 1);
        term *= z2;
    }
    return 2.0 * total + k * LN2;
}

/* rate ** -pace above 1, else 1 (jiggle_rt.pace_factor). */
static double pace_factor(double rate, double pace)
{
    double x;

    if (!(pace != 0.0 && rate > 1.0))
        return 1.0;
    x = -pace * ln(rate);
    if (x < -PACE_LIMIT)
        x = -PACE_LIMIT;
    if (x > PACE_LIMIT)
        x = PACE_LIMIT;
    return expo(x);
}

static void mul4(double *o, const double *a, const double *b)
{
    int r, c;

    for (r = 0; r < 4; r++)
        for (c = 0; c < 4; c++)
            o[4 * r + c] = a[4 * r] * b[c] + a[4 * r + 1] * b[4 + c] + a[4 * r + 2] * b[8 + c]
                + a[4 * r + 3] * b[12 + c];
}

/* The row-vector rotation of the unit quaternion (x, y, z, w). */
static void qrow(double *m, double x, double y, double z, double w)
{
    m[0] = 1.0 - 2.0 * (y * y + z * z); m[1] = 2.0 * (x * y + z * w); m[2] = 2.0 * (x * z - y * w);
    m[3] = 2.0 * (x * y - z * w); m[4] = 1.0 - 2.0 * (x * x + z * z); m[5] = 2.0 * (y * z + x * w);
    m[6] = 2.0 * (x * z + y * w); m[7] = 2.0 * (y * z - x * w); m[8] = 1.0 - 2.0 * (x * x + y * y);
}

static double soft(double n, double stop)
{
    double x;

    if (n <= KNEE * stop)
        return n;
    x = (n - KNEE * stop) / ((1.0 - KNEE) * stop);
    return KNEE * stop + (1.0 - KNEE) * stop * x / (1.0 + x);
}

static double soft1(double a, double stop)
{
    if (!(stop > 0.0))
        return 0.0;
    return a >= 0.0 ? soft(a, stop) : -soft(-a, stop);
}

/* e through the ellipsoid limit of stops; returns its raw radius. */
static double soft3(double *e, const double *stops)
{
    double r2 = 0.0, r, x, m, q;
    int i;

    for (i = 0; i < 3; i++)
        if (stops[i] > 0.0) {
            q = e[i] / stops[i];
            r2 += q * q;
        } else {
            e[i] = 0.0;
        }
    r = root(r2);
    if (r <= KNEE)
        return r;
    x = (r - KNEE) / (1.0 - KNEE);
    m = (KNEE + (1.0 - KNEE) * x / (1.0 + x)) / r;
    for (i = 0; i < 3; i++)
        e[i] *= m;
    return r;
}

/* inv := the inverse of the row-major 3x3 a; 0 when it has none. */
static int inverse3(double *inv, const double *a)
{
    double det = a[0] * (a[4] * a[8] - a[5] * a[7]) - a[1] * (a[3] * a[8] - a[5] * a[6])
        + a[2] * (a[3] * a[7] - a[4] * a[6]);
    double adj[9];
    int i;

    if (!(det != 0.0) || !fin(det))
        return 0;
    adj[0] = a[4] * a[8] - a[5] * a[7]; adj[1] = a[2] * a[7] - a[1] * a[8]; adj[2] = a[1] * a[5] - a[2] * a[4];
    adj[3] = a[5] * a[6] - a[3] * a[8]; adj[4] = a[0] * a[8] - a[2] * a[6]; adj[5] = a[2] * a[3] - a[0] * a[5];
    adj[6] = a[3] * a[7] - a[4] * a[6]; adj[7] = a[1] * a[6] - a[0] * a[7]; adj[8] = a[0] * a[4] - a[1] * a[3];
    for (i = 0; i < 9; i++)
        inv[i] = adj[i] / det;
    return 1;
}

/* inv := the inverse of the affine D3D-row 4x4 m (jiggle_rt._inverse4);
 * 0 when it has none. */
static int inverse4(double *inv, const double *m)
{
    double a[9], i3[9];
    int r, c;

    for (r = 0; r < 3; r++)
        for (c = 0; c < 3; c++)
            a[3 * r + c] = m[4 * r + c];
    if (!inverse3(i3, a))
        return 0;
    for (r = 0; r < 3; r++) {
        for (c = 0; c < 3; c++)
            inv[4 * r + c] = i3[3 * r + c];
        inv[4 * r + 3] = 0.0;
    }
    for (c = 0; c < 3; c++)
        inv[12 + c] = -(m[12] * i3[c] + m[13] * i3[3 + c] + m[14] * i3[6 + c]);
    inv[15] = 1.0;
    return 1;
}

/* The form's scales (jiggle_rt._squash): eps_i = squash_i x the offset
 * along i over its stop, each e^(eps_i - (eps_j + eps_k) / 2), the
 * exponent softly limited: its volume kept. */
static void squash(double *sc, const double *delta, const double *stops, const volatile float *sq)
{
    double eps[3];
    int i;

    for (i = 0; i < 3; i++)
        eps[i] = stops[i] > 0.0 ? (double)sq[i] * delta[i] / stops[i] : 0.0;
    for (i = 0; i < 3; i++)
        sc[i] = (eps[0] != 0.0 || eps[1] != 0.0 || eps[2] != 0.0)
            ? expo(soft1(eps[i] - 0.5 * (eps[(i + 1) % 3] + eps[(i + 2) % 3]), SQUASH_LIMIT)) : 1.0;
}

/* o := the move taking the centre by delta (jiggle_rt._offset): the
 * squash's scale sc about the centre, then the rigid move; 0 when
 * anything isn't finite. */
static int offset(double *o, const double *delta, double roll, double yaw, const double *centre,
                  const double *pivot, double share, const double *sc)
{
    double rt[9], rs[9] = {1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0}, rot[9];
    double r[3], b[3], cx[3], rsr[3], t[3], crt[3], lead[3];
    double qy = roll * 0.5, qz = yaw * 0.5, nq, rr, along, w, nn;
    int i, j;

    if (!fin(delta[0]) || !fin(delta[1]) || !fin(delta[2]) || !fin(roll) || !fin(yaw))
        return 0;
    nq = root(qy * qy + qz * qz + 1.0);
    qrow(rt, 0.0, qy / nq, qz / nq, 1.0 / nq);
    for (i = 0; i < 3; i++)
        r[i] = centre[i] - pivot[i];
    rr = r[0] * r[0] + r[1] * r[1] + r[2] * r[2];
    if (rr > 0.0 && share != 0.0) {
        along = (delta[0] * r[0] + delta[1] * r[1] + delta[2] * r[2]) / rr;
        for (i = 0; i < 3; i++)
            b[i] = r[i] + share * (delta[i] - along * r[i]);
        cx[0] = r[1] * b[2] - r[2] * b[1];
        cx[1] = r[2] * b[0] - r[0] * b[2];
        cx[2] = r[0] * b[1] - r[1] * b[0];
        w = root(rr * (b[0] * b[0] + b[1] * b[1] + b[2] * b[2])) + r[0] * b[0] + r[1] * b[1] + r[2] * b[2];
        nn = root(cx[0] * cx[0] + cx[1] * cx[1] + cx[2] * cx[2] + w * w);
        if (nn > 0.0)
            qrow(rs, cx[0] / nn, cx[1] / nn, cx[2] / nn, w / nn);
    }
    for (i = 0; i < 3; i++)
        for (j = 0; j < 3; j++)
            rot[3 * i + j] = rt[3 * i] * rs[j] + rt[3 * i + 1] * rs[3 + j] + rt[3 * i + 2] * rs[6 + j];
    for (j = 0; j < 3; j++) {
        rsr[j] = r[0] * rs[j] + r[1] * rs[3 + j] + r[2] * rs[6 + j];
        t[j] = delta[j] - (rsr[j] - r[j]);
        crt[j] = centre[0] * rt[j] + centre[1] * rt[3 + j] + centre[2] * rt[6 + j];
        lead[j] = centre[j] - crt[j] - pivot[j];
    }
    for (i = 0; i < 3; i++) {
        o[4 * i] = rot[3 * i]; o[4 * i + 1] = rot[3 * i + 1]; o[4 * i + 2] = rot[3 * i + 2]; o[4 * i + 3] = 0.0;
    }
    for (j = 0; j < 3; j++)
        o[12 + j] = lead[0] * rs[j] + lead[1] * rs[3 + j] + lead[2] * rs[6 + j] + pivot[j] + t[j];
    o[15] = 1.0;
    if (sc[0] != 1.0 || sc[1] != 1.0 || sc[2] != 1.0) {
        double s4[16] = {0.0}, r4[16];

        if (!fin(sc[0]) || !fin(sc[1]) || !fin(sc[2]))
            return 0;
        for (i = 0; i < 3; i++) {
            s4[5 * i] = sc[i];
            s4[12 + i] = centre[i] * (1.0 - sc[i]);
        }
        s4[15] = 1.0;
        mul4(r4, s4, o);
        for (i = 0; i < 16; i++)
            o[i] = r4[i];
    }
    return 1;
}

static void substep(State *st, int k, const volatile double *phi, const volatile double *gam, const double *force)
{
    double a = phi[0], b = phi[1], c = phi[2], d = phi[3], g0 = gam[0], g1 = gam[1], u, v;
    int i;

    for (i = 0; i < 3; i++) {
        u = st->u[k][i];
        v = st->v[k][i];
        st->u[k][i] = a * u + b * v + g0 * force[i];
        st->v[k][i] = c * u + d * v + g1 * force[i];
    }
}

/* A probe's offset in the bind axes from its mass (jiggle_rt.Twin._shape):
 * the gain on the springs' motion (the mass from its world rest), the hang
 * (its world rest from the bone's turned rest sag) at the strength. */
static void shape(double *e, const double *u, double kg, double ks, double sag, const double *down,
                  const double *inv, const volatile float *weights)
{
    double dw[3];
    int i, j;

    for (i = 0; i < 3; i++)
        dw[i] = kg * (u[i] + (i == 2 ? sag : 0.0)) + ks * sag * ((i == 2 ? -1.0 : 0.0) - down[i]);
    for (j = 0; j < 3; j++)
        e[j] = (double)weights[j] * (dw[0] * inv[j] + dw[1] * inv[3 + j] + dw[2] * inv[6 + j]);
}

/* The probes in the model and the drawn matrix, for the next step's split
 * of the body's motion from its pose's (the pace). */
static void keep_frame(State *st, double qs[2][3], double qa[2][3], const double *m)
{
    int k, i;

    for (k = 0; k < 2; k++)
        for (i = 0; i < 3; i++) {
            st->qprev[k][i] = qs[k][i];
            st->qaprev[k][i] = qa[k][i];
        }
    for (i = 0; i < 16; i++)
        st->mprev[i] = m[i];
}

static void reset_all(void)
{
    int n;

    for (n = 0; n < ROWS; n++) {
        player_model_jiggle_state[n].live = 0;
        player_model_jiggle_state[n].has_q = 0;
    }
    player_model_jiggle_kick.on = 0;
    player_model_jiggle_kick.armed = 0;
    player_model_jiggle_resets++;
}

/* Bone 0 of a build (cdecl): is it the player's, and is the clock new? */
__attribute__((used))
void jiggle_begin(char *anim)
{
    char *scene, *world, *player, *control;
    unsigned at, held_at, edge_at;
    int held = 0, edge = 0, i;
    float s;
    double now;

    player_model_jiggle_build = 0;
    if (g_busy || !T.rows)
        return;
    at = *(const volatile unsigned *)player_model_jiggle_scene;
    if (!at || !(scene = *(char **)at) || !(world = AT(scene, SC_WORLD, char *))
        || !(player = AT(world, WD_PLAYER, char *)) || AT(player, CR_ANIM, char *) != anim
        || !(control = AT(player, CR_CONTROL, char *)))
        return;
    s = AT(player, CR_SCALE, float);
    if (!(s > 0.0f || s < 0.0f) || *AT(anim, AN_BODY, int *) != (int)T.bones)
        return;
    now = AT(AT(anim, AN_CLOCK, char *), 0x10, double);
    if (anim != g_anim || player != g_player || control != g_control || !fin(now)
        || (g_have && !(now >= g_clock))) {
        reset_all();
        g_anim = anim;
        g_player = player;
        g_control = control;
        g_clock = now;
        g_have = 1;
        return;
    }
    if (now != g_clock) {
        held_at = ((const volatile unsigned *)player_model_jiggle_x26)[0];
        edge_at = ((const volatile unsigned *)player_model_jiggle_x26)[1];
        if (held_at)
            held = *(int *)held_at;
        if (edge_at)
            edge = *(int *)edge_at;
        g_busy = 1;
        model_matrix(player, g_raw);
        g_busy = 0;
        if (held_at)
            *(int *)held_at = held;
        if (edge_at)
            *(int *)edge_at = edge;
        for (i = 0; i < 16; i++) {
            player_model_jiggle_m[i] = i < 12 ? (float)((double)g_raw[i] * (double)s) : g_raw[i];
            if (!fin(player_model_jiggle_m[i])) {
                reset_all();
                g_clock = now;
                return;
            }
        }
        g_dt = now - g_clock;
        g_clock = now;
        g_step = 1;
        player_model_jiggle_steps++;
        {   /* the run-start clock (jiggle_rt.Twin._kick_clock) */
            float *v = (float *)(control + PC_VELOCITY);
            double sp2 = (double)v[0] * (double)v[0] + (double)v[1] * (double)v[1];
            int ground = AT(control, PC_STATE, int) == 0;
            Kick *kk = &player_model_jiggle_kick;

            if (kk->on)
                kk->t += g_dt;
            if (!ground || sp2 < START2)
                kk->on = 0;
            if (!ground)
                kk->armed = 0;
            if (ground && sp2 < REST2) {
                kk->armed = 1;
            } else if (kk->armed && ground && sp2 >= START2) {
                kk->on = 1;
                kk->armed = 0;
                kk->t = 0.0;
                kk->starts++;
            }
            kk->running = sp2 >= RUN2;
        }
        {
            double ws = 0.0, wr = 0.0;

            for (i = 0; i < 3; i++) {
                char *layer = anim + AN_LAYERS + 0x40 * i;

                if (AT(layer, LY_FLAGS, unsigned)) {
                    ws += AT(layer, LY_WEIGHT, float);
                    wr += (double)AT(layer, LY_WEIGHT, float) * (double)AT(layer, LY_RATE, float);
                }
            }
            g_rate = ws > 0.0 ? wr / ws : 1.0;
        }
    } else {
        g_step = 0;
    }
    g_scale = s;
    g_build++;
    player_model_jiggle_build = anim;
}

/* A row's springs stepped once a new clock from w, its bone's world as
 * built (wa: as the clip poses it, before a chain parent's swing; 0: w). */
static void step(int n, const volatile Row *r, State *st, const double *w, const double *wa)
{
    double ib[16], m[16], x[16], xa[16], xm[16], wb[16], o[16], ob[16], a3[9], inv[9];
    double pts[2][3] = {{0.0}}, qs[2][3] = {{0.0}}, qa[2][3] = {{0.0}}, dn[3], down[3], dl, dt, g, sag, bound, tm;
    double sc, stops[3], kg, ks, raw = 0.0, scale[3];
    double centre[3], pivot[3], es[2][3], delta[3], roll = 0.0, yaw = 0.0, ac, span, keep, share, f, pace, e;
    double nw[3], gw[3], gg = 0.0, lim = 0.0, over;
    int walled;
    const volatile double *phi, *gam;
    float *vel = (float *)(g_control + PC_VELOCITY);
    int np, k, i, j, swim, steps, jump, mode = AT(g_player, CR_MODE, int);
    int state = AT(g_control, PC_STATE, int);
    Shown *sh = &player_model_jiggle_shown[n];

    if (r->flags & RESTS) {
        st->has_q = 0;
        return;
    }
    for (i = 0; i < 16; i++) {
        ib[i] = r->ib[i];
        wb[i] = r->wbind[i];
        m[i] = player_model_jiggle_m[i];
    }
    for (i = 0; i < 3; i++) {
        centre[i] = r->centre[i];
        pivot[i] = r->pivot[i];
    }
    mul4(x, ib, w);
    if (wa)
        mul4(xa, ib, wa);
    else
        for (i = 0; i < 16; i++)
            xa[i] = x[i];
    mul4(xm, x, m);
    np = (r->flags & TWO_PROBES) ? 2 : 1;
    for (k = 0; k < np; k++) {
        double side = np == 2 ? (k ? (double)r->sides : -(double)r->sides) : 0.0;
        double c0 = centre[0] + side;

        for (j = 0; j < 3; j++) {
            pts[k][j] = c0 * xm[j] + centre[1] * xm[4 + j] + centre[2] * xm[8 + j] + xm[12 + j];
            qs[k][j] = c0 * x[j] + centre[1] * x[4 + j] + centre[2] * x[8 + j] + x[12 + j];
            qa[k][j] = c0 * xa[j] + centre[1] * xa[4 + j] + centre[2] * xa[8 + j] + xa[12 + j];
        }
    }
    dn[0] = -xm[8];
    dn[1] = -xm[9];
    dn[2] = -xm[10];
    dl = root(dn[0] * dn[0] + dn[1] * dn[1] + dn[2] * dn[2]);
    if (!(dl > 0.0) || !fin(dl)) {
        st->live = 0;
        st->has_q = 0;
        return;
    }
    for (i = 0; i < 3; i++)
        down[i] = dn[i] / dl;
    swim = state == SWIMMING || (state == HIT && st->live && st->swim);   /* a hit in the water writes 0x102 */
    st->swim = swim;
    phi = swim ? r->phi_swim : r->phi_land;
    gam = swim ? r->gamma_swim : r->gamma_land;
    g = swim ? r->g_swim : r->g_land;
    sag = swim ? r->sag_swim : r->sag_land;
    if (!st->live) {
        for (k = 0; k < np; k++)
            for (i = 0; i < 3; i++) {
                st->u[k][i] = sag * down[i];
                st->v[k][i] = 0.0;
                st->prev[k][i] = pts[k][i];
            }
        st->live = 1;
        st->warm = 1;
        st->mode = mode;
        st->acc = 0.0;
        st->has_q = 0;
        st->lt[0] = st->lt[1] = -1.0;
        st->air = state == AIR ? 0.0 : -1.0;
        keep_frame(st, qs, qa, m);
        for (i = 0; i < 3; i++) {
            sh->offset[i] = 0.0f;
            sh->scale[i] = 1.0f;
        }
        sh->roll = sh->yaw = sh->raw = 0.0f;
        sh->now = g_clock;
        return;
    }
    dt = g_dt;
    if (state == AIR)   /* in the air: a landing may begin until LAND_TIME after */
        st->air = 0.0;
    else if (st->air >= 0.0 && (st->air += dt) > LAND_TIME)
        st->air = -1.0;
    if (dt > GAP) {   /* a gap: ring free under gravity, the drive re-seeded */
        double force[3] = {0.0, 0.0, -g};

        for (k = 0; k < np; k++)
            for (i = 0; i < GAP_STEPS; i++)
                substep(st, k, phi, gam, force);
        st->acc = 0.0;
        st->lt[0] = st->lt[1] = -1.0;
        for (k = 0; k < np; k++)
            for (i = 0; i < 3; i++)
                st->prev[k][i] = pts[k][i];
        st->mode = mode;
        keep_frame(st, qs, qa, m);
    } else {
        double acc[2][3] = {{0.0, 0.0, 0.0}, {0.0, 0.0, 0.0}};

        st->acc += dt;
        steps = 0;
        while (steps < MAX_STEPS && st->acc > T.h * EDGE) {
            st->acc -= T.h;
            steps++;
        }
        jump = mode != st->mode;
        for (k = 0; k < np; k++) {
            double d0 = pts[k][0] - st->prev[k][0] - (double)vel[0] * dt;
            double d1 = pts[k][1] - st->prev[k][1] - (double)vel[1] * dt;
            double d2 = pts[k][2] - st->prev[k][2] - (double)vel[2] * dt;

            if (d0 * d0 + d1 * d1 + d2 * d2 > TELEPORT2)
                jump = 1;
        }
        if (st->warm) {
            for (k = 0; k < np; k++)
                for (i = 0; i < 3; i++)
                    st->vf[k][i] = (pts[k][i] - st->prev[k][i]) / dt;
            st->warm = 0;
        } else if (!jump) {
            keep = 1.0;
            for (i = 0; i < steps; i++)
                keep *= 1.0 - r->alpha;
            share = 1.0 - keep;
            ac = r->accel;
            pace = pace_factor(g_rate, r->pace);
            e = 0.0;   /* a run's start: its kick, tapering */
            if (player_model_jiggle_kick.on && player_model_jiggle_kick.running && r->kick_time > 0.0f
                && player_model_jiggle_kick.t < (double)r->kick_time)
                e = 1.0 - player_model_jiggle_kick.t / (double)r->kick_time;
            for (k = 0; k < np; k++) {
                double *qp = st->qprev[k], *qap = st->qaprev[k], *mp = st->mprev, frame[3], posed[3], swung[3];
                double da[3], dj[3], fall = st->vf[k][2];

                for (i = 0; i < 3; i++) {
                    da[i] = qa[k][i] - qap[i];
                    dj[i] = (qs[k][i] - qa[k][i]) - (qp[i] - qap[i]);
                }
                for (j = 0; j < 3; j++) {
                    frame[j] = qp[0] * (m[j] - mp[j]) + qp[1] * (m[4 + j] - mp[4 + j])
                        + qp[2] * (m[8 + j] - mp[8 + j]) + (m[12 + j] - mp[12 + j]);
                    posed[j] = da[0] * m[j] + da[1] * m[4 + j] + da[2] * m[8 + j];
                    swung[j] = dj[0] * m[j] + dj[1] * m[4 + j] + dj[2] * m[8 + j];
                }
                for (i = 0; i < 3; i++) {
                    double va = (pace == 1.0 ? pts[k][i] - st->prev[k][i]
                                 : frame[i] + pace * posed[i] + swung[i]) / dt;
                    double nf = st->vf[k][i] + (va - st->vf[k][i]) * share;

                    acc[k][i] = (nf - st->vf[k][i]) / dt;
                    st->vf[k][i] = nf;
                }
                if (e > 0.0 && r->kick_hold != 0.0f) {   /* the level drive held, to none at most */
                    double level = 1.0 - (double)r->kick_hold * e;

                    if (!(level > 0.0))
                        level = 0.0;
                    acc[k][0] *= level;
                    acc[k][1] *= level;
                }
                if (ac > 0.0) {
                    double a2 = acc[k][0] * acc[k][0] + acc[k][1] * acc[k][1] + acc[k][2] * acc[k][2];

                    f = 1.0 / root(1.0 + a2 / (ac * ac));
                    for (i = 0; i < 3; i++)
                        acc[k][i] *= f;
                }
                if (e > 0.0 && r->kick != 0.0f)   /* her first footfalls' push raised */
                    acc[k][2] *= 1.0 + (double)r->kick * e;
                if (r->impact > 0.0f) {   /* a landing: its up push keyed on the speed it met the ground at */
                    if (st->lt[k] < 0.0 && state != AIR && st->air >= 0.0 && fall < -IMPACT_FALL
                        && st->vf[k][2] > fall) {
                        st->land[k] = (double)r->impact * -fall;
                        st->lt[k] = 0.0;
                        st->hard[k] = state == HARD;
                        st->rate[k] = st->land[k] / LAND_TIME;
                    }
                    if (st->lt[k] >= 0.0) {   /* spread evenly over LAND_TIME along her up, the own held */
                        double d = st->rate[k] * dt < st->land[k] ? st->rate[k] * dt : st->land[k];

                        st->land[k] -= d;
                        acc[k][2] = 0.0;
                        for (i = 0; i < 3; i++)
                            acc[k][i] -= d / dt * down[i];
                        st->lt[k] += dt;
                        if (st->lt[k] >= LAND_TIME && !(st->hard[k] && state == HARD))
                            st->lt[k] = -1.0;
                    }
                }
            }
        }
        for (k = 0; k < np; k++)
            for (i = 0; i < 3; i++)
                st->prev[k][i] = pts[k][i];
        st->mode = mode;
        keep_frame(st, qs, qa, m);
        for (k = 0; k < np; k++) {
            double force[3];

            force[0] = -acc[k][0];
            force[1] = -acc[k][1];
            force[2] = -g - acc[k][2];
            for (i = 0; i < steps; i++)
                substep(st, k, phi, gam, force);
        }
    }
    tm = r->travel[0];
    if (r->travel[1] > tm)
        tm = r->travel[1];
    if (r->travel[2] > tm)
        tm = r->travel[2];
    bound = BOUND * tm;
    for (k = 0; k < np; k++) {   /* the state stop: on its sphere, the outward speed bounced */
        double dd[3], rad, nh[3], vr;

        for (i = 0; i < 3; i++)
            dd[i] = st->u[k][i] - sag * down[i];
        rad = root(dd[0] * dd[0] + dd[1] * dd[1] + dd[2] * dd[2]);
        if (bound > 0.0 && rad > bound) {
            for (i = 0; i < 3; i++) {
                nh[i] = dd[i] / rad;
                st->u[k][i] = sag * down[i] + nh[i] * bound;
            }
            vr = st->v[k][0] * nh[0] + st->v[k][1] * nh[1] + st->v[k][2] * nh[2];
            if (vr > 0.0)
                for (i = 0; i < 3; i++)
                    st->v[k][i] = st->v[k][i] - (1.0 + RESTITUTION) * vr * nh[i];
        }
    }
    for (k = 0; k < np; k++)
        for (i = 0; i < 3; i++)
            if (!fin(st->u[k][i]) || !fin(st->v[k][i]) || !fin(st->vf[k][i]) || !fin(st->prev[k][i])) {
                st->live = 0;
                st->has_q = 0;
                return;
            }
    for (i = 0; i < 3; i++)
        for (j = 0; j < 3; j++)
            a3[3 * i + j] = xm[4 * i + j];
    if (!inverse3(inv, a3)) {
        st->has_q = 0;
        return;
    }
    sc = g_scale < 0.0f ? -(double)g_scale : (double)g_scale;
    for (i = 0; i < 3; i++)
        stops[i] = r->travel[i] / sc;
    ks = (double)player_model_jiggle_strength;
    kg = ks * (double)r->gain;
    for (i = 0; i < 3; i++)
        nw[i] = (double)r->wall[i];
    walled = (nw[0] != 0.0 || nw[1] != 0.0 || nw[2] != 0.0) && kg != 0.0;
    for (i = 0; i < 3; i++) {   /* the axis's part of the offset per unit of the mass's move */
        gw[i] = inv[3 * i] * (double)r->weights[0] * nw[0] + inv[3 * i + 1] * (double)r->weights[1] * nw[1]
            + inv[3 * i + 2] * (double)r->weights[2] * nw[2];
        gg += gw[i] * gw[i];
    }
    for (k = 0; k < np; k++) {
        double rr;

        if (walled) {   /* the allowance: the stop less its parents' swing toward her off the clip's pose */
            double hw[3], hb = 0.0;

            for (j = 0; j < 3; j++)
                hw[j] = (qs[k][0] - qa[k][0]) * m[j] + (qs[k][1] - qa[k][1]) * m[4 + j]
                    + (qs[k][2] - qa[k][2]) * m[8 + j];
            for (j = 0; j < 3; j++)
                hb += (hw[0] * inv[j] + hw[1] * inv[3 + j] + hw[2] * inv[6 + j]) * nw[j];
            lim = (double)r->wall[3] / sc - hb;
        }
        shape(es[k], st->u[k], kg, ks, sag, down, inv, r->weights);
        if (walled && gg > 0.0) {   /* the part past it off the mass, its inward speed bounced */
            over = es[k][0] * nw[0] + es[k][1] * nw[1] + es[k][2] * nw[2] - lim;
            if (over > 0.0) {
                double c = over / (kg * gg), vr = st->v[k][0] * gw[0] + st->v[k][1] * gw[1] + st->v[k][2] * gw[2];

                for (i = 0; i < 3; i++)
                    st->u[k][i] -= c * gw[i];
                if (kg * vr > 0.0)
                    for (i = 0; i < 3; i++)
                        st->v[k][i] -= (1.0 + RESTITUTION) * vr / gg * gw[i];
                shape(es[k], st->u[k], kg, ks, sag, down, inv, r->weights);
            }
        }
        rr = soft3(es[k], stops);
        if (rr > raw)
            raw = rr;
        if (walled) {   /* the shown offset held to it */
            over = es[k][0] * nw[0] + es[k][1] * nw[1] + es[k][2] * nw[2] - lim;
            if (over > 0.0)
                for (i = 0; i < 3; i++)
                    es[k][i] -= over * nw[i];
        }
    }
    if (np == 2) {
        span = 2.0 * (double)r->sides;
        for (i = 0; i < 3; i++)
            delta[i] = (es[0][i] + es[1][i]) * 0.5;
        roll = soft1((es[0][2] - es[1][2]) / span, r->turn);
        yaw = soft1((es[1][1] - es[0][1]) / span, r->turn);
    } else {
        for (i = 0; i < 3; i++)
            delta[i] = es[0][i];
    }
    squash(scale, delta, stops, r->squash);
    if (!offset(o, delta, roll, yaw, centre, pivot, r->rot_share, scale)) {
        st->has_q = 0;
        return;
    }
    mul4(ob, wb, o);
    mul4(st->q, ob, ib);
    st->has_q = 1;
    for (i = 0; i < 16; i++)
        if (!fin(st->q[i]))
            st->has_q = 0;
    for (i = 0; i < 3; i++) {
        sh->offset[i] = (float)(delta[i] * sc * 1000.0);
        sh->scale[i] = (float)scale[i];
    }
    sh->roll = (float)roll;
    sh->yaw = (float)yaw;
    sh->raw = (float)raw;
    sh->now = g_clock;
}

/* After the game's 0xCA470 built a bone of the player's build (cdecl). */
__attribute__((used))
void jiggle_bone(char *anim, unsigned off)
{
    unsigned k = off / 0xB0, idx, up;
    char *bone;
    float *w, f[16];
    double wd[16], out[16], wa[16], *posed = 0;
    State *st;
    int i;

    if (k >= BONES || !(idx = T.map[k]) || idx > T.rows)
        return;
    bone = AT(anim, AN_BONES, char *) + off;
    if (AT(AT(bone, 0, char *), 8, short) != T.row[idx - 1].parent)
        return;
    st = &player_model_jiggle_state[idx - 1];
    w = (float *)(bone + BN_WORLD);
    for (i = 0; i < 16; i++)
        wd[i] = w[i];
    up = (unsigned)T.row[idx - 1].chain;
    if (up && up <= T.rows) {   /* built from a chain parent's written world: as the clip poses it */
        State *ps = &player_model_jiggle_state[up - 1];
        double back[16], t[16];

        if (ps->stamp == g_build && ps->wrote && inverse4(back, ps->wo)) {
            mul4(t, wd, back);
            mul4(wa, t, ps->wa);
            posed = wa;
        }
    }
    if (g_step)
        step(idx - 1, &T.row[idx - 1], st, wd, posed);
    st->stamp = g_build;
    st->wrote = 0;
    for (i = 0; i < 16; i++)
        st->wa[i] = posed ? wa[i] : wd[i];
    if (!st->has_q)
        return;
    mul4(out, st->q, wd);
    for (i = 0; i < 16; i++) {
        f[i] = (float)out[i];
        if (!fin(f[i]))
            return;
    }
    for (i = 0; i < 16; i++) {
        w[i] = f[i];
        st->wo[i] = f[i];
    }
    st->wrote = 1;
}

/* 0xCB5CB in 0xCB550: the CALL of anim_bone_matrix (0xCA470). */
__attribute__((naked))
void c_player_model_jiggle(void)
{
    __asm__ volatile (
        "testl %%esi, %%esi                  \n\t"
        "jnz 1f                              \n\t"   /* bone 0 opens a build */
        "pushl %%eax                         \n\t"
        "pushl %%ebp                         \n\t"
        "movl %%esp, %%ebp                   \n\t"
        "andl $-16, %%esp                    \n\t"
        "subl $12, %%esp                     \n\t"
        "pushl %%ebx                         \n\t"   /* the anim */
        "calll _jiggle_begin                 \n\t"
        "movl %%ebp, %%esp                   \n\t"
        "popl %%ebp                          \n\t"
        "popl %%eax                          \n\t"
        "1:                                  \n\t"
        "cmpl _player_model_jiggle_build, %%ebx \n\t"
        "jne 9f                              \n\t"
        "pushl 4(%%esp)                      \n\t"   /* the parent's world */
        "calll \"_anim_bone_matrix@4\"       \n\t"
        "pushl %%ebp                         \n\t"
        "movl %%esp, %%ebp                   \n\t"
        "andl $-16, %%esp                    \n\t"
        "subl $8, %%esp                      \n\t"
        "pushl %%esi                         \n\t"   /* the bone's offset */
        "pushl %%ebx                         \n\t"
        "calll _jiggle_bone                  \n\t"
        "movl %%ebp, %%esp                   \n\t"
        "popl %%ebp                          \n\t"
        "retl $4                             \n\t"
        "9:                                  \n\t"
        "jmp \"_anim_bone_matrix@4\"         \n\t"   /* every other bone: the game's */
        : : : "memory"
    );
}
