/* X28: a body hanging deeper than garret4 rides over every floor under
 * its path, at most a step a tick (Step 2.118, AZ-529 (b), D293;
 * hang_start reworked in Step 2.118c).
 *
 * Why.  X9's ride hangs a body drawn at a model scale X' times
 * garret4's grab under the cable (its pose's top at the cable, Step
 * 2.106), and the model is drawn from its origin (+0x1B0, +0x1BC),
 * which 0x42E40 puts there each tick, while the body collides at its
 * centre (+0x15C), garret4's.  A body whose drawn hang reaches further
 * under the cable than garret4's (2.83 m: no floor his x1 collision
 * allows comes closer) is drawn through the floors the centre passes
 * over: f3's start platform (keylord own x2 0.51 m under, Europe's golem
 * own x2 4.01, kingkong own x2 25.99) and its hang_start glide (0.88,
 * 2.60, 21.66 m), sitting 2.106.  Step 2.118's first X28 held the ride
 * (its mesh at least -0.004 m over the face under the centre on every
 * ride tick of 14 rows) but its hang_start half broke D293 (sitting
 * 2.118): it raised the glide's ends by each tick's shortfall and never
 * lowered them (a ratchet: ride tick 1 then dropped 1.06-4.44 m), the
 * rise had no cap (guard_air own x2 2.17 m in a tick), the set-up tick
 * wasn't held, and a pose that falls faster than a step a tick (guard_air
 * own x2's crossfade into its stand-in, about 4 m in 3 ticks) can't be
 * followed from the last drawn pose at a capped rise: it has to be seen
 * coming.  Step 2.118c's first rework capped the glide origin, but the
 * draw adds 0x402E0's aligned-node term (the node +0x1F8 names, m_root
 * in hang_start, in the clip less in the blended pose), which moves in
 * the crossfade into the clip on a body with that node: guard_air own x2
 * drew 0.877-0.880 m a tick at h2-h5, its term rising 0.032 m a tick
 * (sitting 2.118c).
 *
 * What.  Three landings of this object share one state block, the ride
 * landing's (the others reach it through player_model_hold_shared, the
 * block's address the build writes after the ride lands): the last
 * tick's clock time, the drawn origin's height, the centre, hang_start's
 * offset, its set-up time, the critter and the phase (hang_start or the
 * ride).  A tick's state counts for the next only within 0.1 s
 * (LAST_FOR) and for the same critter.
 *
 *   c_player_model_hang_hold_ride, at the ride's (state 5, 0x8A510)
 *   CALL of the state's landing 0x8C080 at 0x8AB3F, right after X9's
 *   0x42E40 at 0x8AB32: the drawn origin's height D (the glide origin
 *   plus the term's height, read through 0x402E0 at the landing, where
 *   the layers are already this tick's: 0xCB370 runs before the state
 *   machine) is the most of the game's G (+0x1B0 plus the term, no glide
 *   on the ride); F - low, F the first face
 *   under the centre (collision_sweep 0x60870 through the level's tree,
 *   mask 0x10, a face with flag bit 0 clear and a normal z over 0: the
 *   slopes and cliffs too, within player_model_hold_ray), low the lowest
 *   posed bone x the drawn scale less player_model_hold_margin (the
 *   mesh under that bone and a tick of the pose: the posed bones are the
 *   last drawn); the last tick's D less a step (the release eased); and,
 *   after a ride tick, for every tick k = 1..player_model_hold_ahead
 *   ahead F at the centre advanced k ticks along its last motion less
 *   low and k steps (the rise begins early enough, every future tick
 *   sampled).  It rises no more than a step a tick over the last D
 *   unless G does.  Ride tick 1, after hang_start's last, takes that
 *   tick's drawn height as its last (its release and cap) with no
 *   lookahead (its motion would be hang_start's).  D less the term into
 *   +0x1B0 and +0x1BC.
 *
 *   c_player_model_hang_hold_setup, at hang_start's set-up (0x8A480's
 *   CALL of 0x8C080 at 0x8A4F0, right after 0x42430 started the glide
 *   at 0x8A4E3, X9's landing there), the tick drawn first (h1), and
 *   c_player_model_hang_hold_tick, at hang_start's every later tick (the
 *   dispatcher 0x8CFA0's state-0x105 case at 0x8D091, reached only
 *   there: mov ebp,[ebp+0x30]; test ebp,ebp, replayed, then RET to
 *   0x8D096, whose JE reads the test): the glide 0x42070 draws (+0x1B0
 *   to +0x1BC) is held by an offset added to both ends, taken off again
 *   first each tick (no ratchet: the ends carry this tick's offset only,
 *   a carry 0x43170 adds after it on its own).  G is 0x42070's blend of
 *   the game's ends plus the term, j the tick (0 at the set-up, then the clock's ticks
 *   since it), low the least of the table's entry j and the live low
 *   above, and D the most of G, F - low and the last D less a step,
 *   at most a step over the last D unless G is higher (the set-up's last
 *   is G, where the stance was drawn).  The table (the build's, one
 *   float a tick, m) is the lowest drawn point the pose reaches at j or
 *   any later tick up to the ride's eighth less a step a tick to it:
 *   the crossfade from whatever the player was in at the grab (every
 *   phase of its idle, walk, run, jump and fall clips) into hang_start's
 *   clip, that clip, and the crossfade into the hang; so the hold rises
 *   early, a step a tick, to clear a dip before it comes (guard_air own
 *   x2's 3.1 m at h4 risen to from h1).  Which table (Step 2.175b,
 *   AZ-574): at the set-up the grab's own prior picks it, the anim layer
 *   other than the active one (the new clip's) with the most weight: its
 *   clip's length matched against player_model_hold_priors' keys (the
 *   build's prior clips) and the phase of its time over that length in
 *   twelfths, that prior's table for that twelfth (the crossfade from
 *   those phases alone); no match, the least over every prior and phase
 *   (player_model_hold_table).  So a grab from a prior that doesn't dip
 *   isn't held up for one that does (firedrake own x2: from its idle
 *   2.1 m clear, from its fly at phase 0.37 4.3 m under its origin;
 *   sitting 2.175b's frames matched the crossfade from its idle at
 *   t 0.567 to 1 mm), and the build installs X28 on a hang no deeper than
 *   garret4's where some grab's hang_start would take the drawn body
 *   through the floor it grabs from, past where its ground clips draw it
 *   (overlord own x2's glide 0.49 m).
 *
 * The ride's pose (Step 2.189b, AZ-713).  The live bones are the last
 * drawn pose, a tick late, so the ride held the lowest bone over the
 * floor by player_model_hold_margin (a tick of the pose's fastest move)
 * and moved the drawn origin at most a step a tick; a hang clip that
 * bobs (key_air1 own x2's idle at X12's x16, 8 m a loop, 1.2 m a tick)
 * then rode up to 7.7 m over f3's start platform, its top 4.7 m over the
 * cable, where the body fits under it (sitting 2.175b): the margin, the
 * tick's lag and an origin that may come down only a step a tick while
 * the pose rises faster.  Where the build writes player_model_hold_loop
 * (the hang clip's float32 length, then its lowest drawn point over the
 * origin at 64 times over its loop: the build's pose model, the mesh of
 * a one-bone rig, less the sole, x the drawn scale), a ride tick whose
 * active anim layer plays that clip at full weight (the crossfade into
 * it done) takes its pose there, at the layer's time as the landing
 * reads it (0xCB370 updated it before the state machine; X28's
 * hang_start frames matched the layers so read to 1 mm, sitting 2.175b),
 * with no margin; else the live bones less the margin, as before.  And the steps are on the drawn lowest point (the origin
 * plus that pose), not the origin: over a floor under the centre it
 * comes down at most a step a tick, and it rises at most a step a tick
 * unless the game's is higher, the floors ahead held k steps under, so
 * the hold moves the origin against the pose as fast as the pose moves
 * and the drawn body stays on the floor while the hang bobs; with no
 * floor within the ray the drawn origin comes down a step a tick, as
 * before, so the bob comes back.  Ride tick 1 still starts from hang_start's
 * last drawn height.  The live bones' lowest point, less the margin, and
 * the table's are apart by the margin and the live pose's lag (a drawn
 * frame can be two ticks old), so a tick that switches between them (the
 * crossfade into the hang clip done, or another clip) steps the drawn
 * origin from the last, as ride tick 1 does, and the next steps the
 * lowest point again: stepped from the live tick's lowest point the
 * switch dropped key_air1 own x2 4.57 m in a tick at ride tick 9 over f3's
 * start platform, guard_air own x2 2.03 m at ride tick 2, and less the
 * lag 2.98 m (sitting 2.189b and its record sitting).
 *
 * Known poses, no margin (Step 2.199, AZ-713).  The ride's anim change
 * crosses into the hang clip over its first 7.5 ticks, so the hang
 * layer's weight stays under FADED and the ride held the live bones less
 * the margin there, and hang_start held the least of its table and the
 * live bones less the margin on every tick: key_air1 own x2 (its margin
 * 2.42 m) left hang_start 3.27 m over f3's start platform and rose to
 * 4.95 m on the ride's first ticks, its top up to 4.26 m over the cable
 * on ride ticks 1-14, where the body fits under it (Step 2.189b's record
 * sitting).  Where the build writes player_model_hold_cross (hang_start's
 * clip's float32 length, its time at the ride's first tick and its rate,
 * then the lowest drawn point of the crossfade at each of its 8 ticks), a
 * ride tick whose active layer fades the hang clip in while the one other
 * playing layer holds hang_start's clip at that tick's time takes its
 * pose from that table, the tick read from the hang layer's weight
 * (0xCAD40 starts it at 0.01, the update adds dt / 0.25 s a tick), no
 * margin; and hang_start, once its active layer plays alone (the prior's
 * crossfade done: 0x42430 starts its clip from t 0 on a layer of its
 * own), holds by its table alone, which is that clip's pose at its own
 * time less a step a tick to every dip ahead, the ride's first ticks
 * included.  Which way the ride starts the hang clip where it is
 * hang_start's (an X9 stand-in X11 also gave the hang slot) is the
 * layers': 0xCAD40's loop (0xCAE20) takes the first layer whose clip is
 * the new one, so where hang_start's layer comes first the ride goes on
 * there (guard_air's and water_tentacle1's own x2 rides) and where a
 * layer before it held that clip (the grab's prior, freed by now) the
 * ride restarts it there from t 0 with a fade-in (key_air1's: sitting
 * 2.189b's frames to 1 mm).  The table is the first way; the build
 * writes the second's dips ahead of each hang_start tick after
 * player_model_hold_cross's crossfade, which hang_start takes too where a
 * layer before its own holds its clip (crosses): a table of both ways
 * rose guard_air own x2 1.1 m off f3's start platform over hang_start's
 * last two ticks for a crossfade its ride doesn't play (the record seat's
 * sitting).  The live bones less the margin stay for the prior's
 * crossfade and anything else.
 *
 * It only raises the drawn body: the centre, +0x168, collision, state
 * and timing stay the game's.
 *
 * ABI.  0x8AB3F and 0x8A4F0: EAX the PlayerControl, two stack arguments,
 * RET 8; 0x8C080 reads no ECX or EDX before writing them; the stubs keep
 * EAX for it.  0x8D091: EBP the PlayerControl, EAX dead (the caller at
 * 0x8C37D overwrites it); the stub keeps every register but EBP, which
 * the replay sets.  All keep EBX, ESI, EDI and EBP (the C helpers are
 * cdecl) and leave the x87 stack empty; collision_sweep is
 * __stdcall(36), AL its answer; glide_origin __stdcall(8);
 * aligned_node_offset EAX the critter, EDI the out, a plain RET (keeps
 * EBX, ESI, EDI and EBP).
 */

#include "azurik_vanilla.h"   /* and azurik.h: AZURIK_FLOAT_PARAM */

#define PC_CLOCK     0x00C   /* PlayerControl -> its clock (+0x10 its time) */
#define PC_CRITTER   0x020   /* PlayerControl -> its critter              */
#define CK_TIME      0x010   /* the clock: its time, a double (s)          */
#define CR_LEVEL     0x154   /* critter -> its level (+0xAC: the tree)     */
#define CR_CENTRE    0x15C   /* critter: its body centre (x, y, z)        */
#define CR_SPECIES   0x178   /* critter -> its species                    */
#define CR_ANIM      0x17C   /* critter -> its anim object                */
#define CR_SCALE     0x188   /* critter: its drawn scale D                */
#define CR_MODE      0x19C   /* critter: 0x42E40's glide mode, 0 none      */
#define CR_ORIGIN    0x1B0   /* critter: the drawn origin (a glide's start) */
#define CR_GLIDE_END 0x1BC   /* critter: a glide's end, the origin at rest */
#define AN_BODY      0x000   /* anim object -> its body (+0: its bones)    */
#define AN_BONES     0x008   /* anim object -> its posed bones            */
#define BONE_SIZE    0xB0    /* one posed bone                            */
#define BONE_Z       0xA8    /* its matrix's translation z (model units)   */
#define LV_TREE      0x0AC   /* level -> its collision tree               */
#define SP_FLAGS     0x064   /* species: its kind flags                    */
#define PLAYER_FLAG  0x20    /* the `player` feature                      */
#define FLOOR_MASK   0x10    /* 0x8AE10's faces                           */
#define HIT_SIZE     0x50    /* collision_sweep writes 0x48 bytes on a hit */
#define HIT_NORMAL_Z 0x14    /* hit: its normal's z                        */
#define HIT_FRACTION 0x18    /* hit: its fraction of the way               */
#define HIT_FLAGS    0x20    /* hit: its flags (bit 0: not a floor)        */
#define LAST_FOR     0.1     /* the last tick's state counts this long (s) */
#define TICKS        22      /* hang_start's ticks (garret4's 0.7333 s)    */
#define PRIORS       8       /* the prior clips' tables, by their length    */
#define PHASES       12      /* each prior's tables by its phase             */
#define AN_ACTIVE    0x010   /* anim: the active layer's index             */
#define AN_LAYERS    0x040   /* anim: three 0x40-byte layers               */
#define N_LAYERS     3
#define LY_CLIP      0x004   /* layer: its clip ('banm')                   */
#define LY_FLAGS     0x008   /* layer: 0 free                              */
#define LY_TIME      0x018   /* layer: its time, clip s                    */
#define LY_WEIGHT    0x01C   /* layer: its blend weight                    */
#define LOOP         64      /* the hang clip's table: its times over the loop */
#define FADED        0.999f  /* a layer weighed this much has crossed in     */
#define FADE_FROM    0.01f   /* 0xCAD40 starts a layer at this weight      */
#define FADE_TICKS   7.5f    /* and the update adds 1 / FADE_TICKS a tick  */
#define RIDE_FADE    8       /* the ride's crossfade ticks the build tables */
#define CLIP_LENGTH  0x010   /* banm: its length, s                        */
#define TICK_HZ      30.0

#define NONE         0
#define HANG_START   1
#define RIDE         2

/* The ray's length under a point (the span + the margin + 2 m), the
 * margin under the lowest bone (m), how many ticks ahead the ride's
 * lookahead samples, and the step (m), written by the build. */
AZURIK_FLOAT_PARAM(player_model_hold_ray, 0.0f);
AZURIK_FLOAT_PARAM(player_model_hold_margin, 0.0f);
AZURIK_FLOAT_PARAM(player_model_hold_ahead, 0.0f);
AZURIK_FLOAT_PARAM(player_model_hold_step, 0.847f);

/* The state block's address (the ride landing's; 0 there: its own), and
 * hang_start's table, one float a tick: the lowest drawn point (m, under
 * the origin negative) the pose reaches then or later less a step a tick
 * to it.  Both written by the build. */
volatile const unsigned player_model_hold_shared __attribute__((used, section(".rdata"))) = 0;
volatile const float player_model_hold_table[TICKS] __attribute__((used, section(".rdata"))) = {0.0f};
/* The hang clip's float32 length (0: none), then its lowest drawn point
 * over the origin (m) at LOOP times evenly over its loop, written by the
 * build. */
volatile const float player_model_hold_loop[1 + LOOP] __attribute__((used, section(".rdata"))) = {0.0f};
/* hang_start's clip's float32 length (0: none), its time at the ride's
 * first tick and its rate, then the lowest drawn point over the origin
 * (m) at each tick of the ride's crossfade from it into the hang clip,
 * then per hang_start tick those dips ahead of it as its table takes a
 * dip, written by the build. */
volatile const float player_model_hold_cross[3 + RIDE_FADE + TICKS] __attribute__((used, section(".rdata"))) = {0.0f};
/* The prior clips' lengths (0: none), then per prior and phase twelfth a
 * table as player_model_hold_table, written by the build. */
volatile const float player_model_hold_priors[PRIORS + PRIORS * PHASES * TICKS]
    __attribute__((used, section(".rdata"))) = {0.0f};

struct hold {
    double time;        /* the PlayerControl's clock at the last write  */
    double t0;          /* hang_start's set-up time                      */
    const char *critter;
    int phase;          /* NONE, HANG_START, RIDE                        */
    float z;            /* the drawn origin's height then (the glide
                           origin plus 0x402E0's term)                   */
    float centre[3];
    float offset;       /* what hang_start's last tick added to the ends */
    int pick;           /* the table: prior x PHASES + phase, -1 the least */
    float low;          /* the ride's: its pose's lowest point under the origin then */
    float margin;       /* the ride's: the margin that low took off (0: the clip's table) */
};

struct hold player_model_hold_state;

static struct hold *state(void)
{
    unsigned at = player_model_hold_shared;

    return at ? (struct hold *)at : &player_model_hold_state;
}

static char *player_critter(const char *control)
{
    char *critter = control ? *(char *const *)(control + PC_CRITTER) : 0;
    const char *species = critter ? *(const char *const *)(critter + CR_SPECIES) : 0;

    return species && (*(const unsigned *)(species + SP_FLAGS) & PLAYER_FLAG) ? critter : 0;
}

static void *tree_of(const char *critter)
{
    const char *level = *(const char *const *)(critter + CR_LEVEL);

    return level ? *(void *const *)(level + LV_TREE) : 0;
}

/* The PlayerControl's clock time into *now; 0: no clock. */
static int clock_of(const char *control, double *now)
{
    const char *clock = *(const char *const *)(control + PC_CLOCK);

    *now = clock ? *(const double *)(clock + CK_TIME) : 0.0;
    return clock != 0;
}

/* How far under the drawn origin's height the floor may be: the lowest
 * posed bone (m, D x model units; negative under the origin) less the
 * margin; 0 bones: the origin itself. */
static float under(const char *critter)
{
    const char *anim = *(const char *const *)(critter + CR_ANIM);
    const char *bones = anim ? *(const char *const *)(anim + AN_BONES) : 0;
    const char *body = anim ? *(const char *const *)(anim + AN_BODY) : 0;
    int n = body ? *(const int *)body : 0, b;
    float low = 0.0f, z;

    if (bones)
        for (b = 0; b < n; b++) {
            z = *(const float *)(bones + BONE_SIZE * b + BONE_Z);
            if (b == 0 || z < low)
                low = z;
        }
    return low * *(const float *)(critter + CR_SCALE) - player_model_hold_margin;
}

/* term := 0x402E0's aligned-node term for critter, which the draw adds
 * to the glide origin (0x42200's CALL at 0x42253, unscaled). */
__attribute__((naked, noinline, used))
static void node_offset(const char *critter, float *term)
{
    __asm__ volatile (
        "pushl %%edi             \n\t"
        "movl 0x8(%%esp), %%eax  \n\t"   /* the critter */
        "movl 0xc(%%esp), %%edi  \n\t"   /* the term    */
        "calll _aligned_node_offset \n\t"
        "popl %%edi              \n\t"
        "retl                    \n\t"
        : : : "memory"
    );
}

/* The term's height this tick: the layers' weights and times are this
 * tick's at the landings (0xCB370 ran before the state machine at
 * 0x8C346), as the draw reads them. */
static float node_z(const char *critter)
{
    float term[3] = {0.0f, 0.0f, 0.0f};

    node_offset(critter, term);
    return term[2];
}

/* *z := the first floor under at within the ray (any slope); 0: none. */
static int floor_under(const char *critter, void *tree, const float *at, float *z)
{
    float from[3], to[3], ray = player_model_hold_ray;
    unsigned hit[HIT_SIZE / 4];
    unsigned char *flags = (unsigned char *)hit + HIT_FLAGS;
    int k;

    for (k = 0; k < 3; k++)
        from[k] = to[k] = at[k];
    to[2] -= ray;
    for (k = 0; k < HIT_SIZE / 4; k++)
        hit[k] = 0;
    flags[1] = 0x80;   /* as 0x8AE10: the word 0x8000, then 0, 0xCC */
    flags[3] = 0xCC;
    if (!collision_sweep(tree, (void *)critter, 0, from, to, 0.0f, 0.0f, FLOOR_MASK, hit))
        return 0;
    if ((flags[0] & 1) || !(*(const float *)((const char *)hit + HIT_NORMAL_Z) > 0.0f))
        return 0;
    *z = from[2] - ray * *(const float *)((const char *)hit + HIT_FRACTION);
    return 1;
}

/* The table the grab's prior picks at the set-up: the anim layer other
 * than the active one with the most weight, its clip's length one of the
 * build's priors, its phase in PHASES; -1 none (the least table). */
static int prior_pick(const char *critter)
{
    const char *anim = *(const char *const *)(critter + CR_ANIM), *layer, *best = 0, *clip;
    float w, most = 0.0f, length, phase;
    int n, active, k, b;

    if (!anim)
        return -1;
    active = *(const int *)(anim + AN_ACTIVE);
    for (n = 0; n < N_LAYERS; n++) {
        layer = anim + AN_LAYERS + AN_LAYERS * n;
        if (n == active || !*(const int *)(layer + LY_FLAGS) || !*(const char *const *)(layer + LY_CLIP))
            continue;
        w = *(const float *)(layer + LY_WEIGHT);
        if (w > most) {
            most = w;
            best = layer;
        }
    }
    if (!best)
        return -1;
    clip = *(const char *const *)(best + LY_CLIP);
    length = *(const float *)(clip + CLIP_LENGTH);
    if (!(length > 0.0f))
        return -1;
    for (k = 0; k < PRIORS && player_model_hold_priors[k] != length; k++)
        ;
    if (k == PRIORS)
        return -1;
    phase = *(const float *)(best + LY_TIME) / length;
    phase -= (float)(int)phase;
    if (phase < 0.0f)
        phase += 1.0f;
    b = (int)(phase * PHASES);
    if (b < 0)
        b = 0;
    if (b > PHASES - 1)
        b = PHASES - 1;
    return k * PHASES + b;
}

/* The state the last tick left for this critter, if it counts now (a
 * clock, the same critter, within LAST_FOR, later, or this very tick
 * after hang_start's). */
static int kept(const struct hold *s, const char *critter, int have, double now)
{
    double dt = now - s->time;

    return have && s->critter == critter && s->phase != NONE && dt < LAST_FOR
        && (dt > 0.0 || (dt == 0.0 && s->phase == HANG_START));
}

/* *low := the hang clip's lowest drawn point under the origin (m) at the
 * active layer's time (this tick's: 0xCB370 ran before the state
 * machine), from the build's table; 0: no table, another clip, or the
 * crossfade into it not done. */
static int loop_low(const char *critter, float *low)
{
    const char *anim = *(const char *const *)(critter + CR_ANIM), *layer, *clip;
    float length = player_model_hold_loop[0], t, f;
    int i;

    if (!anim || !(length > 0.0f))
        return 0;
    layer = anim + AN_LAYERS + AN_LAYERS * *(const int *)(anim + AN_ACTIVE);
    clip = *(const char *const *)(layer + LY_CLIP);
    if (!*(const int *)(layer + LY_FLAGS) || !clip || *(const float *)(clip + CLIP_LENGTH) != length
            || !(*(const float *)(layer + LY_WEIGHT) >= FADED))
        return 0;
    t = *(const float *)(layer + LY_TIME) / length;
    t -= (float)(int)t;
    if (t < 0.0f)
        t += 1.0f;
    f = t * LOOP;
    i = (int)f;
    if (i > LOOP - 1)
        i = LOOP - 1;
    f -= (float)i;
    *low = player_model_hold_loop[1 + i] * (1.0f - f) + player_model_hold_loop[1 + (i + 1) % LOOP] * f;
    return 1;
}

/* 1: no anim layer but the active one plays (a crossfade into it done). */
static int alone(const char *critter)
{
    const char *anim = *(const char *const *)(critter + CR_ANIM), *layer;
    int n, active;

    if (!anim)
        return 0;
    active = *(const int *)(anim + AN_ACTIVE);
    for (n = 0; n < N_LAYERS; n++) {
        layer = anim + AN_LAYERS + AN_LAYERS * n;
        if (n != active && *(const int *)(layer + LY_FLAGS) && *(const float *)(layer + LY_WEIGHT) > 0.0f)
            return 0;
    }
    return 1;
}

/* 1: the ride will restart hang_start's clip on a layer of its own (a
 * crossfade): the hang clip is hang_start's (by the build's lengths) and
 * a layer before the active one holds it, so 0xCAD40's loop takes that
 * one first. */
static int crosses(const char *critter)
{
    const char *anim = *(const char *const *)(critter + CR_ANIM), *clip;
    float from = player_model_hold_cross[0];
    int n, active;

    if (!anim || !(from > 0.0f) || from != player_model_hold_loop[0])
        return 0;
    active = *(const int *)(anim + AN_ACTIVE);
    if (active < 0 || active >= N_LAYERS)
        return 0;
    clip = *(const char *const *)(anim + AN_LAYERS + AN_LAYERS * active + LY_CLIP);
    if (!clip || *(const float *)(clip + CLIP_LENGTH) != from)
        return 0;
    for (n = 0; n < active; n++)
        if (*(const char *const *)(anim + AN_LAYERS + AN_LAYERS * n + LY_CLIP) == clip)
            return 1;
    return 0;
}

/* *low := the ride's crossfade into the hang clip at this tick, from the
 * build's table: the active layer fades the hang clip in (its weight the
 * tick: FADE_FROM, then 1 / FADE_TICKS more a tick) and the one other
 * playing layer holds hang_start's clip at that tick's time (within a
 * tick); 0: no table, or another crossfade. */
static int cross_low(const char *critter, float *low)
{
    const char *anim = *(const char *const *)(critter + CR_ANIM), *layer, *other = 0, *clip;
    float length = player_model_hold_loop[0], from = player_model_hold_cross[0], w, t, d;
    int n, k, active;

    if (!anim || !(length > 0.0f) || !(from > 0.0f))
        return 0;
    active = *(const int *)(anim + AN_ACTIVE);
    for (n = 0; n < N_LAYERS; n++) {
        layer = anim + AN_LAYERS + AN_LAYERS * n;
        if (n == active || !*(const int *)(layer + LY_FLAGS))
            continue;
        if (other)
            return 0;   /* a third layer: not the ride's own crossfade */
        other = layer;
    }
    layer = anim + AN_LAYERS + AN_LAYERS * active;
    clip = *(const char *const *)(layer + LY_CLIP);
    w = *(const float *)(layer + LY_WEIGHT);
    if (!other || !*(const int *)(layer + LY_FLAGS) || !clip || *(const float *)(clip + CLIP_LENGTH) != length
            || !(w < FADED))
        return 0;
    clip = *(const char *const *)(other + LY_CLIP);
    if (!clip || *(const float *)(clip + CLIP_LENGTH) != from)
        return 0;
    k = (int)((w - FADE_FROM) * FADE_TICKS + 0.5f);
    if (k < 0)
        k = 0;
    if (k > RIDE_FADE - 1)
        k = RIDE_FADE - 1;
    t = player_model_hold_cross[1] + (float)k * player_model_hold_cross[2] / (float)TICK_HZ;
    if (t > from)
        t = from;
    d = *(const float *)(other + LY_TIME) - t;
    if (d < 0.0f)
        d = -d;
    if (d > player_model_hold_cross[2] / (float)TICK_HZ + 0.001f)
        return 0;
    *low = player_model_hold_cross[3 + k];
    return 1;
}

/* The ride (state 5), after 0x42E40 placed the drawn origin. */
__attribute__((used))
void hang_hold_ride(const char *control)
{
    char *critter = player_critter(control);
    struct hold *s = state();
    void *tree;
    float *centre, *start, *end, at[3], v[3], g, tz, want, cap, low, z, lg, lw, ll, m, step = player_model_hold_step;
    double now;
    int k, n, have, last, over;

    if (!critter || *(const int *)(critter + CR_MODE) != 0 || !(player_model_hold_ray > 0.0f))
        return;
    tree = tree_of(critter);
    if (!tree)
        return;
    have = clock_of(control, &now);
    centre = (float *)(critter + CR_CENTRE);
    start = (float *)(critter + CR_ORIGIN);
    end = (float *)(critter + CR_GLIDE_END);
    tz = node_z(critter);
    g = start[2] + tz;   /* the game's drawn height */
    m = 0.0f;
    if (!loop_low(critter, &low) && !cross_low(critter, &low)) {
        low = under(critter);
        m = player_model_hold_margin;
    }
    lg = g + low;        /* the game's drawn lowest point */
    lw = lg;
    over = floor_under(critter, tree, centre, &z);
    if (over && z > lw)
        lw = z;
    last = kept(s, critter, have, now);
    if (last) {
        /* the last drawn lowest point; a tick that switches between the clip's table and the live bones
         * (their lowest points apart by the margin and the live pose's lag) steps the drawn origin from
         * the last, as ride tick 1 steps from hang_start's last drawn height */
        ll = s->z + (s->phase == RIDE && s->margin == m ? s->low : low);
        if (over && ll - step > lw)   /* over a floor the drawn lowest point comes down a step a tick */
            lw = ll - step;
        else if (!over && s->z - step + low > lw)
            lw = s->z - step + low;   /* with none the drawn origin comes down a step a tick, as before */
        if (s->phase == RIDE) {
            for (k = 0; k < 3; k++)
                v[k] = centre[k] - s->centre[k];
            n = (int)player_model_hold_ahead;
            for (k = 1; k <= n; k++) {
                at[0] = centre[0] + k * v[0];
                at[1] = centre[1] + k * v[1];
                at[2] = centre[2] + k * v[2];
                if (floor_under(critter, tree, at, &z) && z - k * step > lw)
                    lw = z - k * step;
            }
        }
        cap = ll + step;
        if (lw > cap)
            lw = cap > lg ? cap : lg;
    }
    want = lw - low;
    if (want > g)
        start[2] = end[2] = want - tz;
    s->time = now;
    s->critter = critter;
    s->phase = RIDE;
    s->z = want;
    s->low = low;
    s->margin = m;
    for (k = 0; k < 3; k++)
        s->centre[k] = centre[k];
    s->offset = 0.0f;
}

/* hang_start's tick j (0 the set-up): the glide's ends carry the hold's
 * offset, this tick's only. */
static void hold_start(const char *control, int setup)
{
    char *critter = player_critter(control);
    struct hold *s = state();
    void *tree;
    float *centre, *start, *end, at[3], g, tz, want, cap, low, live, z, last, off, step = player_model_hold_step;
    double now, t0;
    int k, j, have, mine, valid, pick;

    if (!critter || !(player_model_hold_ray > 0.0f))
        return;
    have = clock_of(control, &now);
    centre = (float *)(critter + CR_CENTRE);
    start = (float *)(critter + CR_ORIGIN);
    end = (float *)(critter + CR_GLIDE_END);
    mine = !setup && s->critter == critter && s->phase == HANG_START;
    if (mine) {   /* the last tick's offset off the ends first */
        start[2] -= s->offset;
        end[2] -= s->offset;
    }
    glide_origin(critter, at);
    tz = node_z(critter);
    g = at[2] + tz;   /* the game's drawn height: in a crossfade into the clip the term moves */
    valid = mine && kept(s, critter, have, now);
    t0 = mine ? s->t0 : now;
    j = (int)((now - t0) * TICK_HZ + 0.5);
    if (j < 0)
        j = 0;
    if (j > TICKS - 1)
        j = TICKS - 1;
    /* the set-up: the glide's start, where the stance was drawn (its own term none: on main h1 steps
     * from it by this tick's term alone, sitting 2.118c) */
    last = valid ? s->z : at[2];
    pick = setup ? prior_pick(critter) : mine ? s->pick : -1;
    low = pick >= 0 ? player_model_hold_priors[PRIORS + pick * TICKS + j] : player_model_hold_table[j];
    live = under(critter);
    if (live < low && !alone(critter))   /* the prior's crossfade: the live bones less the margin too */
        low = live;
    if (crosses(critter) && player_model_hold_cross[3 + RIDE_FADE + j] < low)
        low = player_model_hold_cross[3 + RIDE_FADE + j];   /* the ride's crossfade ahead */
    want = g;
    tree = tree_of(critter);
    if (tree && floor_under(critter, tree, centre, &z) && z - low > want)
        want = z - low;
    if (last - step > want)
        want = last - step;
    cap = last + step;
    if (want > cap)
        want = cap > g ? cap : g;
    off = want - g;
    start[2] += off;
    end[2] += off;
    s->time = now;
    s->t0 = t0;
    s->critter = critter;
    s->phase = HANG_START;   /* its offset is in the ends: the next tick takes it off */
    s->pick = pick;
    s->z = want;
    for (k = 0; k < 3; k++)
        s->centre[k] = centre[k];
    s->offset = off;
}

__attribute__((used))
void hang_hold_setup(const char *control)
{
    hold_start(control, 1);
}

__attribute__((used))
void hang_hold_tick(const char *control)
{
    hold_start(control, 0);
}

/* 0x8AB3F: the ride's CALL of 0x8C080 (EAX the PlayerControl; two stack
 * arguments, RET 8). */
__attribute__((naked))
void c_player_model_hang_hold_ride(void)
{
    __asm__ volatile (
        "pushl %%eax              \n\t"   /* the PlayerControl, kept */
        "pushl %%eax              \n\t"
        "calll _hang_hold_ride    \n\t"
        "addl $4, %%esp           \n\t"
        "popl %%eax               \n\t"
        "jmp _player_landing@8    \n\t"
        : : : "memory"
    );
}

/* 0x8A4F0: hang_start's set-up's CALL of 0x8C080 (EAX the PlayerControl;
 * two stack arguments, RET 8). */
__attribute__((naked))
void c_player_model_hang_hold_setup(void)
{
    __asm__ volatile (
        "pushl %%eax              \n\t"   /* the PlayerControl, kept */
        "pushl %%eax              \n\t"
        "calll _hang_hold_setup   \n\t"
        "addl $4, %%esp           \n\t"
        "popl %%eax               \n\t"
        "jmp _player_landing@8    \n\t"
        : : : "memory"
    );
}

/* 0x8D091: hang_start's tick, then mov ebp,[ebp+0x30]; test ebp,ebp
 * and back (a CALL in: RET to 0x8D096, the flags the test's). */
__attribute__((naked))
void c_player_model_hang_hold_tick(void)
{
    __asm__ volatile (
        "pushl %%eax              \n\t"
        "pushl %%ecx              \n\t"
        "pushl %%edx              \n\t"
        "pushl %%ebp              \n\t"   /* the PlayerControl */
        "calll _hang_hold_tick    \n\t"
        "addl $4, %%esp           \n\t"
        "popl %%edx               \n\t"
        "popl %%ecx               \n\t"
        "popl %%eax               \n\t"
        "movl 0x30(%%ebp), %%ebp  \n\t"
        "testl %%ebp, %%ebp       \n\t"
        "retl                     \n\t"
        : : : "memory"
    );
}
