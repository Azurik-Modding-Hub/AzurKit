/* X22: a body drawn at a model scale eases off the zipline instead of
 * popping (Step 2.105, AZ-529's let-go and cable's end; D115's
 * defaults: the control's own let-go step a placement, no floor rays),
 * from where it was drawn, the aligned node's term in it (Step 2.175b,
 * AZ-600).
 *
 * Why.  X9's ride hangs a body drawn X times its size X times garret4's
 * grab under the cable (AZ-526), so its drawn origin (+0x1B0/+0x1BC,
 * which 0x42E40 sets to the point less the turned marker; the model is
 * drawn from it) rides 5.4-5.6 m under its collision centre (+0x15C) at
 * x2, where x1's rides 1.7-1.9 m under it.  The let-go (Y on the ride:
 * player_jump_init's state-5 branch places m_feet at the centre less
 * 1.0 m with the CALL 0x42E40 at 0x89290, then state 2) and the cable's
 * end (the ride returns 0; the same tick's player_airborne_tick places
 * m_feet there with the CALL at 0x8996D, every airborne tick) each put
 * the origin 1.0 m under the centre in one tick: 4.55-4.64 m at x2
 * (sitting 2.104: town_male_6 own, Balthazar own, kingkong at garret4's
 * height, Europe's golem own), the control's step 0.85 m.  The centre
 * never moves with the drawn body, so collision, the fall and its
 * timing don't change; only where the body is drawn.  And the body is
 * drawn at the origin plus 0x402E0's aligned-node term (critter_model_
 * matrix's CALL at 0x42253: the node +0x1F8 names in the top layer's
 * clip less in the blended pose), which the placement's new node and
 * the airborne clip's layer (started before it: anim_change at 0x89254
 * and 0x898B6) change in the same tick: a body with no clips, its root
 * riding garret4's m_feet / D, drew its frame 1.184 m lower on its first
 * airborne tick off the cable than the term-free ride (the term 0, then
 * -1.184, -1.026 ... 0 over 8 ticks), so it dropped 2.0 m in a tick
 * while the origin moved 0.79 (sitting 2.127 C, frag_air_1 own x1; at
 * X22's landing the airborne layer already on at 0.01, sitting 2.175b).
 *
 * What.  This shim takes the CALLs of 0x42E40 at 0x89290 (the let-go),
 * 0x8944E (the wing flap's, which places m_feet as the let-go does) and
 * 0x8996D (the airborne tick), one landing each, sharing the airborne
 * landing's state block (player_model_ease_shared, its address the
 * build writes after that landing).  Before the call it reads the
 * offset the body was drawn at: its origin (+0x1BC) less its centre,
 * plus the term the last placement left (the block's, kept 0.1 s for
 * the same critter; else 0 off the ride or the ladder, PlayerControl
 * +0x98 5 or 1, whose settled pose drew none: 0x402E0 now reads the
 * ride's node in the move's new clip, which keys no m_grab, so its rest
 * less its hang, garret4's 2.24 m under where it was drawn, the review's
 * F1; else 0x402E0's now);
 * it makes the game's call; then the game's drawn offset is the new
 * origin less the centre plus 0x402E0's new term, and when it lies more
 * than player_model_hang_step (0.847 m: the control's let-go step) from
 * the old one and no more than player_model_hang_span from it (|X - 1|
 * x garret4's hang grab, 3.693 m, plus 2 m: farther is a move no hang
 * makes), the drawn offset moves that step toward it and the origin
 * (+0x1B0 and +0x1BC) is put there less the new term.  So at x2 the
 * body eases from its hang to its stance over 6 placements (0.2 s at 30
 * ticks a second) and every later airborne tick is the game's.  The
 * term is kept for the next placement.  Only the player's species (flag
 * 0x20), and only a body that isn't gliding (+0x19C, 0x42E40's glide
 * mode, 0) before and after: a glide's origin isn't where it is drawn.
 * One tick runs at most one of the three (the state machine leaves the
 * tick after a let-go or a flap).  The build installs it on a body X9's
 * ride or hang landings serve drawn at a model scale other than 1.
 *
 * The landing (Step 2.189b, AZ-711).  A body that lands while this
 * object still eases it (key_air1 own x2 off the cable's end, 9.53 m
 * under its stance on the ease's 7th tick) was put at its stance by the
 * walk's placement (0x42E40 at 0x866D9, which this object doesn't take)
 * in one tick: a 9.53 m pop (sitting 2.175b).  A fourth landing, at the
 * walk's CALL of the classifier 0x85920 at 0x8672A right after that
 * placement, goes on with an ease the last placement left (the shared
 * block's: the same critter within LAST_FOR, its drawn offset not yet
 * the game's): the drawn offset moves a step from where the last
 * placement drew it toward the game's (the origin less the centre plus
 * 0x402E0's term), as the airborne landing does, until it is there.  A
 * walk with no ease left is the game's, and a jump from the ground reads
 * 0x402E0's term before its call as before (the walk's kept term isn't
 * used).
 *
 * The let-go's crossfade (Step 2.175b, AZ-569) is X48's (fade_floor.c,
 * Step 2.189b, AZ-711): held at the draw by the frame's pose, where this
 * object's table hold lifted the body up to 3.95 m over the floor and
 * left it 2.56 m over its stance when it landed inside the hold.
 *
 * ABI: 0x42E40 takes ECX (the turn), EAX (the new centre's buffer) and
 * four stack arguments (the critter, the blend time, the marker's name,
 * the point), RET 0x10; none of the three callers reads EAX, ECX or EDX
 * after it.  The stub keeps EBX, ESI, EDI and EBP and leaves the x87
 * stack empty; aligned_node_offset takes EAX the critter and EDI the
 * out, a plain RET (keeps EBX, ESI, EDI and EBP).  0x85920 takes ESI
 * (the PlayerControl) and three stack arguments (the walk's input, whose
 * +0 is the critter, the move result and the query), RET 0xC; its stub
 * calls the C part with the input, which keeps ESI, then jumps there.
 */

#include "azurik_vanilla.h"   /* and azurik.h: AZURIK_FLOAT_PARAM */

#define CR_CLOCK     0x0E4   /* critter -> its clock (+0x10 its time)      */
#define CK_TIME      0x010   /* the clock: its time, a double (s)          */
#define CR_CENTRE    0x15C   /* critter: its body centre (x, y, z)        */
#define CR_SPECIES   0x178   /* critter -> its species                    */
#define CR_MODE      0x19C   /* critter: 0x42E40's glide mode, 0 none      */
#define CR_ORIGIN    0x1B0   /* critter: the drawn origin (a glide's start) */
#define CR_GLIDE_END 0x1BC   /* critter: a glide's end, the origin at rest */
#define SP_FLAGS     0x064   /* species: its kind flags                    */
#define PLAYER_FLAG  0x20    /* the `player` feature                      */
#define LAST_FOR     0.1     /* the last placement's term counts this long (s) */
#define CR_CONTROL   0x180   /* critter -> its PlayerControl              */
#define PC_LAST      0x098   /* PlayerControl: the state its last tick started in */
#define RIDE_STATE   5       /* the zipline ride                          */
#define CLIMB_STATE  1       /* the ladder                                */

/* The most the drawn offset moves a placement, and the farthest new
 * offset it eases toward, metres (written by the build). */
AZURIK_FLOAT_PARAM(player_model_hang_step, 0.847f);
AZURIK_FLOAT_PARAM(player_model_hang_span, 0.0f);

/* The state block's address (the airborne landing's; 0 there: its
 * own), written by the build. */
volatile const unsigned player_model_ease_shared __attribute__((used, section(".rdata"))) = 0;

struct ease {
    double time;        /* the critter's clock at the last placement     */
    const char *critter;
    float term[3];      /* 0x402E0's term after it                       */
    float drawn[3];     /* the drawn offset it left (origin less centre plus term) */
    int easing;         /* 1: that offset isn't the game's (an ease goes on) */
    int ground;         /* 1: it was the walk's (its term isn't a jump's) */
};

struct ease player_model_ease_state;

static struct ease *state(void)
{
    unsigned at = player_model_ease_shared;

    return at ? (struct ease *)at : &player_model_ease_state;
}

static int is_player(const char *critter)
{
    const char *species = *(const char *const *)(critter + CR_SPECIES);

    return species && (*(const unsigned *)(species + SP_FLAGS) & PLAYER_FLAG) != 0;
}

static float root(float x)
{
    float r;

    __asm__("sqrtss %1, %0" : "=x"(r) : "x"(x));
    return r;
}

/* The critter's clock time into *now; 0: no clock. */
static int clock_of(const char *critter, double *now)
{
    const char *clock = *(const char *const *)(critter + CR_CLOCK);

    *now = clock ? *(const double *)(clock + CK_TIME) : 0.0;
    return clock != 0;
}

/* term := 0x402E0's aligned-node term for critter, which the draw adds
 * to the origin (0x42200's CALL at 0x42253, unscaled). */
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

/* o := the offset the body's origin is at; 0 while it glides. */
static int origin_offset(const char *critter, float *o)
{
    const float *centre = (const float *)(critter + CR_CENTRE);
    const float *end = (const float *)(critter + CR_GLIDE_END);
    int k;

    if (*(const int *)(critter + CR_MODE) != 0)
        return 0;
    for (k = 0; k < 3; k++)
        o[k] = end[k] - centre[k];
    return 1;
}

/* drawn := a step from was along d (the game's offset less was) where d is
 * longer than the step and no longer than the span; else as it is. */
static void ease_step(const float *was, const float *d, float *drawn)
{
    float step = player_model_hang_step, span = player_model_hang_span, far;
    int k;

    far = d[0] * d[0] + d[1] * d[1] + d[2] * d[2];
    if (step > 0.0f && far > step * step && far <= span * span) {
        far = step / root(far);
        for (k = 0; k < 3; k++)
            drawn[k] = was[k] + d[k] * far;
    }
}

/* The block keeps the drawn offset a placement left, whether it is off
 * the game's o, and whether the walk's placement left it. */
static void keep(struct ease *s, const float *drawn, const float *o, int ground)
{
    int k;

    s->easing = !(drawn[0] == o[0] && drawn[1] == o[1] && drawn[2] == o[2]);
    s->ground = ground;
    for (k = 0; k < 3; k++)
        s->drawn[k] = drawn[k];
}

/* Before the placement: was (x, y, z, 1) := the offset the player was
 * drawn at (its origin's plus the last term), else w 0. */
__attribute__((used))
void hang_ease_before(const char *critter, float *was)
{
    struct ease *s = state();
    const char *control;
    float term[3] = {0.0f, 0.0f, 0.0f};
    double now, dt;
    int k, last;

    was[3] = 0.0f;
    if (!critter || !is_player(critter) || !origin_offset(critter, was))
        return;
    control = *(const char *const *)(critter + CR_CONTROL);
    last = control ? *(const int *)(control + PC_LAST) : -1;
    dt = clock_of(critter, &now) ? now - s->time : -1.0;
    if (s->critter == critter && dt > 0.0 && dt < LAST_FOR && !s->ground)
        for (k = 0; k < 3; k++)
            term[k] = s->term[k];
    else if (last != RIDE_STATE && last != CLIMB_STATE)
        node_offset(critter, term);
    for (k = 0; k < 3; k++)
        was[k] += term[k];
    was[3] = 1.0f;
}

/* After the game's placement: the drawn offset a step from was toward
 * its, the term kept. */
__attribute__((used))
void hang_ease_after(char *critter, const float *was)
{
    struct ease *s = state();
    float *centre = (float *)(critter + CR_CENTRE);
    float *start = (float *)(critter + CR_ORIGIN);
    float *end = (float *)(critter + CR_GLIDE_END);
    float o[3], d[3], term[3] = {0.0f, 0.0f, 0.0f}, drawn[3];
    double now;
    int k;

    if (!(was[3] > 0.0f) || !origin_offset(critter, o))
        return;
    node_offset(critter, term);
    s->critter = clock_of(critter, &now) ? critter : 0;
    s->time = now;
    for (k = 0; k < 3; k++) {
        s->term[k] = term[k];
        o[k] += term[k];   /* the game's drawn offset */
        d[k] = o[k] - was[k];
        drawn[k] = o[k];
    }
    ease_step(was, d, drawn);
    keep(s, drawn, o, 0);
    if (!s->easing)
        return;
    for (k = 0; k < 3; k++)
        start[k] = end[k] = centre[k] + drawn[k] - term[k];
}

/* The walk's placement done (0x8672A, before the classifier): an ease the
 * last placement left goes on a step from where it drew the body. */
__attribute__((used))
void hang_ease_ground(const char *input)
{
    char *critter = input ? *(char *const *)input : 0;
    struct ease *s = state();
    float *centre, *start, *end;
    float o[3], d[3], term[3] = {0.0f, 0.0f, 0.0f}, drawn[3];
    double now;
    int k, going;

    if (!critter || !is_player(critter) || !clock_of(critter, &now) || !origin_offset(critter, o))
        return;
    going = s->critter == critter && now - s->time > 0.0 && now - s->time < LAST_FOR && s->easing;
    node_offset(critter, term);
    for (k = 0; k < 3; k++) {
        o[k] += term[k];   /* the game's drawn offset */
        d[k] = o[k] - s->drawn[k];
        drawn[k] = o[k];
    }
    if (going)
        ease_step(s->drawn, d, drawn);
    s->critter = critter;
    s->time = now;
    for (k = 0; k < 3; k++)
        s->term[k] = term[k];
    keep(s, drawn, o, 1);
    if (!s->easing)
        return;
    centre = (float *)(critter + CR_CENTRE);
    start = (float *)(critter + CR_ORIGIN);
    end = (float *)(critter + CR_GLIDE_END);
    for (k = 0; k < 3; k++)
        start[k] = end[k] = centre[k] + drawn[k] - term[k];
}

/* 0x89290, 0x8944E, 0x8996D: 0x42E40 (ECX the turn, EAX the centre's
 * buffer; the critter, the blend, the marker and the point; RET 0x10). */
__attribute__((naked))
void c_player_model_hang_ease(void)
{
    __asm__ volatile (
        "pushl %%eax              \n\t"   /* the centre's buffer   */
        "pushl %%ecx              \n\t"   /* the turn              */
        "subl $16, %%esp          \n\t"   /* was                   */
        "movl %%esp, %%eax        \n\t"
        "pushl %%eax              \n\t"
        "pushl 0x20(%%esp)        \n\t"   /* the critter           */
        "calll _hang_ease_before  \n\t"
        "addl $8, %%esp           \n\t"
        "pushl 0x28(%%esp)        \n\t"   /* the point             */
        "pushl 0x28(%%esp)        \n\t"   /* the marker            */
        "pushl 0x28(%%esp)        \n\t"   /* the blend             */
        "pushl 0x28(%%esp)        \n\t"   /* the critter           */
        "movl 0x20(%%esp), %%ecx  \n\t"
        "movl 0x24(%%esp), %%eax  \n\t"
        "calll _anim_apply_translation \n\t"
        "movl %%esp, %%eax        \n\t"
        "pushl %%eax              \n\t"   /* was                   */
        "pushl 0x20(%%esp)        \n\t"   /* the critter           */
        "calll _hang_ease_after   \n\t"
        "addl $0x20, %%esp        \n\t"
        "retl $0x10               \n\t"
        : : : "memory"
    );
}

/* 0x8672A: the walk's CALL of player_land_classify (ESI the PlayerControl;
 * the input, the move result and the query; RET 0xC), right after its
 * placement 0x42E40 at 0x866D9. */
__attribute__((naked))
void c_player_model_hang_ease_ground(void)
{
    __asm__ volatile (
        "pushl 0x4(%%esp)                    \n\t"   /* the input */
        "calll _hang_ease_ground             \n\t"
        "addl $4, %%esp                      \n\t"
        "jmp \"_player_land_classify@12\"    \n\t"
        : : : "memory"
    );
}
