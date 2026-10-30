/* X42: a weaponless townsperson throws a rock or her vase (Step 2.159b;
 * D473, the owner: "Vase + rock (Recommended)": townswomen throw the
 * vase they carry, townsmen a rock; a real travelling projectile that
 * hits enemies, as a second WHITE set, D325), and since Step 2.167b
 * (D538's E2: "create new effects ... without replacing assets",
 * projectiles first) any body throws an effects template's projectile
 * (a fireball, an ice shard, an arrow) from the columns its recipe's
 * row names.
 *
 * Why.  The game has thrown projectiles only as critters of their own:
 * the earth guardian's boulders are critters it spawns (critter_spawn,
 * 0x45C10) into an owner object of its own, holds in its hand through
 * that owner's interface, launches with message 10 (a velocity and a
 * landing state, 0x38AE4) and lets state 23 (0x3A249) end on contact,
 * where apply_damage plays the boulder's die clip and its m_alpha link
 * loads the break.  Nothing of the player's throws.
 *
 * What.  The build gives the spare species `debug` a clone of the
 * boulder or a vase (W30) and this shim the throw's table (bytes param
 * player_model_throw_table).  Every PlayerControl tick, after the game's
 * own last call:
 *
 *   a swing of a table column (PC+0x134; its slot playing, critter+0x200
 *   == 0x52 + it; the attack bit PC+0x94 & 0x100; HP > 0) reaching that
 *   column's spawn fraction (PC+0x178) spawns a `debug` critter into this shim's
 *   owner object (a 7-slot interface: +0x00 the home, the player's point;
 *   +0x04 the death notify; +0x08 the held point, the palm, and the
 *   body's rotation; +0x0C no leash, zeros; +0x10 held?; +0x14 the held
 *   clip, 1; +0x18 0), its no-hit window (+0x1E0) 1e9 s so no hit lands on
 *   it, its target kinds (+0x168 & 0x4040) cleared so no target search
 *   (the game's, X21's, this one's) takes it;
 *
 *   held, the game's held update (0x37AB0) puts it at the palm: the hand
 *   bone's runtime origin (the anim object's bone +0xA0) plus the
 *   table's palm, through critter_model_matrix (0x42200) and the scale,
 *   no lower than the table's low over the player's point (a template's
 *   0: his point, about 1 m up; AZ-705, Step 2.167c: a catalisk's paw
 *   held its arrow 0.2-0.5 m over the sand, which ended it there; the
 *   kit's -1e9: the hand wherever it is);
 *
 *   at the column's release fraction it leaves from the palm pushed out
 *   horizontally to the table's push-out from his axis, aimed straight
 *   along the facing at the miss point (the table's miss on, the table's
 *   miss_z over his point: the kit's about the floor, so a throw dead
 *   ahead comes down through a critter's height; D761, Step 2.194b: no
 *   current ranged attack seeks);
 *   only a table with seek set aims at the critter attack_target_find
 *   (0x7EBB0) returns within the table's range (X21's radius, bytes param
 *   player_model_throw_radius_at, raised for the call) within the table's
 *   cone of the facing: the player's bounds centre (his vtable +0x80) plus
 *   the result's +4..+0xC, else the miss point.  Its velocity lands it there in t =
 *   clamp(the horizontal distance / the speed, tmin, tmax): v = (T -
 *   P0) / t + (0, 0, arc 4.9 t), sent as message 10 {10, the player, v, -,
 *   the table's clip slot, its landing state} through its vtable +0xB4;
 *   the game's thrown state takes 9.8 dt off its AI's vertical velocity
 *   each tick (AI = critter+0x180, its velocity +0x24, 0x30220), so with
 *   an arc other than 1 it gives (1 - arc) 9.8 dt back (or, above 1, takes
 *   it off) on the release tick and each flying tick after (dt the clock's
 *   step): it falls as arc g (the kit's 1: the game's lob; an arrow's 0: a
 *   straight line);
 *
 *   flying, each tick one hit_send (0x460B0) of the swept box between its
 *   last two points, padded by its radius and the table's pad, as the
 *   player's hit ({3, the player, his damage record, the column's
 *   multiplier}: the sender skips its source, so he is never hit), his
 *   species' hitsThroughWalls (+0x7C) set around the call so no wall test
 *   runs from him; its no-hit window re-armed; past the table's life in
 *   game time (the PlayerControl's clock) apply_damage(it, 0, 1) ends it;
 *
 *   on contact or landing state 23 ends it (apply_damage, the die clip,
 *   the break); the notify marks its slot, which one last hit test at the
 *   death point frees next tick;
 *
 *   a swing cut while it is held (another column, a hit reaction, HP 0)
 *   drops it from the push-out point with no velocity: it falls and
 *   breaks, sending no hit (the life caps it too).
 *
 * Four slots; a swing that finds none free ends the oldest flying one
 * (apply_damage notifies at once, 0x446E8: its slot is ENDED) and throws
 * on the next tick, once that slot frees; a swing ends at most one, and
 * none while a slot is already ENDED (a life that ran out this tick).  A
 * spawn the world queues (EAX 0, the flag 1) is adopted from the owner
 * list (the node no slot holds) once the world builds it, its slot
 * forgotten if it doesn't within the life.  Liveness is "its node
 * (critter+0x1EC) is still in the owner's list" (the engine unlinks it
 * at death and destruction), read with no dereference of a freed
 * critter; a new world, a new player or the clock going back empties the
 * ring and the list.
 *
 * ABI.  The trampoline takes the PlayerControl tick's CALL 0x8C450
 * (player_move_fx) at 0x8C3C3 (Europe 0x8C373, CALL 0x8C400): EAX = EDI
 * = the PlayerControl, one stack argument (RET 4).  It pushes the
 * argument again and makes the game's call with EAX as the caller set
 * it, then throw_tick(EDI), and returns popping the argument; the caller
 * reads only [esp+0x14] and EDI after.  Every C helper is cdecl (it
 * keeps EBX, ESI, EDI and EBP); x87 and SSE1 only (AZ-021).
 */

#include "azurik_vanilla.h"   /* the game's calls; and azurik.h: AZURIK_BYTES_PARAM */

#define PC_CLOCK      0x00C   /* PlayerControl -> the clock (+0x10: now, f64) */
#define PC_CRITTER    0x020   /* PlayerControl -> the player critter         */
#define PC_STATE      0x094   /* its move state: 0x100 attacking             */
#define PC_COLUMN     0x134   /* the attacks_anims column swinging           */
#define PC_YAW        0x138   /* the swing's yaw                             */
#define PC_FRAC       0x178   /* the swing's clip fraction                   */
#define CR_WORLD      0x154
#define CR_CELL       0x158
#define CR_POS        0x15C   /* its point (centre), m                       */
#define CR_FLAGS      0x168   /* its kinds: 0x4040 a target                  */
#define CR_SPECIES    0x178
#define CR_ANIM       0x17C   /* its anim object                             */
#define CR_SCALE      0x188
#define CR_QUAT       0x18C
#define CR_IMMUNE     0x1E0   /* its no-hit window, s                        */
#define CR_NODE       0x1EC   /* its node in its owner's list                */
#define CR_SLOT       0x200   /* the anim slot anim_change took              */
#define CR_HP         0x210
#define CR_RECORD     0x220   /* its damage record                           */
#define CR_AI         0x180   /* its AI: a thrown one's velocity at +0x24    */
#define AI_VZ         0x02C   /* its velocity's z, which 0x30220 takes g dt off */
#define SP_THRU       0x07C   /* species: hitsThroughWalls (byte)            */
#define AN_BONES      0x008   /* anim object -> its bones                    */
#define BONE_SIZE     0x0B0
#define BONE_ORIGIN   0x0A0   /* a bone's model-space origin                 */
#define CLOCK_NOW     0x010
#define ATTACK        0x100
#define SLOT_ATTACK   0x52
#define TARGETED      0x4040u /* the kinds attack_target_find takes          */
#define COLUMNS       24
#define RING          4
#define FOUND_WORDS   16
#define IMMUNE        1e9f
#define GRAVITY_HALF  4.9f    /* half the projectile's gravity, m/s^2        */
#define GRAVITY       9.8f    /* the thrown state's ([0x198740])             */
#define DT_MAX        0.1     /* the longest clock step gravity is given back over, s */

enum { FREE, HELD, FLYING, ENDED, DROPPED, PENDING, PENDING_DROP };

typedef struct Table {
    int   columns;      /* +0x00 the attacks_anims columns that throw (a mask)          */
    int   bone;         /* +0x04 the hand bone (-1: a point ahead of the chest)         */
    float palm[3];      /* +0x08 model units from the bone's origin                     */
    float vh;           /* +0x14 its horizontal speed, m/s                              */
    float arc;          /* +0x18 the share of gravity it falls with (1 the game's)      */
    float range;        /* +0x1C the aim's radius, m                                    */
    float miss;         /* +0x20 with no target, this far along the facing, m           */
    float cone;         /* +0x24 the cosine of the aim's half angle                     */
    float tmin, tmax;   /* +0x28, +0x2C the flight time's clamp, s                      */
    float pad;          /* +0x30 the hit box's pad past its radius, m                   */
    float life;         /* +0x34 the longest flight, s (game time)                      */
    float pushout;      /* +0x38 how far from his axis it leaves, m                     */
    int   anim;         /* +0x3C message 10's clip slot (-1: none)                      */
    int   landing;      /* +0x40 message 10's landing state                             */
    float radius;       /* +0x44 its radius, m                                          */
    char  species[16];  /* +0x48 its species                                            */
    float spawn[COLUMNS];   /* +0x58 each column's clip fraction it spawns in the hand at */
    float release[COLUMNS]; /* +0xB8 each column's clip fraction it leaves the hand at    */
    float mult[COLUMNS];    /* +0x118 each column's hit's damage multiplier               */
    float low;              /* +0x178 the lowest it is held at over the player's point, m */
    int   seek;             /* +0x17C 1: aim at the critter the target finder gives (D761: opt-in) */
    float miss_z;           /* +0x180 the miss point's height over his point, m              */
} Table;

typedef struct Slot {
    char  *critter;     /* +0x00 */
    int    state;       /* +0x04 */
    double released;    /* +0x08 the clock at its release                               */
    float  prev[3];     /* +0x10 its point a tick ago                                   */
    float  cur[3];      /* +0x1C its point now                                          */
    float  end[3];      /* +0x28 where it died                                          */
    int    record;      /* +0x34 the player's damage record at its release               */
    int    dropped;     /* +0x38 it ended dropped: no last test                          */
    float  mult;        /* +0x3C its column's multiplier at its release                  */
} Slot;

typedef struct Throw {
    void **vtable;      /* +0x00 the owner object: its interface                        */
    char  *head;        /* +0x04 its list's first node                                  */
    void  *slots[8];    /* +0x08 the interface                                          */
    char  *world;       /* +0x28 */
    char  *player;      /* +0x2C */
    double clock;       /* +0x30 */
    int    swing;       /* +0x38 the slot the swing holds, -1 none                      */
    int    tried;       /* +0x3C 1: the swing spawned; 2: it ended one and waits a slot */
    int    on;          /* +0x40 a throwing swing was on last tick                      */
    float  frac;        /* +0x44 its fraction last tick                                 */
    float  palm[3];     /* +0x48 the palm this tick                                     */
    float  rot[9];      /* +0x54 the body's rotation rows this tick                     */
    Slot   ring[RING];  /* +0x78 */
    int    col;         /* +0x178 the column it swings                                  */
} Throw;

_Static_assert(sizeof(Table) == 0x184, "the throw table is 0x184 bytes (_player_throw.TABLE_SIZE)");
_Static_assert(sizeof(Slot) == 0x40, "a slot is 0x40 bytes");
_Static_assert(__builtin_offsetof(Throw, ring) == 0x78, "the ring at +0x78");

volatile const Table player_model_throw_table __attribute__((used, section(".rdata"))) = {0};
AZURIK_BYTES_PARAM(player_model_throw_radius_at, 4);

Throw player_model_throw_state __attribute__((used)) = {0, 0, {0}, 0, 0, 0.0, -1, 0, 0, 0.0f, {0}, {0}, {{0}}, -1};

#define T player_model_throw_table
#define S player_model_throw_state

typedef float *(__attribute__((thiscall)) *centre_fn)(void *self, float *out);
typedef void (__attribute__((thiscall)) *message_fn)(void *self, int *message);

static float g_matrix[16] __attribute__((aligned(16)));
static float g_box[40] __attribute__((aligned(16)));

static float root(float x)
{
    float r;

    __asm__("sqrtss %1, %0" : "=x"(r) : "x"(x));
    return r;
}

static float absf(float x)
{
    return x < 0.0f ? -x : x;
}

static double clock_now(const char *pc)
{
    return *(const double *)(*(const char *const *)(pc + PC_CLOCK) + CLOCK_NOW);
}

/* critter_model_matrix (0x42200): ESI = the 16-aligned out, the critter on the stack. */
__attribute__((naked))
static void model_matrix(float *out, void *critter)
{
    __asm__ volatile (
        "pushl %%esi                         \n\t"
        "movl 8(%%esp), %%esi                \n\t"
        "pushl 12(%%esp)                     \n\t"
        "calll \"_critter_model_matrix@4\"   \n\t"
        "popl %%esi                          \n\t"
        "retl                                \n\t"
        : : : "memory");
}

/* The palm's world point (no lower than the table's low over his point) and the body's rotation rows (p' = p M). */
static void palm_of(char *player)
{
    float s = *(const float *)(player + CR_SCALE);
    const char *pose = *(const char *const *)(player + CR_ANIM);
    const char *bones = pose ? *(const char *const *)(pose + AN_BONES) : 0;
    float p[3];
    int i;

    p[0] = T.palm[0];
    p[1] = T.palm[1];
    p[2] = T.palm[2];
    if (T.bone >= 0 && bones) {
        const float *o = (const float *)(bones + BONE_SIZE * T.bone + BONE_ORIGIN);
        p[0] += o[0];
        p[1] += o[1];
        p[2] += o[2];
    } else {
        p[1] += 0.4f;
        p[2] += 1.2f;
    }
    model_matrix(g_matrix, player);
    for (i = 0; i < 3; i++) {
        S.palm[i] = s * (p[0] * g_matrix[i] + p[1] * g_matrix[4 + i] + p[2] * g_matrix[8 + i]) + g_matrix[12 + i];
        S.rot[i] = g_matrix[i];
        S.rot[3 + i] = g_matrix[4 + i];
        S.rot[6 + i] = g_matrix[8 + i];
    }
    if (S.palm[2] < *(const float *)(player + CR_POS + 8) + T.low)
        S.palm[2] = *(const float *)(player + CR_POS + 8) + T.low;
}

/* -- the owner interface (thiscall on &S) ---------------------------------------------------- */
__attribute__((thiscall)) static float *ow_home(void *self, float *out, int slot)
{
    const char *player = S.player;

    (void)self;
    (void)slot;
    out[0] = player ? *(const float *)(player + CR_POS) : 0.0f;
    out[1] = player ? *(const float *)(player + CR_POS + 4) : 0.0f;
    out[2] = player ? *(const float *)(player + CR_POS + 8) : 0.0f;
    return out;
}

__attribute__((thiscall)) static void ow_notify(void *self, int slot)
{
    Slot *s;

    (void)self;
    if ((unsigned)slot >= RING)
        return;
    s = &S.ring[slot];
    if (s->critter) {
        s->end[0] = *(const float *)(s->critter + CR_POS);
        s->end[1] = *(const float *)(s->critter + CR_POS + 4);
        s->end[2] = *(const float *)(s->critter + CR_POS + 8);
    }
    s->dropped = s->state != FLYING;
    s->state = ENDED;
}

__attribute__((thiscall)) static void ow_held(void *self, int slot, float *pos, float *mat)
{
    int i;

    (void)self;
    (void)slot;
    for (i = 0; i < 3; i++) {
        pos[i] = S.palm[i];
        mat[i] = S.rot[i];
        mat[4 + i] = S.rot[3 + i];
        mat[8 + i] = S.rot[6 + i];
        mat[12 + i] = 0.0f;
    }
    mat[3] = mat[7] = mat[11] = 0.0f;
    mat[15] = 1.0f;
}

__attribute__((thiscall)) static float *ow_leash(void *self, float *out, int slot)
{
    (void)self;
    (void)slot;
    out[0] = out[1] = out[2] = 0.0f;
    return out;
}

__attribute__((thiscall)) static int ow_is_held(void *self, int slot)
{
    (void)self;
    return (unsigned)slot < RING && S.ring[slot].state == HELD;
}

__attribute__((thiscall)) static int ow_clip(void *self, int slot)
{
    (void)self;
    (void)slot;
    return 1;
}

__attribute__((thiscall)) static int ow_none(void *self)
{
    (void)self;
    return 0;
}

/* -- the ring --------------------------------------------------------------------------------- */
static int linked(const char *critter)
{
    const char *node = critter + CR_NODE;
    const char *n = S.head;
    int guard = 0;

    while (n && guard++ < 64) {
        if (n == node)
            return 1;
        n = *(const char *const *)(n + 4);
    }
    return 0;
}

static void free_slot(Slot *s)
{
    volatile int *w = (volatile int *)s;
    unsigned i;

    for (i = 0; i < sizeof(Slot) / 4; i++)
        w[i] = 0;
}

static void send_message(char *critter, char *player, const float *v)
{
    int message[8];

    message[0] = 10;
    message[1] = (int)player;
    ((float *)message)[2] = v[0];
    ((float *)message)[3] = v[1];
    ((float *)message)[4] = v[2];
    message[5] = T.anim;
    message[6] = T.landing;
    message[7] = 0;
    (*(message_fn *)(*(char **)critter + 0xB4))(critter, message);
}

static void hit_test(char *player, const Slot *s, const float *c, const float *half)
{
    int message[8];
    char *species = *(char **)(player + CR_SPECIES);
    unsigned char thru;
    int i;

    for (i = 0; i < 40; i++)
        g_box[i] = 0.0f;
    g_box[0] = g_box[5] = g_box[10] = g_box[15] = 1.0f;
    g_box[16] = g_box[21] = g_box[26] = g_box[31] = 1.0f;
    for (i = 0; i < 3; i++) {
        g_box[12 + i] = c[i];
        g_box[28 + i] = -c[i];
        g_box[32 + i] = -half[i];
        g_box[35 + i] = half[i];
    }
    message[0] = 3;
    message[1] = (int)player;
    message[2] = s->record;
    ((float *)message)[3] = s->mult;
    message[4] = message[5] = message[6] = message[7] = 0;
    thru = species[SP_THRU];
    species[SP_THRU] = 1;
    hit_send(g_box, message);
    species[SP_THRU] = thru;
}

/* The palm pushed out horizontally to the push-out from his axis. */
static void push_out(const char *player, float *p0)
{
    const float *axis = (const float *)(player + CR_POS);
    float dx = S.palm[0] - axis[0], dy = S.palm[1] - axis[1];
    float r = root(dx * dx + dy * dy), fx = S.rot[3], fy = S.rot[4], k;

    p0[0] = S.palm[0];
    p0[1] = S.palm[1];
    p0[2] = S.palm[2];
    if (r >= T.pushout)
        return;
    if (r > 1e-3f) {
        fx = dx / r;
        fy = dy / r;
    } else {
        r = 0.0f;
    }
    k = T.pushout - r;
    p0[0] += fx * k;
    p0[1] += fy * k;
}

/* T for a launch from p0 along fwd: the miss point (miss on, miss_z over his point); with seek, the critter
 * attack_target_find gives within the cone. */
static int aim(char *player, const char *pc, const float *p0, const float *fwd, float *t)
{
    if (T.seek) {
        float *radius = *(float *const volatile *)player_model_throw_radius_at;
        int found[FOUND_WORDS];
        float was = 0.0f;
        int i;

        for (i = 0; i < FOUND_WORDS; i++)
            found[i] = 0;
        ((float *)found)[8] = ((float *)found)[9] = ((float *)found)[10] = 3.4e38f;
        ((float *)found)[11] = ((float *)found)[12] = ((float *)found)[13] = -3.4e38f;
        if (radius) {
            was = *radius;
            *radius = T.range;
        }
        attack_target_find(player, *(const float *)(pc + PC_YAW), found);
        if (radius)
            *radius = was;
        if (found[0] > 0) {   /* +4: the target less the player's bounds centre (0x7EBB0's vtable +0x80) */
            float buf[3];
            const float *centre = (*(centre_fn *)(*(char **)player + 0x80))(player, buf);
            const float *o = (const float *)found + 1;
            float d = root(o[0] * o[0] + o[1] * o[1]);

            if (d > 1e-3f && (o[0] * fwd[0] + o[1] * fwd[1]) / d >= T.cone) {
                t[0] = centre[0] + o[0];
                t[1] = centre[1] + o[1];
                t[2] = centre[2] + o[2];
                return 1;
            }
        }
    }
    t[0] = p0[0] + fwd[0] * T.miss;
    t[1] = p0[1] + fwd[1] * T.miss;
    t[2] = *(const float *)(player + CR_POS + 8) + T.miss_z;
    return 0;
}

/* Gravity's (1 - arc) share given back (taken, above 1) over dt: it falls as arc g (the kit's 1: none). */
static void lift(const Slot *s, double dt)
{
    char *ai = *(char **)(s->critter + CR_AI);

    if (ai && T.arc != 1.0f)
        *(float *)(ai + AI_VZ) += (1.0f - T.arc) * GRAVITY * (float)dt;
}

static void launch(char *player, const char *pc, Slot *s, int col, double dt)
{
    float p0[3], fwd[2], target[3], d[3], v[3], n, h, t;
    int i;

    push_out(player, p0);
    fwd[0] = S.rot[3];
    fwd[1] = S.rot[4];
    n = root(fwd[0] * fwd[0] + fwd[1] * fwd[1]);
    if (n > 1e-4f) {
        fwd[0] /= n;
        fwd[1] /= n;
    }
    aim(player, pc, p0, fwd, target);
    for (i = 0; i < 3; i++)
        d[i] = target[i] - p0[i];
    h = root(d[0] * d[0] + d[1] * d[1]);
    t = h / T.vh;
    if (t < T.tmin)
        t = T.tmin;
    if (t > T.tmax)
        t = T.tmax;
    v[0] = d[0] / t;
    v[1] = d[1] / t;
    v[2] = d[2] / t + GRAVITY_HALF * T.arc * t;
    for (i = 0; i < 3; i++) {
        s->prev[i] = s->cur[i] = p0[i];
        ((float *)(s->critter + CR_POS))[i] = p0[i];
    }
    s->record = *(const int *)(player + CR_RECORD);
    s->mult = T.mult[col];
    s->released = clock_now(pc);
    s->state = FLYING;
    send_message(s->critter, player, v);
    lift(s, dt);
}

/* It falls from the push-out point and breaks, sending no hit. */
static void drop(char *player, Slot *s)
{
    float p0[3], still[3] = {0.0f, 0.0f, 0.0f};
    int i;

    push_out(player, p0);
    for (i = 0; i < 3; i++)
        ((float *)(s->critter + CR_POS))[i] = p0[i];
    s->released = S.clock;
    s->state = DROPPED;
    send_message(s->critter, player, still);
}

static void take(char *critter, Slot *s)
{
    s->critter = critter;
    *(float *)(critter + CR_IMMUNE) = IMMUNE;
    *(unsigned *)(critter + CR_FLAGS) &= ~TARGETED;
}

static void spawn(char *player, int index)
{
    int desc[16], flag = 0, i;
    void *species = species_get_by_name((const char *)T.species, 0);
    char *critter;
    Slot *s = &S.ring[index];

    if (!species)
        return;
    for (i = 0; i < 16; i++)
        desc[i] = 0;
    desc[0] = (int)&S;
    desc[1] = index;
    desc[2] = (int)species;
    desc[3] = *(const int *)(player + CR_CELL);
    for (i = 0; i < 3; i++)
        ((float *)desc)[4 + i] = S.palm[i];
    for (i = 0; i < 4; i++)
        desc[7 + i] = *(const int *)(player + CR_QUAT + 4 * i);
    desc[12] = -1;
    desc[13] = -1;
    critter = (char *)critter_spawn(desc, *(void **)(player + CR_WORLD), &flag);
    if (critter) {
        take(critter, s);
        s->state = HELD;
        S.swing = index;
    } else if (flag) {   /* queued: adopted when the world builds it */
        s->state = PENDING;
        s->released = S.clock;
        S.swing = index;
    }
}

/* A queued spawn's critter: the node in the owner's list no slot holds. */
static void adopt(char *player, Slot *s)
{
    const char *n = S.head;
    int guard = 0, i, held;

    while (n && guard++ < 64) {
        char *critter = (char *)n - CR_NODE;

        held = 0;
        for (i = 0; i < RING; i++)
            if (S.ring[i].critter == critter)
                held = 1;
        if (!held) {
            take(critter, s);
            if (s->state == PENDING_DROP)
                drop(player, s);
            else
                s->state = HELD;
            return;
        }
        n = *(const char *const *)(n + 4);
    }
}

/* A free slot, else -1; with end and none ENDED, the oldest flying one is ended (flights frees its slot next tick). */
static int free_index(int end)
{
    int i, oldest = -1;
    double best = 1e300;

    for (i = 0; i < RING; i++) {
        if (S.ring[i].state == FREE)
            return i;
        if (S.ring[i].state == ENDED)   /* flights' life cap notified this tick: it frees next tick */
            end = 0;
    }
    for (i = 0; end && i < RING; i++)
        if (S.ring[i].state == FLYING && S.ring[i].released < best) {
            best = S.ring[i].released;
            oldest = i;
        }
    if (oldest >= 0)
        apply_damage((int)S.ring[oldest].critter, 0, 1);
    return -1;
}

static void reset(void)
{
    int i;

    for (i = 0; i < RING; i++)
        free_slot(&S.ring[i]);
    S.head = 0;
    S.swing = -1;
    S.tried = 0;
    S.on = 0;
    S.col = -1;
}

static void flights(char *player, double now, double dt)
{
    int i, k;

    for (i = 0; i < RING; i++) {
        Slot *s = &S.ring[i];
        float c[3], half[3];

        if (s->state == FREE)
            continue;
        if (s->state == PENDING || s->state == PENDING_DROP) {   /* never built within the life: forgotten */
            if (!(now - s->released >= 0.0 && now - s->released <= T.life))
                free_slot(s);
            else
                adopt(player, s);
            continue;
        }
        if (s->state == ENDED) {   /* one last test where it died, then free */
            if (!s->dropped) {
                half[0] = half[1] = half[2] = T.radius + T.pad + 0.3f;
                hit_test(player, s, s->end, half);
            }
            free_slot(s);
            continue;
        }
        if (!linked(s->critter)) {   /* gone without a notify */
            free_slot(s);
            continue;
        }
        if (s->state == HELD)
            continue;
        for (k = 0; k < 3; k++) {
            s->prev[k] = s->cur[k];
            s->cur[k] = *(const float *)(s->critter + CR_POS + 4 * k);
        }
        *(float *)(s->critter + CR_IMMUNE) = IMMUNE;
        if (!(now - s->released >= 0.0 && now - s->released <= T.life)) {   /* flying or dropped too long */
            apply_damage((int)s->critter, 0, 1);
            continue;
        }
        if (s->state != FLYING)
            continue;
        lift(s, dt);
        for (k = 0; k < 3; k++) {
            float d = absf(s->cur[k] - s->prev[k]);

            c[k] = (s->cur[k] + s->prev[k]) * 0.5f;
            half[k] = d + T.radius + T.pad;
        }
        hit_test(player, s, c, half);
    }
}

__attribute__((used))
void throw_tick(char *pc)
{
    char *player = *(char **)(pc + PC_CRITTER);
    char *world;
    double now, dt;
    int col, on, i;
    float frac;

    if (!player || !T.species[0])
        return;
    S.vtable = S.slots;
    S.slots[0] = (void *)ow_home;
    S.slots[1] = (void *)ow_notify;
    S.slots[2] = (void *)ow_held;
    S.slots[3] = (void *)ow_leash;
    S.slots[4] = (void *)ow_is_held;
    S.slots[5] = (void *)ow_clip;
    S.slots[6] = (void *)ow_none;
    world = *(char **)(player + CR_WORLD);
    now = clock_now(pc);
    if (world != S.world || player != S.player || now < S.clock) {
        reset();
        S.world = world;
        S.player = player;
        S.clock = now;
    }
    dt = now - S.clock;
    if (dt > DT_MAX)
        dt = DT_MAX;
    S.clock = now;
    palm_of(player);
    flights(player, now, dt);
    col = *(const int *)(pc + PC_COLUMN);
    frac = *(const float *)(pc + PC_FRAC);
    on = (*(const unsigned *)(pc + PC_STATE) & ATTACK) && (unsigned)col < COLUMNS && ((T.columns >> col) & 1)
         && *(const int *)(player + CR_SLOT) == SLOT_ATTACK + col && *(const int *)(player + CR_HP) > 0;
    if (S.swing >= 0 && (!on || frac < S.frac || col != S.col)) {   /* the swing ended or started again: a held one drops */
        Slot *s = &S.ring[S.swing];

        if (s->state == HELD)
            drop(player, s);
        else if (s->state == PENDING)
            s->state = PENDING_DROP;
        S.swing = -1;
    }
    if (on && (!S.on || frac < S.frac || col != S.col))
        S.tried = 0;
    if (on && S.tried != 1 && frac >= T.spawn[col]) {   /* a full ring: the first try ends one, then each tick waits */
        i = free_index(!S.tried);
        S.tried = i >= 0 ? 1 : 2;
        if (i >= 0)
            spawn(player, i);
    }
    if (on && S.swing >= 0 && frac >= T.release[col]) {
        Slot *s = &S.ring[S.swing];

        if (s->state == HELD)
            launch(player, pc, s, col, dt);
        else if (s->state == PENDING)
            s->state = PENDING_DROP;
        S.swing = -1;
    }
    S.on = on;
    S.frac = frac;
    S.col = on ? col : -1;
}

/* 0x8C3C3: CALL player_move_fx (EAX the PlayerControl, its argument), then the throw. */
__attribute__((naked))
void c_player_model_throw(void)
{
    __asm__ volatile (
        "pushl 4(%%esp)                      \n\t"
        "calll \"_player_move_fx@4\"         \n\t"
        "pushl %%edi                         \n\t"
        "calll _throw_tick                   \n\t"
        "addl $4, %%esp                      \n\t"
        "retl $4                             \n\t"
        : : : "memory");
}
